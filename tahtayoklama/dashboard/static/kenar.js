// Kenar çubuğu: mobilde aç/kapat + sidebar altındaki mini sistem durumu rozeti.
// Tema seçimiyle ilgisi yok (bkz. tema.js) — tek sorumluluk ayrımı.
(function () {
  var KENAR = document.getElementById('kenar-cubugu');
  var ORTU = document.getElementById('kenar-orustu');
  var AC_BUTON = document.getElementById('menu-ac');
  var KAPAT_BUTON = document.getElementById('kenar-kapat');

  function kenariAc() {
    KENAR.classList.add('acik');
    ORTU.classList.add('acik');
  }
  function kenariKapat() {
    KENAR.classList.remove('acik');
    ORTU.classList.remove('acik');
  }
  if (AC_BUTON) AC_BUTON.addEventListener('click', kenariAc);
  if (KAPAT_BUTON) KAPAT_BUTON.addEventListener('click', kenariKapat);
  if (ORTU) ORTU.addEventListener('click', kenariKapat);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') kenariKapat();
  });

  // ---- Mini sistem durumu rozeti (sidebar altı) ----
  var SICAKLIK_ALANI = document.getElementById('mini-durum-sicaklik');
  var SERVIS_ALANI = document.getElementById('mini-durum-servis');
  var NOKTA = document.getElementById('mini-durum-nokta');
  if (!SICAKLIK_ALANI) return; // giriş sayfası gibi sidebar'sız sayfalarda yok

  function miniDurumGuncelle() {
    fetch('/api/sistem-durumu').then(function (r) {
      if (!r.ok) throw new Error('durum alınamadı');
      return r.json();
    }).then(function (veri) {
      SICAKLIK_ALANI.textContent = veri.cpu && veri.cpu.sicaklik_c != null ? veri.cpu.sicaklik_c + '°C' : '—';
      var toplam = veri.servisler ? veri.servisler.length : 0;
      var aktif = veri.servisler ? veri.servisler.filter(function (s) { return s.aktif; }).length : 0;
      SERVIS_ALANI.textContent = aktif + '/' + toplam + ' servis';
      NOKTA.className = 'mini-durum-nokta ' + (aktif === toplam ? 'nokta-yesil' : aktif === 0 ? 'nokta-kirmizi' : 'nokta-amber');
    }).catch(function () {
      SICAKLIK_ALANI.textContent = '—';
      SERVIS_ALANI.textContent = 'durum yok';
      NOKTA.className = 'mini-durum-nokta nokta-gri';
    });
  }
  miniDurumGuncelle();
  setInterval(miniDurumGuncelle, 30000);
})();
