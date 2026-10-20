// Öğretmen: havuz sorusunu "hatalı" işaretle (fetch). Yeni bildirim soruyu hemen gizler; satır listeden kalkar.
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-isaretle]");
    if (!b) return;
    var kok = b.closest("[data-csrf]");
    var kap = b.closest("[data-isaretle-kap]");
    if (!kok || !kap) return;
    var veri = new FormData();
    veri.set("csrf", kok.dataset.csrf);
    veri.set("soru_id", b.dataset.soruId);
    veri.set("tur", b.dataset.tur);
    veri.set("kaynak", b.dataset.kaynak || "odev");
    kap.querySelectorAll("button").forEach(function (x) { x.disabled = true; });
    fetch("/ogretmen/soru-bildir", { method: "POST", body: veri, credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }, function () { return { ok: false, j: {} }; }); })
      .then(function (s) {
        var satir = b.closest("[data-soru-satir]");
        if (s.ok) {
          if (satir && satir.dataset.soruSatir === "kaldir") { satir.remove(); return; }
          kap.textContent = "Bildirildi, soru artık kullanılmayacak.";
        } else {
          kap.textContent = (s.j && s.j.mesaj) || "Bildirim gönderilemedi.";
        }
      })
      .catch(function () { kap.textContent = "Bağlantı sorunu."; });
  });
})();
