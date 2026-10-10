/* Vesikalık: yüklemeden önce telefonda 400 piksele küçültülüp JPEG'e çevrilir (veli/öğrenci mobil verisi
 * korunur, sunucuya kütüphane gerekmez). Tarayıcı desteklemezse dosya olduğu gibi gönderilir; sunucu yine doğrular. */
(function () {
  "use strict";
  var girdi = document.getElementById("foto");
  var onizleme = document.getElementById("foto-onizleme");
  if (!girdi || !window.FileReader || !window.DataTransfer || !HTMLCanvasElement.prototype.toBlob) return;
  var AZAMI = 400;

  girdi.addEventListener("change", function () {
    var dosya = girdi.files && girdi.files[0];
    if (!dosya || !/^image\/(jpeg|png|webp)$/.test(dosya.type)) return;
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
        dt.items.add(new File([blob], "vesikalik.jpg", { type: "image/jpeg" }));
        girdi.files = dt.files;
        if (onizleme) { onizleme.src = URL.createObjectURL(blob); onizleme.hidden = false; }
      }, "image/jpeg", 0.85);
    };
    resim.onerror = function () { URL.revokeObjectURL(adres); };
    resim.src = adres;
  });
})();
