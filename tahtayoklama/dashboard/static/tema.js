// Tema seçimi: localStorage'da saklanır; Görünüm › Tema menüsü (menu.js) farabiTemaUygula'yı çağırır.
// Sayfa boyanmadan önceki uygulama (FOUC önleme) taban.html <head>'indeki satır içi betikte.
(function () {
  var ANAHTAR = "farabi_yoklama_tema";
  // Tek kaynak menu.TEMALAR: taban.html listeyi window.FARABI_TEMALAR ile verir; yoksa bu yedek liste.
  var TEMALAR = window.FARABI_TEMALAR || ["sade-koyu", "kurumsal", "lacivert", "argon", "argon-koyu", "material", "material-koyu", "black", "koyu"];
  var VARSAYILAN = "sade-koyu";
  // 2026-10-23: klasik/yumuşak kaldırıldı; eski kayıtlar Argon açığa eşlenir.
  var ESKI = { klasik: "argon", yumusak: "argon" };

  function aktifTemaGetir() {
    var kayitli = null;
    try { kayitli = localStorage.getItem(ANAHTAR); } catch (e) { /* kapalı depolama */ }
    if (ESKI[kayitli]) kayitli = ESKI[kayitli];
    return TEMALAR.indexOf(kayitli) !== -1 ? kayitli : VARSAYILAN;
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
  // Tema döngü düğmesi: listeyi sırayla gezer.
  window.farabiTemaSonraki = function () {
    var i = TEMALAR.indexOf(document.documentElement.dataset.tema);
    temaUygula(TEMALAR[(i + 1) % TEMALAR.length]);
  };

  document.addEventListener("DOMContentLoaded", function () {
    temaUygula(aktifTemaGetir());
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.addEventListener("click", function () { temaUygula(buton.dataset.tema); });
    });
  });
})();
