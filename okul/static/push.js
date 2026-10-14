// Bildirim aç/kapat (/bildirimler sayfası). İzin YALNIZCA düğmeye basılınca istenir; içerik taşımayan sabit metinli bildirimler.
(function () {
  "use strict";
  var kutu = document.getElementById("push-kutu");
  var P = window.PushOrtak;
  if (!kutu || !P) return;
  var durum = document.getElementById("push-durum");
  var ac = document.getElementById("push-ac");
  var kapat = document.getElementById("push-kapat");
  var dene = document.getElementById("push-dene");
  var csrf = kutu.getAttribute("data-csrf");

  function yaz(m) { durum.textContent = m; }
  function gorunum(acik) { ac.hidden = acik; kapat.hidden = !acik; dene.hidden = !acik; }

  if (!P.destekli()) {
    yaz("Bu tarayıcı bildirimleri desteklemiyor. iPhone'da uygulamayı önce ana ekrana ekleyin (iOS 16.4 ve üzeri).");
    ac.hidden = true; kapat.hidden = true; dene.hidden = true;
    return;
  }

  function yenile() {
    return P.mevcut().then(function (a) {
      gorunum(!!a);
      yaz(a ? "Bildirimler bu cihazda açık." : (Notification.permission === "denied"
        ? "Bildirimler tarayıcı ayarlarından engellenmiş; açmak için site izinlerini değiştirin."
        : "Bildirimler bu cihazda kapalı."));
    });
  }

  ac.addEventListener("click", function () {
    ac.disabled = true;
    P.ac(csrf).then(yenile).catch(function (e) {
      yaz(e && e.message === "izin" ? "İzin verilmedi." : "Bildirim açılamadı. Biraz sonra tekrar deneyin.");
    }).then(function () { ac.disabled = false; });
  });

  kapat.addEventListener("click", function () {
    P.mevcut().then(function (a) {
      if (!a) return;
      return P.gonder("/push/iptal", csrf, { uc_nokta: a.endpoint }).then(function () { return a.unsubscribe(); });
    }).then(yenile).catch(function () { yaz("Bildirim kapatılamadı."); });
  });

  dene.addEventListener("click", function () {
    P.gonder("/push/deneme", csrf).then(function (r) { yaz(r.ok ? "Deneme bildirimi gönderildi." : "Deneme gönderilemedi."); });
  });

  yenile();
})();
