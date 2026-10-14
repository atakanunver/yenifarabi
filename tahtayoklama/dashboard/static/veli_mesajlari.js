// Velilerden Gelen Mesajlar sayfası: okundu / sil / spam engelle / engeli kaldır (sayfa içi onaylı). Mesaj metni konsola yazılmaz.
(function () {
  var liste = document.getElementById('vm-liste');
  if (!liste) return;
  function bildir(m) { if (window.farabiToast) window.farabiToast(m); }
  function gonder(id, yol, govde) {
    var secenek = { method: 'POST' };
    if (govde) { secenek.headers = { 'Content-Type': 'application/json' }; secenek.body = JSON.stringify(govde); }
    return fetch('/api/veli-mesajlari/' + encodeURIComponent(id) + '/' + yol, secenek)
      .then(function (r) { if (!r.ok) throw new Error('hata'); });
  }
  liste.addEventListener('click', function (e) {
    var dugme = e.target.closest('button[data-eylem]');
    if (!dugme) return;
    var kart = dugme.closest('.vm-kart');
    var id = kart.getAttribute('data-id');
    var onay = kart.querySelector('.vm-onay');
    var sor = kart.querySelector('[data-eylem="sil-sor"]');
    var eylem = dugme.getAttribute('data-eylem');
    var engelOnay = kart.querySelector('.vm-engel-onay');
    var engelSor = kart.querySelector('[data-eylem="engelle-sor"]');
    if (eylem === 'engelle-sor') { engelOnay.hidden = false; engelSor.hidden = true; return; }
    if (eylem === 'engelle-vazgec') { engelOnay.hidden = true; engelSor.hidden = false; return; }
    if (eylem === 'sil-sor') { onay.hidden = false; sor.hidden = true; return; }
    if (eylem === 'vazgec') { onay.hidden = true; sor.hidden = false; return; }
    dugme.disabled = true;
    var yol = { okundu: 'okundu', sil: 'sil', engelle: 'engelle', 'engeli-kaldir': 'engeli-kaldir' }[eylem];
    var govde = eylem === 'engelle' ? { neden: kart.querySelector('.vm-engel-neden').value.trim().slice(0, 80) } : null;
    gonder(id, yol, govde).then(function () {
      location.reload();
    }).catch(function () {
      dugme.disabled = false;
      bildir('İşlem yapılamadı — mesaj servisine ulaşılamıyor.');
    });
  });
})();
