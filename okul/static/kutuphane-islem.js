// Kitap Ver / Kitap Al akışı: okut → (gerekirse demirbaş seç) → (ver: öğrenci seç) → onayla.
// Sunucudan gelen her metin textContent ile yazılır. Onay tuşu istek bitene kadar kilitli (çift tıklama tek işlem).
(function () {
  "use strict";
  var kok = document.getElementById("ktp-islem");
  if (!kok) return;
  var mod = kok.dataset.mod, csrf = kok.dataset.csrf;
  var $ = function (id) { return document.getElementById(id); };
  var kodDurum = $("kod-durum"), nushaListe = $("nusha-liste"), adimOgr = $("adim-ogrenci"), adimOnay = $("adim-onay");
  var ozet = $("ozet"), onayTus = $("onay-tus"), sonuc = $("sonuc"), ogrQ = $("ogrenci-q"), ogrListe = $("ogrenci-liste");
  var secili = { nusha: null, ogrenci: null }, limit = 0, aramaZ = 0, aramaNo = 0;

  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin !== undefined && metin !== null) e.textContent = metin;
    return e;
  }

  function tarih(s) {
    if (!s) return "";
    var p = s.slice(0, 10).split("-");
    return p[2] + "." + p[1] + "." + p[0];
  }

  function json(url, secenek) {
    secenek = secenek || {};
    secenek.credentials = "same-origin";
    secenek.headers = { Accept: "application/json" };
    return fetch(url, secenek).then(function (r) {
      return r.json().catch(function () { return { tamam: false, mesaj: "Sunucu yanıtı okunamadı." }; }).then(function (v) {
        v._kod = r.status;
        return v;
      });
    });
  }

  var kamera = window.KtpKamera(kok.querySelector("[data-kamera]"), kodGeldi);

  function sonucYaz(metin, tamam, ek) {
    sonuc.textContent = metin;
    sonuc.className = "kart " + (tamam ? "tamam" : "olmadi");
    if (ek) sonuc.appendChild(ek);
    sonuc.hidden = false;
  }

  function sifirla(sonucuTut) {
    secili = { nusha: null, ogrenci: null };
    nushaListe.textContent = "";
    kodDurum.textContent = "";
    if (adimOgr) { adimOgr.hidden = true; ogrQ.value = ""; ogrListe.textContent = ""; }
    adimOnay.hidden = true;
    onayTus.disabled = false;
    if (!sonucuTut) sonuc.hidden = true;
    kamera.yeniden();
    if (!kamera.acik()) kamera.odakla();
  }

  function nushaNeden(n) {
    if (n.durum !== "saglam") return n.durum_ad;
    if (mod === "ver" && n.oduncte) return "Ödünçte: " + n.odunc_ad + " (" + n.odunc_sinif + ")";
    if (mod === "al" && !n.oduncte) return "Ödünçte değil";
    return "";
  }

  function kodGeldi(kod) {
    sonuc.hidden = true;
    kodDurum.textContent = "Aranıyor: " + kod;
    json("/kutuphane/api/kod?kod=" + encodeURIComponent(kod)).then(function (v) {
      if (v._kod !== 200) { kodDurum.textContent = "Sunucuya ulaşılamadı; tekrar deneyin."; kamera.yeniden(); return; }
      var liste = [];
      v.demirbas.forEach(function (n) { n.kaynak = "Demirbaş"; liste.push(n); });
      v.isbn.forEach(function (n) { if (!liste.some(function (x) { return x.id === n.id; })) { n.kaynak = "ISBN"; liste.push(n); } });
      nushaListe.textContent = "";
      if (!liste.length) {
        kodDurum.textContent = v.isbn_kodu ? "Bu ISBN ile kayıtlı kitap yok." : "Bu numarayla kayıtlı nüsha yok: " + kod;
        if (v.isbn_kodu) { var a = el("a", null, " Kitap Ekle →"); a.href = "/kutuphane/ekle"; kodDurum.appendChild(a); }
        kamera.yeniden();
        return;
      }
      var uygun = liste.filter(function (n) { return !nushaNeden(n); });
      if (uygun.length === 1 && liste.length === 1) { nushaSec(uygun[0]); return; }
      kodDurum.textContent = liste.length > 1 ? "Bu kitabın " + liste.length + " nüshası var. Etiketteki demirbaş numarasını seçin:" : "";
      if (!uygun.length) kodDurum.textContent = mod === "al" ? "Bu kitabın ödünçte nüshası yok." : "Bu kitabın verilebilir nüshası yok.";
      var kap = el("div", "ktp-secim");
      liste.forEach(function (n) {
        var b = el("button");
        b.type = "button";
        b.appendChild(el("span", "buyuk", n.demirbas));
        var orta = el("span", null);
        orta.appendChild(el("b", null, n.baslik));
        orta.appendChild(el("br"));
        orta.appendChild(el("span", "soluk kucuk", [n.kaynak, n.basim_sayisi, n.raf ? "Raf " + n.raf : ""].filter(Boolean).join(" · ")));
        b.appendChild(orta);
        var neden = nushaNeden(n);
        var ayrildi = mod === "ver" && !neden && n.ayrilan_ad ? n.ayrilan_ad + " için ayrıldı" : "";
        b.appendChild(el("span", "sag kucuk", neden || ayrildi || (mod === "al" ? n.odunc_ad : "Rafta")));
        b.disabled = !!neden;
        b.addEventListener("click", function () { nushaSec(n); });
        kap.appendChild(b);
      });
      nushaListe.appendChild(kap);
      if (!uygun.length) kamera.yeniden();
    }).catch(function () { kodDurum.textContent = "Bağlantı yok; tekrar deneyin."; kamera.yeniden(); });
  }

  function satir(dl, ad, deger) {
    dl.appendChild(el("dt", null, ad));
    dl.appendChild(el("dd", null, deger));
  }

  function ozetYaz() {
    var n = secili.nusha, dl = el("dl", "ktp-ozet");
    ozet.textContent = "";
    satir(dl, "Kitap", n.baslik);
    satir(dl, "Demirbaş", n.demirbas);
    if (mod === "al") {
      satir(dl, "Öğrenci", n.odunc_ad + " (" + n.odunc_sinif + " · " + n.odunc_no + ")");
      satir(dl, "Veriliş", tarih(n.verilis));
      satir(dl, "Son teslim", tarih(n.son_tarih));
      satir(dl, "Durum", n.gecikme_gun ? n.gecikme_gun + " gün gecikme" : "Zamanında");
    } else if (secili.ogrenci) {
      var o = secili.ogrenci;
      satir(dl, "Öğrenci", o.ad_soyad + " (" + o.sinif + " · " + o.okul_no + ")");
      satir(dl, "Elindeki kitap", o.aktif + " / " + limit);
    }
    ozet.appendChild(dl);
    if (mod === "ver" && n.ayrilan_ad) ozet.appendChild(el("p", "ktp-ayir kucuk", "Bu nüsha " + n.ayrilan_ad + " (" + n.ayrilan_sinif + ") için ayrıldı; yalnızca ona verilebilir."));
    adimOnay.hidden = false;
    onayTus.focus();
  }

  function nushaSec(n) {
    secili.nusha = n;
    kodDurum.textContent = "Seçildi: " + n.demirbas + " · " + n.baslik;
    nushaListe.textContent = "";
    if (mod === "ver") {
      adimOgr.hidden = false;
      adimOnay.hidden = true;
      ogrQ.focus();
    } else {
      ozetYaz();
    }
  }

  function ogrenciAra() {
    var q = ogrQ.value.trim(), no = ++aramaNo;
    if (!q) { ogrListe.textContent = ""; return; }
    json("/kutuphane/api/ogrenci?q=" + encodeURIComponent(q)).then(function (v) {
      if (no !== aramaNo) return; // eski yanıt yenisini ezmesin
      limit = v.limit;
      ogrListe.textContent = "";
      if (!v.ogrenciler || !v.ogrenciler.length) { ogrListe.appendChild(el("p", "bos", "Öğrenci bulunamadı.")); return; }
      v.ogrenciler.forEach(function (o) {
        var b = el("button");
        b.type = "button";
        b.setAttribute("role", "listitem");
        b.appendChild(el("span", "buyuk", String(o.okul_no)));
        var orta = el("span");
        orta.appendChild(el("b", null, o.ad_soyad));
        orta.appendChild(el("br"));
        orta.appendChild(el("span", "soluk kucuk", o.sinif));
        b.appendChild(orta);
        var dolu = o.aktif >= limit;
        b.appendChild(el("span", "sag kucuk", dolu ? "Limit dolu (" + o.aktif + ")" : o.aktif + " / " + limit));
        b.disabled = dolu;
        b.addEventListener("click", function () {
          secili.ogrenci = o;
          Array.prototype.forEach.call(ogrListe.children, function (c) { c.setAttribute("aria-pressed", c === b ? "true" : "false"); });
          ozetYaz();
        });
        ogrListe.appendChild(b);
      });
    }).catch(function () { /* sessiz: kullanıcı yeniden yazar */ });
  }

  if (ogrQ) {
    ogrQ.addEventListener("input", function () { clearTimeout(aramaZ); aramaZ = setTimeout(ogrenciAra, 220); });
    ogrQ.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var ilk = ogrListe.querySelector("button:not(:disabled)");
      if (ilk && ogrListe.querySelectorAll("button").length === 1) ilk.click();
    });
  }

  onayTus.addEventListener("click", function () {
    if (!secili.nusha || (mod === "ver" && !secili.ogrenci) || onayTus.disabled) return;
    onayTus.disabled = true;
    var f = new FormData();
    f.append("csrf", csrf);
    f.append("nusha_id", secili.nusha.id);
    if (mod === "ver") f.append("ogrenci_id", secili.ogrenci.id);
    json("/kutuphane/" + mod, { method: "POST", body: f }).then(function (v) {
      if (!v.tamam) { sonucYaz(v.mesaj || "İşlem yapılamadı.", false); sifirla(true); return; }
      var k = v.kayit, ek = null;
      if (mod === "ver") {
        sonucYaz("✓ " + k.baslik + " → " + k.ad_soyad + " · son teslim " + tarih(k.son_tarih), true);
      } else {
        sonucYaz("✓ Teslim alındı: " + k.baslik + " (" + k.ad_soyad + ")" + (k.gecikme_gun ? " · " + k.gecikme_gun + " gün gecikmeli" : ""), true,
          k.ayrilan ? el("span", "ktp-ayir", "Rafa koymayın! Bu nüsha " + k.ayrilan.ad_soyad + " (" + k.ayrilan.sinif + ") için ayrıldı.") : null);
        if (k.ayrilan) ek = true;
      }
      if (navigator.vibrate) navigator.vibrate(ek ? [80, 60, 80] : 40);
      sifirla(true);
    }).catch(function () { sonucYaz("Bağlantı yok; işlem yapılmadı. Tekrar deneyin.", false); onayTus.disabled = false; });
  });

  $("vazgec-tus").addEventListener("click", function () { sifirla(false); });
})();
