"use strict";
/* NetDash – frontend dashboardu (bez závislostí) */

const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
};
const svg = (paths) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.innerHTML = paths;
  return s;
};

const ICONS = {
  router: '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 16.5h.01M11 16.5h.01M17 13V9M8.5 7.5a5 5 0 0 1 7 0M6 5a8.5 8.5 0 0 1 12 0"/>',
  smart: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>',
  media: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  computer: '<rect x="4" y="4" width="16" height="11" rx="2"/><path d="M2 19h20"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
  printer: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><rect x="7" y="14" width="10" height="7" rx="1"/>',
  camera: '<path d="M15 10l5-3v10l-5-3z"/><rect x="3" y="6" width="12" height="12" rx="2"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  unknown: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  web: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  power: '<path d="M12 3v8M6.3 7.3a8 8 0 1 0 11.4 0"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  up: '<path d="M6 15l6-6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  play: '<path d="M7 4l13 8-13 8z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
  next: '<path d="M5 5l10 7-10 7zM19 5v14"/>', prev: '<path d="M19 5L9 12l10 7zM5 5v14"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  home: '<path d="M3 11l9-8 9 8M5 10v10h14V10"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>',
};
const CATS = [
  ["all", "Všetko"], ["controllable", "Ovládateľné"], ["smart", "Smart domácnosť"], ["media", "TV a audio"],
  ["computer", "Počítače"], ["phone", "Mobily"], ["router", "Sieť"], ["server", "Servery a NAS"],
  ["printer", "Tlačiarne"], ["camera", "Kamery"], ["unknown", "Neznáme"], ["offline", "Offline"],
];
const CAT_LABEL = Object.fromEntries(CATS);

const S = {
  devices: [], meta: {}, scan: {}, demo: false,
  filter: localGet("filter") || "all", q: "",
  controls: {}, loading: {}, lastAction: {}, expanded: new Set(),
};
const cards = new Map();

function localGet(k) { try { return localStorage.getItem("netdash." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("netdash." + k, v); } catch { /* ignore */ } }

/* ------------------------------------------------------------------ API */
async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-NetDash": "1" },
  };
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch { /* ignore */ }
  if (r.status === 401) { showLogin(); throw new Error("Vyžaduje sa PIN"); }
  if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
  return data;
}

function toast(msg, err = false) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 6000 : 3000);
}

/* ------------------------------------------------------------------ stav */
let stateTimer = null;
async function loadState() {
  clearTimeout(stateTimer);
  try {
    const d = await api("/api/state");
    const wasRunning = S.scan.running;
    Object.assign(S, { devices: d.devices, meta: d.meta || {}, scan: d.scan || {}, demo: d.demo });
    $("#login").hidden = true;
    render();
    if (wasRunning && !S.scan.running) {
      if (S.scan.error) toast("Sken zlyhal: " + S.scan.error, true);
      else toast(`Sken dokončený – nájdených ${S.devices.filter(x => x.online).length} zariadení`);
      for (const dev of S.devices) if (dev.controllable && dev.online) loadControls(dev, true);
    }
  } catch (e) {
    if (!$("#login").hidden) return;
    toast("Server nedostupný: " + e.message, true);
  }
  stateTimer = setTimeout(loadState, S.scan.running ? 700 : 30000);
}

