"""Kulüp tanımları (config/kulupler.json, gitignore'lu — öğrenci verisi içerir).

scripts/kulup_ice_aktar.py üretir. Biçim (liste):
    [{"kod": "KULUP-BEYAZAY", "ad": "Beyazay Kulübü", "danisman": "...",
      "sinif": "10-A", "uyeler": [{"no": 206, "ad_soyad": "Deniz Deneme", "sinif": "9-A"}]}]
2026-10-23'ten beri panelden de düzenlenir (/admin/kulupler; guncelle/ekle). `kod` hiç
değişmez: kulup_yoklama kayıtları ve tahtadaki roster dosya adı ona bağlı.
Kulüp yoklaması sınıf yoklamasından AYRI tutulur (kulup_yoklama tablosu); kod
tahtada roster dosya adı ve kayıttaki `sinif` olur. Dosya yok/bozuksa boş liste.
"""

import json
import os
import re
from pathlib import Path

KULUP_DOSYASI = Path(__file__).resolve().parent / "config" / "kulupler.json"


def yukle() -> list[dict]:
    try:
        veri = json.loads(KULUP_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [k for k in veri if isinstance(k, dict) and k.get("kod")] if isinstance(veri, list) else []


def bul(kod: str) -> dict | None:
    return next((k for k in yukle() if k["kod"] == kod), None)


def isimler(kulup: dict) -> dict[str, str]:
    """no -> ad_soyad (yoklayici._roster_by_no ile aynı biçim)."""
    return {str(u["no"]): u["ad_soyad"] for u in kulup["uyeler"]}


def roster_json(kulup: dict) -> str:
    """Tahta roster'ı (admin._roster_payload_olustur ile aynı şema + "ad")."""
    return json.dumps(
        {
            "sinif": kulup["kod"],
            "ad": kulup["ad"],
            "ogrenciler": [
                {"no": u["no"], "ad_soyad": f"{u['ad_soyad']} ({u['sinif']})"}
                for u in kulup["uyeler"]
            ],
        },
        ensure_ascii=False, indent=2,
    )


# --- Panelden düzenleme (2026-10-23) ---
# kod_uret: scripts/kulup_ice_aktar.py'deki kod_uret ile aynı kural (ilk sözcük, ASCII büyük harf).
_ASCII = str.maketrans("ÇĞİIÖŞÜçğıöşü", "CGIIOSUcgiosu")
_KOD_DISI = re.compile(r"[^A-Z0-9]")
_METIN_AZAMI = 80


def kod_uret(ad: str) -> str:
    ilk = ad.split()[0].replace("i", "İ").replace("ı", "I").upper().translate(_ASCII)
    return "KULUP-" + _KOD_DISI.sub("", ilk)[:20]


def uyeleri_ayristir(nolar: list[str], adlar: list[str], siniflar: list[str]) -> list[dict]:
    """Form sütunlarından üye listesi; boş satır atlanır. Geçersiz/tekrarlı no → ValueError."""
    uyeler, gorulen = [], set()
    for no, ad, sinif in zip(nolar, adlar, siniflar):
        no, ad, sinif = no.strip(), ad.strip(), sinif.strip()
        if not no and not ad:
            continue
        try:
            no_int = int(no)
        except ValueError:
            raise ValueError(f"Geçersiz öğrenci no: {no!r}")
        if not ad or len(ad) > _METIN_AZAMI or len(sinif) > 10:
            raise ValueError(f"Eksik ya da çok uzun bilgi (no {no_int}).")
        if no_int in gorulen:
            raise ValueError(f"Aynı öğrenci no iki kez: {no_int}")
        gorulen.add(no_int)
        uyeler.append({"no": no_int, "ad_soyad": ad, "sinif": sinif})
    return uyeler


def _kaydet(liste: list[dict]) -> None:
    """Atomik yazım; dosya öğrenci verisi içerdiği için 0600."""
    gecici = KULUP_DOSYASI.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(liste, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(gecici, 0o600)
    os.replace(gecici, KULUP_DOSYASI)


def guncelle(kod: str, ad: str, danisman: str, sinif: str, uyeler: list[dict]) -> None:
    ad, danisman, sinif = ad.strip(), danisman.strip(), sinif.strip()
    if not ad or len(ad) > _METIN_AZAMI or len(danisman) > _METIN_AZAMI:
        raise ValueError("Kulüp adı boş ya da çok uzun.")
    liste = yukle()
    kulup = next((k for k in liste if k["kod"] == kod), None)
    if kulup is None:
        raise KeyError(kod)
    kulup.update(ad=ad, danisman=danisman, sinif=sinif, uyeler=uyeler)
    _kaydet(liste)


def ekle(ad: str, sinif: str) -> str:
    ad = ad.strip()
    if not ad or len(ad) > _METIN_AZAMI:
        raise ValueError("Kulüp adı boş ya da çok uzun.")
    liste = yukle()
    kodlar = {k["kod"] for k in liste}
    temel = kod_uret(ad)
    kod, n = temel, 2
    while kod in kodlar:
        kod, n = f"{temel}{n}", n + 1
    liste.append({"kod": kod, "ad": ad, "danisman": "", "sinif": sinif.strip(), "uyeler": []})
    _kaydet(liste)
    return kod
