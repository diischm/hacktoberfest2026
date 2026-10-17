// Landing page ("/"): the scrapbook collage from the design mockup (docs/design/mockup.html).
// Intro loader, pieces settling onto the board, a live "today on the map" receipt (E3), the
// best route of the day (E8/E9), a self-ticking checklist, Organize (tidy/scatter) and drag.
// Labels and condition colors come only from GET /api/meta/ (E2), never from this file.
// API data is always inserted with textContent / text nodes, never as HTML.

import { compareRoutes, getMeta, getReports, getScenarios } from "./api.js";

const INTRO_KEY = "bikeable-intro-seen";
const INTRO_LINES = ["Pumping the tyres", "Checking the bike lanes", "Asking riders what they saw"];
const INTRO_MS = 1800; // one ride across the strip; tap anywhere to skip
const COUNT_UP_MS = 900;

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

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

function sessionGet(key) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function sessionSet(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // private mode / blocked storage: the intro just plays again next time
  }
}

// --- Intro loader -----------------------------------------------------------------------------

const loader = $("#loader");
const landing = $("#landing");

function playIntro() {
  return new Promise((resolve) => {
    loader.hidden = false;
    loader.classList.remove("is-leaving");
    const msg = $("#loader-msg");
    let line = 0;
    msg.textContent = INTRO_LINES[0];
    const ticker = setInterval(() => {
      line = (line + 1) % INTRO_LINES.length;
      msg.textContent = INTRO_LINES[line];
    }, 600);

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearInterval(ticker);
      clearTimeout(timer);
      loader.removeEventListener("click", finish);
      loader.classList.add("is-leaving");
      setTimeout(() => {
        loader.hidden = true;
      }, 500);
      resolve();
    };
    const timer = setTimeout(finish, INTRO_MS);
    loader.addEventListener("click", finish); // never blocks: one tap skips it
  });
}

// Re-run the pieces' "settle onto the board" entrance and the checklist ticks.
function replayEntrance() {
  landing.classList.remove("is-entering");
  void landing.offsetWidth; // restart the CSS animations
  landing.classList.add("is-entering");
  clearTimeout(replayEntrance.timer);
  replayEntrance.timer = setTimeout(() => landing.classList.remove("is-entering"), 1800);
  tickChecklist();
}

// --- Checklist --------------------------------------------------------------------------------

function tickChecklist() {
  const items = $$("#checklist li");
  items.forEach((li, i) => li.classList.toggle("is-done", i < 2));
  if (reduced) {
    items.forEach((li) => li.classList.add("is-done"));
    return;
  }
  items.slice(2).forEach((li, i) => setTimeout(() => li.classList.add("is-done"), 1200 + i * 700));
}

// --- Receipt: today on the map (E3) -----------------------------------------------------------

function countUp(node, target) {
  const final = String(target).padStart(2, "0");
  if (reduced || target === 0) {
    node.textContent = final;
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / COUNT_UP_MS);
    const eased = 1 - (1 - t) ** 3;
    node.textContent = String(Math.round(target * eased)).padStart(2, "0");
    if (t < 1) requestAnimationFrame(step);
    else node.textContent = final;
  };
  requestAnimationFrame(step);
}

function renderReceipt(meta, reports) {
  const conditions = new Map(meta.conditions.map((c) => [c.key, c]));
  const hazards = new Map(meta.hazard_types.map((t) => [t.key, t]));
  const features = reports.features;
  const count = (fn) => features.filter(fn).length;
  const byCondition = (key) => count((f) => f.properties.condition === key);
  const label = (key, fallback) => conditions.get(key)?.label || fallback;

  const rows = [
    ["Active reports", features.length, null],
    [label("red", "Hazard"), byCondition("red"), "red"],
    [label("amber", "Caution"), byCondition("amber"), "amber"],
    [label("grey", "Unknown"), byCondition("grey"), "grey"],
    [
      hazards.get("informal_shortcut")?.label || "Informal shortcut path",
      count((f) => f.properties.hazard_type === "informal_shortcut"),
      "green",
    ],
    [
      "Rider confirmations",
      features.reduce((sum, f) => sum + (f.properties.feedback_counts?.still_there || 0), 0),
      null,
    ],
  ];

  const numbers = [];
  $("#receipt-rows").replaceChildren(
    ...rows.map(([text, n, condition]) => {
      const swatch = condition ? h("span", { class: "sw" }) : null;
      if (swatch) swatch.style.background = `var(--c-${condition})`;
      const b = h("b", {}, "00");
      numbers.push([b, n]);
      return h("li", {}, swatch, h("span", {}, text), b);
    }),
  );
  numbers.forEach(([node, n]) => countUp(node, n));

  const demo = count((f) => f.properties.is_synthetic);
  $("#receipt-demo").textContent = demo ? `${demo} of ${features.length} are demo data.` : "";
  if (reports.truncated) $("#receipt-demo").textContent += " Showing the newest 500.";
}

