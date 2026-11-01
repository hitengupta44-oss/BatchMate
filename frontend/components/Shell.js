"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

const STUDENT_TABS = [
  { href: "/mock", label: "Mock interview" },
  { href: "/memory", label: "My memory" },
  { href: "/share", label: "Share an experience" },
];
const COORD_TABS = [
  { href: "/coordinator", label: "Patterns" },
  { href: "/share", label: "Add an experience" },
];

function StatusChips() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api("/system/status").then((s) => alive && setStatus(s)).catch(() => alive && setStatus({ down: true }));
    load();
    const t = setInterval(load, 60000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (!status) return <div className="chips" aria-hidden="true" />;
  if (status.down) {
    return (
      <div className="chips">
        <span className="chip chip-bad">Server asleep or unreachable</span>
      </div>
    );
  }
  const meko = status.meko;
  const llm = status.llm || {};
  return (
    <div className="chips">
      {status.memory_backend === "meko" ? (
        <span className={`chip ${meko && meko.connected ? "chip-ok" : "chip-bad"}`}
              title={meko && meko.error ? meko.error : undefined}>
          {meko && meko.connected ? `Meko connected, ${meko.datapacks} datapacks` : "Meko not connected"}
        </span>
      ) : (
        <span className="chip chip-warn">Memory: {status.memory_backend} (not Meko)</span>
      )}
      <span className={`chip ${llm.live ? "chip-ok" : "chip-warn"}`}
            title={llm.errors && llm.errors.length ? llm.errors.join("\n") : undefined}>
        {llm.live ? `AI: ${llm.provider}` : "AI offline: using built-in rules"}
      </span>
    </div>
  );
}

export default function Shell({ children }) {
  const { session, signOut } = useSession();
  const path = usePathname();
  const tabs = session && session.role === "coordinator" ? COORD_TABS : STUDENT_TABS;

  return (
    <div className="app">
      <header className="topbar">
        <Link href="/" className="wordmark" aria-label="Batchmate home">
          <span className="wordmark-rule" aria-hidden="true" />
          Batchmate
        </Link>
        <StatusChips />
        {session && (
          <div className="who">
            <span className="who-name">{session.user}</span>
            <span className="who-role">{session.role === "coordinator" ? "Placement coordinator" : "Student"}</span>
            <button className="link-button" onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>
      {session && (
        <nav className="tabs" aria-label="Sections">
          {tabs.map((t) => (
            <Link key={t.href} href={t.href} className="tab" aria-current={path === t.href ? "page" : undefined}>
              {t.label}
            </Link>
          ))}
        </nav>
      )}
      <main className="main">{children}</main>
    </div>
  );
}
