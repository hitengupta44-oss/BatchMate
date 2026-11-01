"""No repeats across sessions, profile-personalised questions, memory-only coach."""
import os
import sys
import tempfile

os.environ.setdefault("LLM_CHAIN", "offline")
os.environ.setdefault("EMBED_MODEL", "hash")
os.environ["MEMORY_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = os.path.join(tempfile.mkdtemp(), "mem3.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from batchmate.agents import coach, interviewer, profile  # noqa: E402
from batchmate.graph import run_offline  # noqa: E402
from seed.seed import seed  # noqa: E402

ANSWER = "I'd use a hashmap and a doubly linked list. O(1) because each step is a pointer update; space O(n)."


def norm(q):
    return interviewer._norm(q)


def test_features():
    seed(approve=True, reset=True)

    # Profiles are seeded and readable.
    p = profile.get_profile("priya")
    assert p.projects and p.projects[0].name == "CampusEats" and "Amazon" in p.target_companies

    # Three sessions in a row: the coach never asks Priya the same question twice.
    asked = []
    for _ in range(3):
        s = run_offline("priya", "Amazon", "SDE intern", [ANSWER] * 6, memory_on=True, max_turns=3)
        asked += [t["question"] for t in s["transcript"]]
    dupes = {q for q in asked if [norm(x) for x in asked].count(norm(q)) > 1}
    assert not dupes, f"repeated across sessions: {dupes}"
    print(f"{len(asked)} questions over 3 sessions, all different")

    # Memory off still never repeats inside one session.
    off = run_offline("priya", "Amazon", "SDE intern", [ANSWER] * 6, memory_on=False, max_turns=3)
    qs = [t["question"] for t in off["transcript"]]
    assert len({norm(q) for q in qs}) == len(qs)

    # Project questions use the student's own project (and say where that came from).
    state = {"turn": 0, "plan": {"mock_topics": ["project_explanation"]}, "transcript": [],
             "memory_on": True, "student_id": "priya", "company": "Amazon", "role": "SDE intern"}
    q, shown = interviewer.next_question(state)
    assert "CampusEats" in q.text, q.text
    assert any(m.kind == "student_profile" for m in shown)

    # Profile edits are saved and used.
    p.projects[0].name = "HostelHub"
    profile.save_profile("priya", p)
    q, _ = interviewer.next_question(state)
    assert "HostelHub" in q.text, q.text

    # Coach answers from memory and cites what it used.
    answer, used = coach.ask("priya", "What should I focus on before my Amazon interview?")
    assert answer and used, answer
    assert all(u.scope.startswith(("student-priya", "company-", "batch-")) for u in used)
    # ...never from another student's private memory.
    _, used_a = coach.ask("arjun", "What am I weak at?")
    assert all(not u.scope.startswith("student-priya") for u in used_a)
    # ...and says so when memory has nothing.
    empty, used_e = coach.ask("new-student", "What did I struggle with last week?")
    print("coach:", answer[:120], "| new student:", empty[:80])
    assert all(not u.scope.startswith("student-") for u in used_e)


if __name__ == "__main__":
    test_features()
    print("features OK")
