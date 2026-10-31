"""Supabase Postgres + pgvector MemoryService. Run sql/schema.sql once first."""
from __future__ import annotations

from dataclasses import fields

from .. import config
from .base import SYSTEM, Memory, MemoryService, check_access, now_iso, score
from .embeddings import embed_one

_MEM_FIELDS = {f.name for f in fields(Memory)}
TABLE = "memories"


def _row_to_mem(row: dict) -> Memory:
    return Memory(**{k: v for k, v in row.items() if k in _MEM_FIELDS})


class SupabaseMemoryService(MemoryService):
    def __init__(self, url: str | None = None, key: str | None = None):
        from supabase import create_client

        self.db = create_client(url or config.SUPABASE_URL, key or config.SUPABASE_KEY)

    def write(self, mem: Memory, requester: str = SYSTEM) -> Memory:
        check_access(mem.scope, requester, write=True)
        row = {k: v for k, v in mem.to_dict().items() if k not in ("similarity", "confidence")}
        row["embedding"] = embed_one(mem.text)
        self.db.table(TABLE).upsert(row).execute()
        return mem

    def recall(self, query, scopes, requester, k=5, kinds=None, statuses=("active",),
               weight_by=("recency", "corroboration"), min_similarity=0.05):
        for s in scopes:
            check_access(s, requester)
        res = self.db.rpc("match_memories", {
            "query_embedding": embed_one(query),
            "match_scopes": scopes,
            "match_kinds": kinds,
            "match_statuses": list(statuses),
            "match_count": k * 4,  # over-fetch, then re-rank by confidence
        }).execute()
        hits = []
        for row in res.data or []:
            sim = row.pop("similarity")
            if sim < min_similarity:
                continue
            m = _row_to_mem(row)
            m.similarity = round(sim, 4)
            m.confidence = score(m, sim, tuple(weight_by))
            hits.append(m)
        hits.sort(key=lambda h: h.confidence, reverse=True)
        return hits[:k]

    def get(self, memory_id):
        res = self.db.table(TABLE).select("*").eq("id", memory_id).limit(1).execute()
        return _row_to_mem(res.data[0]) if res.data else None

    def update(self, memory_id, requester=SYSTEM, **changes):
        mem = self.get(memory_id)
        if mem is None:
            raise KeyError(memory_id)
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        changes["updated_at"] = now_iso()
        if "text" in changes:
            changes["embedding"] = embed_one(changes["text"])
        res = self.db.table(TABLE).update(changes).eq("id", memory_id).execute()
        return _row_to_mem(res.data[0])

    def forget(self, memory_id, requester):
        mem = self.get(memory_id)
        if mem is None:
            return False
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        self.db.table(TABLE).delete().eq("id", memory_id).execute()
        return True

    def list_scopes(self, prefix=""):
        res = self.db.table(TABLE).select("scope").like("scope", f"{prefix}%").execute()
        return sorted({r["scope"] for r in res.data or []})

    def list(self, scope, requester, kinds=None, statuses=None):
        check_access(scope, requester)
        q = self.db.table(TABLE).select("*").eq("scope", scope)
        if kinds:
            q = q.in_("kind", kinds)
        if statuses:
            q = q.in_("status", list(statuses))
        res = q.order("created_at", desc=True).execute()
        return [_row_to_mem(r) for r in res.data or []]
