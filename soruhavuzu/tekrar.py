"""soruhavuzu/tekrar.py — aynı ders+sınıfta neredeyse aynı soruları eler (bilgehan bge-m3)."""

import sys
from pathlib import Path

import numpy as np

ESIK = 0.92


class Eleyici:
    def __init__(self, gomucu):
        self.gomucu = gomucu
        self.vektorler: dict[tuple[str, int], list[np.ndarray]] = {}

    def _ekle(self, ders: str, sinif: int, v: np.ndarray) -> None:
        self.vektorler.setdefault((ders, sinif), []).append(v)

    def yukle(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ders, sinif, soru FROM soru WHERE durum IN ('uretildi','onayli')"
            )
            satirlar = cur.fetchall()
        for i in range(0, len(satirlar), 64):
            parca = satirlar[i : i + 64]
            vler = self.gomucu.encode([s[2] for s in parca], normalize_embeddings=True)
            for (ders, sinif, _), v in zip(parca, vler):
                self._ekle(ders, sinif, np.asarray(v))

    def kopya_mi(self, ders: str, sinif: int, soru: str) -> bool:
        v = np.asarray(self.gomucu.encode([soru], normalize_embeddings=True)[0])
        onceki = self.vektorler.get((ders, sinif), [])
        if onceki and float(np.max(np.stack(onceki) @ v)) >= ESIK:
            return True
        self._ekle(ders, sinif, v)
        return False


# Aynı ders+sınıfta aynı soru metni VE aynı şık kümesi = birebir kopya (içe aktarma betikleri Eleyici'yi
# atlıyor). Yalnızca metin aynı, şıklar farklıysa kopya sayılmaz (ortak yönergeli ayrı sorular).
_KOPYA_SQL = """
WITH anahtarli AS (
  SELECT id, durum,
         row_number() OVER (
           PARTITION BY ders, sinif,
                        lower(regexp_replace(soru, '\\s+', ' ', 'g')),
                        (SELECT string_agg(lower(btrim(v)), '|' ORDER BY lower(btrim(v)))
                           FROM jsonb_array_elements_text(secenekler) v)
           ORDER BY (durum = 'onayli') DESC, id) AS sira
  FROM soru
  WHERE durum IN ('onayli', 'uretildi') AND NOT (sinif = ANY(%s))
)
SELECT id FROM anahtarli WHERE sira > 1
"""


def kopyalari_isaretle(conn, kuru: bool = False) -> int:
    """Birebir kopyalardan ilkini (onaylı öncelikli, sonra en düşük id) bırakıp gerisini 'kopya' yapar."""
    from soruhavuzu import vt

    with conn.cursor() as cur:
        cur.execute(_KOPYA_SQL, (list(vt.DONDURULMUS_SINIFLAR),))
        idler = [r[0] for r in cur.fetchall()]
        if idler and not kuru:
            cur.execute(
                "UPDATE soru SET durum='kopya', denetim_notu=COALESCE(denetim_notu||' | ','')||'birebir kopya' "
                "WHERE id = ANY(%s)", (idler,))
            conn.commit()
    return len(idler)


def _gomucu():
    """farabi-api'nin kullandığı bilgehan gömme istemcisi (server/uzak_model.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
    import uzak_model

    embed, _reranker = uzak_model.olustur(*uzak_model.ayar_oku(), zaman_asimi=30.0)
    return embed
