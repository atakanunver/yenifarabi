// DijitalOkul service worker — kapsam "/" (tek worker).
// KVKK: yalnızca aşağıdaki STATİK dosyalar önbelleklenir. HTML sayfaları, öğrenci/veli/öğretmen
// verileri ve POST istekleri (giriş, çıkış, formlar) hiçbir zaman önbelleğe alınmaz; her zaman ağdan gelir.
// Güncelleme: SURUM değişince yeni worker hemen devreye girer ve eski önbellekleri siler. Önbellekteki
// dosyalar sürüm sorgusuyla (?v=N) adreslendiğinden eski CSS/JS yeni HTML ile karışmaz.
const SURUM = "okul-v8";
const CEVRIMDISI = "/static/cevrimdisi.html";
const STATIK = [
  "/static/okul.css?v=8",
  "/static/foto.js?v=1",
  "/static/kurulum.js?v=1",
  "/static/saat.js?v=1",
  "/static/maraton.js?v=1",
  "/static/logo-64.png",
  "/static/logo-192.png",
  "/static/apple-touch-icon.png",
  CEVRIMDISI,
];

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
  const istek = e.request;
  if (istek.method !== "GET") return;
  const url = new URL(istek.url);
  if (url.origin !== location.origin) return;

  // Sayfa gezinmesi: her zaman ağ. Yalnızca ağ yoksa veri içermeyen çevrimdışı sayfası.
  if (istek.mode === "navigate") {
    e.respondWith(fetch(istek).catch(() => caches.match(CEVRIMDISI)));
    return;
  }
  // Statik dosyalar: önbellekte varsa oradan, yoksa ağdan (ağdan gelen önbelleğe yazılmaz).
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(istek).then((r) => r || fetch(istek)));
  }
});
