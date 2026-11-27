const okul = require("../_ortak/okul.js");
const cikti = require("../_ortak/cikti.js");

async function listeSorgula(govde, ayar) {
  let yanit;
  try {
    yanit = await fetch(ayar.OKUL_API_URL || "http://127.0.0.1/api/okul/liste", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Farabi-Okul-Key": ayar.OKUL_API_KEY || "",
        "X-Farabi-Kullanici": "atos",
        "X-Farabi-Rol": "admin",
      },
      body: JSON.stringify(govde),
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new Error("Okul veri servisine ulaşılamadı.");
  }
  if (yanit.status === 403) throw new Error("Okul verisine yalnızca yönetici erişebilir.");
  const veri = await yanit.json().catch(() => null);
  if (yanit.status === 400) throw new Error(veri?.hata || veri?.detail || "Liste isteği geçersiz.");
  if (!yanit.ok || !Array.isArray(veri?.satirlar)) throw new Error("Okul veri servisine ulaşılamadı.");
  return veri;
}

module.exports.runtime = {
  handler: async function ({ tur, sinif, sube, ders, ogretmen_adi, kulup_adi, brans, aranan, cikti_formati = "metin", dosya_adi }) {
    try {
      if (typeof tur === "string") {
        tur = tur.toLocaleLowerCase("tr").replaceAll("ı", "i");
        const turler = new Map([["kulüp", "kulup"], ["öğretmen", "ogretmen"], ["öğrenci", "ogrenci"]]);
        tur = turler.get(tur) ?? tur;
      }
      cikti_formati = String(cikti_formati).toLowerCase();
      if (cikti_formati === "word") cikti_formati = "docx";
      if (cikti_formati === "excel") cikti_formati = "xlsx";
      if (!["metin", "xlsx", "docx", "pdf"].includes(cikti_formati)) return "Çıktı biçimi metin, xlsx, docx veya pdf olmalı.";
      const veri = await listeSorgula({ tur, sinif, sube, ders, ogretmen_adi, kulup_adi, brans, aranan }, this.runtimeArgs || {});
      if (!veri.satirlar.length) return "Sorgu çalıştı, eşleşen kayıt yok.";
      if (cikti_formati === "metin") return okul.tabloMetni(veri);

      const ad = cikti.guvenliDosyaAdi(dosya_adi, cikti_formati, veri.baslik);
      let buffer;
      if (cikti_formati === "docx") {
        const tarih = new Date().toLocaleDateString("tr-TR", { timeZone: "Europe/Istanbul" });
        buffer = await cikti.docxBuffer({ baslik: veri.baslik, okulAdi: veri.okul_adi, mudurAdi: veri.mudur_adi, tarih }, veri);
      } else if (cikti_formati === "xlsx") {
        buffer = await cikti.xlsxBuffer(veri.baslik, veri);
      } else {
        buffer = await okul.pdfBuffer(veri.baslik, veri);
      }
      await cikti.dosyaKaydet(this, cikti_formati, buffer, ad);
      return `Dosya hazır: "${ad}" (${veri.satir_sayisi} satır). İndirme kartı sohbette gösterildi.`;
    } catch (e) {
      return e.message;
    }
  },
};
