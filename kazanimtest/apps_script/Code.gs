/**
 * Kazanım Testi — Google Apps Script web uygulaması (okulun Google hesabında çalışır).
 * Kurulum: kazanimtest/CLAUDE.md. Sır yok: ANAHTAR Script Properties'te durur.
 *
 * İstek (POST, JSON): {anahtar, baslik, aciklama, sorular:[{metin, secenekler[4], dogru_index, puan}]}
 * Yanıt: {ok:true, form_url, form_kisa_url, form_id, tablo_url} | {ok:false, hata}
 *
 * İstek (POST, JSON): {anahtar, islem:'sonuclar', form_id}
 * Yanıt: {ok:true, cevaplar:[{zaman:ISO, okul_no:string, secimler:[şık metni|null,...]}]}
 *   secimler = formdaki çoktan seçmeli maddelerin sırasıyla; boş bırakılan madde null.
 *
 * İstek (POST, JSON): {anahtar, islem:'rapor_yaz', raporlar:[{token, ay, sinif, okul_no, son_gecerlilik, veri}]}
 * Yanıt: {ok:true, yazilan:n, linkler:{<token>:"https://docs.google.com/document/d/<id>/view"}}.
 *   Her token için bir Google Dokümanı ("bağlantıya sahip herkes görüntüleyebilir"), Kazanım Testleri/Raporlar
 *   klasöründe; tekrar çağrıda aynı doküman güncellenir (link değişmez). Süresi dolanların dokümanı çöpe gider.
 *   "Kazanım Raporları" e-tablosu (id: Script Properties RAPOR_TABLO_ID) token→doc_id kaydını tutar.
 *   Gizlilik: veri YALNIZCA sınıf + okul no + kazanım sonuçları; isim/telefon yoktur.
 *
 * GET ?r=<token>: ESKİ HTML rapor sayfası (yedek; çoklu Google hesabında açılmıyor — asıl yol Doküman linki).
 */
var KLASOR_ADI = 'Kazanım Testleri';

function doPost(e) {
  try {
    var istek = JSON.parse(e.postData.contents);
    var anahtar = PropertiesService.getScriptProperties().getProperty('ANAHTAR');
    if (!anahtar || istek.anahtar !== anahtar) {
      return cevap_({ ok: false, hata: 'yetkisiz' });
    }
    if (istek.islem === 'sonuclar') {
      return cevap_(sonuclar_(istek.form_id));
    }
    if (istek.islem === 'rapor_yaz') {
      return cevap_(rapor_yaz_(istek.raporlar));
    }
    if (!istek.sorular || !istek.sorular.length) {
      return cevap_({ ok: false, hata: 'soru yok' });
    }

    var form = FormApp.create(istek.baslik || 'Kazanım Testi');
    form.setDescription(istek.aciklama || '');
    form.setIsQuiz(true);
    form.setLimitOneResponsePerUser(false);   // oturum açma zorunlu değil
    form.setCollectEmail(false);
    form.setShowLinkToRespondAgain(false);
    // Workspace hesabında form varsayılan "yalnızca kuruluş içi" olabilir; öğrenci kendi
    // telefonundan oturumsuz girebilmeli. Kişisel hesapta bu çağrı yok/hata verir → yut.
    try { form.setRequireLogin(false); } catch (x) {}
    // Yeni Forms yayınlama modeli: yayınlanmamış form yanıt almaz.
    try { form.setPublished(true); } catch (x) {}

    var no = form.addTextItem();
    no.setTitle('Okul numarası').setRequired(true);
    no.setValidation(FormApp.createTextValidation()
      .setHelpText('Yalnızca sayı giriniz.')
      .requireNumber()
      .build());

    istek.sorular.forEach(function (s) {
      var madde = form.addMultipleChoiceItem();
      madde.setTitle(s.metin).setRequired(true).setPoints(s.puan || 10);
      madde.setChoices(s.secenekler.map(function (secenek, i) {
        return madde.createChoice(String(secenek), i === s.dogru_index);
      }));
    });

    var tablo = SpreadsheetApp.create((istek.baslik || 'Kazanım Testi') + ' (Yanıtlar)');
    form.setDestination(FormApp.DestinationType.SPREADSHEET, tablo.getId());

    var klasor = klasor_();
    DriveApp.getFileById(form.getId()).moveTo(klasor);
    DriveApp.getFileById(tablo.getId()).moveTo(klasor);

    var url = form.getPublishedUrl();
    var kisa = '';
    try { kisa = form.shortenFormUrl(url); } catch (x) { kisa = url; }
    return cevap_({
      ok: true,
      form_url: url,
      form_kisa_url: kisa,
      form_id: form.getId(),
      tablo_url: tablo.getUrl()
    });
  } catch (err) {
    return cevap_({ ok: false, hata: String(err) });
  }
}

