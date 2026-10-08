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
    if (m.getType() === FormApp.ItemType.TEXT && m.getTitle() === 'Okul numarası') {
      okulId = m.getId();
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
