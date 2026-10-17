// DijitalOkul service worker — kapsam "/" (tek worker).
// KVKK: yalnızca aşağıdaki STATİK dosyalar önbelleklenir. HTML sayfaları, öğrenci/veli/öğretmen
// verileri ve POST istekleri (giriş, çıkış, formlar) hiçbir zaman önbelleğe alınmaz; her zaman ağdan gelir.
// Güncelleme: SURUM değişince yeni worker hemen devreye girer ve eski önbellekleri siler. Önbellekteki
// dosyalar sürüm sorgusuyla (?v=N) adreslendiğinden eski CSS/JS yeni HTML ile karışmaz.
const SURUM = "okul-v31";
const CEVRIMDISI = "/static/cevrimdisi.html";
const STATIK = [
  "/static/okul.css?v=26",
  "/static/foto.js?v=1",
  "/static/kurulum.js?v=1",
  "/static/saat.js?v=1",
  "/static/maraton.js?v=1",
  "/static/nabiz.js?v=1",
  "/static/push-ortak.js?v=1",
  "/static/push.js?v=2",
  "/static/push-kart.js?v=1",
  "/static/sohbet.js?v=2",
  "/static/sudoku.js?v=1",
  "/static/acil.js?v=2",
  "/static/push-cikis.js?v=1",
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

// Web Push: yalnızca sunucunun gönderdiği sabit, veri içermeyen metin gösterilir. Tıklayınca bildirimin sayfası açılır.
// Uygulama zaten açıksa pencere o sayfaya YÖNLENDİRİLİR (aynı adres olsa bile yeniden yüklenir): eski sayfada kalıp
// yeni duyuruyu görmeme sorununu önler. Adres yalnızca aynı kaynaktaki bir yol olabilir.
function guvenliYol(u) {
  return typeof u === "string" && u.startsWith("/") && !u.startsWith("//") ? u : "/";
}

self.addEventListener("push", (e) => {
  let v = {};
  try { v = e.data ? e.data.json() : {}; } catch (_) { v = {}; }
  e.waitUntil(
    self.registration.showNotification(String(v.baslik || "Dijital Okul"), {
      body: String(v.govde || "Yeni bir bildirimin var."),
      icon: "/static/logo-192.png",
      badge: "/static/logo-64.png",
      data: { url: guvenliYol(v.url) },
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const yol = guvenliYol(e.notification.data && e.notification.data.url);
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
      for (const w of ws) {
        if ("navigate" in w) {
          return w.navigate(yol).then((c) => (c || w).focus()).catch(() => w.focus());
        }
        if ("focus" in w) return w.focus();
      }
      return clients.openWindow(yol);
    })
  );
});
