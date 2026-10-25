// Atos agent yetenekleri için ortak yardımcılar: dashboard /api/okul/sql ucu ve dosya kütüphaneleri.
// Yetki ve güvenlik sunucuda (tahtayoklama/dashboard/okul_sql.py): salt-okunur, izinli tablolar, satır sınırı.
const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");
const { pathToFileURL } = require("url");

const SUNUCU = "/opt/anythingllm/app/server";
const sunucuRequire = createRequire(path.join(SUNUCU, "package.json"));

async function sorgula(sorgu, ayar, azamiSatir) {
  if (typeof sorgu !== "string" || !sorgu.trim()) throw new Error("Sorgu boş; bir SELECT yazın.");
  const govde = { sorgu };
  if (azamiSatir) govde.azami_satir = azamiSatir;
  let yanit;
  try {
    yanit = await fetch(ayar.OKUL_API_URL || "http://127.0.0.1/api/okul/sql", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Farabi-Okul-Key": ayar.OKUL_API_KEY || "",
        "X-Farabi-Kullanici": "atos",
        "X-Farabi-Rol": "admin", // tek kullanıcı modu: parolayı bilen yönetici
      },
      body: JSON.stringify(govde),
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new Error("Okul veri servisine ulaşılamadı.");
  }
  let veri = null;
  try {
    veri = await yanit.json();
  } catch {
    /* gövde JSON değil */
  }
  if (yanit.status === 400 && veri && veri.hata) throw new Error(`Sorgu çalışmadı: ${veri.hata}`);
  if (yanit.status === 403) throw new Error("Okul verisine bu hesapla erişilemez (yalnızca yönetici).");
  if (!yanit.ok || !veri || !Array.isArray(veri.satirlar)) throw new Error("Okul veri servisine ulaşılamadı.");
  return veri; // {kolonlar, satirlar, kesildi}
}

function tabloMetni(veri, azamiKarakter = 12000) {
  if (!veri.satirlar.length) return "Sorgu çalıştı, eşleşen kayıt yok.";
  const satirlar = [veri.kolonlar.join(" | ")];
  for (const s of veri.satirlar) satirlar.push(s.map((h) => (h === null || h === undefined ? "" : String(h))).join(" | "));
  let metin = satirlar.join("\n");
  if (metin.length > azamiKarakter) metin = metin.slice(0, azamiKarakter) + "\n…(çıktı kısaltıldı; sorguyu daraltın)";
  if (veri.kesildi) metin += `\n(Yalnızca ilk ${veri.satirlar.length} satır gösterildi; LIMIT/WHERE ile daraltın.)`;
  return metin;
}

function guvenliDosyaAdi(ad, uzanti, varsayilan) {
  let temiz = String(ad || varsayilan).replace(/[\\/:*?"<>|\r\n]+/g, "_").trim().replace(/\.(xlsx|pdf)$/i, "");
  if (!temiz) temiz = varsayilan;
  return `${temiz.slice(0, 80)}.${uzanti}`;
}

async function xlsxBuffer(baslik, veri) {
  const ExcelJS = sunucuRequire("exceljs");
  const kitap = new ExcelJS.Workbook();
  kitap.creator = "Atos";
  kitap.created = new Date();
  const sayfaAdi = String(baslik || "Liste").replace(/[*?:\\/[\]]/g, "_").slice(0, 31) || "Liste";
  const sayfa = kitap.addWorksheet(sayfaAdi);
  sayfa.addRow(veri.kolonlar);
  for (const s of veri.satirlar) sayfa.addRow(s.map((h) => (h === undefined ? null : h)));
  const baslikSatiri = sayfa.getRow(1);
  baslikSatiri.font = { bold: true, color: { argb: "FFFFFFFF" } };
  baslikSatiri.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF2F5597" } };
  sayfa.views = [{ state: "frozen", ySplit: 1 }];
  sayfa.columns.forEach((sutun, i) => {
    let enUzun = String(veri.kolonlar[i] ?? "").length;
    for (const s of veri.satirlar) enUzun = Math.max(enUzun, String(s[i] ?? "").length);
    sutun.width = Math.min(Math.max(enUzun + 2, 8), 50);
  });
  return Buffer.from(await kitap.xlsx.writeBuffer());
}

async function pdfBuffer(baslik, veri) {
  const girdi = path.join(SUNUCU, "node_modules/@mintplex-labs/mdpdf/index.js");
  const { markdownToPdf } = await import(pathToFileURL(girdi).href);
  const hucre = (h) => (h === null || h === undefined ? "" : String(h)).replace(/\|/g, "/").replace(/\r?\n/g, " ");
  const tarih = new Date().toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" });
  const md = [
    `# ${baslik || "Liste"}`,
    "",
    `| ${veri.kolonlar.map(hucre).join(" | ")} |`,
    `|${veri.kolonlar.map(() => "---").join("|")}|`,
    ...veri.satirlar.map((s) => `| ${s.map(hucre).join(" | ")} |`),
    "",
    `${veri.satirlar.length} kayıt — Atos, ${tarih}`,
  ].join("\n");
  return Buffer.from(await markdownToPdf(md));
}

function dosyaKutuphanesi() {
  return require(path.join(SUNUCU, "utils/agents/aibitat/plugins/create-files/lib.js"));
}

module.exports = { sorgula, tabloMetni, guvenliDosyaAdi, xlsxBuffer, pdfBuffer, dosyaKutuphanesi, fs };
