// Report page ("/report/"): photo + spot on the map + optional note -> POST /api/reports/ (E5).
// Upload limits, labels and the map area come from GET /api/meta/ (E2). The server checks
// everything again; the checks here only give a friendly message before a slow upload.
// API data is always inserted with textContent / text nodes, never as HTML.

import { ApiError, createReport, getMeta } from "./api.js";
import { TILE_LAYER } from "./config.js";

const L = window.L; // Leaflet, loaded by a classic <script> before this module runs

const MAX_EDGE_PX = 1600; // long edge after resizing; the server shrinks to the same size
const JPEG_QUALITY = 0.85;
const PICK_ZOOM = 17; // close enough to put the pin on the right side of the street
const ANALYZE_LINES = [
  "Reading your photo…",
  "Looking for cars and barriers…",
  "Checking the bike lane…",
  "Pinning it to the map…",
];

const $ = (selector) => document.querySelector(selector);

const el = {
  form: $("#report-form"),
  photo: $("#photo"),
  drop: $("#drop"),
  dropEmpty: $("#drop-empty"),
  photoHint: $("#photo-hint"),
  preview: $("#photo-preview"),
  caption: $("#photo-caption"),
  errPhoto: $("#err-photo"),
  pickMap: $("#pick-map"),
  coords: $("#where-coords"),
  useLocation: $("#use-location"),
  errLocation: $("#err-location"),
  note: $("#note"),
  noteCount: $("#note-count"),
  errNote: $("#err-note"),
  submit: $("#submit-btn"),
  formMsg: $("#form-msg"),
  formAction: $("#form-action"),
  analyzing: $("#analyzing"),
  analyzingMsg: $("#analyzing-msg"),
  result: $("#result"),
  resultPhoto: $("#result-photo"),
  resultChips: $("#result-chips"),
  resultTitle: $("#result-title"),
  resultDesc: $("#result-desc"),
  resultReview: $("#result-review"),
  resultNote: $("#result-note"),
  resultFacts: $("#result-facts"),
  resultView: $("#result-view"),
  resultAgain: $("#result-again"),
  noPhotoTpl: $("#no-photo-tpl"),
};

const state = {
  meta: null,
  photo: null, // the Blob we will upload (resized JPEG, or the original if already small)
  previewUrl: null,
  picked: null, // L.latLng
  submitting: false,
  countdown: null, // interval id while waiting out a 429
};

let map = null;
let pickMarker = null;
let bounds = null;

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

const mb = (bytes) => Math.round(bytes / 1048576);

// --- Meta -------------------------------------------------------------------------------

function applyMeta(meta) {
  state.meta = meta;
  const up = meta.upload;
  const types = up.accepted_types.map((t) => t.split("/")[1].toUpperCase()).join(", ");
  el.photoHint.textContent = `${types} · up to ${mb(up.max_photo_bytes)} MB`;
  el.note.maxLength = up.max_note_length;
  updateCount();
  // Condition colors: CSS uses var(--c-red) etc.; set them from meta so CSS follows the API.
  const root = document.documentElement.style;
  for (const c of meta.conditions) {
    if (/^[a-z_]+$/.test(c.key) && /^#[0-9a-f]{3,8}$/i.test(c.hex)) {
      root.setProperty(`--c-${c.key}`, c.hex);
    }
  }
}

function hazardLabel(key) {
  const types = state.meta.hazard_types;
  return (types.find((t) => t.key === key) || types.find((t) => t.key === "other"))?.label || "Other";
}

function conditionOf(key) {
  const list = state.meta.conditions;
  return list.find((c) => c.key === key) || list.find((c) => c.key === "grey") || { key: "grey", label: "Unknown" };
}

function statusLabel(key) {
  return state.meta.verification_statuses.find((s) => s.key === key)?.label || String(key);
}

// --- Step 1: photo ----------------------------------------------------------------------

el.photo.addEventListener("change", () => {
  const file = el.photo.files[0];
  if (file) takePhoto(file);
});

// Drag and drop for desktop. On phones the input opens the camera instead.
for (const type of ["dragenter", "dragover"]) {
  el.drop.addEventListener(type, (e) => {
    e.preventDefault();
    el.drop.classList.add("is-over");
  });
}
for (const type of ["dragleave", "drop"]) {
  el.drop.addEventListener(type, () => el.drop.classList.remove("is-over"));
}
el.drop.addEventListener("drop", (e) => {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) takePhoto(file);
});

