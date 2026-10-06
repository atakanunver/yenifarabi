/* hata.js - ortak istemci hata raporlama (3 sayfa + ozet).
 * Aynı mesaj sayfa başına en fazla 60 sn'de bir, toplam en fazla 20 rapor gönderilir
 * (eski tahtalarda tek hata saniyeler içinde yüzlerce kez loglanıyordu). Asla hata fırlatmaz. */
(function () {
  var ARALIK_MS = 60000, MAX_RAPOR = 20;
  var sonGonderim = {}, toplam = 0;

  function raporla(msg, url, line, col, stack) {
    try {
      var mesaj = String(msg || 'Bilinmeyen Hata');
      var anahtar = mesaj.slice(0, 200);
      var simdi = Date.now();
      if (toplam >= MAX_RAPOR) return;
      if (sonGonderim[anahtar] && simdi - sonGonderim[anahtar] < ARALIK_MS) return;
      sonGonderim[anahtar] = simdi;
      toplam++;
      var govde = JSON.stringify({
        mesaj: mesaj,
        kaynak_url: String(url || window.location.href),
        satir: Number(line || 0),
        sutun: Number(col || 0),
        stack: String(stack || '').slice(0, 2000),
        user_agent: navigator.userAgent
      });
      if (navigator.sendBeacon && window.Blob) {
        // application/json olmazsa FastAPI gövdeyi reddeder (text/plain -> 422)
        navigator.sendBeacon('/api/arena/log-hata', new Blob([govde], { type: 'application/json' }));
      } else {
        fetch('/api/arena/log-hata', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: govde }).catch(function () {});
      }
    } catch (e) { /* raporlama asla oyunu bozmasın */ }
  }

  window.reportClientError = raporla;
  window.hataLogla = function (mesaj) { raporla(mesaj, window.location.href, 0, 0, ''); };

  window.addEventListener('error', function (e) {
    raporla(e.message, e.filename, e.lineno, e.colno, e.error ? e.error.stack : '');
  });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason || {};
    raporla('Unhandled Rejection: ' + (r.message || r), window.location.href, 0, 0, r.stack || '');
  });
})();