function sonuclar_(formId) {
  var form = FormApp.openById(formId);
  var maddeler = form.getItems();
  var okulId = null;
  var mcIdler = [];               // MC maddelerinin id'leri, formdaki sırayla
  maddeler.forEach(function (m) {
    if (m.getType() === FormApp.ItemType.TEXT) {
      var baslik = (m.getTitle() || '').trim().toLowerCase();
      if (baslik === 'okul numarası' || baslik.indexOf('okul') >= 0 || baslik.indexOf('numara') >= 0 || okulId === null) {
        okulId = m.getId();
      }
    } else if (m.getType() === FormApp.ItemType.MULTIPLE_CHOICE) {
      mcIdler.push(m.getId());
    }
  });
  var cevaplar = form.getResponses().map(function (r) {
    var harita = {};              // madde id -> yanıt (getItemResponses boş maddeyi atlayabilir)
    r.getItemResponses().forEach(function (ir) {
      harita[ir.getItem().getId()] = ir.getResponse();
    });
    var no = okulId !== null && harita[okulId] !== undefined ? String(harita[okulId]) : '';
    return {
      zaman: r.getTimestamp().toISOString(),
      okul_no: no,
      secimler: mcIdler.map(function (id) {
        var v = harita[id];
        return (v === undefined || v === null || v === '') ? null : String(v);
      })
    };
  });
  return { ok: true, cevaplar: cevaplar };
}

function klasor_() {
  var it = DriveApp.getFoldersByName(KLASOR_ADI);
  return it.hasNext() ? it.next() : DriveApp.createFolder(KLASOR_ADI);
}

function cevap_(nesne) {
  return ContentService.createTextOutput(JSON.stringify(nesne))
    .setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------- Aylık rapor

var RAPOR_TABLO_ADI = 'Kazanım Raporları';
var RAPOR_SUTUNLAR = ['token', 'ay', 'sinif', 'okul_no', 'son_gecerlilik', 'veri_json', 'yazilma', 'doc_id'];
var RAPOR_ALT_KLASOR = 'Raporlar';

function rapor_sayfa_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('RAPOR_TABLO_ID');
  var tablo;
  if (id) {
    tablo = SpreadsheetApp.openById(id);
  } else {
    tablo = SpreadsheetApp.create(RAPOR_TABLO_ADI);
    props.setProperty('RAPOR_TABLO_ID', tablo.getId());
    DriveApp.getFileById(tablo.getId()).moveTo(klasor_());
  }
  var sayfa = tablo.getSheets()[0];
  if (sayfa.getLastRow() === 0) {
    sayfa.getRange(1, 1, 1, RAPOR_SUTUNLAR.length).setValues([RAPOR_SUTUNLAR]);
    // token / ay / son_gecerlilik metin kalsın (e-tablo tarihe çevirmesin)
    sayfa.getRange('A:B').setNumberFormat('@');
    sayfa.getRange('E:E').setNumberFormat('@');
  } else if (!sayfa.getRange(1, RAPOR_SUTUNLAR.length).getValue()) {
    // eski 7 sütunlu tablo: doc_id başlığını ekle (eski satırlarda hücre boş kalır)
    sayfa.getRange(1, RAPOR_SUTUNLAR.length).setValue('doc_id');
  }
  return sayfa;
}

function rapor_satiri_bul_(sayfa, token) {
  if (!token || sayfa.getLastRow() < 2) { return 0; }
  var bulunan = sayfa.getRange(1, 1, sayfa.getLastRow(), 1)
    .createTextFinder(String(token)).matchEntireCell(true).matchCase(true).findNext();
  return bulunan && bulunan.getRow() > 1 ? bulunan.getRow() : 0;
}

function tarih_metni_(sg) {
  if (sg instanceof Date) { return Utilities.formatDate(sg, 'Europe/Istanbul', 'yyyy-MM-dd'); }
  return String(sg).substr(0, 10);
}

function rapor_klasoru_() {
  var ust = klasor_();
  var it = ust.getFoldersByName(RAPOR_ALT_KLASOR);
  return it.hasNext() ? it.next() : ust.createFolder(RAPOR_ALT_KLASOR);
}

