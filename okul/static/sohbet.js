// Sohbet odası: ~5 sn'de bir yeni mesajları sorar (yalnızca sekme görünürken). Metin YALNIZCA textContent ile eklenir (XSS yok).
(function () {
  "use strict";
  var kok = document.getElementById("sohbet");
  if (!kok || !window.fetch) return;
  var liste = document.getElementById("sohbet-liste");
  var bos = document.getElementById("sohbet-bos");
  var form = document.getElementById("sohbet-form");
  var kutu = document.getElementById("sohbet-metin");
  var hata = document.getElementById("sohbet-hata");
  var csrf = kok.getAttribute("data-csrf");
  var son = parseInt(kok.getAttribute("data-son") || "0", 10);
  var gonderiyor = false;

  function altta() { return liste.scrollHeight - liste.scrollTop - liste.clientHeight < 80; }
  function kaydir() { liste.scrollTop = liste.scrollHeight; }
  function hataGoster(m) { hata.textContent = m || ""; hata.hidden = !m; }

  function silDugmesi() {
    var b = document.createElement("button");
    b.type = "button"; b.className = "sohbet-sil"; b.title = "Mesajı sil"; b.setAttribute("aria-label", "Mesajı sil");
    b.textContent = "Sil";
    return b;
  }
  function satir(m) {
    var li = document.createElement("li");
    li.className = "sohbet-mesaj" + (m.benim ? " benim" : "");
    li.setAttribute("data-id", String(m.id));
    var ust = document.createElement("div");
    ust.className = "sohbet-ust";
    var ad = document.createElement("b"); ad.textContent = m.yazar;
    var bilgi = document.createElement("span"); bilgi.className = "soluk";
    bilgi.textContent = " " + (m.rol === "yonetici" ? "Yönetici" : "Öğretmen") + " · " + m.zaman + " ";
    ust.appendChild(ad); ust.appendChild(bilgi);
    if (m.silinebilir) ust.appendChild(silDugmesi());
    var metin = document.createElement("div");
    metin.className = "sohbet-metin"; metin.textContent = m.metin;
    li.appendChild(ust); li.appendChild(metin);
    return li;
  }
  function ekle(mesajlar) {
    if (!mesajlar.length) return;
    var asagida = altta();
    mesajlar.forEach(function (m) {
      if (m.id <= son) return;
      liste.appendChild(satir(m));
      son = m.id;
    });
    bos.hidden = true;
    if (asagida) kaydir();
  }
  var uyeKutu = document.getElementById("sohbet-uyeler");
  function uyeleriYaz(uyeler) {
    if (!uyeKutu || !uyeler) return;
    while (uyeKutu.firstChild) uyeKutu.removeChild(uyeKutu.firstChild);
    uyeler.forEach(function (u) {
      var li = document.createElement("li");
      li.className = "sohbet-uye" + (u.cevrimici ? " cevrimici" : "");
      li.title = u.cevrimici ? "Çevrim içi" : "Çevrim dışı";
      var nokta = document.createElement("i"); nokta.setAttribute("aria-hidden", "true");
      li.appendChild(nokta);
      li.appendChild(document.createTextNode(u.ad + (u.ben ? " (sen)" : "")));
      var sr = document.createElement("span"); sr.className = "sr-only";
      sr.textContent = " — " + (u.cevrimici ? "çevrim içi" : "çevrim dışı");
      li.appendChild(sr);
      uyeKutu.appendChild(li);
    });
  }
  function getir() {
    return fetch("/sohbet/mesajlar?sonra=" + son, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) { ekle(j.mesajlar || []); uyeleriYaz(j.uyeler); } })
      .catch(function () {});
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (gonderiyor || !kutu.value.trim()) return;
    gonderiyor = true; hataGoster("");
    var f = new FormData(form);
    fetch("/sohbet/gonder", { method: "POST", body: f, credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (s) {
        if (!s.ok) { hataGoster(s.j.hata || "Mesaj gönderilemedi."); return; }
        kutu.value = "";
        return getir().then(kaydir);
      })
      .catch(function () { hataGoster("Mesaj gönderilemedi. Bağlantını kontrol et."); })
      .then(function () { gonderiyor = false; kutu.focus(); });
  });
  kutu.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });

  liste.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest(".sohbet-sil") : null;
    if (!b) return;
    var li = b.closest(".sohbet-mesaj");
    if (!li || !window.confirm("Bu mesaj silinsin mi?")) return;
    var f = new FormData(); f.append("csrf", csrf);
    fetch("/sohbet/" + li.getAttribute("data-id") + "/sil", { method: "POST", body: f, credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (r.ok) li.remove(); else hataGoster("Mesaj silinemedi."); })
      .catch(function () { hataGoster("Mesaj silinemedi."); });
  });

  setInterval(function () { if (!document.hidden) getir(); }, 5000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) getir(); });
  kaydir();
})();
