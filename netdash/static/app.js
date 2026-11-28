"use strict";
/* Môj domov – frontend dashboardu (bez závislostí) */

/* ================================================================ pomocníci */
const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(3)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
};
const svg = (name, extra) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.innerHTML = ICONS[name] || ICONS.dot;
  if (extra) s.setAttribute("class", extra);
  return s;
};
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmt = (n, d = 0) => Number(n).toLocaleString("sk-SK", { maximumFractionDigits: d, minimumFractionDigits: d });
const ipNum = ip => ip.split(".").reduce((a, b) => a * 256 + +b, 0);
const hash = s => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
function lsGet(k, d) { try { const v = localStorage.getItem("netdash." + k); return v == null ? d : JSON.parse(v); } catch { return d; } }
function lsSet(k, v) { try { localStorage.setItem("netdash." + k, JSON.stringify(v)); } catch { /* nič */ } }

const ICONS = {
  dot: '<circle cx="12" cy="12" r="2"/>',
  home: '<path d="M4 11 12 4.5l8 6.5v9H4z"/><path d="M10 20v-5h4v5"/>',
  pie: '<path d="M12 3v9h9"/><path d="M20.5 15A9 9 0 1 1 9 3.5"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  net: '<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="19" r="2.2"/><circle cx="19" cy="19" r="2.2"/><path d="M12 7.2v4.3M12 11.5 6.5 17M12 11.5l5.5 5.5"/>',
  tv: '<rect x="3" y="5" width="18" height="12" rx="2.5"/><path d="M8 20h8"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  plug: '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>',
  bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>',
  speaker: '<rect x="5" y="3" width="14" height="18" rx="3"/><circle cx="12" cy="14" r="3.5"/><path d="M12 7h.01"/>',
  play: '<path d="M7 4.5v15l12.5-7.5z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
  next: '<path d="M5 5l10 7-10 7zM19 5v14"/>', prev: '<path d="M19 5 9 12l10 7zM5 5v14"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>', up: '<path d="M6 15l6-6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>',
  power: '<path d="M12 3v8M6.3 7.3a8 8 0 1 0 11.4 0"/>', link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  vol: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>', mute: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="m17 9 4 6M21 9l-4 6"/>',
  blinds: '<path d="M4 4h16M5 4v12M19 4v12M5 8h14M5 12h14M5 16h14M12 16v4"/>',
  thermo: '<path d="M10 14.5V5a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z"/>', snow: '<path d="M12 2v20M4.9 6.5l14.2 11M19.1 6.5 4.9 17.5"/>',
  flame: '<path d="M12 22c4 0 6.5-2.6 6.5-6.3 0-3.6-2.6-5.5-3.7-8.7-.4 1.9-1.5 3-2.8 3.4C12.5 6.8 11 4 8 2c.5 4-3.5 6.5-3.5 11.7C4.5 18.7 8 22 12 22z"/>',
  wind: '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8"/>', fan: '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7 2 0 3 2 2 4-1 1.6-3.4 2.7-6 3zM14 12c4 0 7 1 7 4 0 2-2 3-4 2-1.6-1-2.7-3.4-3-6zM12 14c0 4-1 7-4 7-2 0-3-2-2-4 1-1.6 3.4-2.7 6-3zM10 12c-4 0-7-1-7-4 0-2 2-3 4-2 1.6 1 2.7 3.4 3 6z"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>', monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>', web: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>', warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  router: '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 16.5h.01M11 16.5h.01M17 13V9M8.5 7.5a5 5 0 0 1 7 0M6 5a8.5 8.5 0 0 1 12 0"/>',
  smart: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>',
  media: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>', computer: '<rect x="4" y="4" width="16" height="11" rx="2"/><path d="M2 19h20"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
  printer: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><rect x="7" y="14" width="10" height="7" rx="1"/>',
  camera: '<path d="M15 10l5-3v10l-5-3z"/><rect x="3" y="6" width="12" height="12" rx="2"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  unknown: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
  remote: '<rect x="7" y="2" width="10" height="20" rx="3"/><circle cx="12" cy="8" r="2"/><path d="M10 14h.01M14 14h.01M10 17h.01M14 17h.01"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
};

const CAT_LABEL = { router: "Sieť", smart: "Smart domácnosť", media: "TV a audio", computer: "Počítače", phone: "Mobily",
  server: "Servery a NAS", printer: "Tlačiarne", camera: "Kamery", unknown: "Neznáme" };
const KIND_CAT = { light: "Svetlá", switch: "Vypínače", media: "Médiá", cover: "Žalúzie", thermo: "Klíma", scene: "Scény", generic: "Ostatné", setup: "Ostatné", loading: "Ostatné" };
const PALETTES = {
  les: { name: "Les", accent: "#2c7a47", a2: "#5cc87a", t1: "#5cc87a", t2: "#ee8a6c", t3: "#f2c14e" },
  ocean: { name: "Oceán", accent: "#0f7f86", a2: "#4fc4c9", t1: "#5fd0c8", t2: "#ef8f74", t3: "#f2c14e" },
  jantar: { name: "Jantár", accent: "#c2571a", a2: "#f19a4b", t1: "#f6b26b", t2: "#e9765b", t3: "#f2d04e" },
  levandula: { name: "Levanduľa", accent: "#6b4fd0", a2: "#a08af7", t1: "#b7a6ff", t2: "#f28fae", t3: "#f2c14e" },
  grafit: { name: "Grafit", accent: "#4a5a70", a2: "#8fa3bd", t1: "#9fb7d1", t2: "#e8907a", t3: "#e6c35f" },
};
const WEATHER = [[0, "☀️", "Jasno"], [1, "🌤️", "Prevažne jasno"], [2, "⛅", "Polojasno"], [3, "☁️", "Zamračené"],
  [48, "🌫️", "Hmla"], [57, "🌦️", "Mrholenie"], [67, "🌧️", "Dážď"], [77, "🌨️", "Sneženie"], [82, "🌦️", "Prehánky"],
  [86, "🌨️", "Snehové prehánky"], [99, "⛈️", "Búrka"]];
const PAGES = [["home", "Domov", "home"], ["cameras", "Kamery", "camera"], ["energy", "Energia", "pie"], ["alerts", "Upozornenia", "bell"], ["network", "Sieť", "net"]];

const S = {
  devices: [], meta: {}, scan: {}, demo: false, location: null, location_name: null, home_name: null,
  controls: {}, loading: {}, lastAction: {}, expanded: new Set(),
  page: "home", filter: "all", netFilter: "all", q: "", weather: null, look: lsGet("look", {}),
  hist: lsGet("hist", []),
  cams: { cameras: [], suggestions: [], ffmpeg: true, presets: {} }, camMode: lsGet("camMode", "live"), camForm: null, camTest: null,
};
let interacting = false, pendingRender = false;
const camEls = new Map();

/* ================================================================ API */
async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json", "X-NetDash": "1" } };
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch { /* nič */ }
  if (r.status === 401) { showLogin(); throw new Error("Vyžaduje sa PIN"); }
  if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
  return data;
}
function toast(msg, err = false) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 6000 : 3000);
}

let stateTimer = null;
async function loadState() {
  clearTimeout(stateTimer);
  try {
    const d = await api("/api/state");
    const wasRunning = S.scan.running;
    Object.assign(S, { devices: d.devices, meta: d.meta || {}, scan: d.scan || {}, demo: d.demo,
      location: d.location, location_name: d.location_name, home_name: d.home_name });
    $("#login").hidden = true;
    for (const dev of S.devices) if (dev.controllable && !(dev.id in S.controls)) loadControls(dev);
    if (wasRunning && !S.scan.running) {
      if (S.scan.error) toast("Sken zlyhal: " + S.scan.error, true);
      else toast(`Sken dokončený – online ${S.devices.filter(x => x.online).length} zariadení`);
      for (const dev of S.devices) if (dev.controllable) loadControls(dev);
    }
    if (!S.weather && S.location) loadWeather();
    render();
  } catch (e) {
    if ($("#login").hidden) toast("Server nedostupný: " + e.message, true);
  }
  stateTimer = setTimeout(loadState, S.scan.running ? 700 : 30000);
}

async function loadControls(dev) {
  if (S.loading[dev.id]) return;
  S.loading[dev.id] = true;
  try {
    S.controls[dev.id] = (await api(`/api/devices/${encodeURIComponent(dev.id)}/controls`)).controls;
  } catch (e) {
    S.controls[dev.id] = [{ id: "x/err", type: "notice", label: "⚠ " + e.message }];
  } finally { S.loading[dev.id] = false; }
  sampleEnergy();
  render();
}

async function send(dev, id, value, card) {
  S.lastAction[dev.id] = Date.now();
  const list = S.controls[dev.id] || [];
  const c = list.find(x => x.id === id);
  if (c && ["toggle", "slider", "color", "select"].includes(c.type)) { c.value = value; render(); }  // optimisticky
  if (card) card.classList.add("busy");
  try {
    S.controls[dev.id] = (await api(`/api/devices/${encodeURIComponent(dev.id)}/controls`, { id, value })).controls;
  } catch (e) {
    toast(`${dev.display_name}: ${e.message}`, true);
    await loadControls(dev);
  }
  render();
}

async function startScan() {
  try { await api("/api/scan", {}); S.scan.running = true; render(); setTimeout(loadState, 300); }
  catch (e) { toast(e.message, true); }
}