// File API: the <input type="file"> gives us File objects (a File is a Blob with a name).
// Nothing is uploaded yet; we can read, resize and preview it locally first.
async function takePhoto(file) {
  el.errPhoto.textContent = "";
  if (!state.meta) {
    el.errPhoto.textContent = "The form is still loading. Choose the photo again in a moment.";
    return;
  }
  const up = state.meta.upload;
  // file.type comes from the file name and can be empty; then we let the server decide.
  if (file.type && !up.accepted_types.includes(file.type)) {
    el.errPhoto.textContent = "That file type won't work. Use a JPEG, PNG or WebP photo.";
    return;
  }

  const blob = await shrink(file);
  // Size is checked on what we will actually send: a 12 MB phone photo is fine once resized.
  if (blob.size > up.max_photo_bytes) {
    el.errPhoto.textContent = `That photo is over ${mb(up.max_photo_bytes)} MB. Pick a smaller one.`;
    return;
  }

  state.photo = blob;
  // An object URL ("blob:...") lets an <img> show a local file without uploading it.
  // Revoke the previous one so the browser can free that memory.
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(blob);
  el.preview.src = state.previewUrl;
  el.preview.hidden = false;
  el.dropEmpty.hidden = true;
  el.caption.textContent = "got it";
}

// Canvas resize: draw the photo onto a smaller <canvas>, then export it as a JPEG Blob.
// Faster upload on mobile data, and the new file has no EXIF (so no GPS position).
// The <img> applies the phone's EXIF rotation, so the drawing comes out the right way up.
async function shrink(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode(); // waits until the image is loaded and decoded
    const longEdge = Math.max(img.naturalWidth, img.naturalHeight);
    if (longEdge <= MAX_EDGE_PX) return file; // already small: send it as it is

    const scale = MAX_EDGE_PX / longEdge;
    const canvas = h("canvas", {
      width: Math.round(img.naturalWidth * scale),
      height: Math.round(img.naturalHeight * scale),
    });
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff"; // JPEG has no transparency: put PNGs on white, not black
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
    return blob || file;
  } catch {
    return file; // the browser couldn't decode it; the server will judge the original
  } finally {
    URL.revokeObjectURL(url);
  }
}

// --- Step 2: location -------------------------------------------------------------------

const PIN_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 40" aria-hidden="true"><path d="M15 39 C 15 39 3 24 3 14 a12 12 0 0 1 24 0 c0 10 -12 25 -12 25z"/><circle cx="15" cy="14" r="4.5"/></svg>';

function pickIcon() {
  const pin = h("div", { class: "pick-pin" });
  pin.append(new DOMParser().parseFromString(PIN_SVG, "image/svg+xml").documentElement);
  return L.divIcon({ className: "pick-pin-icon", html: pin, iconSize: [30, 40], iconAnchor: [15, 39] });
}

// ?lat=&lng= from the map's "Report here" button, if they are valid and inside the area.
function startPoint() {
  const params = new URLSearchParams(location.search);
  const lat = Number(params.get("lat"));
  const lng = Number(params.get("lng"));
  if (params.has("lat") && params.has("lng") && bounds.contains([lat, lng])) {
    return { center: [lat, lng], zoom: PICK_ZOOM };
  }
  const { center, zoom } = state.meta.map;
  return { center: [center.lat, center.lng], zoom };
}

function createMap() {
  const b = state.meta.map.bounds;
  bounds = L.latLngBounds([b.min_lat, b.min_lng], [b.max_lat, b.max_lng]);
  const start = startPoint();

  // L.map takes [lat, lng]. maxBounds stops panning outside the demo area.
  map = L.map(el.pickMap, { maxBounds: bounds, maxBoundsViscosity: 1 }).setView(start.center, start.zoom);
  map.setMinZoom(map.getBoundsZoom(bounds, true));
  L.tileLayer(TILE_LAYER.url, TILE_LAYER.options).addTo(map);
  map.on("click", (e) => setPick(e.latlng));
}

