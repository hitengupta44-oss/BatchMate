"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, loadSession, saveSession } from "./api";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);
  const [labels, setLabels] = useState({});
  const [toast, setToast] = useState(null);
  const router = useRouter();

  useEffect(() => {
    setSession(loadSession());
    setReady(true);
    api("/topics").then(setLabels).catch(() => {});
  }, []);

  const signIn = useCallback(async (user, password) => {
    const data = await api("/auth/login", { method: "POST", body: { user, password } });
    const next = { token: data.token, user: data.user, role: data.role };
    saveSession(next);
    setSession(next);
    return next;
  }, []);

  const signOut = useCallback(() => {
    saveSession(null);
    setSession(null);
    router.push("/login");
  }, [router]);

  const notify = useCallback((message, isError = false) => {
    setToast({ message, isError, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), toast.isError ? 6000 : 3200);
    return () => clearTimeout(t);
  }, [toast]);

  const label = useCallback((tag) => labels[tag] || String(tag || "").replace(/_/g, " "), [labels]);

  const value = useMemo(
    () => ({ session, ready, signIn, signOut, notify, label }),
    [session, ready, signIn, signOut, notify, label]
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
      {toast && (
        <div className={`toast${toast.isError ? " toast-error" : ""}`} role="status" key={toast.id}>
          {toast.message}
        </div>
      )}
    </SessionContext.Provider>
  );
}

export function useSession() {
  return useContext(SessionContext);
}

/** Redirects to /login when signed out; signs out on an expired token. */
export function useRequireSession(role) {
  const ctx = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!ctx.ready) return;
    if (!ctx.session) router.replace("/login");
    else if (role && ctx.session.role !== role) router.replace(ctx.session.role === "coordinator" ? "/coordinator" : "/mock");
  }, [ctx.ready, ctx.session, role, router]);
  return ctx;
}

/** Wrap an API call: shows errors as toasts and signs out on 401. */
export function useApiAction() {
  const { notify, signOut } = useSession();
  return useCallback(
    async (fn) => {
      try {
        return await fn();
      } catch (e) {
        if (e.status === 401) {
          notify("Your session ended. Sign in again.", true);
          signOut();
        } else {
          notify(e.message, true);
        }
        return undefined;
      }
    },
    [notify, signOut]
  );
}
