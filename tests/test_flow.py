"""End-to-end smoke test of the Priya story, fully offline (no LLM, no network).

    LLM_CHAIN=offline EMBED_MODEL=hash python -m pytest tests -q
    # or (from backend/): python tests/test_flow.py
"""
import os
import sys
import tempfile

os.environ.setdefault("LLM_CHAIN", "offline")
os.environ.setdefault("EMBED_MODEL", "hash")
os.environ["MEMORY_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = os.path.join(tempfile.mkdtemp(), "mem.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from batchmate.agents import pattern, planner, verifier  # noqa: E402
from batchmate.graph import run_offline  # noqa: E402
from batchmate.memory import AccessDenied, get_memory, student_scope  # noqa: E402
from seed.seed import seed  # noqa: E402

PRIYA_ANSWERS = [
    # LRU cache: right structure, but no complexity → triggers the adaptive complexity follow-up
    "I would use a hashmap from key to node and a doubly linked list ordered by recency. On get I move "
    "the node to the front, on put I insert at the front and evict from the tail when full.",
    # complexity follow-up: now she justifies it
    "Both get and put are O(1) because the hashmap lookup is O(1) and moving a node in a doubly linked "
    "list is O(1) pointer updates. Space is O(capacity) since we store each key once in both structures.",
    # second planned topic (time_complexity) — good again
    "First I state the worst case: the loop runs n times so it is O(n), then space is O(1) because we only "
    "keep two pointers. I always justify each term because interviewers ask why.",
    # Leadership Principle, STAR
    "Situation: our club's event site crashed a day before launch. Task: nobody owned it, so I took it. "
    "Action: I debugged the deploy, then set up monitoring. Result: we launched on time with 400 signups.",
]


def test_story():
    seeded = seed(approve=False, reset=True)
    assert seeded["experiences"] > 0 and seeded["proposals"]
    mem = get_memory()

    # Before approval, proposals are invisible to students (Verifier gate).
    p, ctx = planner.plan("priya", "Amazon", "SDE intern", 5, memory_on=True)
    assert ctx["patterns"] == []

    for prop in pattern.pending("Amazon"):
        try:
            verifier.approve(prop.id, "priya")  # students can't approve
            raise AssertionError("student approved a pattern")
        except AccessDenied:
            pass
        verifier.approve(prop.id, "coordinator-demo")
    assert pattern.pending("Amazon") == []

    # --- Memory OFF: generic ---
    off = run_offline("priya", "Amazon", "SDE intern", PRIYA_ANSWERS, memory_on=False)
    off_topics = [t["topic"] for t in off["transcript"]]
    print("\nOFF topics:", off_topics, "\nOFF summary:", off["summary"])
    assert "lru_cache" not in off_topics

    # --- Memory ON: targeted ---
    on = run_offline("priya", "Amazon", "SDE intern", PRIYA_ANSWERS, memory_on=True)
    on_topics = [t["topic"] for t in on["transcript"]]
    print("ON plan:", on["plan"]["mock_topics"], "|", on["plan"]["rationale"])
    for t in on["transcript"]:
        print(f"  [{t['topic']}{' follow-up' if t['is_follow_up'] else ''}] {t['question'][:70]}"
              f" -> {t['eval']['scores']}")
    print("ON notes:", on["notes"], "\nON summary:", on["summary"])
    assert on["plan"]["mock_topics"][0] == "lru_cache"
    assert "leadership_principles" in on_topics
    assert any(t["is_follow_up"] and t["topic"] == "time_complexity" for t in on["transcript"])
    assert "much better than last time" in on["summary"]
    assert "DBMS transactions" in on["summary"]

    # Recall panel only ever shows retrieved items, with source + confidence.
    assert all({"source", "confidence", "id"} <= set(r) for r in on["recalled"])

    # --- A5 privacy ---
    try:
        mem.recall("weak", [student_scope("priya")], requester="arjun")
        raise AssertionError("arjun read priya's memory")
    except AccessDenied:
        pass

    # --- forget with one click ---
    w = mem.list(student_scope("priya"), "priya", kinds=["weakness"], statuses=("active",))[0]
    assert mem.forget(w.id, "priya") and mem.get(w.id) is None

    # Next batch inherits promoted knowledge: a brand-new student gets the LRU plan on day one.
    fresh, _ = planner.plan("new-junior", "Amazon", "SDE intern", 5, memory_on=True)
    assert "lru_cache" in fresh.mock_topics
    print("Fresh junior plan:", fresh.mock_topics)


if __name__ == "__main__":
    test_story()
    print("\nOK")
