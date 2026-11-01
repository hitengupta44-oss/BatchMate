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

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
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


_ID_KEYS = ("datapack_id", "id", "uuid", "conversation_id")
SEARCH_TTL_S = 45   # reuse an identical memory_search for this long (cleared on any write)
MISSING_TTL_S = 300  # don't re-check a datapack that didn't exist for this long


def _all_dicts(data):
    """Every dict nested anywhere in a Meko reply (Meko nests rows under varying keys)."""
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from _all_dicts(v)
    elif isinstance(data, list):
        for v in data:
            yield from _all_dicts(v)


def _deep_id(data, keys=_ID_KEYS) -> str | None:
    for d in _all_dicts(data):
        for k in keys:
            v = d.get(k)
            if isinstance(v, (str, int)) and str(v):
                return str(v)
    return None


def _pack_id_for(data, name: str) -> str | None:
    """Id of the object in a Meko reply whose fields include this exact datapack name."""
    for d in _all_dicts(data):
        if any(isinstance(v, str) and v == name for v in d.values()):
            for k in ("datapack_id", "id", "uuid"):
                v = d.get(k)
                if isinstance(v, (str, int)) and str(v) and str(v) != name:
                    return str(v)
            nested = _deep_id({k: v for k, v in d.items() if isinstance(v, (dict, list))})
            if nested:
                return nested
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
        self._conv: dict[str, str] = {}  # datapack id → conversation id
        self._last_lookup: str | None = None
        self._missing: dict[str, float] = {}       # pack key → when we last saw it doesn't exist
        self._search_cache: dict[tuple, tuple] = {}  # (dp, query, limit) → (at, reply)
        self._tix: dict[str, tuple] = {}  # scope → (cached_at, normalised text → ledger memory)

    # ---------- Meko call conventions ----------
    def conversation_id(self, dp: str | None) -> str:
        """Meko requires a conversation_id on every tool call. One conversation per datapack for
        memory calls, plus one bootstrap conversation (no datapack) for datapack_search/create."""
        key = dp or "__bootstrap__"
        if key not in self._conv:
            args = {"agent_id": "batchmate", "title": "batchmate memory" if dp else "batchmate bootstrap"}
            if dp:
                args["datapack_id"] = dp
            data = self.meko.call("conversation_create", args)
            cid = _deep_id(data, ("conversation_id", "id"))
            if not cid:
                raise MekoError(f"conversation_create returned no id: {str(data)[:200]}")
            self._conv[key] = cid
        return self._conv[key]

    def _call(self, tool: str, args: dict):
        args = dict(args)
        if isinstance(args.get("metadata"), dict):  # Meko wants metadata as a JSON string
            args["metadata"] = json.dumps({k: v for k, v in args["metadata"].items() if v is not None})
        if tool.startswith("memory_") and not args.get("datapack_id"):
            raise MekoError(f"{tool}: refusing to call Meko without a datapack_id")
        if "conversation_id" not in args:
            args["conversation_id"] = self.conversation_id(args.get("datapack_id"))
        if tool in ("memory_add", "memory_update", "memory_delete_by_id", "memory_promote"):
            self._invalidate(args.get("datapack_id"))
        return self.meko.call(tool, args)

    # ---------- datapacks ----------
    @staticmethod
    def pack_key(scope: str, kind: str | None = None) -> str:
        return f"{scope}-reports" if kind == "experience" else scope

    def datapack_name(self, scope: str, kind: str | None = None) -> str:
        return f"{self.prefix}-{self.pack_key(scope, kind)}"

    def _find_pack(self, name: str) -> str | None:
        """Find a datapack's id by its exact name.

        Meko's listing shape isn't documented and has differed from the docs, so: try search by
        name, by query, then the full list; in each reply, find any object that carries the name
        in ANY string field, and take the id from that object."""
        attempts = (("datapack_search", {"name": name, "limit": 20}),
                    ("datapack_search", {"query": name, "limit": 100}),
                    ("datapack_list", {"query": name, "limit": 100}),
                    ("datapack_list", {}))
        last = None
        for tool, args in attempts:
            try:
                data = self._call(tool, args)
            except MekoError as e:
                last = f"{tool}: {e}"
                continue
            dp = _pack_id_for(data, name)
            if dp:
                return dp
            last = f"{tool} → {str(data)[:300]}"
        self._last_lookup = last  # kept for the error message below
        return None

    def datapack_id(self, scope: str, create: bool = True, kind: str | None = None) -> str | None:
        key = self.pack_key(scope, kind)
        if key in self._dp:
            return self._dp[key]
        name = self.datapack_name(scope, kind)
        if not create and time.time() - self._missing.get(key, 0) < MISSING_TTL_S:
            return None  # looked a moment ago and it didn't exist: don't ask Meko again
        dp = self._find_pack(name)
        if dp is None and not create:
            self._missing[key] = time.time()
            # Recall must still work after a restart: if the ledger knows this scope has memories,
            # the datapack exists, so a failed lookup is an error worth seeing, not "no context".
            if self.ledger.list_scopes(scope):
                print(f"[meko] could not find existing datapack '{name}'. Last reply: {self._last_lookup}")
            return None
        if dp is None:
            try:
                created = self._call("datapack_create", {"name": name})
                dp = _pack_id_for(created, name) or _deep_id(created)
            except MekoError as e:
                if "exist" not in str(e).lower() and "conflict" not in str(e).lower():
                    raise
                dp = None  # created earlier (e.g. before a restart): look it up again
            dp = self._find_pack(name) or dp
            if not dp:
                raise MekoError(f"datapack '{name}' exists but its id can't be read. "
                                f"Last reply: {self._last_lookup}")
            print(f"[meko] datapack ready: {name} → {dp}")
        self._dp[key] = dp
        self._missing.pop(key, None)
        return dp

    # ---------- write ----------
    def _push(self, mem: Memory) -> str | None:
        """memory_add → Meko id (None if Meko didn't return one yet)."""
        data = self._call("memory_add", {
            "text": tagged(mem), "agent_id": self._agent(mem), "datapack_id": self.datapack_id(mem.scope, kind=mem.kind),
            "metadata": {"bm_id": mem.id, "kind": mem.kind, "topic": mem.meta.get("topic"),
                         "status": mem.status, "source_count": mem.source_count}})
        return _deep_id(data, ("memory_id", "id"))

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
        if mem.kind == "profile":  # settings (opt-in flags), not a memory worth recalling
            self.ledger.update(mem.id, requester=SYSTEM, meta={**mem.meta, "meko_synced": True})
            return False
        try:
            mid = self._push(mem)
        except MekoError as e:
            print(f"[meko] write deferred for {mem.id}: {e}")  # the Steward retries via sync()
            return False
        if mid and mem.kind == "pattern" and mem.status == "active":
            # Approved before it reached Meko (e.g. seeded): promote it in Meko too.
            try:
                self._call("memory_promote", {"memory_ids": [mid], "agent_id": self._agent(mem),
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

    # ---------- cached search ----------
    def _search(self, dp: str, query: str, limit: int):
        """memory_search, reused for SEARCH_TTL_S: a mock asks Meko the same thing several times
        (planner, interviewer, panel). Any write to the datapack clears its cache."""
        key = (dp, query, limit)
        hit = self._search_cache.get(key)
        if hit and time.time() - hit[0] < SEARCH_TTL_S:
            return hit[1]
        reply = self._call("memory_search", {"query": query, "datapack_id": dp, "limit": limit})
        self._search_cache[key] = (time.time(), reply)
        return reply

    def _invalidate(self, dp: str | None):
        for key in [k for k in self._search_cache if k[0] == dp]:
            self._search_cache.pop(key, None)

    # ---------- mapping Meko hits back to the ledger ----------
    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", strip_tag(text).lower()))[:120]

    def _text_index(self, scope: str) -> dict[str, Memory]:
        """If Meko rewrites a memory (fact extraction) and drops our [bm:id] tag, match it back by
        its normalised text. Cached briefly; the ledger only enriches what Meko returned."""
        now = time.time()
        hit = self._tix.get(scope)
        if hit and now - hit[0] < 30:
            return hit[1]
        idx = {self._norm(m.text): m for m in self.ledger.list(scope, SYSTEM)}
        self._tix[scope] = (now, idx)
        return idx

    def _match(self, scope: str, text: str) -> Memory | None:
        key = self._norm(text)
        if not key:
            return None
        idx = self._text_index(scope)
        if key in idx:
            return idx[key]
        # Rewritten text: accept a ledger memory that contains it (or vice versa), if long enough.
        if len(key) >= 24:
            for k, m in idx.items():
                if key in k or k in key:
                    return m
        return None

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
        def search(target):
            scope, kd = target
            try:
                dp = self.datapack_id(scope, create=False, kind=kd)
                if not dp:
                    return scope, None
                return scope, self._search(dp, query, min(max(10, k * 2), 25))
            except MekoError as e:
                print(f"[meko] recall failed for {scope}: {e}")  # no Meko → no context, never invented
                return scope, None

        # Datapacks are searched in parallel: one Meko round-trip of latency, not one per datapack.
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(targets)))) as pool:
            results = list(pool.map(search, targets))

        for scope, data in results:
            if data is None:
                continue
            rows = [d for d in _all_dicts(data)
                    if isinstance(_first(d, "memory", "text", "content"), str)]
            for row in rows:
                text = _first(row, "memory", "text", "content") or ""
                meta = row.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except ValueError:
                        meta = {}
                m_tag = _TAG.search(text)
                bm_id = meta.get("bm_id") or (m_tag.group(1) if m_tag else None)
                try:
                    rec = self.ledger.get(bm_id) if bm_id else None
                    if rec is None:
                        rec = self._match(scope, text)  # Meko rewrote the text and dropped our tag
                except Exception as e:  # ledger hiccup: never fail a whole mock over one lookup
                    print(f"[meko] ledger lookup failed for {bm_id}: {e!r}")
                    rec = None
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
                self._call("memory_update", {
                    "memory_id": str(mem.meta["meko_id"]), "text": tagged(mem),
                    "agent_id": self._agent(mem), "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
            except MekoError as e:
                # Meko's memory_update currently fails server-side ("Object of type UUID is not JSON
                # serializable"). Mirror the change another way: add the new version, drop the old.
                mem = self._replace_in_meko(mem, e)
        return mem

    def _replace_in_meko(self, mem: Memory, why: Exception) -> Memory:
        old_id = mem.meta.get("meko_id")
        try:
            new_id = self._push(mem)
        except MekoError as e:
            print(f"[meko] update not mirrored for {mem.id}: {why}; re-add failed: {e}")
            return mem
        dp = self.datapack_id(mem.scope, kind=mem.kind)
        if new_id and mem.kind == "pattern" and mem.status == "active":
            try:
                self._call("memory_promote", {"memory_ids": [new_id], "agent_id": self._agent(mem),
                                              "datapack_id": dp})
            except MekoError as e:
                print(f"[meko] promote of replacement deferred for {mem.id}: {e}")
        if old_id and old_id != new_id:
            try:
                self._call("memory_delete_by_id", {"memory_id": str(old_id), "agent_id": self._agent(mem),
                                                   "datapack_id": dp})
            except MekoError as e:
                print(f"[meko] old copy of {mem.id} not removed: {e}")
        meta = {**mem.meta, "meko_id": new_id or old_id, "meko_synced": True}
        mem = self.ledger.update(mem.id, requester=SYSTEM, meta=meta)
        print(f"[meko] {mem.id} mirrored by replace (memory_update unavailable)")
        return mem

    def forget(self, memory_id, requester):
        mem = self.ledger.get(memory_id)
        if mem is None:
            return False
        check_access(mem.scope, requester, write=not mem.scope.startswith("student-"))
        if mem.meta.get("meko_id"):
            self._call("memory_delete_by_id", {   # if Meko refuses, don't pretend it's forgotten
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
            self._call("memory_promote", {"memory_ids": [mem.meta["meko_id"]], "agent_id": self._agent(mem),
                                              "datapack_id": self.datapack_id(mem.scope, kind=mem.kind)})
        return super().promote(memory_id, approved_by)
