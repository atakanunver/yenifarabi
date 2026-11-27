// Atos agent yetenekleri için ortak Word/Excel/PDF çıktı motoru.
// exceljs ve docx paketleri /opt/anythingllm/app/server altından yüklenir.
const path = require("path");
const { createRequire } = require("module");

const VARSAYILAN_SUNUCU = "/opt/anythingllm/app/server";
const SUNUCU = process.env.ANYTHINGLLM_SERVER || process.env.SUNUCU || VARSAYILAN_SUNUCU;

function getSunucu() {
  return process.env.ANYTHINGLLM_SERVER || process.env.SUNUCU || SUNUCU;
}

function sunucuRequire(modulAdi) {
  const sunucuYolu = getSunucu();
  const req = createRequire(path.join(sunucuYolu, "package.json"));
  return req(modulAdi);
}

function dosyaKutuphanesi() {
  const sunucuYolu = getSunucu();
  return require(path.join(sunucuYolu, "utils/agents/aibitat/plugins/create-files/lib.js"));
}

function temizMetin(val) {
  if (val === null || val === undefined) return "";
  return String(val).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "");
}

function normalizeVeri(veri) {
  const kolonlar = Array.isArray(veri?.kolonlar) ? veri.kolonlar : [];
  const hamSatirlar = Array.isArray(veri?.satirlar) ? veri.satirlar : [];
  const satirlar = hamSatirlar.map((s) => {
    if (Array.isArray(s)) return s;
    if (s && typeof s === "object") return kolonlar.map((k) => s[k]);
    return [s];
  });
  return { kolonlar, satirlar };
}

