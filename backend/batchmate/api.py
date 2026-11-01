"""FastAPI backend.

Identity comes from a signed token (POST /auth/login) when DEMO_USERS is set; see auth.py.
Coordinators are users whose id starts with "coordinator".
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from datetime import date

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, config
from .agents import curator, pattern, steward, verifier
from .auth import current_user
from .graph import Coach
from .memory import AccessDenied, get_memory, student_scope

_stop = threading.Event()
last_steward_run: dict = {}


def _steward_loop():
    while not _stop.is_set():
        try:
            last_steward_run.update(steward.run_all())
        except Exception as e:  # keep the loop alive
            last_steward_run.update({"error": repr(e)})
        _stop.wait(config.STEWARD_INTERVAL_MIN * 60)


@asynccontextmanager
async def lifespan(_):
    if config.STEWARD_INTERVAL_MIN > 0:
        threading.Thread(target=_steward_loop, daemon=True, name="steward").start()
    yield
    _stop.set()


api = FastAPI(title="Batchmate", lifespan=lifespan)
# Only needed if the website calls the Space directly instead of through the Vercel /api rewrite.
api.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
coach = Coach()


def coordinator_only(user: str = Depends(current_user)) -> str:
    if not user.startswith("coordinator"):
        raise HTTPException(403, "Coordinators only")
    return user


class LoginReq(BaseModel):
    user: str
    password: str = ""


class StartReq(BaseModel):
    company: str = "Amazon"
    role: str = "SDE intern"
    days_left: int = 5
    memory_on: bool = True


class AnswerReq(BaseModel):
    text: str


class ExperienceReq(BaseModel):
    text: str
    company: str = "Amazon"
    role: str = "SDE intern"
    interview_date: date
    names_to_strip: list[str] = []


class OptInReq(BaseModel):
    share_aggregate: bool


# ---------------- public ----------------
@api.get("/health")
def health():
    return {"ok": True}


@api.get("/topics")
def topics():
    from .topics import TOPICS

    return {k: v["label"] for k, v in TOPICS.items()}


@api.get("/auth/config")
def auth_config():
    """Who can sign in (ids and roles only) and whether a password is required."""
    return {"password_required": auth.auth_enabled(), "users": auth.list_users()}


@api.post("/auth/login")
def login(req: LoginReq):
    token = auth.login(req.user.strip(), req.password)
    return {"token": token, "user": req.user.strip(), "role": auth.role(req.user.strip())}


@api.get("/system/status")
def system_status():
    """One call for the UI's status badges: memory backend, Meko connection, LLM provider."""
    from . import llm

    out = {"memory_backend": config.MEMORY_BACKEND, "llm": llm.probe()}
    if config.MEMORY_BACKEND == "meko":
        try:
            mem = get_memory()
            out["meko"] = {"connected": bool(mem.meko.list_tools()),
                           "datapacks": len(mem.list_scopes(""))}
        except Exception as e:
            out["meko"] = {"connected": False, "error": str(e)[:200]}
    return out


@api.get("/meko/status")
def meko_status():
    mem = get_memory()
    if config.MEMORY_BACKEND != "meko":
        return {"backend": config.MEMORY_BACKEND, "meko": False}
    try:
        tools = mem.meko.list_tools()
        packs = {s: mem.datapack_id(s, create=False) for s in mem.list_scopes("")}
        return {"backend": "meko", "meko": True, "tools": len(tools), "datapacks": packs}
    except Exception as e:
        return {"backend": "meko", "meko": False, "error": str(e)[:300]}


@api.get("/meko/log")
def meko_log(limit: int = 50, since: float = 0, user: str = Depends(current_user)):
    """Every Meko call this server made: tool, datapack, ok, latency. Memory text and queries are
    redacted, so the feed proves Meko is working without leaking anyone's private memory."""
    from .memory.meko_client import CALL_LOG

    names = {}
    mem = get_memory()
    if hasattr(mem, "_dp"):
        names = {dp: mem.prefix + "-" + key for key, dp in mem._dp.items()}
    rows = [r for r in list(CALL_LOG) if r["at"] > since][-limit:]
    return [{"at": r["at"], "tool": r["tool"], "ok": r["ok"], "ms": r["ms"],
             "datapack": names.get(r.get("datapack"), r.get("datapack")),
             "note": r.get("note", "")[:120]} for r in reversed(rows)]


