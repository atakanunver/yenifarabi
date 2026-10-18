/* Ödev cevap fotoğrafı: yüklemeden önce telefonda en uzun kenar 1600 piksele küçültülüp JPEG'e çevrilir
 * (5 MB sınırı aşılmasın; sunucu HEIC kabul etmez). Tarayıcı desteklemezse dosya olduğu gibi gönderilir. */
(function () {
  "use strict";
  var form = document.querySelector("form[data-foto-odev]");
  if (!form || !window.DataTransfer || !HTMLCanvasElement.prototype.toBlob) return;
  var girdi = form.querySelector("input[type=file]");
  var onizleme = form.querySelector("[data-onizleme]");
  var AZAMI = 1600;

  girdi.addEventListener("change", function () {
    var dosya = girdi.files && girdi.files[0];
    if (!dosya) return;
    var resim = new Image();
    var adres = URL.createObjectURL(dosya);
    resim.onload = function () {
      var oran = Math.min(1, AZAMI / Math.max(resim.width, resim.height));
      var tuval = document.createElement("canvas");
      tuval.width = Math.round(resim.width * oran);
      tuval.height = Math.round(resim.height * oran);
      tuval.getContext("2d").drawImage(resim, 0, 0, tuval.width, tuval.height);
      URL.revokeObjectURL(adres);
      tuval.toBlob(function (blob) {
        if (!blob) return;
        var dt = new DataTransfer();
        dt.items.add(new File([blob], "cevap.jpg", { type: "image/jpeg" }));
        girdi.files = dt.files;
        if (onizleme) { onizleme.src = URL.createObjectURL(blob); onizleme.hidden = false; }
      }, "image/jpeg", 0.85);
    };
    resim.onerror = function () { URL.revokeObjectURL(adres); };
    resim.src = adres;
  });
})();
