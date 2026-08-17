"""
actions/pdf_sayfa.py — Kitabın belirli bir SAYFA NUMARASINI ekrana görüntü
olarak yansıtır. Sayfa artık PyMuPDF ile BURADA değil, `server/icerik.py`de
render ediliyor (server-taşıma, 2026-08-14) — client yalnızca PNG'i indirip
yerel bir küçük cache'e yazar ve gösterir.

`ders_icerigi` ile farkı ve `ders` neden zorunlu — değişmedi, bkz. eski
modül dokümanı (git geçmişi).

Yerel cache boyut sınırlı LRU: en fazla `_CACHE_LIMIT` dosya tutulur, en eski
dosyalar silinir — client'ta "minimum dosya" ilkesi (CLAUDE.md Kural 1),
sunucudaki kalıcı render cache zaten tüm tahtalar için tek doğruluk kaynağı.
"""

from pathlib import Path

import requests

from core.tahta import sunucu_url as _sunucu_url

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "icerik" / "onbellek" / "pdf_sayfa"
_CACHE_LIMIT = 30

ZAMAN_ASIMI = 15.0


def _cache_yaz(veri: bytes, ders: str, sayfa: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yol = CACHE_DIR / f"{ders}_s{sayfa}.png"
    yol.write_bytes(veri)
    _cache_budala()
    return yol


def _cache_budala() -> None:
    """En fazla _CACHE_LIMIT dosya — fazlası en-eski-önce silinir."""
    try:
        dosyalar = sorted(CACHE_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)
        for eski in dosyalar[:-_CACHE_LIMIT]:
            eski.unlink(missing_ok=True)
    except Exception:
        pass


def pdf_sayfa(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    try:
        sayfa = int(p.get("sayfa"))
    except (TypeError, ValueError):
        return "Sayfa numarası belirtilmedi ya da geçersiz. 'sayfa' parametresiyle bir tam sayı ver."
    if sayfa < 1:
        return "Sayfa numarası 1'den küçük olamaz."

    ders = (p.get("ders") or "").strip()
    sinif = (p.get("sinif") or "").strip()
    if not sinif:
        try:
            from core import tahta
            sinif = tahta.sinif_duzeyi() or ""
        except Exception:
            pass

    if not ders:
        log("[PDF Sayfa] ders verilmedi, eşleme yapılmadı")
        return "Ders belirtilmedi. 'ders' parametresiyle ver — aksi hâlde yanlış kitaptan sayfa gösterme riski var."

    try:
        r = requests.get(f"{_sunucu_url()}/api/egitim/pdf_sayfa",
                          params={"ders": ders, "sinif": sinif or None, "sayfa": sayfa},
                          timeout=ZAMAN_ASIMI)
        if r.status_code != 200:
            detay = ""
            try:
                detay = r.json().get("detail", "")
            except Exception:
                pass
            log(f"[PDF Sayfa] sunucu {r.status_code}: {detay}")
            return detay or "Sayfa render edilemedi."
    except Exception as e:
        log(f"[PDF Sayfa] sunucu hatası: {type(e).__name__}: {e}")
        return "Sayfa render edilemedi: sunucuya ulaşılamadı."

    onbellek_yolu = _cache_yaz(r.content, ders, sayfa)
    log(f"[PDF Sayfa] {ders} · s.{sayfa} gösteriliyor")
    if player is not None and hasattr(player, "show_image"):
        player.show_image(f"{ders.upper()} — s.{sayfa}", str(onbellek_yolu))

    return f"{ders} kitabının {sayfa}. sayfası ekranda gösteriliyor."