function renderDate() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  $("#receipt-date").textContent = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

function applyConditionColors(meta) {
  const root = document.documentElement.style;
  for (const c of meta.conditions) {
    if (/^[a-z_]+$/.test(c.key) && /^#[0-9a-f]{3,8}$/i.test(c.hex)) {
      root.setProperty(`--c-${c.key}`, c.hex);
    }
  }
}

async function loadReceipt() {
  try {
    const [meta, reports] = await Promise.all([getMeta(), getReports()]);
    applyConditionColors(meta);
    renderReceipt(meta, reports);
  } catch {
    $("#receipt-rows").replaceChildren(h("li", {}, h("span", {}, "Couldn't load today's reports")));
    $("#receipt-demo").textContent = "The live map may still work, give it a try.";
  }
}

// --- Ticket: best route today (E8 + E9) -------------------------------------------------------

async function loadTicket() {
  try {
    const { scenarios } = await getScenarios();
    if (!scenarios.length) throw new Error("no scenarios");
    const cmp = await compareRoutes(scenarios[0].id);
    const best = cmp.routes.find((r) => r.id === cmp.recommended_route_id) || cmp.routes[0];
    $("#ticket-route").textContent = cmp.scenario.name;
    $("#ticket-meta").textContent =
      `Take “${best.name}” · score ${best.score}/100 · ${(best.length_m / 1000).toFixed(1)} km`;
  } catch {
    $("#ticket-meta").textContent = "Compare two ways across town";
  }
}

// --- Organize (tidy / scatter, FLIP animation) and drag ---------------------------------------

const collage = $("#collage");
const organizeBtn = $("#organize-btn");

organizeBtn.addEventListener("click", () => {
  const pieces = $$("[data-piece]", collage);
  const first = new Map(pieces.map((p) => [p, p.getBoundingClientRect()]));
  pieces.forEach((p) => {
    p.style.translate = "";
  });
  const tidy = collage.classList.toggle("is-tidy");
  organizeBtn.setAttribute("aria-pressed", String(tidy));
  $("span", organizeBtn).textContent = tidy ? "Scatter" : "Organize";
  if (reduced) return;
  for (const p of pieces) {
    const a = first.get(p);
    const b = p.getBoundingClientRect();
    const dx = a.left - b.left;
    const dy = a.top - b.top;
    if (!dx && !dy) continue;
    p.animate([{ translate: `${dx}px ${dy}px` }, { translate: "0 0" }], {
      duration: 560,
      easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    });
  }
});

// Drag pieces around the board (mouse / pen only, so phones keep normal scrolling).
if (window.matchMedia("(pointer: fine)").matches) {
  for (const piece of $$("[data-piece]", collage)) {
    piece.classList.add("is-draggable");
    let startX = 0;
    let startY = 0;
    let originX = 0;
    let originY = 0;
    let moved = false;
    piece.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("a, button") && !piece.matches("a")) return;
      const current = (piece.style.translate || "0px 0px").split(" ").map(parseFloat);
      [originX, originY] = [current[0] || 0, current[1] || 0];
      startX = e.clientX;
      startY = e.clientY;
      moved = false;
      piece.setPointerCapture(e.pointerId);
    });
    piece.addEventListener("pointermove", (e) => {
      if (!piece.hasPointerCapture(e.pointerId)) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < 6) return;
      moved = true;
      piece.classList.add("is-dragging");
      piece.style.translate = `${originX + dx}px ${originY + dy}px`;
    });
    const end = (e) => {
      if (piece.hasPointerCapture(e.pointerId)) piece.releasePointerCapture(e.pointerId);
      piece.classList.remove("is-dragging");
    };
    piece.addEventListener("pointerup", end);
    piece.addEventListener("pointercancel", end);
    // A drag that ends on a link must not follow it.
    piece.addEventListener(
      "click",
      (e) => {
        if (moved) {
          e.preventDefault();
          e.stopPropagation();
          moved = false;
        }
      },
      true,
    );
  }
}

// --- Start ------------------------------------------------------------------------------------

$("#replay-btn").addEventListener("click", async () => {
  if (!reduced) await playIntro();
  replayEntrance();
});

async function init() {
  renderDate();
  // Data loads while the intro plays; the page fills in as it arrives (never waits on it).
  loadReceipt();
  loadTicket();
  if (!loader.hidden) {
    landing.classList.remove("is-entering");
    await playIntro();
    sessionSet(INTRO_KEY, "1");
  } else if (!sessionGet(INTRO_KEY)) {
    sessionSet(INTRO_KEY, "1");
  }
  replayEntrance();
}

init();
