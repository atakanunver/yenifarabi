"""
actions/uygulama_ac.py — Öğretmen talimat modunda masaüstü uygulaması açar.

ÖĞRETMEN TALİMAT MODUNA ÖZEL (kip="talimat"). Bu tahtada (Pardus ETAP,
`/usr/share/applications/`) kurulu ~80 .desktop dosyasının TAMAMINI değil,
yalnızca aşağıdaki elle seçilmiş listeyi açar — Ayarlar, Paket Kurucu, Sanal
Makine gibi öğretmenin ders sırasında sesle açmasının hiçbir anlamı
olmayan, yanlışlıkla tetiklenirse zararlı olabilecek uygulamalar KASITLI
OLARAK dışarıda: kullanıcı yalnızca kalem/çizim/dosya yöneticisi örneği
verdi. Yeni bir uygulama gerekirse buraya elle eklenir.

Gerçek komutlar bu tahtada doğrulandı (2026-08-23):
  pardus-pen          → "Pardus Kalem" (tr.org.pardus.pen.desktop)
  drawing              → "Çizim" (com.github.maoschanz.drawing.desktop)
  nemo                 → varsayılan dosya yöneticisi
"""

import shlex
import subprocess

_UYGULAMALAR = {
    "kalem":              "pardus-pen",
    "pardus kalem":       "pardus-pen",
    "pen":                "pardus-pen",
    "çizim":              "drawing",
    "cizim":              "drawing",
    "çizim uygulaması":   "drawing",
    "cizim uygulamasi":   "drawing",
    "resim":              "drawing",
    "dosya yöneticisi":   "nemo",
    "dosya yonetici":     "nemo",
    "hesap makinesi":     "gnome-calculator",
    "hesap makinasi":     "gnome-calculator",
    "pdf görüntüleyici":  "evince",
    "pdf goruntuleyici":  "evince",
    "ekran görüntüsü":    "gnome-screenshot",
    "ekran goruntusu":    "gnome-screenshot",
}


def uygulama_ac(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    ad = (params.get("uygulama") or "").strip().lower()

    if player:
        player.write_log(f"[TALİMAT] uygulama_ac: '{ad}'")

    if not ad:
        return "Hangi uygulamayı açacağımı söyleyin."

    komut = _UYGULAMALAR.get(ad)
    if komut is None:
        bilinenler = ", ".join(sorted(set(_UYGULAMALAR)))
        return f"'{ad}' tanınan bir uygulama değil. Bilinenler: {bilinenler}."

    try:
        subprocess.Popen(shlex.split(komut))
    except Exception as e:
        return f"Uygulama açılamadı: {e}"

    return f"Açılıyor: {ad}"
