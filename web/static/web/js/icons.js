// Hazard icons shared by the map (map.js) and the routes page (routes.js).

// Icon shapes keyed by meta.hazard_types[].icon (a hint, not a file). Our own static
// markup, parsed once with DOMParser and cloned per pin.
export const ICONS = {
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

export function icon(name) {
  const key = Object.hasOwn(ICONS, name) ? name : "warning";
  if (!iconCache.has(key)) {
    const viewBox = key === "camera" ? "0 0 64 64" : "0 0 24 24";
    const markup = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" aria-hidden="true">${ICONS[key]}</svg>`;
    const svg = new DOMParser().parseFromString(markup, "image/svg+xml").documentElement;
    iconCache.set(key, document.importNode(svg, true));
  }
  return iconCache.get(key).cloneNode(true);
}
