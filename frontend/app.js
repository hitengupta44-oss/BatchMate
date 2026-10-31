"use strict";

const API = (window.BATCHMATE_API || "/api").replace(/\/$/, "");
const $ = (s) => document.querySelector(s);
const state = { user: "priya", sid: null, labels: {} };

// ---------- helpers ----------
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) n.append(k instanceof Node ? k : String(k));
  return n;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), isError ? 6000 : 3000);
}

async function call(method, path, { body, params, user } = {}) {
  const qs = params ? "?" + new URLSearchParams(params) : "";
  let res;
  try {
    res = await fetch(API + path + qs, {
      method,
      headers: { "X-User": user || state.user, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Can't reach the Batchmate server. If it was asleep, wait 30 seconds and try again.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || `Server returned ${res.status}`);
  return data;
}

async function busy(btn, fn) {
  btn.disabled = true;
  try { return await fn(); }
  catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}

const label = (t) => state.labels[t] || String(t).replace(/_/g, " ");
const isCoordinator = () => state.user.startsWith("coordinator");

// ---------- tabs ----------
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", x === b));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "tab-" + b.dataset.tab));
    if (b.dataset.tab === "memory") loadMemory();
    if (b.dataset.tab === "coord") loadCoordinator();
  })
);

$("#user").addEventListener("change", (e) => {
  state.user = e.target.value;
  state.sid = null;
  $("#chat").replaceChildren();
  $("#answer-form").hidden = true;
  $("#plan").replaceChildren();
  $("#recalled").replaceChildren(el("p", { class: "note muted" }, "Start a mock to see what I remember."));
  const active = document.querySelector('.tabs [aria-selected="true"]').dataset.tab;
  if (active === "memory") loadMemory();
  if (active === "coord") loadCoordinator();
});

// ---------- mock interview ----------
function renderPlan(plan) {
  const box = $("#plan");
  box.replaceChildren();
  if (!plan) return;
  box.append(
    el("h3", {}, "Today: " + plan.mock_topics.map(label).join(", ")),
    el("p", { class: "plan-why" }, plan.rationale || "")
  );
}

function renderRecalled(items) {
  const box = $("#recalled");
  box.replaceChildren();
  if (!items || !items.length) {
    box.append(el("p", { class: "note muted" },
      $("#setup").memory.checked ? "Nothing relevant in memory for this question." :
        "Memory is off, so I'm starting from zero."));
    return;
  }
  for (const r of items) {
    const conf = typeof r.confidence === "number" ? r.confidence : null;
    const note = el("div", { class: "note" },
      el("mark", {}, r.text),
      el("small", {}, r.source,
        conf !== null ? el("span", { class: "conf", style: `width:${Math.max(4, conf * 60)}px`,
                                     title: `confidence ${conf.toFixed(2)}` }) : null));
    if (r.personal && r.kind !== "next_plan") {
      note.append(el("button", { class: "quiet", type: "button", onclick: (e) =>
        busy(e.target, async () => {
          await call("DELETE", `/memory/${r.id}`);
          note.remove();
          toast("Forgotten. I won't use that again.");
        }) }, "Forget this"));
    }
    box.append(note);
  }
}

function addQuestion(q) {
  $("#chat").append(el("li", { class: "q" },
    el("span", { class: "tag" }, (q.is_follow_up ? "Follow-up · " : "") + label(q.topic)), q.text));
}

function addFeedback(t) {
  const s = t.eval.scores;
  $("#chat").append(el("li", { class: "fb" },
    el("div", { class: "scores" },
      `Correctness ${s.correctness}/5`, `Clarity ${s.clarity}/5`,
      `Complexity ${s.complexity}/5`, `Communication ${s.communication}/5`),
    t.eval.feedback));
}

function showView(view) {
  if (view.done) {
    $("#chat").append(el("li", { class: "end" }, view.summary));
    $("#answer-form").hidden = true;
  } else if (view.question) {
    addQuestion(view.question);
    $("#answer-form").hidden = false;
    $("#answer").focus();
  }
  renderRecalled(view.recalled);
  $("#chat").lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

$("#setup").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = e.target;
  busy(f.querySelector("button[type=submit]"), async () => {
    $("#chat").replaceChildren(el("li", { class: "thinking" }, "Planning your mock…"));
    const view = await call("POST", "/sessions", { body: {
      company: f.company.value, role: f.role.value,
      days_left: Number(f.days.value) || 5, memory_on: f.memory.checked } });
    state.sid = view.session_id;
    $("#chat").replaceChildren();
    renderPlan(view.plan);
    showView(view);
  });
});

$("#setup").memory.addEventListener("change", (e) => {
  e.target.parentElement.querySelector(".switch-label").textContent = e.target.checked ? "Memory on" : "Memory off";
});

$("#answer-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#answer").value.trim();
  if (!text || !state.sid) return;
  busy(e.target.querySelector("button"), async () => {
    $("#chat").append(el("li", { class: "a" }, text));
    $("#answer").value = "";
    const thinking = el("li", { class: "thinking" }, "Evaluating…");
    $("#chat").append(thinking);
    const view = await call("POST", `/sessions/${state.sid}/answer`, { body: { text } });
    thinking.remove();
    addFeedback(view.transcript[view.transcript.length - 1]);
    showView(view);
  });
});

$("#answer").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#answer-form").requestSubmit();
});

