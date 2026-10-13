// Kalp atışı: yalnızca sekme GÖRÜNÜRKEN 30 sn'de bir /nabiz'a boş POST (çevrim içi sayısı için). İçerik göndermez.
(function () {
  "use strict";
  var csrf = document.querySelector('input[name="csrf"]');
  if (!csrf || !window.fetch) return;
  function at() {
    if (document.hidden) return;
    var f = new FormData();
    f.append("csrf", csrf.value);
    fetch("/nabiz", { method: "POST", body: f, credentials: "same-origin", keepalive: true }).catch(function () {});
  }
  setInterval(at, 30000);
  document.addEventListener("visibilitychange", at);
  at();
})();
