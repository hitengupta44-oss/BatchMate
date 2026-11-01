"""Meko search is slow (seconds). One interview question must wait ~1 search, not the sum of all."""
import os
import sys
import tempfile
import time

os.environ.setdefault("LLM_CHAIN", "offline")
os.environ.setdefault("EMBED_MODEL", "hash")
os.environ["MEMORY_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = os.path.join(tempfile.mkdtemp(), "speed.json")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import test_meko  # noqa: E402  (reuses its fake Meko)
from batchmate import memory as memory_pkg  # noqa: E402
from batchmate.memory.local import LocalMemoryService  # noqa: E402
from batchmate.memory.meko_store import MekoMemoryService  # noqa: E402

DELAY = 0.4


class SlowMeko(test_meko.FakeMeko):
    def call(self, tool, args, timeout=30):
        if tool == "memory_search":
            time.sleep(DELAY)
        return super().call(tool, args, timeout)


def test_speed():
    fake = SlowMeko()
    fake.rewrite = False
    svc = MekoMemoryService(ledger=LocalMemoryService(os.environ["LOCAL_STORE_PATH"]), client=fake)
    memory_pkg.get_memory = lambda: svc
    import batchmate.agents.interviewer as iv, batchmate.agents.planner as pl  # noqa: E401
    import batchmate.agents.profile as pr, batchmate.agents.curator as cu, batchmate.agents.pattern as pa
    import batchmate.agents.verifier as ve, batchmate.agents.evaluator as ev, batchmate.graph as gr, seed.seed as sd
    for m in (iv, pl, pr, cu, pa, ve, ev, gr, sd):
        m.get_memory = lambda: svc
    sd.seed(approve=True)

    state = {"turn": 0, "plan": {"mock_topics": ["lru_cache"]}, "transcript": [], "memory_on": True,
             "student_id": "priya", "company": "Amazon", "role": "SDE intern"}
    n0, t0 = fake.calls.count("memory_search"), time.time()
    iv.next_question(state)
    took, searches = time.time() - t0, fake.calls.count("memory_search") - n0
    print(f"question: {searches} Meko searches in {took:.2f}s (sequential would be {searches * DELAY:.2f}s)")
    assert searches >= 3 and took < searches * DELAY * 0.6, "recalls are not running in parallel"

    n1, t1 = fake.calls.count("memory_search"), time.time()
    iv.next_question(state)  # same question again within the cache window
    print(f"repeat: {fake.calls.count('memory_search') - n1} searches in {time.time() - t1:.2f}s")
    assert fake.calls.count("memory_search") == n1, "identical searches should be reused"

    t2 = time.time()
    pl.plan("priya", "Amazon", "SDE intern", 5, memory_on=True)
    print(f"plan: {time.time() - t2:.2f}s")
    assert time.time() - t2 < 5 * DELAY * 0.6


if __name__ == "__main__":
    test_speed()
    print("speed OK")
