"""Steward: the autonomous maintenance agent. Runs on a timer and after every new experience.

1. Refresh patterns for every company/role (new reports → new proposals or updated counts).
2. Retire stale patterns: recency below threshold → status 'stale' (no longer recalled).
   If fresh reports later re-corroborate a stale pattern, it goes back to the coordinator.
3. Batch lessons: aggregate weakness topics across students who OPTED IN, counts only, no names,
   into batch-<year>. Below the k-anonymity threshold nothing is published.

It never approves anything: promotion stays a human decision.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .. import config
from ..memory import SYSTEM, Memory, batch_scope, get_memory, student_scope
from ..memory.base import now_iso, recency_weight
from ..topics import label
from . import pattern


# ---------------- opt-in ----------------
def _profile(student_id: str) -> Memory | None:
    rows = get_memory().list(student_scope(student_id), SYSTEM, kinds=["profile"])
    return rows[0] if rows else None


def set_opt_in(student_id: str, opt_in: bool) -> bool:
    mem, prof = get_memory(), _profile(student_id)
    if prof:
        mem.update(prof.id, requester=student_id, meta={**prof.meta, "share_aggregate": opt_in})
    else:
        mem.write(Memory(scope=student_scope(student_id), kind="profile", text="settings",
                         meta={"share_aggregate": opt_in}), requester=student_id)
    return opt_in


def opted_in(student_id: str) -> bool:
    prof = _profile(student_id)
    return bool(prof and prof.meta.get("share_aggregate"))


# ---------------- jobs ----------------
def refresh_patterns() -> int:
    mem, n = get_memory(), 0
    for scope in mem.list_scopes("company-"):
        exps = mem.list(scope, SYSTEM, kinds=["experience"])
        for company, role in {(e.meta["company"], e.meta["role"]) for e in exps}:
            n += len(pattern.find_and_propose(company, role))
    return n


def retire_stale() -> list[str]:
    mem, retired = get_memory(), []
    for scope in mem.list_scopes("company-"):
        for p in mem.list(scope, SYSTEM, kinds=["pattern"], statuses=("active",)):
            if recency_weight(p.observed_at) < config.STALE_RECENCY:
                mem.update(p.id, requester=SYSTEM, status="stale",
                           meta={**p.meta, "retired_at": now_iso()})
                retired.append(p.text)
    return retired


def batch_lessons(year: int | None = None) -> list[str]:
    year = year or datetime.now(timezone.utc).year
    mem, scope = get_memory(), batch_scope(year)
    counts: Counter = Counter()
    for s in mem.list_scopes("student-"):
        sid = s.removeprefix("student-")
        if not opted_in(sid):
            continue
        topics = {m.meta.get("topic") for m in mem.list(s, SYSTEM, kinds=["weakness"], statuses=("active",))}
        counts.update(t for t in topics if t)

    existing = {m.meta.get("topic"): m for m in mem.list(scope, SYSTEM, kinds=["lesson"])}
    published = []
    for topic, n in counts.items():
        if n < config.BATCH_MIN_STUDENTS:
            continue
        text = f"{n} students in your batch are also working on {label(topic)}. Shared drills help."
        if topic in existing:
            mem.update(existing[topic].id, requester=SYSTEM, text=text, source_count=n, status="active",
                       meta={**existing[topic].meta, "observed_at": now_iso()})
        else:
            mem.write(Memory(scope=scope, kind="lesson", text=text, source_count=n,
                             meta={"topic": topic, "observed_at": now_iso(), "aggregate": True}))
        published.append(text)
    for topic, m in existing.items():  # fell below threshold → withdraw
        if counts.get(topic, 0) < config.BATCH_MIN_STUDENTS and m.status == "active":
            mem.update(m.id, requester=SYSTEM, status="stale")
    return published


def sync_meko() -> int:
    mem = get_memory()
    return mem.sync() if hasattr(mem, "sync") else 0


def run_all() -> dict:
    return {"ran_at": now_iso(), "meko_resynced": sync_meko(), "new_proposals": refresh_patterns(),
            "retired": retire_stale(), "batch_lessons": batch_lessons()}
