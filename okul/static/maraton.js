// Soru Maratonu: 30 sn dairesel sayaç + cevabı fetch ile gönder. JS yoksa form normal POST eder.
(function () {
  "use strict";
  var form = document.getElementById("cevap-formu");
  var sayac = document.getElementById("sayac");
  if (!form || !sayac) return;

  var SURE = parseInt(sayac.dataset.sure, 10) || 30;
  var kalan = parseFloat(sayac.dataset.kalan);
  var halka = document.getElementById("halka");
  var sn = document.getElementById("sn");
  var mesaj = document.getElementById("mesaj");
  var puanEl = document.getElementById("puan");
  var kareler = document.querySelectorAll("#ilerleme i");
  var butonlar = Array.prototype.slice.call(form.querySelectorAll("button.sik"));
  var CEVRE = 2 * Math.PI * 26;
  var bitis = performance.now() + kalan * 1000;
  var gonderildi = false;
  var zamanlayici;

  halka.style.strokeDasharray = CEVRE;

  function ciz() {
    var k = Math.max(0, (bitis - performance.now()) / 1000);
    halka.style.strokeDashoffset = CEVRE * (1 - k / SURE);
    sn.textContent = Math.ceil(k);
    sayac.classList.toggle("az", k <= 10);
    if (k <= 0 && !gonderildi) gonder(null);
  }

  function uyar(metin, kalici) {
    mesaj.textContent = metin;
    mesaj.hidden = false;
    if (kalici) {
      var a = document.createElement("a");
      a.className = "tus tam ikincil";
      a.href = location.pathname;
      a.textContent = "Devam et";
      mesaj.appendChild(document.createElement("br"));
      mesaj.appendChild(a);
    }
  }

  function gonder(buton) {
    if (gonderildi) return;
    gonderildi = true;
    clearInterval(zamanlayici);
    butonlar.forEach(function (b) { b.disabled = true; });
    var veri = new FormData(form);
    veri.delete("sec");
    if (buton) veri.set("sec", buton.value);
    fetch(form.action, {
      method: "POST",
      body: veri,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(
          function (j) { return { ok: r.ok, durum: r.status, j: j }; },
          function () { return { ok: false, durum: r.status, j: {} }; }
        );
      })
      .then(function (s) {
        if (!s.ok) {
          if (s.j && s.j.sonraki) { location.href = s.j.sonraki; return; }
          uyar(s.durum === 423 && s.j.mesaj ? s.j.mesaj : "Cevap gönderilemedi. Sayfayı yenileyip tekrar dene.", true);
          return;
        }
        var j = s.j;
        if (buton) buton.classList.add(j.dogru ? "dogru" : "yanlis");
        if (!j.dogru && j.dogru_index !== undefined && butonlar[j.dogru_index]) butonlar[j.dogru_index].classList.add("dogru");
        butonlar.forEach(function (b) { b.classList.add("kilitli"); });
        var kare = kareler[parseInt(form.elements.sira.value, 10) - 1];
        if (kare) kare.className = j.dogru ? "dolu" : "eksik";
        if (puanEl) puanEl.textContent = j.toplam;
        uyar(j.sure_doldu ? "Süre doldu" : (j.dogru ? "Doğru! +" + j.puan : "Yanlış"), false);
        setTimeout(function () { location.href = j.sonraki; }, 1200);
      })
      .catch(function () {
        uyar("Bağlantı sorunu. Cevabın gönderilemedi.", true);
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    gonder(e.submitter || null);
  });

  ciz();
  zamanlayici = setInterval(ciz, 100);
})();
