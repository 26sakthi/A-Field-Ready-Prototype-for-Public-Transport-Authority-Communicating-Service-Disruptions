// Minimal app-shell service worker: caches the shell so the field PWA opens
// with no network. API calls are network-first and fall through to the offline
// queue when unreachable (handled in the app, not here).
const SHELL = "veritransit-shell-v1";
const ASSETS = ["/", "/index.html", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // never cache API/WS; let the app handle offline queueing
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/ws")) return;
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).catch(() => caches.match("/index.html")))
  );
});
