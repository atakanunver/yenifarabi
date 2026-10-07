/**
 * Kazanım Testi — Google Apps Script web uygulaması (okulun Google hesabında çalışır).
 * Kurulum: kazanimtest/CLAUDE.md. Sır yok: ANAHTAR Script Properties'te durur.
 *
 * İstek (POST, JSON): {anahtar, baslik, aciklama, sorular:[{metin, secenekler[4], dogru_index, puan}]}
 * Yanıt: {ok:true, form_url, form_kisa_url, form_id, tablo_url} | {ok:false, hata}
 */
var KLASOR_ADI = 'Kazanım Testleri';

function doPost(e) {
  try {
    var istek = JSON.parse(e.postData.contents);
    var anahtar = PropertiesService.getScriptProperties().getProperty('ANAHTAR');
    if (!anahtar || istek.anahtar !== anahtar) {
      return cevap_({ ok: false, hata: 'yetkisiz' });
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

function klasor_() {
  var it = DriveApp.getFoldersByName(KLASOR_ADI);
  return it.hasNext() ? it.next() : DriveApp.createFolder(KLASOR_ADI);
}

function cevap_(nesne) {
  return ContentService.createTextOutput(JSON.stringify(nesne))
    .setMimeType(ContentService.MimeType.JSON);
}