function rapor_yaz_(raporlar) {
  if (!raporlar || !raporlar.length) { return { ok: false, hata: 'rapor yok' }; }
  var kilit = LockService.getScriptLock();
  if (!kilit.tryLock(30000)) { return { ok: false, hata: 'meşgul, sonra tekrar deneyin' }; }
  try {
    var sayfa = rapor_sayfa_();
    var simdi = new Date().toISOString();
    var yazilan = 0;
    var linkler = {};
    var klasor = null;
    raporlar.forEach(function (r) {
      if (!r.token) { return; }
      var no = rapor_satiri_bul_(sayfa, r.token);
      var docId = no ? String(sayfa.getRange(no, RAPOR_SUTUNLAR.length).getValue() || '') : '';
      var doc = null;
      if (docId) {
        try { doc = DocumentApp.openById(docId); } catch (x) { doc = null; }
        if (doc && DriveApp.getFileById(docId).isTrashed()) { doc = null; }
      }
      var baslik = 'Kazanım raporu – ' + String(r.sinif) + ' – Okul no ' + String(r.okul_no) + ' – ' +
                   String((r.veri || {}).ay_adi || r.ay);
      if (doc) {
        doc.setName(baslik);
      } else {
        doc = DocumentApp.create(baslik);
        docId = doc.getId();
        if (!klasor) { klasor = rapor_klasoru_(); }
        DriveApp.getFileById(docId).moveTo(klasor);
        DriveApp.getFileById(docId).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      }
      rapor_doc_yaz_(doc, r.veri || {});
      doc.saveAndClose();
      var satir = [String(r.token), String(r.ay), String(r.sinif), Number(r.okul_no),
                   String(r.son_gecerlilik), JSON.stringify(r.veri || {}), simdi, docId];
      if (no) {
        sayfa.getRange(no, 1, 1, satir.length).setValues([satir]);
      } else {
        sayfa.appendRow(satir);
      }
      linkler[String(r.token)] = 'https://docs.google.com/document/d/' + docId + '/view';
      yazilan += 1;
    });
    try { suresi_dolanlari_temizle_(sayfa); } catch (x) {}
    return { ok: true, yazilan: yazilan, linkler: linkler };
  } finally {
    kilit.releaseLock();
  }
}

// son_gecerlilik < bugün olan satırların dokümanını çöpe at, doc_id'yi boşalt (satır kalır).
function suresi_dolanlari_temizle_(sayfa) {
  var son = sayfa.getLastRow();
  if (son < 2) { return; }
  var bugun = Utilities.formatDate(new Date(), 'Europe/Istanbul', 'yyyy-MM-dd');
  var sutun = RAPOR_SUTUNLAR.length;
  var veri = sayfa.getRange(2, 1, son - 1, sutun).getValues();
  veri.forEach(function (h, i) {
    var docId = String(h[sutun - 1] || '');
    var sg = tarih_metni_(h[4]);
    if (!docId || !sg || sg >= bugun) { return; }
    try { DriveApp.getFileById(docId).setTrashed(true); } catch (x) {}
    sayfa.getRange(i + 2, sutun).setValue('');
  });
}

var DOC_GRI = '#566170';

function rapor_paragraf_(govde, metin, renk, boyut) {
  var p = govde.appendParagraph(String(metin));
  p.setHeading(DocumentApp.ParagraphHeading.NORMAL);
  p.editAsText().setFontSize(boyut || 11).setForegroundColor(renk || '#1f2933').setBold(false);
  return p;
}

