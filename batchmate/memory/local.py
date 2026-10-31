"""JSON-file MemoryService. Zero setup; ideal for local dev, tests and the HF Space demo."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import fields

from .base import SYSTEM, Memory, MemoryService, check_access, cosine, now_iso, score
from .embeddings import embed_one

_MEM_FIELDS = {f.name for f in fields(Memory)}


class LocalMemoryService(MemoryService):
    def __init__(self, path: str | None = None):
        self.path = path  # None → purely in-memory
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {}  # id → {"mem": Memory, "vec": [...]}
        if path and os.path.exists(path):
            with open(path) as f:
                for row in json.load(f):
                    vec = row.pop("embedding")
                    mem = Memory(**{k: v for k, v in row.items() if k in _MEM_FIELDS})
                    self._rows[mem.id] = {"mem": mem, "vec": vec}

    def _save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        out = [{**r["mem"].to_dict(), "embedding": r["vec"]} for r in self._rows.values()]
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f)
        os.replace(tmp, self.path)

    def write(self, mem: Memory, requester: str = SYSTEM) -> Memory:
        check_access(mem.scope, requester, write=True)
        with self._lock:
            self._rows[mem.id] = {"mem": mem, "vec": embed_one(mem.text)}
            self._save()
        return mem

    def recall(self, query, scopes, requester, k=5, kinds=None, statuses=("active",),
               weight_by=("recency", "corroboration"), min_similarity=0.05):
        for s in scopes:
            check_access(s, requester)
        qv = embed_one(query)
        hits = []
        for r in self._rows.values():
            m = r["mem"]
            if m.scope not in scopes or (kinds and m.kind not in kinds) or m.status not in statuses:
                continue
            sim = cosine(qv, r["vec"])
            if sim < min_similarity:
                continue
            hit = Memory(**{k2: v for k2, v in m.to_dict().items() if k2 in _MEM_FIELDS})
            hit.similarity = round(sim, 4)
            hit.confidence = score(m, sim, tuple(weight_by))
            hits.append(hit)
        hits.sort(key=lambda h: h.confidence, reverse=True)
        return hits[:k]

    def get(self, memory_id):
        r = self._rows.get(memory_id)
        return r["mem"] if r else None

    def update(self, memory_id, requester=SYSTEM, **changes):
        with self._lock:
            r = self._rows[memory_id]
            check_access(r["mem"].scope, requester, write=not r["mem"].scope.startswith("student-"))
            for key, val in changes.items():
                setattr(r["mem"], key, val)
            r["mem"].updated_at = now_iso()
            if "text" in changes:
                r["vec"] = embed_one(r["mem"].text)
            self._save()
            return r["mem"]

    def forget(self, memory_id, requester):
        with self._lock:
            r = self._rows.get(memory_id)
            if not r:
                return False
            check_access(r["mem"].scope, requester, write=not r["mem"].scope.startswith("student-"))
            del self._rows[memory_id]
            self._save()
            return True

    def list_scopes(self, prefix=""):
        return sorted({r["mem"].scope for r in self._rows.values() if r["mem"].scope.startswith(prefix)})

    def list(self, scope, requester, kinds=None, statuses=None):
        check_access(scope, requester)
        out = [r["mem"] for r in self._rows.values() if r["mem"].scope == scope
               and (not kinds or r["mem"].kind in kinds)
               and (not statuses or r["mem"].status in statuses)]
        return sorted(out, key=lambda m: m.created_at, reverse=True)
