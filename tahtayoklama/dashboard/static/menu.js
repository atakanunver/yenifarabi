// Kabuk davranışı (2026-10-30, panel yeniden tasarımı): üst alan sekmeleri + sol sayfa menüsü.
// Menü ağacı sunucuda menu.py'den gelir (taban.html); bu dosya yalnızca davranış: ok tuşları,
// harf kısayolları, <=720px çekmece, ayar menüsü eylemleri, tema döngüsü, veli sayacı ve
// mini sunucu durumu (eski kenar.js buraya katıldı). Gezinme JS'siz de çalışır (düz <a href>).
(function () {
  var kok = document.documentElement;
  var gezinme = document.getElementById('gezinme');
  if (!gezinme) return; // giriş sayfası gibi kabuksuz sayfalar

  function hepsi(secici) { return Array.prototype.slice.call(document.querySelectorAll(secici)); }
  function gorunur(liste) { return liste.filter(function (o) { return o.offsetParent !== null; }); }

  // ---- Bildirim ----
  function toast(metin) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = metin; t.classList.remove('gizli');
    clearTimeout(toast._z);
    toast._z = setTimeout(function () { t.classList.add('gizli'); }, 3000);
  }
  window.farabiToast = toast;

  // ---- Ayar açılır menüsü (<details>): dışarı tıklayınca / Esc ile kapanır ----
  var ayar = document.getElementById('ayar-menu');
  function ayarKapat(odakDon) {
    if (!ayar || !ayar.open) return false;
    ayar.open = false;
    if (odakDon) ayar.querySelector('summary').focus();
    return true;
  }
  document.addEventListener('click', function (e) {
    if (ayar && ayar.open && !ayar.contains(e.target)) ayarKapat(false);
  });

  // ---- <=720px: alan sekmeleri + sol menü tek çekmece ----
  var ortu = document.getElementById('cekmece-ortu');
  var acDugme = document.getElementById('menu-ac');
  function cekmeceKapat(odakDon) {
    if (!kok.classList.contains('cekmece-acik')) return false;
    kok.classList.remove('cekmece-acik'); ortu.hidden = true;
    acDugme.setAttribute('aria-expanded', 'false');
    if (odakDon) acDugme.focus();
    return true;
  }
  acDugme.addEventListener('click', function () {
    if (cekmeceKapat(false)) return;
    kok.classList.add('cekmece-acik'); ortu.hidden = false; acDugme.setAttribute('aria-expanded', 'true');
    var ilk = gezinme.querySelector('.sol-oge[aria-current="page"]') || gezinme.querySelector('.alan-sekme');
    if (ilk) ilk.focus();
  });
  ortu.addEventListener('click', function () { cekmeceKapat(true); });

  // ---- Eylemler (ayar menüsü, tema düğmeleri) ----
  function temaAdi(tema) {
    var b = document.querySelector('[data-eylem="tema:' + tema + '"]');
    return b ? b.textContent.trim() : tema;
  }
  var EYLEMLER = {
    'yazdir': function () { window.print(); },
    // Döngü sırası menu.TEMALAR (window.FARABI_TEMALAR, tema.js)
    'tema-dongu': function () {
      if (!window.farabiTemaSonraki) return;
      window.farabiTemaSonraki();
      toast('Tema: ' + temaAdi(kok.dataset.tema));
    },
    'kisayollar': function () { document.getElementById('kisayol-penceresi').showModal(); },
    'hakkinda': function () { document.getElementById('hakkinda-penceresi').showModal(); },
    'cikis': function () { document.getElementById('cikis-form').submit(); }
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-eylem]'); if (!b) return;
    var ad = b.dataset.eylem;
    if (ad.indexOf('tema:') === 0) {
      if (window.farabiTemaUygula) window.farabiTemaUygula(ad.slice(5));
      return; // temalar arasında gezinirken menü açık kalsın
    }
    if (EYLEMLER[ad]) { ayarKapat(false); EYLEMLER[ad](); }
  });

  // ---- Klavye: ok tuşları ----
  function okGezin(e, liste, geri, ileri) {
    var i = liste.indexOf(document.activeElement);
    if (i === -1) return;
    var j = e.key === 'Home' ? 0 : e.key === 'End' ? liste.length - 1
      : e.key === ileri ? (i + 1) % liste.length
      : e.key === geri ? (i - 1 + liste.length) % liste.length : -1;
    if (j === -1) return;
    e.preventDefault();
    liste[j].focus();
  }
  var masaustu = window.matchMedia('(min-width: 721px)');
  // Telefon yan çevrilip masaüstü genişliğine geçerse açık çekmece/örtü kalmasın
  if (masaustu.addEventListener) masaustu.addEventListener('change', function () { cekmeceKapat(false); });
  document.addEventListener('keydown', function (e) {
    var a = document.activeElement;
    if (!a || !a.classList) return;
    if (a.classList.contains('alan-sekme')) {
      // Çekmecede sekmeler alt alta durur: orada ↑↓ sekmeler arasında gezer.
      var yatay = masaustu.matches;
      okGezin(e, gorunur(hepsi('.alan-sekme')), yatay ? 'ArrowLeft' : 'ArrowUp', yatay ? 'ArrowRight' : 'ArrowDown');
    } else if (a.classList.contains('sol-oge')) {
      okGezin(e, gorunur(hepsi('.sol-oge')), 'ArrowUp', 'ArrowDown');
    } else if (a.closest('.ayar-panel')) {
      okGezin(e, gorunur(hepsi('.ayar-panel button, .ayar-panel a')), 'ArrowUp', 'ArrowDown');
    }
  });

  // ---- Klavye: Esc, F10, ?, harf kısayolları ----
  document.addEventListener('keydown', function (e) {
    var pencereAcik = !!document.querySelector('dialog[open]');
    if (e.key === 'Escape') {
      if (pencereAcik) return; // açık <dialog> Esc'i kendisi işler
      if (ayarKapat(true) || cekmeceKapat(true)) e.preventDefault();
      return;
    }
    if (e.key === 'F10') {
      e.preventDefault();
      // Telefonda sekmeler kapalı çekmecede: önce çekmeceyi aç
      if (!masaustu.matches && !kok.classList.contains('cekmece-acik')) acDugme.click();
      var ilk = document.querySelector('.alan-sekme');
      if (ilk) ilk.focus();
      return;
    }
    // Ctrl+P, Ctrl+S gibi tarayıcı kısayollarına, basılı tutmaya ve açık pencereye dokunma
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat || e.isComposing || pencereAcik) return;
    var a = document.activeElement;
    if (a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable)) return;
    if (e.key === '?') { e.preventDefault(); EYLEMLER.kisayollar(); return; }
    if (e.key.length !== 1) return;
    var hedef = document.querySelector('[data-kisayol="' + e.key.toLocaleLowerCase('tr') + '"]');
    if (hedef) { e.preventDefault(); hedef.click(); }
  });

  // ---- Üst çubuk saati ----
  var saat = document.getElementById('ust-saat');
  function saatYaz() {
    if (saat) saat.textContent = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
  }
  saatYaz(); setInterval(saatYaz, 20000);

  // ---- Veli mesajları okunmamış sayacı (alan sekmesi + sol menü rozeti): hata → gizli, 30 sn'de bir ----
  var rozetler = hepsi('[data-sayac="veli"]');
  function sayacYaz(n) {
    rozetler.forEach(function (r) {
      r.hidden = !n;
      r.textContent = n > 99 ? '99+' : String(n);
      r.setAttribute('aria-label', n + ' okunmamış mesaj');
    });
  }
  function sayacGuncelle() {
    if (document.hidden) return;
    fetch('/api/veli-mesajlari/sayac').then(function (r) {
      if (!r.ok) throw new Error('sayaç yok');
      return r.json();
    }).then(function (v) { sayacYaz(v && typeof v.okunmamis === 'number' ? v.okunmamis : 0); })
      .catch(function () { sayacYaz(0); });
  }
  if (rozetler.length) { sayacGuncelle(); setInterval(sayacGuncelle, 30000); }

  // ---- Mini sunucu durumu (ayar menüsünde) ----
  // İlk açılışta sunucu durumu ÇEKİLMEZ (ana sayfa yalnızca yoklamayı yüklesin — 2026-10-03
  // kullanıcı isteği). Düğmeye tıklanınca ya da Sistem durumu sayfasındayken başlar, 30 sn'de bir yenilenir.
  var durum = document.getElementById('mini-durum');
  var sicaklik = document.getElementById('mini-durum-sicaklik');
  var servis = document.getElementById('mini-durum-servis');
  var nokta = document.getElementById('mini-durum-nokta');
  function miniDurumGuncelle() {
    if (document.hidden) return;
    fetch('/api/sistem-durumu').then(function (r) {
      if (!r.ok) throw new Error('durum alınamadı');
      return r.json();
    }).then(function (veri) {
      sicaklik.textContent = veri.cpu && veri.cpu.sicaklik_c != null ? veri.cpu.sicaklik_c + '°C' : '—';
      var toplam = veri.servisler ? veri.servisler.length : 0;
      var aktif = veri.servisler ? veri.servisler.filter(function (s) { return s.aktif; }).length : 0;
      servis.textContent = aktif + '/' + toplam + ' servis';
      nokta.className = 'mini-durum-nokta ' + (aktif === toplam ? 'nokta-yesil' : aktif === 0 ? 'nokta-kirmizi' : 'nokta-amber');
    }).catch(function () {
      sicaklik.textContent = '—';
      servis.textContent = 'durum yok';
      nokta.className = 'mini-durum-nokta nokta-gri';
    });
  }
  var basladi = false;
  function baslat() {
    if (basladi) return;
    basladi = true;
    durum.title = 'Sunucu durumu — ayrıntı için Sistem durumu sayfasına git';
    servis.textContent = 'yükleniyor…';
    miniDurumGuncelle();
    setInterval(miniDurumGuncelle, 30000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) miniDurumGuncelle(); });
  }
  if (durum) {
    durum.addEventListener('click', function () {
      if (basladi) window.location = '/sistem-durumu';
      else baslat();
    });
    if (window.location.pathname.indexOf('/sistem-durumu') === 0) baslat();
  }
})();
