/* soru-bildir.js - tahtada açık sorunun yanında "Soru hatalı" düğmesi + sebep seçimi.
 * soruBildir.ayarla(sid, sube) soru gösterilince, soruBildir.gizle() kapanınca çağrılır.
 * sid yoksa (hazır/yedek soru) düğme görünmez. Hata fırlatmaz; oyunu asla bozmaz. */
(function () {
  var TURLER = [['cevap', 'Cevap yanlış'], ['sekil', 'Şekil / grafik yok'], ['alakasiz', 'Alakasız'], ['sacma', 'Saçma'], ['anlasilmiyor', 'Anlaşılmıyor']];
  var aktif = { sid: null, sube: '' };
  var dugme, panel, mesaj;

  function kur() {
    if (dugme) return;
    dugme = document.createElement('button');
    dugme.type = 'button';
    dugme.textContent = '🚩 Soru hatalı';
    dugme.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9998;padding:10px 16px;border-radius:14px;border:1px solid #475569;background:#1e293b;color:#fda4af;font-weight:700;font-size:14px;display:none;cursor:pointer';
    dugme.onclick = function () { panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; };
    panel = document.createElement('div');
    panel.style.cssText = 'position:fixed;right:12px;bottom:60px;z-index:9998;padding:12px;border-radius:14px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;display:none;max-width:260px;font-size:14px';
    mesaj = document.createElement('div');
    mesaj.style.cssText = 'margin-top:6px;font-size:12px;color:#94a3b8';
    var baslik = document.createElement('div');
    baslik.textContent = 'Sorunun sorunu nedir?';
    baslik.style.cssText = 'font-weight:700;margin-bottom:8px';
    panel.appendChild(baslik);
    TURLER.forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = t[1];
      b.style.cssText = 'display:block;width:100%;text-align:left;margin-bottom:6px;padding:8px 10px;border-radius:10px;border:1px solid #334155;background:#1e293b;color:#e2e8f0;cursor:pointer';
      b.onclick = function () { gonder(t[0]); };
      panel.appendChild(b);
    });
    panel.appendChild(mesaj);
    document.body.appendChild(dugme);
    document.body.appendChild(panel);
  }

  function gonder(tur) {
    var sid = aktif.sid;
    if (!sid) return;
    mesaj.textContent = 'Gönderiliyor...';
    try {
      fetch('/api/arena/soru-bildir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sid: sid, tur: tur, sube: aktif.sube || '' })
      }).then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (j) {
          mesaj.textContent = j.durum === 'ok' ? 'Bildirildi, teşekkürler.' : (j.mesaj || 'Bildirim gönderilemedi.');
          if (j.durum === 'ok') setTimeout(function () { panel.style.display = 'none'; mesaj.textContent = ''; }, 1500);
        })
        .catch(function () { mesaj.textContent = 'Bildirim gönderilemedi.'; });
    } catch (e) { /* oyunu bozma */ }
  }

  window.soruBildir = {
    ayarla: function (sid, sube) {
      try {
        kur();
        aktif = { sid: sid || null, sube: sube || '' };
        mesaj.textContent = '';
        panel.style.display = 'none';
        dugme.style.display = aktif.sid ? 'block' : 'none';
      } catch (e) { /* oyunu bozma */ }
    },
    gizle: function () {
      try { aktif = { sid: null, sube: '' }; if (dugme) { dugme.style.display = 'none'; panel.style.display = 'none'; } } catch (e) { /* */ }
    }
  };
})();
