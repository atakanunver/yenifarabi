/* sonuc.js - biten oyunun sonucunu yerel sunucuya (POST /api/arena/sonuc) yollar.
 * Veri yalnızca bu makinedeki veri/sonuclar.db'ye yazılır. Asla hata fırlatmaz. */
(function () {
  function yeniKimlik() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  var kimlik = yeniKimlik();

  window.sonucKimlikYenile = function () { kimlik = yeniKimlik(); return kimlik; };

  // katilimcilar: [{ad, puan, tur:'takim'|'ogrenci', uyeler:[...], kazanan:bool}]
  window.sonucGonder = function (oyun, sinif, ders, katilimcilar, ozelKimlik) {
    try {
      fetch('/api/arena/sonuc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          oyun: oyun, sinif: sinif || '', ders: ders || '',
          kimlik: ozelKimlik || kimlik, katilimcilar: katilimcilar || []
        })
      }).catch(function () {});
    } catch (e) { /* sonuç kaydı oyunu asla bozmasın */ }
  };
})();
