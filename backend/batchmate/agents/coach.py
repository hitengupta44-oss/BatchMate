"""Ask your coach: answers a student's prep questions ONLY from what Meko recalls.

Recall before reasoning: the student's private memory (weak spots, strengths, sessions, profile,
next-session promise), verified company patterns, and anonymous batch tips. The model may only use
those memories and must cite which ones it used; if nothing relevant comes back, it says so
instead of guessing (A5: nothing shown as context that Meko didn't return).
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..llm import structured
from ..memory import Memory, batch_scope, get_memory, student_scope
from ..topics import detect_topics, label

PERSONAL_KINDS = ["weakness", "strength", "session", "next_plan", "student_profile"]


class Reply(BaseModel):
    answer: str = Field(description="2-6 sentences, plain and specific, addressed to the student")
    used: list[int] = Field(default_factory=list, description="numbers of the memories you used")


def _company_scopes(question: str) -> list[str]:
    mem = get_memory()
    scopes = [s for s in mem.list_scopes("company-")]
    q = question.lower()
    named = [s for s in scopes if s.removeprefix("company-").replace("-", " ") in q]
    return named or scopes  # shared and readable by every student


def recall(student_id: str, question: str) -> list[Memory]:
    mem = get_memory()
    hits = mem.recall(question, [student_scope(student_id)], requester=student_id, k=6,
                      kinds=PERSONAL_KINDS, min_similarity=0.0)
    company = _company_scopes(question)
    if company:
        hits += mem.recall(question, company, requester=student_id, k=4, kinds=["pattern"], min_similarity=0.0)
    year = datetime.now(timezone.utc).year
    hits += mem.recall(question, [batch_scope(year)], requester=student_id, k=2, kinds=["lesson"],
                       min_similarity=0.05)
    seen, out = set(), []
    for h in sorted(hits, key=lambda h: h.confidence or 0, reverse=True):
        if h.id not in seen:
            seen.add(h.id)
            out.append(h)
    return out[:8]


_RANK = {"next_plan": 0, "weakness": 1, "pattern": 2, "lesson": 3, "session": 4, "strength": 5,
         "student_profile": 6}


def _about_me(question: str) -> bool:
    words = set(question.lower().replace("?", " ").split())
    return bool(words & {"i", "me", "my", "mine", "myself", "i'm", "am"})


def _offline(question: str, hits: list[Memory]) -> Reply:
    personal = [i for i, h in enumerate(hits) if h.scope.startswith("student-")]
    if not hits or (_about_me(question) and not personal and "company" not in question.lower()
                    and not detect_topics(question)):
        return Reply(answer="I don't have anything in your memory about that yet. Finish a mock with memory "
                            "on and I'll start keeping track.", used=[])
    asked_topics = set(detect_topics(question))
    pool = [i for i, h in enumerate(hits) if not asked_topics or h.meta.get("topic") in asked_topics] or \
        list(range(len(hits)))
    chosen = sorted(pool, key=lambda i: _RANK.get(hits[i].kind, 9))[:4]
    lines = []
    for i in chosen:
        h = hits[i]
        if h.kind == "weakness":
            lines.append(f"You're still working on {label(h.meta.get('topic')).lower()}, so drill that first.")
        elif h.kind == "next_plan":
            lines.append(f"Last session we agreed on this: {h.text}")
        elif h.kind == "pattern":
            lines.append(f"From your seniors: {h.text}")
        elif h.kind == "strength":
            lines.append(f"You've done well on {label(h.meta.get('topic')).lower()} before.")
        else:
            lines.append(h.text)
    return Reply(answer=" ".join(lines), used=chosen)


def ask(student_id: str, question: str) -> tuple[str, list[Memory]]:
    hits = recall(student_id, question)
    numbered = "\n".join(f"[{i}] ({h.kind}) {h.text}" for i, h in enumerate(hits)) or "(nothing recalled)"
    system = ("You are Batchmate, a placement-prep coach. Answer ONLY from the numbered memories "
              "recalled from the student's memory and their batch's verified knowledge. Do not add "
              "facts, company details or statistics that are not in the memories. If the memories "
              "don't answer the question, say plainly that you don't have that in memory yet and "
              "suggest what would create it (a mock, or a senior sharing an experience). "
              "List the numbers of the memories you used.")
    user = f"Student question: {question}\n\nRecalled memories:\n{numbered}"
    reply = structured(Reply, system, user, lambda: _offline(question, hits))
    used = [hits[i] for i in reply.used if isinstance(i, int) and 0 <= i < len(hits)]
    return reply.answer, used  # only memories the answer actually used are shown as its sources
