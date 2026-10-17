// Where api.js gets its data from, per endpoint.
//   "mock" = read web/static/web/mock/*.json (no backend needed)
//   "live" = call the real backend at /api/...
// Flip a key to "live" only after backend announces that milestone (docs/plan/WORKFLOW.md).
export const API_MODE = {
  meta: "live", // M1
  reports: "live", // M1
  reportDetail: "live", // M1
  createReport: "live", // M2
  feedback: "mock", // M3
  segments: "live", // existing bike lanes from OpenStreetMap (E7)
  bikeParking: "live", // existing bicycle parking from OpenStreetMap (E10)
  scenarios: "live", // M4: demo trips (E8)
  compare: "live", // M4: scored routes (E9)
};

export const API_BASE = "/api";

// Mock POSTs wait this long so loading states can be seen and tested.
export const MOCK_DELAY_MS = 2000;

// Make every mock call fail, to build error UI. null = normal mock data.
// One of: null, "ai_rate_limited", "validation_error", "not_found",
// "duplicate_feedback", "server_error", "timeout", "network_error".
export const MOCK_FORCE_ERROR = null;

// Mock files live next to this file: /static/web/js/config.js -> /static/web/mock/.
export const MOCK_BASE = new URL("../mock/", import.meta.url).pathname;

// Map background tiles. Swap the whole object to change provider.
// referrerPolicy: Django sends "Referrer-Policy: same-origin", which strips the Referer
// header from tile requests; OSM's tile policy requires it and answers 403 without it.
export const TILE_LAYER = {
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  options: {
    maxZoom: 19,
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
};

// Cycling basemap (CyclOSM): the same OSM data rendered for bikes — cycleways, paths and
// bicycle parking are drawn on the tiles. Offered as a second choice in the Layers panel.
export const CYCLE_TILE_LAYER = {
  url: "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
  options: {
    maxZoom: 20,
    subdomains: "abc",
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="https://www.cyclosm.org">CyclOSM</a>',
  },
};

export const TIMEOUT_MS = 10_000;
export const UPLOAD_TIMEOUT_MS = 30_000; // E5 runs the AI inside the request (~15 s)
