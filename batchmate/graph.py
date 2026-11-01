"""LangGraph loop: plan → ask → (wait for answer) → evaluate → ask … → wrap_up.

Each node is a plain function over a dict state, so the loop is testable without LangGraph.
`Coach` wraps the compiled graph: one thread per mock session, `interrupt()` waits for the answer.
"""
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from . import config
from .agents import evaluator, interviewer, planner
from .memory import Memory, get_memory, student_scope
from .memory.base import now_iso
from .topics import label, short


class State(TypedDict, total=False):
    session_id: str
    student_id: str
    company: str
    role: str
    days_left: int
    memory_on: bool
    max_turns: int
    turn: int
    plan: dict
    prior_weak: list[str]
    question: dict
    recalled: list[dict]  # A4: exactly what was retrieved for the current step, nothing else
    answer: str
    transcript: list[dict]
    notes: list[str]
    summary: str
    done: bool


def _panel(mems: list[Memory]) -> list[dict]:
    out = []
    for m in mems:
        personal = m.scope.startswith("student-")
        n = m.source_count
        if m.kind == "next_plan":
            where = "promised in your last session"
        elif m.kind == "student_profile":
            where = "from your profile"
        elif m.kind == "asked":
            where = "from your memory of earlier sessions"
        elif m.kind == "lesson":
            where = f"from your batch, {n} opted-in students (anonymous)"
        elif personal:
            where = f"from your memory, {n} session{'s' * (n > 1)}"
        else:
            where = f"from batch knowledge, {n} verified report{'s' * (n > 1)}"
        if m.meta.get("seeded"):
            where += " (seeded demo data)"
        out.append({"id": m.id, "source": where, "text": m.text, "kind": m.kind,
                    "confidence": m.confidence, "personal": personal,
                    "via": "Meko" if m.meta.get("from_meko") else "local store"})
    return out


# ---------------- nodes ----------------
def plan_node(s: State) -> State:
    p, ctx = planner.plan(s["student_id"], s["company"], s["role"], s.get("days_left", 5), s["memory_on"])
    prior = [m.meta.get("topic") for m in ctx["weaknesses"]]
    return {"plan": p.model_dump(), "prior_weak": prior, "turn": 0, "transcript": [], "notes": [],
            "recalled": _panel(ctx.get("commitments", []) + ctx["patterns"] + ctx["weaknesses"]
                               + ctx.get("lessons", []))}


def ask_node(s: State) -> State:
    q, recalled = interviewer.next_question(s)
    return {"question": q.model_dump(), "recalled": _panel(recalled)}


def answer_node(s: State) -> State:
    from langgraph.types import interrupt

    return {"answer": interrupt({"question": s["question"]})}


def evaluate_node(s: State) -> State:
    q = s["question"]
    ev = evaluator.evaluate(q["text"], s["answer"], q["topic"])
    notes = evaluator.remember(s["student_id"], q["topic"], ev, s["session_id"]) if s["memory_on"] else []
    if s["memory_on"]:  # so the next session never asks this again
        interviewer.remember_asked(s["student_id"], q["topic"], q["text"], s["session_id"])
    item = {"question": q["text"], "topic": q["topic"], "is_follow_up": q["is_follow_up"],
            "answer": s["answer"], "eval": ev.model_dump()}
    # Follow-ups don't consume a planned topic slot.
    turn = s["turn"] + (0 if q["is_follow_up"] else 1)
    return {"transcript": s["transcript"] + [item], "notes": s["notes"] + notes, "turn": turn}


def route_after_eval(s: State) -> str:
    asked_main = sum(1 for t in s["transcript"] if not t["is_follow_up"])
    return "wrap_up" if asked_main >= s.get("max_turns", config.MOCK_TURNS) else "ask"


