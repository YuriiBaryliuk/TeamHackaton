// The Kropka dot: logo, map marker and status icon in one.
// Status is shown by SHAPE so it never depends on colour alone:
//   ok -> filled dot, low -> half-filled, empty -> ring, unknown -> pale grey dot.

const SHAPES = {
  ok: `<circle cx="12" cy="12" r="9" fill="var(--accent)" stroke="var(--accent)" stroke-width="3"/>`,
  low: `<circle cx="12" cy="12" r="9" fill="var(--surface)" stroke="var(--accent)" stroke-width="3"/>
        <path d="M12 3 A9 9 0 0 0 12 21 Z" fill="var(--accent)"/>`,
  empty: `<circle cx="12" cy="12" r="9" fill="var(--surface)" stroke="var(--accent)" stroke-width="3"/>`,
  unknown: `<circle cx="12" cy="12" r="9" fill="var(--muted)" stroke="var(--muted)" stroke-width="3" opacity="0.55"/>`,
};

// Returns an SVG string. `faded` lowers the opacity (status not confirmed for 24-72 h).
export function dotSvg(status = "ok", { size = 24, faded = false } = {}) {
  const shape = SHAPES[status] || SHAPES.unknown;
  const cls = faded ? "dot-svg faded" : "dot-svg";
  return `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${shape}</svg>`;
}