# ---------------- student ----------------
@api.get("/me")
def me(user: str = Depends(current_user)):
    return {"user": user, "role": auth.role(user)}


@api.post("/sessions")
def start(req: StartReq, user: str = Depends(current_user)):
    if user.startswith("coordinator"):
        raise HTTPException(403, "Mock interviews are for students")
    return coach.start(user, req.company, req.role, req.days_left, req.memory_on)


@api.post("/sessions/{sid}/answer")
def answer(sid: str, req: AnswerReq, user: str = Depends(current_user)):
    if coach.owner(sid) != user:
        raise HTTPException(404, "No such session")
    return coach.answer(sid, req.text)


@api.get("/memory")
def my_memory(user: str = Depends(current_user)):
    rows = get_memory().list(student_scope(user), user)
    return [m.to_dict() for m in rows if m.kind != "profile"]


@api.delete("/memory/{mid}")
def forget(mid: str, user: str = Depends(current_user)):
    try:
        return {"forgotten": get_memory().forget(mid, user)}
    except AccessDenied as e:
        raise HTTPException(403, str(e))


@api.post("/memory/{mid}/fixed")
def mark_fixed(mid: str, user: str = Depends(current_user)):
    """'I've fixed this' → resolved: kept for history, no longer recalled."""
    try:
        return get_memory().update(mid, requester=user, status="resolved").to_dict()
    except (AccessDenied, KeyError) as e:
        raise HTTPException(403, str(e))


@api.post("/experiences")
def contribute(req: ExperienceReq, bg: BackgroundTasks, user: str = Depends(current_user)):
    mems = curator.curate(req.text, req.company, req.role, req.interview_date.year,
                          req.interview_date.isoformat(), names=req.names_to_strip + [user])
    if mems:  # new evidence → look for patterns right away
        bg.add_task(pattern.find_and_propose, req.company, req.role)
    return [m.to_dict() for m in mems]


@api.get("/me/opt-in")
def get_opt_in(user: str = Depends(current_user)):
    return {"share_aggregate": steward.opted_in(user)}


@api.post("/me/opt-in")
def set_opt_in(req: OptInReq, user: str = Depends(current_user)):
    """Explicit opt-in: weak TOPICS count anonymously, only in groups of 3+, toward batch lessons."""
    return {"share_aggregate": steward.set_opt_in(user, req.share_aggregate)}


# ---------------- coordinator ----------------
@api.get("/steward")
def steward_status(user: str = Depends(coordinator_only)):
    return last_steward_run


@api.post("/steward/run")
def steward_run(user: str = Depends(coordinator_only)):
    last_steward_run.update(steward.run_all())
    return last_steward_run


@api.post("/patterns/run")
def run_patterns(company: str = "Amazon", role: str = "SDE intern", user: str = Depends(coordinator_only)):
    return [m.to_dict() for m in pattern.find_and_propose(company, role)]


@api.get("/patterns")
def patterns(company: str = "Amazon", user: str = Depends(coordinator_only)):
    """All patterns for a company, any status, newest first (the coordinator's board)."""
    from .memory import SYSTEM, company_scope

    rows = get_memory().list(company_scope(company), SYSTEM, kinds=["pattern"])
    return [m.to_dict() for m in rows]


@api.get("/patterns/pending")
def pending(company: str = "Amazon", user: str = Depends(coordinator_only)):
    return [m.to_dict() for m in pattern.pending(company)]


@api.post("/patterns/{mid}/{decision}")
def decide(mid: str, decision: str, user: str = Depends(coordinator_only)):
    try:
        fn = {"approve": verifier.approve, "reject": verifier.reject}[decision]
        return fn(mid, user).to_dict()
    except KeyError:
        raise HTTPException(400, "decision must be approve or reject")
    except (AccessDenied, ValueError) as e:
        raise HTTPException(403, str(e))

