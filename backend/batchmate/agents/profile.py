"""Student profile: the prep-relevant facts the interviewer personalises with.

Stored as one `student_profile` memory in the student's private datapack (so it goes to Meko and
comes back through recall like everything else). Only fields interview prep needs: no phone,
email, CGPA or address (A5).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..memory import Memory, get_memory, student_scope
from ..memory.base import now_iso

KIND = "student_profile"


class Project(BaseModel):
    name: str = Field(max_length=80)
    summary: str = Field(default="", max_length=300)


class Profile(BaseModel):
    branch: str = Field(default="", max_length=60)
    year: str = Field(default="", max_length=20)
    target_companies: list[str] = Field(default_factory=list, max_length=8)
    projects: list[Project] = Field(default_factory=list, max_length=5)
    languages: list[str] = Field(default_factory=list, max_length=6)
    goal: str = Field(default="", max_length=200)

    def as_text(self) -> str:
        parts = []
        if self.branch or self.year:
            parts.append(f"{self.year} {self.branch}".strip())
        if self.target_companies:
            parts.append("targets " + ", ".join(self.target_companies))
        if self.languages:
            parts.append("codes in " + ", ".join(self.languages))
        for p in self.projects:
            parts.append(f"project {p.name}" + (f" ({p.summary})" if p.summary else ""))
        if self.goal:
            parts.append(f"goal: {self.goal}")
        return "Profile: " + "; ".join(parts) + "."


def _current(student_id: str) -> Memory | None:
    rows = get_memory().list(student_scope(student_id), student_id, kinds=[KIND], statuses=("active",))
    return rows[0] if rows else None


def get_profile(student_id: str) -> Profile:
    m = _current(student_id)
    return Profile(**m.meta.get("profile", {})) if m else Profile()


def save_profile(student_id: str, profile: Profile, seeded: bool = False) -> Profile:
    mem = get_memory()
    meta = {"profile": profile.model_dump(), "observed_at": now_iso(), "seeded": seeded}
    old = _current(student_id)
    if old:
        mem.update(old.id, requester=student_id, text=profile.as_text(), meta={**old.meta, **meta})
    else:
        mem.write(Memory(scope=student_scope(student_id), kind=KIND, text=profile.as_text(), meta=meta),
                  requester=student_id)
    return profile


def recall_profile(student_id: str) -> list[Memory]:
    """Through recall (Meko), so a profile shown as context is one Meko actually returned."""
    return get_memory().recall("student profile projects target companies languages",
                               [student_scope(student_id)], requester=student_id, k=1,
                               kinds=[KIND], min_similarity=-1)


def project_from(recalled: list[Memory]) -> dict | None:
    for m in recalled:
        projects = (m.meta.get("profile") or {}).get("projects") or []
        if projects:
            return projects[0]
    return None
