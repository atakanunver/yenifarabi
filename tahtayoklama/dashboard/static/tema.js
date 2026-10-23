// Tema seçimi: localStorage'da saklanır; Görünüm › Tema menüsü (menu.js) farabiTemaUygula'yı çağırır.
// Sayfa boyanmadan önceki uygulama (FOUC önleme) taban.html <head>'indeki satır içi betikte.
(function () {
  var ANAHTAR = "farabi_yoklama_tema";
  var TEMALAR = ["argon", "argon-koyu", "koyu"];
  // 2026-10-23: klasik/yumuşak kaldırıldı; eski kayıtlar Argon açığa eşlenir.
  var ESKI = { klasik: "argon", yumusak: "argon" };

  function aktifTemaGetir() {
    var kayitli = null;
    try { kayitli = localStorage.getItem(ANAHTAR); } catch (e) { /* kapalı depolama */ }
    if (ESKI[kayitli]) kayitli = ESKI[kayitli];
    if (TEMALAR.indexOf(kayitli) !== -1) return kayitli;
    // Kayıt yoksa sistem tercihi (2026-10-23; önceki varsayılan Taş Tahta idi).
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "argon-koyu" : "argon";
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
