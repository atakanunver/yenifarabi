// Tarih-saat widget'ı (_saat.html) + program sayfasındaki zil tablosu vurgusu.
// Saat sunucu saatine göre düzeltilir (telefon saati yanlış olabilir) ve İstanbul saatiyle gösterilir.
// Ders durumu kuralı kaynaklar/zil.py::durum ile aynı: yarı açık [başlangıç, bitiş).
(function () {
  var kart = document.getElementById("saat-kart");
  var tablo = document.getElementById("zil-tablo");
  if (!kart && !tablo) return;

  var veri = {};
  try { veri = JSON.parse(kart ? kart.dataset.saat : tablo.dataset.saat) || {}; } catch (e) {}
  var fark = veri.epoch ? veri.epoch - Date.now() : 0;
  var dersler = veri.dersler || [];
  var ogle = veri.ogle;

  var parcala = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  });
  var tarihYaz = new Intl.DateTimeFormat("tr-TR", {
    timeZone: "Europe/Istanbul", weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  function an() {
    var t = new Date(Date.now() + fark), p = {};
    parcala.formatToParts(t).forEach(function (x) { p[x.type] = x.value; });
    return { t: t, tarih: p.year + "-" + p.month + "-" + p.day, sa: +p.hour, dk: +p.minute, sn: +p.second };
  }
  function dakika(hhmm) { var s = hhmm.split(":"); return +s[0] * 60 + +s[1]; }
  function iki(n) { return (n < 10 ? "0" : "") + n; }

  function durum(z) {
    if (veri.durum && (veri.durum.tur === "tatil" || veri.durum.tur === "yok")) return veri.durum;
    if (!dersler.length) return { tur: "yok", metin: "" };
    var simdi = z.sa * 60 + z.dk;
    if (simdi < dakika(dersler[0][1])) return { tur: "once", metin: "1. ders " + dersler[0][1] + "'de başlıyor" };
    for (var i = 0; i < dersler.length; i++) {
      var d = dersler[i], bas = dakika(d[1]), bit = dakika(d[2]);
      if (bas <= simdi && simdi < bit) {
        var kalan = bit * 60 - (simdi * 60 + z.sn);
        return {
          tur: "ders", no: d[0], metin: d[0] + ". ders · bitmesine " + Math.ceil(kalan / 60) + " dk",
          oran: 1 - kalan / ((bit - bas) * 60),
        };
      }
      var s = dersler[i + 1];
      if (s && bit <= simdi && simdi < dakika(s[1])) {
        var oglede = ogle && dakika(ogle[0]) <= simdi && simdi < dakika(ogle[1]);
        return { tur: oglede ? "ogle" : "teneffus", sonraki: s[0],
                 metin: (oglede ? "Öğle arası" : "Teneffüs") + " · " + s[0] + ". ders " + s[1] };
      }
    }
    return { tur: "bitti", metin: "Dersler bitti" };
  }

  var akrep = document.getElementById("ibre-akrep");
  var yelkovan = document.getElementById("ibre-yelkovan");
  var saniye = document.getElementById("ibre-saniye");
  var dijital = document.getElementById("saat-dijital");
  var tarihEl = document.getElementById("saat-tarih");
  var durumEl = document.getElementById("saat-durum");
  var ilerleme = document.getElementById("saat-ilerleme");

  function dondur(el, derece) { if (el) el.setAttribute("transform", "rotate(" + derece + " 50 50)"); }

  function guncelle() {
    var z = an();
    if (veri.tarih && z.tarih !== veri.tarih) { location.reload(); return; } // gün döndü: yeni çizelge
    var d = durum(z);
    if (kart) {
      dondur(akrep, (z.sa % 12) * 30 + z.dk * 0.5);
      dondur(yelkovan, z.dk * 6 + z.sn * 0.1);
      dondur(saniye, z.sn * 6);
      dijital.innerHTML = iki(z.sa) + "<span>:</span>" + iki(z.dk);
      tarihEl.textContent = tarihYaz.format(z.t);
      kart.className = "saat-kart tur-" + d.tur;
      durumEl.textContent = d.metin;
      durumEl.hidden = !d.metin;
      ilerleme.hidden = d.tur !== "ders";
      if (d.tur === "ders") ilerleme.firstElementChild.style.width = (d.oran * 100).toFixed(1) + "%";
    }
    if (tablo) {
      var etkin = d.tur === "ders" ? d.no : null, sonraki = d.sonraki || null;
      tablo.querySelectorAll("tr[data-no]").forEach(function (tr) {
        tr.classList.toggle("simdi", +tr.dataset.no === etkin);
        tr.classList.toggle("siradaki", +tr.dataset.no === sonraki);
      });
    }
  }

  guncelle();
  setInterval(guncelle, 1000);
})();
