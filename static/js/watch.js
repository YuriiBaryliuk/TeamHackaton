// "Points I look after" (steward). Kept ONLY in this browser (localStorage):
// no account, nothing about the person is sent to the server.
const KEY = "kropka_watch";

export function getWatched() {
  try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; }
}

export function isWatched(id) {
  return getWatched().includes(id);
}

export function setWatched(id, on) {
  const ids = getWatched().filter((x) => x !== id);
  if (on) ids.push(id);
  try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch { /* private mode: not saved */ }
}
