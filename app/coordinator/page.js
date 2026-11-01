"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "../../components/Shell";
import MekoRegister from "../../components/MekoRegister";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

const COLUMNS = [
  { status: "proposed", title: "Waiting for you", empty: "Nothing waiting. A pattern appears here once 3 seniors report the same topic." },
  { status: "active", title: "Approved, students see these", empty: "Nothing approved yet." },
  { status: "stale", title: "Retired as too old", empty: "Nothing retired." },
  { status: "rejected", title: "Rejected", empty: "Nothing rejected." },
];

export default function Coordinator() {
  const { session, notify } = useRequireSession("coordinator");
  const run = useApiAction();
  const [company, setCompany] = useState("Amazon");
  const [patterns, setPatterns] = useState(null);
  const [steward, setSteward] = useState(null);
  const [busy, setBusy] = useState(null);
  const [pulse, setPulse] = useState(0);

  const load = useCallback(async () => {
    const res = await run(() => Promise.all([api("/patterns", { params: { company } }), api("/steward")]));
    if (res) {
      setPatterns(res[0]);
      setSteward(res[1]);
    }
  }, [company, run]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  const decide = async (p, decision) => {
    setBusy(p.id);
    const ok = await run(() => api(`/patterns/${p.id}/${decision}`, { method: "POST" }));
    setBusy(null);
    if (ok) {
      notify(decision === "approve" ? "Approved and promoted in Meko. Students will see this pattern." : "Rejected.");
      setPulse((x) => x + 1);
      load();
    }
  };

  const runSteward = async () => {
    setBusy("steward");
    const res = await run(() => api("/steward/run", { method: "POST" }));
    setBusy(null);
    if (res) {
      setSteward(res);
      notify("Steward finished.");
      setPulse((x) => x + 1);
      load();
    }
  };

  if (!session) return null;

  return (
    <Shell>
      <div className="desk desk-coord">
        <div className="page">
          <header className="page-head">
            <h1>Patterns from senior experiences</h1>
            <p>
              Students only see a pattern after you approve it. Approving promotes it into Meko's shared
              knowledge for the whole batch. The Steward finds new patterns and retires old ones on its own,
              but never approves anything.
            </p>
          </header>

          <div className="row row-end">
            <label className="field">
              Company
              <input value={company} onChange={(e) => setCompany(e.target.value)} onBlur={load} />
            </label>
            <button className="btn btn-quiet" onClick={runSteward} disabled={busy === "steward"}>
              {busy === "steward" ? "Running…" : "Run the Steward now"}
            </button>
          </div>
          {steward && steward.ran_at && (
            <p className="muted">
              Steward last ran at {new Date(steward.ran_at).toLocaleTimeString()}: {steward.new_proposals} new
              proposals, {(steward.retired || []).length} retired, {(steward.batch_lessons || []).length} batch tips,
              {" "}{steward.meko_resynced || 0} memories re-synced to Meko.
            </p>
          )}

          {patterns === null && <p className="muted">Loading…</p>}
          {patterns && (
            <div className="board">
              {COLUMNS.map((col) => {
                const list = patterns.filter((p) => p.status === col.status);
                return (
                  <section key={col.status} className={`col col-${col.status}`}>
                    <h2>
                      {col.title} <span className="count">{list.length}</span>
                    </h2>
                    {list.length === 0 && <p className="empty">{col.empty}</p>}
                    <ul>
                      {list.map((p) => (
                        <li key={p.id} className="pattern">
                          <p className="pattern-text">{p.text}</p>
                          <p className="pattern-meta">
                            Backed by {p.source_count} report{p.source_count > 1 ? "s" : ""}
                            {p.meta && p.meta.approved_by ? `, approved by ${p.meta.approved_by}` : ""}
                          </p>
                          {col.status === "proposed" && (
                            <div className="card-actions">
                              <button className="btn btn-ink" disabled={busy === p.id} onClick={() => decide(p, "approve")}>
                                Approve
                              </button>
                              <button className="btn btn-quiet" disabled={busy === p.id} onClick={() => decide(p, "reject")}>
                                Reject
                              </button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                );
              })}
            </div>
          )}
        </div>
        <MekoRegister pulse={pulse} />
      </div>
    </Shell>
  );
}
