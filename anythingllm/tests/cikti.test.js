const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { createRequire } = require("module");

const cikti = require("../skills/_ortak/cikti.js");
const { xlsxBuffer, docxBuffer, dosyaKaydet, guvenliDosyaAdi, SUNUCU } = cikti;

const sunucuRequire = createRequire(path.join(SUNUCU, "package.json"));
const ExcelJS = sunucuRequire("exceljs");
const AdmZip = sunucuRequire("adm-zip");

// Sahte veri (3 sütun, 40 satır, Türkçe karakterli adlar)
const SAHTE_KOLONLAR_3 = ["Öğrenci No", "Adı Soyadı", "Şube"];
const SAHTE_SATIRLAR_40 = [
  ["101", "Çağrı Öztürk", "10-A"],
  ["102", "Şule Aydın", "10-A"],
  ["103", "Yağız Çelik", "10-A"],
  ["104", "Büşra Güneş", "10-A"],
  ["105", "Gökçe İnce", "10-A"],
  ["106", "Oğuzhan Kıraç", "10-A"],
  ["107", "İrem Şimşek", "10-A"],
  ["108", "Ömer Faruk Dağ", "10-A"],
  ["109", "Ayşe Gül Çetin", "10-A"],
  ["110", "Mehmet Ali Koç", "10-A"],
  ["111", "Zeynep Sude Uğur", "10-A"],
  ["112", "Mustafa Can Baş", "10-A"],
  ["113", "Elif Naz Doğru", "10-A"],
  ["114", "Emir Kaan Güler", "10-A"],
  ["115", "Fatma Zehra Taş", "10-A"],
  ["116", "Ahmet Buğra Kurt", "10-A"],
  ["117", "Hatice Kübra Öz", "10-A"],
  ["118", "Burak Emre Şen", "10-A"],
  ["119", "Ceren Yağmur Ak", "10-A"],
  ["120", "Deniz Umut Kaya", "10-A"],
  ["121", "Ece Naz Erdem", "10-A"],
  ["122", "Furkan Berk Tan", "10-A"],
  ["123", "Gamze Nur Doğan", "10-A"],
  ["124", "Hakan Serdar Yiğit", "10-A"],
  ["125", "İsmail Hakkı Polat", "10-A"],
  ["126", "Kadir Sinan Alkan", "10-A"],
  ["127", "Leyla Tuğba Yavuz", "10-A"],
  ["128", "Murat Tarık Çakır", "10-A"],
  ["129", "Nihal Pelin Arslan", "10-A"],
  ["130", "Onur Caner Yıldız", "10-A"],
  ["131", "Pınar Derya Demir", "10-A"],
  ["132", "Ramazan Tolga Kılıç", "10-A"],
  ["133", "Selim Cihan Avcı", "10-A"],
  ["134", "Tuğçe Melis Acar", "10-A"],
  ["135", "Uğur Barış Koçak", "10-A"],
  ["136", "Volkan Metin Özer", "10-A"],
  ["137", "Yasemin Selen Tunç", "10-A"],
  ["138", "Zafer Engin Aslan", "10-A"],
  ["139", "Berke Koray Tekin", "10-A"],
  ["140", "Defne Melike Bulut", "10-A"],
];

const SAHTE_BELGE = {
  okulAdi: "Örnek Anadolu Lisesi",
  baslik: "10-A Sınıfı Öğrenci Listesi",
  mudurAdi: "Ahmet YILMAZ",
  tarih: "27.11.2026",
  ustBilgi: "2026-2027 Eğitim Öğretim Yılı",
};

