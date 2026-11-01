// Sahyog Care Companion: patient web page. Plain JS, no build step; talks only to this API.
// Identity always comes from the bearer token; the page never sends a patient id of its own
// except as the subject of a records question, which the server checks against consent.
"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { token: null, me: null, thread: null, awaiting: null, received: [] };
const IST = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
});
const DATE = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });

/** Build an element: h("p", {class: "x"}, "text", child, ...). Text is always set as text, never HTML. */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 5000);
}

class ApiError extends Error { constructor(status, detail) { super(detail); this.status = status; } }

async function api(method, path, body, isForm = false) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : res.statusText;
    if (res.status === 429) throw new ApiError(429, `Too many requests. Wait ${res.headers.get("Retry-After") || "a few"} seconds and try again.`);
    if (res.status === 401) throw new ApiError(401, "Your session has expired. Pick a person again to sign back in.");
    throw new ApiError(res.status, detail);
  }
  return data;
}

async function busy(btn, fn) {
  btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message || "Something went wrong. Try again."); } finally { btn.disabled = false; }
}

/* ---------- sign-in (demo personas) ---------- */
async function signIn(pid) {
  try {
    const r = await api("POST", "/demo/token", { patient_id: pid });
    state.token = r.token;
  } catch (e) {
    if (e.status === 404) { $("#token-form").hidden = false; $("#persona-box").hidden = true; return; }
    toast(e.message); return;
  }
  await afterSignIn();
}

async function afterSignIn() {
  state.me = await api("GET", "/v1/me");
  $("#me-name").textContent = state.me.name || state.me.sub;
  $("#me-id").textContent = state.me.patient_id || "—";
  resetChat();
  $("#answers").replaceChildren();
  await Promise.all([loadConsents(), loadDocs()]);
  renderExamples();
}

/* ---------- tabs ---------- */
const tabs = ["doctor", "records", "data"];
function selectTab(name, focus = false) {
  for (const t of tabs) {
    const on = t === name;
    const tab = $(`#tab-${t}`);
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    $(`#panel-${t}`).hidden = !on;
    if (on && focus) tab.focus();
  }
  if (name === "data") { loadDocs(); loadConsents(); }
}
for (const t of tabs) $(`#tab-${t}`).addEventListener("click", () => selectTab(t));
$(".tabs").addEventListener("keydown", (e) => {
  const i = tabs.findIndex((t) => $(`#tab-${t}`).getAttribute("aria-selected") === "true");
  if (e.key === "ArrowRight") selectTab(tabs[(i + 1) % tabs.length], true);
  if (e.key === "ArrowLeft") selectTab(tabs[(i + tabs.length - 1) % tabs.length], true);
});

/* ---------- W1 Find my doctor ---------- */
const chat = $("#chat");
function say(who, ...content) {
  const li = who === "me"
    ? h("li", { class: "msg msg--me" }, ...content)
    : h("li", { class: "msg msg--bot" }, h("span", { class: "msg__who" }, "Sahyog"), ...content);
  chat.append(li);
  li.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  return li;
}
function resetChat() {
  state.thread = null; state.awaiting = null;
  chat.replaceChildren();
  say("bot", h("div", { class: "msg__bubble" }, "Tell me what is bothering you. I will suggest the right kind of doctor and show the next free appointments."));
}

