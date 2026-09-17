// Tema seçimi: localStorage'da saklanır, .tema-secici içindeki butonlarla değiştirilir.
// Sayfa boyanmadan önceki uygulama (FOUC önleme) her şablonun <head>'inde ayrı bir
// inline script ile yapılır; bu dosya yalnızca buton etkileşimini yönetir.
(function () {
  var ANAHTAR = "farabi_yoklama_tema";
  var TEMALAR = ["klasik", "yumusak", "koyu"];

  function aktifTemaGetir() {
    var kayitli = localStorage.getItem(ANAHTAR);
    return TEMALAR.indexOf(kayitli) !== -1 ? kayitli : "klasik";
  }

  function temaUygula(tema) {
    document.documentElement.dataset.tema = tema;
    try {
      localStorage.setItem(ANAHTAR, tema);
    } catch (e) {
      /* localStorage kapalıysa sessizce yok say, tema yine de uygulanır */
    }
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.classList.toggle("aktif", buton.dataset.tema === tema);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    temaUygula(aktifTemaGetir());
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.addEventListener("click", function () {
        temaUygula(buton.dataset.tema);
      });
    });
  });
})();
