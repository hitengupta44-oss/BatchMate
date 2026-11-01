"use client";

const KEY = "bm_session";

export function loadSession() {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try {
    if (session) window.localStorage.setItem(KEY, JSON.stringify(session));
    else window.localStorage.removeItem(KEY);
  } catch {
    /* private mode: the session simply won't survive a reload */
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body, params, token } = {}) {
  const session = token ? { token } : loadSession();
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const headers = { "Content-Type": "application/json" };
  if (session && session.token) headers.Authorization = `Bearer ${session.token}`;
  let res;
  try {
    res = await fetch(`/api${path}${qs}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Can't reach the Batchmate server. If it was asleep, wait 30 seconds and try again.", 0);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    throw new ApiError(detail || `Server returned ${res.status}`, res.status);
  }
  return data;
}
