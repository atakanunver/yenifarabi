"""Kazanım test sonuçları ve soru havuzu (PostgreSQL soru_havuzu) — yalnızca SELECT.

ozet() saf fonksiyondur: Google Form kazanım testleri + platform içi test ödevleri
(ders, kazanım) bazında birleştirilir.
"""

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass

from ayarlar import AYAR

from kaynaklar import KaynakHatasi


@dataclass(frozen=True)
class TestSonucu:
    __test__ = False  # pytest bunu test sınıfı sanmasın

    ders: str
    hafta: int
    kazanim: str
    dogru: int
    toplam: int
    tarih: str


@dataclass
class KazanimDurum:
    ders: str
    kazanim: str
    dogru: int
    toplam: int

    @property
    def yuzde(self) -> int:
        return round(100 * self.dogru / self.toplam) if self.toplam else 0

    def basarili(self, esik: float) -> bool:
        return self.toplam > 0 and self.dogru / self.toplam >= esik


@contextmanager
def _baglan():
    import psycopg2

    try:
        c = psycopg2.connect(
            host="127.0.0.1", dbname=AYAR.havuz_db, user="farabi", connect_timeout=3
        )
    except psycopg2.Error as e:
        raise KaynakHatasi(f"soru havuzu veritabanına bağlanılamadı: {e}") from e
    try:
        c.set_session(readonly=True, autocommit=True)
        yield c
    except psycopg2.Error as e:
        raise KaynakHatasi(f"soru havuzu sorgusu başarısız: {e}") from e
    finally:
        c.close()


def form_sonuclari(okul_no: int) -> list[TestSonucu]:
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT t.ders, t.hafta, t.kazanim, count(*) FILTER (WHERE c.dogru), count(*),"
            " to_char(min(c.zaman) AT TIME ZONE 'Europe/Istanbul', 'YYYY-MM-DD')"
            " FROM form_cevap c JOIN form_testi t ON t.id = c.form_testi_id"
            " WHERE c.okul_no = %s GROUP BY t.id, t.ders, t.hafta, t.kazanim"
            " ORDER BY min(c.zaman) DESC",
            (okul_no,),
        )
        return [TestSonucu(*r) for r in cur.fetchall()]


def havuz_dersleri(seviye: int) -> list[str]:
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ders FROM soru WHERE durum = 'onayli' AND sinif = %s ORDER BY ders",
            (seviye,),
        )
        return [r[0] for r in cur.fetchall()]


def havuz_sorulari(seviye: int, ders: str, limit: int = 40) -> list[dict]:
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id, konu, soru, secenekler, dogru_index FROM soru"
            " WHERE durum = 'onayli' AND sinif = %s AND ders = %s"
            " ORDER BY kullanim_sayisi, id DESC LIMIT %s",
            (seviye, ders, limit),
        )
        return [_havuz_satiri(r) for r in cur.fetchall()]


def havuz_sorulari_getir(idler: list[int]) -> list[dict]:
    if not idler:
        return []
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id, konu, soru, secenekler, dogru_index FROM soru"
            " WHERE durum = 'onayli' AND id = ANY(%s) ORDER BY id",
            (list(idler),),
        )
        return [_havuz_satiri(r) for r in cur.fetchall()]


def _havuz_satiri(r) -> dict:
    return {
        "id": r[0],
        "konu": r[1],
        "soru": r[2],
        "secenekler": list(r[3]),
        "dogru_index": r[4],
    }


def ozet(
    form: list[TestSonucu], odev: list[tuple[str, str, bool]]
) -> dict[str, list[KazanimDurum]]:
    toplam: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for t in form:
        toplam[(t.ders, t.kazanim)][0] += t.dogru
        toplam[(t.ders, t.kazanim)][1] += t.toplam
    for ders, kaz, dogru in odev:
        toplam[(ders, kaz)][0] += int(dogru)
        toplam[(ders, kaz)][1] += 1
    sonuc: dict[str, list[KazanimDurum]] = defaultdict(list)
    for (ders, kaz), (d, n) in sorted(toplam.items()):
        sonuc[ders].append(KazanimDurum(ders, kaz, d, n))
    return dict(sonuc)


def ders_ozeti(
    o: dict[str, list[KazanimDurum]], esik: float
) -> list[tuple[str, int, int]]:
    """(ders, başarılı kazanım sayısı, toplam kazanım sayısı)."""
    return [
        (ders, sum(d.basarili(esik) for d in liste), len(liste))
        for ders, liste in sorted(o.items())
    ]