function rapor_doc_yaz_(doc, v) {
  var govde = doc.getBody();
  govde.clear();
  var g = v.genel || {};
  govde.appendParagraph('Kazanım raporu').setHeading(DocumentApp.ParagraphHeading.HEADING1);
  rapor_paragraf_(govde, String(v.sinif) + ' · Okul no ' + String(v.okul_no) + ' · ' + String(v.ay_adi), DOC_GRI);
  rapor_paragraf_(govde, 'Genel doğru oranı: %' + yuzde_(g.oran) + ' (sınıf ortalaması %' + yuzde_(g.sinif_orani) +
                  ') · Katıldığın test: ' + String(g.test_sayisi), '#1f2933', 12).editAsText().setBold(true);
  (v.dersler || []).forEach(function (d) {
    govde.appendParagraph(String(d.ders)).setHeading(DocumentApp.ParagraphHeading.HEADING2);
    rapor_paragraf_(govde, 'Senin oranın %' + yuzde_(d.oran) + ' · Sınıf ortalaması %' + yuzde_(d.sinif_orani), DOC_GRI);
    var hucreler = [['Kazanım', 'Oran', 'Durum']];
    (d.kazanimlar || []).forEach(function (k) {
      hucreler.push([String(k.kazanim_satiri), '%' + yuzde_(k.oran), DURUM_ETIKET[k.durum] || 'Az veri']);
    });
    var tablo = govde.appendTable(hucreler);
    for (var c = 0; c < 3; c++) { tablo.getCell(0, c).editAsText().setBold(true); }
    (d.kazanimlar || []).forEach(function (k, i) {
      var r = DURUM_RENK[k.durum] || DURUM_RENK.az_veri;
      var hucre = tablo.getCell(i + 1, 2);
      hucre.setBackgroundColor(r[0]);
      hucre.editAsText().setForegroundColor(r[1]).setBold(true);
    });
  });
  var sayfalar = [];
  (v.eksikler || []).forEach(function (k) {
    (k.sayfalar || []).forEach(function (s) { if (sayfalar.indexOf(s) < 0) { sayfalar.push(s); } });
  });
  govde.appendParagraph('Tekrar etmen gereken sayfalar').setHeading(DocumentApp.ParagraphHeading.HEADING2);
  if (sayfalar.length) {
    sayfalar.forEach(function (s) { govde.appendListItem(String(s)).setGlyphType(DocumentApp.GlyphType.BULLET); });
  } else {
    rapor_paragraf_(govde, 'Bu ay tekrar önerilen sayfa yok.', DOC_GRI);
  }
  govde.appendParagraph('Güçlü olduğun kazanımlar').setHeading(DocumentApp.ParagraphHeading.HEADING2);
  if ((v.gucluler || []).length) {
    v.gucluler.forEach(function (k) {
      govde.appendListItem(String(k.ders) + ': ' + String(k.kazanim_satiri)).setGlyphType(DocumentApp.GlyphType.BULLET);
    });
  } else {
    rapor_paragraf_(govde, 'Bu ay güçlü sayılan kazanım yok.', DOC_GRI);
  }
  rapor_paragraf_(govde, 'Bu rapor okulumuzun kazanım testlerinden otomatik hazırlanmıştır.', '#8a94a0', 9);
}

function doGet(e) {
  var token = e && e.parameter ? e.parameter.r : '';
  var kayit = null;
  try { kayit = rapor_oku_(token); } catch (err) { kayit = null; }
  if (!kayit) {
    return sayfa_('<p class="bos">Rapor bulunamadı ya da süresi doldu.</p>');
  }
  return sayfa_(rapor_html_(kayit));
}

function rapor_oku_(token) {
  if (!token || !PropertiesService.getScriptProperties().getProperty('RAPOR_TABLO_ID')) { return null; }
  var sayfa = rapor_sayfa_();
  var no = rapor_satiri_bul_(sayfa, token);
  if (!no) { return null; }
  var h = sayfa.getRange(no, 1, 1, RAPOR_SUTUNLAR.length).getValues()[0];
  var sg = h[4];
  if (sg instanceof Date) {
    sg = Utilities.formatDate(sg, 'Europe/Istanbul', 'yyyy-MM-dd');
  } else {
    sg = String(sg).substr(0, 10);
  }
  var bugun = Utilities.formatDate(new Date(), 'Europe/Istanbul', 'yyyy-MM-dd');
  if (!sg || bugun > sg) { return null; }
  return JSON.parse(h[5]);
}

