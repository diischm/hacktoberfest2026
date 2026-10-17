// Map page ("/"): reports from E3 as pins, report detail sheet from E4.
// Labels and condition colors come only from GET /api/meta/ (E2), never from this file.
// API data is always inserted with textContent / text nodes, never as HTML.

import { ApiError, getMeta, getReport, getReports } from "./api.js";
import { TILE_LAYER } from "./config.js";

const L = window.L; // Leaflet, loaded by a classic <script> before this module runs

const RELOAD_DEBOUNCE_MS = 300;
const MIN_PIN_OPACITY = 0.55;

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const $ = (selector) => document.querySelector(selector);

const el = {
  map: $("#map"),
  layersBtn: $("#layers-btn"),
  layers: $("#layers"),
  layerTypes: $("#layer-types"),
  showResolved: $("#show-resolved"),
  showDemo: $("#show-demo"),
  layersKey: $("#layers-key"),
  legendKey: $("#legend-key"),
  loading: $("#map-loading"),
  error: $("#map-error"),
  errorText: $("#map-error-text"),
  retry: $("#map-retry"),
  note: $("#map-note"),
  summary: $("#summary"),
  summaryRows: $("#summary-rows"),
  summaryDemo: $("#summary-demo"),
  reportHere: $("#report-here"),
  detail: $("#detail"),
  detailGrip: $("#detail-grip"),
  detailClose: $("#detail-close"),
  detailPhoto: $("#detail-photo"),
  detailChips: $("#detail-chips"),
  detailTitle: $("#detail-title"),
  detailDesc: $("#detail-desc"),
  detailNote: $("#detail-note"),
  detailFacts: $("#detail-facts"),
  detailMsg: $("#detail-msg"),
  detailActions: $("#detail-actions"),
};

const state = {
  meta: null,
  hazards: new Map(), // key -> meta.hazard_types item
  conditions: new Map(), // key -> meta.conditions item
  statuses: new Map(), // key -> label
  data: null, // last E3 FeatureCollection
  hiddenTypes: new Set(),
  showDemo: true,
  includeResolved: false,
  reportsSeq: 0, // bumps on every E3 request; older answers are ignored
  detailSeq: 0,
  activeId: null,
  seenIds: new Set(), // pins already shown once (only new ones get the drop animation)
};

let map = null;
let reportLayer = null;
let retryAction = null;

// --- Small DOM helpers -----------------------------------------------------------------

// h("span", {class: "chip"}, "text"): strings become text nodes, so they can't inject HTML.
function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) node.append(child);
  }
  return node;
}

// Icon shapes keyed by meta.hazard_types[].icon (a hint, not a file). Our own static
// markup, parsed once with DOMParser and cloned per pin.
const ICONS = {
  barrier:
    '<path d="M3 9h18v5H3z"/><path d="M7 9l-3 5M12 9l-3 5M17 9l-3 5M21 9l-3 5"/><path d="M5 14v5M19 14v5"/>',
  car: '<path d="M4 15l1.5-5A2 2 0 0 1 7.4 8.5h9.2a2 2 0 0 1 1.9 1.5L20 15"/><rect x="3" y="15" width="18" height="4" rx="1"/><circle cx="7.5" cy="19" r="1.5"/><circle cx="16.5" cy="19" r="1.5"/>',
  pothole:
    '<ellipse cx="12" cy="14" rx="8" ry="4"/><path d="M8 13.5c1.5 1 6.5 1 8 0"/><path d="M5 8l2 2M19 8l-2 2M12 5v3"/>',
  cone: '<path d="M10 4h4l4 15H6z"/><path d="M8.5 10h7M7.5 14h9"/><path d="M4 19h16"/>',
  footpath:
    '<path d="M8 4c1.5 0 2 1.5 2 3s-1 3-2 3-2-1.5-2-3 .5-3 2-3zM16 12c1.5 0 2 1.5 2 3s-1 3-2 3-2-1.5-2-3 .5-3 2-3z"/><path d="M7 12v1M15 20v1"/>',
  warning: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
  check: '<path d="M5 12l4 4 10-10"/>',
  camera:
    '<rect x="8" y="18" width="48" height="34" rx="4"/><circle cx="32" cy="35" r="10"/><path d="M22 18 L26 11 L38 11 L42 18"/><path d="M10 54 L54 14"/>',
};
const iconCache = new Map();

