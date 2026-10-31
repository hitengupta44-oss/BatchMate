"""MemoryService interface: the one seam the agents depend on.

Swap LocalMemoryService / SupabaseMemoryService for a Meko MCP implementation later
without touching any agent. Scopes map 1:1 onto Meko datapacks:
    student-<id>    private to that student
    company-<name>  shared (experiences + promoted patterns)
    batch-<year>    shared (batch-wide lessons)
"""
from __future__ import annotations

import math
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .. import config

SYSTEM = "system"  # trusted internal caller (agents acting on a student's behalf pass the student id)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def student_scope(student_id: str) -> str:
    return f"student-{student_id}"


def company_scope(company: str) -> str:
    return f"company-{company.strip().lower().replace(' ', '-')}"


def batch_scope(year: int | str) -> str:
    return f"batch-{year}"


class AccessDenied(PermissionError):
    pass


def check_access(scope: str, requester: str, write: bool = False) -> None:
    """A5: personal memory is readable/writable only by its owner (or the system)."""
    if requester == SYSTEM:
        return
    if scope.startswith("student-"):
        if scope != student_scope(requester):
            raise AccessDenied(f"{requester} cannot access {scope}")
    elif write and not requester.startswith("coordinator"):
        # Shared scopes are written by agents (SYSTEM) or coordinators, never directly by students.
        raise AccessDenied(f"{requester} cannot write shared scope {scope}")


@dataclass
class Memory:
    scope: str
    kind: str  # weakness | strength | session | experience | pattern | lesson
    text: str
    meta: dict = field(default_factory=dict)
    source_count: int = 1  # corroboration: how many independent reports/sessions back this
    status: str = "active"  # active | proposed | rejected | resolved
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    # Filled in at recall time only.
    similarity: float | None = None
    confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def observed_at(self) -> str:
        """When the underlying event happened (e.g. interview date), else when stored."""
        return self.meta.get("observed_at") or self.created_at


def recency_weight(observed_at: str, half_life_days: float | None = None) -> float:
    hl = half_life_days or config.RECENCY_HALF_LIFE_DAYS
    try:
        ts = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return 1.0
    age_days = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400)
    return 0.5 ** (age_days / hl)


def corroboration_weight(source_count: int) -> float:
    return 1 - 0.5 ** max(1, source_count)  # 1 → .5, 2 → .75, 3 → .875


def score(mem: Memory, similarity: float, weight_by: tuple[str, ...]) -> float:
    """recall(..., weight_by="recency,corroboration") → a confidence per memory."""
    conf = max(0.0, similarity)
    if "recency" in weight_by:
        conf *= 0.5 + 0.5 * recency_weight(mem.observed_at)
    if "corroboration" in weight_by:
        conf *= 0.5 + 0.5 * corroboration_weight(mem.source_count)
    return round(conf, 4)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class MemoryService(ABC):
    """write / recall / promote / forget, plus small helpers the UI needs."""

    @abstractmethod
    def write(self, mem: Memory, requester: str = SYSTEM) -> Memory: ...

    @abstractmethod
    def recall(
        self,
        query: str,
        scopes: list[str],
        requester: str,
        k: int = 5,
        kinds: list[str] | None = None,
        statuses: tuple[str, ...] = ("active",),
        weight_by: tuple[str, ...] = ("recency", "corroboration"),
        min_similarity: float = 0.05,
    ) -> list[Memory]: ...

    @abstractmethod
    def get(self, memory_id: str) -> Memory | None: ...

    @abstractmethod
    def update(self, memory_id: str, requester: str = SYSTEM, **fields) -> Memory: ...

    @abstractmethod
    def forget(self, memory_id: str, requester: str) -> bool: ...

    @abstractmethod
    def list(self, scope: str, requester: str, kinds: list[str] | None = None,
             statuses: tuple[str, ...] | None = None) -> list[Memory]: ...

    @abstractmethod
    def list_scopes(self, prefix: str = "") -> list[str]:
        """Distinct scopes (SYSTEM use only, for the Steward's sweeps)."""

    # --- promotion to shared knowledge (Pattern Agent proposes, Verifier approves) ---
    def propose(self, mem: Memory) -> Memory:
        mem.status = "proposed"
        return self.write(mem, requester=SYSTEM)

    def promote(self, memory_id: str, approved_by: str) -> Memory:
        if not approved_by.startswith("coordinator"):
            raise AccessDenied("only a placement coordinator can approve promotions")
        mem = self.get(memory_id)
        if mem is None or mem.status != "proposed":
            raise ValueError(f"{memory_id} is not a pending proposal")
        meta = {**mem.meta, "approved_by": approved_by, "approved_at": now_iso()}
        return self.update(memory_id, requester=SYSTEM, status="active", meta=meta)

    def reject(self, memory_id: str, approved_by: str) -> Memory:
        if not approved_by.startswith("coordinator"):
            raise AccessDenied("only a placement coordinator can reject promotions")
        return self.update(memory_id, requester=SYSTEM, status="rejected")
