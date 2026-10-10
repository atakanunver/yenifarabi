// Yalnızca statik dosyalar önbelleklenir; kişisel veri içeren sayfalar asla (KVKK).
const SURUM = "okul-v3";
const STATIK = ["/static/okul.css?v=3", "/static/logo-64.png", "/static/logo-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SURUM).then((c) => c.addAll(STATIK)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SURUM).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !url.pathname.startsWith("/static/")) return;
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
