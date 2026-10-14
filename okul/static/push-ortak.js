// Bildirim aboneliği ortak işlevleri (push.js ve push-kart.js kullanır). İzin YALNIZCA bir kullanıcı eylemi içinden istenir.
(function () {
  "use strict";
  function destekli() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }
  function b64(s) {
    var p = "=".repeat((4 - (s.length % 4)) % 4);
    var r = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
    var o = new Uint8Array(r.length);
    for (var i = 0; i < r.length; i++) o[i] = r.charCodeAt(i);
    return o;
  }
  function gonder(yol, csrf, alanlar) {
    var f = new FormData();
    f.append("csrf", csrf);
    Object.keys(alanlar || {}).forEach(function (k) { f.append(k, alanlar[k]); });
    return fetch(yol, { method: "POST", body: f, credentials: "same-origin" });
  }
  function mevcut() {
    return navigator.serviceWorker.ready.then(function (r) { return r.pushManager.getSubscription(); });
  }
  // Başarıyla abone olunca aboneliği döndürür; izin verilmezse Error("izin"), sunucu reddederse Error("kayit").
  function ac(csrf) {
    return Notification.requestPermission().then(function (izin) {
      if (izin !== "granted") throw new Error("izin");
      return fetch("/push/anahtar", { credentials: "same-origin" });
    }).then(function (r) {
      if (!r.ok) throw new Error("kapali");
      return r.json();
    }).then(function (j) {
      return navigator.serviceWorker.ready.then(function (reg) {
        return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(j.acik) });
      });
    }).then(function (a) {
      var k = a.toJSON().keys || {};
      return gonder("/push/abone", csrf, { uc_nokta: a.endpoint, p256dh: k.p256dh, auth: k.auth }).then(function (r) {
        if (!r.ok) return a.unsubscribe().then(function () { throw new Error("kayit"); });
        return a;
      });
    });
  }
  window.PushOrtak = { destekli: destekli, mevcut: mevcut, ac: ac, gonder: gonder };
})();
