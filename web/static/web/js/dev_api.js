// Drives the /dev/api/ page (DEBUG only): call each api.js function and print the result.

import * as api from "./api.js";
import { API_MODE, MOCK_DELAY_MS, MOCK_FORCE_ERROR } from "./config.js";

const $ = (id) => document.getElementById(id);
const out = $("out");

// One mock/live dropdown per endpoint. Changing it edits API_MODE in memory only.
for (const key of Object.keys(API_MODE)) {
  const label = document.createElement("label");
  label.htmlFor = `mode-${key}`;
  label.textContent = key;
  const select = document.createElement("select");
  select.id = `mode-${key}`;
  for (const mode of ["mock", "live"]) select.add(new Option(mode, mode, false, API_MODE[key] === mode));
  select.addEventListener("change", () => (API_MODE[key] = select.value));
  $("modes").append(label, select);
}

$("force-error").value = MOCK_FORCE_ERROR || "";
$("force-error").addEventListener("change", (e) => api.setMockOptions({ forceError: e.target.value || null }));
$("delay").value = MOCK_DELAY_MS;
$("delay").addEventListener("change", (e) => api.setMockOptions({ delayMs: Number(e.target.value) || 0 }));

const calls = {
  getMeta: () => api.getMeta(),
  getReports: () =>
    api.getReports({ bbox: $("bbox").value.trim() || undefined, includeResolved: $("include-resolved").checked }),
  getReport: () => api.getReport($("report-id").value.trim()),
  createReport: () => {
    const form = new FormData();
    if ($("photo").files[0]) form.append("photo", $("photo").files[0]);
    form.append("lat", $("lat").value);
    form.append("lng", $("lng").value);
    if ($("note").value) form.append("note", $("note").value);
    return api.createReport(form);
  },
  sendFeedback: () => api.sendFeedback($("feedback-id").value.trim(), $("feedback-action").value),
  getSegments: () => api.getSegments(),
  getScenarios: () => api.getScenarios(),
  compareRoutes: () => api.compareRoutes($("scenario").value.trim()),
};

document.querySelectorAll("[data-call]").forEach((button) => {
  button.addEventListener("click", async () => {
    const name = button.dataset.call;
    const key = {
      getMeta: "meta", getReports: "reports", getReport: "reportDetail", createReport: "createReport",
      sendFeedback: "feedback", getSegments: "segments", getScenarios: "scenarios", compareRoutes: "compare",
    }[name];
    const started = performance.now();
    out.textContent = `${name} (${API_MODE[key]}) …`;
    button.disabled = true;
    try {
      const data = await calls[name]();
      out.textContent = `${name} (${API_MODE[key]}) OK in ${ms(started)}\n\n${JSON.stringify(data, null, 2)}`;
    } catch (err) {
      const detail = err instanceof api.ApiError
        ? { code: err.code, status: err.status, message: err.message, fields: err.fields, retryAfterSeconds: err.retryAfterSeconds }
        : { error: String(err) };
      out.textContent = `${name} (${API_MODE[key]}) FAILED in ${ms(started)}\n\n${JSON.stringify(detail, null, 2)}`;
    } finally {
      button.disabled = false;
    }
  });
});

function ms(started) {
  return `${Math.round(performance.now() - started)} ms`;
}
