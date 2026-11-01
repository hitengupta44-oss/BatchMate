"""Supabase Postgres + pgvector MemoryService. Run sql/schema.sql once first."""
from __future__ import annotations

import threading
import time
from dataclasses import fields

from .. import config
from .base import SYSTEM, Memory, MemoryService, check_access, now_iso, score
from .embeddings import embed_one

_MEM_FIELDS = {f.name for f in fields(Memory)}
TABLE = "memories"


def _transient(e: Exception) -> bool:
    name = e.__class__.__name__
    return name in ("RemoteProtocolError", "ConnectError", "ReadError", "WriteError", "ReadTimeout",
                    "ConnectTimeout", "PoolTimeout", "LocalProtocolError") or "disconnected" in str(e).lower()


def _row_to_mem(row: dict) -> Memory:
    return Memory(**{k: v for k, v in row.items() if k in _MEM_FIELDS})


class SupabaseMemoryService(MemoryService):
    def __init__(self, url: str | None = None, key: str | None = None):
        self._url, self._key = url or config.SUPABASE_URL, key or config.SUPABASE_KEY
        self._local = threading.local()

    @property
    def db(self):
        """One client per thread. Recall runs Meko searches in parallel threads, and a single shared
        HTTP/2 connection to Supabase drops under that ("Server disconnected")."""
        c = getattr(self._local, "client", None)
        if c is None:
            from supabase import create_client
            c = self._local.client = create_client(self._url, self._key)
        return c

    def _run(self, build):
        """Execute a query, retrying on dropped connections with a fresh client."""
        for attempt in range(3):
            try:
                return build().execute()
            except Exception as e:  # httpx.RemoteProtocolError / ConnectError / ReadError …
                if attempt == 2 or not _transient(e):
                    raise
                self._local.client = None
                time.sleep(0.3 * (attempt + 1))

    def write(self, mem: Memory, requester: str = SYSTEM) -> Memory:
        check_access(mem.scope, requester, write=True)
        row = {k: v for k, v in mem.to_dict().items() if k not in ("similarity", "confidence")}
        row["embedding"] = embed_one(mem.text)
        self._run(lambda: self.db.table(TABLE).upsert(row))
        return mem

    def recall(self, query, scopes, requester, k=5, kinds=None, statuses=("active",),
               weight_by=("recency", "corroboration"), min_similarity=0.05):
        for s in scopes:
            check_access(s, requester)
        args = {
            "query_embedding": embed_one(query),
            "match_scopes": scopes,
            "match_kinds": kinds,
            "match_statuses": list(statuses),
            "match_count": k * 4,  # over-fetch, then re-rank by confidence
        }
        res = self._run(lambda: self.db.rpc("match_memories", args))
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
        res = self._run(lambda: self.db.table(TABLE).select("*").eq("id", memory_id).limit(1))
        return _row_to_mem(res.data[0]) if res.data else None

    def update(self, memory_id, requester=SYSTEM, **changes):
        mem = self.get(memory_id)
        if mem is None:
            raise KeyError(memory_id)
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        changes["updated_at"] = now_iso()
        if "text" in changes:
            changes["embedding"] = embed_one(changes["text"])
        res = self._run(lambda: self.db.table(TABLE).update(changes).eq("id", memory_id))
        return _row_to_mem(res.data[0])

    def forget(self, memory_id, requester):
        mem = self.get(memory_id)
        if mem is None:
            return False
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        self._run(lambda: self.db.table(TABLE).delete().eq("id", memory_id))
        return True

    def list_scopes(self, prefix=""):
        res = self._run(lambda: self.db.table(TABLE).select("scope").like("scope", f"{prefix}%"))
        return sorted({r["scope"] for r in res.data or []})

    def list(self, scope, requester, kinds=None, statuses=None):
        check_access(scope, requester)
        def build():
            q = self.db.table(TABLE).select("*").eq("scope", scope)
            if kinds:
                q = q.in_("kind", kinds)
            if statuses:
                q = q.in_("status", list(statuses))
            return q.order("created_at", desc=True)
        res = self._run(build)
        return [_row_to_mem(r) for r in res.data or []]
