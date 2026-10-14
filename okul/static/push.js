// Bildirim aç/kapat (profil sayfası). İzin YALNIZCA düğmeye basılınca istenir; içerik taşımayan sabit metinli bildirimler.
(function () {
  "use strict";
  var kutu = document.getElementById("push-kutu");
  if (!kutu) return;
  var durum = document.getElementById("push-durum");
  var ac = document.getElementById("push-ac");
  var kapat = document.getElementById("push-kapat");
  var dene = document.getElementById("push-dene");
  var csrf = kutu.getAttribute("data-csrf");

  function yaz(m) { durum.textContent = m; }
  function gorunum(acik) { ac.hidden = acik; kapat.hidden = !acik; dene.hidden = !acik; }

  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    yaz("Bu tarayıcı bildirimleri desteklemiyor. iPhone'da uygulamayı önce ana ekrana ekleyin (iOS 16.4 ve üzeri).");
    gorunum(true); ac.hidden = true; kapat.hidden = true; dene.hidden = true;
    return;
  }

  function b64(s) {
    var p = "=".repeat((4 - (s.length % 4)) % 4);
    var r = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
    var o = new Uint8Array(r.length);
    for (var i = 0; i < r.length; i++) o[i] = r.charCodeAt(i);
    return o;
  }
  function b64url(buf) {
    var b = new Uint8Array(buf), s = "";
    for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function gonder(yol, alanlar) {
    var f = new FormData();
    f.append("csrf", csrf);
    Object.keys(alanlar || {}).forEach(function (k) { f.append(k, alanlar[k]); });
    return fetch(yol, { method: "POST", body: f, credentials: "same-origin" });
  }

  function mevcut() {
    return navigator.serviceWorker.ready.then(function (r) { return r.pushManager.getSubscription(); });
  }
  function yenile() {
    return mevcut().then(function (a) {
      gorunum(!!a);
      yaz(a ? "Bildirimler bu cihazda açık." : (Notification.permission === "denied"
        ? "Bildirimler tarayıcı ayarlarından engellenmiş; açmak için site izinlerini değiştirin."
        : "Bildirimler bu cihazda kapalı."));
    });
  }

  ac.addEventListener("click", function () {
    ac.disabled = true;
    Notification.requestPermission().then(function (izin) {
      if (izin !== "granted") { yaz("İzin verilmedi."); ac.disabled = false; return; }
      return fetch("/push/anahtar", { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error("kapali");
        return r.json();
      }).then(function (j) {
        return navigator.serviceWorker.ready.then(function (reg) {
          return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(j.acik) });
        });
      }).then(function (a) {
        var k = a.toJSON().keys || {};
        return gonder("/push/abone", { uc_nokta: a.endpoint, p256dh: k.p256dh, auth: k.auth }).then(function (r) {
          if (!r.ok) { return a.unsubscribe().then(function () { throw new Error("kayit"); }); }
        });
      }).then(yenile);
    }).catch(function () { yaz("Bildirim açılamadı. Biraz sonra tekrar deneyin."); })
      .then(function () { ac.disabled = false; });
  });

  kapat.addEventListener("click", function () {
    mevcut().then(function (a) {
      if (!a) return;
      return gonder("/push/iptal", { uc_nokta: a.endpoint }).then(function () { return a.unsubscribe(); });
    }).then(yenile).catch(function () { yaz("Bildirim kapatılamadı."); });
  });

  dene.addEventListener("click", function () {
    gonder("/push/deneme").then(function (r) { yaz(r.ok ? "Deneme bildirimi gönderildi." : "Deneme gönderilemedi."); });
  });

  yenile();
})();
