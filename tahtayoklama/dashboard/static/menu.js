// Menü çubuğu (WAI-ARIA menubar), mobil çekmece, Görünüm/Yardım eylemleri (2026-10-08).
// Menü ağacı sunucuda menu.py'den gelir (taban.html); bu dosya yalnızca davranış.
(function () {
  var cubuk = document.querySelector('.menubar');
  if (!cubuk) return;
  var ustler = Array.prototype.slice.call(cubuk.querySelectorAll('.ust-menu-dugme'));
  var acik = null;

  function ogeler(panel) {
    return Array.prototype.slice.call(panel.querySelectorAll(':scope > li > .menu-oge'));
  }
  function kapat(odakDon) {
    if (!acik) return;
    acik.setAttribute('aria-expanded', 'false');
    acik.nextElementSibling.hidden = true;
    acik.nextElementSibling.querySelectorAll('.alt-panel').forEach(function (p) { p.hidden = true; });
    if (odakDon) acik.focus();
    acik = null;
  }
  function ac(dugme, ilkOgeyeOdak) {
    if (acik && acik !== dugme) kapat(false);
    acik = dugme;
    dugme.setAttribute('aria-expanded', 'true');
    var panel = dugme.nextElementSibling;
    panel.hidden = false;
    if (ilkOgeyeOdak) { var o = ogeler(panel); if (o[0]) o[0].focus(); }
  }
  function komsu(dugme, yon) {
    var i = (ustler.indexOf(dugme) + yon + ustler.length) % ustler.length;
    return ustler[i];
  }
  function altAc(dugme) {
    var p = dugme.nextElementSibling;
    p.hidden = false;
    dugme.setAttribute('aria-expanded', 'true');
    var o = ogeler(p); if (o[0]) o[0].focus();
  }

  ustler.forEach(function (d) {
    d.addEventListener('click', function () { if (acik === d) { kapat(true); } else { ac(d, false); } });
    d.addEventListener('mouseenter', function () { if (acik && acik !== d) ac(d, false); });
    d.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        var k = komsu(d, e.key === 'ArrowRight' ? 1 : -1);
        if (acik) ac(k, false);
        k.focus();
      } else if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault(); ac(d, true);
      } else if (e.key === 'Home' || e.key === 'End') {
        e.preventDefault(); ustler[e.key === 'Home' ? 0 : ustler.length - 1].focus();
      } else if (e.key === 'Escape') {
        kapat(true);
      }
    });
  });

  cubuk.addEventListener('keydown', function (e) {
    var hedef = e.target;
    if (!hedef.classList.contains('menu-oge')) return;
    var panel = hedef.closest('[role="menu"]');
    var liste = ogeler(panel);
    var i = liste.indexOf(hedef);
    if (e.key === 'ArrowDown') { e.preventDefault(); liste[(i + 1) % liste.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); liste[(i - 1 + liste.length) % liste.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); liste[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); liste[liste.length - 1].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); kapat(true); }
    else if (e.key === 'ArrowRight' && hedef.getAttribute('aria-haspopup')) { e.preventDefault(); altAc(hedef); }
    else if (e.key === 'ArrowLeft' && panel.classList.contains('alt-panel')) {
      e.preventDefault();
      panel.hidden = true;
      panel.previousElementSibling.setAttribute('aria-expanded', 'false');
      panel.previousElementSibling.focus();
    } else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && acik) {
      e.preventDefault(); ac(komsu(acik, e.key === 'ArrowRight' ? 1 : -1), true);
    }
  });
  document.querySelectorAll('.alt-menu-kap > .menu-oge').forEach(function (d) {
    d.addEventListener('click', function () { altAc(d); });
    d.parentElement.addEventListener('mouseenter', function () { d.nextElementSibling.hidden = false; });
    d.parentElement.addEventListener('mouseleave', function () {
      if (!d.parentElement.contains(document.activeElement)) d.nextElementSibling.hidden = true;
    });
  });
  document.addEventListener('click', function (e) { if (acik && !cubuk.contains(e.target)) kapat(false); });

  // ---- Eylemler ----
  function toast(metin) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = metin; t.classList.remove('gizli');
    clearTimeout(toast._z);
    toast._z = setTimeout(function () { t.classList.add('gizli'); }, 3000);
  }
  window.farabiToast = toast;
  var kabuk = document.getElementById('kabuk');
  function seritUygula(gizli) {
    kabuk.classList.toggle('serit-gizli', gizli);
    try { localStorage.setItem('farabi_serit_gizli', gizli ? '1' : '0'); } catch (e) { /* kapalı depolama */ }
  }
  var EYLEMLER = {
    'yazdir': function () { window.print(); },
    'yenile': function () { location.reload(); },
    'bagla-kopyala': function () {
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject())
        .then(function () { toast('Bağlantı kopyalandı.'); }, function () { toast('Kopyalanamadı.'); });
    },
    'serit': function () { seritUygula(!kabuk.classList.contains('serit-gizli')); },
    'kisayollar': function () { document.getElementById('kisayol-penceresi').showModal(); },
    'hakkinda': function () { document.getElementById('hakkinda-penceresi').showModal(); },
    'cikis': function () { document.getElementById('cikis-form').submit(); }
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-eylem]'); if (!b) return;
    var ad = b.dataset.eylem;
    if (ad.indexOf('tema:') === 0) { if (window.farabiTemaUygula) window.farabiTemaUygula(ad.slice(5)); }
    else if (EYLEMLER[ad]) { EYLEMLER[ad](); }
    kapat(false); cekmeceKapat();
  });
  try { seritUygula(localStorage.getItem('farabi_serit_gizli') === '1'); } catch (e) { /* kapalı depolama */ }

  // ---- Kısayollar ----
  document.addEventListener('keydown', function (e) {
    if (e.key === 'F10') { e.preventDefault(); ustler[0].focus(); return; }
    var a = document.activeElement;
    var yazi = a && (/INPUT|TEXTAREA|SELECT/.test(a.tagName) || a.isContentEditable);
    if (e.key === '?' && !yazi) { e.preventDefault(); EYLEMLER.kisayollar(); }
  });

  // ---- Mobil çekmece ----
  var cek = document.getElementById('cekmece');
  var ortu = document.getElementById('cekmece-ortu');
  var acDugme = document.getElementById('menu-ac');
  function cekmeceKapat() {
    if (!cek || cek.hidden) return;
    cek.hidden = true; ortu.hidden = true;
    acDugme.setAttribute('aria-expanded', 'false');
    acDugme.focus();
  }
  if (acDugme) acDugme.addEventListener('click', function () {
    cek.hidden = false; ortu.hidden = false; acDugme.setAttribute('aria-expanded', 'true');
    var ilk = cek.querySelector('summary'); if (ilk) ilk.focus();
  });
  if (ortu) ortu.addEventListener('click', cekmeceKapat);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cekmeceKapat(); });
})();
