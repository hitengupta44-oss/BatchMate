"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

const KIND = {
  weakness: "Weak spot",
  strength: "Strength",
  session: "Session summary",
  next_plan: "Next session",
};

export default function Memory() {
  const { session, notify } = useRequireSession("student");
  const run = useApiAction();
  const [rows, setRows] = useState(null);
  const [optIn, setOptIn] = useState(false);

  const load = useCallback(async () => {
    const [mems, opt] = (await run(() => Promise.all([api("/memory"), api("/me/opt-in")]))) || [[], { share_aggregate: false }];
    setRows(mems);
    setOptIn(opt.share_aggregate);
  }, [run]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  const act = async (fn, msg) => {
    if (await run(fn)) {
      notify(msg);
      load();
    }
  };

  const toggleOptIn = async (value) => {
    setOptIn(value);
    const res = await run(() => api("/me/opt-in", { method: "POST", body: { share_aggregate: value } }));
    if (!res) setOptIn(!value);
    else notify(value ? "Your weak topics now count toward anonymous batch tips." : "Stopped sharing.");
  };

  if (!session) return null;
  const active = (rows || []).filter((m) => m.status === "active");
  const past = (rows || []).filter((m) => m.status !== "active");

  return (
    <Shell>
      <div className="page">
        <header className="page-head">
          <h1>What Batchmate remembers about you</h1>
          <p>Only you can see this. Mark a weak spot as fixed once you've got it, or forget anything. Forgetting deletes it from Meko.</p>
        </header>

        <label className="switch switch-wide">
          <input type="checkbox" checked={optIn} onChange={(e) => toggleOptIn(e.target.checked)} />
          <span className="switch-track" aria-hidden="true" />
          <span>
            Let my weak topics count toward anonymous batch tips. Only topics, never your answers or name,
            and only shown when 3 or more students share one.
          </span>
        </label>

        {rows === null && <p className="muted">Loading…</p>}
        {rows && rows.length === 0 && (
          <p className="empty">Nothing yet. Finish a mock with memory on and Batchmate will start remembering.</p>
        )}

        <ul className="cards">
          {active.map((m) => (
            <li key={m.id} className={`card card-${m.kind}`}>
              <div>
                <span className="card-kind">{KIND[m.kind] || m.kind}</span>
                <p className="card-text">{m.text}</p>
                <span className="card-meta">
                  {m.source_count > 1 ? `Seen in ${m.source_count} sessions, ` : ""}updated {m.updated_at.slice(0, 10)}
                  {m.meta && m.meta.seeded ? ", seeded demo data" : ""}
                </span>
              </div>
              <div className="card-actions">
                {m.kind === "weakness" && (
                  <button className="btn btn-quiet" onClick={() =>
                    act(() => api(`/memory/${m.id}/fixed`, { method: "POST" }), "Marked as fixed. It won't come up again.")}>
                    I've fixed this
                  </button>
                )}
                <button className="btn btn-danger" onClick={() =>
                  act(() => api(`/memory/${m.id}`, { method: "DELETE" }), "Forgotten.")}>
                  Forget
                </button>
              </div>
            </li>
          ))}
        </ul>

        {past.length > 0 && (
          <details className="past">
            <summary>Fixed and past items ({past.length})</summary>
            <ul className="cards">
              {past.map((m) => (
                <li key={m.id} className="card card-past">
                  <div>
                    <span className="card-kind">{KIND[m.kind] || m.kind}, {m.status}</span>
                    <p className="card-text">{m.text}</p>
                  </div>
                  <div className="card-actions">
                    <button className="btn btn-danger" onClick={() =>
                      act(() => api(`/memory/${m.id}`, { method: "DELETE" }), "Forgotten.")}>
                      Forget
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </Shell>
  );
}