async function startScan() {
  try {
    await api("/api/scan", {});
    S.scan.running = true;
    renderScan();
    setTimeout(loadState, 300);
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------------ render */
function render() {
  renderScan();
  renderMeta();
  renderStats();
  renderChips();
  renderGrids();
}

function renderScan() {
  const sc = S.scan, btn = $("#scanBtn");
  btn.disabled = !!sc.running;
  btn.classList.toggle("spin", !!sc.running);
  btn.querySelector("span").textContent = sc.running ? "Skenujem…" : "Skenovať";
  $("#progress").hidden = !sc.running;
  const st = $("#scanStatus");
  st.hidden = !sc.running;
  if (sc.running) {
    const pct = sc.total ? Math.round((sc.done / sc.total) * 100) : 5;
    $("#progressBar").style.width = pct + "%";
    st.textContent = `${sc.phase || "Skenujem"}${sc.total ? ` – ${pct} %` : ""}`;
  }
  $("#demoBanner").hidden = !S.demo;
}

function ago(ts) {
  if (!ts) return "nikdy";
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 60) return "práve teraz";
  if (s < 3600) return `pred ${Math.round(s / 60)} min`;
  if (s < 86400) return `pred ${Math.round(s / 3600)} h`;
  return new Date(ts * 1000).toLocaleString("sk-SK");
}

function renderMeta() {
  const m = S.meta;
  $("#meta").textContent = m.network
    ? `Sieť ${m.network} · brána ${m.gateway || "?"} · sken ${ago(m.scanned_at)}`
    : "Sieť ešte nebola preskenovaná";
}

function renderStats() {
  const on = S.devices.filter(d => d.online);
  const items = [
    [on.length, "Online"],
    [on.filter(d => d.controllable).length, "Ovládateľné"],
    [S.devices.length - on.length, "Offline"],
    [S.devices.filter(d => d.new).length, "Nové od minulého skenu"],
  ];
  $("#stats").replaceChildren(...items.map(([v, l]) => h("div", { class: "stat" }, h("div", { class: "v" }, String(v)), h("div", { class: "l" }, l))));
}

function matchesCat(d, f) {
  if (f === "all") return true;
  if (f === "offline") return !d.online;
  if (f === "controllable") return d.controllable;
  return d.category === f;
}

function renderChips() {
  const chips = CATS.map(([k, label]) => {
    const n = S.devices.filter(d => matchesCat(d, k)).length;
    if (!n && !["all", "controllable"].includes(k) && S.filter !== k) return null;
    return h("button", {
      class: "chip", role: "tab", "aria-selected": String(S.filter === k),
      onclick: () => { S.filter = k; localSet("filter", k); renderChips(); renderGrids(); },
    }, label, h("span", { class: "n" }, String(n)));
  });
  $("#chips").replaceChildren(...chips.filter(Boolean));
}

function matchesQuery(d) {
  if (!S.q) return true;
  const hay = [d.display_name, d.name, d.ip, d.mac, d.vendor, d.model, d.hostname, CAT_LABEL[d.category],
    ...(d.drivers || []).map(x => x.label)].join(" ").toLowerCase();
  return S.q.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}

function renderGrids() {
  const list = S.devices.filter(d => matchesCat(d, S.filter) && matchesQuery(d));
  const canWake = d => (d.drivers || []).some(x => x.key === "lgwebos" || x.key === "samsung");
  const ctrl = list.filter(d => d.controllable && (d.online || canWake(d)))
    .sort((a, b) => (a.category === "server") - (b.category === "server") || a.display_name.localeCompare(b.display_name, "sk"));
  const order = { router: 0, computer: 1, server: 2, smart: 3, media: 4, printer: 5, camera: 6, phone: 7, unknown: 8 };
  const all = [...list].sort((a, b) => (b.online - a.online) || (order[a.category] - order[b.category]) ||
    ipNum(a.ip) - ipNum(b.ip));

  place($("#ctrlGrid"), ctrl.map(d => ctrlCard(d)));
  place($("#devGrid"), all.map(d => devCard(d)));
  $("#ctrlSection").hidden = !ctrl.length;
  $("#allSection").hidden = !all.length;
  $("#ctrlCount").textContent = `· ${ctrl.length}`;
  $("#allCount").textContent = `· ${all.length}`;
  const empty = $("#empty");
  empty.hidden = !!list.length;
  if (!list.length) {
    empty.textContent = S.devices.length ? "Nič nevyhovuje filtru." :
      (S.scan.running ? "Hľadám zariadenia…" : "Zatiaľ žiadne zariadenia. Klikni na Skenovať.");
  }
}

function place(container, els) {
  els.forEach((el, i) => { if (container.children[i] !== el) container.insertBefore(el, container.children[i] || null); });
  while (container.children.length > els.length) container.lastChild.remove();
}

const ipNum = ip => ip.split(".").reduce((a, b) => a * 256 + +b, 0);

/* ------------------------------------------------------------------ karty */
function subtitle(d) {
  const parts = [d.ip];
  const vm = [d.vendor, d.model].filter(Boolean);
  if (vm.length && !(d.model || "").includes(d.vendor || "\0")) parts.push(vm.join(" "));
  else if (d.model) parts.push(d.model);
  return parts.join(" · ");
}

function headEl(d) {
  const name = h("span", { class: "txt", title: "Premenovať" }, d.display_name);
  const wrap = h("div", { class: "dev-name" }, h("span", { class: "dot", title: d.online ? "Online" : "Offline" }), name);
  const startEdit = () => {
    const inp = h("input", { value: d.display_name, maxlength: "60", "aria-label": "Názov zariadenia" });
    let done = false;
    const finish = async (save) => {
      if (done) return; done = true;
      const v = inp.value.trim();
      if (save && v !== d.display_name) {
        try {
          await api(`/api/devices/${encodeURIComponent(d.id)}/alias`, { name: v === d.name ? "" : v });
          await loadState();
          return;
        } catch (e) { toast(e.message, true); }
      }
      inp.replaceWith(name);
    };
    inp.addEventListener("keydown", e => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
    inp.addEventListener("blur", () => finish(true));
    name.replaceWith(inp);
    inp.focus(); inp.select();
  };
  name.addEventListener("dblclick", startEdit);
  wrap.append(h("button", { class: "edit", title: "Premenovať", "aria-label": "Premenovať", onclick: startEdit }, svg(ICONS.edit)));
  if (d.new) wrap.append(h("span", { class: "badge new" }, "nové"));
  if (d.is_self) wrap.append(h("span", { class: "badge" }, "tento PC"));
  return h("div", { class: "card-head" },
    h("div", { class: "dev-ico c-" + d.category, title: CAT_LABEL[d.category] }, svg(ICONS[d.category] || ICONS.unknown)),
    h("div", { class: "dev-title" }, wrap,
      h("div", { class: "dev-sub" }, subtitle(d)),
      d.controllable ? h("div", { class: "dev-sub" }, (d.drivers || []).map(x => x.label).join(" + ")) : null));
}

function footEl(d, withDetails) {
  const foot = h("div", { class: "card-foot" });
  for (const l of d.links || []) foot.append(h("a", { class: "link-btn", href: l.url, target: "_blank", rel: "noopener" }, svg(ICONS.web), l.label));
  if (d.mac && !d.is_self) {
    foot.append(h("button", {
      class: "link-btn", title: "Wake-on-LAN – zobudí počítač, ktorý to podporuje",
      onclick: async () => {
        try { await api(`/api/devices/${encodeURIComponent(d.id)}/wol`, {}); toast(`Magický paket odoslaný na ${d.mac}`); }
        catch (e) { toast(e.message, true); }
      },
    }, svg(ICONS.power), "Zobudiť"));
  }
  if (withDetails) {
    foot.append(h("button", {
      class: "link-btn", onclick: () => {
        S.expanded.has(d.id) ? S.expanded.delete(d.id) : S.expanded.add(d.id);
        refreshCard(d, true);
      },
    }, svg(ICONS.info), S.expanded.has(d.id) ? "Menej" : "Detaily"));
  }
  return foot.children.length ? foot : null;
}

function detailsEl(d) {
  const rows = [
    ["IP", d.ip], ["MAC", d.mac ? d.mac + (d.random_mac ? " (náhodná/súkromná)" : "") : "—"],
    ["Typ", CAT_LABEL[d.category]], ["Výrobca", d.vendor], ["Model", d.model], ["Hostname", d.hostname],
    ["Služby", (d.mdns_services || []).map(s => s.replace(/^_|\._(tcp|udp)$/g, "")).join(", ")],
    ["Videné", d.online ? "teraz" : ago(d.last_seen)], ["Prvýkrát", ago(d.first_seen)],
  ].filter(([, v]) => v);
  return h("dl", { class: "details" }, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
}

function portsEl(d) {
  if (!d.ports || !d.ports.length) return null;
  return h("div", { class: "ports" }, d.ports.map(p => h("span", { class: "port", title: "Port " + p.port }, `${p.service}${String(p.service) === String(p.port) ? "" : " :" + p.port}`)));
}

function sig(d) { return JSON.stringify([d.display_name, d.online, d.ip, d.vendor, d.model, d.category, d.new, d.links, d.ports, S.expanded.has(d.id)]); }

function devCard(d) {
  const key = "d:" + d.id;
  let c = cards.get(key);
  const s = sig(d);
  if (c && c.sig === s) return c.el;
  const el = h("article", { class: "card" + (d.online ? "" : " offline") },
    headEl(d), portsEl(d), S.expanded.has(d.id) ? detailsEl(d) : null, footEl(d, true));
  if (c) c.el.replaceWith(el);
  cards.set(key, { el, sig: s });
  return el;
}

function ctrlCard(d) {
  const key = "c:" + d.id;
  let c = cards.get(key);
  const s = sig(d);
  if (c && c.sig === s) return c.el;
  const body = c ? c.body : h("div", { class: "card-body" }, h("div", { class: "loading-ctrl" }, "Načítavam stav…"));
  const isWide = (d.drivers || []).some(x => x.key === "homeassistant" || x.key === "hue");
  const el = h("article", { class: "card ctrl-card" + (isWide ? " wide" : ""), "data-id": d.id }, headEl(d), body, footEl(d, false));
  if (c) c.el.replaceWith(el);
  cards.set(key, { el, sig: s, body, dev: d });
  if (!c) loadControls(d);
  else if (S.controls[d.id]) renderControls(d);
  return el;
}

function refreshCard(d, force) {
  for (const k of ["d:", "c:"]) {
    const c = cards.get(k + d.id);
    if (c && force) c.sig = null;
  }
  renderGrids();
}

/* ------------------------------------------------------------------ ovládanie */
async function loadControls(d, quiet) {
  if (S.loading[d.id]) return;
  S.loading[d.id] = true;
  try {
    const r = await api(`/api/devices/${encodeURIComponent(d.id)}/controls`);
    S.controls[d.id] = r.controls;
  } catch (e) {
    S.controls[d.id] = [{ id: "err", type: "notice", label: "⚠ " + e.message }];
  } finally {
    S.loading[d.id] = false;
  }
  renderControls(d);
}

async function send(d, id, value) {
  const c = cards.get("c:" + d.id);
  c && c.el.classList.add("busy");
  S.lastAction[d.id] = Date.now();
  try {
    const r = await api(`/api/devices/${encodeURIComponent(d.id)}/controls`, { id, value });
    S.controls[d.id] = r.controls;
  } catch (e) {
    toast(`${d.display_name}: ${e.message}`, true);
    await loadControls(d, true);
  } finally {
    c && c.el.classList.remove("busy");
  }
  renderControls(d);
}

function renderControls(d) {
  const c = cards.get("c:" + d.id);
  const list = S.controls[d.id];
  if (!c || !list) return;
  if (c.body.contains(document.activeElement) && document.activeElement.matches("input[type=range],input[type=text],input[type=password],select")) return;
  const wrap = h("div", { class: "ctrls" });
  let section = null, group = null, btnRow = null, sensRow = null;
  const flush = () => { btnRow = null; sensRow = null; };
  for (const ct of list) {
    if (ct.section && ct.section !== section) { section = ct.section; group = null; flush(); wrap.append(h("div", { class: "ctrl-section" }, section)); }
    if ((ct.group || null) !== group) { group = ct.group || null; flush(); if (group) wrap.append(h("div", { class: "ctrl-group" }, group)); }
    if (ct.type !== "button") btnRow = null;
    if (ct.type !== "sensor") sensRow = null;
    switch (ct.type) {
      case "toggle": {
        const inp = h("input", { type: "checkbox", "aria-label": ct.label });
        inp.checked = !!ct.value;
        inp.addEventListener("change", () => send(d, ct.id, inp.checked));
        wrap.append(h("label", { class: "row" }, h("span", { class: "lbl" }, ct.label), h("span", { class: "switch" }, inp, h("span"))));
        break;
      }
      case "slider": {
        const unit = ct.unit || "";
        const val = h("span", { class: "val" }, `${ct.value}${unit}`);
        const inp = h("input", { type: "range", min: ct.min, max: ct.max, step: ct.step || 1, value: ct.value, "aria-label": ct.label });
        inp.addEventListener("input", () => { val.textContent = inp.value + unit; });
        inp.addEventListener("change", () => { send(d, ct.id, Number(inp.value)); inp.blur(); });
        wrap.append(h("div", { class: "slider" }, h("div", { class: "top-line" }, h("span", {}, ct.label), val), inp));
        break;
      }
      case "color": {
        const inp = h("input", { type: "color", value: ct.value || "#ffffff", "aria-label": ct.label });
        inp.addEventListener("change", () => send(d, ct.id, inp.value));
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, ct.label), inp));
        break;
      }
      case "select": {
        const sel = h("select", { "aria-label": ct.label }, (ct.options || []).map(([v, l]) => h("option", { value: v }, l)));
        sel.value = ct.value;
        sel.addEventListener("change", () => { send(d, ct.id, sel.value); sel.blur(); });
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, ct.label), sel));
        break;
      }
      case "button": {
        if (!btnRow) { btnRow = h("div", { class: "btn-row" }); wrap.append(btnRow); }
        btnRow.append(h("button", { class: "btn", onclick: () => send(d, ct.id, true) }, ct.icon && ICONS[ct.icon] ? svg(ICONS[ct.icon]) : null, ct.label));
        break;
      }
      case "sensor": {
        if (!sensRow) { sensRow = h("div", { class: "sensors" }); wrap.append(sensRow); }
        sensRow.append(h("span", { class: "sensor" }, ct.label + " ", h("b", {}, `${ct.value}${ct.unit ? " " + ct.unit : ""}`)));
        break;
      }
      case "pad": {
        const pad = h("div", { class: "pad" });
        for (const row of ct.rows) for (const cell of row) {
          pad.append(cell ? h("button", { title: cell[0], onclick: () => send(d, ct.id, cell[0]) }, cell[1]) : h("span"));
        }
        wrap.append(pad);
        break;
      }
      case "input": {
        const inp = h("input", { type: ct.secret ? "password" : "text", placeholder: ct.placeholder || "", "aria-label": ct.label, autocomplete: "off" });
        const go = () => inp.value.trim() && send(d, ct.id, inp.value.trim());
        inp.addEventListener("keydown", e => e.key === "Enter" && go());
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, ct.label)),
          h("div", { class: "input-row" }, inp, h("button", { class: "btn primary", onclick: go }, ct.button || "Uložiť")));
        break;
      }
      case "notice":
      default:
        wrap.append(h("div", { class: "notice" }, ct.label));
    }
  }
  c.body.replaceChildren(wrap);
}

/* priebežná obnova stavu ovládateľných zariadení */
setInterval(() => {
  if (document.hidden || S.scan.running) return;
  for (const d of S.devices) {
    if (!d.controllable || !cards.has("c:" + d.id)) continue;
    if (Date.now() - (S.lastAction[d.id] || 0) < 5000) continue;
    if (!cards.get("c:" + d.id).el.isConnected) continue;
    loadControls(d, true);
  }
}, 15000);

/* ------------------------------------------------------------------ login, téma */
function showLogin() {
  $("#login").hidden = false;
  setTimeout(() => $("#pinInput").focus(), 50);
}
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#loginErr").textContent = "";
  try {
    await api("/api/login", { pin: $("#pinInput").value.trim() });
    $("#login").hidden = true;
    loadState();
  } catch (err) { $("#loginErr").textContent = err.message; }
});

function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
applyTheme(localGet("theme"));
$("#themeBtn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  const t = dark ? "light" : "dark";
  applyTheme(t); localSet("theme", t);
});

$("#scanBtn").addEventListener("click", startScan);
let qTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { S.q = e.target.value.trim(); renderGrids(); }, 120);
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadState(); });
setInterval(renderMeta, 60000);

loadState();
