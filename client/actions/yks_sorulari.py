"""
actions/yks_sorulari.py — Konuyla ilgili YKS (TYT/AYT) çıkmış sorularını
sunucudan (server/yks.py) getirir, PDF sayfası GÖRÜNTÜ olarak gösterilir.

Server-taşıma (2026-08-14): arama + sıralı-sunum oturumu artık BURADA değil,
`server/yks.py`de (`derslik` anahtarlı, çoklu tahta güvenli — bkz. o dosyanın
modül dokümanı). Bu dosya yalnızca HTTP çağrısı + görüntü indirme yapıyor.
"""

from pathlib import Path

import requests
from core.tahta import auth_headers as _auth_headers
from core.tahta import sunucu_url as _sunucu_url

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "icerik" / "onbellek" / "yks_sayfa"
_CACHE_LIMIT = 30

ZAMAN_ASIMI = 15.0


def _cache_yaz(veri: bytes, dosya_adi: str, sayfa: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yol = CACHE_DIR / f"{dosya_adi}_s{sayfa}.png"
    yol.write_bytes(veri)
    try:
        dosyalar = sorted(CACHE_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)
        for eski in dosyalar[:-_CACHE_LIMIT]:
            eski.unlink(missing_ok=True)
    except Exception:
        pass
    return yol


def _sayfayi_goster(player, log, dosya_adi: str, sayfa: int) -> None:
    """Görüntüyü sunucudan çekip gösterir. Başarısız olursa sessizce
    atlanır — sınıfa teknik sorun anlatılmaz (mimari.md §2), metinle devam
    edilir (bu araç zaten görüntüsüz de anlamlı bir metin döner)."""
    try:
        r = requests.get(f"{_sunucu_url()}/api/egitim/yks_sayfa",
                          params={"dosya": dosya_adi, "sayfa": sayfa},
                          headers=_auth_headers(), timeout=ZAMAN_ASIMI)
        r.raise_for_status()
    except Exception as e:
        log(f"[YKS] sayfa görüntüsü alınamadı: {type(e).__name__}: {e}")
        return
    onbellek_yolu = _cache_yaz(r.content, dosya_adi, sayfa)
    if player is not None and hasattr(player, "show_image"):
        player.show_image(f"YKS — {dosya_adi[:24]} s.{sayfa}", str(onbellek_yolu))


def yks_sorulari(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    try:
        from core import tahta
        derslik = tahta.derslik() or "bilinmeyen"
    except Exception:
        derslik = "bilinmeyen"

    istek = {
        "derslik": derslik,
        "ders": (p.get("ders") or "").strip(),
        "konu": (p.get("konu") or "").strip(),
        "sonraki": bool(p.get("sonraki")),
        "adet": int(p.get("adet") or 3),
    }

    try:
        r = requests.post(f"{_sunucu_url()}/api/egitim/yks_sorusu", json=istek,
                           headers=_auth_headers(), timeout=ZAMAN_ASIMI)
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        log(f"[YKS] sunucu hatası: {type(e).__name__}: {e}")
        return ("Çıkmış soru sunucusuna şu an ulaşılamıyor, efendim. "
                "Kitaptaki örneklerle devam edelim.")

    log(f"[YKS] status={veri.get('status')} · {veri.get('latency_ms')}ms")

    if veri.get("status") == "ok" and veri.get("dosya_adi") and veri.get("sayfa"):
        _sayfayi_goster(player, log, veri["dosya_adi"], veri["sayfa"])

    return veri.get("metin") or "Çıkmış soru bulunamadı, efendim."
