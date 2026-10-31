"""Interviewer: picks each question and adaptive follow-ups, recalling before every question."""
from __future__ import annotations

from pydantic import BaseModel

from ..llm import structured
from ..memory import company_scope, get_memory, student_scope
from ..topics import TOPICS, label


class Question(BaseModel):
    text: str
    topic: str
    is_follow_up: bool = False
    why: str = ""


def recall_for_topic(student_id: str, company: str, topic: str) -> list:
    mem = get_memory()
    q = f"{label(topic)} {company}"
    personal = mem.recall(q, [student_scope(student_id)], requester=student_id, k=3,
                          kinds=["weakness", "strength"], min_similarity=0.1)
    shared = mem.recall(q, [company_scope(company)], requester=student_id, k=2,
                        kinds=["pattern"], min_similarity=0.1)
    return [m for m in personal + shared if m.meta.get("topic") == topic]


def next_question(state: dict) -> tuple[Question, list]:
    turn, topics = state["turn"], state["plan"]["mock_topics"]
    asked = [t["question"] for t in state["transcript"]]
    last = state["transcript"][-1] if state["transcript"] else None
    memory_on = state["memory_on"]

    # Adaptive follow-up: if the last answer was weak on complexity, probe it once.
    if memory_on and last and not last.get("is_follow_up") and last["eval"]["scores"]["complexity"] <= 2 \
            and last["topic"] != "time_complexity":
        topic, follow_up = "time_complexity", True
    else:
        topic, follow_up = topics[min(turn, len(topics) - 1)], False

    recalled = recall_for_topic(state["student_id"], state["company"], topic) if memory_on else []

    def offline() -> Question:
        bank = [q for q in TOPICS[topic]["questions"] if q not in asked] or TOPICS[topic]["questions"]
        why = "; ".join(m.text for m in recalled) or "generic question"
        text = bank[0]
        if follow_up:
            text = f"Follow-up on your last answer: {text}"
        return Question(text=text, topic=topic, is_follow_up=follow_up, why=why)

    if not memory_on:
        return offline(), recalled
    system = ("You are a realistic, friendly technical interviewer. Ask ONE question at a time. "
              "Use recalled memory to target the student's weak spots and patterns seniors reported. "
              "Do not repeat questions already asked.")
    user = (f"Company: {state['company']} {state['role']}. Topic tag: {topic} ({label(topic)}).\n"
            f"Follow-up on previous answer: {follow_up}. Previous Q/A: "
            f"{(last['question'], last['answer']) if last else None}\n"
            f"Recalled memory: {[m.text for m in recalled]}\nAlready asked: {asked}\n"
            "Return the question text, the topic tag, is_follow_up, and `why` (which memory drove it).")
    q = structured(Question, system, user, offline)
    q.topic, q.is_follow_up = topic, follow_up
    return q, recalled
