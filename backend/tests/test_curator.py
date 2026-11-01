"""Share-an-experience: the AI's wording must never cause a valid report to be dropped."""
import os, sys, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("LLM_CHAIN", "offline"); os.environ.setdefault("EMBED_MODEL", "hash")
from batchmate.agents import curator
from batchmate.agents.curator import Entries, Entry

CO = f"TestCo{uuid.uuid4().hex[:6]}"
TEXT = ("Round 1 was an online test with a sliding window problem on arrays and a tree BFS question. "
        "Round 2 started with my project, then they asked me to design an LRU cache and explain the time "
        "complexity. The last 15 minutes were Leadership Principles questions about ownership. I got the offer.")

def fake_structured(schema, system, user, offline):  # a live model answering with phrases, not tags
    return Entries(entries=[Entry(round=2, topic="LRU cache design", summary="Designing a cache", outcome="cleared"),
                            Entry(round=1, topic="Trees / Graphs (BFS)", summary="BFS on a tree", outcome="cleared"),
                            Entry(round=2, topic="Behavioural", summary="Ownership stories", outcome="cleared")])

curator.structured = fake_structured
rows, why = curator.curate_report(TEXT, CO, "SDE intern", 2026, "2026-11-01")
tags = {r.meta["topic"] for r in rows}
assert why == "added", why
assert {"lru_cache", "leadership_principles", "project_explanation"} <= tags, tags
assert curator.curate_report(TEXT, CO, "SDE intern", 2026, "2026-11-01")[1] == "duplicate"
assert curator.curate_report("heloo 123", CO, "SDE intern", 2026, "2026-11-01")[1] == "no_topics"
curator.structured = lambda *a: (_ for _ in ()).throw(RuntimeError("model down"))
assert curator.curate_report(TEXT + " Again.", f"TestCo{uuid.uuid4().hex[:6]}", "SDE", 2026, "2026-11-01")[1] == "added"
print("curator OK:", sorted(tags))
