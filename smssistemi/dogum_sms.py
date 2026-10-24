"""Doğum günü SMS'i (2026-10-24): doğum günü olan telefonlu öğrenci ve personele günde bir SMS.

Hafta içi 09:30-09:40 penceresinde `otomasyon.otomasyon_arkaplan_dongusu` tetikler. İki anahtar gerekir:
`sms_otomatik` = "1" (ana şalter) ve `dogum_sms_gercek` = "1" (varsayılan "0": KURU — alıcıları hesaplar, sayıyı
kaydeder, SMS GÖNDERMEZ). Gönderimde `otomasyon._CALISMA_KILIDI` alınır (modem tek istek işler; devamsızlık
otomasyonuyla aynı anda koşmaz). Veli hariç. Pazartesi cumartesi/pazar doğanları da kapsar. Günlükte yalnızca sayı.
"""

import calendar
import json
import logging
import threading
import uuid
from datetime import date, timedelta

import db
import gonderim
import otomasyon
import sms_gonderici

logger = logging.getLogger("smssistemi.dogum_sms")

AYAR_ANA = "sms_otomatik"
AYAR_GERCEK = "dogum_sms_gercek"
AYAR_SABLON = "dogum_sms_sablonu"
AYAR_SON_TARIH = "dogum_sms_son_tarih"
AYAR_SON_SONUC = "dogum_sms_son_sonuc"

VARSAYILAN_SABLON = "Sevgili {isim}, dogum gununuzu kutlar, saglikli ve mutlu bir yil dileriz. Okul Idaresi"
_AYRILAN = "Bilinmeyen Sınıf"


def _gunler(bugun: date) -> list[date]:
    """Pazartesi için cumartesi+pazar da (okul kapalıyken kutlanamazlar)."""
    if bugun.weekday() == 0:
        return [bugun - timedelta(days=2), bugun - timedelta(days=1), bugun]
    return [bugun]


def _mm_gg(gun: date) -> list[str]:
    anahtarlar = [f"{gun.month:02d}-{gun.day:02d}"]
    if gun.month == 2 and gun.day == 28 and not calendar.isleap(gun.year):  # 29 Şubat doğanlar artık olmayan yılda 28'inde
        anahtarlar.append("02-29")
    return anahtarlar


def alicilar(conn, bugun: date) -> dict:
    """{'alicilar': [{'isim','telefon'}...], 'telefonsuz': n} — öğrenci+personel, geçerli ve tekil telefon."""
    anahtarlar = [a for g in _gunler(bugun) for a in _mm_gg(g)]
    yer = ",".join("?" * len(anahtarlar))
    satirlar = conn.execute(
        "SELECT k.ad_soyad, k.telefon FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id"
        " WHERE k.tur IN ('ogrenci', 'personel') AND s.ad != ?"
        f" AND substr(k.dogum_tarihi, 6, 5) IN ({yer}) ORDER BY k.tur, k.ad_soyad",
        (_AYRILAN, *anahtarlar),
    ).fetchall()
    alicilar_, gorulen, telefonsuz = [], set(), 0
    for ad, ham in satirlar:
        tel = gonderim.normalize_phone(ham or "")
        if not tel or not gonderim.is_valid_phone(tel):
            telefonsuz += 1
            continue
        if tel in gorulen:  # aynı numaraya aynı gün iki SMS gitmesin
            continue
        gorulen.add(tel)
        alicilar_.append({"isim": ad, "telefon": tel})
    return {"alicilar": alicilar_, "telefonsuz": telefonsuz}


def son_sonuc_oku(conn) -> dict | None:
    try:
        return json.loads(db.ayar_oku(conn, AYAR_SON_SONUC) or "")
    except ValueError:
        return None


def _gonder(conn, gonderim_id: str, kisiler: list[tuple[str, str, str]], bekleme_sn: float) -> tuple[int, int, bool]:
    """toplu_gonder + gonderimler kaydı; (başarılı, hatalı, sms_denendi). otomasyon_calistir ile aynı kural."""
    sayac = {"ok": 0, "hata": 0, "denendi": False}

    def _kaydet(isim: str, telefon: str, mesaj: str, durum: str, hata_metni: str | None) -> None:
        sayac["ok" if durum == "gonderildi" else "hata"] += 1
        if durum == "gonderildi" or not (hata_metni or "").startswith("BAĞLANTI HATASI"):
            sayac["denendi"] = True
        db.gonderim_kaydet(conn, gonderim_id, isim, telefon, mesaj, durum, hata_metni)

    try:
        sms_gonderici.toplu_gonder(
            sms_gonderici.modem_ayarlarini_yukle(), kisiler, _kaydet,
            durdur_bayragi=threading.Event(), bekleme_sn=bekleme_sn,
        )
    except Exception as exc:  # noqa: BLE001 — kaydedilmemişleri hata işaretle, kaydedilmişi çiftleme
        logger.error("Doğum günü SMS gönderiminde hata: %s", type(exc).__name__)
        for k in kisiler[sayac["ok"] + sayac["hata"]:]:
            _kaydet(k[0], k[1], k[2], "hata", str(exc))
    return sayac["ok"], sayac["hata"], sayac["denendi"]