function renderW1(r) {
  state.awaiting = r.status === "needs_input" ? r.prompt.type : null;
  if (r.status === "needs_input" && r.prompt.type === "clarify") {
    say("bot", h("div", { class: "msg__bubble" }, r.prompt.question));
    $("#w1-input").placeholder = "Answer the question above";
    return;
  }
  if (r.status === "needs_input" && r.prompt.type === "choose_slot") {
    const cards = r.prompt.options.map((o) => h("div", { class: "slot" },
      h("p", { class: "slot__doc" }, o.doctor_name),
      h("p", { class: "slot__meta" }, `${o.specialty} · ${o.clinic_name}, ${o.city}`),
      h("p", { class: "slot__time" }, IST.format(new Date(o.starts_at))),
      h("p", { class: "slot__meta" }, `Speaks ${o.languages.map(langName).join(", ")}`),
      h("button", { class: "btn btn--primary", type: "button", onclick: (e) => book(e.currentTarget, o) }, "Book this slot")));
    say("bot", h("div", { class: "msg__bubble" }, `A ${r.prompt.specialty} doctor is the right fit. These are the earliest free slots:`),
      h("div", { class: "slots" }, cards));
    return;
  }
  // finished
  if (r.route === "emergency_desk") {
    say("bot", h("div", { class: "alert alert--danger", role: "alert" },
      h("strong", {}, "This needs urgent care"), h("p", {}, r.reply),
      r.ticket_id ? h("p", { class: "mono" }, `Emergency desk ticket ${r.ticket_id}`) : null));
  } else if (r.route === "booked") {
    say("bot", slip(r));
  } else {
    say("bot", h("div", { class: "alert alert--warn" }, h("p", {}, r.reply),
      r.ticket_id ? h("p", { class: "mono" }, `Front desk ticket ${r.ticket_id}`) : null));
  }
  state.thread = null;
  $("#w1-input").placeholder = "Describe another problem, or press Start over";
}

function slip(r) {
  const chosen = state.lastSlot || {};
  return h("div", { class: "slip", role: "group", "aria-label": "Appointment booked" },
    h("div", { class: "slip__stub" }, h("small", {}, "Token"), h("span", { class: "slip__no" }, r.appointment_id)),
    h("div", { class: "slip__body" },
      h("p", { class: "slip__title" }, "Appointment booked"),
      h("p", {}, chosen.doctor_name ? `${chosen.doctor_name}, ${chosen.specialty}` : r.reply),
      chosen.clinic_name ? h("p", {}, `${chosen.clinic_name}, ${chosen.city}`) : null,
      chosen.starts_at ? h("p", { class: "slot__time" }, IST.format(new Date(chosen.starts_at))) : null,
      h("p", { class: "slot__meta" }, "An SMS confirmation has been queued.")));
}

function langName(code) {
  return { en: "English", hi: "Hindi", mr: "Marathi", te: "Telugu", ta: "Tamil", kn: "Kannada", gu: "Gujarati", ur: "Urdu" }[code] || code;
}

async function book(btn, option) {
  await busy(btn, async () => {
    state.lastSlot = option;
    const key = (crypto.randomUUID && crypto.randomUUID()) || `k-${Date.now()}-${Math.random()}`;
    const r = await api("POST", `/v1/w1/sessions/${state.thread}/reply`, { slot_id: option.slot_id, idempotency_key: key });
    btn.closest(".slots").querySelectorAll("button").forEach((b) => { b.disabled = true; });
    if (r.route === "booked") btn.textContent = "Booked";
    renderW1(r);
  });
}

$("#w1-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#w1-input").value.trim();
  if (!text) return;
  await busy($("#w1-send"), async () => {
    say("me", text);
    $("#w1-input").value = "";
    const typing = say("bot", h("p", { class: "typing" }, "Checking…"));
    try {
      // a typed message answers a clarifying question; otherwise it starts a new conversation
      const r = state.thread && state.awaiting === "clarify"
        ? await api("POST", `/v1/w1/sessions/${state.thread}/reply`, { answer: text })
        : await api("POST", "/v1/w1/sessions", { message: text });
      if (r.status === "needs_input") state.thread = r.thread_id;
      renderW1(r);
    } finally { typing.remove(); }
  });
});
$("#w1-reset").addEventListener("click", resetChat);
$("#w1-examples").addEventListener("click", (e) => {
  const b = e.target.closest(".chip");
  if (b) { $("#w1-input").value = b.dataset.text; $("#w1-input").focus(); }
});