async function loadWeather() {
  if (!S.location) { S.weather = null; return; }
  try {
    const [lat, lon] = S.location;
    const r = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1`);
    const j = await r.json();
    const code = j.current.weather_code;
    const w = WEATHER.find(x => code <= x[0]) || WEATHER[WEATHER.length - 1];
    S.weather = { ico: w[1], txt: w[2], t: j.current.temperature_2m, min: j.daily.temperature_2m_min[0], max: j.daily.temperature_2m_max[0],
      hum: j.current.relative_humidity_2m, wind: j.current.wind_speed_10m };
  } catch { S.weather = { error: true }; }
  render();
}

/* ================================================================ vzhľad */
function applyLook() {
  const L = S.look, root = document.documentElement;
  const pal = PALETTES[L.palette] || PALETTES.les;
  const accent = L.accent || pal.accent;
  const theme = L.theme || "dark";
  const light = theme === "light" || (theme === "system" && matchMedia("(prefers-color-scheme: light)").matches);
  root.classList.toggle("light", light);
  root.dataset.tint = L.tint || "neutral";
  root.dataset.density = L.density || "comfortable";
  root.style.setProperty("--accent", accent);
  root.style.setProperty("--accent-2", L.accent ? mix(accent, "#ffffff", .35) : pal.a2);
  root.style.setProperty("--t1", pal.t1); root.style.setProperty("--t2", pal.t2); root.style.setProperty("--t3", pal.t3);
  root.style.setProperty("--r", (L.radius || 22) + "px");
  $('meta[name="theme-color"]').setAttribute("content", light ? "#efeae3" : "#1a1714");
}
function mix(a, b, t) {
  const p = x => [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16));
  const [r1, g1, b1] = p(a), [r2, g2, b2] = p(b);
  return "#" + [r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t].map(v => Math.round(v).toString(16).padStart(2, "0")).join("");
}
function setLook(patch) { Object.assign(S.look, patch); lsSet("look", S.look); applyLook(); render(true); }
matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyLook);

/* ================================================================ widgety */
const attrOf = c => { const tail = c.id.split("/").slice(1).join("/"); return tail.includes("|") ? tail.split("|")[2] : tail; };
const isVol = c => c.type === "slider" && (/vol/.test(attrOf(c)) || /hlasitos/i.test(c.label));
const isBri = c => c.type === "slider" && (/(^|:)(bri|bright|dimmer|gain)$/.test(attrOf(c)) || /jas/i.test(c.label));
const isCt = c => c.type === "slider" && /teplota farby/i.test(c.label);
const mediaBtn = c => c.type === "button" && ["play", "pause", "next", "prev"].includes(c.icon);
const coverBtn = c => c.type === "button" && ["up", "down", "stop"].includes(c.icon);

function canWake(d) { return (d.drivers || []).some(x => ["lgwebos", "samsung", "philips"].includes(x.key)); }

function buildWidgets() {
  const out = [];
  for (const dev of S.devices) {
    if (!dev.controllable || !(dev.online || canWake(dev))) continue;
    const list = S.controls[dev.id];
    if (!list) { out.push({ kind: "loading", dev, key: dev.id, title: dev.display_name, ctrls: [] }); continue; }
    const groups = new Map();
    for (const c of list) {
      const ha = c.id.match(/^[^/]+\/ha\|([^|]+)\|/);
      const grp = c.type === "pad" ? "" : (c.group || "");
      const key = ha ? "ha:" + ha[1] : (c.section || "") + "|" + grp;
      if (!groups.has(key)) groups.set(key, { ctrls: [], ha: !!ha, group: ha ? c.group : grp || null });
      groups.get(key).ctrls.push(c);
    }
    const single = groups.size === 1;
    for (const [key, g] of groups) {
      let title, sub;
      if (g.ha) {
        title = g.ctrls[0].label.replace(/ – (aktuálne|cieľ)$/, "").replace(/ \(zamknuté\)$/, "").replace(/^↳ /, "");
        sub = g.group;
      } else if (single || !g.group) { title = dev.display_name; sub = g.group || driverSub(dev); }
      else { title = g.group; sub = dev.display_name; }
      out.push({ kind: classify(g.ctrls), dev, key: dev.id + "#" + key, title, sub, ctrls: g.ctrls });
    }
  }
  const order = { thermo: 0, media: 1, light: 2, switch: 3, cover: 4, scene: 5, generic: 6, setup: 7, loading: 8 };
  return out.sort((a, b) => (order[a.kind] - order[b.kind]) || a.title.localeCompare(b.title, "sk"));
}
function driverSub(dev) { return (dev.drivers || []).map(x => x.label).join(" + ") || CAT_LABEL[dev.category]; }

function classify(cs) {
  const t = type => cs.filter(c => c.type === type);
  if (cs.length === 1 && cs[0].type === "button") return "scene";
  if (t("pad").length || cs.some(isVol) || cs.some(mediaBtn)) return "media";
  if (cs.filter(coverBtn).length >= 2) return "cover";
  if (cs.some(c => c.type === "slider" && c.unit === "°C")) return "thermo";
  if (cs.some(isBri) && t("toggle").length) return "light";
  if (t("toggle").length === 1 && !t("slider").length && !t("select").length && !t("button").length) return "switch";
  if (cs.length === 1 && cs[0].type === "button") return "scene";
  if (cs.every(c => ["notice", "input", "button"].includes(c.type))) return "setup";
  return "generic";
}

/* ---------------------------------------------------------------- spoločné prvky */
function swToggle(on, onchange, small, label) {
  const inp = h("input", { type: "checkbox", "aria-label": label || "Zapnúť" });
  inp.checked = !!on;
  inp.addEventListener("change", () => onchange(inp.checked));
  return h("label", { class: "sw" + (small ? " sm" : "") }, inp, h("span"));
}
function range(c, onDone, cls) {
  const inp = h("input", { type: "range", min: c.min, max: c.max, step: c.step || 1, value: c.value, "aria-label": c.label, class: cls });
  const paint = () => inp.style.setProperty("--p", ((inp.value - c.min) / ((c.max - c.min) || 1) * 100) + "%");
  paint();
  inp.addEventListener("pointerdown", () => { interacting = true; });
  inp.addEventListener("input", paint);
  inp.addEventListener("change", () => { interacting = false; onDone(Number(inp.value)); });
  inp.addEventListener("blur", () => { interacting = false; });
  return inp;
}
function cardShell(w, extraCls, ...kids) {
  return h("article", { class: "glass card " + (extraCls || "") + (w.dev.online ? "" : " offline"), "data-key": w.key }, ...kids);
}
function head(w, right) {
  return h("div", { class: "card-top" },
    h("div", {}, h("div", { class: "card-title" }, w.title), w.sub ? h("div", { class: "card-sub" }, w.sub) : null), right || null);
}

/* generické riadky (všetko, čo špecializovaný widget nespotrebuje) */
function rows(dev, list, card) {
  const wrap = h("div", { class: "rows" });
  let grp = null, btnRow = null, sens = null;
  for (const c of list) {
    if (c.type !== "pad" && c.group && c.group !== grp && list.some(x => x.group !== c.group)) { grp = c.group; btnRow = sens = null; wrap.append(h("div", { class: "group-t" }, grp)); }
    if (c.type !== "button") btnRow = null;
    if (c.type !== "sensor") sens = null;
    switch (c.type) {
      case "toggle":
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, c.label), swToggle(c.value, v => send(dev, c.id, v, card), true, c.label)));
        break;
      case "slider": {
        const val = h("span", { class: "val" }, `${c.value}${c.unit || ""}`);
        const r = range(c, v => send(dev, c.id, v, card));
        r.addEventListener("input", () => { val.textContent = r.value + (c.unit || ""); });
        wrap.append(h("div", { class: "slider-row" }, h("div", { class: "top-line" }, h("span", {}, c.label), val), r));
        break;
      }
      case "color": {
        const inp = h("input", { type: "color", value: c.value || "#ffffff", "aria-label": c.label });
        inp.addEventListener("change", () => send(dev, c.id, inp.value, card));
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, c.label), inp));
        break;
      }
      case "select": {
        const sel = h("select", { "aria-label": c.label }, (c.options || []).map(([v, l]) => h("option", { value: v }, l)));
        sel.value = c.value;
        sel.addEventListener("focus", () => { interacting = true; });
        sel.addEventListener("blur", () => { interacting = false; });
        sel.addEventListener("change", () => { interacting = false; send(dev, c.id, sel.value, card); sel.blur(); });
        wrap.append(h("div", { class: "row" }, h("span", { class: "lbl" }, c.label), sel));
        break;
      }
      case "button":
        if (!btnRow) { btnRow = h("div", { class: "btn-row" }); wrap.append(btnRow); }
        btnRow.append(h("button", { class: "btn" + (c.icon === "power" || c.icon === "link" ? " primary" : ""), onclick: () => send(dev, c.id, true, card) },
          c.icon && ICONS[c.icon] ? svg(c.icon) : null, c.label));
        break;
      case "sensor":
        if (!sens) { sens = h("div", { class: "sensors" }); wrap.append(sens); }
        sens.append(h("span", { class: "sensor" }, c.label + " ", h("b", {}, `${typeof c.value === "number" ? fmt(c.value, 1) : c.value}${c.unit ? " " + c.unit : ""}`)));
        break;
      case "pad": {
        const pad = h("div", { class: "pad" });
        for (const row of c.rows) for (const cell of row) pad.append(cell ? h("button", { title: cell[0], onclick: () => send(dev, c.id, cell[0], card) }, cell[1]) : h("span"));
        wrap.append(h("details", { class: "more" }, h("summary", {}, svg("remote"), "Diaľkový ovládač"), pad));
        break;
      }
      case "input": {
        const inp = h("input", { type: c.secret ? "password" : "text", placeholder: c.placeholder || "", "aria-label": c.label, autocomplete: "off" });
        const go = () => inp.value.trim() && send(dev, c.id, inp.value.trim(), card);
        inp.addEventListener("focus", () => { interacting = true; });
        inp.addEventListener("blur", () => { interacting = false; });
        inp.addEventListener("keydown", e => e.key === "Enter" && go());
        wrap.append(h("div", { class: "lbl" }, c.label), h("div", { class: "input-row" }, inp, h("button", { class: "btn primary", onclick: go }, c.button || "Uložiť")));
        break;
      }
      default:
        wrap.append(h("div", { class: "notice" }, c.label));
    }
  }
  return wrap;
}

/* ---------------------------------------------------------------- svetlo */
function ctToColor(c) {
  const f = (c.value - c.min) / ((c.max - c.min) || 1);
  const warm = c.unit && c.unit.includes("K") ? 1 - f : f;  // Kelvin: viac = studenšie; mired: viac = teplejšie
  return mix("#dfe9ff", "#ffc98a", warm);
}
function lightWidget(w) {
  const { dev, ctrls } = w;
  const tg = ctrls.find(c => c.type === "toggle"), bri = ctrls.find(isBri);
  const col = ctrls.find(c => c.type === "color"), ct = ctrls.find(isCt);
  const used = new Set([tg, bri, col, ct].filter(Boolean));
  const on = !!tg.value;
  const card = cardShell(w, "");
  const pct = Math.round((bri.value - bri.min) / ((bri.max - bri.min) || 1) * 100);
  const lc = col && col.value ? mix(col.value, "#ffffff", .25) : ct ? ctToColor(ct) : "#ead8b8";

  const lvl = h("div", { class: "lvl", style: `height:${on ? Math.max(pct, 4) : 0}%;--lc:${lc}` });
  const pctEl = h("div", { class: "pct" }, on ? pct + "%" : "Vyp.");
  const fill = h("div", { class: "fill" + (on ? "" : " off") + (on && pct < 86 ? " low" : ""), tabindex: "0", role: "slider", "aria-label": "Jas", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100 },
    lvl, pctEl, h("div", { class: "bulb" }, svg("bulb")));
  let cur = pct;
  const setPct = p => { cur = clamp(Math.round(p), 1, 100); lvl.style.height = cur + "%"; pctEl.textContent = cur + "%"; fill.classList.remove("off"); fill.classList.toggle("low", cur < 86); };
  const commit = () => send(dev, bri.id, Math.round(bri.min + (bri.max - bri.min) * cur / 100), card);
  const fromEvent = e => { const r = fill.getBoundingClientRect(); setPct((r.bottom - e.clientY) / r.height * 100); };
  fill.addEventListener("pointerdown", e => { interacting = true; fill.setPointerCapture(e.pointerId); fill.classList.add("dragging"); fromEvent(e); });
  fill.addEventListener("pointermove", e => { if (fill.classList.contains("dragging")) fromEvent(e); });
  fill.addEventListener("pointerup", () => { fill.classList.remove("dragging"); interacting = false; commit(); });
  fill.addEventListener("pointercancel", () => { fill.classList.remove("dragging"); interacting = false; });
  let kt;
  fill.addEventListener("keydown", e => {
    const d = { ArrowUp: 5, ArrowRight: 5, ArrowDown: -5, ArrowLeft: -5 }[e.key];
    if (!d) return;
    e.preventDefault(); setPct(cur + d); clearTimeout(kt); kt = setTimeout(commit, 400);
  });

  const presets = h("div", { class: "presets" });
  if (ct) {
    const lo = ct.min + (ct.max - ct.min) * .08, hi = ct.max - (ct.max - ct.min) * .08, mid = (ct.min + ct.max) / 2;
    const kelvin = ct.unit && ct.unit.includes("K");
    for (const [name, v, dot] of [["Teplá", kelvin ? lo : hi, "#ffc070"], ["Jemná", mid, "#ffe7c2"], ["Studená", kelvin ? hi : lo, "#dbe8ff"]]) {
      const near = Math.abs(ct.value - v) < (ct.max - ct.min) * .18;
      presets.append(h("button", { class: "chip" + (near && on ? " on" : ""), onclick: () => send(dev, ct.id, Math.round(v / (ct.step || 1)) * (ct.step || 1), card) },
        h("span", { class: "sw-dot", style: `background:${dot}` }), name));
    }
  }
  if (col && !ct) {
    for (const [name, hex] of [["Teplá", "#ffb46b"], ["Jemná", "#ffe3bf"], ["Studená", "#d6e6ff"]]) {
      presets.append(h("button", { class: "chip" + (on && col.value && col.value.toLowerCase() === hex ? " on" : ""), onclick: () => send(dev, col.id, hex, card) },
        h("span", { class: "sw-dot", style: `background:${hex}` }), name));
    }
  }
  if (col) {
    const pick = h("input", { type: "color", value: col.value || "#ffffff", "aria-label": "Vlastná farba", title: "Vlastná farba" });
    pick.addEventListener("change", () => send(dev, col.id, pick.value, card));
    presets.append(pick);
  }
  card.append(head(w, swToggle(on, v => send(dev, tg.id, v, card), false, w.title)),
    h("div", { class: "light-body" }, fill, presets.children.length ? presets : null));
  const rest = ctrls.filter(c => !used.has(c));
  if (rest.length) card.append(rows(dev, rest, card));
  return card;
}

/* ---------------------------------------------------------------- vypínač / zásuvka */
function switchWidget(w) {
  const { dev, ctrls } = w;
  const tg = ctrls.find(c => c.type === "toggle");
  const sensors = ctrls.filter(c => c.type === "sensor");
  const power = sensors.find(c => c.unit === "W");
  const on = !!tg.value;
  const ico = /svetl|lamp|light/i.test(w.title + tg.label) ? "bulb" : /ventil|fan/i.test(w.title) ? "fan" : /zámk|lock/i.test(tg.label) ? "lock" : "plug";
  const card = cardShell(w, on ? `tile-c c${(hash(w.key) % 3) + 1}` : "");
  card.append(head(w, swToggle(on, v => send(dev, tg.id, v, card), false, w.title)),
    h("div", { class: "big-ico" }, svg(ico)),
    h("div", { class: "stat-pill" },
      h("span", {}, power ? `${fmt(power.value, 1)} W` : (tg.label !== w.title && tg.label !== "Napájanie" ? tg.label + " · " : "") + (on ? "Zapnuté" : "Vypnuté")),
      h("span", { class: "mini" }, svg(power ? "bolt" : "power"))));
  const others = sensors.filter(c => c !== power);
  if (others.length) card.append(rows(dev, others, card));
  return card;
}

/* ---------------------------------------------------------------- prehrávač / TV */
function mediaWidget(w) {
  const { dev, ctrls } = w;
  const vol = ctrls.find(isVol), mute = ctrls.find(c => c.type === "toggle" && /stlmi|mute/i.test(c.label));
  const stateS = ctrls.find(c => c.type === "sensor" && /stav/i.test(c.label));
  const pwr = ctrls.find(c => c.type === "toggle" && c !== mute && (/zapnut|^power$/i.test(c.label) || /:on$|\|on$|\/power$|\/on$/.test(c.id)));
  const btn = ic => ctrls.find(c => c.type === "button" && c.icon === ic);
  const play = btn("play"), pause = btn("pause"), next = btn("next"), prev = btn("prev");
  const used = new Set([vol, mute, stateS, pwr, play, pause, next, prev].filter(Boolean));
  const isTv = dev.category === "media" && /tv|televíz/i.test((dev.display_name || "") + driverSub(dev));
  const playing = stateS && /hrá|playing/i.test(String(stateS.value));
  const card = cardShell(w, "w2");

  const tr = h("div", { class: "transport" });
  if (prev) tr.append(h("button", { title: prev.label, onclick: () => send(dev, prev.id, true, card) }, svg("prev")));
  const main = playing ? (pause || play) : (play || pause);
  if (main) tr.append(h("button", { class: "play", title: main.label, onclick: () => send(dev, main.id, true, card) }, svg(main === pause ? "pause" : "play")));
  if (play && pause && !stateS) tr.append(h("button", { title: pause.label, onclick: () => send(dev, pause.id, true, card) }, svg("pause")));
  if (next) tr.append(h("button", { title: next.label, onclick: () => send(dev, next.id, true, card) }, svg("next")));

  const info = h("div", { class: "player-main" },
    h("div", { class: "card-sub" }, w.sub || driverSub(dev)),
    h("div", { class: "title" }, w.title),
    h("div", { class: "state" }, stateS ? stateS.value : pwr ? (pwr.value ? "Zapnuté" : "Vypnuté") : (dev.online ? "Online" : "Offline")),
    tr.children.length ? tr : null,
    vol ? h("div", { class: "vol" },
      mute ? h("button", { class: "round", style: "width:38px;height:38px", title: "Stlmiť", onclick: () => send(dev, mute.id, !mute.value, card) }, svg(mute.value ? "mute" : "vol")) : svg("vol"),
      range(vol, v => send(dev, vol.id, v, card)),
      h("span", { style: "min-width:2.5em;text-align:right" }, String(vol.value))) : null);
  card.append(h("div", { class: "card-top" }, h("div"), pwr ? swToggle(pwr.value, v => send(dev, pwr.id, v, card), false, "Zapnúť") : null));
  card.firstChild.style.cssText = "position:absolute;right:var(--pad);top:var(--pad)";
  card.append(h("div", { class: "player" }, h("div", { class: "art" }, svg(isTv ? "tv" : "speaker")), info));
  const rest = ctrls.filter(c => !used.has(c));
  if (rest.length) card.append(rows(dev, rest, card));
  return card;
}

/* ---------------------------------------------------------------- žalúzie */
function coverWidget(w) {
  const { dev, ctrls } = w;
  const pos = ctrls.find(c => c.type === "slider");
  const st = ctrls.find(c => c.type === "sensor");
  const btns = ctrls.filter(coverBtn).sort((a, b) => ["up", "stop", "down"].indexOf(a.icon) - ["up", "stop", "down"].indexOf(b.icon));
  const used = new Set([pos, st, ...btns].filter(Boolean));
  const open = pos ? pos.value : st && /otvoren/.test(st.value) ? 100 : st && /zatvoren/.test(st.value) ? 0 : 50;
  const card = cardShell(w, "");
  card.append(head(w), h("div", { class: "blind" }, h("div", { class: "slats", style: `height:${100 - open}%` }),
    h("div", { class: "pos" }, pos ? `${pos.value} % otvorené` : (st ? st.value : ""))));
  if (pos) card.append(range(pos, v => send(dev, pos.id, v, card)));
  card.append(h("div", { class: "btn-row" }, btns.map(b => h("button", { class: "btn", onclick: () => send(dev, b.id, true, card) }, svg(b.icon), b.label))));
  const rest = ctrls.filter(c => !used.has(c));
  if (rest.length) card.append(rows(dev, rest, card));
  return card;
}

/* ---------------------------------------------------------------- termostat */
function thermoWidget(w) {
  const { dev, ctrls } = w;
  const tgt = ctrls.find(c => c.type === "slider" && c.unit === "°C");
  const cur = ctrls.find(c => c.type === "sensor" && c.unit === "°C");
  const used = new Set([tgt, cur].filter(Boolean));
  const card = cardShell(w, "");
  const R = 80, C = 2 * Math.PI * R, sweep = .75, f = clamp((tgt.value - tgt.min) / ((tgt.max - tgt.min) || 1), 0, 1);
  const ang = (135 + 270 * f) * Math.PI / 180;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  g.setAttribute("viewBox", "0 0 200 180"); g.setAttribute("class", "gauge");
  const gid = "g" + (hash(w.key) % 1e6);
  g.innerHTML = `<defs><linearGradient id="${gid}" x1="0" x2="1"><stop offset="0" stop-color="#4aa3ff"/><stop offset=".55" stop-color="#f2c14e"/><stop offset="1" stop-color="#ee6c4d"/></linearGradient></defs>
    <circle cx="100" cy="100" r="${R}" stroke="var(--glass-3)" stroke-dasharray="${C * sweep} ${C}" transform="rotate(135 100 100)"/>
    <circle cx="100" cy="100" r="${R}" stroke="url(#${gid})" stroke-dasharray="${C * sweep * f} ${C}" transform="rotate(135 100 100)"/>
    <circle cx="100" cy="100" r="58" stroke="var(--line)" stroke-width="1"/>
    <circle cx="${100 + R * Math.cos(ang)}" cy="${100 + R * Math.sin(ang)}" r="9" fill="#fff" stroke="none"/>
    <text x="34" y="176" fill="var(--muted)" stroke="none" font-size="11">${fmt(tgt.min, 0)}°</text>
    <text x="150" y="176" fill="var(--muted)" stroke="none" font-size="11">${fmt(tgt.max, 0)}°</text>`;
  const step = tgt.step || .5;
  card.append(head(w),
    h("div", { class: "thermo" }, g, h("div", { class: "center" }, h("small", {}, "Cieľová teplota"), h("b", {}, fmt(tgt.value, 1) + "°"),
      cur ? h("span", {}, `Teraz ${fmt(cur.value, 1)}°`) : null)),
    h("div", { class: "pm" },
      h("button", { class: "round", onclick: () => send(dev, tgt.id, clamp(+(tgt.value - step).toFixed(1), tgt.min, tgt.max), card), "aria-label": "Znížiť" }, "−"),
      h("button", { class: "round", onclick: () => send(dev, tgt.id, clamp(+(tgt.value + step).toFixed(1), tgt.min, tgt.max), card), "aria-label": "Zvýšiť" }, "+")));
  const rest = ctrls.filter(c => !used.has(c));
  if (rest.length) card.append(rows(dev, rest, card));
  return card;
}

/* ---------------------------------------------------------------- scéna, setup, generické */
function sceneWidget(w) {
  const b = w.ctrls[0];
  const card = cardShell(w, `tile-c c${(hash(w.key) % 3) + 1}`);
  card.style.cursor = "pointer";
  card.addEventListener("click", () => send(w.dev, b.id, true, card));
  card.append(head(w, h("span", { class: "round", style: "background:rgba(0,0,0,.12);border:0" }, svg(b.icon === "play" ? "sparkle" : (b.icon || "sparkle")))),
    h("div", { class: "stat-pill" }, h("span", {}, "Spustiť"), h("span", { class: "mini" }, svg("play"))));
  return card;
}
function genericWidget(w) {
  const card = cardShell(w, w.ctrls.length > 8 ? "w2" : "");
  card.append(head(w), rows(w.dev, w.ctrls, card));
  return card;
}
function loadingWidget(w) { return cardShell(w, "", head({ ...w, sub: driverSub(w.dev) }), h("div", { class: "loading" }, "Načítavam stav…")); }

const RENDER = { light: lightWidget, switch: switchWidget, media: mediaWidget, cover: coverWidget, thermo: thermoWidget,
  scene: sceneWidget, generic: genericWidget, setup: genericWidget, loading: loadingWidget };

/* ================================================================ stránky */
function pageHome() {
  const all = buildWidgets();
  const q = S.q.toLowerCase();
  const cats = ["all", ...new Set(all.map(w => KIND_CAT[w.kind]))];
  if (!cats.includes(S.filter)) S.filter = "all";
  setDock(cats.map(c => [c, c === "all" ? "Všetko" : c]), S.filter, v => { S.filter = v; render(true); });
  const list = all.filter(w => (S.filter === "all" || KIND_CAT[w.kind] === S.filter) &&
    (!q || (w.title + " " + (w.sub || "") + " " + w.dev.display_name).toLowerCase().includes(q)));

  const frag = h("div");
  const top = h("div", { class: "grid" }, weatherCard(), summaryCard());
  frag.append(top);
  if (!list.length) {
    frag.append(h("div", { class: "glass card empty", style: "margin-top:var(--gap)" },
      S.devices.length ? (all.length ? "Nič nevyhovuje filtru." : "V sieti sa nenašli ovládateľné zariadenia. Pozri stránku Sieť.") :
        (S.scan.running ? "Hľadám zariadenia…" : "Zatiaľ nič – klikni na + a preskenuj sieť.")));
  }
  const grid = h("div", { class: "grid" });
  if (S.filter === "all" && !q) for (const cam of S.cams.cameras.slice(0, 2)) grid.append(camTile(cam, "home"));
  for (const w of list) {
    try { grid.append(RENDER[w.kind](w)); }
    catch (e) { console.error(e); grid.append(genericWidget(w)); }
  }
  frag.append(grid);
  return frag;
}

function weatherCard() {
  const W = S.weather;
  if (!S.location) {
    return h("article", { class: "glass card weather w2" }, h("div", { class: "w-ico" }, "🌤️"),
      h("div", {}, h("div", { class: "card-title" }, "Počasie"), h("div", { class: "card-sub" }, "Nastav svoje mesto v Nastaveniach"),
        h("button", { class: "btn", style: "margin-top:10px", onclick: () => go("settings") }, svg("gear"), "Nastaviť")));
  }
  if (!W || W.error) return h("article", { class: "glass card weather w2" }, h("div", { class: "w-ico" }, "🌤️"), h("div", { class: "card-sub" }, W ? "Počasie sa nepodarilo načítať" : "Načítavam počasie…"));
  return h("article", { class: "glass card weather w2" }, h("div", { class: "w-ico" }, W.ico),
    h("div", {}, h("div", { class: "w-t" }, Math.round(W.t) + "°", h("small", {}, ` / ${Math.round(W.min)}°`)),
      h("div", { class: "card-sub" }, `${W.txt} · ${S.location_name || "vonku"} · max ${Math.round(W.max)}° · vietor ${Math.round(W.wind)} km/h`)));
}
function summaryCard() {
  const on = S.devices.filter(d => d.online).length;
  const e = energy();
  const lightsOn = buildWidgets().filter(w => (w.kind === "light" || w.kind === "switch") && w.ctrls.some(c => c.type === "toggle" && c.value)).length;
  return h("article", { class: "glass card w2" }, h("div", { class: "card-top" }, h("div", {}, h("div", { class: "card-title" }, "Prehľad"),
    h("div", { class: "card-sub" }, S.meta.scanned_at ? `Posledný sken ${ago(S.meta.scanned_at)}` : "Sieť ešte nebola preskenovaná"))),
  h("div", { class: "summary" },
    h("div", {}, h("b", {}, String(on)), h("span", {}, "online")),
    h("div", {}, h("b", {}, String(lightsOn)), h("span", {}, "zapnutých")),
    h("div", {}, h("b", {}, e.devices.length ? fmtW(e.total) : "–"), h("span", {}, "príkon"))));
}

/* ---------------------------------------------------------------- energia */
function energy() {
  const devices = [];
  let total = 0, today = 0;
  for (const d of S.devices) {
    const list = S.controls[d.id];
    if (!list || !d.online) continue;
    let w = null, k = null;
    for (const c of list) {
      if (c.type !== "sensor" || typeof c.value !== "number") continue;
      if (c.unit === "W") w = (w || 0) + c.value;
      if (c.unit === "kWh" && /dnes|today/i.test(c.label)) k = (k || 0) + c.value;
    }
    if (w != null || k != null) devices.push({ dev: d, w: w || 0, kwh: k });
    total += w || 0; today += k || 0;
  }
  devices.sort((a, b) => b.w - a.w);
  return { devices, total, today, hasToday: devices.some(x => x.kwh != null) };
}
const fmtW = w => w >= 1000 ? fmt(w / 1000, 2) + " kW" : fmt(w, 0) + " W";
let lastSample = 0;
function sampleEnergy() {
  const e = energy();
  if (!e.devices.length || Date.now() - lastSample < 55000) return;
  lastSample = Date.now();
  S.hist.push([Math.round(Date.now() / 1000), Math.round(e.total)]);
  const cut = Date.now() / 1000 - 86400;
  S.hist = S.hist.filter(x => x[0] > cut).slice(-1500);
  lsSet("hist", S.hist);
}

function pageEnergy() {
  setDock([], null);
  const e = energy();
  const top = e.devices[0];
  const frag = h("div");
  frag.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Energia"),
    h("p", {}, e.devices.length ? `Práve teraz ${fmtW(e.total)} z ${e.devices.length} meraných zariadení` : "Žiadne zariadenie zatiaľ nemeria príkon"))));
  const drawing = e.devices.filter(x => x.w > 1).length;
  frag.append(h("div", { class: "stats4" },
    stat("d", "bolt", "Príkon teraz", fmtW(e.total), `${drawing} zariadení odoberá`),
    stat("c1", "plug", "Spotreba dnes", e.hasToday ? fmt(e.today, 2) + " kWh" : "–", e.hasToday ? "zo zariadení s meraním energie" : "zariadenia nehlásia dennú spotrebu"),
    stat("c2", "sparkle", "Najväčší odber", top ? fmtW(top.w) : "–", top ? top.dev.display_name : "—"),
    stat("c3", "net", "Zariadenia online", String(S.devices.filter(d => d.online).length), `${S.devices.filter(d => d.controllable).length} ovládateľných`)));

  // graf – hodinové priemery z histórie (zbiera sa, kým je dashboard otvorený)
  const now = Date.now() / 1000, buckets = [];
  for (let i = 23; i >= 0; i--) {
    const from = now - (i + 1) * 3600, to = now - i * 3600;
    const v = S.hist.filter(x => x[0] > from && x[0] <= to).map(x => x[1]);
    buckets.push({ v: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null, hour: new Date(to * 1000).getHours() });
  }
  const max = Math.max(1, ...buckets.map(b => b.v || 0));
  const chart = h("div", { class: "chart" }, buckets.map(b => h("div", { class: "b", style: `height:${b.v == null ? 2 : Math.max(3, b.v / max * 100)}%;${b.v == null ? "opacity:.25" : ""}`,
    "data-tip": b.v == null ? `${b.hour}:00 – bez dát` : `${b.hour}:00 – ${fmtW(b.v)}` })));
  const chartCard = h("article", { class: "glass card" },
    h("div", { class: "card-top" }, h("div", {}, h("div", { class: "card-title" }, "Príkon za posledných 24 hodín"),
      h("div", { class: "card-sub" }, "Hodinové priemery · zaznamenáva sa, kým je dashboard otvorený"))),
    chart, S.hist.length < 3 ? h("div", { class: "card-sub" }, "Graf sa bude postupne plniť – každú minútu sa zaznamená aktuálny príkon.") : null,
    h("div", { class: "chart-x" }, buckets.filter((_, i) => i % 4 === 0).map(b => h("span", {}, b.hour + ":00"))));

  const share = top && e.total ? top.w / e.total : 0;
  const R = 70, C = 2 * Math.PI * R;
  const d = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  d.setAttribute("viewBox", "0 0 180 180");
  d.innerHTML = `<circle cx="90" cy="90" r="${R}" stroke="var(--glass-3)"/><circle cx="90" cy="90" r="${R}" stroke="var(--t3)" stroke-dasharray="${C * share} ${C}" transform="rotate(-90 90 90)"/>`;
  const donut = h("article", { class: "glass card" }, h("div", {}, h("div", { class: "card-title" }, "Najväčší spotrebič"), h("div", { class: "card-sub" }, top ? top.dev.display_name : "—")),
    h("div", { class: "donut" }, d, h("div", { class: "c" }, h("b", {}, Math.round(share * 100) + " %"), h("span", {}, "z celkového príkonu"))),
    h("div", { class: "kv" }, h("span", {}, "Celkom teraz"), h("b", {}, fmtW(e.total)), h("span", {}, "Merané zariadenia"), h("b", {}, String(e.devices.length)),
      h("span", {}, "Záznamov v grafe"), h("b", {}, String(S.hist.length))));
  frag.append(h("div", { class: "split" }, chartCard, donut));

  const bars = h("div", { class: "bars" }, e.devices.length ? e.devices.map(x => h("div", { class: "bar-row" },
    h("span", {}, x.dev.display_name), h("b", {}, fmtW(x.w) + (x.kwh != null ? ` · dnes ${fmt(x.kwh, 2)} kWh` : "")),
    h("div", { class: "track" }, h("i", { style: `width:${e.total ? x.w / Math.max(...e.devices.map(y => y.w), 1) * 100 : 0}%` })))) :
    h("div", { class: "notice" }, "Príkon merajú napr. Shelly Plug/PM, Tasmota s meraním energie alebo Home Assistant. Keď ich dashboard nájde, objavia sa tu."));
  frag.append(h("article", { class: "glass card", style: "margin-top:var(--gap)" }, h("div", { class: "card-title" }, "Podľa zariadenia"), bars));
  return frag;
}
function stat(cls, ico, k, v, s) {
  return h("div", { class: "stat " + cls }, h("div", { class: "k" }, svg(ico), k), h("div", {}, h("div", { class: "v" }, v), h("div", { class: "s" }, s)));
}

/* ---------------------------------------------------------------- upozornenia */
function alertsList() {
  const out = [];
  for (const d of S.devices.filter(x => x.new)) out.push(["new", "sparkle", `Nové zariadenie: ${d.display_name}`, `${d.ip}${d.vendor ? " · " + d.vendor : ""} · prvýkrát ${ago(d.first_seen)}`, d]);
  for (const d of S.devices) {
    const err = (S.controls[d.id] || []).find(c => /\/err$/.test(c.id));
    if (err && d.online) out.push(["err", "warn", `${d.display_name} nereaguje`, err.label.replace(/^⚠\s*/, ""), d]);
  }
  for (const d of S.devices.filter(x => !x.online)) out.push(["off", "power", `${d.display_name} je offline`, `naposledy ${ago(d.last_seen)} · ${d.ip}`, d]);
  return out;
}
function pageAlerts() {
  setDock([], null);
  const list = alertsList();
  return h("div", {}, h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Upozornenia"), h("p", {}, list.length ? `${list.length} položiek` : "Všetko v poriadku"))),
    list.length ? list.map(([k, ico, t, s, d]) => h("div", { class: "glass alert" }, h("div", { class: "a-ico " + k }, svg(ico)),
      h("div", { class: "a-t" }, h("b", {}, t), h("div", {}, s)),
      d.mac && k === "off" ? h("button", { class: "btn", onclick: () => wol(d) }, svg("power"), "Zobudiť") : null)) :
      h("div", { class: "glass card empty" }, "Žiadne nové ani nedostupné zariadenia."));
}

/* ---------------------------------------------------------------- sieť */
function pageNetwork() {
  const cats = ["all", "controllable", ...Object.keys(CAT_LABEL).filter(c => S.devices.some(d => d.category === c)), "offline"];
  const label = c => c === "all" ? "Všetko" : c === "controllable" ? "Ovládateľné" : c === "offline" ? "Offline" : CAT_LABEL[c];
  setDock(cats.map(c => [c, label(c)]), S.netFilter, v => { S.netFilter = v; render(true); });
  const q = S.q.toLowerCase();
  const list = S.devices.filter(d => {
    const f = S.netFilter;
    const okF = f === "all" || (f === "offline" ? !d.online : f === "controllable" ? d.controllable : d.category === f);
    const hay = [d.display_name, d.ip, d.mac, d.vendor, d.model, d.hostname, CAT_LABEL[d.category]].join(" ").toLowerCase();
    return okF && (!q || q.split(/\s+/).every(x => hay.includes(x)));
  }).sort((a, b) => (b.online - a.online) || ipNum(a.ip) - ipNum(b.ip));
  const m = S.meta;
  return h("div", {}, h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Sieť"),
    h("p", {}, m.network ? `${m.network} · brána ${m.gateway || "?"} · ${S.devices.filter(d => d.online).length} online z ${S.devices.length}` : "Sieť ešte nebola preskenovaná")),
  h("button", { class: "btn primary", onclick: startScan, disabled: S.scan.running }, svg("plus"), S.scan.running ? "Skenujem…" : "Skenovať")),
  list.length ? h("div", { class: "dev-list" }, list.map(devCard)) : h("div", { class: "glass card empty" }, "Nič nevyhovuje filtru."));
}
function devCard(d) {
  const name = h("span", { class: "txt", title: "Dvojklik = premenovať" }, d.display_name);
  const nameRow = h("div", { class: "dev-name" }, h("span", { class: "dot" }), name,
    h("button", { class: "edit", title: "Premenovať", "aria-label": "Premenovať", onclick: () => rename(d, name) }, svg("edit")),
    d.new ? h("span", { class: "tag new" }, "nové") : null, d.is_self ? h("span", { class: "tag" }, "tento PC") : null,
    d.controllable ? h("span", { class: "tag" }, "ovládateľné") : null);
  name.addEventListener("dblclick", () => rename(d, name));
  const vm = [d.vendor, d.model].filter(Boolean).join(" ");
  const card = h("article", { class: "glass dev" + (d.online ? "" : " offline") },
    h("div", { class: "dev-h" }, h("div", { class: "dev-ico c-" + d.category, title: CAT_LABEL[d.category] }, svg(ICONS[d.category] ? d.category : "unknown")),
      h("div", { class: "dev-t" }, nameRow, h("div", { class: "dev-sub" }, [d.ip, vm].filter(Boolean).join(" · ")))),
    d.ports && d.ports.length ? h("div", { class: "ports" }, d.ports.map(p => h("span", { class: "port" }, String(p.service) === String(p.port) ? p.port : `${p.service} :${p.port}`))) : null,
    S.expanded.has(d.id) ? details(d) : null,
    h("div", { class: "links" },
      (d.links || []).map(l => h("a", { class: "link", href: l.url, target: "_blank", rel: "noopener" }, svg("web"), l.label)),
      d.mac && !d.is_self ? h("button", { class: "link", title: "Wake-on-LAN", onclick: () => wol(d) }, svg("power"), "Zobudiť") : null,
      h("button", { class: "link", onclick: () => { S.expanded.has(d.id) ? S.expanded.delete(d.id) : S.expanded.add(d.id); render(true); } },
        svg("info"), S.expanded.has(d.id) ? "Menej" : "Detaily")));
  return card;
}
function details(d) {
  const rows = [["IP", d.ip], ["MAC", d.mac ? d.mac + (d.random_mac ? " (súkromná)" : "") : "—"], ["Typ", CAT_LABEL[d.category]],
    ["Výrobca", d.vendor], ["Model", d.model], ["Hostname", d.hostname], ["Ovládanie", (d.drivers || []).map(x => x.label).join(", ")],
    ["Služby", (d.mdns_services || []).map(s => s.replace(/^_|\._(tcp|udp)$/g, "")).join(", ")],
    ["Videné", d.online ? "teraz" : ago(d.last_seen)], ["Prvýkrát", ago(d.first_seen)]].filter(([, v]) => v);
  return h("dl", { class: "details" }, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
}
function rename(d, nameEl) {
  const inp = h("input", { value: d.display_name, maxlength: "60", "aria-label": "Názov" });
  let done = false;
  const finish = async save => {
    if (done) return; done = true; interacting = false;
    const v = inp.value.trim();
    if (save && v !== d.display_name) {
      try { await api(`/api/devices/${encodeURIComponent(d.id)}/alias`, { name: v === d.name ? "" : v }); await loadState(); return; }
      catch (e) { toast(e.message, true); }
    }
    render(true);
  };
  inp.addEventListener("keydown", e => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
  inp.addEventListener("blur", () => finish(true));
  interacting = true;
  nameEl.replaceWith(inp); inp.focus(); inp.select();
}
async function wol(d) {
  try { await api(`/api/devices/${encodeURIComponent(d.id)}/wol`, {}); toast(`Magický paket odoslaný (${d.display_name})`); }
  catch (e) { toast(e.message, true); }
}

/* ---------------------------------------------------------------- nastavenia */
function seg(options, value, onpick) {
  return h("div", { class: "seg" }, options.map(([v, l, ic]) => h("button", { class: v === value ? "on" : "", onclick: () => onpick(v) }, ic ? svg(ic) : null, l)));
}
function pageSettings() {
  setDock([], null);
  const L = S.look, pal = PALETTES[L.palette || "les"];
  const accent = L.accent || pal.accent;
  const hex = h("input", { class: "field", value: accent, maxlength: "7", "aria-label": "Farba akcentu" });
  hex.addEventListener("change", () => { if (/^#[0-9a-f]{6}$/i.test(hex.value)) setLook({ accent: hex.value.toLowerCase() }); });
  const sw = h("input", { type: "color", class: "swatch", value: accent, "aria-label": "Vybrať farbu" });
  sw.addEventListener("change", () => setLook({ accent: sw.value }));
  const rad = h("input", { type: "range", min: 8, max: 32, value: L.radius || 22, "aria-label": "Zaoblenie" });
  const radV = h("span", { style: "min-width:3em;text-align:right;color:var(--muted)" }, (L.radius || 22) + " px");
  const paintR = () => rad.style.setProperty("--p", ((rad.value - 8) / 24 * 100) + "%");
  paintR();
  rad.addEventListener("input", () => { paintR(); radV.textContent = rad.value + " px"; document.documentElement.style.setProperty("--r", rad.value + "px"); });
  rad.addEventListener("change", () => setLook({ radius: Number(rad.value) }));

  const homeIn = h("input", { class: "field", value: S.home_name || "", placeholder: "Môj domov", maxlength: "40", style: "max-width:260px" });
  homeIn.addEventListener("change", async () => { try { await api("/api/settings", { home_name: homeIn.value }); S.home_name = homeIn.value.trim() || null; renderHead(); } catch (e) { toast(e.message, true); } });

  const geoIn = h("input", { class: "field", placeholder: "Napíš mesto, napr. Košice", "aria-label": "Mesto" });
  const geoRes = h("div", { class: "geo-results" });
  let gt;
  geoIn.addEventListener("input", () => {
    clearTimeout(gt);
    gt = setTimeout(async () => {
      const q = geoIn.value.trim();
      if (q.length < 2) { geoRes.replaceChildren(); return; }
      try {
        const j = await (await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=5&language=sk&format=json`)).json();
        geoRes.replaceChildren(...(j.results || []).map(r => h("button", { onclick: async () => {
          const nm = r.name;
          await api("/api/settings", { location: [r.latitude, r.longitude], location_name: nm });
          S.location = [r.latitude, r.longitude]; S.location_name = nm; S.weather = null; loadWeather();
          toast(`Poloha nastavená: ${nm}`); render(true);
        } }, `${r.name}${r.admin1 ? ", " + r.admin1 : ""}${r.country ? ", " + r.country : ""}`)));
        if (!(j.results || []).length) geoRes.replaceChildren(h("div", { class: "card-sub" }, "Nič sa nenašlo"));
      } catch { geoRes.replaceChildren(h("div", { class: "card-sub" }, "Vyhľadávanie miest nie je dostupné (bez internetu?)")); }
    }, 350);
  });

  const left = h("article", { class: "glass card" },
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Názov domova"), h("span", {}, "Zobrazí sa v hlavičke")), homeIn),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Téma"), h("span", {}, "Svetlé sklo cez deň, tmavé v noci")),
      seg([["light", "Svetlá", "sun"], ["dark", "Tmavá", "moon"], ["system", "Systém", "monitor"]], L.theme || "dark", v => setLook({ theme: v }))),
    h("div", { class: "set-row col" }, h("div", { class: "t" }, h("b", {}, "Paleta")),
      h("div", { class: "chips" }, Object.entries(PALETTES).map(([k, p]) => h("button", { class: "chip" + ((L.palette || "les") === k && !L.accent ? " on" : ""), onclick: () => setLook({ palette: k, accent: null }) },
        h("span", { style: "display:inline-flex" }, h("span", { class: "sw-dot", style: `background:${p.accent}` }), h("span", { class: "sw-dot", style: `background:${p.a2};margin-left:-5px` })), p.name)))),
    h("div", { class: "set-row col" }, h("div", { class: "t" }, h("b", {}, "Akcent"), h("span", {}, "Tlačidlá, aktívne prvky a odkazy")), h("div", { class: "accent-pick" }, sw, hex)),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Odtieň skla"), h("span", {}, "Farba okna a kariet")),
      seg([["neutral", "Neutrálne"], ["cool", "Studené"], ["warm", "Teplé"]], L.tint || "neutral", v => setLook({ tint: v }))),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Zaoblenie"), h("span", {}, "Karty, tlačidlá a polia")), h("div", { class: "range-wrap" }, rad, radV)),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Hustota"), h("span", {}, "Pohodlná alebo kompaktná")),
      seg([["comfortable", "Pohodlná"], ["compact", "Kompaktná"]], L.density || "comfortable", v => setLook({ density: v }))),
    h("div", { class: "set-row col" }, h("div", { class: "t" }, h("b", {}, "Poloha pre počasie"),
      h("span", {}, S.location ? `Teraz: ${S.location_name || S.location.join(", ")}` : "Zatiaľ nenastavená")), geoIn, geoRes),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "TV režim"), h("span", {}, "Celoobrazovkový domov pre televízor, ovládaný šípkami")),
      h("a", { class: "btn", href: "/tv", target: "_blank" }, svg("tv"), "Otvoriť")),
    h("div", { class: "set-row" }, h("div", { class: "t" }, h("b", {}, "Obnoviť vzhľad"), h("span", {}, "Vráti predvolené farby a tvary")),
      h("button", { class: "btn", onclick: () => { S.look = {}; lsSet("look", {}); applyLook(); render(true); } }, "Obnoviť")));

  const t = swToggle(true, () => { }, false, "Ukážka");
  const preview = h("article", { class: "glass card preview" },
    h("div", {}, h("div", { class: "card-title" }, "Náhľad"), h("div", { class: "card-sub" }, "Z aktuálnych nastavení")),
    h("div", { class: "btn-row", style: "flex-wrap:nowrap" }, h("button", { class: "btn primary" }, "Hlavné"), h("button", { class: "btn" }, "Tlačidlo")),
    h("div", { class: "chips", style: "align-items:center" }, h("span", { class: "status-chip" }, "Aktívne"), h("span", { class: "status-chip" }, "Online"), t),
    h("input", { class: "field", placeholder: "Textové pole" }),
    h("div", { class: "progress" }, h("i")),
    h("div", { class: "bars-p" }, [40, 70, 55, 100, 60, 75].map((v, i) => h("i", { class: i === 3 ? "hi" : "", style: `height:${v}%` }))),
    h("div", { class: "grid", style: "grid-template-columns:repeat(3,1fr);gap:8px;margin:0" },
      ["c1", "c2", "c3"].map(c => h("div", { class: `tile-c ${c}`, style: "height:54px;border-radius:calc(var(--r) - 8px)" }))));
  return h("div", {}, h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Nastavenia"), h("p", {}, "Tvoj domov a ako dashboard vyzerá"))),
    h("div", { class: "settings" }, left, preview));
}

