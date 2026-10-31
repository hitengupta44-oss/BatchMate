"""Runs the full Priya story through MekoMemoryService against a fake Meko MCP server
that follows the documented tool contracts (datapacks, memory_add/search/update/delete/promote)."""
import os
import sys
import tempfile
import uuid

os.environ.setdefault("LLM_CHAIN", "offline")
os.environ.setdefault("EMBED_MODEL", "hash")
os.environ["MEMORY_BACKEND"] = "local"
os.environ["LOCAL_STORE_PATH"] = os.path.join(tempfile.mkdtemp(), "ledger.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from batchmate import memory as memory_pkg  # noqa: E402
from batchmate.memory.base import cosine  # noqa: E402
from batchmate.memory.embeddings import embed_one  # noqa: E402
from batchmate.memory.local import LocalMemoryService  # noqa: E402
from batchmate.memory.meko_client import MekoError  # noqa: E402
from batchmate.memory.meko_store import MekoMemoryService  # noqa: E402


class FakeMeko:
    def __init__(self):
        self.packs, self.mems, self.calls, self.down = {}, {}, [], False

    def call(self, tool, args, timeout=30):
        self.calls.append(tool)
        if self.down:
            raise MekoError(f"{tool} failed: offline")
        if tool == "datapack_search":
            return {"datapacks": [{"id": i, "name": n} for n, i in self.packs.items() if n == args["name"]]}
        if tool == "datapack_create":
            self.packs[args["name"]] = "dp_" + uuid.uuid4().hex[:6]
            return {"datapack_id": self.packs[args["name"]]}
        if tool == "memory_add":
            mid = "m_" + uuid.uuid4().hex[:8]
            self.mems[mid] = {**args, "promoted": False}
            return {"results": [{"id": mid, "memory": args["text"], "event": "ADD"}]}
        if tool == "memory_search":
            qv = embed_one(args["query"])
            rows = [{"id": i, "memory": m["text"], "score": cosine(qv, embed_one(m["text"])),
                     "raw_similarity_score": cosine(qv, embed_one(m["text"]))}
                    for i, m in self.mems.items() if m["datapack_id"] == args["datapack_id"]]
            return {"results": sorted(rows, key=lambda r: -r["score"])[:args.get("limit", 10)]}
        if tool == "memory_update":
            m = self.mems[args["memory_id"]]
            assert m["agent_id"] == args["agent_id"], "agent_id must match writer"
            m["text"] = args["text"]
            return {"id": args["memory_id"]}
        if tool == "memory_delete_by_id":
            m = self.mems[args["memory_id"]]
            assert m["agent_id"] == args["agent_id"], "agent_id must match writer"
            del self.mems[args["memory_id"]]
            return {"deleted": True}
        if tool == "memory_promote":
            for i in args["memory_ids"]:
                self.mems[i]["promoted"] = True
            return {"promoted": args["memory_ids"]}
        raise AssertionError(tool)


def test_meko_backend():
    fake = FakeMeko()
    svc = MekoMemoryService(ledger=LocalMemoryService(os.environ["LOCAL_STORE_PATH"]), client=fake)
    memory_pkg.get_memory.cache_clear()
    memory_pkg.get_memory = lambda: svc  # route every agent through Meko
    import batchmate.agents.curator, batchmate.agents.evaluator, batchmate.agents.interviewer  # noqa
    import batchmate.agents.pattern, batchmate.agents.planner, batchmate.agents.steward  # noqa
    import batchmate.agents.verifier, batchmate.graph, seed.seed  # noqa
    for mod in [batchmate.agents.curator, batchmate.agents.evaluator, batchmate.agents.interviewer,
                batchmate.agents.pattern, batchmate.agents.planner, batchmate.agents.steward,
                batchmate.agents.verifier, batchmate.graph, seed.seed]:
        mod.get_memory = lambda: svc

    from batchmate.graph import run_offline
    from seed.seed import seed

    out = seed(approve=True)
    assert out["experiences"] > 0
    assert {"batchmate-company-amazon", "batchmate-student-priya", "batchmate-student-arjun"} <= set(fake.packs)
    promoted = [m for m in fake.mems.values() if m["promoted"]]
    assert promoted, "approved patterns must be promoted in Meko"

    on = run_offline("priya", "Amazon", "SDE intern", ["hashmap and doubly linked list, O(1) because ..."] * 5)
    assert on["plan"]["mock_topics"][0] == "lru_cache", on["plan"]
    assert all(r["text"] and "[bm:" not in r["text"] for r in on["recalled"]), "tags must be stripped"
    assert "memory_search" in fake.calls

    # forget deletes in Meko as well
    w = svc.list("student-priya", "priya", kinds=["weakness"], statuses=("active",))[0]
    meko_id = w.meta["meko_id"]
    assert svc.forget(w.id, "priya") and meko_id not in fake.mems

    # Meko down: recall returns nothing (never invented), writes are deferred and resynced later
    fake.down = True
    assert svc.recall("anything", ["company-amazon"], "priya") == []
    from batchmate.memory import Memory
    m = svc.write(Memory(scope="student-priya", kind="weakness", text="Weak at DBMS normalization",
                         meta={"topic": "dbms_normalization"}), requester="priya")
    assert not svc.get(m.id).meta["meko_synced"]
    fake.down = False
    assert svc.sync() >= 1 and svc.get(m.id).meta["meko_synced"]
    print("meko OK:", len(fake.mems), "memories in", len(fake.packs), "datapacks;",
          {t: fake.calls.count(t) for t in set(fake.calls)})


if __name__ == "__main__":
    test_meko_backend()
    print("OK")
