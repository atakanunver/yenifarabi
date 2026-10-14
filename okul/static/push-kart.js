// Ana sayfa/duyurular üstündeki "Bildirimleri aç" kartı. Yalnızca destekleyen, henüz abone olmayan, izni engellememiş
// ve son 7 günde "Şimdi değil" demeyen kullanıcıya görünür. İzin penceresi yalnızca düğmeye basınca açılır.
(function () {
  "use strict";
  var kart = document.getElementById("push-kart");
  var P = window.PushOrtak;
  if (!kart || !P || !P.destekli()) return;
  var ANAHTAR = "pushKartGec";
  var GUN_MS = 7 * 24 * 3600 * 1000;
  var csrf = kart.getAttribute("data-csrf");
  var durum = document.getElementById("push-kart-durum");

  function gecmis() {
    try {
      var t = parseInt(localStorage.getItem(ANAHTAR) || "0", 10);
      return t && Date.now() - t < GUN_MS;
    } catch (_) { return false; }
  }
  if (Notification.permission === "denied" || gecmis()) return;

  P.mevcut().then(function (a) {
    if (a) return;
    kart.hidden = false;
  }).catch(function () {});

  document.getElementById("push-kart-ac").addEventListener("click", function () {
    var d = this;
    d.disabled = true;
    P.ac(csrf).then(function () {
      kart.hidden = true;
    }).catch(function (e) {
      durum.textContent = e && e.message === "izin"
        ? "İzin verilmedi. İstersen sonra üst çubuktaki 🔔 simgesinden açabilirsin."
        : "Bildirim açılamadı. Biraz sonra tekrar dene.";
      d.disabled = false;
    });
  });

  document.getElementById("push-kart-gec").addEventListener("click", function () {
    try { localStorage.setItem(ANAHTAR, String(Date.now())); } catch (_) {}
    kart.hidden = true;
  });
})();
