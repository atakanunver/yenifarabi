// Çıkışta bu cihazın bildirim aboneliğini kapatır (paylaşılan telefonda önceki kullanıcıya bildirim gitmesin).
// Çıkışı ASLA engellemez: 1,5 sn içinde bitmezse form olduğu gibi gönderilir.
(function () {
  "use strict";
  var f = document.querySelector('form[action="/cikis"]');
  if (!f || !("serviceWorker" in navigator) || !("PushManager" in window)) return;
  f.addEventListener("submit", function (e) {
    if (f.dataset.hazir) return;
    e.preventDefault();
    var gitti = false;
    function git() {
      if (gitti) return;
      gitti = true;
      f.dataset.hazir = "1";
      f.submit();
    }
    setTimeout(git, 1500);
    navigator.serviceWorker.getRegistration().then(function (r) {
      return r && r.pushManager.getSubscription();
    }).then(function (a) {
      if (!a) return;
      var i = document.createElement("input");
      i.type = "hidden"; i.name = "push_uc"; i.value = a.endpoint;
      f.appendChild(i);
      return a.unsubscribe();
    }).catch(function () {}).then(git);
  });
})();