function guvenliDosyaAdi(ad, uzanti = "xlsx", varsayilan = "liste") {
  const normUzanti = String(uzanti || "xlsx").toLowerCase().replace(/^\./, "");
  let temiz = String(ad || varsayilan)
    .replace(/[\\/:*?"<>|\r\n]+/g, "_")
    .trim()
    .replace(/\.(xlsx|docx|pdf)$/i, "");
  if (!temiz) temiz = varsayilan;
  return `${temiz.slice(0, 80)}.${normUzanti}`;
}

async function xlsxBuffer(baslik, veri) {
  const ExcelJS = sunucuRequire("exceljs");
  const kitap = new ExcelJS.Workbook();
  kitap.creator = "Atos";
  kitap.created = new Date();

  const { kolonlar, satirlar } = normalizeVeri(veri);

  const baslikMetni = temizMetin(typeof baslik === "string" ? baslik.trim() : (baslik?.baslik || ""));
  const sayfaAdi = baslikMetni.replace(/[*?:\\/[\]]/g, "_").slice(0, 31) || "Liste";
  const sayfa = kitap.addWorksheet(sayfaAdi);

  let headerRowIndex = 1;

  if (baslikMetni) {
    const titleRow = sayfa.addRow([baslikMetni]);
    titleRow.height = 28;
    if (kolonlar.length > 1) {
      sayfa.mergeCells(1, 1, 1, kolonlar.length);
    }
    const cell = sayfa.getCell("A1");
    cell.font = { name: "Calibri", bold: true, size: 13, color: { argb: "FF1F4E79" } };
    cell.alignment = { vertical: "middle", horizontal: "center" };
    headerRowIndex = 2;
  }

  const headerRow = sayfa.addRow(kolonlar.map((k) => temizMetin(k)));
  headerRow.height = 24;
  headerRow.eachCell((c) => {
    c.font = { name: "Calibri", bold: true, color: { argb: "FFFFFFFF" }, size: 11 };
    c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF2F5597" } };
    c.alignment = { vertical: "middle", horizontal: "center" };
    c.border = {
      top: { style: "thin", color: { argb: "FF1F4E79" } },
      left: { style: "thin", color: { argb: "FF1F4E79" } },
      bottom: { style: "thin", color: { argb: "FF1F4E79" } },
      right: { style: "thin", color: { argb: "FF1F4E79" } },
    };
  });

  for (const s of satirlar) {
    const r = sayfa.addRow(s.map((h) => (h === undefined ? null : temizMetin(h))));
    r.eachCell((c) => {
      c.font = { name: "Calibri", size: 10 };
      c.border = {
        top: { style: "thin", color: { argb: "FFD9D9D9" } },
        left: { style: "thin", color: { argb: "FFD9D9D9" } },
        bottom: { style: "thin", color: { argb: "FFD9D9D9" } },
        right: { style: "thin", color: { argb: "FFD9D9D9" } },
      };
    });
  }

  sayfa.columns.forEach((sutun, i) => {
    let enUzun = String(kolonlar[i] ?? "").length;
    for (const s of satirlar) {
      enUzun = Math.max(enUzun, String(s[i] ?? "").length);
    }
    sutun.width = Math.min(Math.max(enUzun + 4, 12), 50);
  });

  sayfa.views = [{ state: "frozen", ySplit: headerRowIndex }];

  if (kolonlar.length > 0) {
    const sonSatir = headerRowIndex + satirlar.length;
    sayfa.autoFilter = {
      from: { row: headerRowIndex, column: 1 },
      to: { row: Math.max(sonSatir, headerRowIndex), column: kolonlar.length },
    };
  }

  return Buffer.from(await kitap.xlsx.writeBuffer());
}

async function docxBuffer(belge = {}, veri = {}) {
  const docx = sunucuRequire("docx");
  const {
    Document,
    Packer,
    Paragraph,
    TextRun,
    Table,
    TableRow,
    TableCell,
    AlignmentType,
    WidthType,
    BorderStyle,
    PageOrientation,
    VerticalAlign,
  } = docx;

  const ayar = typeof belge === "string" ? { baslik: belge } : (belge || {});
  const { kolonlar, satirlar } = normalizeVeri(veri);

  // A4 dikey (6+ sütunda yatay)
  const isLandscape = kolonlar.length >= 6;

  const children = [];

  // Üstte ortalı "T.C."
  children.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [
        new TextRun({
          text: "T.C.",
          bold: true,
          size: 24, // 12pt
        }),
      ],
    })
  );

  // Okul adı: parametre boşsa yalnız o satır atlanır (ASLA kodda sabit değil)
  const okulAdi = temizMetin(ayar.okulAdi ? String(ayar.okulAdi).trim() : "");
  if (okulAdi) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 60 },
        children: [
          new TextRun({
            text: okulAdi,
            bold: true,
            size: 24,
          }),
        ],
      })
    );
  }

  // Üst bilgi (opsiyonel)
  const ustBilgi = temizMetin(ayar.ustBilgi ? String(ayar.ustBilgi).trim() : "");
  if (ustBilgi) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 60 },
        children: [
          new TextRun({
            text: ustBilgi,
            size: 20,
          }),
        ],
      })
    );
  }

  // Liste başlığı
  const baslik = temizMetin(ayar.baslik ? String(ayar.baslik).trim() : "");
  if (baslik) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 180 },
        children: [
          new TextRun({
            text: baslik,
            bold: true,
            size: 24,
          }),
        ],
      })
    );
  }

  // "S.No" sütunlu kenarlıklı tablo (başlık satırı kalın, her sayfada tekrar)
  const borderDef = { style: BorderStyle.SINGLE, size: 1, color: "7F7F7F" };
  const tabloKolonlari = ["S.No", ...kolonlar];

  const headerCells = tabloKolonlari.map((kolonAdi) => {
    return new TableCell({
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({
              text: temizMetin(kolonAdi),
              bold: true,
              size: 20, // 10pt
            }),
          ],
        }),
      ],
      shading: {
        fill: "F2F2F2",
      },
      verticalAlign: VerticalAlign.CENTER,
    });
  });

  const headerRow = new TableRow({
    tableHeader: true,
    cantSplit: true,
    children: headerCells,
  });

  const dataRows = satirlar.map((s, idx) => {
    const rowValues = [String(idx + 1), ...s];
    const cells = rowValues.map((val, colIdx) => {
      return new TableCell({
        children: [
          new Paragraph({
            alignment: colIdx === 0 ? AlignmentType.CENTER : AlignmentType.LEFT,
            children: [
              new TextRun({
                text: temizMetin(val),
                size: 19, // 9.5pt
              }),
            ],
          }),
        ],
        verticalAlign: VerticalAlign.CENTER,
      });
    });
    return new TableRow({
      cantSplit: true,
      children: cells,
    });
  });

  const table = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: borderDef,
      bottom: borderDef,
      left: borderDef,
      right: borderDef,
      insideHorizontal: borderDef,
      insideVertical: borderDef,
    },
    rows: [headerRow, ...dataRows],
  });

  children.push(table);

  // Altta sağda tarih → imza için ~3 boş satır → müdür adı (boşsa satır atlanır) → "Okul Müdürü"
  // Okul adı/müdür adı ASLA kodda sabit değil; parametre boşsa yalnız o satır atlanır.
  const tarihMetni = ayar.tarih !== undefined
    ? temizMetin(String(ayar.tarih).trim())
    : new Date().toLocaleDateString("tr-TR");

  if (tarihMetni) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        spacing: { before: 240, after: 60 },
        children: [
          new TextRun({
            text: tarihMetni,
            size: 22,
          }),
        ],
      })
    );
  } else {
    children.push(
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        spacing: { before: 240 },
        children: [],
      })
    );
  }

  // İmza için ~3 boş satır
  for (let i = 0; i < 3; i++) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [],
      })
    );
  }

  // Müdür adı (boşsa satır atlanır)
  const mudurAdi = temizMetin(ayar.mudurAdi ? String(ayar.mudurAdi).trim() : "");
  if (mudurAdi) {
    children.push(
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        spacing: { after: 60 },
        children: [
          new TextRun({
            text: mudurAdi,
            size: 22,
          }),
        ],
      })
    );
  }

  // "Okul Müdürü"
  children.push(
    new Paragraph({
      spacing: { after: 60 },
      alignment: AlignmentType.RIGHT,
      children: [
        new TextRun({
          text: "Okul Müdürü",
          bold: true,
          size: 22,
        }),
      ],
    })
  );

  const doc = new Document({
    sections: [
      {
        properties: {
          page: {
            size: {
              orientation: isLandscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT,
            },
          },
        },
        children,
      },
    ],
  });

  return await Packer.toBuffer(doc);
}

