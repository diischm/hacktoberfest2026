// The only place the frontend talks to the backend. One function per contract endpoint
// (docs/plan/API_CONTRACT.md, E2-E9). Each returns the parsed JSON or throws an ApiError.
// Whether a function reads a mock file or calls /api/ is decided by API_MODE in config.js.

import {
  API_BASE,
  API_MODE,
  MOCK_BASE,
  MOCK_DELAY_MS,
  MOCK_FORCE_ERROR,
  TIMEOUT_MS,
  UPLOAD_TIMEOUT_MS,
} from "./config.js";

// Error codes from the contract's error table. Anything else from the server -> unknown_error.
const KNOWN_CODES = new Set([
  "validation_error",
  "invalid_bbox",
  "csrf_failed",
  "not_found",
  "method_not_allowed",
  "duplicate_feedback",
  "photo_too_large",
  "unsupported_photo_type",
  "ai_rate_limited",
  "server_error",
]);

export class ApiError extends Error {
  // status 0 = no HTTP response at all (timeout, offline).
  constructor(code, message, { status = 0, fields = {}, retryAfterSeconds = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.fields = fields;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

// Debug-only overrides used by /dev/api/. Pages never call these.
const mockOptions = { forceError: MOCK_FORCE_ERROR, delayMs: MOCK_DELAY_MS };
export function setMockOptions(options) {
  Object.assign(mockOptions, options);
}

// --- Endpoints ------------------------------------------------------------------------

// E2: labels, colors, upload limits, map center. Load once at startup.
export function getMeta() {
  return request("meta", { path: "/meta/", mockFile: "meta.json" });
}

// E3: GeoJSON FeatureCollection of report points.
// bbox: Leaflet's map.getBounds().toBBoxString(), or [minLng, minLat, maxLng, maxLat].
export function getReports({ bbox, includeResolved } = {}) {
  const query = {};
  if (bbox != null) query.bbox = Array.isArray(bbox) ? bbox.join(",") : bbox;
  if (includeResolved != null) query.include_resolved = includeResolved ? "true" : "false";
  return request("reports", { path: "/reports/", query, mockFile: "reports.json" });
}

// E4: one report (flat object with lat/lng).
export function getReport(id) {
  return request("reportDetail", {
    path: `/reports/${encodeURIComponent(id)}/`,
    mock: () => mockReport(id),
  });
}

// E5: formData with photo, lat, lng and optional note. Slow: the AI runs in the request.
export function createReport(formData) {
  return request("createReport", {
    path: "/reports/",
    method: "POST",
    body: formData,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    mockFile: "report-create.json",
  });
}

// E6: action is "still_there" | "resolved" | "dispute". Returns the updated report.
export function sendFeedback(id, action) {
  return request("feedback", {
    path: `/reports/${encodeURIComponent(id)}/feedback/`,
    method: "POST",
    json: { action },
    mockFile: "report-feedback.json",
  });
}

// E7: GeoJSON FeatureCollection of LineString segments.
export function getSegments({ bbox } = {}) {
  const query = {};
  if (bbox != null) query.bbox = Array.isArray(bbox) ? bbox.join(",") : bbox;
  return request("segments", { path: "/segments/", query, mockFile: "segments.json" });
}

// E10: GeoJSON FeatureCollection of bicycle-parking Points.
export function getBikeParking({ bbox } = {}) {
  const query = {};
  if (bbox != null) query.bbox = Array.isArray(bbox) ? bbox.join(",") : bbox;
  return request("bikeParking", { path: "/bike-parking/", query, mockFile: "bike-parking.json" });
}

// E8: demo origin/destination pairs.
export function getScenarios() {
  return request("scenarios", { path: "/routes/scenarios/", mockFile: "scenarios.json" });
}

// E9: scored route alternatives for one scenario id from E8.
export function compareRoutes(scenarioId) {
  return request("compare", {
    path: "/routes/compare/",
    query: { scenario: scenarioId },
    mock: () => mockCompare(scenarioId),
  });
}

// --- Plumbing -------------------------------------------------------------------------

async function request(endpoint, options) {
  const mode = API_MODE[endpoint];
  if (mode === "live") return liveRequest(options);
  if (mode === "mock") return mockRequest(options);
  throw new Error(`API_MODE.${endpoint} must be "mock" or "live", got ${mode}`);
}

async function liveRequest({ path, query, method = "GET", body, json, timeoutMs = TIMEOUT_MS }) {
  let url = API_BASE + path;
  if (query && Object.keys(query).length) url += "?" + new URLSearchParams(query);

  const headers = { Accept: "application/json" };
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }
  // FormData: no Content-Type on purpose, the browser adds it with the multipart boundary.
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();

  // AbortController cancels the fetch if the timer fires first.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body,
      signal: controller.signal,
      credentials: "same-origin",
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new ApiError("timeout", "The server took too long to answer. Please try again.");
    }
    throw new ApiError("network_error", "Can't reach the server. Check your connection.");
  } finally {
    clearTimeout(timer);
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    // Not JSON (e.g. an HTML error page): handled below.
  }
  if (response.ok && data !== null) return data;
  throw toApiError(response.status, data, response.headers.get("Retry-After"));
}

