// Sol kenar menü (2026-10-23; önceki üst menü çubuğunun yerine): grup aç/kapa, daraltma,
// <720px çekmece, eylemler ve kısayollar. Menü ağacı sunucuda menu.py'den gelir (taban.html);
// bu dosya yalnızca davranış.
(function () {
  var kenar = document.getElementById('kenar');
  if (!kenar) return;
  var kok = document.documentElement;
  var kabuk = document.getElementById('kabuk');

  function grupAyarla(dugme, acik) {
    dugme.setAttribute('aria-expanded', acik ? 'true' : 'false');
    document.getElementById(dugme.getAttribute('aria-controls')).hidden = !acik;
  }

  // ---- Daraltma (yalnız ikonlar, 72px) ----
  function daraltUygula(dar) {
    kok.classList.toggle('kenar-dar', dar);
    try { localStorage.setItem('farabi_kenar_dar', dar ? '1' : '0'); } catch (e) { /* kapalı depolama */ }
  }

  kenar.addEventListener('click', function (e) {
    var d = e.target.closest('.kenar-grup-dugme'); if (!d) return;
    if (kok.classList.contains('kenar-dar')) { daraltUygula(false); grupAyarla(d, true); return; }
    grupAyarla(d, d.getAttribute('aria-expanded') !== 'true');
  });

  // Ok tuşları: görünür menü öğeleri arasında gezinme
  function gorunurOgeler() {
    return Array.prototype.slice.call(kenar.querySelectorAll('.kenar-acil, .kenar-oge, .kenar-alt-oge, .mini-durum'))
      .filter(function (o) { return o.offsetParent !== null; });
  }
  kenar.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return;
    var liste = gorunurOgeler(); var i = liste.indexOf(document.activeElement);
    if (i === -1) return;
    e.preventDefault();
    var j = e.key === 'Home' ? 0 : e.key === 'End' ? liste.length - 1
      : (i + (e.key === 'ArrowDown' ? 1 : -1) + liste.length) % liste.length;
    liste[j].focus();
  });

  // ---- Eylemler ----
  function toast(metin) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = metin; t.classList.remove('gizli');
    clearTimeout(toast._z);
    toast._z = setTimeout(function () { t.classList.add('gizli'); }, 3000);
  }
  window.farabiToast = toast;
  var TEMA_SIRA = ['argon', 'argon-koyu', 'material', 'material-koyu', 'black', 'koyu'];
  var TEMA_AD = { 'argon': 'Argon açık', 'argon-koyu': 'Argon koyu', 'material': 'Material açık',
                  'material-koyu': 'Material koyu', 'black': 'Black', 'koyu': 'Taş Tahta' };
  var EYLEMLER = {
    'yazdir': function () { window.print(); },
    'yenile': function () { location.reload(); },
    'bagla-kopyala': function () {
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject())
        .then(function () { toast('Bağlantı kopyalandı.'); }, function () { toast('Kopyalanamadı.'); });
    },
    'daralt': function () { daraltUygula(!kok.classList.contains('kenar-dar')); },
    'tema-dongu': function () {
      var sonraki = TEMA_SIRA[(TEMA_SIRA.indexOf(kok.dataset.tema) + 1) % TEMA_SIRA.length];
      if (window.farabiTemaUygula) window.farabiTemaUygula(sonraki);
      toast('Tema: ' + TEMA_AD[sonraki]);
    },
    'kisayollar': function () { document.getElementById('kisayol-penceresi').showModal(); },
    'hakkinda': function () { document.getElementById('hakkinda-penceresi').showModal(); },
    'cikis': function () { document.getElementById('cikis-form').submit(); }
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-eylem]'); if (!b) return;
    var ad = b.dataset.eylem;
    if (ad.indexOf('tema:') === 0) { if (window.farabiTemaUygula) window.farabiTemaUygula(ad.slice(5)); }
    else if (EYLEMLER[ad]) { EYLEMLER[ad](); }
    if (ad !== 'daralt') cekmeceKapat(false);
  });

  // ---- Kısayollar ----
  document.addEventListener('keydown', function (e) {
    if (e.key === 'F10') { e.preventDefault(); var o = gorunurOgeler(); if (o[0]) o[0].focus(); return; }
    var a = document.activeElement;
    var yazi = a && (/INPUT|TEXTAREA|SELECT/.test(a.tagName) || a.isContentEditable);
    if (e.key === '?' && !yazi) { e.preventDefault(); EYLEMLER.kisayollar(); }
  });

  // ---- <720px çekmece: aynı <nav> soldan kayar ----
  var ortu = document.getElementById('cekmece-ortu');
  var acDugme = document.getElementById('menu-ac');
  function cekmeceKapat(odakDon) {
    if (!kabuk.classList.contains('kenar-acik')) return;
    kabuk.classList.remove('kenar-acik'); ortu.hidden = true;
    acDugme.setAttribute('aria-expanded', 'false');
    if (odakDon) acDugme.focus();
  }
  if (acDugme) acDugme.addEventListener('click', function () {
    kabuk.classList.add('kenar-acik'); ortu.hidden = false; acDugme.setAttribute('aria-expanded', 'true');
    var o = gorunurOgeler(); if (o[0]) o[0].focus();
  });
  if (ortu) ortu.addEventListener('click', function () { cekmeceKapat(true); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cekmeceKapat(true); });

  // ---- Başlık şeridi saati ----
  var saat = document.getElementById('ust-saat');
  function saatYaz() {
    if (saat) saat.textContent = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
  }
  saatYaz(); setInterval(saatYaz, 20000);
})();
