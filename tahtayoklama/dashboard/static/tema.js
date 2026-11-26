// Tema ve duvar kağıdı seçimi: localStorage'da saklanır; Ayarlar › Temalar menüsü (menu.js) farabiTemaUygula /
// farabiDuvarUygula'yı çağırır. Sayfa boyanmadan önceki uygulama (FOUC önleme) taban.html <head>'indeki satır içi betikte.
(function () {
  var ANAHTAR = "farabi_yoklama_tema";
  var DUVAR_ANAHTAR = "farabi_duvar_kagidi";
  var ANIMASYON_ANAHTAR = "farabi_animasyon";
  var ANIMASYONLAR = ["acik", "oto", "kapali"];
  // Tek kaynak menu.TEMALAR: taban.html listeyi window.FARABI_TEMALAR ile verir; yoksa bu yedek liste.
  var TEMALAR = window.FARABI_TEMALAR || ["cam", "sade-koyu", "kurumsal", "lacivert", "argon", "argon-koyu", "material", "material-koyu", "black", "koyu"];
  var VARSAYILAN = "cam";
  // 2026-10-23: klasik/yumuşak kaldırıldı; eski kayıtlar Argon açığa eşlenir.
  var ESKI = { klasik: "argon", yumusak: "argon" };
  // Duvar kağıtları panel_duvar.liste() → window.FARABI_DUVAR ([{ad, url}]); "yok" = yalnız renk geçişi
  var DUVARLAR = window.FARABI_DUVAR || [];

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

  function duvarBul(ad) {
    for (var i = 0; i < DUVARLAR.length; i++) if (DUVARLAR[i].ad === ad) return DUVARLAR[i];
    return null;
  }
  function aktifDuvarGetir() {
    var kayitli = null;
    try { kayitli = localStorage.getItem(DUVAR_ANAHTAR); } catch (e) { /* kapalı depolama */ }
    if (kayitli === "yok" || duvarBul(kayitli)) return kayitli;
    return DUVARLAR.length ? DUVARLAR[0].ad : "yok";
  }
  function duvarUygula(ad) {
    var d = duvarBul(ad);
    if (!d) ad = "yok";
    var kok = document.documentElement;
    kok.dataset.duvar = ad;
    if (d) kok.style.setProperty("--duvar-resmi", 'url("' + d.url + '")');
    else kok.style.removeProperty("--duvar-resmi");
    try { localStorage.setItem(DUVAR_ANAHTAR, ad); } catch (e) { /* kapalı depolama */ }
    document.querySelectorAll('[data-eylem^="duvar:"]').forEach(function (buton) {
      buton.setAttribute("aria-checked", buton.dataset.eylem === "duvar:" + ad ? "true" : "false");
    });
  }
  window.farabiDuvarUygula = duvarUygula;

  function aktifAnimasyonGetir() {
    var kayitli = null;
    try { kayitli = localStorage.getItem(ANIMASYON_ANAHTAR); } catch (e) { /* kapalı depolama */ }
    return ANIMASYONLAR.indexOf(kayitli) !== -1 ? kayitli : "acik";
  }
  function animasyonUygula(mod) {
    if (ANIMASYONLAR.indexOf(mod) === -1) mod = "acik";
    document.documentElement.dataset.animasyon = mod;
    try { localStorage.setItem(ANIMASYON_ANAHTAR, mod); } catch (e) { /* kapalı depolama */ }
    document.querySelectorAll('[data-eylem^="animasyon:"]').forEach(function (buton) {
      buton.setAttribute("aria-checked", buton.dataset.eylem === "animasyon:" + mod ? "true" : "false");
    });
    try { window.dispatchEvent(new CustomEvent("farabi-animasyon", { detail: mod })); } catch (e) { /* eski tarayıcı */ }
  }
  window.farabiAnimasyonUygula = animasyonUygula;

  document.addEventListener("DOMContentLoaded", function () {
    temaUygula(aktifTemaGetir());
    duvarUygula(aktifDuvarGetir());
    animasyonUygula(aktifAnimasyonGetir());
    document.querySelectorAll(".tema-secici button").forEach(function (buton) {
      buton.addEventListener("click", function () { temaUygula(buton.dataset.tema); });
    });
  });
})();
