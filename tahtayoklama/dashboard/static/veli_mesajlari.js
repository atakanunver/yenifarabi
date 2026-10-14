// Velilerden Gelen Mesajlar sayfası: okundu / sil (sayfa içi onaylı). Mesaj metni konsola yazılmaz.
(function () {
  var liste = document.getElementById('vm-liste');
  if (!liste) return;
  function bildir(m) { if (window.farabiToast) window.farabiToast(m); }
  function gonder(id, yol) {
    return fetch('/api/veli-mesajlari/' + encodeURIComponent(id) + '/' + yol, { method: 'POST' })
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
    if (eylem === 'sil-sor') { onay.hidden = false; sor.hidden = true; return; }
    if (eylem === 'vazgec') { onay.hidden = true; sor.hidden = false; return; }
    dugme.disabled = true;
    gonder(id, eylem === 'okundu' ? 'okundu' : 'sil').then(function () {
      location.reload();
    }).catch(function () {
      dugme.disabled = false;
      bildir('İşlem yapılamadı — mesaj servisine ulaşılamıyor.');
    });
  });
})();
