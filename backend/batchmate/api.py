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
from .agents import coach as coach_agent
from .agents import curator, pattern, steward, verifier
from .agents import profile as profile_agent
from .auth import current_user
from .graph import Coach, _panel
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


def readable_errors(fn):
    """The routes run inside Gradio's FastAPI app on the Space, so an app-level exception handler on
    `api` is never called. Wrap each route instead: full traceback in the Space logs, and a readable
    reason in the UI instead of a bare 500."""
    import functools
    import traceback

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            traceback.print_exc()
            raise HTTPException(500, f"{fn.__name__} failed: {exc.__class__.__name__}: {str(exc)[:200]}")

    return wrapper


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
@readable_errors
def health():
    return {"ok": True}


@api.get("/topics")
@readable_errors
def topics():
    from .topics import TOPICS

    return {k: v["label"] for k, v in TOPICS.items()}


@api.get("/auth/config")
@readable_errors
def auth_config():
    """Who can sign in (ids and roles only) and whether a password is required."""
    return {"password_required": auth.auth_enabled(), "users": auth.list_users()}


@api.post("/auth/login")
@readable_errors
def login(req: LoginReq):
    token = auth.login(req.user.strip(), req.password)
    return {"token": token, "user": req.user.strip(), "role": auth.role(req.user.strip())}


@api.get("/system/status")
@readable_errors
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
@readable_errors
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
@readable_errors
def meko_log(limit: int = 50, since: float = 0, user: str = Depends(current_user)):
    """Every Meko call this server made: tool, datapack, ok, latency. Memory text and queries are
    redacted, so the feed proves Meko is working without leaking anyone's private memory."""
    from .memory.meko_client import CALL_LOG

    names = {}
    mem = get_memory()
    if hasattr(mem, "_dp"):
        names = {dp: mem.prefix + "-" + key for key, dp in mem._dp.items()}
    mine = f"student-{user}"

    def visible(name) -> bool:
        # Shared datapacks and lookups are fine; another student's private datapack never is.
        n = str(name or "")
        return "student-" not in n or n.endswith(mine) or n.endswith(mine + "-reports")

    rows = []
    for r in reversed(list(CALL_LOG)):
        if r["at"] <= since:
            continue
        name = names.get(r.get("datapack"), r.get("datapack"))
        if visible(name):
            rows.append({"at": r["at"], "tool": r["tool"], "ok": r["ok"], "ms": r["ms"],
                         "datapack": name, "note": r.get("note", "")[:120]})
        if len(rows) >= limit:
            break
    return rows


# ---------------- student ----------------
@api.get("/me")
@readable_errors
def me(user: str = Depends(current_user)):
    return {"user": user, "role": auth.role(user)}


@api.post("/sessions")
@readable_errors
def start(req: StartReq, user: str = Depends(current_user)):
    if user.startswith("coordinator"):
        raise HTTPException(403, "Mock interviews are for students")
    return coach.start(user, req.company, req.role, req.days_left, req.memory_on)


@api.post("/sessions/{sid}/answer")
@readable_errors
def answer(sid: str, req: AnswerReq, user: str = Depends(current_user)):
    if coach.owner(sid) != user:
        raise HTTPException(404, "No such session")
    return coach.answer(sid, req.text)


@api.get("/memory")
@readable_errors
def my_memory(user: str = Depends(current_user)):
    rows = get_memory().list(student_scope(user), user)
    return [m.to_dict() for m in rows if m.kind != "profile"]


@api.delete("/memory/{mid}")
@readable_errors
def forget(mid: str, user: str = Depends(current_user)):
    try:
        return {"forgotten": get_memory().forget(mid, user)}
    except AccessDenied as e:
        raise HTTPException(403, str(e))


@api.post("/memory/{mid}/fixed")
@readable_errors
def mark_fixed(mid: str, user: str = Depends(current_user)):
    """'I've fixed this' → resolved: kept for history, no longer recalled."""
    try:
        return get_memory().update(mid, requester=user, status="resolved").to_dict()
    except (AccessDenied, KeyError) as e:
        raise HTTPException(403, str(e))


