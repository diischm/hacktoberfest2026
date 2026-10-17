// Routes page ("/routes/"): demo trips from E8 as tabs, scored alternatives from E9 drawn on
// a map and listed as tickets. Hazard pins come from E3 (only the ids in hazards_on_route).
// Labels and condition colors come only from GET /api/meta/ (E2), never from this file.
// API data is always inserted with textContent / text nodes, never as HTML.

import { ApiError, compareRoutes, getMeta, getReports, getScenarios } from "./api.js";
import { API_MODE, TILE_LAYER } from "./config.js";
import { icon } from "./icons.js";

const L = window.L; // Leaflet, loaded by a classic <script> before this module runs

const BEST_STYLE = { weight: 8, opacity: 0.95, dashArray: null };
const OTHER_STYLE = { weight: 5, opacity: 0.85, dashArray: "10 9" };
const MIN_PIN_OPACITY = 0.55;

const $ = (selector) => document.querySelector(selector);

const el = {
  tabs: $("#scenario-tabs"),
  tickets: $("#route-tickets"),
  loading: $("#routes-loading"),
  error: $("#routes-error"),
  errorText: $("#routes-error-text"),
  retry: $("#routes-retry"),
  demo: $("#routes-demo"),
};

const state = {
  conditions: new Map(),
  hazards: new Map(),
  scenarios: [],
  activeScenario: null,
  reports: new Map(), // report id -> GeoJSON feature (E3)
  lines: new Map(), // route id -> L.GeoJSON
  requestId: 0,
};

let map = null;
let routeLayer = null;
let retryAction = null;

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

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// --- Meta (unknown values fall back as the contract says) ---------------------------------

function conditionOf(key) {
  return state.conditions.get(key) || state.conditions.get("grey") || { key: "grey", label: String(key) };
}

function hazardOf(key) {
  return (
    state.hazards.get(key) ||
    state.hazards.get("other") || { key: "other", label: String(key), icon: "warning", is_hazard: true }
  );
}

function applyMeta(meta) {
  state.conditions = new Map(meta.conditions.map((c) => [c.key, c]));
  state.hazards = new Map(meta.hazard_types.map((t) => [t.key, t]));
  const root = document.documentElement.style;
  for (const c of meta.conditions) {
    if (/^[a-z_]+$/.test(c.key) && /^#[0-9a-f]{3,8}$/i.test(c.hex)) {
      root.setProperty(`--c-${c.key}`, c.hex);
    }
  }
}

// Line color for a condition: the hex from meta (Leaflet's SVG stroke needs a real color).
function lineColor(conditionKey) {
  return conditionOf(conditionKey).hex || cssVar("--c-grey");
}

// --- Status -----------------------------------------------------------------------------------

function friendlyMessage(err) {
  if (err instanceof ApiError) {
    if (err.code === "network_error") {
      return "Can't reach BikeAble right now. Check your connection, then try again.";
    }
    if (err.code === "timeout") return "The server is taking too long to answer. Try again in a moment.";
    if (err.code === "not_found") return "This trip doesn't exist any more. Pick another one.";
    return err.message || "Something went wrong. Please try again.";
  }
  console.error(err);
  return "Something went wrong on this page. Please try again.";
}

function setLoading(on) {
  if (on) el.tickets.replaceChildren(el.loading);
  el.loading.hidden = !on;
}

