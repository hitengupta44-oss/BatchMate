"""FastAPI backend. Demo auth: the caller's id comes from the X-User header
(student id, or 'coordinator-<name>'). Swap for real auth before going beyond the hackathon."""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import date

import os

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, ratelimit
from .agents import curator, pattern, steward, verifier
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


def _guard(user: str):
    if not user:
        raise HTTPException(401, "X-User header required")
    if not ratelimit.allow(user):
        raise HTTPException(429, "Slow down: rate limit reached")


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


@api.get("/health")
def health():
    return {"ok": True}


@api.get("/topics")
def topics():
    from .topics import TOPICS

    return {k: v["label"] for k, v in TOPICS.items()}


@api.get("/meko/status")
def meko_status():
    """Is Meko connected? Which datapacks does Batchmate use?"""
    from .memory import get_memory

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
def meko_log(limit: int = 50):
    """The last Meko MCP calls this server made (tool, args, ok, latency): the visible-context feed."""
    from .memory.meko_client import CALL_LOG

    return list(CALL_LOG)[-limit:][::-1]


@api.post("/sessions")
def start(req: StartReq, x_user: str = Header("")):
    _guard(x_user)
    return coach.start(x_user, req.company, req.role, req.days_left, req.memory_on)


@api.post("/sessions/{sid}/answer")
def answer(sid: str, req: AnswerReq, x_user: str = Header("")):
    _guard(x_user)
    return coach.answer(sid, req.text)


@api.get("/memory")
def my_memory(x_user: str = Header("")):
    _guard(x_user)
    return [m.to_dict() for m in get_memory().list(student_scope(x_user), x_user)]


@api.delete("/memory/{mid}")
def forget(mid: str, x_user: str = Header("")):
    _guard(x_user)
    try:
        return {"forgotten": get_memory().forget(mid, x_user)}
    except AccessDenied as e:
        raise HTTPException(403, str(e))


@api.post("/memory/{mid}/fixed")
def mark_fixed(mid: str, x_user: str = Header("")):
    """'I've fixed this' → resolved: kept for history, no longer recalled."""
    _guard(x_user)
    try:
        return get_memory().update(mid, requester=x_user, status="resolved").to_dict()
    except AccessDenied as e:
        raise HTTPException(403, str(e))


@api.post("/experiences")
def contribute(req: ExperienceReq, bg: BackgroundTasks, x_user: str = Header("")):
    _guard(x_user)
    mems = curator.curate(req.text, req.company, req.role, req.interview_date.year,
                          req.interview_date.isoformat(), names=req.names_to_strip + [x_user])
    if mems:  # new evidence → look for patterns right away, coordinator sees proposals immediately
        bg.add_task(pattern.find_and_propose, req.company, req.role)
    return [m.to_dict() for m in mems]


class OptInReq(BaseModel):
    share_aggregate: bool


@api.get("/me/opt-in")
def get_opt_in(x_user: str = Header("")):
    _guard(x_user)
    return {"share_aggregate": steward.opted_in(x_user)}


@api.post("/me/opt-in")
def set_opt_in(req: OptInReq, x_user: str = Header("")):
    """Explicit opt-in: let your weak TOPICS count (anonymously, only in groups of 3+) toward batch lessons."""
    _guard(x_user)
    return {"share_aggregate": steward.set_opt_in(x_user, req.share_aggregate)}


@api.get("/steward")
def steward_status(x_user: str = Header("")):
    _guard(x_user)
    return last_steward_run


@api.post("/steward/run")
def steward_run(x_user: str = Header("")):
    _guard(x_user)
    if not x_user.startswith("coordinator"):
        raise HTTPException(403, "coordinators only")
    last_steward_run.update(steward.run_all())
    return last_steward_run


@api.post("/patterns/run")
def run_patterns(company: str = "Amazon", role: str = "SDE intern", x_user: str = Header("")):
    _guard(x_user)
    return [m.to_dict() for m in pattern.find_and_propose(company, role)]


@api.get("/patterns/pending")
def pending(company: str = "Amazon", x_user: str = Header("")):
    _guard(x_user)
    return [m.to_dict() for m in pattern.pending(company)]


@api.post("/patterns/{mid}/{decision}")
def decide(mid: str, decision: str, x_user: str = Header("")):
    _guard(x_user)
    try:
        fn = {"approve": verifier.approve, "reject": verifier.reject}[decision]
        return fn(mid, x_user).to_dict()
    except KeyError:
        raise HTTPException(400, "decision must be approve or reject")
    except AccessDenied as e:
        raise HTTPException(403, str(e))