const CIKTI_TURLERI = {
  xlsx: "ExcelFileDownload",
  docx: "DocxFileDownload",
  pdf: "PdfFileDownload",
};

async function dosyaKaydet(agent, tur, buffer, gorunenAd, secenekler = {}) {
  const normTur = String(tur || "xlsx").toLowerCase().replace(/^\./, "");
  const lib = secenekler.lib || dosyaKutuphanesi();
  if (!lib) throw new Error("Dosya kütüphanesine ulaşılamadı.");

  const kayit = await lib.saveGeneratedFile({
    fileType: normTur,
    extension: normTur,
    buffer,
    displayFilename: gorunenAd,
  });

  const payload = {
    filename: kayit.displayFilename,
    storageFilename: kayit.filename,
    fileSize: kayit.fileSize,
  };

  const aibitat = agent?.super || agent || {};
  const socket = aibitat.socket || agent?.socket;

  if (socket && typeof socket.send === "function") {
    socket.send("fileDownloadCard", payload);
  }

  const ciktiTuru = CIKTI_TURLERI[normTur] || "FileDownload";
  if (typeof lib.registerOutput === "function") {
    lib.registerOutput(aibitat, ciktiTuru, payload);
  }

  return kayit;
}

module.exports = {
  SUNUCU,
  guvenliDosyaAdi,
  xlsxBuffer,
  docxBuffer,
  dosyaKaydet,
  dosyaKutuphanesi,
};