/* ================================================================ kostra */
function ago(ts) {
  if (!ts) return "nikdy";
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 60) return "práve teraz";
  if (s < 3600) return `pred ${Math.round(s / 60)} min`;
  if (s < 86400) return `pred ${Math.round(s / 3600)} h`;
  return new Date(ts * 1000).toLocaleString("sk-SK");
}
let dockPick = null;
function setDock(items, value, onpick) {
  const dock = $("#dock");
  dockPick = onpick;
  dock.replaceChildren(...items.map(([v, l]) => h("button", { class: "f" + (v === value ? " on" : ""), onclick: () => dockPick && dockPick(v) }, l)),
    h("button", { class: "plus", title: "Skenovať sieť", "aria-label": "Skenovať sieť", onclick: startScan }, svg("plus")));
  dock.hidden = false;
}
function renderRail() {
  const alerts = alertsList().filter(a => a[0] !== "off").length;
  $("#railMain").replaceChildren(...PAGES.map(([id, label, ico]) => h("button", { class: "rail-btn" + (S.page === id ? " active" : ""), onclick: () => go(id), "aria-label": label },
    svg(ico), id === "alerts" && alerts ? h("span", { class: "badge-dot" }) : null, h("span", { class: "tip" }, label))));
  $("#railMore").replaceChildren(
    h("a", { class: "rail-btn", href: "/tv", target: "_blank", "aria-label": "TV režim" }, svg("tv"), h("span", { class: "tip" }, "TV režim")),
    h("button", { class: "rail-btn" + (S.page === "settings" ? " active" : ""), onclick: () => go("settings"), "aria-label": "Nastavenia" }, svg("gear"), h("span", { class: "tip" }, "Nastavenia")));
}
function renderHead() {
  $("#homeName").textContent = S.home_name || "Môj domov";
  const m = S.meta, on = S.devices.filter(d => d.online).length;
  $("#homeSub").textContent = S.scan.running ? (S.scan.phase || "Skenujem…") :
    m.network ? `${S.location_name ? S.location_name + " · " : ""}${on} zariadení online · sieť ${m.network}` : "Sieť ešte nebola preskenovaná";
  $("#homeDot").classList.toggle("scanning", !!S.scan.running);
  const e = energy();
  $("#powerPill").hidden = !e.devices.length;
  $("#powerVal").textContent = fmtW(e.total);
  const sc = S.scan;
  $("#scanBtn").classList.toggle("spin", !!sc.running);
  $("#scanBtn").disabled = !!sc.running;
  $("#scanbar").hidden = !sc.running;
  $("#scanbarFill").style.width = (sc.total ? Math.round(sc.done / sc.total * 100) : 5) + "%";
  $("#demoNote").hidden = !S.demo;
}
function render(force) {
  if (interacting && !force) { pendingRender = true; return; }
  pendingRender = false;
  renderRail();
  renderHead();
  const page = { home: pageHome, cameras: pageCameras, energy: pageEnergy, alerts: pageAlerts, network: pageNetwork, settings: pageSettings }[S.page] || pageHome;
  if ((S.page === "settings" || (S.page === "cameras" && S.camForm)) && $("#page").dataset.page === S.page && !force) return;  // neprerušovať písanie
  const scrollY = window.scrollY;
  const openDetails = [...document.querySelectorAll("details.more[open]")].map(d => d.closest("[data-key]") && d.closest("[data-key]").dataset.key);
  $("#page").replaceChildren(page());
  $("#page").dataset.page = S.page;
  for (const k of openDetails) { const el = document.querySelector(`[data-key="${CSS.escape(k)}"] details.more`); if (el) el.open = true; }
  window.scrollTo(0, scrollY);
  syncCams();
}
document.addEventListener("pointerup", () => { if (interacting) setTimeout(() => { if (!document.activeElement || !document.activeElement.matches("input,select")) { interacting = false; if (pendingRender) render(); } }, 50); });

