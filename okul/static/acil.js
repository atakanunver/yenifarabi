// Acil durum: (1) kırmızı şerit ~10 sn'de bir aktif alarmı sorar (yalnızca sekme görünürken); (2) /acil sayfasında
// konum formu GPS'i isteğe bağlı ekler. Metin YALNIZCA textContent ile yazılır (XSS yok).
(function () {
  "use strict";
  if (!window.fetch) return;
  var serit = document.getElementById("acil-serit");
  var sayfa = document.getElementById("konum-form");
  var son = null; // "aktifId:konumId"

  function guncelle(d) {
    var a = d.aktif;
    if (serit) {
      serit.hidden = !a;
      document.getElementById("acil-serit-tur").textContent = a ? ": " + a.tur_ad + (a.tatbikat ? " (TATBİKAT)" : "") : "";
      document.getElementById("acil-serit-kim").textContent = a ? a.ad + " · " + a.saat : "";
    }
    var imza = (a ? a.id : 0) + ":" + d.konum_id;
    if (son !== null && imza !== son && sayfa) { location.reload(); return; }
    son = imza;
  }
  function sor() {
    if (document.hidden) return;
    fetch("/acil/durum", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) guncelle(d); })
      .catch(function () {});
  }
  if (serit || sayfa) { sor(); setInterval(sor, 10000); }

  var ogr = document.getElementById("ogr-acil-form");
  if (ogr) {
    var od = document.getElementById("ogr-durum");
    if (navigator.geolocation) {
      od.textContent = "Konum alınıyor…";
      navigator.geolocation.getCurrentPosition(function (p) {
        document.getElementById("ogr-enlem").value = p.coords.latitude;
        document.getElementById("ogr-boylam").value = p.coords.longitude;
        document.getElementById("ogr-dogruluk").value = Math.round(p.coords.accuracy);
        od.textContent = "Konum alındı (±" + Math.round(p.coords.accuracy) + " m).";
      }, function () { od.textContent = "Konum izni verilmedi; yalnızca adın ve sınıfın gidecek."; },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
    } else { od.textContent = "Bu cihaz konum vermiyor; yalnızca adın ve sınıfın gidecek."; }
    return;
  }
  if (!sayfa) return;
  var kutu = document.getElementById("konum-gps");
  var durum = document.getElementById("konum-durum");
  var enlem = document.getElementById("konum-enlem");
  var boylam = document.getElementById("konum-boylam");
  var dogruluk = document.getElementById("konum-dogruluk");
  function temizle() { enlem.value = boylam.value = dogruluk.value = ""; }
  kutu.addEventListener("change", function () {
    temizle(); durum.textContent = "";
    if (!kutu.checked) return;
    if (!navigator.geolocation) { kutu.checked = false; durum.textContent = "Bu cihaz konum vermiyor; yalnızca yer gönderilecek."; return; }
    durum.textContent = "Konum alınıyor…";
    navigator.geolocation.getCurrentPosition(function (p) {
      enlem.value = p.coords.latitude; boylam.value = p.coords.longitude; dogruluk.value = Math.round(p.coords.accuracy);
      durum.textContent = "Konum eklendi (±" + Math.round(p.coords.accuracy) + " m).";
    }, function () {
      kutu.checked = false; temizle(); durum.textContent = "Konum izni verilmedi; yalnızca yer gönderilecek.";
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
  });
})();
