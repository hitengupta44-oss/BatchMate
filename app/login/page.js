"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

const NAMES = {
  priya: { name: "Priya", line: "3rd-year CSE, Amazon SDE intern interview in 5 days" },
  arjun: { name: "Arjun", line: "3rd-year CSE, working on system design" },
  "coordinator-demo": { name: "Placement coordinator", line: "Approves what the whole batch gets to see" },
};

export default function Login() {
  const { session, ready, signIn, notify } = useSession();
  const router = useRouter();
  const [config, setConfig] = useState(null);
  const [picked, setPicked] = useState(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (ready && session) router.replace(session.role === "coordinator" ? "/coordinator" : "/mock");
  }, [ready, session, router]);

  useEffect(() => {
    api("/auth/config")
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const s = await signIn(picked, password);
      notify(`Signed in as ${NAMES[s.user] ? NAMES[s.user].name : s.user}.`);
      router.replace(s.role === "coordinator" ? "/coordinator" : "/mock");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="hallticket" onSubmit={submit}>
        <div className="hallticket-margin" aria-hidden="true" />
        <div className="hallticket-body">
          <h1 className="login-title">Batchmate</h1>
          <p className="login-lede">
            Mock interviews that remember you, and what your seniors were actually asked.
          </p>

          <fieldset className="pick">
            <legend>Sign in as</legend>
            {(config ? config.users : []).map((u) => {
              const info = NAMES[u.id] || { name: u.id, line: u.role };
              return (
                <label key={u.id} className={`pick-option${picked === u.id ? " picked" : ""}`}>
                  <input type="radio" name="user" value={u.id} checked={picked === u.id}
                         onChange={() => setPicked(u.id)} />
                  <span className="pick-name">{info.name}</span>
                  <span className="pick-line">{info.line}</span>
                </label>
              );
            })}
            {!config && !error && <p className="muted">Loading…</p>}
          </fieldset>

          {config && config.password_required && (
            <label className="field">
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                     autoComplete="current-password" required />
            </label>
          )}

          {error && <p className="form-error" role="alert">{error}</p>}

          <button className="btn btn-ink" type="submit" disabled={!picked || busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="fineprint">
            Demo accounts with seeded practice history. Each student's memory is private to them.
          </p>
        </div>
      </form>
    </div>
  );
}