def wrap_up_node(s: State) -> State:
    if not s["memory_on"]:
        avg = sum(sum(t["eval"]["scores"].values()) / 4 for t in s["transcript"]) / max(1, len(s["transcript"]))
        return {"summary": f"Session done. Average score {avg:.1f}/5. Keep practising.", "done": True}

    weak_now = {t["topic"] for t in s["transcript"] if t["eval"]["weak"]}
    good_now = {t["topic"] for t in s["transcript"] if not t["eval"]["weak"]} - weak_now
    prior = set(s.get("prior_weak", []))
    parts = [f"You explained {short(t)} much better than last time"
             for t in sorted(prior & good_now)]
    still = sorted((prior - good_now) | weak_now)
    if still:
        parts.append(f"{', '.join(label(t) for t in still)} {'is' if len(still) == 1 else 'are'} still weak, "
                     f"so tomorrow we'll drill {short(still[0])}")
    summary = ("; ".join(parts) or "Strong session across the board") + "."
    get_memory().write(Memory(scope=student_scope(s["student_id"]), kind="session", text=summary,
                              meta={"session_id": s["session_id"], "company": s["company"],
                                    "observed_at": now_iso(),
                                    "topics": [t["topic"] for t in s["transcript"]]}),
                       requester=s["student_id"])
    # Keep the promise: store the next drill so the next plan starts with it.
    mem, scope = get_memory(), student_scope(s["student_id"])
    for old in mem.list(scope, s["student_id"], kinds=["next_plan"], statuses=("active",)):
        mem.update(old.id, requester=s["student_id"], status="resolved")
    if still:
        mem.write(Memory(scope=scope, kind="next_plan", text=f"Next session: drill {label(still[0])}.",
                         meta={"topic": still[0], "company": s["company"], "observed_at": now_iso(),
                               "from_session": s["session_id"]}), requester=s["student_id"])
    return {"summary": summary, "done": True}


# ---------------- graph ----------------
def build_graph(checkpointer=None):
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(State)
    g.add_node("plan", plan_node)
    g.add_node("ask", ask_node)
    g.add_node("answer", answer_node)
    g.add_node("evaluate", evaluate_node)
    g.add_node("wrap_up", wrap_up_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "ask")
    g.add_edge("ask", "answer")
    g.add_edge("answer", "evaluate")
    g.add_conditional_edges("evaluate", route_after_eval, {"ask": "ask", "wrap_up": "wrap_up"})
    g.add_edge("wrap_up", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


class Coach:
    """Session API used by FastAPI and Gradio."""

    def __init__(self):
        self.graph = build_graph()

    def _cfg(self, sid):
        return {"configurable": {"thread_id": sid}}

    def _view(self, sid) -> dict[str, Any]:
        st = self.graph.get_state(self._cfg(sid)).values
        return {"session_id": sid, **{k: st.get(k) for k in
                ("plan", "question", "recalled", "transcript", "notes", "summary", "done")}}

    def start(self, student_id, company, role, days_left=5, memory_on=True, max_turns=None) -> dict:
        sid = uuid.uuid4().hex[:10]
        self.graph.invoke({"session_id": sid, "student_id": student_id, "company": company, "role": role,
                           "days_left": days_left, "memory_on": memory_on,
                           "max_turns": max_turns or config.MOCK_TURNS}, self._cfg(sid))
        return self._view(sid)

    def owner(self, sid: str) -> str | None:
        try:
            return self.graph.get_state(self._cfg(sid)).values.get("student_id")
        except Exception:
            return None

    def answer(self, sid: str, text: str) -> dict:
        from langgraph.types import Command

        if self.graph.get_state(self._cfg(sid)).values.get("done"):
            return self._view(sid)  # session over; ignore extra answers
        self.graph.invoke(Command(resume=text), self._cfg(sid))
        return self._view(sid)


def run_offline(student_id, company, role, answers: list[str], memory_on=True, max_turns=3) -> State:
    """The same loop without LangGraph: used by tests and as a sanity check."""
    s: State = {"session_id": uuid.uuid4().hex[:10], "student_id": student_id, "company": company,
                "role": role, "days_left": 5, "memory_on": memory_on, "max_turns": max_turns}
    s.update(plan_node(s))
    answers = list(answers)
    while True:
        s.update(ask_node(s))
        s["answer"] = answers.pop(0) if answers else "I'm not sure."
        s.update(evaluate_node(s))
        if route_after_eval(s) == "wrap_up":
            s.update(wrap_up_node(s))
            return s
