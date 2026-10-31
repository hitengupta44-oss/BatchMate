"""MemoryService on Meko.

Meko is the memory the agents reason over: every write goes to `memory_add`, every recall is a
`memory_search` in the scope's datapack, approval is `memory_promote`, forget is
`memory_delete_by_id`. A structured ledger (Supabase or local JSON) keeps ids, status and
metadata, because the agents need fields like topic and round that free-text search can't filter on.

Honesty rule (A5): recall returns ONLY what Meko returned. The ledger enriches a Meko hit with its
fields and drops it if its status says it's retired; it never adds hits of its own.

Datapacks, one per scope:
    <prefix>-student-<id>      private to one student
    <prefix>-company-<name>    shared: curated patterns (promoted when a coordinator approves)
    <prefix>-company-<name>-reports   raw anonymised senior experiences (kept apart so they
                               don't drown the patterns in search)
    <prefix>-batch-<year>      shared: anonymous batch lessons
"""
from __future__ import annotations

import re
from dataclasses import fields

from .. import config
from ..topics import detect_topics
from .base import SYSTEM, AccessDenied, Memory, MemoryService, check_access, now_iso, score
from .meko_client import MekoClient, MekoError

_FIELDS = {f.name for f in fields(Memory)}
_TAG = re.compile(r"\s*\[bm:([0-9a-f]{6,32})[^\]]*\]\s*$")


def tagged(mem: Memory) -> str:
    """Text stored in Meko: the memory plus a trailing id tag used to map hits back."""
    topic = mem.meta.get("topic", "")
    return f"{mem.text} [bm:{mem.id} kind:{mem.kind}{' topic:' + topic if topic else ''} status:{mem.status}]"


def strip_tag(text: str) -> str:
    return _TAG.sub("", text or "").strip()