def calistir(conn, bugun: date | None = None, tetikleyen: str = "otomasyon",
             bekleme_sn: float = 2.0, test_telefon: str | None = None) -> dict:
    """Pencerede çağrılır. test_telefon verilirse YALNIZ o numaraya örnek bir SMS gider (kayıt/son tarih yazılmaz)."""
    bugun = bugun or otomasyon.bugun_istanbul()
    hedef = bugun.isoformat()
    sablon = db.ayar_oku(conn, AYAR_SABLON) or VARSAYILAN_SABLON

    if test_telefon is not None:
        tel = gonderim.normalize_phone(test_telefon)
        if not gonderim.is_valid_phone(tel):
            raise ValueError("Geçersiz test telefonu")
        ok, hata, _ = _gonder(conn, f"dgm_test_{uuid.uuid4().hex[:8]}", [("Test", tel, gonderim.kisisellestir(sablon, "Test"))], bekleme_sn)
        return {"durum": "test", "basarili_sayisi": ok, "hatali_sayisi": hata}

    gercek = db.ayar_oku(conn, AYAR_GERCEK) == "1"
    otomatik = tetikleyen == "otomatik_zamanlayici"
    onceki = son_sonuc_oku(conn)
    if otomatik and gercek and db.ayar_oku(conn, AYAR_SON_TARIH) == hedef:
        return {"durum": "zaten_calisti", "tarih": hedef}
    if otomatik and not gercek and onceki and onceki.get("tarih") == hedef and onceki.get("kuru"):
        return {"durum": "kuru_zaten", "tarih": hedef}

    a = alicilar(conn, bugun)
    ozet = {"tarih": hedef, "tetikleyen": tetikleyen, "alici_sayisi": len(a["alicilar"]), "telefonsuz_sayisi": a["telefonsuz"],
            "calisma_zamani": otomasyon.simdi_istanbul().strftime("%Y-%m-%d %H:%M:%S")}

    if not gercek:
        ozet.update(durum="kuru", kuru=True)
        db.ayar_yaz(conn, AYAR_SON_SONUC, json.dumps(ozet, ensure_ascii=False))
        logger.info("Doğum günü SMS kuru çalışma: %d alıcı, %d telefonsuz (gönderilmedi)", ozet["alici_sayisi"], a["telefonsuz"])
        return {"durum": "kuru", "ozet": ozet}

    gonderim_id = f"dgm_{uuid.uuid4().hex[:8]}"
    kisiler = [(x["isim"], x["telefon"], gonderim.kisisellestir(sablon, x["isim"])) for x in a["alicilar"]]
    ok = hata = 0
    denendi = False
    if kisiler:
        logger.info("Doğum günü SMS başlatılıyor: %d alıcı. Gonderim ID: %s", len(kisiler), gonderim_id)
        ok, hata, denendi = _gonder(conn, gonderim_id, kisiler, bekleme_sn)
    durum = "basarisiz" if kisiler and not denendi else "tamamlandi"
    if durum == "tamamlandi":  # hiç SMS denenmediyse (modem/proxy yok) son tarih yazılmaz: pencerede tekrar denenir
        db.ayar_yaz(conn, AYAR_SON_TARIH, hedef)
    ozet.update(durum=durum, kuru=False, gonderim_id=gonderim_id, basarili_sayisi=ok, hatali_sayisi=hata)
    db.ayar_yaz(conn, AYAR_SON_SONUC, json.dumps(ozet, ensure_ascii=False))
    return {"durum": durum, "ozet": ozet}


def calistir_thread(**kwargs) -> dict:
    """`asyncio.to_thread` için. Kilit meşgulse (ör. devamsızlık SMS'i gidiyor) hemen döner; döngü 30 sn sonra yeniden dener."""
    if not otomasyon._CALISMA_KILIDI.acquire(blocking=False):
        return {"durum": "calisiyor"}
    try:
        conn = db.baglanti()
        try:
            return calistir(conn, **kwargs)
        finally:
            conn.close()
    finally:
        otomasyon._CALISMA_KILIDI.release()
