"""Seed the MVP: 10 Amazon SDE-intern experiences + 2 students' session history.

    python -m seed.seed            # seed, run Pattern Agent, leave proposals pending (demo the approval)
    python -m seed.seed --approve  # also auto-approve as coordinator (skip the approval step)
    python -m seed.seed --reset    # wipe the local store first
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from batchmate import config
from batchmate.agents import curator, pattern, verifier
from batchmate.memory import SYSTEM, Memory, get_memory, student_scope
from batchmate.topics import label

HERE = Path(__file__).parent
COMPANY, ROLE = "Amazon", "SDE intern"


def seed(approve: bool = False, reset: bool = False) -> dict:
    if reset and config.MEMORY_BACKEND == "local" and os.path.exists(config.LOCAL_STORE_PATH):
        os.remove(config.LOCAL_STORE_PATH)
        get_memory.cache_clear()
    mem = get_memory()

    n_exp = 0
    for e in json.loads((HERE / "experiences.json").read_text()):
        n_exp += len(curator.curate(e["text"], COMPANY, ROLE, e["year"], e["observed_at"],
                                    names=e.get("names"), seeded=True))

    for sid, s in json.loads((HERE / "students.json").read_text()).items():
        for w in s["weaknesses"]:
            mem.write(Memory(scope=student_scope(sid), kind="weakness", source_count=len(w["sessions"]),
                             text=f"Weak at {label(w['topic'])} (seen in {len(w['sessions'])} sessions). {w['note']}",
                             meta={"topic": w["topic"], "sessions": w["sessions"],
                                   "observed_at": w["observed_at"], "seeded": True}), requester=SYSTEM)
        for st in s["strengths"]:
            mem.write(Memory(scope=student_scope(sid), kind="strength", text=f"Answered {label(st['topic'])} well.",
                             meta={"topic": st["topic"], "sessions": st["sessions"],
                                   "observed_at": st["observed_at"], "seeded": True}), requester=SYSTEM)

    proposals = pattern.find_and_propose(COMPANY, ROLE)
    if approve:
        for p in proposals:
            verifier.approve(p.id, "coordinator-demo")
    return {"experiences": n_exp, "proposals": [p.text for p in proposals], "approved": approve}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--if-empty", action="store_true", help="only seed when no company data exists")
    a = ap.parse_args()
    if a.if_empty and get_memory().list_scopes("company-"):
        print("Store already has data; skipping seed.")
    else:
        print(json.dumps(seed(a.approve, a.reset), indent=2))
