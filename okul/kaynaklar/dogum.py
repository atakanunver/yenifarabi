"""Doğum günleri (smssistemi.db) — salt-okunur; kiosk panosundaki kutlama için.

Yalnızca öğrenci ve personel (veli tarihi tutulmaz). Kişisel veri olarak kısa ad (+ öğrenci için
sınıf) döner; telefon/okul no okunmaz. "Bilinmeyen Sınıf" (okuldan ayrılan) öğrenciler hariç.
Pazartesi hafta sonu doğanları da kapsar (okul kapalıyken kutlanamazlar).
"""

import calendar
import sqlite3
from contextlib import closing
from datetime import date, timedelta

from ayarlar import AYAR
from metin import kisa_ad

from kaynaklar import KaynakHatasi

_AYRILAN = "Bilinmeyen Sınıf"


def _gunler(bugun: date) -> list[date]:
    """Kutlanacak günler: pazartesi için cumartesi+pazar da; diğer günler yalnızca bugün."""
    if bugun.weekday() == 0:
        return [bugun - timedelta(days=2), bugun - timedelta(days=1), bugun]
    return [bugun]


def _mm_gg(gun: date) -> list[str]:
    anahtarlar = [f"{gun.month:02d}-{gun.day:02d}"]
    if gun.month == 2 and gun.day == 28 and not calendar.isleap(gun.year):  # 29 Şubat doğanlar artık olmayan yılda 28'inde
        anahtarlar.append("02-29")
    return anahtarlar


def bugunun_dogumlari(bugun: date) -> list[dict]:
    """[{"ad": "Ayşe K.", "sinif": "9-A" | None}] — önce öğrenciler, sonra personel; ada göre sıralı."""
    yol = AYAR.sms_db_yolu
    if not yol.exists():
        raise KaynakHatasi("SMS rehberi bulunamadı")
    anahtarlar = [a for g in _gunler(bugun) for a in _mm_gg(g)]
    yer = ",".join("?" * len(anahtarlar))
    try:
        with closing(sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)) as c:
            satirlar = c.execute(
                "SELECT k.ad_soyad, k.tur, s.ad FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id"
                " WHERE k.tur IN ('ogrenci', 'personel') AND s.ad != ?"
                f" AND substr(k.dogum_tarihi, 6, 5) IN ({yer}) ORDER BY k.tur, k.ad_soyad",
                (_AYRILAN, *anahtarlar),
            ).fetchall()
    except sqlite3.Error as e:
        raise KaynakHatasi(f"SMS rehberi okunamadı: {e}") from e
    return [
        {"ad": kisa_ad(ad), "sinif": None if tur == "personel" else sinif}
        for ad, tur, sinif in satirlar
    ]
