"use client";

import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import MekoRegister from "../../components/MekoRegister";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

const STARTERS = [
  "What should I focus on before my Amazon interview?",
  "What did seniors say about Amazon round 2?",
  "Have I improved at explaining time complexity?",
  "What did we agree to drill next?",
];

export default function Ask() {
  const { session } = useRequireSession("student");
  const run = useApiAction();
  const [turns, setTurns] = useState([]); // {q, answer, sources}
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [pulse, setPulse] = useState(0);
  const endRef = useRef(null);

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns, busy]);

  const ask = async (text) => {
    const q = (text || question).trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setTurns((t) => [...t, { q, answer: null, sources: [] }]);
    const res = await run(() => api("/coach/ask", { method: "POST", body: { question: q } }));
    setBusy(false);
    setPulse((p) => p + 1);
    setTurns((t) => {
      const next = [...t];
      next[next.length - 1] = res
        ? { q, answer: res.answer, sources: res.sources || [] }
        : { q, answer: "That question didn't go through. Try again in a moment.", sources: [], failed: true };
      return next;
    });
  };

  if (!session) return null;

  return (
    <Shell>
      <div className="desk">
        <section className="sheet sheet-ask" aria-label="Ask your coach">
          <div className="ruled">
            <header className="ask-head">
              <h1 className="sheet-empty-title">Ask your coach</h1>
              <p>
                Answers come only from what Batchmate remembers about you and what your seniors verified.
                If it isn't in memory, the coach says so instead of guessing. Each answer lists the
                memories it used.
              </p>
            </header>

            {turns.length === 0 && (
              <div className="starters">
                {STARTERS.map((s) => (
                  <button key={s} type="button" className="starter" onClick={() => ask(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            <ol className="script">
              {turns.map((t, i) => (
                <li key={i} className="ask-turn">
                  <p className="a">{t.q}</p>
                  {t.answer === null ? (
                    <p className="thinking">Recalling from Meko, then writing an answer. This takes about 10 seconds.</p>
                  ) : (
                    <div className="coach-answer">
                      <p className="q">{t.answer}</p>
                      {t.sources.length > 0 ? (
                        <div className="sources">
                          <span className="sources-label">From memory</span>
                          <ul>
                            {t.sources.map((s) => (
                              <li key={s.id} className="source">
                                <mark>{s.text}</mark>
                                <span className="note-source">
                                  {s.source}
                                  {s.via ? `, retrieved from ${s.via}` : ""}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        !t.failed && <p className="sources-none">No memories used for this answer.</p>
                      )}
                    </div>
                  )}
                </li>
              ))}
              <li ref={endRef} aria-hidden="true" className="script-end" />
            </ol>

            <form
              className="answer"
              onSubmit={(e) => {
                e.preventDefault();
                ask();
              }}
            >
              <label htmlFor="question" className="sr-only">Your question</label>
              <textarea
                id="question"
                rows={2}
                value={question}
                placeholder="Ask about your weak spots, your plan, or what seniors reported."
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    ask();
                  }
                }}
              />
              <button className="btn btn-ink" type="submit" disabled={busy || !question.trim()}>
                Ask
              </button>
            </form>
          </div>
        </section>
        <MekoRegister pulse={pulse} />
      </div>
    </Shell>
  );
}
