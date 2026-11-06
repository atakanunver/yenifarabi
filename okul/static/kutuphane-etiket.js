// Demirbaş etiketleri: QR kod tarayıcıda (ZXing) çizilir; içerik "KTP-<demirbaş>".
(function () {
  "use strict";
  var yazici = window.ZXing ? new window.ZXing.BrowserQRCodeSvgWriter() : null;
  document.querySelectorAll(".ktp-etiket .qr").forEach(function (q) {
    if (!yazici) { q.textContent = q.dataset.kod; return; }
    try { q.appendChild(yazici.write(q.dataset.kod, 120, 120)); } catch (e) { q.textContent = q.dataset.kod; }
  });
  var tus = document.querySelector("[data-yazdir]");
  if (tus) tus.addEventListener("click", function () { window.print(); });
})();
