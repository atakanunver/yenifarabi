// Veli izin formu: seçilen aralığın okul günü sayısını canlı gösterir (yalnız bilgi; kayıtta sunucu hesaplar).
(function () {
  var bas = document.getElementById("baslangic"), bit = document.getElementById("bitis"), cikti = document.getElementById("izin-gun");
  if (!bas || !bit || !cikti) return;
  function guncelle() {
    if (!bas.value || !bit.value) return;
    fetch("/veli/izin/gun?baslangic=" + encodeURIComponent(bas.value) + "&bitis=" + encodeURIComponent(bit.value), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { gun: null }; })
      .then(function (v) {
        cikti.textContent = v.gun === null ? "Geçerli bir aralık seçin (en çok 30 gün)." :
          v.gun === 0 ? "Seçilen tarihlerde okul günü yok." : "Okul günü: " + v.gun + " gün (otomatik hesaplanır).";
      })
      .catch(function () {});
  }
  bas.addEventListener("change", guncelle);
  bit.addEventListener("change", guncelle);
  guncelle();
})();
