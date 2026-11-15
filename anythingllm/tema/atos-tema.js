// Atos (AnythingLLM) tema yöneticisi ve sabit köşe tema seçicisi.
// Bağımlılık yok; FOUC önleme için <head> içinde senkron çalışır.
(function () {
  var ANAHTAR = "atos_tema";
  var VARSAYILAN = "cam";
  var TEMALAR = [
    ["cam", "Uzamsal cam"],
    ["sade-koyu", "Sade koyu"],
    ["kurumsal", "Sakin kurumsal"],
    ["lacivert", "Lacivert"],
    ["argon", "Argon açık"],
    ["argon-koyu", "Argon koyu"],
    ["material", "Material açık"],
    ["material-koyu", "Material koyu"],
    ["black", "Black"],
    ["koyu", "Taş Tahta"]
  ];

  function temaGecerliMi(ad) {
    for (var i = 0; i < TEMALAR.length; i++) {
      if (TEMALAR[i][0] === ad) return true;
    }
    return false;
  }

  function temaAdiBul(ad) {
    for (var i = 0; i < TEMALAR.length; i++) {
      if (TEMALAR[i][0] === ad) return TEMALAR[i][1];
    }
    return ad;
  }

  function kayitliTemaGetir() {
    var kayitli = null;
    try {
      kayitli = localStorage.getItem(ANAHTAR);
    } catch (e) {
      /* depolama kapalıysa varsayılana düş */
    }
    return temaGecerliMi(kayitli) ? kayitli : VARSAYILAN;
  }

  var aktifTema = kayitliTemaGetir();

  function temaUygula(tema) {
    if (!temaGecerliMi(tema)) return;
    aktifTema = tema;
    if (document.documentElement.dataset.tema !== tema) {
      document.documentElement.dataset.tema = tema;
    }
    try {
      localStorage.setItem(ANAHTAR, tema);
    } catch (e) {
      /* depolama kapalıysa yalnız DOM'a uygula */
    }
    var etiket = document.querySelector("#atos-tema-dugme .atos-tema-etiket");
    if (etiket) etiket.textContent = temaAdiBul(tema);
    var dugmeler = document.querySelectorAll("[data-atos-tema]");
    for (var i = 0; i < dugmeler.length; i++) {
      duzmeyiGuncelle(dugmeler[i], tema);
    }
  }

  function duzmeyiGuncelle(buton, tema) {
    var secili = buton.dataset.atosTema === tema;
    buton.setAttribute("aria-checked", secili ? "true" : "false");
    buton.tabIndex = secili ? 0 : -1;
  }

  // FOUC önleme: betik yüklendiği anda ilk boyamadan önce uygula
  document.documentElement.dataset.tema = aktifTema;

  window.atosTemaUygula = temaUygula;
  window.atosTemaSonraki = function () {
    for (var i = 0; i < TEMALAR.length; i++) {
      if (TEMALAR[i][0] === aktifTema) {
        temaUygula(TEMALAR[(i + 1) % TEMALAR.length][0]);
        return;
      }
    }
    temaUygula(VARSAYILAN);
  };

  var sarici = null;
  var acDugme = null;
  var panel = null;
  var ogeDugmeleri = [];

  function panelKapat(odakDon) {
    if (!panel || panel.hidden) return false;
    panel.hidden = true;
    if (acDugme) {
      acDugme.setAttribute("aria-expanded", "false");
      if (odakDon) acDugme.focus();
    }
    return true;
  }

  function panelAc(odakSecili) {
    if (!panel || !acDugme) return;
    panel.hidden = false;
    acDugme.setAttribute("aria-expanded", "true");
    if (odakSecili) {
      var hedef = panel.querySelector('[aria-checked="true"]') || ogeDugmeleri[0];
      if (hedef) hedef.focus();
    }
  }

  function bilesenOlustur() {
    if (sarici) return sarici;

    sarici = document.createElement("div");
    sarici.id = "atos-tema-secici";

    acDugme = document.createElement("button");
    acDugme.id = "atos-tema-dugme";
    acDugme.type = "button";
    acDugme.setAttribute("aria-haspopup", "true");
    acDugme.setAttribute("aria-expanded", "false");
    acDugme.setAttribute("aria-controls", "atos-tema-panel");
    acDugme.setAttribute("aria-label", "Tema seçici");
    acDugme.title = "Farabi temaları";

    var nokta = document.createElement("span");
    nokta.className = "atos-tema-nokta";
    nokta.setAttribute("aria-hidden", "true");

    var etiket = document.createElement("span");
    etiket.className = "atos-tema-etiket";
    etiket.textContent = temaAdiBul(aktifTema);

    acDugme.appendChild(nokta);
    acDugme.appendChild(etiket);

    panel = document.createElement("div");
    panel.id = "atos-tema-panel";
    panel.hidden = true;
    panel.setAttribute("role", "radiogroup");
    panel.setAttribute("aria-labelledby", "atos-tema-baslik");

    var baslik = document.createElement("div");
    baslik.id = "atos-tema-baslik";
    baslik.className = "atos-tema-baslik";
    baslik.textContent = "Temalar";

    var liste = document.createElement("div");
    liste.className = "atos-tema-liste";

    ogeDugmeleri = [];
    for (var i = 0; i < TEMALAR.length; i++) {
      (function (id, ad) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "atos-tema-oge";
        b.setAttribute("role", "radio");
        b.dataset.atosTema = id;
        b.textContent = ad;
        duzmeyiGuncelle(b, aktifTema);
        b.addEventListener("click", function () {
          temaUygula(id);
        });
        liste.appendChild(b);
        ogeDugmeleri.push(b);
      })(TEMALAR[i][0], TEMALAR[i][1]);
    }

    panel.appendChild(baslik);
    panel.appendChild(liste);
    sarici.appendChild(acDugme);
    sarici.appendChild(panel);

    acDugme.addEventListener("click", function (e) {
      e.stopPropagation();
      if (panel.hidden) panelAc(e.detail === 0);
      else panelKapat(false);
    });

    acDugme.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        panelAc(true);
      }
    });

    panel.addEventListener("keydown", function (e) {
      var idx = ogeDugmeleri.indexOf(document.activeElement);
      if (idx === -1) return;
      var sonraki = -1;
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        sonraki = (idx + 1) % ogeDugmeleri.length;
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        sonraki = (idx - 1 + ogeDugmeleri.length) % ogeDugmeleri.length;
      } else if (e.key === "Home") {
        sonraki = 0;
      } else if (e.key === "End") {
        sonraki = ogeDugmeleri.length - 1;
      }
      if (sonraki !== -1) {
        e.preventDefault();
        ogeDugmeleri[sonraki].focus();
      }
    });

    document.addEventListener("click", function (e) {
      if (sarici && !sarici.contains(e.target)) panelKapat(false);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (panelKapat(true)) e.preventDefault();
      }
    });

    return sarici;
  }

  function bagla() {
    if (!document.body) return;
    var mevcut = document.getElementById("atos-tema-secici");
    if (!mevcut) {
      document.body.appendChild(bilesenOlustur());
    }
    if (document.documentElement.dataset.tema !== aktifTema) {
      document.documentElement.dataset.tema = aktifTema;
    }
  }

  function baslat() {
    bagla();
    if (typeof MutationObserver === "undefined") return;
    var gozlemci = new MutationObserver(function () {
      if (document.body && !document.getElementById("atos-tema-secici")) {
        bagla();
      }
      if (document.documentElement.dataset.tema !== aktifTema) {
        document.documentElement.dataset.tema = aktifTema;
      }
    });
    gozlemci.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-tema"]
    });
    if (document.body) {
      gozlemci.observe(document.body, { childList: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", baslat);
  } else {
    baslat();
  }
})();
