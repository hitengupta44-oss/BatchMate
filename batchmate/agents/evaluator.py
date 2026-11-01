"""Evaluator: rubric scoring + writes weaknesses/strengths into the student's private memory."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import structured
from ..memory import Memory, get_memory, student_scope
from ..memory.base import now_iso
from ..topics import TOPICS, label


class Scores(BaseModel):
    correctness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    complexity: int = Field(ge=1, le=5, description="did they state and justify time/space complexity")
    communication: int = Field(ge=1, le=5)


class Evaluation(BaseModel):
    scores: Scores
    feedback: str
    weak: bool = Field(description="true if the answer shows a real weakness on this topic")


def _heuristic(topic: str, answer: str) -> Evaluation:
    a = answer.lower()
    words = len(a.split())
    expect = TOPICS[topic]["expect"]
    hit = sum(1 for e in expect if e in a) / max(1, len(expect))
    correctness = 1 + round(4 * hit)
    complexity = 5 if ("o(" in a and ("space" in a or "because" in a)) else (3 if "o(" in a else 1)
    if topic in ("leadership_principles", "behavioral_intro", "project_explanation"):
        complexity = 3  # not applicable; neutral
    clarity = 2 if words < 15 else (4 if words < 120 else 3)
    communication = min(5, clarity + (1 if any(w in a for w in ("first", "then", "because", "so")) else 0))
    weak = correctness <= 2 or (topic == "time_complexity" and complexity <= 3)
    missing = [e for e in expect if e not in a]
    fb = "Solid." if not weak else f"Missing: {', '.join(missing) or 'depth'}."
    if complexity <= 2 and topic not in ("leadership_principles", "behavioral_intro", "project_explanation"):
        fb += " State the time and space complexity and why."
    return Evaluation(scores=Scores(correctness=correctness, clarity=clarity, complexity=complexity,
                                    communication=communication), feedback=fb, weak=weak)


def evaluate(question: str, answer: str, topic: str) -> Evaluation:
    system = ("You are a strict but kind interview evaluator. Score 1-5 on correctness, clarity, "
              "complexity (stated + justified time/space complexity; 3 if not applicable) and "
              "communication. Give 2-3 sentences of specific feedback. Set weak=true only for a real gap.")
    user = f"Topic: {label(topic)}\nQuestion: {question}\nAnswer: {answer}"
    return structured(Evaluation, system, user, lambda: _heuristic(topic, answer))


def remember(student_id: str, topic: str, ev: Evaluation, session_id: str) -> list[str]:
    """Extracted memories: turn a scored answer into durable 'weak at X' / 'improved at Y' facts."""
    mem = get_memory()
    scope = student_scope(student_id)
    existing = {m.meta.get("topic"): m for m in mem.list(scope, student_id, kinds=["weakness"],
                                                          statuses=("active",))}
    notes = []
    prior = existing.get(topic)
    good = ev.scores.correctness >= 4 and ev.scores.communication >= 4 and not ev.weak
    if ev.weak:
        if prior:
            sessions = sorted(set(prior.meta.get("sessions", []) + [session_id]))
            mem.update(prior.id, requester=student_id, source_count=len(sessions),
                       text=f"Weak at {label(topic)} (seen in {len(sessions)} sessions). Last note: {ev.feedback}",
                       meta={**prior.meta, "sessions": sessions, "observed_at": now_iso()})
            notes.append(f"still weak: {label(topic)}")
        else:
            mem.write(Memory(scope=scope, kind="weakness", text=f"Weak at {label(topic)}. {ev.feedback}",
                             meta={"topic": topic, "sessions": [session_id], "observed_at": now_iso()}),
                      requester=student_id)
            notes.append(f"new weak spot: {label(topic)}")
    elif good:
        if prior:
            improved = prior.meta.get("improved", 0) + 1
            meta = {**prior.meta, "improved": improved, "observed_at": now_iso()}
            # Two good sessions in a row → the weakness is resolved (kept for history, not recalled).
            mem.update(prior.id, requester=student_id, meta=meta,
                       status="resolved" if improved >= 2 else "active")
            notes.append(f"improved: {label(topic)}")
        mem.write(Memory(scope=scope, kind="strength", text=f"Answered {label(topic)} well.",
                         meta={"topic": topic, "sessions": [session_id], "observed_at": now_iso()}),
                  requester=student_id)
    return notes