test("xlsxBuffer: exceljs ile okunur, başlık kalın, frozen pane var, sütun genişlikleri > varsayılan, satır sayısı doğru", async () => {
  const veri = { kolonlar: SAHTE_KOLONLAR_3, satirlar: SAHTE_SATIRLAR_40 };
  const buffer = await xlsxBuffer("10-A Sınıfı Öğrenci Listesi", veri);

  assert.ok(Buffer.isBuffer(buffer), "Dönen değer Buffer olmalı");
  assert.ok(buffer.length > 0, "Buffer boş olmamalı");

  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(buffer);
  const ws = wb.worksheets[0];

  assert.ok(ws, "Çalışma sayfası bulunmalı");

  // Satır sayısı doğru (1 başlık + 1 tablo başlığı + 40 veri satırı = 42)
  assert.equal(ws.rowCount, 42, "Toplam satır sayısı 42 olmalı");

  // İlk satırda başlık ve kalın
  const titleCell = ws.getCell("A1");
  assert.equal(titleCell.value, "10-A Sınıfı Öğrenci Listesi");
  assert.equal(titleCell.font?.bold, true, "İlk satırdaki başlık kalın olmalı");

  // Tablo başlık satırı (2. satır): kalın, dolgu renkli, kenarlıklı
  const headerRow = ws.getRow(2);
  const cell1 = headerRow.getCell(1);
  assert.equal(cell1.font?.bold, true, "Tablo başlık hücresi kalın olmalı");
  assert.equal(cell1.fill?.type, "pattern");
  assert.equal(cell1.fill?.fgColor?.argb, "FF2F5597", "Tablo başlık dolgu rengi doğru olmalı");
  assert.ok(cell1.border?.top && cell1.border?.bottom, "Tablo başlık hücresi kenarlıklı olmalı");

  // Üst satırlar dondurulmuş (frozen pane)
  assert.ok(Array.isArray(ws.views) && ws.views.length > 0, "Sayfa görünüm ayarları bulunmalı");
  const frozenView = ws.views.find((v) => v.state === "frozen");
  assert.ok(frozenView, "Dondurulmuş panel (frozen pane) bulunmalı");
  assert.equal(frozenView.ySplit, 2, "İlk 2 satır dondurulmuş olmalı");

  // Otomatik filtre tanımlı
  assert.ok(ws.autoFilter, "Otomatik filtre tanımlanmış olmalı");

  // Sütun genişlikleri > varsayılan (Excel varsayılanı ~8.43)
  for (let i = 1; i <= SAHTE_KOLONLAR_3.length; i++) {
    const col = ws.getColumn(i);
    assert.ok(col.width > 8.5, `Sütun ${i} genişliği (${col.width}) varsayılandan büyük olmalı`);
  }

  // Türkçe karakterler doğru korunmuş
  assert.equal(ws.getRow(3).getCell(2).value, "Çağrı Öztürk");
  assert.equal(ws.getRow(42).getCell(2).value, "Defne Melike Bulut");
});

test("docxBuffer: zip açılıp word/document.xml'de okul adı, başlık, 40 veri satırı, 'Okul Müdürü' ve tarih bulunur", async () => {
  const veri = { kolonlar: SAHTE_KOLONLAR_3, satirlar: SAHTE_SATIRLAR_40 };
  const buffer = await docxBuffer(SAHTE_BELGE, veri);

  assert.ok(Buffer.isBuffer(buffer), "Dönen değer Buffer olmalı");
  assert.ok(buffer.length > 0, "Buffer boş olmamalı");

  const zip = new AdmZip(buffer);
  const xml = zip.readAsText("word/document.xml");

  // T.C., Okul adı, Başlık, Tarih, Okul Müdürü, Müdür Adı
  assert.ok(xml.includes("T.C."), "XML içinde 'T.C.' bulunmalı");
  assert.ok(xml.includes(SAHTE_BELGE.okulAdi), "XML içinde okul adı bulunmalı");
  assert.ok(xml.includes(SAHTE_BELGE.baslik), "XML içinde liste başlığı bulunmalı");
  assert.ok(xml.includes(SAHTE_BELGE.tarih), "XML içinde tarih bulunmalı");
  assert.ok(xml.includes("Okul Müdürü"), "XML içinde 'Okul Müdürü' bulunmalı");
  assert.ok(xml.includes(SAHTE_BELGE.mudurAdi), "XML içinde müdür adı bulunmalı");
  assert.ok(xml.includes("S.No"), "Tabloda 'S.No' sütun başlığı bulunmalı");

  // Resmi yazı imza bloğu sırası: tarih < müdür adı < "Okul Müdürü"
  const posTarih = xml.indexOf(SAHTE_BELGE.tarih);
  const posMudur = xml.indexOf(SAHTE_BELGE.mudurAdi);
  const posOkulMuduru = xml.indexOf("Okul Müdürü");
  assert.ok(posTarih !== -1, "XML içinde tarih bulunmalı");
  assert.ok(posMudur !== -1, "XML içinde müdür adı bulunmalı");
  assert.ok(posOkulMuduru !== -1, "XML içinde 'Okul Müdürü' bulunmalı");
  assert.ok(
    posTarih < posMudur && posMudur < posOkulMuduru,
    `İmza bloğu sırası hatalı: tarih (${posTarih}) < müdür adı (${posMudur}) < 'Okul Müdürü' (${posOkulMuduru}) olmalı`
  );

  // 40 veri satırının tamamı bulunmalı (Türkçe adlar)
  for (const s of SAHTE_SATIRLAR_40) {
    assert.ok(xml.includes(s[1]), `XML içinde öğrenci '${s[1]}' bulunmalı`);
  }

  // 3 sütun için dikey sayfa düzeni (orient='landscape' OLMAMALI)
  assert.ok(!xml.includes('orient="landscape"'), "3 sütunda sayfa dikey olmalı (landscape olmamalı)");
});

