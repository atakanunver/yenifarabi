// Panel görünümü Progmatik arayüzünden (Panel, Buton, Rozet, Bildirim, SayfaBaslik). Renkler HAM DEĞİL:
// hepsi static/tema.css belirteçlerine bağlı, böylece 9 tema (data-tema) çalışır. Preflight kapalı:
// pano.css + bilesen.css taban kuralları zaten yükleniyor, sonradan gelen preflight onları ezerdi.
// Opaklık eki (/15) belirteç renklerinde ÇALIŞMAZ; yarı saydam ton için "-zemin" adlarını kullan.
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["../templates/**/*.html", "../static/*.js", "!../static/pano-cam.js", "../*.py"],
  corePlugins: { preflight: false },
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      zemin: "var(--renk-zemin)",
      yuzey: "var(--renk-yuzey)",
      "yuzey-2": "var(--renk-yuzey-2)",
      kenar: "var(--renk-kenar)",
      "kenar-vurgu": "var(--renk-kenar-vurgu)",
      metin: "var(--renk-metin)",
      "metin-soluk": "var(--renk-metin-soluk)",
      "metin-cok-soluk": "var(--renk-metin-cok-soluk)",
      acik: "var(--renk-sabit-acik)",
      birincil: "var(--renk-birincil)",
      "birincil-koyu": "var(--renk-birincil-koyu)",
      "birincil-zemin": "var(--renk-birincil-zemin)",
      yesil: "var(--renk-yesil)",
      "yesil-zemin": "var(--renk-yesil-zemin)",
      kirmizi: "var(--renk-kirmizi)",
      "kirmizi-zemin": "var(--renk-kirmizi-zemin)",
      amber: "var(--renk-amber)",
      "amber-zemin": "var(--renk-amber-zemin)",
      gri: "var(--renk-gri)",
      "gri-zemin": "var(--renk-gri-zemin)",
    },
    extend: {
      borderRadius: { tema: "var(--yaricap)", "tema-buyuk": "var(--yaricap-buyuk)" },
      boxShadow: { kart: "var(--renk-golge-kart)" },
      borderColor: { DEFAULT: "var(--renk-kenar)" },
      ringColor: { DEFAULT: "var(--renk-birincil)" },
    },
  },
  plugins: [],
};