function go(page) {
  S.page = page;
  const slug = { home: "", cameras: "kamery", energy: "energia", alerts: "upozornenia", network: "siet", settings: "nastavenia" }[page];
  history.replaceState(null, "", slug ? "#/" + slug : location.pathname);
  window.scrollTo(0, 0);
  render(true);
}
function fromHash() {
  const m = { kamery: "cameras", energia: "energy", upozornenia: "alerts", siet: "network", nastavenia: "settings" }[location.hash.replace(/^#\/?/, "")];
  S.page = m || "home";
}

/* ================================================================ udalosti */
function showLogin() { $("#login").hidden = false; setTimeout(() => $("#pinInput").focus(), 50); }
$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault();
  $("#loginErr").textContent = "";
  try { await api("/api/login", { pin: $("#pinInput").value.trim() }); $("#login").hidden = true; loadState(); }
  catch (err) { $("#loginErr").textContent = err.message; }
});
$("#themeBtn").addEventListener("click", () => setLook({ theme: document.documentElement.classList.contains("light") ? "dark" : "light" }));
$("#scanBtn").addEventListener("click", startScan);
$("#homeName").addEventListener("dblclick", () => go("settings"));
let qt;
$("#search").addEventListener("input", e => { clearTimeout(qt); qt = setTimeout(() => { S.q = e.target.value.trim(); render(true); }, 120); });
$("#search").addEventListener("focus", () => { if (!["home", "network"].includes(S.page)) go("home"); });
window.addEventListener("hashchange", () => { fromHash(); render(true); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadState(); });