function showError(err, retry) {
  setLoading(false);
  el.tickets.replaceChildren();
  el.errorText.textContent = friendlyMessage(err);
  retryAction = retry;
  el.error.hidden = false;
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

// --- Map --------------------------------------------------------------------------------------

function createMap(meta) {
  const { center, zoom } = meta.map;
  map = L.map("routes-map", { scrollWheelZoom: false, zoomControl: true }).setView(
    [center.lat, center.lng], // plain object -> Leaflet [lat, lng]
    zoom,
  );
  L.tileLayer(TILE_LAYER.url, TILE_LAYER.options).addTo(map);
  routeLayer = L.layerGroup().addTo(map);
}

function endpointMarker(point, label) {
  return L.circleMarker([point.lat, point.lng], {
    radius: 8,
    color: cssVar("--ink"),
    weight: 3,
    fillColor: cssVar("--paper"),
    fillOpacity: 1,
  }).bindTooltip(label, { permanent: true, direction: "top", offset: [0, -8], className: "route-end" });
}

function hazardPin(feature) {
  const p = feature.properties;
  const type = hazardOf(p.hazard_type);
  const condition = conditionOf(p.condition);
  const classes = ["pin"];
  if (!type.is_hazard) classes.push("is-info");
  if (p.is_synthetic) classes.push("is-synthetic");
  const pin = h("div", { class: classes.join(" "), "data-cond": condition.key });
  pin.style.setProperty("--c", `var(--c-${condition.key})`);
  pin.style.opacity = String(Math.min(1, Math.max(MIN_PIN_OPACITY, Number(p.freshness_weight ?? 1))));
  pin.append(h("div", { class: "pin__head" }, icon(type.icon)));

  const [lng, lat] = feature.geometry.coordinates; // GeoJSON order is [lng, lat]
  const marker = L.marker([lat, lng], {
    icon: L.divIcon({ className: "pin-icon", html: pin, iconSize: [36, 44], iconAnchor: [18, 42] }),
    title: `${type.label} (${condition.label})`,
    keyboard: true,
    riseOnHover: true,
  });
  // Tapping a pin opens the report on the main map.
  marker.on("click", () => {
    window.location.href = `/map/?report=${encodeURIComponent(p.id)}`;
  });
  return marker;
}

function drawRoutes(cmp) {
  routeLayer.clearLayers();
  state.lines.clear();
  const all = L.featureGroup();

  // Recommended route drawn last so it sits on top.
  const ordered = [...cmp.routes].sort(
    (a, b) => (a.id === cmp.recommended_route_id) - (b.id === cmp.recommended_route_id),
  );
  for (const route of ordered) {
    const best = route.id === cmp.recommended_route_id;
    const color = lineColor(route.condition);
    // White-ish casing under each line keeps it readable over busy streets.
    const casing = L.geoJSON(route.geometry, {
      style: { color: cssVar("--paper"), weight: (best ? BEST_STYLE : OTHER_STYLE).weight + 5, opacity: 0.9 },
      interactive: false,
    });
    const line = L.geoJSON(route.geometry, {
      style: { color, lineCap: "round", lineJoin: "round", ...(best ? BEST_STYLE : OTHER_STYLE) },
    });
    line.on("click", () => selectRoute(route.id, { scroll: true }));
    line.casing = casing;
    casing.addTo(routeLayer);
    line.addTo(routeLayer).addTo(all);
    state.lines.set(route.id, line);
  }

  const seen = new Set();
  for (const route of cmp.routes) {
    for (const id of route.hazards_on_route) {
      const feature = state.reports.get(id);
      if (feature && !seen.has(id)) {
        seen.add(id);
        hazardPin(feature).addTo(routeLayer);
      }
    }
  }

  endpointMarker(cmp.scenario.from, cmp.scenario.from.name).addTo(routeLayer);
  endpointMarker(cmp.scenario.to, cmp.scenario.to.name).addTo(routeLayer);
  map.invalidateSize();
  if (all.getLayers().length) map.fitBounds(all.getBounds().pad(0.2));
}

// Highlight one route (map + ticket); the others fade back.
function selectRoute(routeId, { scroll = false } = {}) {
  for (const [id, line] of state.lines) {
    const active = id === routeId;
    line.setStyle(active ? BEST_STYLE : { ...OTHER_STYLE, opacity: 0.6 });
    line.casing.setStyle({ weight: (active ? BEST_STYLE : OTHER_STYLE).weight + 5 });
    if (active) {
      line.casing.bringToFront();
      line.bringToFront();
    }
  }
  for (const ticket of el.tickets.querySelectorAll(".route-ticket")) {
    const active = ticket.dataset.id === routeId;
    ticket.classList.toggle("is-active", active);
    ticket.setAttribute("aria-pressed", String(active));
    if (active && scroll) ticket.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// --- Tickets ----------------------------------------------------------------------------------

function ticket(route, index, recommendedId) {
  const best = route.id === recommendedId;
  const condition = conditionOf(route.condition);
  const reportCount = route.hazards_on_route.length;
  const meta = [
    `${(route.length_m / 1000).toFixed(2)} KM`,
    `${reportCount} REPORT${reportCount === 1 ? "" : "S"}`,
  ].join(" · ");
  const chip = h("span", { class: "chip chip--cond", "data-cond": condition.key }, condition.label);
  chip.style.setProperty("--c", `var(--c-${condition.key})`);

  const node = h(
    "button",
    {
      type: "button",
      class: `route-ticket${best ? " is-active" : ""}`,
      "data-id": route.id,
      "aria-pressed": String(best),
    },
    best ? h("span", { class: "stamp" }, "RECOMMENDED") : null,
    h("span", { class: "route-ticket__name" }, route.name),
    h(
      "span",
      { class: "route-ticket__meta" },
      chip,
      meta,
    ),
    h("ul", {}, route.explanation.map((line) => h("li", {}, line))),
    h(
      "span",
      { class: "route-ticket__score", "aria-label": `Score ${route.score} out of 100` },
      h("b", {}, String(route.score)),
      h("small", {}, "/ 100"),
    ),
  );
  node.style.setProperty("--c", `var(--c-${condition.key})`);
  node.style.setProperty("--i", String(index));
  node.style.setProperty("--r", `${index % 2 ? 0.8 : -0.8}deg`);
  node.addEventListener("click", () => {
    selectRoute(route.id);
    const line = state.lines.get(route.id);
    if (line) map.fitBounds(line.getBounds().pad(0.2));
    document.querySelector(".routes__map").scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  return node;
}

function renderTickets(cmp) {
  setLoading(false);
  if (!cmp.routes.length) {
    el.tickets.replaceChildren(h("p", { class: "routes__status" }, "No routes for this trip yet."));
    return;
  }
  el.tickets.replaceChildren(...cmp.routes.map((r, i) => ticket(r, i, cmp.recommended_route_id)));
}

function renderDemoNote(cmp) {
  const usesMock = API_MODE.scenarios === "mock" || API_MODE.compare === "mock";
  const synthetic = cmp.routes.some((r) =>
    r.hazards_on_route.some((id) => state.reports.get(id)?.properties.is_synthetic),
  );
  el.demo.hidden = !(usesMock || synthetic);
}

// --- Loading ----------------------------------------------------------------------------------

function renderTabs() {
  el.tabs.replaceChildren(
    ...state.scenarios.map((s) => {
      const tab = h(
        "button",
        {
          type: "button",
          role: "tab",
          "aria-selected": String(s.id === state.activeScenario),
          "data-id": s.id,
        },
        s.name,
      );
      tab.addEventListener("click", () => loadScenario(s.id));
      return tab;
    }),
  );
}

async function loadScenario(id) {
  state.activeScenario = id;
  for (const tab of el.tabs.querySelectorAll("button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.id === id));
  }
  clearError();
  setLoading(true);
  const requestId = ++state.requestId;
  try {
    const cmp = await compareRoutes(id);
    if (requestId !== state.requestId) return; // a newer tab click won
    drawRoutes(cmp);
    renderTickets(cmp);
    renderDemoNote(cmp);
  } catch (err) {
    if (requestId === state.requestId) showError(err, () => loadScenario(id));
  }
}

async function loadReports() {
  // Hazard pins are a nice-to-have: the page still works if E3 fails.
  try {
    const data = await getReports();
    state.reports = new Map(data.features.map((f) => [f.id, f]));
  } catch (err) {
    console.warn("Could not load hazard pins", err);
  }
}

async function init() {
  clearError();
  setLoading(true);
  try {
    const [meta, scenarios] = await Promise.all([getMeta(), getScenarios(), loadReports()]);
    applyMeta(meta);
    if (!map) createMap(meta);
    state.scenarios = scenarios.scenarios;
  } catch (err) {
    showError(err, init);
    return;
  }
  if (!state.scenarios.length) {
    setLoading(false);
    el.tickets.replaceChildren(h("p", { class: "routes__status" }, "No demo trips yet. Check back soon."));
    return;
  }
  state.activeScenario = state.activeScenario || state.scenarios[0].id;
  renderTabs();
  await loadScenario(state.activeScenario);
}

init();
