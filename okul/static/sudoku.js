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
    if (mesaj.scrollIntoView) mesaj.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  // Aynı satır/sütun/3x3 kutuda tekrar eden rakamlar (dolu hücreler arasında) kırmızı gösterilir. Tek çözümlü bulmacada
  // dolu ve çakışmasız tahta zaten doğru çözümdür; bu yüzden yanlış tahta sunucuya gitmeden fark edilir (ceza yazılmaz).
  function cakisanlar() {
    var kotu = {};
    for (var i = 0; i < 81; i++) {
      var d = hucreler[i].value;
      if (!d) continue;
      for (var j = i + 1; j < 81; j++) {
        if (hucreler[j].value !== d) continue;
        var ayniSatir = Math.floor(i / 9) === Math.floor(j / 9);
        var ayniSutun = i % 9 === j % 9;
        var ayniKutu = Math.floor(i / 27) === Math.floor(j / 27) && Math.floor((i % 9) / 3) === Math.floor((j % 9) / 3);
        if (ayniSatir || ayniSutun || ayniKutu) { kotu[i] = true; kotu[j] = true; }
      }
    }
    return kotu;
  }
  function vurgula() {
    var kotu = cakisanlar();
    hucreler.forEach(function (h, i) { h.classList.toggle("cakisma", !!kotu[i]); });
    return Object.keys(kotu).map(Number);
  }
  vurgula();

  function git(i) {
    if (i >= 0 && i < 81) hucreler[i].focus();
  }

  hucreler.forEach(function (h, i) {
    if (h.readOnly) return;
    h.addEventListener("input", function () {
      var m = h.value.replace(/[^1-9]/g, "");
      h.value = m.slice(-1);
      vurgula();
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

  // İpucu düğmesi: sunucu bir kutunun doğru rakamını açar (skora ceza yazar). JS yoksa düğme gizli kalır.
  var ipucuDugme = document.getElementById("sudoku-ipucu-dugme");
  var ipucuUrl = form.dataset.ipucu;
  var ipucuSayac = document.getElementById("sudoku-ipucu");
  var ipucuKalan = parseInt(form.dataset.ipucuKalan, 10);
  if (ipucuDugme && ipucuUrl && window.fetch) {
    ipucuDugme.hidden = false;
    ipucuDugme.addEventListener("click", function () {
      if (gonderiyor || bitti || ipucuKalan <= 0) return;
      ipucuDugme.disabled = true;
      var veri = new FormData();
      veri.append("csrf", form.elements.csrf.value);
      veri.append("tahta", dizi());
      fetch(ipucuUrl, { method: "POST", body: veri, headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (x) {
          if (!x.ok) { uyar(x.j.mesaj || "İpucu alınamadı."); return; }
          var h = hucreler[x.j.index];
          h.value = String(x.j.rakam);
          h.classList.add("ipucu-hucre");
          setTimeout(function () { h.classList.remove("ipucu-hucre"); }, 4000);
          ipucuKalan = x.j.kalan;
          if (ipucuSayac) ipucuSayac.textContent = x.j.ipucu;
          vurgula();
          yaz();
          uyar("İpucu: " + (Math.floor(x.j.index / 9) + 1) + ". satır, " + ((x.j.index % 9) + 1) + ". sütundaki kutu açıldı (skoruna +" +
               (form.dataset.ipucuCeza || "15") + " sn eklendi). Kalan hak: " + x.j.kalan + ".");
        })
        .catch(function () { uyar("Bağlantı hatası. Tekrar dene."); })
        .then(function () { ipucuDugme.disabled = ipucuKalan <= 0; });
    });
  }

  form.addEventListener("submit", function (e) {
    var tahta = hucreler.map(function (h) { return h.value || "0"; }).join("");
    if (tahta.indexOf("0") !== -1) {
      e.preventDefault();
      uyar("Önce tüm kutuları doldur.");
      return;
    }
    var kotu = vurgula();
    if (kotu.length) {
      e.preventDefault();
      uyar("Tahtada hata var: kırmızı kutularda aynı rakam bir satır, sütun veya 3×3 kutuda tekrar ediyor. Düzeltip tekrar dene. (Ceza yazılmadı.)");
      hucreler[kotu[0]].focus();
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
