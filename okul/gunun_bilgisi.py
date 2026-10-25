"""Günün bilgisi kartı (2026-10-25): "Tarihte Bugün" + "Bugün dünyada / Türkiye'de ne günü".

Kaynak `config/gunun_bilgisi.json` (elle derlenmiş, AA-GG anahtarlı; her istekte okunur, içerik değişikliği restart
istemez). Yalnızca sabit tarihli günler; o güne kayıt yoksa ilgili bölüm görünmez, dosya yok/bozuksa kart gizlenir.
Öğrenci, öğretmen ve veli ana sayfalarının en altında, dikkat dağıtmayan sade bir kart olarak gösterilir.
"""

import json
import logging
from pathlib import Path

import zaman
from ayarlar import KOK

log = logging.getLogger("okul.gunun_bilgisi")
YOL = KOK / "config" / "gunun_bilgisi.json"


def bugun(yol: Path | None = None) -> dict | None:
    """{'gunler': [metin], 'tarihte': [{'yil', 'olay'}]} (yıla göre sıralı); bugün için kayıt yoksa None."""
    anahtar = zaman.simdi().strftime("%m-%d")
    try:
        veri = json.loads((yol or YOL).read_text(encoding="utf-8"))
        gunler = [str(g) for g in veri.get("gunler", {}).get(anahtar, [])]
        tarihte = sorted(
            ({"yil": int(t["yil"]), "olay": str(t["olay"])} for t in veri.get("tarihte", {}).get(anahtar, [])), key=lambda t: t["yil"]
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        log.warning("gunun_bilgisi okunamadı: %s", type(e).__name__)
        return None
    return {"gunler": gunler, "tarihte": tarihte} if gunler or tarihte else None
