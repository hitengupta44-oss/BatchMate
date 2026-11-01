"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

const VERBS = {
  memory_search: "recalled from",
  memory_add: "wrote to",
  memory_update: "updated in",
  memory_delete_by_id: "forgot in",
  memory_promote: "promoted in",
  datapack_search: "looked up",
  datapack_create: "created",
  conversation_create: "opened a conversation in",
};

function time(at) {
  return new Date(at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortPack(name) {
  return name ? String(name).replace(/^batchmate-/, "") : "Meko";
}

/** Live register of every Meko call the server makes. Polls while `active`. */
export default function MekoRegister({ active = true, pulse = 0 }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    try {
      setOpen(window.localStorage.getItem("bm_register_open") === "1");
    } catch {
      /* storage blocked: stay closed */
    }
  }, []);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem("bm_register_open", next ? "1" : "0");
    } catch {
      /* ignore */
    }
  };
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const newest = useRef(0);
  const [fresh, setFresh] = useState(new Set());

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api("/meko/log", { params: { limit: 40 } });
        if (!alive) return;
        const latest = data.length ? data[0].at : 0;
        const added = new Set(data.filter((r) => r.at > newest.current && newest.current > 0).map((r) => r.at));
        newest.current = Math.max(newest.current, latest);
        setRows(data);
        setFresh(added);
        setError(null);
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    if (!open) return () => { alive = false; };
    load();
    if (!active) return () => { alive = false; };
    const t = setInterval(load, 2500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [active, pulse, open]);

  if (!open) {
    return (
      <aside className="register register-closed" aria-label="Meko activity">
        <button type="button" className="btn btn-quiet register-toggle" onClick={toggle} aria-expanded="false">
          Show Meko activity
        </button>
        <p className="register-sub">See every call this app makes to Meko, live.</p>
      </aside>
    );
  }

  return (
    <aside className="register" aria-label="Meko activity">
      <div className="register-head">
        <h2 className="register-title">Meko register</h2>
        <button type="button" className="link-button" onClick={toggle} aria-expanded="true">Hide</button>
      </div>
      <p className="register-sub">Every call this app makes to Meko, live. Memory text is never shown here.</p>
      {error && <p className="register-empty">{error}</p>}
      {!error && rows.length === 0 && (
        <p className="register-empty">No Meko calls yet. Start a mock with memory on and watch this fill in.</p>
      )}
      <ol className="register-list">
        {rows.map((r, i) => (
          <li key={`${r.at}-${i}`} className={`reg-row${r.ok ? "" : " reg-fail"}${fresh.has(r.at) ? " reg-fresh" : ""}`}>
            <span className="reg-time">{time(r.at)}</span>
            <span className="reg-what">
              <b>{r.tool.replace(/_/g, " ")}</b> {r.ok ? VERBS[r.tool] || "in" : "failed in"} {shortPack(r.datapack)}
            </span>
            <span className="reg-ms">{r.ms} ms</span>
            {!r.ok && r.note && <span className="reg-note">{r.note}</span>}
          </li>
        ))}
      </ol>
    </aside>
  );
}
