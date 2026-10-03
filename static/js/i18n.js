// Minimal i18n: JSON files per language, a t(key) helper, the choice kept in localStorage.
// HTML elements with data-i18n="key" get their text replaced automatically,
// data-i18n-aria="key" sets aria-label.

export const LANGS = ["pl", "en", "uk"];
const DEFAULT_LANG = "pl";
const STORAGE_KEY = "kropka_lang";

let lang = DEFAULT_LANG;
let strings = {};
let fallback = {}; // Polish, used when a key is missing in the chosen language

function storedLang() {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

function detectLang() {
  const saved = storedLang();
  if (LANGS.includes(saved)) return saved;
  const browser = (navigator.language || "").slice(0, 2).toLowerCase();
  return LANGS.includes(browser) ? browser : DEFAULT_LANG;
}

async function load(code) {
  const res = await fetch(`/static/i18n/${code}.json`);
  return res.ok ? res.json() : {};
}

export function getLang() {
  return lang;
}

// t("point.confirmed", {ago: "5 min temu"}) -> "Ostatnio potwierdzone 5 min temu"
export function t(key, vars = {}) {
  const text = strings[key] ?? fallback[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? "");
}

// Plurals: tn("n.takes", 5) looks up "n.takes.many" in Polish ("5 pobrań"),
// using the browser's plural rules (one / few / many / other).
export function tn(key, n, vars = {}) {
  const category = new Intl.PluralRules(lang).select(n);
  const exists = `${key}.${category}` in strings || `${key}.${category}` in fallback;
  return t(exists ? `${key}.${category}` : `${key}.other`, { n: n.toLocaleString(lang), ...vars });
}

// Numbers in the user's language: 1240 -> "1240" / "1,240", 31.7 h -> "31,7 godz."
export function fmtNumber(n, options = {}) {
  return new Intl.NumberFormat(lang, options).format(n);
}

export function fmtHours(h) {
  if (h == null) return "–";
  return fmtNumber(h, { style: "unit", unit: "hour", unitDisplay: "short", maximumFractionDigits: 1 });
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
}

export async function setLang(code) {
  lang = LANGS.includes(code) ? code : DEFAULT_LANG;
  try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* private mode: fine */ }
  [fallback, strings] = await Promise.all([load(DEFAULT_LANG), lang === DEFAULT_LANG ? null : load(lang)]);
  strings = strings || fallback;
  document.documentElement.lang = lang;
  applyTranslations();
  document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
}

export function initI18n() {
  return setLang(detectLang());
}

// "5 minut temu" / "5 minutes ago" / "5 хвилин тому", with correct plurals from the browser.
export function timeAgo(minutes) {
  if (minutes == null) return "";
  if (minutes < 1) return t("time.just_now");
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  if (minutes < 60) return rtf.format(-Math.round(minutes), "minute");
  if (minutes < 48 * 60) return rtf.format(-Math.round(minutes / 60), "hour");
  return rtf.format(-Math.round(minutes / 1440), "day");
}

// Buttons PL / EN / UK inside `container`.
export function renderLangSwitch(container) {
  container.classList.add("lang-switch");
  container.setAttribute("role", "group");
  container.dataset.i18nAria = "lang.label";
  container.innerHTML = LANGS.map(
    (code) => `<button type="button" data-lang="${code}" lang="${code}">${code.toUpperCase()}</button>`,
  ).join("");
  const update = () => container.querySelectorAll("button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === lang));
  });
  container.addEventListener("click", (e) => {
    const code = e.target.closest("button")?.dataset.lang;
    if (code && code !== lang) setLang(code);
  });
  document.addEventListener("langchange", update);
  update();
}
