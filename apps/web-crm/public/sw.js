/* Service worker of the CRM shell (M31 WP5, operator decision M30-08, ADR 0017).
 *
 * Caches exactly the static offline page and the app icons, nothing else. Navigations go to the
 * network first; only when the network fails or does not answer within NAVIGATION_TIMEOUT_MS
 * is the static offline page returned. API responses (/api), documents, pages with personal or
 * financial data and every other request are never cached and never read from the cache. The
 * cache name carries the release, so an update drops the previous shell on activation. */
const CACHE = "mhvp-crm-shell-1.45.0";
const SHELL = ["/offline.html", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-512-maskable.png"];
const NAVIGATION_TIMEOUT_MS = 8000;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

function networkFirstNavigation(request) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (response) => {
      if (settled) return;
      settled = true;
      resolve(response);
    };
    const timer = setTimeout(() => {
      caches.match("/offline.html").then((page) => finish(page || Response.error()));
    }, NAVIGATION_TIMEOUT_MS);
    fetch(request)
      .then((response) => {
        clearTimeout(timer);
        finish(response);
      })
      .catch(() => {
        clearTimeout(timer);
        caches.match("/offline.html").then((page) => finish(page || Response.error()));
      });
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }
  if (SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
  }
});
