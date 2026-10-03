// Register the service worker (offline app shell + last known data).
// Browsers only allow this on HTTPS or localhost; elsewhere it is silently skipped.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* the app still works without it */ });
}
