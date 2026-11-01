"""Planner: builds a prep plan from company, date and the student's weak areas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..concurrency import parallel
from ..llm import structured
from datetime import datetime, timezone

from ..memory import batch_scope, company_scope, get_memory, student_scope
from ..topics import GENERIC_TOPICS, TOPICS, label

BEHAVIOURAL = {"leadership_principles", "behavioral_intro", "project_explanation"}


class Plan(BaseModel):
    mock_topics: list[str] = Field(description="3 topic tags for today's mock, most important first")
    focus_areas: list[str] = Field(description="topic tags to focus on before the interview")
    daily_plan: list[str] = Field(description="one short line per remaining day")
    rationale: str


def recall_context(student_id: str, company: str, role: str) -> dict:
    """Recall before reasoning: personal weaknesses + verified company patterns (in parallel)."""
    mem = get_memory()
    me, co = [student_scope(student_id)], [company_scope(company)]
    year = batch_scope(datetime.now(timezone.utc).year)
    r = parallel(
        weaknesses=lambda: mem.recall(f"weak areas struggled with in {company} {role} mock interviews", me,
                                      requester=student_id, k=5, kinds=["weakness"], min_similarity=-1),
        strengths=lambda: mem.recall("answered well", me, requester=student_id, k=5,
                                     kinds=["strength"], min_similarity=-1),
        patterns=lambda: mem.recall(f"{company} {role} interview rounds topics asked", co,
                                    requester=student_id, k=8, kinds=["pattern"], min_similarity=-1),
        # Through recall (Meko), not a ledger read: anything shown as context must come from search.
        commitments=lambda: mem.recall("next session drill", me, requester=student_id, k=1,
                                       kinds=["next_plan"], min_similarity=-1),
        lessons=lambda: mem.recall(f"batch working on {company} interview topics", [year],
                                   requester=student_id, k=3, kinds=["lesson"], min_similarity=-1),
    )
    r["commitments"] = r["commitments"][:1]
    return r


def plan(student_id: str, company: str, role: str, days_left: int, memory_on: bool) -> tuple[Plan, dict]:
    ctx = recall_context(student_id, company, role) if memory_on else \
        {"weaknesses": [], "strengths": [], "patterns": [], "commitments": [], "lessons": []}
    weak = [m.meta.get("topic") for m in ctx["weaknesses"] if m.meta.get("topic")]
    pats = [m.meta.get("topic") for m in ctx["patterns"] if m.meta.get("topic")]
    strong = {m.meta.get("topic") for m in ctx.get("strengths", [])} - set(weak)

    def offline() -> Plan:
        if not memory_on:
            return Plan(mock_topics=GENERIC_TOPICS, focus_areas=GENERIC_TOPICS,
                        daily_plan=[f"Day {d + 1}: mixed DSA practice" for d in range(days_left)],
                        rationale="No memory: a generic warm-up set.")
        # Later rounds first (where the batch actually gets filtered), most-corroborated first.
        ranked = sorted(ctx["patterns"], key=lambda m: (-m.meta.get("round", 1), -m.source_count))
        top_pats = [m.meta["topic"] for m in ranked if m.meta.get("topic") not in strong][:2]
        promised = [m.meta["topic"] for m in ctx.get("commitments", []) if m.meta.get("topic")]
        extra_weak = [w for w in promised + weak if w not in top_pats][:1]
        mock = list(dict.fromkeys(top_pats + extra_weak + weak + pats))[:3] or GENERIC_TOPICS
        mock.sort(key=lambda t: t in BEHAVIOURAL)  # technical first, behavioural last
        ordered = list(dict.fromkeys(mock + weak + pats))
        days = [f"Day {d + 1}: {label(ordered[d % len(ordered)])}" for d in range(days_left)]
        why = []
        if pats:
            why.append("batch knowledge: " + ", ".join(label(p) for p in pats))
        if promised:
            why.append("promised last session: drill " + label(promised[0]))
        if weak:
            why.append("your weak spots: " + ", ".join(label(w) for w in weak))
        return Plan(mock_topics=mock, focus_areas=ordered, daily_plan=days, rationale="; ".join(why))

    system = ("You are the Planner for an interview coach. Use ONLY the recalled context; never "
              f"invent what a company asks. Valid topic tags: {', '.join(TOPICS)}.")
    user = (f"Company: {company}, role: {role}, days left: {days_left}.\n"
            f"Student weaknesses (recalled): {[m.text for m in ctx['weaknesses']]}\n"
            f"Verified company patterns (recalled): {[m.text for m in ctx['patterns']]}\n"
            "Pick 3 mock_topics for today (company patterns first, then weaknesses), focus_areas, "
            "a one-line-per-day daily_plan, and a short rationale.")
    p = structured(Plan, system, user, offline) if memory_on else offline()
    p.mock_topics = [t for t in p.mock_topics if t in TOPICS][:3] or offline().mock_topics
    return p, ctx