function kacis_(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function yuzde_(oran) {
  var n = Number(oran);
  if (!isFinite(n)) { n = 0; }
  return Math.max(0, Math.min(100, Math.round(n * 100)));
}

var DURUM_ETIKET = { eksik: 'Eksik', orta: 'Orta', guclu: 'Güçlü', az_veri: 'Az veri' };
var DURUM_RENK = {
  eksik: ['#fde8e8', '#b42318', '#e5484d'],
  orta: ['#fef3c7', '#92400e', '#e0a100'],
  guclu: ['#dcfce7', '#166534', '#2e9e5b'],
  az_veri: ['#eef0f3', '#566170', '#aab2bd']
};

function cubuk_(oran, renk) {
  return '<div class="cubuk"><div class="dolgu" style="width:' + yuzde_(oran) + '%;background:' + renk + '"></div></div>';
}

function rapor_html_(v) {
  var h = [];
  h.push('<h1>Kazanım raporu</h1>');
  h.push('<p class="alt">' + kacis_(v.sinif) + ' &middot; Okul no ' + kacis_(v.okul_no) + ' &middot; ' + kacis_(v.ay_adi) + '</p>');
  var g = v.genel || {};
  h.push('<div class="kart"><h2>Genel doğru oranı</h2>');
  h.push('<p class="buyuk">%' + yuzde_(g.oran) + '</p>' + cubuk_(g.oran, '#2f6fdb'));
  h.push('<p class="kucuk">Sınıf ortalaması: %' + yuzde_(g.sinif_orani) + ' &middot; Katıldığın test: ' + kacis_(g.test_sayisi) + '</p></div>');
  (v.dersler || []).forEach(function (d) {
    h.push('<div class="kart"><h2>' + kacis_(d.ders) + '</h2>');
    h.push('<p class="kucuk">Senin oranın: %' + yuzde_(d.oran) + ' &middot; Sınıf ortalaması: %' + yuzde_(d.sinif_orani) + '</p>');
    (d.kazanimlar || []).forEach(function (k) {
      var r = DURUM_RENK[k.durum] || DURUM_RENK.az_veri;
      h.push('<div class="kaz"><div class="kaz-ust"><span class="kaz-ad">' + kacis_(k.kazanim_satiri) + '</span>' +
             '<span class="rozet" style="background:' + r[0] + ';color:' + r[1] + '">' + kacis_(DURUM_ETIKET[k.durum] || 'Az veri') + '</span></div>' +
             cubuk_(k.oran, r[2]) + '<span class="kucuk">%' + yuzde_(k.oran) + '</span></div>');
    });
    h.push('</div>');
  });
  var sayfalar = [];
  (v.eksikler || []).forEach(function (k) {
    (k.sayfalar || []).forEach(function (s) { if (sayfalar.indexOf(s) < 0) { sayfalar.push(s); } });
  });
  h.push('<div class="kart"><h2>Tekrar etmen gereken sayfalar</h2>');
  if (sayfalar.length) {
    h.push('<ul>' + sayfalar.map(function (s) { return '<li>' + kacis_(s) + '</li>'; }).join('') + '</ul>');
  } else {
    h.push('<p class="kucuk">Bu ay tekrar önerilen sayfa yok.</p>');
  }
  h.push('</div>');
  h.push('<div class="kart"><h2>Güçlü olduğun kazanımlar</h2>');
  if ((v.gucluler || []).length) {
    h.push('<ul>' + v.gucluler.map(function (k) {
      return '<li>' + kacis_(k.ders) + ': ' + kacis_(k.kazanim_satiri) + '</li>';
    }).join('') + '</ul>');
  } else {
    h.push('<p class="kucuk">Bu ay güçlü sayılan kazanım yok.</p>');
  }
  h.push('</div>');
  h.push('<p class="not">Bu rapor okulumuzun kazanım testlerinden otomatik hazırlanmıştır.</p>');
  return h.join('');
}

var SAYFA_CSS = 'body{margin:0;background:#f5f7fa;color:#1f2933;font-family:Arial,Helvetica,sans-serif;line-height:1.45}' +
  '.sar{max-width:640px;margin:0 auto;padding:16px}h1{font-size:22px;margin:8px 0 2px}h2{font-size:17px;margin:0 0 8px}' +
  '.alt{color:#566170;margin:0 0 14px}.kart{background:#fff;border:1px solid #e1e5ea;border-radius:10px;padding:14px;margin-bottom:12px}' +
  '.buyuk{font-size:30px;font-weight:bold;margin:0 0 6px}.kucuk{font-size:13px;color:#566170;margin:6px 0 0}' +
  '.cubuk{height:10px;background:#e8ebef;border-radius:6px;overflow:hidden}.dolgu{height:100%}' +
  '.kaz{margin-top:12px}.kaz-ust{display:flex;justify-content:space-between;gap:8px;margin-bottom:5px}' +
  '.kaz-ad{font-size:14px}.rozet{font-size:12px;font-weight:bold;padding:2px 8px;border-radius:10px;white-space:nowrap;align-self:flex-start}' +
  'ul{margin:0;padding-left:20px}li{margin-bottom:4px;font-size:14px}.not{font-size:12px;color:#566170;text-align:center;margin:16px 0}' +
  '.bos{text-align:center;margin-top:60px;font-size:16px}';

function sayfa_(govde) {
  var html = '<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>Kazanım raporu</title>' +
    '<style>' + SAYFA_CSS + '</style></head><body><div class="sar">' + govde + '</div></body></html>';
  return HtmlService.createHtmlOutput(html)
    .setTitle('Kazanım raporu')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
