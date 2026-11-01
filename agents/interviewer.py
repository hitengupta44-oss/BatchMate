"""Interviewer: picks each question and adaptive follow-ups, recalling before every question.

With memory on it recalls, from Meko: the student's weak spots and strengths on the topic, the
company's verified patterns, the student's profile (to ask about THEIR project), and the questions
it already asked this student in earlier sessions, so it never repeats itself.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..concurrency import parallel
from ..llm import structured
from ..memory import Memory, company_scope, get_memory, student_scope
from ..memory.base import now_iso
from ..topics import TOPICS, label
from . import profile as profile_agent

ASKED = "asked"


class Question(BaseModel):
    text: str
    topic: str
    is_follow_up: bool = False
    why: str = ""


def recall_for_topic(student_id: str, company: str, topic: str) -> list:
    mem = get_memory()
    q = f"{label(topic)} {company}"
    r = parallel(
        personal=lambda: mem.recall(q, [student_scope(student_id)], requester=student_id, k=3,
                                    kinds=["weakness", "strength"], min_similarity=0.1),
        shared=lambda: mem.recall(q, [company_scope(company)], requester=student_id, k=2,
                                  kinds=["pattern"], min_similarity=0.1))
    return [m for m in r["personal"] + r["shared"] if m.meta.get("topic") == topic]


def recall_asked(student_id: str, topic: str) -> list[str]:
    """Questions on this topic the student already answered in earlier sessions (from Meko)."""
    hits = get_memory().recall(f"asked about {label(topic)}", [student_scope(student_id)],
                               requester=student_id, k=12, kinds=[ASKED], min_similarity=-1)
    return [h.meta.get("question") or h.text for h in hits if h.meta.get("topic") == topic]


def remember_asked(student_id: str, topic: str, question: str, session_id: str) -> None:
    get_memory().write(Memory(scope=student_scope(student_id), kind=ASKED,
                              text=f"Asked about {label(topic)}: {question}",
                              meta={"topic": topic, "question": question, "session_id": session_id,
                                    "observed_at": now_iso()}), requester=student_id)


def _norm(q: str) -> str:
    return " ".join(q.lower().replace("follow-up on your last answer:", "").split())[:90]


def next_question(state: dict) -> tuple[Question, list]:
    turn, topics = state["turn"], state["plan"]["mock_topics"]
    asked_now = [t["question"] for t in state["transcript"]]
    last = state["transcript"][-1] if state["transcript"] else None
    memory_on = state["memory_on"]
    student = state["student_id"]

    # Adaptive follow-up: if the last answer was weak on complexity, probe it once.
    if memory_on and last and not last.get("is_follow_up") and last["eval"]["scores"]["complexity"] <= 2 \
            and last["topic"] != "time_complexity":
        topic, follow_up = "time_complexity", True
    else:
        topic, follow_up = topics[min(turn, len(topics) - 1)], False

    recalled, asked_before, prof = [], [], []
    if memory_on:
        r = parallel(recalled=lambda: recall_for_topic(student, state["company"], topic),
                     asked=lambda: recall_asked(student, topic),
                     prof=lambda: profile_agent.recall_profile(student))
        recalled, asked_before, prof = r["recalled"], r["asked"], r["prof"]
    project = profile_agent.project_from(prof)

    def offline() -> Question:
        seen = {_norm(q) for q in asked_now + asked_before}
        bank = TOPICS[topic]["questions"]
        fresh = [q for q in bank if _norm(q) not in seen]
        # Everything asked before: rotate instead of repeating the first one forever.
        text = fresh[0] if fresh else bank[(len(asked_before) + turn) % len(bank)]
        if project and topic in ("project_explanation", "behavioral_intro"):
            text = f"Let's talk about {project['name']}. {text}"
        if follow_up:
            text = f"Follow-up on your last answer: {text}"
        why = "; ".join(m.text for m in recalled) or "generic question"
        return Question(text=text, topic=topic, is_follow_up=follow_up, why=why)

    if not memory_on:
        return offline(), []

    system = ("You are a realistic, friendly technical interviewer. Ask ONE question at a time. "
              "Use the recalled memory to target the student's weak spots, the patterns seniors "
              "reported, and the student's own projects. NEVER repeat or lightly reword a question "
              "the student was already asked; probe a different angle of the same topic.")
    user = (f"Company: {state['company']} {state['role']}. Topic tag: {topic} ({label(topic)}).\n"
            f"Follow-up on previous answer: {follow_up}. Previous Q/A: "
            f"{(last['question'], last['answer']) if last else None}\n"
            f"Recalled memory: {[m.text for m in recalled]}\n"
            f"Student profile: {[m.text for m in prof]}\n"
            f"Asked in THIS session: {asked_now}\n"
            f"Asked in EARLIER sessions (do not repeat): {asked_before}\n"
            "Return the question text, the topic tag, is_follow_up, and `why` (which memory drove it).")
    q = structured(Question, system, user, offline)
    if _norm(q.text) in {_norm(x) for x in asked_now + asked_before}:
        q = offline()  # the model repeated itself anyway
    q.topic, q.is_follow_up = topic, follow_up
    shown = recalled + ([m for m in prof] if project and topic in ("project_explanation", "behavioral_intro")
                        else [])
    if asked_before:
        shown = shown + [Memory(scope=student_scope(student), kind=ASKED,
                                text=f"Already asked you {len(asked_before)} question"
                                     f"{'s' * (len(asked_before) > 1)} on {label(topic).lower()}; "
                                     "picking a new angle.",
                                source_count=len(asked_before),
                                meta={"topic": topic, "from_meko": True})]
    return q, shown
