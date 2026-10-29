"""Kazanım test sonuçları ve soru havuzu (PostgreSQL soru_havuzu) — yalnızca SELECT.

ozet() saf fonksiyondur: Google Form kazanım testleri + platform içi test ödevleri
(ders, kazanım) bazında birleştirilir.
"""

import json
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta

import zaman
from ayarlar import AYAR

from kaynaklar import KaynakHatasi


MIN_SORU = 3  # kazanım başına; altında durum etiketi yok (gelisim.MIN_SORU ile aynı ilke)


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

    @property
    def yeterli(self) -> bool:
        """Birkaç soruluk veriyle 'çalış' etiketi basılmaz."""
        return self.toplam >= MIN_SORU

    def basarili(self, esik: float) -> bool:
        return self.toplam > 0 and self.dogru / self.toplam >= esik


@contextmanager
def _baglan():
    import psycopg2

    try:
        c = psycopg2.connect(
            host="127.0.0.1",
            dbname=AYAR.havuz_db,
            user="farabi",
            connect_timeout=3,
            options="-c statement_timeout=3000",
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


def havuz_sorulari(seviye: int, ders: str, limit: int = 40, yasak: list[int] | None = None) -> list[dict]:
    """Konu'ya göre gruplanabilsin diye konu sırasıyla döner (her konu içinde en az kullanılan önce)."""
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.konu, s.soru, s.secenekler, s.dogru_index, k.kod, k.metin"
            " FROM soru s LEFT JOIN kazanim k ON k.id = s.kazanim_id"
            " WHERE s.durum = 'onayli' AND s.sinif = %s AND s.ders = %s AND s.id <> ALL(%s)"
            " ORDER BY s.konu, s.kullanim_sayisi, s.id DESC LIMIT %s",
            (seviye, ders, list(yasak or []) or [0], limit),
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
    d = {
        "id": r[0],
        "konu": r[1],
        "soru": r[2],
        "secenekler": list(r[3]),
        "dogru_index": r[4],
    }
    if len(r) > 5:
        d["kazanim_kod"] = r[5]
        d["kazanim_metin"] = r[6]
    return d


def ozet(
    form: list[TestSonucu],
    odev: list[tuple[str, str, bool]],
    deneme: list[tuple[str, str, int, int]] = (),
) -> dict[str, list[KazanimDurum]]:
    toplam: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for t in form:
        toplam[(t.ders, t.kazanim)][0] += t.dogru
        toplam[(t.ders, t.kazanim)][1] += t.toplam
    for ders, kaz, dogru in odev:
        toplam[(ders, kaz)][0] += int(dogru)
        toplam[(ders, kaz)][1] += 1
    for ders, kaz, dogru, n in deneme:
        toplam[(ders, kaz)][0] += dogru
        toplam[(ders, kaz)][1] += n
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


# --- yıllık plan kazanımları (tahtayoklama/data/kazanimlar.json) ---

_plan_onbellek: dict = {"yol": None, "mtime": None, "veri": {}}


def plan_kazanimlari() -> dict:
    """tahtayoklama/data/kazanimlar.json — salt-okunur, dosya değişince mtime ile yeniden okunur."""
    yol = AYAR.kazanim_yolu
    try:
        mtime = yol.stat().st_mtime
        if _plan_onbellek.get("yol") != yol or _plan_onbellek.get("mtime") != mtime:
            veri = json.loads(yol.read_text(encoding="utf-8"))
            _plan_onbellek.update(
                yol=yol, mtime=mtime, veri=veri if isinstance(veri, dict) else {}
            )
    except (OSError, ValueError):
        return {}
    return _plan_onbellek.get("veri", {})


def haftalik_kazanim(sinif: str, ders: str, tarih: date | None = None) -> str | None:
    """Bu haftanın kazanımı: yoklama tahtasındaki _kazanim() mantığıyla aynı kurallar.
    haftalar (hafta no → o haftanın pazartesisi) içinde bugünü kapsayan hafta,
    kazanimlar[düzey][ders][hafta]. Düzey sınıf adından ("10-A" → "10").
    Tatil haftası/eksik plan/bulunamazsa None."""
    if not sinif or not ders:
        return None
    kz = plan_kazanimlari()
    if not kz:
        return None
    bugun = tarih or zaman.simdi().date()
    duzey = sinif.split("-")[0]
    hafta = None
    for no, pazartesi in kz.get("haftalar", {}).items():
        try:
            baslangic = date.fromisoformat(pazartesi)
            if baslangic <= bugun < baslangic + timedelta(days=7):
                hafta = no
                break
        except (ValueError, TypeError):
            continue
    if hafta is None:
        return None

    ders_ham = ders.strip().lower()
    metin = kz.get("kazanimlar", {}).get(duzey, {}).get(ders_ham, {}).get(hafta)
    if not metin:
        # Alternatif ad eşleme (matematik uygulamaları -> matematik, vb.)
        eslestir = {
            "matematik uygulamaları": "matematik",
            "spor etkinlikleri": "beden eğitimi",
        }
        if ders_ham in eslestir:
            metin = kz.get("kazanimlar", {}).get(duzey, {}).get(eslestir[ders_ham], {}).get(hafta)
    if not isinstance(metin, str):
        return None
    satirlar = [" ".join(s.split()) for s in metin.split("\n")]
    return "\n".join(s for s in satirlar if s) or None