function icon(name) {
  const key = Object.hasOwn(ICONS, name) ? name : "warning";
  if (!iconCache.has(key)) {
    const viewBox = key === "camera" ? "0 0 64 64" : "0 0 24 24";
    const markup = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" aria-hidden="true">${ICONS[key]}</svg>`;
    const svg = new DOMParser().parseFromString(markup, "image/svg+xml").documentElement;
    iconCache.set(key, document.importNode(svg, true));
  }
  return iconCache.get(key).cloneNode(true);
}

// --- Meta lookups (unknown values fall back as the contract says) ----------------------

function hazardOf(key) {
  return (
    state.hazards.get(key) ||
    state.hazards.get("other") || { key: "other", label: String(key), icon: "warning", is_hazard: true }
  );
}

function conditionOf(key) {
  return state.conditions.get(key) || state.conditions.get("grey") || { key: "grey", label: String(key) };
}

function statusLabel(key) {
  return state.statuses.get(key) || String(key);
}

function applyMeta(meta) {
  state.meta = meta;
  state.hazards = new Map(meta.hazard_types.map((t) => [t.key, t]));
  state.conditions = new Map(meta.conditions.map((c) => [c.key, c]));
  state.statuses = new Map(meta.verification_statuses.map((s) => [s.key, s.label]));
  // Condition colors: CSS uses var(--c-red) etc.; set them from meta so CSS follows the API.
  const root = document.documentElement.style;
  for (const c of meta.conditions) {
    if (/^[a-z_]+$/.test(c.key) && /^#[0-9a-f]{3,8}$/i.test(c.hex)) {
      root.setProperty(`--c-${c.key}`, c.hex);
    }
  }
}

// --- Status: loading / error / empty / truncated ---------------------------------------

let loadingTimer = null;

function setLoading(on) {
  clearTimeout(loadingTimer);
  // Wait a moment before showing it, so fast answers don't flash the indicator.
  if (on) loadingTimer = setTimeout(() => (el.loading.hidden = false), 150);
  else el.loading.hidden = true;
}

function friendlyMessage(err) {
  if (err instanceof ApiError) {
    if (err.code === "network_error") {
      return "Can't reach BikeAble right now. Check your connection, then try again.";
    }
    if (err.code === "timeout") return "The server is taking too long to answer. Try again in a moment.";
    return err.message || "Something went wrong. Please try again.";
  }
  console.error(err);
  return "Something went wrong on this page. Please try again.";
}

function showError(err, retry) {
  el.errorText.textContent = friendlyMessage(err);
  retryAction = retry;
  el.error.hidden = false;
  el.note.hidden = true;
}

function clearError() {
  el.error.hidden = true;
  retryAction = null;
}

el.retry.addEventListener("click", () => {
  const action = retryAction;
  clearError();
  if (action) action();
});

function renderNote(visibleCount) {
  const notes = [];
  if (visibleCount === 0) {
    notes.push(state.data.features.length ? "No reports match your layers." : "No reports here yet.");
  }
  if (state.data.truncated) notes.push("Showing the newest reports only. Zoom in to see all.");
  el.note.textContent = notes.join(" ");
  el.note.hidden = notes.length === 0;
}

// --- Map --------------------------------------------------------------------------------

function createMap() {
  const { center, zoom, bounds } = state.meta.map;
  const maxBounds = L.latLngBounds([bounds.min_lat, bounds.min_lng], [bounds.max_lat, bounds.max_lng]);

  // L.map takes [lat, lng]. maxBounds stops panning outside the demo area.
  map = L.map(el.map, { maxBounds, maxBoundsViscosity: 1, zoomControl: false }).setView(
    [center.lat, center.lng],
    zoom,
  );
  map.setMinZoom(map.getBoundsZoom(maxBounds, true));
  L.control.zoom({ position: "topright" }).addTo(map);
  L.tileLayer(TILE_LAYER.url, TILE_LAYER.options).addTo(map);

  // A Leaflet "layer" is anything drawn on the map. L.geoJSON is one layer holding many
  // markers; it reads GeoJSON [lng, lat] and converts to Leaflet's [lat, lng] for us.
  reportLayer = L.geoJSON(null, { pointToLayer, filter: isVisible }).addTo(map);

  map.on("moveend", () => {
    updateReportHere();
    scheduleReload();
  });
  map.on("click", () => closeDetail());
  updateReportHere();
}