/* ---------- W2 My records ---------- */
const ROUTE = {
  answer: ["Answered from reports on file", "pill--ok"],
  not_in_record: ["Not in the reports on file", "pill--muted"],
  handoff_doctor: ["For your doctor", "pill--warn"],
  refuse: ["Cannot share", "pill--danger"],
  unavailable: ["Try again shortly", "pill--muted"],
};
const EXAMPLES = {
  "P-PRIYA": ["What did the neck ultrasound recommend next?", "What did my mother's echocardiogram show?", "Can I stop my seizure medicine?"],
  "P-SUNITA": ["What was my creatinine?", "What did my chest CT show?", "Show me my daughter Priya's reports"],
  "P00637": ["Summarise my latest report.", "What else does my uploaded report tell you to do?", "List all patients who have pneumonia."],
};
function renderExamples() {
  const box = $("#w2-examples");
  box.replaceChildren(...(EXAMPLES[state.me?.patient_id] || []).map((q) =>
    h("button", { type: "button", class: "chip", onclick: () => {
      $("#w2-input").value = q;
      if (/mother/i.test(q) && state.received.length) $("#w2-subject").value = state.received[0].patient_id;
      $("#w2-input").focus();
    } }, q)));
}

$("#w2-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#w2-input").value.trim();
  if (!q) return;
  const subject = $("#w2-subject").value;
  const whoText = $("#w2-subject").selectedOptions[0]?.textContent || "";
  await busy($("#w2-send"), async () => {
    const body = { question: q };
    if (subject && subject !== state.me.patient_id) body.subject_patient_id = subject;
    const r = await api("POST", "/v1/w2/questions", body);
    const [label, cls] = ROUTE[r.route] || [r.route, "pill--muted"];
    const item = h("li", { class: "answer" },
      h("div", { class: "answer__head" }, h("p", { class: "answer__q" }, q), h("span", { class: `pill ${cls}` }, label)),
      h("p", { class: "answer__who" }, `About: ${whoText}`),
      h("p", { class: "answer__text" }, r.reply),
      r.citations?.length ? h("div", { class: "cites", "aria-label": "Sources" },
        r.citations.map((c) => h("span", { class: "cite" }, `${c.report_id} · page ${c.page}`))) : null);
    $("#answers").prepend(item);
    $("#w2-input").value = "";
  });
});

$("#upload-file").addEventListener("change", (e) => {
  $("#upload-name").textContent = e.target.files[0]?.name || "No file chosen";
});
$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("#upload-file").files[0];
  if (!file) return;
  const status = $("#upload-status");
  await busy($("#upload-send"), async () => {
    const fd = new FormData();
    fd.append("file", file, file.name);
    status.textContent = "Uploading…";
    const r = await api("POST", "/v1/w2/uploads", fd, true);
    status.textContent = "Queued. Reading the report…";
    for (let i = 0; i < 40; i++) {
      await new Promise((res) => setTimeout(res, 1500));
      const s = await api("GET", r.status_url);
      if (s.status === "done") { status.textContent = "Added. You can ask about it now."; loadDocs(); return; }
      if (s.status === "failed") { status.textContent = `Could not add this report: ${s.error}`; return; }
      status.textContent = s.status === "running" ? "Reading the report and masking names and numbers…" : "Queued. Reading the report…";
    }
    status.textContent = "Still working. Check My data in a minute.";
  });
});

/* ---------- My data ---------- */
async function loadDocs() {
  if (!state.token) return;
  const body = $("#docs-body");
  let docs;
  try { docs = await api("GET", "/v1/w2/documents"); } catch (e) { toast(e.message); return; }
  if (!docs.length) { body.replaceChildren(h("tr", {}, h("td", { colspan: 5, class: "empty" }, "No reports on file yet."))); return; }
  body.replaceChildren(...docs.slice().reverse().map((d) => h("tr", {},
    h("td", { class: "mono" }, d.report_id || "—"),
    h("td", {}, d.title || "—"),
    h("td", {}, d.report_date ? DATE.format(new Date(d.report_date)) : "—"),
    h("td", {}, h("span", { class: `pill ${d.erasable ? "pill--warn" : "pill--muted"}` }, d.erasable ? "Your upload" : "Hospital report")),
    h("td", {}, d.erasable ? confirmButton("Erase", "Erase this report and everything made from it?", async () => {
      const r = await api("DELETE", `/v1/w2/documents/${d.doc_id}`);
      toast(`Erased ${d.report_id}: file and ${r.chunks_removed} searchable sections removed.`);
      loadDocs();
    }) : h("span", { class: "slot__meta" }, "Kept as medical record")))));
}