test("docxBuffer: 7 sütunda sayfa yatay (landscape)", async () => {
  const kolonlar7 = ["No", "Ad", "Soyad", "Sınıf", "Şube", "Doğum Tarihi", "Not"];
  const satirlar7 = [
    ["201", "Gökçe", "Şahin", "11", "B", "12.04.2008", "Başarılı"],
    ["202", "Yağız", "Özkan", "11", "B", "23.09.2008", "Teşekkür"],
  ];
  const veri = { kolonlar: kolonlar7, satirlar: satirlar7 };
  const buffer = await docxBuffer(SAHTE_BELGE, veri);

  const zip = new AdmZip(buffer);
  const xml = zip.readAsText("word/document.xml");

  assert.ok(
    xml.includes('orient="landscape"') || xml.includes("w:orient=\"landscape\""),
    "7 sütunda sayfa yatay (landscape) olmalı"
  );
});

test("docxBuffer: okul adı ve müdür adı parametresi boşsa ilgili satırlar atlanır", async () => {
  const veri = { kolonlar: ["Ad Soyad"], satirlar: [["Test Öğrenci"]] };
  const buffer = await docxBuffer({ baslik: "Yalnız Başlık" }, veri);

  const zip = new AdmZip(buffer);
  const xml = zip.readAsText("word/document.xml");

  assert.ok(xml.includes("Yalnız Başlık"), "Başlık XML'de olmalı");
  assert.ok(xml.includes("T.C."), "'T.C.' XML'de olmalı");
  assert.ok(xml.includes("Okul Müdürü"), "'Okul Müdürü' XML'de olmalı");
  assert.ok(!xml.includes("Örnek Anadolu"), "Okul adı verilmediyse XML'de olmamalı");
});

test("guvenliDosyaAdi: .docx, .xlsx, .pdf uzantılarını doğru yönetir", () => {
  assert.equal(guvenliDosyaAdi("liste.docx", "docx"), "liste.docx");
  assert.equal(guvenliDosyaAdi("liste.docx", "xlsx"), "liste.xlsx");
  assert.equal(guvenliDosyaAdi("rapor.xlsx", "docx"), "rapor.docx");
  assert.equal(guvenliDosyaAdi("belge.pdf", "pdf"), "belge.pdf");
  assert.equal(guvenliDosyaAdi("tehlikeli/ad*test?", "docx"), "tehlikeli_ad_test_.docx");
  assert.equal(guvenliDosyaAdi("", "docx", "varsayilan"), "varsayilan.docx");
  assert.equal(guvenliDosyaAdi(null, "xlsx", "tablo"), "tablo.xlsx");
});

test("dosyaKaydet: saveGeneratedFile, fileDownloadCard ve registerOutput akışını yürütür", async () => {
  const gonderilenKartlar = [];
  const kayitliCiktilar = [];

  const mockAgent = {
    socket: {
      send: (olay, veri) => {
        gonderilenKartlar.push({ olay, veri });
      },
    },
  };

  const mockLib = {
    saveGeneratedFile: async ({ fileType, extension, buffer, displayFilename }) => ({
      filename: `${fileType}-uuid123.${extension}`,
      displayFilename,
      fileSize: buffer.length,
      storagePath: `/tmp/${fileType}-uuid123.${extension}`,
    }),
    registerOutput: (aibitat, type, payload) => {
      kayitliCiktilar.push({ type, payload });
    },
  };

  // 1. docx testi -> DocxFileDownload
  const docxKayit = await dosyaKaydet(
    mockAgent,
    "docx",
    Buffer.from("sahte-docx"),
    "liste.docx",
    { lib: mockLib }
  );
  assert.equal(docxKayit.displayFilename, "liste.docx");
  assert.equal(gonderilenKartlar[0].olay, "fileDownloadCard");
  assert.equal(gonderilenKartlar[0].veri.filename, "liste.docx");
  assert.equal(kayitliCiktilar[0].type, "DocxFileDownload");

  // 2. xlsx testi -> ExcelFileDownload
  await dosyaKaydet(
    mockAgent,
    "xlsx",
    Buffer.from("sahte-xlsx"),
    "liste.xlsx",
    { lib: mockLib }
  );
  assert.equal(kayitliCiktilar[1].type, "ExcelFileDownload");

  // 3. pdf testi -> PdfFileDownload
  await dosyaKaydet(
    mockAgent,
    "pdf",
    Buffer.from("sahte-pdf"),
    "liste.pdf",
    { lib: mockLib }
  );
  assert.equal(kayitliCiktilar[2].type, "PdfFileDownload");
});
