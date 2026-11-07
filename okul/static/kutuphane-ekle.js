// Kitap Ekle: kamera ISBN okuyunca forma yazar; eser kayıtlıysa (yoksa internetten bulunursa) bilgileri doldurur (yalnızca boş alanları).
(function () {
  "use strict";
  var form = document.getElementById("ekle-form"), durum = document.getElementById("isbn-durum");
  var kok = document.querySelector("[data-kamera]");
  if (!form || !kok) return;
  var kamera = window.KtpKamera(kok, function (kod) {
    if (/^KTP-/i.test(kod)) { durum.textContent = "Bu bir demirbaş etiketi; ISBN barkodunu okutun."; kamera.yeniden(); return; }
    var temiz = kod.replace(/[\s-]/g, "");
    if (!/^(\d{13}|\d{9}[\dXx])$/.test(temiz)) { durum.textContent = "ISBN okunamadı: " + kod; kamera.yeniden(); return; }
    form.elements.isbn.value = temiz;
    kamera.durdur();
    durum.textContent = "Aranıyor…";
    fetch("/kutuphane/api/isbn?isbn=" + encodeURIComponent(temiz), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (v) {
        if (v.kitap) {
          ["baslik", "yazar", "yayinevi", "tur"].forEach(function (a) { if (!form.elements[a].value) form.elements[a].value = v.kitap[a] || ""; });
          durum.textContent = "Bu eser kayıtlı: " + v.kitap.baslik + ". Yeni nüshanın demirbaş numarasını yazın.";
        } else if (v.dis) {
          ["baslik", "yazar", "yayinevi"].forEach(function (a) { if (!form.elements[a].value) form.elements[a].value = v.dis[a] || ""; });
          durum.textContent = "İnternetten bulundu: " + v.dis.baslik + ". Bilgileri kontrol edip demirbaş numarasını yazın.";
        } else {
          durum.textContent = "Yeni eser: ISBN yazıldı, diğer bilgileri girin.";
        }
        form.elements.demirbas.focus();
      })
      .catch(function () { durum.textContent = "ISBN yazıldı (sunucuya sorulamadı)."; });
  });
})();
