"""Steward, dedup, verbatim guard, staleness, commitments, opt-in batch lessons."""
import os
import sys
import tempfile

os.environ.setdefault("LLM_CHAIN", "offline")
os.environ.setdefault("EMBED_MODEL", "hash")
os.environ["MEMORY_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = os.path.join(tempfile.mkdtemp(), "mem2.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from batchmate.agents import curator, pattern, planner, steward  # noqa: E402
from batchmate.graph import run_offline  # noqa: E402
from batchmate.memory import SYSTEM, Memory, batch_scope, get_memory, student_scope  # noqa: E402
from batchmate.memory.base import AccessDenied  # noqa: E402
from seed.seed import seed  # noqa: E402

from datetime import datetime, timezone  # noqa: E402


def test_autonomy():
    seed(approve=True, reset=True)
    mem = get_memory()

    # 1. duplicate write-up is ignored (no fake corroboration)
    t = "Round 2: LRU cache design and Leadership Principles. Selected."
    assert curator.curate(t, "Amazon", "SDE intern", 2026, "2026-09-01")
    assert curator.curate(t + "  ", "Amazon", "SDE intern", 2026, "2026-09-01") == []

    # 2. verbatim guard
    assert curator._copies_source("they asked implement an lru cache with get and put in o one",
                                  "q: they asked implement an lru cache with get and put in o one time")

    # 3. Steward picks up new evidence without anyone clicking, never auto-approves
    for i in range(3):
        curator.curate(f"Report {i}: Round 3 was a system design trade-off discussion about scalability. "
                       f"Offer {i}.", "Amazon", "SDE intern", 2026, "2026-09-1%d" % i)
    report = steward.run_all()
    pend = pattern.pending("Amazon")
    assert any(p.meta["topic"] == "system_design" and p.meta["round"] == 3 for p in pend), report
    assert all(p.status == "proposed" for p in pend)

    # 4. stale pattern retired; revived only through the coordinator
    old = [p for p in mem.list("company-amazon", SYSTEM, kinds=["pattern"], statuses=("active",))][0]
    mem.update(old.id, meta={**old.meta, "observed_at": "2021-01-01"})
    assert old.text in steward.retire_stale()
    assert mem.get(old.id).status == "stale"
    _, ctx_fresh = planner.plan("new-junior", "Amazon", "SDE intern", 5, memory_on=True)
    assert old.id not in {m.id for m in ctx_fresh["patterns"]}  # stale → never recalled

    # 5. "tomorrow we'll drill X" becomes the next plan
    s1 = run_offline("priya", "Amazon", "SDE intern", ["I don't know"] * 6, memory_on=True)
    promised = mem.list(student_scope("priya"), "priya", kinds=["next_plan"], statuses=("active",))
    assert len(promised) == 1
    p2, ctx = planner.plan("priya", "Amazon", "SDE intern", 4, memory_on=True)
    assert promised[0].meta["topic"] in p2.mock_topics, (p2.mock_topics, s1["summary"])
    assert "promised last session" in p2.rationale

    # 6. batch lessons: opt-in only, k-anonymity of 3
    for sid in ["s1", "s2"]:
        mem.write(Memory(scope=student_scope(sid), kind="weakness", text="Weak at DBMS transactions",
                         meta={"topic": "dbms_transactions"}))
        steward.set_opt_in(sid, True)
    year = datetime.now(timezone.utc).year
    assert steward.batch_lessons() == []  # priya hasn't opted in → only 2
    steward.set_opt_in("priya", True)
    lessons = steward.batch_lessons()
    assert any("DBMS transactions" in t for t in lessons), lessons
    assert all("priya" not in t and "s1" not in t for t in lessons)
    steward.set_opt_in("priya", False)
    steward.batch_lessons()
    assert not mem.list(batch_scope(year), SYSTEM, kinds=["lesson"], statuses=("active",))

    # 7. students still can't touch shared scopes or each other
    try:
        mem.write(Memory(scope="company-amazon", kind="pattern", text="fake"), requester="priya")
        raise AssertionError("student wrote shared scope")
    except AccessDenied:
        pass
    print("autonomy OK:", {k: v for k, v in report.items() if k != "ran_at"})


if __name__ == "__main__":
    test_autonomy()
    print("OK")