// pointToLayer: L.geoJSON calls this once per Point feature to ask "what do I draw here?".
// We answer with a marker that uses our own HTML pin instead of Leaflet's default icon.
function pointToLayer(feature, latlng) {
  const p = feature.properties;
  const type = hazardOf(p.hazard_type);
  const condition = conditionOf(p.condition);
  const marker = L.marker(latlng, {
    icon: pinIcon(p, type, condition),
    keyboard: true, // focusable with Tab, Enter opens it
    title: type.label,
    riseOnHover: true,
  });
  marker.reportId = p.id;
  marker.on("click", () => openDetail(p.id));
  marker.on("add", () => {
    marker.getElement()?.setAttribute("aria-label", `${type.label}, ${condition.label}. Open report`);
  });
  return marker;
}

function pinIcon(p, type, condition) {
  const classes = ["pin"];
  if (!type.is_hazard) classes.push("is-info");
  if (p.is_synthetic) classes.push("is-synthetic");
  if (p.id === state.activeId) classes.push("is-active");
  if (!state.seenIds.has(p.id) && !reducedMotion.matches) classes.push("pin-drop");

  const pin = h("div", { class: classes.join(" "), "data-cond": condition.key });
  pin.style.setProperty("--c", `var(--c-${condition.key})`);
  const weight = Number(p.freshness_weight ?? 1);
  pin.style.opacity = String(Math.min(1, Math.max(MIN_PIN_OPACITY, weight)));
  pin.append(h("div", { class: "pin__head" }, icon(type.icon)));

  return L.divIcon({ className: "pin-icon", html: pin, iconSize: [36, 44], iconAnchor: [18, 42] });
}

// filter: L.geoJSON skips features for which this returns false (layer checkboxes).
function isVisible(feature) {
  const p = feature.properties;
  if (!state.showDemo && p.is_synthetic) return false;
  return !state.hiddenTypes.has(hazardOf(p.hazard_type).key);
}

function drawReports() {
  if (!state.data) return;
  reportLayer.clearLayers();
  reportLayer.addData(state.data);
  const visible = state.data.features.filter(isVisible);
  for (const f of visible) state.seenIds.add(f.properties.id);
  renderSummary(visible);
  renderNote(visible.length);
}

// Debounce: moveend fires after every drag/zoom. Wait until the map has been still for
// RELOAD_DEBOUNCE_MS, then load once, instead of sending a request per tiny move.
let reloadTimer = null;
function scheduleReload() {
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(loadReports, RELOAD_DEBOUNCE_MS);
}

async function loadReports() {
  const seq = ++state.reportsSeq;
  setLoading(true);
  try {
    const data = await getReports({
      bbox: map.getBounds().toBBoxString(), // already minLng,minLat,maxLng,maxLat
      includeResolved: state.includeResolved,
    });
    if (seq !== state.reportsSeq) return; // a newer request is on its way: drop this answer
    state.data = data;
    clearError();
    drawReports();
  } catch (err) {
    if (seq !== state.reportsSeq) return;
    showError(err, loadReports);
  } finally {
    if (seq === state.reportsSeq) setLoading(false);
  }
}

function updateReportHere() {
  const c = map.getCenter();
  const params = new URLSearchParams({ lat: c.lat.toFixed(6), lng: c.lng.toFixed(6) });
  el.reportHere.href = `${el.reportHere.dataset.base}?${params}`;
}

// --- Summary card + legend --------------------------------------------------------------

