"""Kelebek sınav salon dağıtımı (kelebek.db) — salt-okunur. Öğrenci yalnızca KENDİ yerleşimini görür (okul_no ile).

Koltuk numarası: sütunlar soldan sağa, sıralar öne→arkaya, tek sayı = cam kenarı (kelebek/dagitim.py::Salon.yer ile aynı kural).
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from ayarlar import AYAR

from kaynaklar import KaynakHatasi


@dataclass(frozen=True)
class Yerlesim:
    tarih: str
    ders_no: int
    ders: str
    salon: str
    koltuk: int
    sutun: int  # 1'den
    sira: int  # 1'den, önden sayılır


@contextmanager
def _baglan():
    yol = AYAR.kelebek_db_yolu
    if not yol.exists():
        raise KaynakHatasi("kelebek veritabanı bulunamadı")
    try:
        c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)
    except sqlite3.Error as e:
        raise KaynakHatasi(f"kelebek veritabanı açılamadı: {e}") from e
    try:
        yield c
    finally:
        c.close()


def yaklasan(okul_no: int, baslangic: str, bitis: str) -> list[Yerlesim]:
    """okul_no'nun [baslangic, bitis] (YYYY-AA-GG) arasındaki sınav yerleşimleri, tarihe göre."""
    try:
        with _baglan() as c:
            satirlar = c.execute(
                "SELECT d.tarih, d.ders_no, d.ders, s.ad, d.koltuk, s.sira, s.sira_basi"
                " FROM dagitim d JOIN dagitim_salon s"
                " ON s.tarih = d.tarih AND s.ders_no = d.ders_no AND s.derslik_id = d.derslik_id"
                " WHERE d.okul_no = ? AND d.tarih BETWEEN ? AND ? ORDER BY d.tarih, d.ders_no",
                (okul_no, baslangic, bitis),
            ).fetchall()
    except sqlite3.Error as e:
        raise KaynakHatasi(f"kelebek okunamadı: {e}") from e
    sonuc = []
    for tarih, ders_no, ders, salon, koltuk, sira_sayisi, sira_basi in satirlar:
        masa = (koltuk - 1) // sira_basi
        sonuc.append(Yerlesim(tarih, ders_no, ders, salon, koltuk, masa // sira_sayisi + 1, masa % sira_sayisi + 1))
    return sonuc
