// Sudoku Düellosu: ızgara gezinme, sunucu saatinden akan süre göstergesi, tahtayı fetch ile gönderme.
// JS yoksa form normal POST eder (81 "h" alanı). Metin yalnızca textContent ile yazılır.
(function () {
  "use strict";
  var form = document.getElementById("sudoku-form");
  if (!form) return;
  var hucreler = Array.prototype.slice.call(form.querySelectorAll(".sudoku-hucre"));
  var mesaj = document.getElementById("sudoku-mesaj");
  var hataEl = document.getElementById("sudoku-hata");
  var sureEl = document.getElementById("sudoku-sure");
  var dugme = document.getElementById("sudoku-gonder");
  var baslangic = performance.now() - (parseInt(sureEl.dataset.gecen, 10) || 0) * 1000;
  var gonderiyor = false;

  // Doldurulan rakamlar kaybolmasın: (1) bot oyununda sunucuya otomatik kaydedilir (data-kaydet; sayfa sunucudan dolu gelir,
  // başka cihazdan da devam edilir), (2) her oyunda bu tarayıcıda da saklanır (düello için). Depolama kapalıysa sessizce atlanır.
  var anahtar = "sudoku:" + form.getAttribute("action");
  var kaydetUrl = form.dataset.kaydet;
  var kaydetZamani = null;
  var bitti = false;
  function dizi() {
    return hucreler.map(function (h) { return h.readOnly ? "0" : (h.value || "0"); }).join("");
  }
  function sunucuyaKaydet() {
    if (!kaydetUrl || !window.fetch || bitti) return;
    var veri = new FormData();
    veri.append("csrf", form.elements.csrf.value);
    veri.append("tahta", dizi());
    fetch(kaydetUrl, { method: "POST", body: veri, headers: { Accept: "application/json" }, credentials: "same-origin", keepalive: true })
      .catch(function () { /* sonraki yazışta yeniden denenir */ });
  }
  function yaz() {
    try { localStorage.setItem(anahtar, dizi()); } catch (e) { /* depolama yok */ }
    if (kaydetUrl) { clearTimeout(kaydetZamani); kaydetZamani = setTimeout(sunucuyaKaydet, 700); }
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden" && kaydetUrl) { clearTimeout(kaydetZamani); sunucuyaKaydet(); }
  });
  function sil() {
    try { localStorage.removeItem(anahtar); } catch (e) { /* depolama yok */ }
  }
  try {
    var kayit = localStorage.getItem(anahtar) || "";
    if (kayit.length === 81) {
      hucreler.forEach(function (h, i) { if (!h.readOnly && !h.value && /^[1-9]$/.test(kayit.charAt(i))) h.value = kayit.charAt(i); });
    }
  } catch (e) { /* depolama yok */ }

  setInterval(function () {
    var s = Math.floor((performance.now() - baslangic) / 1000);
    sureEl.textContent = Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
  }, 1000);

  function uyar(metin) {
    mesaj.textContent = metin;
    mesaj.hidden = false;
  }

  function git(i) {
    if (i >= 0 && i < 81) hucreler[i].focus();
  }

  hucreler.forEach(function (h, i) {
    if (h.readOnly) return;
    h.addEventListener("input", function () {
      var m = h.value.replace(/[^1-9]/g, "");
      h.value = m.slice(-1);
      yaz();
      if (h.value) git(i + 1);
    });
    h.addEventListener("focus", function () { h.select(); });
  });
  hucreler.forEach(function (h, i) {
    h.addEventListener("keydown", function (e) {
      var d = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -9, ArrowDown: 9 }[e.key];
      if (d) { e.preventDefault(); git(i + d); }
      else if (e.key === "Backspace" && !h.readOnly && !h.value) git(i - 1);
    });
  });

  form.addEventListener("submit", function (e) {
    var tahta = hucreler.map(function (h) { return h.value || "0"; }).join("");
    if (tahta.indexOf("0") !== -1) {
      e.preventDefault();
      uyar("Önce tüm kutuları doldur.");
      return;
    }
    if (!window.fetch) return; // JS'siz akışa düş
    e.preventDefault();
    if (gonderiyor) return;
    gonderiyor = true;
    dugme.disabled = true;
    var veri = new FormData();
    veri.append("csrf", form.elements.csrf.value);
    veri.append("tahta", tahta);
    fetch(form.action, { method: "POST", body: veri, headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) {
        if (x.ok && x.j.dogru) { bitti = true; clearTimeout(kaydetZamani); sil(); location.href = x.j.sonraki; return; }
        if (x.ok) {
          hataEl.textContent = x.j.hata;
          uyar("Tahtada hata var (+10 sn ceza). Kontrol edip tekrar dene.");
        } else {
          uyar(x.j.mesaj || "Gönderilemedi.");
          if (x.j.sonraki) setTimeout(function () { location.href = x.j.sonraki; }, 1500);
        }
      })
      .catch(function () { uyar("Bağlantı hatası. Tekrar dene."); })
      .then(function () { gonderiyor = false; dugme.disabled = false; });
  });
})();