function renderSummary(visible) {
  const counts = new Map();
  for (const f of visible) {
    const key = conditionOf(f.properties.condition).key;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const rows = state.meta.conditions.map((c) => {
    const sw = h("span", { class: "sw", "aria-hidden": "true" });
    sw.style.setProperty("--c", `var(--c-${c.key})`);
    return h("li", {}, sw, h("span", {}, c.label), h("b", {}, String(counts.get(c.key) || 0)));
  });
  el.summaryRows.replaceChildren(...rows);
  const demo = visible.filter((f) => f.properties.is_synthetic).length;
  el.summaryDemo.textContent = demo ? `${demo} of ${visible.length} demo data` : "";
  el.summary.hidden = false;
}

function keyItems() {
  return state.meta.conditions.map((c) => {
    const sw = h("span", { class: "sw", "aria-hidden": "true" });
    sw.style.setProperty("--c", `var(--c-${c.key})`);
    return h("li", { title: c.meaning || "" }, sw, c.label);
  });
}

// --- Layers panel -----------------------------------------------------------------------

const CHECK_MARK = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M4 11 L8 15 L16 4"/></svg>';

function checkBox(id, checked, label, onChange) {
  const input = h("input", { type: "checkbox", id, checked });
  input.addEventListener("change", () => onChange(input.checked));
  const box = h("span", { class: "box", "aria-hidden": "true" });
  box.append(new DOMParser().parseFromString(CHECK_MARK, "image/svg+xml").documentElement);
  return h("label", { class: "check", for: id }, input, box, label);
}

function buildLayers() {
  for (const t of state.meta.hazard_types) {
    if (t.key === "none") continue; // "no hazard found" isn't a layer
    el.layerTypes.append(
      checkBox(`layer-${t.key}`, !state.hiddenTypes.has(t.key), t.label, (on) => {
        if (on) state.hiddenTypes.delete(t.key);
        else state.hiddenTypes.add(t.key);
        drawReports();
      }),
    );
  }
  el.layersKey.replaceChildren(...keyItems());
  el.legendKey.replaceChildren(...keyItems());
  el.layersBtn.disabled = false;
}

el.showResolved.addEventListener("change", () => {
  state.includeResolved = el.showResolved.checked;
  loadReports(); // include_resolved is a server-side filter
});
el.showDemo.addEventListener("change", () => {
  state.showDemo = el.showDemo.checked;
  drawReports();
});

function toggleLayers(open = el.layers.hidden) {
  el.layers.hidden = !open;
  el.layersBtn.setAttribute("aria-expanded", String(open));
}
el.layersBtn.addEventListener("click", () => toggleLayers());

// --- Report detail sheet ----------------------------------------------------------------

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const UNITS = [
  ["year", 31536000],
  ["month", 2592000],
  ["week", 604800],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

function timeAgo(iso) {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "unknown";
  const seconds = (time - Date.now()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

function timeEl(iso) {
  const date = new Date(iso);
  const title = Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
  return h("time", { datetime: iso, title }, timeAgo(iso));
}

function renderPhoto(url, label) {
  const placeholder = () =>
    el.detailPhoto.replaceChildren(h("div", { class: "no-photo" }, icon("camera"), h("span", {}, "No photo")));
  if (!url) return placeholder();
  const img = h("img", { src: url, alt: `Photo of: ${label}` });
  img.addEventListener("error", placeholder, { once: true });
  el.detailPhoto.replaceChildren(img);
}

function renderDetail(r) {
  const type = hazardOf(r.hazard_type);
  const condition = conditionOf(r.condition);

  renderPhoto(r.photo_url, type.label);

  const condChip = h("span", { class: "chip chip--cond", "data-cond": condition.key }, condition.label);
  condChip.style.setProperty("--c", `var(--c-${condition.key})`);
  const chips = [condChip, h("span", { class: "chip" }, statusLabel(r.verification_status))];
  // ai_flagged's own label already says "needs review"; don't show it twice.
  if (r.needs_review && r.verification_status !== "ai_flagged") {
    chips.push(h("span", { class: "chip chip--warn" }, "Needs review"));
  }
  if (r.is_synthetic) chips.push(h("span", { class: "chip chip--demo" }, "Demo data"));
  el.detailChips.replaceChildren(...chips);

  el.detailTitle.textContent = type.label;
  el.detailDesc.textContent = r.description || "";
  el.detailNote.textContent = r.note ? `“${r.note}”` : "";

  const confidence = r.ai_confidence == null ? "Not analysed" : `${Math.round(r.ai_confidence * 100)}%`;
  el.detailFacts.replaceChildren(
    h("dt", {}, "Reported"),
    h("dd", {}, timeEl(r.created_at)),
    h("dt", {}, "Last seen"),
    h("dd", {}, timeEl(r.last_confirmed_at)),
    h("dt", {}, "AI sure"),
    h("dd", {}, confidence),
  );

  // Rendered now, wired in feat/report-feedback (E6).
  const counts = r.feedback_counts || {};
  el.detailActions.replaceChildren(
    ...state.meta.feedback_actions.map((a) =>
      h(
        "button",
        { type: "button", class: "fb-btn", disabled: true, title: "coming soon", "data-action": a.key },
        h("b", {}, String(counts[a.key] ?? 0)),
        a.label,
      ),
    ),
  );
}

function renderDetailSkeleton() {
  el.detailPhoto.replaceChildren();
  el.detailChips.replaceChildren(h("span", { class: "skeleton", style: "width: 8rem" }));
  el.detailTitle.textContent = "Loading report…";
  el.detailDesc.replaceChildren(h("span", { class: "skeleton" }));
  el.detailNote.textContent = "";
  el.detailFacts.replaceChildren();
  el.detailActions.replaceChildren();
}

function setActivePin(id) {
  state.activeId = id;
  reportLayer.eachLayer((marker) => {
    marker.getElement()?.querySelector(".pin")?.classList.toggle("is-active", marker.reportId === id);
  });
}

function markerElement(id) {
  let found = null;
  reportLayer?.eachLayer((marker) => {
    if (marker.reportId === id) found = marker.getElement();
  });
  return found;
}

async function openDetail(id) {
  const wasOpen = !el.detail.hidden;
  setActivePin(id);
  toggleLayers(false);
  el.detailMsg.textContent = "";

  // Show what we already have from the list right away, then refresh from E4.
  const fromList = state.data?.features.find((f) => f.properties.id === id)?.properties;
  if (fromList) renderDetail(fromList);
  else renderDetailSkeleton();

  el.detail.classList.remove("is-closing");
  el.detail.style.translate = "";
  el.detail.hidden = false;
  if (!wasOpen) el.detailClose.focus();

  const seq = ++state.detailSeq;
  el.detail.setAttribute("aria-busy", "true");
  try {
    const report = await getReport(id);
    if (seq !== state.detailSeq) return;
    renderDetail(report);
  } catch (err) {
    if (seq !== state.detailSeq) return;
    if (err instanceof ApiError && err.code === "not_found") {
      el.detailMsg.textContent = "This report no longer exists.";
    } else {
      el.detailMsg.textContent = `${friendlyMessage(err)} Showing what the map already knows.`;
      if (!fromList) el.detailTitle.textContent = "Couldn't load this report";
    }
  } finally {
    if (seq === state.detailSeq) el.detail.removeAttribute("aria-busy");
  }
}

function closeDetail() {
  if (el.detail.hidden) return;
  const id = state.activeId;
  state.detailSeq++; // ignore a detail answer that arrives after closing
  setActivePin(null);

  const finish = () => {
    el.detail.hidden = true;
    el.detail.classList.remove("is-closing");
    el.detail.style.translate = "";
  };
  if (reducedMotion.matches) finish();
  else {
    el.detail.classList.add("is-closing");
    el.detail.addEventListener("animationend", finish, { once: true });
  }

  // Focus goes back to the pin that opened the sheet (or the map if it was redrawn away).
  const pin = markerElement(id);
  (pin || el.map).focus({ preventScroll: true });
}

el.detailClose.addEventListener("click", closeDetail);

// Swipe down on the grip to close (phones).
let dragStartY = null;
el.detailGrip.addEventListener("pointerdown", (e) => {
  dragStartY = e.clientY;
  el.detailGrip.setPointerCapture(e.pointerId);
});
el.detailGrip.addEventListener("pointermove", (e) => {
  if (dragStartY === null) return;
  el.detail.style.translate = `0 ${Math.max(0, e.clientY - dragStartY)}px`;
});
const endDrag = (e) => {
  if (dragStartY === null) return;
  const distance = e.clientY - dragStartY;
  dragStartY = null;
  if (distance > 80) closeDetail();
  else el.detail.style.translate = "";
};
el.detailGrip.addEventListener("pointerup", endDrag);
el.detailGrip.addEventListener("pointercancel", endDrag);

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!el.layers.hidden) {
    toggleLayers(false);
    el.layersBtn.focus();
  } else {
    closeDetail();
  }
});

// --- Start ------------------------------------------------------------------------------

async function init() {
  setLoading(true);
  let meta;
  try {
    meta = await getMeta();
  } catch (err) {
    setLoading(false);
    showError(err, init);
    return;
  }
  applyMeta(meta);
  createMap();
  buildLayers();
  loadReports();
}

init();
