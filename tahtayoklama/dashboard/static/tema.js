// Tema seçimi: localStorage'da saklanır; Görünüm › Tema menüsü (menu.js) farabiTemaUygula'yı çağırır.
// Sayfa boyanmadan önceki uygulama (FOUC önleme) taban.html <head>'indeki satır içi betikte.
(function () {
  var ANAHTAR = "farabi_yoklama_tema";
  var TEMALAR = ["klasik", "yumusak", "koyu"];

  function aktifTemaGetir() {
    var kayitli = null;
    try { kayitli = localStorage.getItem(ANAHTAR); } catch (e) { /* kapalı depolama */ }
    return TEMALAR.indexOf(kayitli) !== -1 ? kayitli : "koyu";  // varsayılan koyu (2026-10-08, kullanıcı)
  }

  function temaUygula(tema) {
    if (TEMALAR.indexOf(tema) === -1) return;
    document.documentElement.dataset.tema = tema;
    try {
      localStorage.setItem(ANAHTAR, tema);
    } catch (e) {
      /* localStorage kapalıysa sessizce yok say, tema yine de uygulanır */
    }
    document.querySelectorAll('[data-eylem^="tema:"]').forEach(function (buton) {
      buton.setAttribute("aria-checked", buton.dataset.eylem === "tema:" + tema ? "true" : "false");
    });
    // Giriş sayfası kabuksuz; eski .tema-secici butonları orada duruyor.
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.classList.toggle("aktif", buton.dataset.tema === tema);
    });
  }
  window.farabiTemaUygula = temaUygula;

  document.addEventListener("DOMContentLoaded", function () {
    temaUygula(aktifTemaGetir());
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.addEventListener("click", function () { temaUygula(buton.dataset.tema); });
    });
  });
})();
