// Atos: tek fonksiyonlu okul veri sorgusu (salt-okunur SELECT). Ortak mantık: ../_ortak/okul.js
const okul = require("../_ortak/okul.js");

module.exports.runtime = {
  handler: async function ({ sorgu }) {
    try {
      this.introspect("Okul kayıtlarında sorgu çalıştırılıyor…");
      const veri = await okul.sorgula(sorgu, this.runtimeArgs || {});
      return okul.tabloMetni(veri);
    } catch (e) {
      // Hata metni modele okunur halde döner: sorguyu düzeltip yeniden denesin.
      return e.message;
    }
  },
};
