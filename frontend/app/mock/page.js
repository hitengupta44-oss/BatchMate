"use client";

import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import MekoRegister from "../../components/MekoRegister";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

function Scores({ s }) {
  const rows = [
    ["Correctness", s.correctness],
    ["Clarity", s.clarity],
    ["Complexity", s.complexity],
    ["Communication", s.communication],
  ];
  return (
    <dl className="rubric">
      {rows.map(([k, v]) => (
        <div key={k} className="rubric-cell">
          <dt>{k}</dt>
          <dd>
            <span className="rubric-score">{v}</span>/5
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MarginNote({ r, onForget, label }) {
  const conf = typeof r.confidence === "number" ? r.confidence : null;
  return (
    <div className="note">
      <p className="note-text">
        <mark>{r.text}</mark>
      </p>
      <p className="note-source">
        {r.source}
        {r.via ? `, retrieved from ${r.via}` : ""}
        {conf !== null && (
          <span className="note-conf" title={`confidence ${conf.toFixed(2)}`}>
            <span style={{ width: `${Math.max(6, conf * 100)}%` }} />
          </span>
        )}
      </p>
      {r.personal && !["next_plan", "asked", "student_profile"].includes(r.kind) && (
        <button className="note-forget" type="button" onClick={() => onForget(r)}>
          Forget this
        </button>
      )}
    </div>
  );
}

export default function Mock() {
  const { session, label, notify } = useRequireSession("student");
  const run = useApiAction();
  const [form, setForm] = useState({ company: "Amazon", role: "SDE intern", days: 5, memory: true });
  const [sid, setSid] = useState(null);
  const [plan, setPlan] = useState(null);
  const [recalled, setRecalled] = useState([]);
  const [items, setItems] = useState([]); // {type: q|a|fb|end, ...}
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(null);
  const [done, setDone] = useState(false);
  const [pulse, setPulse] = useState(0);
  const endRef = useRef(null);
  const answerRef = useRef(null);

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [items]);

  const applyView = (view, prev) => {
    const next = [...prev];
    if (view.done) next.push({ type: "end", text: view.summary });
    else if (view.question) next.push({ type: "q", ...view.question });
    setItems(next);
    setRecalled(view.recalled || []);
    setDone(Boolean(view.done));
    setPulse((p) => p + 1);
    if (!view.done && answerRef.current) answerRef.current.focus();
  };

  const start = async (e) => {
    e.preventDefault();
    setBusy("start");
    setItems([]);
    setPlan(null);
    setDone(false);
    const view = await run(() =>
      api("/sessions", {
        method: "POST",
        body: { company: form.company, role: form.role, days_left: Number(form.days) || 5, memory_on: form.memory },
      })
    );
    setBusy(null);
    if (!view) return;
    setSid(view.session_id);
    setPlan(view.plan);
    applyView(view, []);
  };

  const send = async (e) => {
    e.preventDefault();
    const text = answer.trim();
    if (!text || !sid) return;
    setBusy("answer");
    const withAnswer = [...items, { type: "a", text }];
    setItems(withAnswer);
    setAnswer("");
    const view = await run(() => api(`/sessions/${sid}/answer`, { method: "POST", body: { text } }));
    setBusy(null);
    if (!view) return;
    const last = view.transcript[view.transcript.length - 1];
    applyView(view, [...withAnswer, { type: "fb", scores: last.eval.scores, text: last.eval.feedback }]);
  };

  const forget = async (r) => {
    const ok = await run(() => api(`/memory/${r.id}`, { method: "DELETE" }));
    if (ok) {
      setRecalled((list) => list.filter((x) => x.id !== r.id));
      notify("Forgotten. It's deleted from Meko and won't be used again.");
      setPulse((p) => p + 1);
    }
  };

  if (!session) return null;

  return (
    <Shell>
      <form className="setup" onSubmit={start}>
        <label className="field">
          Company
          <input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} required />
        </label>
        <label className="field">
          Role
          <input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} required />
        </label>
        <label className="field field-narrow">
          Days left
          <input type="number" min="1" max="60" value={form.days}
                 onChange={(e) => setForm({ ...form, days: e.target.value })} />
        </label>
        <label className="switch">
          <input type="checkbox" checked={form.memory} onChange={(e) => setForm({ ...form, memory: e.target.checked })} />
          <span className="switch-track" aria-hidden="true" />
          <span>{form.memory ? "Memory on" : "Memory off"}</span>
        </label>
        <button className="btn btn-ink" type="submit" disabled={busy === "start"}>
          {busy === "start" ? "Planning…" : sid ? "Start a new mock" : "Start mock"}
        </button>
      </form>

      <div className="desk">
        <section className="sheet" aria-label="Interview">
          <aside className="margin" aria-label="What the coach recalled">
            {plan && (
              <div className="plan">
                <h2 className="plan-title">Today: {plan.mock_topics.map(label).join(", ")}</h2>
                {plan.rationale && <p className="plan-why">{plan.rationale}</p>}
              </div>
            )}
            {recalled.length > 0
              ? recalled.map((r) => <MarginNote key={r.id} r={r} label={label} onForget={forget} />)
              : (
                <p className="note note-empty">
                  {!sid
                    ? "Start a mock. Whatever I remember about you or your seniors shows up here, in the margin."
                    : form.memory
                      ? "Nothing in memory for this question."
                      : "Memory is off, so I'm starting from zero."}
                </p>
              )}
          </aside>

          <div className="ruled">
            {items.length === 0 && (
              <div className="sheet-empty">
                <h1 className="sheet-empty-title">Your answer sheet</h1>
                <p>
                  Run the same mock twice: once with memory off, once with it on. The questions, the follow-ups
                  and the closing remark change with what Batchmate remembers.
                </p>
              </div>
            )}
            <ol className="script">
              {items.map((it, i) => {
                if (it.type === "q")
                  return (
                    <li key={i} className="q">
                      <span className="q-topic">{it.is_follow_up ? `Follow-up on ${label(it.topic)}` : label(it.topic)}</span>
                      {it.text}
                    </li>
                  );
                if (it.type === "a") return <li key={i} className="a">{it.text}</li>;
                if (it.type === "fb")
                  return (
                    <li key={i} className="fb">
                      <Scores s={it.scores} />
                      <p>{it.text}</p>
                    </li>
                  );
                return (
                  <li key={i} className="remark">
                    <span className="remark-label">Examiner's remark</span>
                    {it.text}
                  </li>
                );
              })}
              {busy === "answer" && <li className="thinking">Reading your answer…</li>}
              <li ref={endRef} aria-hidden="true" className="script-end" />
            </ol>

            {sid && !done && (
              <form className="answer" onSubmit={send}>
                <label htmlFor="answer" className="sr-only">Your answer</label>
                <textarea id="answer" ref={answerRef} rows={4} value={answer}
                          placeholder="Answer as you would out loud. Ctrl+Enter sends."
                          onChange={(e) => setAnswer(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(e);
                          }} />
                <button className="btn btn-ink" type="submit" disabled={busy === "answer" || !answer.trim()}>
                  Send answer
                </button>
              </form>
            )}
          </div>
        </section>

        <MekoRegister pulse={pulse} />
      </div>
    </Shell>
  );
}