function toApiError(status, data, retryAfterHeader) {
  const error = data && typeof data.error === "object" ? data.error : null;
  if (!error || !KNOWN_CODES.has(error.code)) {
    return new ApiError(
      "unknown_error",
      (error && error.message) || "Something went wrong. Please try again.",
      { status, fields: (error && error.fields) || {} },
    );
  }
  let retryAfterSeconds = null;
  if (error.code === "ai_rate_limited") {
    retryAfterSeconds = Number(error.retry_after_seconds ?? retryAfterHeader) || null;
  }
  return new ApiError(error.code, error.message, {
    status,
    fields: error.fields || {},
    retryAfterSeconds,
  });
}

// Django sets the csrftoken cookie on views decorated with ensure_csrf_cookie
// (web/views.py). Fallback: a {% csrf_token %} hidden input on the page.
function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (match) return decodeURIComponent(match[1]);
  const input = document.querySelector("[name=csrfmiddlewaretoken]");
  return input ? input.value : "";
}

// --- Mock mode ------------------------------------------------------------------------

const FORCED_ERRORS = {
  ai_rate_limited: { status: 429, file: "error-ai-rate-limited.json" },
  validation_error: { status: 400, file: "error-validation.json" },
  not_found: { status: 404, message: "Not found." },
  duplicate_feedback: { status: 409, message: "You already sent this feedback." },
  server_error: { status: 500, message: "Server error." },
};

async function mockRequest({ method = "GET", mockFile, mock }) {
  if (method !== "GET") await sleep(mockOptions.delayMs);

  const forced = mockOptions.forceError;
  if (forced === "timeout") {
    throw new ApiError("timeout", "The server took too long to answer. Please try again.");
  }
  if (forced === "network_error") {
    throw new ApiError("network_error", "Can't reach the server. Check your connection.");
  }
  if (forced) {
    const spec = FORCED_ERRORS[forced];
    if (!spec) throw new Error(`Unknown MOCK_FORCE_ERROR: ${forced}`);
    const data = spec.file
      ? await loadMock(spec.file)
      : { error: { code: forced, message: spec.message, fields: {} } };
    throw toApiError(spec.status, data, null);
  }

  return mock ? mock() : loadMock(mockFile);
}

async function loadMock(file) {
  const response = await fetch(MOCK_BASE + file);
  if (!response.ok) throw new Error(`Mock file missing: ${file}`);
  return response.json();
}

// E4 mock: report 101 has its own file; other ids are built from reports.json.
async function mockReport(id) {
  if (String(id) === "101") return loadMock("report-101.json");
  const list = await loadMock("reports.json");
  const feature = list.features.find((f) => String(f.id) === String(id));
  if (!feature) throw new ApiError("not_found", "Not found.", { status: 404 });
  const [lng, lat] = feature.geometry.coordinates; // GeoJSON order is [lng, lat]
  return { id: feature.properties.id, lat, lng, ...feature.properties };
}

async function mockCompare(scenarioId) {
  if (!scenarioId) {
    throw new ApiError("validation_error", "Choose a route scenario.", {
      status: 400,
      fields: { scenario: ["This field is required."] },
    });
  }
  const data = await loadMock("routes-compare.json");
  if (data.scenario.id !== scenarioId) {
    throw new ApiError("not_found", "Not found.", { status: 404 });
  }
  return data;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
