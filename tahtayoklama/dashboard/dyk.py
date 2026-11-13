"""DYK kursu tanımları (config/dyk.json, gitignore'lu — öğrenci verisi içerir).

scripts/dyk_ice_aktar.py üretir. Biçim:
    {"siniflar": {"11": {"derslik": "10-A", "ad": "11. Sınıf DYK", "dersler": [
        {"kod": "DYK-11-COGRAFYA", "ad": "Coğrafya", "ogretmen": "...",
         "uyeler": [{"no": 123, "ad_soyad": "Deniz Deneme"}]}]}},
     "program": {"11": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30",
                         "kod": "DYK-11-COGRAFYA", "ders_no": 1}]}}
Panelden yalnız `ogretmen` ve `uyeler` düzenlenir (guncelle). `kod` ve program hiç değişmez:
DYK yoklama kayıtları ve tahtadaki roster dosya adı koda bağlı.
DYK yoklaması sınıf yoklamasından AYRI tutulur; kod tahtada roster dosya adı ve kayıttaki
`sinif` olur. Dosya yok/bozuksa boş yapı döner.
"""

import json
import os
from pathlib import Path

DYK_DOSYASI = Path(__file__).resolve().parent / "config" / "dyk.json"
ONEK = "DYK-"
_METIN_AZAMI = 80


def _bos() -> dict:
    return {"siniflar": {}, "program": {}}


def yukle() -> dict:
    try:
        veri = json.loads(DYK_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _bos()
    if not isinstance(veri, dict):
        return _bos()
    siniflar, program = veri.get("siniflar"), veri.get("program")
    return {
        "siniflar": siniflar if isinstance(siniflar, dict) else {},
        "program": program if isinstance(program, dict) else {},
    }


def dersler() -> list[dict]:
    """Düz liste: her ders + sinif_grubu ("11"/"12") + derslik ("10-A"/"12-B")."""
    sonuc = []
    for grup, sinif in yukle()["siniflar"].items():
        if not isinstance(sinif, dict):
            continue
        for d in sinif.get("dersler") or []:
            if isinstance(d, dict) and d.get("kod"):
                sonuc.append({**d, "sinif_grubu": grup, "derslik": sinif.get("derslik", "")})
    return sonuc


def bul(kod: str) -> dict | None:
    return next((d for d in dersler() if d["kod"] == kod), None)


def isimler(ders: dict) -> dict[str, str]:
    """no -> ad_soyad (yoklayici._roster_by_no ile aynı biçim)."""
    return {str(u["no"]): u["ad_soyad"] for u in ders["uyeler"]}


def roster_json(ders: dict) -> str:
    """Tahta roster'ı (kulupler.roster_json ile aynı şema; ad_soyad'a sınıf eki yok)."""
    return json.dumps(
        {
            "sinif": ders["kod"],
            "ad": f"{ders['sinif_grubu']}. sınıf {ders['ad']}",
            "ogrenciler": [{"no": u["no"], "ad_soyad": u["ad_soyad"]} for u in ders["uyeler"]],
        },
        ensure_ascii=False, indent=2,
    )


def rosterlari(sinif_ad: str | None) -> dict[str, str]:
    """Derslik == sinif_ad olan derslerin {kod: roster_json}; eşleşme yoksa {}."""
    if not sinif_ad:
        return {}
    return {d["kod"]: roster_json(d) for d in dersler() if d["derslik"] == sinif_ad}


def program_json(sinif_ad: str | None) -> str | None:
    """O derslik grubunun {"oturumlar": [...]} JSON'u; eşleşme yoksa None."""
    if not sinif_ad:
        return None
    veri = yukle()
    for grup, sinif in veri["siniflar"].items():
        if isinstance(sinif, dict) and sinif.get("derslik") == sinif_ad:
            return json.dumps({"oturumlar": veri["program"].get(grup, [])}, ensure_ascii=False, indent=1)
    return None


def uyeleri_ayristir(nolar: list[str], adlar: list[str]) -> list[dict]:
    """Form sütunlarından üye listesi; boş satır atlanır. Geçersiz/tekrarlı no → ValueError."""
    uyeler, gorulen = [], set()
    for no, ad in zip(nolar, adlar):
        no, ad = no.strip(), ad.strip()
        if not no and not ad:
            continue
        try:
            no_int = int(no)
        except ValueError:
            raise ValueError(f"Geçersiz öğrenci no: {no!r}")
        if no_int <= 0:
            raise ValueError(f"Geçersiz öğrenci no: {no!r}")
        if not ad or len(ad) > _METIN_AZAMI:
            raise ValueError(f"Eksik ya da çok uzun ad (no {no_int}).")
        if no_int in gorulen:
            raise ValueError(f"Aynı öğrenci no iki kez: {no_int}")
        gorulen.add(no_int)
        uyeler.append({"no": no_int, "ad_soyad": ad})
    return uyeler


def _kaydet(veri: dict) -> None:
    """Atomik yazım; dosya öğrenci verisi içerdiği için 0600."""
    gecici = DYK_DOSYASI.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(gecici, 0o600)
    os.replace(gecici, DYK_DOSYASI)


def guncelle(kod: str, ogretmen: str, uyeler: list[dict]) -> None:
    ogretmen = ogretmen.strip()
    if len(ogretmen) > _METIN_AZAMI:
        raise ValueError("Öğretmen adı çok uzun.")
    veri = yukle()
    for sinif in veri["siniflar"].values():
        if not isinstance(sinif, dict):
            continue
        for d in sinif.get("dersler") or []:
            if isinstance(d, dict) and d.get("kod") == kod:
                d.update(ogretmen=ogretmen, uyeler=uyeler)
                _kaydet(veri)
                return
    raise KeyError(kod)
