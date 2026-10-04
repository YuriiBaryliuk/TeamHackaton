// Shared header for the secondary pages: the brand dot and the language select.
import { dotSvg } from "./dot.js";
import { getLang, LANGS, setLang } from "./i18n.js";

export function setupHeader() {
  const brand = document.getElementById("brand-dot");
  if (brand) brand.innerHTML = dotSvg("ok", { size: 26 });
  const select = document.getElementById("lang-select");
  if (!select) return;
  select.innerHTML = LANGS.map((l) => `<option value="${l}">${l.toUpperCase()}</option>`).join("");
  select.addEventListener("change", () => setLang(select.value));
  document.addEventListener("langchange", () => { select.value = getLang(); });
}