function setPick(latlng) {
  el.errLocation.textContent = "";
  if (!bounds.contains(latlng)) {
    el.errLocation.textContent = "That spot is outside the area BikeAble covers. Pick a place closer to the centre.";
    return;
  }
  state.picked = latlng;
  if (pickMarker) pickMarker.setLatLng(latlng);
  else pickMarker = L.marker(latlng, { icon: pickIcon(), keyboard: false }).addTo(map);
  el.coords.textContent = `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
}

// Browsers only allow GPS on https or localhost ("secure context"). On http://<LAN-IP>
// the call would just fail, so the button stays hidden there.
function setupGeolocation() {
  if (!("geolocation" in navigator) || !window.isSecureContext) return;
  el.useLocation.hidden = false;
  el.useLocation.addEventListener("click", () => {
    el.useLocation.disabled = true;
    el.errLocation.textContent = "";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        el.useLocation.disabled = false;
        const latlng = L.latLng(pos.coords.latitude, pos.coords.longitude);
        setPick(latlng);
        if (bounds.contains(latlng)) map.setView(latlng, Math.max(map.getZoom(), PICK_ZOOM));
      },
      () => {
        el.useLocation.disabled = false;
        el.errLocation.textContent = "Couldn't get your location. Tap the map instead.";
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  });
}

// --- Step 3: note -----------------------------------------------------------------------

function updateCount() {
  const max = el.note.maxLength;
  el.noteCount.textContent = `${el.note.value.length} / ${max}`;
  el.noteCount.classList.toggle("is-near", el.note.value.length > max * 0.9);
}
el.note.addEventListener("input", updateCount);

// --- Submit -----------------------------------------------------------------------------

function clearMessages() {
  for (const node of [el.errPhoto, el.errLocation, el.errNote, el.formMsg]) node.textContent = "";
  el.formAction.hidden = true;
}

function showAction(label, onClick) {
  el.formAction.textContent = label;
  el.formAction.onclick = onClick;
  el.formAction.hidden = false;
}

el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  send();
});

async function send() {
  if (state.submitting || state.countdown || !state.meta) return; // no double submits
  clearMessages();
  let ok = true;
  if (!state.photo) {
    el.errPhoto.textContent = "Add a photo of the hazard first.";
    ok = false;
  }
  if (!state.picked) {
    el.errLocation.textContent = "Tap the map where you saw it.";
    ok = false;
  }
  if (!ok) return revealFirstMessage();

  // FormData = the body of a multipart/form-data request: text fields plus files, exactly
  // what an HTML form would send. api.js adds the CSRF header; the browser sets Content-Type.
  const form = new FormData();
  form.append("photo", state.photo, state.photo.name || "hazard.jpg");
  form.append("lat", state.picked.lat.toFixed(6));
  form.append("lng", state.picked.lng.toFixed(6));
  const note = el.note.value.trim();
  if (note) form.append("note", note);

  setSubmitting(true);
  try {
    showResult(await createReport(form));
  } catch (err) {
    showError(err);
  } finally {
    setSubmitting(false);
  }
  revealFirstMessage();
}

// After a failed submit, make sure the first message is on screen (not under the bottom nav).
function revealFirstMessage() {
  const first = [el.errPhoto, el.errLocation, el.errNote, el.formMsg].find((node) => node.textContent);
  first?.scrollIntoView({ block: "center", behavior: "smooth" });
}

let ticker = null;

function setSubmitting(on) {
  state.submitting = on;
  el.submit.disabled = on || Boolean(state.countdown);
  el.submit.dataset.state = on ? "loading" : "";
  el.form.inert = on; // nothing behind the overlay can be clicked or focused
  el.analyzing.hidden = !on;
  clearInterval(ticker);
  if (on) {
    let line = 0;
    el.analyzingMsg.textContent = ANALYZE_LINES[0];
    ticker = setInterval(() => {
      line = (line + 1) % ANALYZE_LINES.length;
      el.analyzingMsg.textContent = ANALYZE_LINES[line];
    }, 2200);
  }
}

const FIELD_ERRORS = { photo: "errPhoto", lat: "errLocation", lng: "errLocation", note: "errNote" };

function showError(err) {
  if (!(err instanceof ApiError)) {
    console.error(err);
    el.formMsg.textContent = "Something went wrong on this page. Please try again.";
    return;
  }
  switch (err.code) {
    case "ai_rate_limited":
      startCountdown(err.message, err.retryAfterSeconds || 60);
      break;
    case "validation_error": {
      let placed = false;
      for (const [field, messages] of Object.entries(err.fields || {})) {
        const target = el[FIELD_ERRORS[field]];
        if (target) {
          target.textContent = [].concat(messages).join(" ");
          placed = true;
        }
      }
      el.formMsg.textContent = placed ? "Please fix the marked fields." : err.message;
      break;
    }
    case "photo_too_large":
      el.errPhoto.textContent = err.message || "That photo is too large. Pick a smaller one.";
      break;
    case "unsupported_photo_type":
      el.errPhoto.textContent = err.message || "That file type won't work. Use a JPEG, PNG or WebP photo.";
      break;
    case "csrf_failed":
      el.formMsg.textContent = "Your session expired. Please reload the page and send it again.";
      showAction("Reload page", () => location.reload());
      break;
    case "timeout":
      // The server may still have saved it: say so, so people check before sending twice.
      el.formMsg.textContent =
        "That took too long. It may still have reached the map, so check there before sending again.";
      showAction("Try again", send);
      break;
    case "network_error":
      el.formMsg.textContent = "Can't reach BikeAble. Check your connection, then try again.";
      showAction("Try again", send);
      break;
    default:
      el.formMsg.textContent = "Something went wrong. Please try again in a moment.";
  }
}

function startCountdown(message, seconds) {
  let left = Math.max(1, Math.round(seconds));
  const render = () => {
    el.formMsg.textContent = `${message} You can retry in ${left}s.`;
  };
  render();
  el.submit.disabled = true;
  state.countdown = setInterval(() => {
    left -= 1;
    if (left > 0) return render();
    clearInterval(state.countdown);
    state.countdown = null;
    el.submit.disabled = false;
    el.formMsg.textContent = "Ready. Try sending again.";
  }, 1000);
}

// --- Result -----------------------------------------------------------------------------

function showResult(r) {
  const condition = conditionOf(r.condition);
  const label = hazardLabel(r.hazard_type);

  // Photo: the server's copy; our local preview if it has none or it fails to load.
  const fallback = () => {
    if (state.previewUrl) el.resultPhoto.replaceChildren(h("img", { src: state.previewUrl, alt: `Photo of: ${label}` }));
    else el.resultPhoto.replaceChildren(el.noPhotoTpl.content.cloneNode(true));
  };
  if (r.photo_url) {
    const img = h("img", { src: r.photo_url, alt: `Photo of: ${label}` });
    img.addEventListener("error", fallback, { once: true });
    el.resultPhoto.replaceChildren(img);
  } else {
    fallback();
  }

  const condChip = h("span", { class: "chip chip--cond", "data-cond": condition.key }, condition.label);
  condChip.style.setProperty("--c", `var(--c-${condition.key})`);
  const chips = [condChip];
  // ai_flagged's own label is "Needs review"; show that once, as the dashed warning chip.
  if (r.verification_status !== "ai_flagged") chips.push(h("span", { class: "chip" }, statusLabel(r.verification_status)));
  if (r.needs_review) chips.push(h("span", { class: "chip chip--warn" }, "Needs review"));
  if (r.is_synthetic) chips.push(h("span", { class: "chip chip--demo" }, "Demo data"));
  el.resultChips.replaceChildren(...chips);

  el.resultTitle.textContent = label;
  el.resultDesc.textContent = r.description || "";
  el.resultReview.hidden = !r.needs_review;
  el.resultNote.textContent = r.note ? `“${r.note}”` : "";
  const confidence = r.ai_confidence == null ? "Not analysed" : `${Math.round(r.ai_confidence * 100)}%`;
  el.resultFacts.replaceChildren(h("dt", {}, "AI sure"), h("dd", {}, confidence));

  el.resultView.href = `/map/?report=${encodeURIComponent(r.id)}`;
  el.form.hidden = true;
  el.result.hidden = false;
  window.scrollTo({ top: 0 });
  el.result.focus({ preventScroll: true });
}

el.resultAgain.addEventListener("click", () => {
  el.form.reset();
  clearMessages();
  state.photo = null;
  state.picked = null;
  if (pickMarker) {
    pickMarker.remove();
    pickMarker = null;
  }
  el.preview.hidden = true;
  el.preview.removeAttribute("src");
  el.dropEmpty.hidden = false;
  el.caption.textContent = "the hazard";
  el.coords.textContent = "No spot yet";
  updateCount();
  el.result.hidden = true;
  el.form.hidden = false;
  map.invalidateSize(); // the map was hidden; Leaflet must re-measure its box
  window.scrollTo({ top: 0 });
});

// --- Start ------------------------------------------------------------------------------

async function init() {
  el.submit.disabled = true; // until meta (limits, map area) has loaded
  try {
    applyMeta(await getMeta());
  } catch (err) {
    el.formMsg.textContent =
      err instanceof ApiError && err.code === "network_error"
        ? "Can't reach BikeAble. Check your connection, then try again."
        : "Couldn't load the report form. Please try again.";
    showAction("Try again", () => {
      clearMessages();
      init();
    });
    return;
  }
  createMap();
  setupGeolocation();
  el.submit.disabled = false;
}

init();