@api.post("/experiences")
@readable_errors
def contribute(req: ExperienceReq, bg: BackgroundTasks, user: str = Depends(current_user)):
    mems, reason = curator.curate_report(req.text, req.company, req.role, req.interview_date.year,
                                         req.interview_date.isoformat(), names=req.names_to_strip + [user])
    if reason == "duplicate":
        raise HTTPException(409, "This exact experience was already shared, so it isn't counted twice.")
    if reason == "no_topics":
        raise HTTPException(422, "No interview topics found. Mention rounds and topics, "
                                 "like \"Round 2: LRU cache\".")
    bg.add_task(pattern.find_and_propose, req.company, req.role)  # new evidence → look for patterns now
    return [m.to_dict() for m in mems]


@api.get("/me/profile")
@readable_errors
def get_profile(user: str = Depends(current_user)):
    if user.startswith("coordinator"):
        raise HTTPException(403, "Profiles are for students")
    return profile_agent.get_profile(user).model_dump()


@api.put("/me/profile")
@readable_errors
def put_profile(req: profile_agent.Profile, user: str = Depends(current_user)):
    if user.startswith("coordinator"):
        raise HTTPException(403, "Profiles are for students")
    return profile_agent.save_profile(user, req).model_dump()


class AskReq(BaseModel):
    question: str


@api.post("/coach/ask")
@readable_errors
def ask_coach(req: AskReq, user: str = Depends(current_user)):
    """Answers only from what Meko recalls; returns the memories the answer used."""
    if user.startswith("coordinator"):
        raise HTTPException(403, "The coach is for students")
    q = req.question.strip()[:500]
    if not q:
        raise HTTPException(400, "Ask a question first")
    answer, used = coach_agent.ask(user, q)
    return {"answer": answer, "sources": _panel(used)}


@api.get("/me/opt-in")
@readable_errors
def get_opt_in(user: str = Depends(current_user)):
    return {"share_aggregate": steward.opted_in(user)}


@api.post("/me/opt-in")
@readable_errors
def set_opt_in(req: OptInReq, user: str = Depends(current_user)):
    """Explicit opt-in: weak TOPICS count anonymously, only in groups of 3+, toward batch lessons."""
    return {"share_aggregate": steward.set_opt_in(user, req.share_aggregate)}


# ---------------- coordinator ----------------
@api.get("/steward")
@readable_errors
def steward_status(user: str = Depends(coordinator_only)):
    return last_steward_run


@api.post("/steward/run")
@readable_errors
def steward_run(user: str = Depends(coordinator_only)):
    last_steward_run.update(steward.run_all())
    return last_steward_run


@api.post("/patterns/run")
@readable_errors
def run_patterns(company: str = "Amazon", role: str = "SDE intern", user: str = Depends(coordinator_only)):
    return [m.to_dict() for m in pattern.find_and_propose(company, role)]


@api.get("/patterns")
@readable_errors
def patterns(company: str = "Amazon", user: str = Depends(coordinator_only)):
    """All patterns for a company, any status, newest first (the coordinator's board)."""
    from .memory import SYSTEM, company_scope

    rows = get_memory().list(company_scope(company), SYSTEM, kinds=["pattern"])
    return [m.to_dict() for m in rows]


@api.get("/patterns/pending")
@readable_errors
def pending(company: str = "Amazon", user: str = Depends(coordinator_only)):
    return [m.to_dict() for m in pattern.pending(company)]


@api.post("/patterns/{mid}/{decision}")
@readable_errors
def decide(mid: str, decision: str, user: str = Depends(coordinator_only)):
    try:
        fn = {"approve": verifier.approve, "reject": verifier.reject}[decision]
        return fn(mid, user).to_dict()
    except KeyError:
        raise HTTPException(400, "decision must be approve or reject")
    except (AccessDenied, ValueError) as e:
        raise HTTPException(403, str(e))