setInterval(() => {
  if (document.hidden || S.scan.running) return;
  for (const d of S.devices) {
    if (!d.controllable) continue;
    if (Date.now() - (S.lastAction[d.id] || 0) < 6000) continue;
    loadControls(d);
  }
}, 15000);
setInterval(() => { if (S.location) loadWeather(); }, 1800000);
setInterval(() => renderHead(), 60000);

document.addEventListener("visibilitychange", syncCams);
setInterval(loadCams, 60000);

applyLook();
fromHash();
loadCams();
render(true);
loadState();

/* ================================================================ kamery */
async function loadCams() {
  try { S.cams = await api("/api/cameras"); } catch { return; }
  if (!interacting) render();
}
function camSrc(cam) { return `/cam/${cam.id}/stream.mjpg${S.camMode === "slow" ? "?slow=1" : ""}`; }
function camTile(cam, variant) {
  const key = cam.id + ":" + variant + ":" + S.camMode;
  let rec = camEls.get(key);
  if (rec) { rec.name.textContent = cam.name; return rec.el; }
  const img = h("img", { alt: cam.name, decoding: "async" });
  const err = h("div", { class: "cam-err", hidden: true });
  const name = h("span", {}, cam.name);
  const el = h("article", { class: "cam glass" + (variant === "home" ? " w2" : ""), "data-key": "cam-" + key },
    img, err,
    h("div", { class: "cam-top" }, h("span", { class: "cam-name" }, h("i", { class: "live" }), name),
      h("div", { class: "cam-act" },
        h("a", { class: "round sm", href: `/cam/${cam.id}/snapshot.jpg`, download: `${cam.name}.jpg`, title: "Uložiť snímku", onclick: e => e.stopPropagation() }, svg("download")),
        variant !== "home" ? h("button", { class: "round sm", title: "Nastavenia kamery", onclick: e => { e.stopPropagation(); editCam(cam); } }, svg("gear")) : null,
        h("button", { class: "round sm", title: "Na celú obrazovku", onclick: e => { e.stopPropagation(); (el.requestFullscreen || el.webkitRequestFullscreen || (() => {})).call(el); } }, svg("expand")))));
  if (variant === "home") el.addEventListener("click", () => go("cameras"));
  rec = { el, img, err, name, cam, active: false, retry: null };
  img.addEventListener("load", () => { err.hidden = true; el.classList.add("ok"); });
  img.addEventListener("error", async () => {
    if (!rec.active) return;
    el.classList.remove("ok");
    let msg = "Obraz nie je dostupný";
    try {
      const r = await fetch(`/cam/${cam.id}/snapshot.jpg`, { cache: "no-store" });
      if (!r.ok) msg = (await r.json()).error || msg;
    } catch { /* nič */ }
    err.textContent = msg + " – skúšam znova…";
    err.hidden = false;
    clearTimeout(rec.retry);
    rec.retry = setTimeout(() => { if (rec.active) img.src = camSrc(cam) + (camSrc(cam).includes("?") ? "&" : "?") + "t=" + Date.now(); }, 10000);
  });
  camEls.set(key, rec);
  return el;
}
function syncCams() {
  for (const [key, rec] of camEls) {
    const want = rec.el.isConnected && !document.hidden;
    if (want && !rec.active) { rec.active = true; rec.img.src = camSrc(rec.cam) + (camSrc(rec.cam).includes("?") ? "&" : "?") + "t=" + Date.now(); }
    else if (!want && rec.active) { rec.active = false; clearTimeout(rec.retry); rec.img.removeAttribute("src"); rec.img.src = "data:,"; }
    if (!rec.el.isConnected && !S.cams.cameras.some(c => c.id === rec.cam.id)) camEls.delete(key);
  }
}
function editCam(cam) {
  S.camForm = cam ? { id: cam.id, type: cam.type, name: cam.name, preset: cam.preset || "generic", ip: cam.ip || "", user: cam.user || "", password: "",
    rtsp: (cam.custom || {}).rtsp || "", snapshot: (cam.custom || {}).snapshot || "", mjpeg: (cam.custom || {}).mjpeg || "",
    ha_ip: cam.ha_ip, entity: cam.entity, channel: cam.channel || 1, editing: true } :
    { type: "net", name: "", preset: "hikvision", ip: "", user: "admin", password: "", rtsp: "", snapshot: "", mjpeg: "", channel: 1 };
  S.camTest = null;
  go("cameras");
  setTimeout(() => { const f = $(".cam-form"); if (f) f.scrollIntoView({ behavior: "smooth", block: "start" }); }, 50);
}
function addSuggested(sg) {
  S.camForm = sg.type === "ha" ? { type: "ha", name: sg.name, ha_ip: sg.ha_ip, entity: sg.entity } :
    { type: "net", name: sg.name, preset: sg.preset, ip: sg.ip, user: (S.cams.presets[sg.preset] || {}).user || "admin", password: "", rtsp: "", snapshot: "", mjpeg: "" };
  S.camTest = null;
  render(true);
  setTimeout(() => { const f = $(".cam-form"); if (f) f.scrollIntoView({ behavior: "smooth", block: "start" }); }, 50);
}
async function camAction(action, extra) {
  const F = S.camForm;
  const btns = document.querySelectorAll(".cam-form .btn");
  btns.forEach(b => b.disabled = true);
  try {
    const r = await api("/api/cameras", { action, camera: F, ...(extra || {}) });
    if (action === "test") { S.camTest = { image: r.image }; }
    else { S.camForm = null; S.camTest = null; toast("Kamera uložená"); await loadCams(); }
  } catch (e) {
    S.camTest = { error: e.message };
  }
  render(true);
}
function camForm() {
  const F = S.camForm;
  const bind = (k, attrs) => {
    const inp = h("input", { class: "field", value: F[k] || "", ...attrs });
    inp.addEventListener("input", () => { F[k] = inp.value; });
    inp.addEventListener("focus", () => { interacting = true; });
    inp.addEventListener("blur", () => { interacting = false; });
    return inp;
  };
  const lbl = (t, el, hint) => h("label", { class: "form-row" }, h("span", {}, t), el, hint ? h("small", {}, hint) : null);
  const card = h("article", { class: "glass card cam-form w2" }, h("div", { class: "card-title" }, F.editing ? "Upraviť kameru" : "Pridať kameru"));
  if (F.type === "ha") {
    card.append(h("div", { class: "notice" }, `Kamera z Home Assistant: ${F.entity}`), lbl("Názov", bind("name", { maxlength: "40" })));
  } else {
    const sel = h("select", { class: "field" }, Object.entries(S.cams.presets).map(([k, p]) => h("option", { value: k }, p.label)));
    sel.value = F.preset;
    sel.addEventListener("change", () => { F.preset = sel.value; F.user = (S.cams.presets[sel.value] || {}).user || F.user; render(true); });
    const note = (S.cams.presets[F.preset] || {}).note;
    card.append(h("div", { class: "form-grid" },
      lbl("Značka / typ", sel), lbl("Názov", bind("name", { maxlength: "40", placeholder: "Napr. Vchod" })),
      F.preset !== "generic" ? lbl("IP adresa", bind("ip", { placeholder: "192.168.1.60", inputmode: "decimal" })) : null,
      (S.cams.presets[F.preset] || {}).channels ? lbl("Kanál", bind("channel", { type: "number", min: "1", max: "64", inputmode: "numeric" }), "1 = samostatná kamera") : null,
      lbl("Používateľ", bind("user", { autocomplete: "off" })),
      lbl("Heslo", bind("password", { type: "password", autocomplete: "new-password", placeholder: F.editing ? "nezmenené" : "" }))),
    note ? h("div", { class: "notice" }, note) : "");
    if (F.preset === "generic") {
      card.append(lbl("RTSP adresa", bind("rtsp", { placeholder: "rtsp://192.168.1.60:554/stream1" }), "Meno a heslo môžeš zadať hore, alebo priamo v adrese."),
        lbl("Adresa obrázka (JPEG)", bind("snapshot", { placeholder: "http://192.168.1.60/snapshot.jpg" })),
        lbl("Adresa MJPEG videa", bind("mjpeg", { placeholder: "http://192.168.1.60/video.mjpg" })));
    }
  }
  if (S.camTest && S.camTest.image) card.append(h("img", { class: "cam-preview", src: S.camTest.image, alt: "Test" }), h("div", { class: "status-chip" }, "Kamera funguje"));
  if (S.camTest && S.camTest.error) card.append(h("div", { class: "notice err" }, "⚠ " + S.camTest.error));
  card.append(h("div", { class: "btn-row" },
    h("button", { class: "btn", onclick: () => camAction("test") }, svg("camera"), "Otestovať"),
    h("button", { class: "btn primary", onclick: () => camAction("save") }, "Uložiť"),
    S.camTest && S.camTest.error ? h("button", { class: "btn", onclick: () => camAction("save", { test: false }) }, "Uložiť aj tak") : null,
    F.editing ? h("button", { class: "btn danger", onclick: async () => {
      if (!confirm(`Odstrániť kameru ${F.name}?`)) return;
      await api("/api/cameras", { action: "delete", id: F.id }); S.camForm = null; toast("Kamera odstránená"); loadCams();
    } }, "Odstrániť") : null,
    h("button", { class: "btn", onclick: () => { S.camForm = null; S.camTest = null; render(true); } }, "Zrušiť")));
  return card;
}
function pageCameras() {
  setDock([["live", "Živé video"], ["slow", "Úsporný režim"]], S.camMode, v => { S.camMode = v; lsSet("camMode", v); render(true); });
  const C = S.cams;
  const frag = h("div", {}, h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Kamery"),
    h("p", {}, C.cameras.length ? `${C.cameras.length} ${C.cameras.length === 1 ? "kamera" : C.cameras.length < 5 ? "kamery" : "kamier"} · ${S.camMode === "slow" ? "úsporný režim (obrázok každé 2 s)" : "živé video"}` : "Zatiaľ žiadna kamera")),
  S.camForm ? null : h("button", { class: "btn primary", onclick: () => editCam(null) }, svg("plus"), "Pridať kameru")));
  if (!C.ffmpeg && C.cameras.some(c => c.source === "RTSP")) {
    frag.append(h("div", { class: "glass card notice-card" }, h("b", {}, "Pre plynulé živé video nainštaluj ffmpeg"),
      h("div", { class: "card-sub" }, "Bez neho sa RTSP kamery nedajú prehrať. Po inštalácii program reštartuj."),
      h("pre", {}, "Mac:      brew install ffmpeg\nWindows:  winget install ffmpeg\nLinux:    sudo apt install ffmpeg")));
  }
  const grid = h("div", { class: "grid cam-grid" });
  if (S.camForm) grid.append(camForm());
  for (const cam of C.cameras) grid.append(camTile(cam, "page"));
  frag.append(grid);
  if (C.suggestions.length && !S.camForm) {
    frag.append(h("div", { class: "sec" }, "Nájdené v sieti"), h("div", { class: "grid" }, C.suggestions.map(sg => h("article", { class: "glass card" },
      h("div", { class: "card-top" }, h("div", {}, h("div", { class: "card-title" }, sg.name), h("div", { class: "card-sub" }, sg.type === "ha" ? `Home Assistant · ${sg.entity}` : `${sg.ip}${sg.vendor ? " · " + sg.vendor : ""}`)),
        h("span", { class: "round", style: "border:0" }, svg("camera"))),
      h("button", { class: "btn primary", onclick: () => addSuggested(sg) }, svg("plus"), "Pridať")))));
  }
  if (!C.cameras.length && !C.suggestions.length && !S.camForm) {
    frag.append(h("div", { class: "glass card empty" }, "V sieti som nenašiel žiadnu kameru. Pridaj ju ručne – stačí IP adresa, meno a heslo."));
  }
  return frag;
}
