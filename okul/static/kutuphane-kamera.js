// Kütüphane kamerası: barkod/QR tarayıcıda çözülür, görüntü sunucuya GİTMEZ (yalnızca okunan metin).
// Yerleşik BarcodeDetector varsa (Android Chrome, masaüstü Chrome) o; yoksa (iPhone Safari, Firefox) ZXing.
// Bir kod okununca kilitlenir (tek işlem); çağıran `yeniden()` deyince yeni okuma alınır. Elle giriş her zaman çalışır.
(function () {
  "use strict";
  var BICIMLER = ["ean_13", "ean_8", "code_128", "qr_code"];
  var ZXING = "/static/vendor/zxing-0.21.3.min.js";
  var zxingSoz = null;

  function zxingYukle() {
    if (window.ZXing) return Promise.resolve();
    if (!zxingSoz) {
      zxingSoz = new Promise(function (ok, hata) {
        var s = document.createElement("script");
        s.src = ZXING;
        s.onload = ok;
        s.onerror = function () { zxingSoz = null; hata(); };
        document.head.appendChild(s);
      });
    }
    return zxingSoz;
  }

  function yerelDedektor() {
    if (!("BarcodeDetector" in window)) return Promise.resolve(null);
    return window.BarcodeDetector.getSupportedFormats().then(function (destek) {
      var f = BICIMLER.filter(function (b) { return destek.indexOf(b) >= 0; });
      return f.indexOf("ean_13") >= 0 ? new window.BarcodeDetector({ formats: f }) : null;
    }).catch(function () { return null; });
  }

  function hafiza(ad, deger) {
    try {
      if (deger === undefined) return localStorage.getItem(ad);
      localStorage.setItem(ad, deger);
    } catch (e) { /* özel pencere: yok say */ }
    return null;
  }

  window.KtpKamera = function (kok, okununca) {
    var kap = kok.querySelector(".ktp-video"), video = kok.querySelector("video");
    var ac = kok.querySelector("[data-kamera-ac]"), kapat = kok.querySelector("[data-kamera-kapat]");
    var sec = kok.querySelector("[data-kamera-sec]"), durum = kok.querySelector("[data-kamera-durum]");
    var elle = kok.querySelector("[data-elle]");
    var akis = null, zx = null, zamanlayici = 0, kilit = false, sonKod = "", sonZaman = 0, nesil = 0;

    function yaz(m) { durum.textContent = m; }

    function bildir(kod, elden) {
      kod = String(kod || "").trim();
      if (!kod || (kilit && !elden)) return;
      var t = Date.now();
      if (!elden && kod === sonKod && t - sonZaman < 3000) return; // aynı barkod kamerada kalınca ikinci kez sayılmaz
      sonKod = kod; sonZaman = t; kilit = true;
      if (!elden && navigator.vibrate) navigator.vibrate(60);
      okununca(kod);
    }

    function durdur() {
      nesil++;
      clearTimeout(zamanlayici);
      if (zx) { try { zx.reset(); } catch (e) { /* yok say */ } zx = null; }
      if (akis) akis.getTracks().forEach(function (t) { t.stop(); });
      akis = null;
      video.srcObject = null;
      kap.hidden = true; kapat.hidden = true; ac.hidden = false;
    }

    function cihazlar() {
      if (!navigator.mediaDevices.enumerateDevices) return Promise.resolve();
      return navigator.mediaDevices.enumerateDevices().then(function (liste) {
        var kameralar = liste.filter(function (d) { return d.kind === "videoinput"; });
        var aktif = akis && akis.getVideoTracks()[0] && akis.getVideoTracks()[0].getSettings().deviceId;
        sec.textContent = "";
        kameralar.forEach(function (d, i) {
          var o = document.createElement("option");
          o.value = d.deviceId;
          o.textContent = d.label || ("Kamera " + (i + 1));
          o.selected = d.deviceId === aktif;
          sec.appendChild(o);
        });
        sec.hidden = kameralar.length < 2;
      }).catch(function () { /* yok say */ });
    }

    function baslat(cihazId) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        yaz(window.isSecureContext ? "Bu tarayıcı kamerayı desteklemiyor; numarayı elle yazın."
          : "Kamera yalnızca güvenli bağlantıda (https://smual.app) açılır; numarayı elle yazın.");
        return;
      }
      durdur();
      var benim = nesil;
      kilit = false;
      var v = cihazId ? { deviceId: { exact: cihazId } } : { facingMode: { ideal: "environment" } };
      v.width = { ideal: 1280 }; v.height = { ideal: 720 };
      yaz("Kamera açılıyor…");
      navigator.mediaDevices.getUserMedia({ audio: false, video: v }).then(function (s) {
        if (benim !== nesil) { s.getTracks().forEach(function (t) { t.stop(); }); return; }
        akis = s;
        video.srcObject = s;
        kap.hidden = false; ac.hidden = true; kapat.hidden = false;
        var oynat = video.play();
        if (oynat && oynat.catch) oynat.catch(function () { /* iOS: kullanıcı dokunuşuyla başlar */ });
        cihazlar();
        return yerelDedektor().then(function (ded) {
          if (benim !== nesil) return;
          if (ded) {
            yaz("Barkodu çerçeveye tutun.");
            var tara = function () {
              if (benim !== nesil) return;
              var bitti = function () { zamanlayici = setTimeout(tara, 160); };
              if (kilit || video.readyState < 2) { bitti(); return; }
              ded.detect(video).then(function (k) { if (k.length) bildir(k[0].rawValue); }).catch(function () {}).then(bitti);
            };
            tara();
            return;
          }
          yaz("Okuyucu yükleniyor…");
          return zxingYukle().then(function () {
            if (benim !== nesil) return;
            var Z = window.ZXing, ipucu = new Map();
            ipucu.set(Z.DecodeHintType.POSSIBLE_FORMATS, [Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.EAN_8, Z.BarcodeFormat.CODE_128, Z.BarcodeFormat.QR_CODE]);
            ipucu.set(Z.DecodeHintType.TRY_HARDER, true);
            zx = new Z.BrowserMultiFormatReader(ipucu, 200);
            yaz("Barkodu çerçeveye tutun.");
            zx.decodeFromStream(s, video, function (sonuc) { if (sonuc && !kilit) bildir(sonuc.getText()); });
          }, function () { yaz("Okuyucu yüklenemedi; numarayı elle yazın."); });
        });
      }).catch(function (e) {
        var ad = e && e.name;
        yaz(ad === "NotAllowedError" ? "Kamera izni verilmedi. Tarayıcı ayarlarından izin verin ya da numarayı elle yazın."
          : ad === "NotFoundError" || ad === "OverconstrainedError" ? "Kamera bulunamadı; numarayı elle yazın."
          : ad === "NotReadableError" ? "Kamera başka bir uygulamada açık; kapatıp tekrar deneyin."
          : "Kamera açılamadı; numarayı elle yazın.");
        durdur();
      });
    }

    ac.addEventListener("click", function () { baslat(hafiza("ktp-kamera")); });
    kapat.addEventListener("click", function () { durdur(); yaz(""); });
    sec.addEventListener("change", function () { hafiza("ktp-kamera", sec.value); baslat(sec.value); });
    elle.addEventListener("submit", function (e) {
      e.preventDefault();
      var g = elle.elements.kod;
      bildir(g.value, true);
      g.value = "";
    });
    document.addEventListener("visibilitychange", function () { if (document.hidden && akis) { durdur(); yaz("Kamera kapatıldı."); } });

    return {
      yeniden: function () { kilit = false; },
      durdur: durdur,
      acik: function () { return !!akis; },
      odakla: function () { elle.elements.kod.focus(); },
    };
  };
})();
