// Atos: SQL sonucunu doğrudan Excel/PDF dosyasına çevirir (sınıf listesi, yoklama/devamsızlık raporu, telefon listesi…).
// Satırları sunucu çeker; model satır yazmaz (uzun listelerde hata/atlama olmaz). Ortak mantık: ../_ortak/okul.js
const okul = require("../_ortak/okul.js");

module.exports.runtime = {
  handler: async function ({ sorgu, dosya_adi = "liste", bicim = "xlsx", baslik = "" }) {
    try {
      const tur = String(bicim).toLowerCase() === "pdf" ? "pdf" : "xlsx";
      this.introspect(`Veri çekiliyor, ${tur.toUpperCase()} dosyası hazırlanacak…`);
      const veri = await okul.sorgula(sorgu, this.runtimeArgs || {}, 2000);
      if (!veri.satirlar.length) return "Sorgu çalıştı, eşleşen kayıt yok; dosya üretilmedi.";

      const gorunenAd = okul.guvenliDosyaAdi(dosya_adi, tur, "liste");
      const baslikMetni = baslik || gorunenAd.replace(/\.(xlsx|pdf)$/i, "");
      const buffer = tur === "pdf" ? await okul.pdfBuffer(baslikMetni, veri) : await okul.xlsxBuffer(baslikMetni, veri);

      const lib = okul.dosyaKutuphanesi();
      const kayit = await lib.saveGeneratedFile({
        fileType: tur,
        extension: tur,
        buffer,
        displayFilename: gorunenAd,
      });
      this.super.socket.send("fileDownloadCard", {
        filename: kayit.displayFilename,
        storageFilename: kayit.filename,
        fileSize: kayit.fileSize,
      });
      lib.registerOutput(this.super, tur === "pdf" ? "PdfFileDownload" : "ExcelFileDownload", {
        filename: kayit.displayFilename,
        storageFilename: kayit.filename,
        fileSize: kayit.fileSize,
      });
      this.introspect(`"${gorunenAd}" hazır.`);
      const not = veri.kesildi ? ` (en çok ${veri.satirlar.length} satır; sorguyu daraltın)` : "";
      return `Dosya hazır: "${gorunenAd}" — ${veri.satirlar.length} satır${not}. İndirme kartı sohbette gösterildi.`;
    } catch (e) {
      return `Dosya üretilemedi: ${e.message}`;
    }
  },
};
