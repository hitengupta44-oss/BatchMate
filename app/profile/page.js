"use client";

import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { useApiAction, useRequireSession } from "../../lib/session";

const EMPTY = { branch: "", year: "", target_companies: [], projects: [], languages: [], goal: "" };
const list = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Profile() {
  const { session, notify } = useRequireSession("student");
  const run = useApiAction();
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session) return;
    run(() => api("/me/profile")).then((data) => setP({ ...EMPTY, ...(data || {}) }));
  }, [session, run]);

  const setProject = (i, field, value) => {
    const projects = p.projects.map((x, j) => (j === i ? { ...x, [field]: value } : x));
    setP({ ...p, projects });
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    const body = { ...p, projects: p.projects.filter((x) => x.name.trim()) };
    const saved = await run(() => api("/me/profile", { method: "PUT", body }));
    setBusy(false);
    if (saved) {
      setP({ ...EMPTY, ...saved });
      notify("Profile saved. Your next mock will ask about your own projects.");
    }
  };

  if (!session) return null;

  return (
    <Shell>
      <div className="page">
        <header className="page-head">
          <h1>Your profile</h1>
          <p>
            The interviewer uses this to ask about your own projects and target companies. It's stored in
            your private memory and only you can see it. Only add what interview prep needs: no phone, email
            or marks.
          </p>
        </header>

        {!p && <p className="muted">Loading…</p>}
        {p && (
          <form className="share" onSubmit={save}>
            <div className="row">
              <label className="field">
                Branch
                <input value={p.branch} maxLength={60} onChange={(e) => setP({ ...p, branch: e.target.value })} />
              </label>
              <label className="field">
                Year
                <input value={p.year} maxLength={20} onChange={(e) => setP({ ...p, year: e.target.value })} />
              </label>
            </div>
            <label className="field">
              Target companies (comma-separated)
              <input value={p.target_companies.join(", ")}
                     onChange={(e) => setP({ ...p, target_companies: list(e.target.value).slice(0, 8) })} />
            </label>
            <label className="field">
              Languages you interview in (comma-separated)
              <input value={p.languages.join(", ")}
                     onChange={(e) => setP({ ...p, languages: list(e.target.value).slice(0, 6) })} />
            </label>
            <label className="field">
              Goal this season
              <input value={p.goal} maxLength={200} onChange={(e) => setP({ ...p, goal: e.target.value })} />
            </label>

            <fieldset className="projects">
              <legend>Projects</legend>
              {p.projects.map((proj, i) => (
                <div key={i} className="project-row">
                  <label className="field">
                    Name
                    <input value={proj.name} maxLength={80} onChange={(e) => setProject(i, "name", e.target.value)} />
                  </label>
                  <label className="field field-wide">
                    What it does and what you built
                    <textarea rows={2} value={proj.summary} maxLength={300}
                              onChange={(e) => setProject(i, "summary", e.target.value)} />
                  </label>
                  <button type="button" className="btn btn-danger"
                          onClick={() => setP({ ...p, projects: p.projects.filter((_, j) => j !== i) })}>
                    Remove
                  </button>
                </div>
              ))}
              {p.projects.length < 5 && (
                <button type="button" className="btn btn-quiet"
                        onClick={() => setP({ ...p, projects: [...p.projects, { name: "", summary: "" }] })}>
                  Add a project
                </button>
              )}
            </fieldset>

            <button className="btn btn-ink" type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save profile"}
            </button>
          </form>
        )}
      </div>
    </Shell>
  );
}
