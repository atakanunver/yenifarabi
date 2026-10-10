/* DijitalOkul — "Ana Ekrana Ekle".
 *
 * - Uygulama zaten ana ekrandan (standalone) açıldıysa hiçbir şey göstermez.
 * - Chrome/Edge/Samsung (beforeinstallprompt): butona basınca tarayıcının KENDİ kurulum penceresi açılır.
 *   İptal edilirse hata gösterilmez; buton yerinde kalır ve sonraki dokunuşta menü adımları gösterilir.
 * - iPhone/iPad: programatik kurulum yok; tarayıcıya göre adım adım yönerge gösterilir.
 * - Kurulum olayı gelmeyen Android tarayıcılar: tarayıcı menüsünden ekleme adımları gösterilir.
 * Tarayıcı tespiti yalnızca hangi yönergenin gösterileceğini seçmek içindir; hiçbir işlev ona bağlı değildir.
 */
(function () {
  "use strict";

  var kutu = document.getElementById("ana-ekran");
  if (!kutu) return;
  var tus = document.getElementById("ana-ekran-tus");
  var rehber = document.getElementById("ana-ekran-rehber");

  function kuruluMu() {
    return (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
  }
  if (kuruluMu()) return;

  var ua = navigator.userAgent || "";
  var ios = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var android = /Android/i.test(ua);
  var uygulamaIci = /FBAN|FBAV|Instagram|WhatsApp|Line\/|Telegram|GSA\//i.test(ua);
  var bekleyenIstem = null;

  function goster() { kutu.hidden = false; }

  function yonerge(baslik, adimlar, not) {
    var html = "<p><b>" + baslik + "</b></p><ol>";
    for (var i = 0; i < adimlar.length; i++) html += "<li>" + adimlar[i] + "</li>";
    html += "</ol>";
    if (not) html += '<p class="soluk kucuk">' + not + "</p>";
    rehber.innerHTML = html; // yalnızca bu dosyadaki sabit metinler; kullanıcı girdisi yok
    rehber.hidden = false;
    rehber.focus();
  }

  var PAYLAS = '<span class="sembol" aria-label="Paylaş simgesi">⬆︎</span>';

  function iosYonergesi() {
    if (uygulamaIci) {
      return yonerge("Önce sayfayı Safari'de açın", [
        "Sağ üstteki ••• (ya da paylaş) menüsüne dokunun.",
        "<b>Safari'de Aç</b> seçeneğini seçin.",
        "Safari'de bu sayfadaki <b>📲 Ana Ekrana Ekle</b> düğmesine yeniden dokunun."
      ], "Uygulama içi tarayıcılar (WhatsApp, Instagram vb.) ana ekrana eklemeyi desteklemez.");
    }
    if (/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua)) {
      return yonerge("Ana ekrana eklemek için", [
        "Adres çubuğundaki ya da menüdeki " + PAYLAS + " <b>Paylaş</b> simgesine dokunun.",
        "<b>Ana Ekrana Ekle</b> seçeneğini seçin.",
        "Gerekirse uygulama adını düzenleyin.",
        "<b>Ekle</b> düğmesine dokunun."
      ], "Seçenek görünmüyorsa sayfayı Safari'de açıp aynı adımları izleyin.");
    }
    yonerge("Safari'de ana ekrana eklemek için", [
      "Ekranın altındaki (iPad'de üstteki) " + PAYLAS + " <b>Paylaş</b> simgesine dokunun.",
      "<b>Ana Ekrana Ekle</b> seçeneğini seçin (görmüyorsanız listeyi aşağı kaydırın).",
      "Gerekirse uygulama adını düzenleyin.",
      "<b>Ekle</b> düğmesine dokunun."
    ], "DijitalOkul, ana ekranda okul logosuyla görünecek.");
  }

  function menuYonergesi() {
    if (/SamsungBrowser/i.test(ua)) {
      return yonerge("Samsung Internet'te ana ekrana eklemek için", [
        "Alttaki <b>≡</b> menü düğmesine dokunun.",
        "<b>Sayfayı ekle</b> → <b>Ana ekran</b> seçeneğini seçin.",
        "<b>Ekle</b> düğmesine dokunun."
      ]);
    }
    if (/Firefox/i.test(ua)) {
      return yonerge("Firefox'ta ana ekrana eklemek için", [
        "Sağ üstteki <b>⋮</b> menüsüne dokunun.",
        "<b>Yükle</b> ya da <b>Ana ekrana ekle</b> seçeneğini seçin.",
        "<b>Ekle</b> düğmesine dokunun."
      ]);
    }
    yonerge("Chrome'da ana ekrana eklemek için", [
      "Sağ üstteki <b>⋮</b> menüsüne dokunun.",
      "<b>Uygulamayı yükle</b> ya da <b>Ana ekrana ekle</b> seçeneğini seçin.",
      "Açılan pencerede <b>Yükle</b> / <b>Ekle</b> düğmesine dokunun."
    ], "Seçenek görünmüyorsa sayfayı yenileyip birkaç saniye sonra tekrar deneyin.");
  }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault(); // tarayıcının kendi bandı yerine bizim düğmemizle açılsın
    if (kuruluMu()) return;
    bekleyenIstem = e;
    goster();
  });

  window.addEventListener("appinstalled", function () {
    bekleyenIstem = null;
    tus.hidden = true;
    yonerge("✅ DijitalOkul ana ekranınıza eklendi", [
      "Uygulamayı ana ekrandaki okul logosuna dokunarak açabilirsiniz."
    ]);
  });

  tus.addEventListener("click", function () {
    if (bekleyenIstem) {
      var istem = bekleyenIstem;
      bekleyenIstem = null; // bir istem yalnızca bir kez kullanılabilir
      Promise.resolve()
        .then(function () { return istem.prompt(); })
        .then(function () { return istem.userChoice; })
        .then(function (secim) {
          if (secim && secim.outcome === "accepted") {
            tus.hidden = true;
            yonerge("✅ Kurulum başladı", ["Birkaç saniye içinde DijitalOkul ana ekranınızda görünecek."]);
          }
          // İptal: sessizce bırak (hata gösterme). Sonraki dokunuş menü adımlarını gösterir.
        })
        .catch(function () {
          // Tarayıcı kurulum penceresini açamadıysa sahte pencere yok: menü adımlarını göster.
          if (ios) iosYonergesi(); else menuYonergesi();
        });
      return;
    }
    if (ios) return iosYonergesi();
    menuYonergesi();
  });

  // Telefon/tablette düğme her zaman görünür (iOS'ta istem olayı hiç gelmez, yönerge gösterilir).
  // Masaüstünde yalnızca tarayıcı gerçekten kurulumu destekliyorsa (beforeinstallprompt) görünür.
  if (ios || android) goster();

  // Uygulama ana ekrandan açılırsa (ör. kurulumdan sonra aynı sekme) düğmeyi kaldır.
  if (window.matchMedia) {
    var mq = window.matchMedia("(display-mode: standalone)");
    var degisti = function (olay) { if (olay.matches) kutu.hidden = true; };
    if (mq.addEventListener) mq.addEventListener("change", degisti);
    else if (mq.addListener) mq.addListener(degisti);
  }
})();
