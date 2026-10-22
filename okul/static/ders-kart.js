// Canlı ders kartı: geri sayım. Süre, sunucu saatine göre düzeltilir (telefon saati yanlış olabilir).
// JS yoksa kart sunucunun yazdığı başlangıç/bitiş saatini gösterir.
(function () {
  var kart = document.getElementById("ders-kart");
  var sayac = document.getElementById("ders-sayac");
  if (!kart || !sayac) return;
  var hedef = parseInt(kart.dataset.hedef, 10);
  var sunucu = parseInt(kart.dataset.sunucu, 10);
  if (!hedef || !sunucu) return;
  var fark = sunucu - Date.now();
  var yenilendi = false;

  // Sonsuz yenileme koruması: son 30 sn içinde zaten yenilendiyse (saat sapması vb.) tekrar yenileme.
  function yenilenebilir() {
    try {
      var son = parseInt(sessionStorage.getItem("dersKartYenile") || "0", 10);
      if (Date.now() - son < 30000) return false;
      sessionStorage.setItem("dersKartYenile", "" + Date.now());
    } catch (e) {}
    return true;
  }
  function iki(n) { return n < 10 ? "0" + n : "" + n; }
  function yaz() {
    var kalan = Math.round((hedef - (Date.now() + fark)) / 1000);
    if (kalan <= 0) {
      sayac.textContent = "00:00";
      if (!yenilendi && yenilenebilir()) { yenilendi = true; setTimeout(function () { location.reload(); }, 1500); }
      return;
    }
    var s = kalan % 60, d = Math.floor(kalan / 60) % 60, sa = Math.floor(kalan / 3600);
    sayac.textContent = (sa ? sa + ":" + iki(d) : iki(d)) + ":" + iki(s);
  }
  yaz();
  setInterval(yaz, 1000);
})();
