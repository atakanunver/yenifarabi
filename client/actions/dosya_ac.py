"""
actions/dosya_ac.py — Öğretmen talimat modunda dosya/klasör açar.

ÖĞRETMEN TALİMAT MODUNA ÖZEL (kip="talimat"). "hedef" bilinen bir klasör
anahtar kelimesiyse ($HOME altında) doğrudan o klasör açılır. Aksi halde
$HOME altında (gizli dizinler, venv, önbellek vb. hariç, sınırlı derinlik)
dosya adı aranır — TAM eşleşme önce, yoksa alt dize eşleşmesi — bulunursa
xdg-open ile varsayılan uygulamasında açılır (PDF görüntüleyici, medya
oynatıcı, ne ise xdg-open zaten onu seçer). $HOME DIŞINDA arama yapılmaz.
"""

import os
import subprocess
from pathlib import Path

HOME = Path.home()

_KLASORLER = {
    "ev dizini":     HOME,
    "ana dizin":     HOME,
    "home":          HOME,
    "masaüstü":      HOME / "Masaüstü",
    "masaustu":      HOME / "Masaüstü",
    "belgelerim":    HOME / "Belgeler",
    "belgeler":      HOME / "Belgeler",
    "indirilenler":  HOME / "İndirilenler",
    "müzik":         HOME / "Müzik",
    "muzik":         HOME / "Müzik",
}

_HARICI_DIZINLER = {".git", "venv", "__pycache__", "node_modules", ".cache", ".local", ".mozilla"}
_MAX_DERINLIK = 4


def _ac(yol: Path) -> None:
    subprocess.Popen(["xdg-open", str(yol)])


def _dosya_ara(ad: str) -> Path | None:
    ad_lower = ad.lower()
    aday_kismi: Path | None = None
    ev = str(HOME)
    for kok, dizinler, dosyalar in os.walk(ev):
        derinlik = kok[len(ev):].count(os.sep)
        if derinlik >= _MAX_DERINLIK:
            dizinler[:] = []
            continue
        dizinler[:] = [d for d in dizinler if d not in _HARICI_DIZINLER and not d.startswith(".")]
        for dosya in dosyalar:
            if dosya.lower() == ad_lower:
                return Path(kok) / dosya
            if aday_kismi is None and ad_lower in dosya.lower():
                aday_kismi = Path(kok) / dosya
    return aday_kismi


def dosya_ac(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    hedef = (params.get("hedef") or "").strip() or "ev dizini"

    if player:
        player.write_log(f"[TALİMAT] dosya_ac: '{hedef}'")

    klasor = _KLASORLER.get(hedef.lower())
    if klasor is not None:
        if not klasor.exists():
            return f"'{hedef}' klasörü bulunamadı."
        try:
            _ac(klasor)
        except Exception as e:
            return f"Klasör açılamadı: {e}"
        return f"Açılıyor: {hedef}"

    dosya = _dosya_ara(hedef)
    if dosya is None:
        return f"'{hedef}' adında bir dosya bulunamadı."

    try:
        _ac(dosya)
    except Exception as e:
        return f"Dosya açılamadı: {e}"

    return f"Açılıyor: {dosya.name}"
