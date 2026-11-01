"use client";

import { useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

export default function Share() {
  const { session, label, notify } = useRequireSession();
  const run = useApiAction();
  const [form, setForm] = useState({
    text: "",
    company: "Amazon",
    role: "SDE intern",
    date: new Date().toISOString().slice(0, 10),
  });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const rows = await run(() =>
      api("/experiences", {
        method: "POST",
        body: { text: form.text, company: form.company, role: form.role, interview_date: form.date },
      })
    );
    setBusy(false);
    if (!rows) return;
    setResult(rows);
    if (rows.length) {
      setForm({ ...form, text: "" });
      notify(`Added ${rows.length} topic${rows.length > 1 ? "s" : ""}. Thanks for helping your juniors.`);
    }
  };

  if (!session) return null;

  return (
    <Shell>
      <div className="page">
        <header className="page-head">
          <h1>Share what you were asked</h1>
          <p>
            Names, emails and phone numbers are removed before anything is stored. Only the topics are kept,
            never the exact questions. A topic becomes batch knowledge only after 3 seniors report it and a
            coordinator approves it.
          </p>
        </header>

        <form className="share" onSubmit={submit}>
          <label className="field">
            Your experience
            <textarea className="lined" rows={8} required value={form.text}
                      placeholder="Round 1 was an online test with a sliding-window question. Round 2 started with my project, then an LRU cache…"
                      onChange={(e) => setForm({ ...form, text: e.target.value })} />
          </label>
          <div className="row">
            <label className="field">
              Company
              <input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            </label>
            <label className="field">
              Role
              <input required value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </label>
            <label className="field">
              Interview date
              <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </label>
          </div>
          <button className="btn btn-ink" type="submit" disabled={busy}>
            {busy ? "Structuring…" : "Add to batch knowledge"}
          </button>
        </form>

        {result && result.length === 0 && (
          <p className="empty">
            Nothing new was added. Either this was already shared, or no interview topics were found. Mention
            rounds and topics, like "Round 2: LRU cache".
          </p>
        )}
        {result && result.length > 0 && (
          <table className="table">
            <caption>What Batchmate stored</caption>
            <thead>
              <tr><th>Round</th><th>Topic</th><th>Outcome</th></tr>
            </thead>
            <tbody>
              {result.map((m) => (
                <tr key={m.id}>
                  <td>{m.meta.round}</td>
                  <td>{label(m.meta.topic)}</td>
                  <td>{m.meta.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