def _first(d: dict, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def _rows(data) -> list[dict]:
    if isinstance(data, list):
        return data
    for k in ("results", "memories", "items", "data", "datapacks"):
        if isinstance(data, dict) and isinstance(data.get(k), list):
            return data[k]
    return []


class MekoMemoryService(MemoryService):
    def __init__(self, ledger: MemoryService, client: MekoClient | None = None, prefix: str | None = None):
        self.ledger = ledger
        self.meko = client or MekoClient()
        self.prefix = prefix or config.MEKO_DATAPACK_PREFIX
        self._dp: dict[str, str] = {}

    # ---------- datapacks ----------
    @staticmethod
    def pack_key(scope: str, kind: str | None = None) -> str:
        return f"{scope}-reports" if kind == "experience" else scope

    def datapack_name(self, scope: str, kind: str | None = None) -> str:
        return f"{self.prefix}-{self.pack_key(scope, kind)}"

    def datapack_id(self, scope: str, create: bool = True, kind: str | None = None) -> str | None:
        key = self.pack_key(scope, kind)
        if key in self._dp:
            return self._dp[key]
        name = self.datapack_name(scope, kind)
        found = _rows(self.meko.call("datapack_search", {"name": name, "limit": 5}))
        dp = next((_first(r, "datapack_id", "id") for r in found if r.get("name") == name), None)
        if dp is None and not create:
            return None
        if dp is None and create:
            dp = _first(self.meko.call("datapack_create", {"name": name}), "datapack_id", "id")
        if dp:
            self._dp[key] = dp
        return dp

    # ---------- write ----------
    def _push(self, mem: Memory) -> str | None:
        """memory_add → Meko id (None if Meko didn't return one yet)."""
        data = self.meko.call("memory_add", {
            "text": tagged(mem), "agent_id": self._agent(mem), "datapack_id": self.datapack_id(mem.scope, kind=mem.kind),
            "metadata": {"bm_id": mem.id, "kind": mem.kind, "topic": mem.meta.get("topic"),
                         "status": mem.status, "source_count": mem.source_count}})
        row = _rows(data)[0] if _rows(data) else data
        return _first(row, "id", "memory_id")

    @staticmethod
    def _agent(mem: Memory) -> str:
        # Meko update/delete require the same agent_id as the writer, so it's derived, not chosen.
        return mem.meta.get("meko_agent") or f"batchmate-{mem.kind}"

    def write(self, mem: Memory, requester: str = SYSTEM) -> Memory:
        check_access(mem.scope, requester, write=True)
        mem.meta = {**mem.meta, "meko_agent": self._agent(mem), "meko_synced": False}
        self.ledger.write(mem, requester=SYSTEM)
        self._sync_one(mem)
        return mem

    def _sync_one(self, mem: Memory) -> bool:
        try:
            mid = self._push(mem)
        except MekoError as e:
            print(f"[meko] write deferred for {mem.id}: {e}")  # the Steward retries via sync()
            return False
        if mid and mem.kind == "pattern" and mem.status == "active":
            # Approved before it reached Meko (e.g. seeded): promote it in Meko too.
            try:
                self.meko.call("memory_promote", {"memory_ids": [mid], "agent_id": self._agent(mem),
                                                  "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
            except MekoError as e:
                print(f"[meko] promote deferred for {mem.id}: {e}")
        meta = {**mem.meta, "meko_id": mid, "meko_synced": True, "meko_datapack": self.datapack_name(mem.scope, mem.kind)}
        self.ledger.update(mem.id, requester=SYSTEM, meta=meta)
        mem.meta = meta
        return True

    def sync(self) -> int:
        """Push any memory Meko hasn't acknowledged yet. Called by the Steward."""
        n = 0
        for scope in self.ledger.list_scopes(""):
            for m in self.ledger.list(scope, SYSTEM):
                if not m.meta.get("meko_synced"):
                    n += self._sync_one(m)
        return n

    # ---------- recall: Meko only ----------
    def recall(self, query, scopes, requester, k=5, kinds=None, statuses=("active",),
               weight_by=("recency", "corroboration"), min_similarity=0.05):
        for s in scopes:
            check_access(s, requester)
        hits: list[Memory] = []
        want_reports = kinds is None or "experience" in kinds
        want_main = kinds is None or any(k != "experience" for k in kinds)
        targets = [(s, kd) for s in scopes for kd, ok in (("experience", want_reports and s.startswith("company-")),
                                                          (None, want_main)) if ok]
        for scope, kd in targets:
            dp = self.datapack_id(scope, create=False, kind=kd)
            if not dp:
                continue
            try:
                data = self.meko.call("memory_search", {"query": query, "datapack_id": dp,
                                                        "limit": max(10, k * 4)})
            except MekoError as e:
                print(f"[meko] recall failed for {scope}: {e}")  # no Meko → no context, never invented
                continue
            for row in _rows(data):
                text = _first(row, "memory", "text", "content") or ""
                meta = row.get("metadata") or {}
                m_tag = _TAG.search(text)
                bm_id = meta.get("bm_id") or (m_tag.group(1) if m_tag else None)
                rec = self.ledger.get(bm_id) if bm_id else None
                if rec is None:
                    # Meko returned something the ledger doesn't know (e.g. an auto-extracted fact).
                    # Still honest to show; infer what we can from the text.
                    topics = detect_topics(text)
                    rec = Memory(scope=scope, kind=meta.get("kind", "meko"), text=strip_tag(text),
                                 meta={"topic": meta.get("topic") or (topics[0] if topics else None)})
                    if statuses and "active" not in statuses:
                        continue
                elif rec.scope != scope or (statuses and rec.status not in statuses):
                    continue  # retired / proposed / rejected in the ledger → not context
                if kinds and rec.kind not in kinds:
                    continue
                raw = _first(row, "raw_similarity_score", "similarity", "score")
                sim = max(0.0, min(1.0, float(raw))) if raw is not None else 0.5
                if sim < min_similarity:
                    continue
                hit = Memory(**{f: v for f, v in rec.to_dict().items() if f in _FIELDS})
                hit.text = strip_tag(hit.text)
                hit.similarity = round(sim, 4)
                hit.confidence = score(hit, sim, tuple(weight_by))
                hit.meta = {**hit.meta, "from_meko": True}
                hits.append(hit)
        seen, out = set(), []
        for h in sorted(hits, key=lambda h: h.confidence or 0, reverse=True):
            if h.id not in seen:
                seen.add(h.id)
                out.append(h)
        return out[:k]

    # ---------- reads from the ledger (structured listing for the UI) ----------
    def get(self, memory_id):
        return self.ledger.get(memory_id)

    def list(self, scope, requester, kinds=None, statuses=None):
        return self.ledger.list(scope, requester, kinds=kinds, statuses=statuses)

    def list_scopes(self, prefix=""):
        return self.ledger.list_scopes(prefix)

    # ---------- update / forget / promote ----------
    def update(self, memory_id, requester=SYSTEM, **changes):
        mem = self.ledger.update(memory_id, requester=requester, **changes)
        if {"text", "status", "source_count"} & set(changes) and mem.meta.get("meko_id"):
            try:
                self.meko.call("memory_update", {
                    "memory_id": mem.meta["meko_id"], "text": tagged(mem),
                    "agent_id": self._agent(mem), "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
            except MekoError as e:
                print(f"[meko] update not mirrored for {memory_id}: {e}")
        return mem

    def forget(self, memory_id, requester):
        mem = self.ledger.get(memory_id)
        if mem is None:
            return False
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        if mem.meta.get("meko_id"):
            self.meko.call("memory_delete_by_id", {   # if Meko refuses, don't pretend it's forgotten
                "memory_id": mem.meta["meko_id"], "agent_id": self._agent(mem),
                "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
        return self.ledger.forget(memory_id, requester)

    def promote(self, memory_id: str, approved_by: str) -> Memory:
        if not approved_by.startswith("coordinator"):
            raise AccessDenied("only a placement coordinator can approve promotions")
        mem = self.ledger.get(memory_id)
        if mem is None or mem.status != "proposed":
            raise ValueError(f"{memory_id} is not a pending proposal")
        if mem.meta.get("meko_id"):
            self.meko.call("memory_promote", {"memory_ids": [mem.meta["meko_id"]], "agent_id": self._agent(mem),
                                              "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
        return super().promote(memory_id, approved_by)