async function loadConsents() {
  if (!state.token) return;
  let c;
  try { c = await api("GET", "/v1/w2/consents"); } catch (e) { toast(e.message); return; }
  const valid = (x) => x.state === "valid";
  // one row per person: the most recent grant decides what is shown
  const latest = (rows, key) => Object.values(rows.reduce((m, r) => ({ ...m, [r[key]]: r }), {}));
  c.given = latest(c.given, "grantee_id");
  c.received = latest(c.received, "patient_id");
  state.received = c.received.filter(valid);
  // records dropdown: myself plus anyone who gave me valid consent
  const sel = $("#w2-subject");
  sel.replaceChildren(h("option", { value: state.me.patient_id }, `Myself (${state.me.name || state.me.patient_id})`),
    ...state.received.map((r) => h("option", { value: r.patient_id }, `${r.patient_name} (consent until ${DATE.format(new Date(r.expires_at))})`)));
  $("#me-access").textContent = state.received.length ? state.received.map((r) => r.patient_name).join(", ") : "Only their own";

  const pill = (s) => h("span", { class: `pill ${{ valid: "pill--ok", expired: "pill--muted", revoked: "pill--danger" }[s] || "pill--muted"}` },
    { valid: "Active", expired: "Expired", revoked: "Withdrawn" }[s] || s);
  const given = c.given.filter(valid);
  $("#given").replaceChildren(...(given.length ? given.map((g) => h("li", { class: "consent" },
    h("div", { class: "consent__who" }, h("b", {}, g.grantee_name), h("small", {}, `${g.purpose} · until ${DATE.format(new Date(g.expires_at))}`)),
    pill(g.state),
    confirmButton("Withdraw", `Stop ${g.grantee_name} reading your records?`, async () => {
      await api("DELETE", `/v1/w2/consents/${g.grantee_id}`);
      toast(`${g.grantee_name} can no longer read your records.`);
      loadConsents();
    }))) : [h("li", { class: "empty" }, "Nobody else can read your records.")]));
  $("#received").replaceChildren(...(c.received.length ? c.received.map((r) => h("li", { class: "consent" },
    h("div", { class: "consent__who" }, h("b", {}, r.patient_name), h("small", {}, `${r.purpose} · until ${DATE.format(new Date(r.expires_at))}`)),
    pill(r.state))) : [h("li", { class: "empty" }, "No one has shared their records with you.")]));
}

/** A destructive action with its confirmation step inside the page (no browser dialogs). */
function confirmButton(label, question, action) {
  const wrap = h("span", { class: "confirm" });
  const start = h("button", { type: "button", class: "btn btn--danger" }, label);
  start.addEventListener("click", () => {
    const yes = h("button", { type: "button", class: "btn btn--danger" }, `Yes, ${label.toLowerCase()}`);
    const no = h("button", { type: "button", class: "btn btn--quiet" }, "Cancel");
    yes.addEventListener("click", () => busy(yes, action));
    no.addEventListener("click", () => wrap.replaceChildren(start));
    wrap.replaceChildren(h("span", {}, question), yes, no);
    no.focus();
  });
  wrap.append(start);
  return wrap;
}

$("#grant-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const who = $("#grant-who").value.trim();
  await busy(e.submitter || $("#grant-form button"), async () => {
    await api("POST", "/v1/w2/consents", { grantee_id: who, days: Number($("#grant-days").value) });
    toast(`Access given to ${who}.`);
    $("#grant-who").value = "";
    loadConsents();
  });
});

/* ---------- boot ---------- */
document.querySelectorAll('input[name="persona"]').forEach((r) =>
  r.addEventListener("change", () => { if (r.checked) signIn(r.value); }));
$("#token-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  state.token = $("#token-input").value.trim().replace(/^Bearer\s+/i, "");
  try { await afterSignIn(); } catch (err) { toast(err.message); }
});
signIn(document.querySelector('input[name="persona"]:checked').value);