// ---------- my memory ----------
async function loadMemory() {
  const list = $("#memories");
  if (isCoordinator()) {
    list.replaceChildren(el("li", { class: "empty" }, "Coordinators don't have personal memory. Pick a student above."));
    return;
  }
  try {
    const [mems, opt] = await Promise.all([call("GET", "/memory"), call("GET", "/me/opt-in")]);
    $("#optin").checked = opt.share_aggregate;
    const shown = mems.filter((m) => !["profile"].includes(m.kind));
    list.replaceChildren();
    if (!shown.length) {
      list.append(el("li", { class: "empty" }, "Nothing yet. Finish a mock with memory on and I'll start remembering."));
      return;
    }
    const names = { weakness: "Weak spot", strength: "Strength", session: "Session summary",
                    next_plan: "Next session", };
    for (const m of shown) {
      const actions = el("div", { class: "actions" });
      if (m.kind === "weakness" && m.status === "active") {
        actions.append(el("button", { class: "quiet", type: "button", onclick: (e) => busy(e.target, async () => {
          await call("POST", `/memory/${m.id}/fixed`);
          toast("Marked as fixed. I'll stop bringing it up.");
          loadMemory();
        }) }, "I've fixed this"));
      }
      actions.append(el("button", { class: "danger", type: "button", onclick: (e) => busy(e.target, async () => {
        await call("DELETE", `/memory/${m.id}`);
        toast("Forgotten.");
        loadMemory();
      }) }, "Forget"));
      list.append(el("li", {},
        el("div", {},
          el("span", { class: "kind " + m.kind }, names[m.kind] || m.kind),
          el("p", { class: "text" }, m.text),
          el("span", { class: "meta" },
            (m.status !== "active" ? m.status + ", " : "") + "updated " + m.updated_at.slice(0, 10))),
        actions));
    }
  } catch (e) {
    list.replaceChildren(el("li", { class: "empty" }, e.message));
  }
}

$("#optin").addEventListener("change", async (e) => {
  try {
    await call("POST", "/me/opt-in", { body: { share_aggregate: e.target.checked } });
    toast(e.target.checked ? "Your weak topics now count toward batch tips, anonymously." : "Stopped sharing.");
  } catch (err) {
    e.target.checked = !e.target.checked;
    toast(err.message, true);
  }
});

// ---------- share ----------
$("#share-form").date.value = new Date().toISOString().slice(0, 10);
$("#share-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = e.target;
  busy(f.querySelector("button"), async () => {
    const rows = await call("POST", "/experiences", { body: {
      text: f.text.value, company: f.company.value, role: f.role.value, interview_date: f.date.value } });
    const out = $("#share-out");
    if (!rows.length) {
      out.replaceChildren(el("p", { class: "muted" },
        "Nothing new was added: either this was already shared, or no interview topics were found. Mention rounds and topics, like \"Round 2: LRU cache\"."));
      return;
    }
    out.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, el("th", {}, "Round"), el("th", {}, "Topic"), el("th", {}, "Outcome"))),
      el("tbody", {}, rows.map((m) => el("tr", {},
        el("td", {}, m.meta.round), el("td", {}, label(m.meta.topic)), el("td", {}, m.meta.outcome))))));
    f.text.value = "";
    toast(`Added ${rows.length} topic${rows.length > 1 ? "s" : ""}. Thanks for helping your juniors.`);
  });
});

// ---------- coordinator ----------
const coordUser = () => (isCoordinator() ? state.user : "coordinator-demo");

async function loadCoordinator() {
  const list = $("#pending");
  if (!isCoordinator()) {
    list.replaceChildren(el("li", { class: "empty" }, "Switch \"You are\" to Placement coordinator to approve patterns."));
    $("#steward").textContent = "";
    return;
  }
  try {
    const [rows, st] = await Promise.all([
      call("GET", "/patterns/pending", { params: { company: $("#c-company").value } }),
      call("GET", "/steward"),
    ]);
    renderSteward(st);
    list.replaceChildren();
    if (!rows.length) {
      list.append(el("li", { class: "empty" }, "Nothing waiting. New patterns appear here once 3 seniors report the same topic."));
      return;
    }
    for (const p of rows) {
      const decide = (d) => (e) => busy(e.target, async () => {
        await call("POST", `/patterns/${p.id}/${d}`, { user: coordUser() });
        toast(d === "approve" ? "Approved. Students will see this pattern." : "Rejected.");
        loadCoordinator();
      });
      list.append(el("li", {},
        el("div", {},
          el("span", { class: "kind" }, `${p.source_count} reports`),
          el("p", { class: "text" }, p.text)),
        el("div", { class: "actions" },
          el("button", { class: "primary", type: "button", onclick: decide("approve") }, "Approve"),
          el("button", { class: "quiet", type: "button", onclick: decide("reject") }, "Reject"))));
    }
  } catch (e) {
    list.replaceChildren(el("li", { class: "empty" }, e.message));
  }
}

function renderSteward(st) {
  if (!st || !st.ran_at) {
    $("#steward").textContent = "The Steward hasn't run yet.";
    return;
  }
  const bits = [`Steward last ran ${st.ran_at.slice(0, 16).replace("T", " ")} UTC`,
    `${st.new_proposals} new proposals`, `${(st.retired || []).length} stale patterns retired`,
    `${(st.batch_lessons || []).length} batch tips published`];
  $("#steward").textContent = bits.join(", ") + ".";
}

$("#steward-run").addEventListener("click", (e) => {
  if (!isCoordinator()) return toast("Switch to Placement coordinator first.", true);
  busy(e.target, async () => {
    renderSteward(await call("POST", "/steward/run"));
    await loadCoordinator();
    toast("Steward finished.");
  });
});
$("#c-company").addEventListener("change", loadCoordinator);

// ---------- boot ----------
call("GET", "/topics").then((t) => (state.labels = t)).catch(() => {});
