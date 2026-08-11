"""
core/olaylar.py — Tahta içi olay veri yolu (event bus)

Küçük ve tek süreçlik. Redis/RabbitMQ değil, olmasına da gerek yok: tek bir
tahta, tek bir süreç, saniyede birkaç olay.

Neden var: araç çağrısı, HUD güncellemesi, transkript yazımı ve log satırı
aynı kod yollarına serpiştirilmiş durumdaydı. Yeni bir tüketici eklemek
mevcut kodun içine girmek demekti. Olay yayınlayan bir çekirdek, tüketicileri
birbirinden ayırır.

Kullanım:

    from core import olaylar
    olaylar.abone(olaylar.ARAC_BITTI, yazici)          # senkron ya da async
    await olaylar.yayinla(olaylar.ARAC_BITTI, ad="web_search", sure=2.1)

Tasarım kuralları:
- Abone hatası yayıncıyı ETKİLEMEZ. Ders, log yazamadı diye durmaz.
- Yayınlamak ucuz olmalı; abone ağır iş yapacaksa kendi görevini açar.
- Olay adları SABİT ve az. Serbest metin olay adı, aboneyi sessizce boşa düşürür.
"""

import asyncio
import inspect
from collections import defaultdict
from datetime import datetime

from core.logger import get_logger

log = get_logger("olaylar")

# ── Olay adları ────────────────────────────────────────────────────────────
DERS_BASLADI      = "DersBasladi"
DERS_BITTI        = "DersBitti"
DURUM_DEGISTI     = "DurumDegisti"        # ders motoru adımı değişti
ZIL_CALDI         = "ZilCaldi"
OGRENCI_SORDU     = "OgrenciSordu"
FARABI_KONUSTU    = "FarabiKonustu"
OGRETMEN_MUDAHALE = "OgretmenMudahale"
ARAC_BASLADI      = "AracBasladi"
ARAC_BITTI        = "AracBitti"
ARAC_ZAMAN_ASIMI  = "AracZamanAsimi"
GORU_GUNCELLENDI  = "GoruGuncellendi"
DEGERLENDIRME_BITTI = "DegerlendirmeBitti"
HAFIZA_GUNCELLENDI  = "HafizaGuncellendi"

TUM_OLAYLAR = (
    DERS_BASLADI, DERS_BITTI, DURUM_DEGISTI, ZIL_CALDI, OGRENCI_SORDU,
    FARABI_KONUSTU, OGRETMEN_MUDAHALE, ARAC_BASLADI, ARAC_BITTI,
    ARAC_ZAMAN_ASIMI, GORU_GUNCELLENDI, DEGERLENDIRME_BITTI,
    HAFIZA_GUNCELLENDI,
)

_aboneler: dict[str, list] = defaultdict(list)


def abone(olay: str, geri_cagri) -> None:
    """Bir olaya abone ol. Geri çağrı senkron ya da async olabilir."""
    if olay not in TUM_OLAYLAR:
        # Sessizce eklemek, yazım hatası yüzünden hiç tetiklenmeyen bir abone
        # bırakır; en zor bulunan hata türü budur.
        raise ValueError(f"Bilinmeyen olay: {olay}")
    _aboneler[olay].append(geri_cagri)


def temizle() -> None:
    """Testler için: bütün abonelikleri kaldır."""
    _aboneler.clear()


async def yayinla(olay: str, **veri) -> None:
    """
    Olayı bütün abonelere ilet. Abone hatası yutulur ve loglanır —
    bir tüketicinin hatası dersi durdurmamalı.
    """
    veri.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    veri["olay"] = olay
    for geri_cagri in list(_aboneler.get(olay, ())):
        try:
            sonuc = geri_cagri(veri)
            if inspect.isawaitable(sonuc):
                await sonuc
        except Exception as e:                        # pragma: no cover
            log.error("Olay abonesi hata verdi (%s): %s", olay, e)


def yayinla_esnek(olay: str, **veri) -> None:
    """
    Olay döngüsü dışından (iş parçacığından) yayınlamak için. Döngü yoksa
    sessizce vazgeçer: bir olayın kaybolması, dersin durmasından iyidir.
    """
    try:
        dongu = asyncio.get_running_loop()
    except RuntimeError:
        return
    dongu.create_task(yayinla(olay, **veri))
