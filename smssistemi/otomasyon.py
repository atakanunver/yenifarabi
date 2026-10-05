"""Devamsızlık SMS Otomasyonu ve Zamanlayıcı Servisi.

Pazartesi-Cuma günleri:
1. Sabah 09:00'da yoklama veritabanını kontrol ederek 1. derse gelmeyen öğrencilerin
   velilerine (anne ve baba) otomatik SMS gönderir.
2. Öğleden sonra 14:00'te yoklama veritabanını kontrol ederek öğleden sonraki derse (6. ders)
   gelmeyen öğrencilerin velilerine otomatik SMS gönderir.

Tasarım ve Güvenlik İlkeleri:
1. Yalnızca ilgili derste `durum == 'alindi'` olan sınıflar işlenir. Yoklaması
   alınmamış veya tahtasına ulaşılamamış sınıflar hariç tutulur (yanlış SMS önleme).
2. İzinli öğrenciler (`izinli_isimleri`) devamsız sayılmaz, SMS gönderilmez.
3. Bir öğrencinin kayıtlı her iki velisine de (anne ve baba) kişiselleştirilmiş
   ayrı SMS gider.
4. Aynı gün içinde mükerrer gönderim yapılmaz (idempotent; `otomasyon_ilk_ders_son_tarih` ve `otomasyon_ogle_son_tarih`).
5. Arayüzden her iki servis de bağımsız tek tıkla açılıp kapatılabilir.
6. Kuru çalıştırma (dry-run / simülasyon) desteği ile test edilebilir.
"""

import asyncio
import json
import logging
import re
import threading
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import db
import gonderim
import sms_gonderici
import yoklama_kaynak

logger = logging.getLogger("smssistemi.otomasyon")

_ISTANBUL = ZoneInfo("Europe/Istanbul")

# Sabah İlk Ders (1. Ders - 09:00) Ayarları
AYAR_AKTIF = "otomasyon_ilk_ders_aktif"
AYAR_SABLON = "otomasyon_ilk_ders_sablonu"
AYAR_SON_TARIH = "otomasyon_ilk_ders_son_tarih"
AYAR_SON_SONUC = "otomasyon_ilk_ders_son_sonuc"

# Öğleden Sonra (6. Ders - 14:00) Ayarları
AYAR_OGLE_AKTIF = "otomasyon_ogle_aktif"
AYAR_OGLE_SABLON = "otomasyon_ogle_sablonu"
AYAR_OGLE_SON_TARIH = "otomasyon_ogle_son_tarih"
AYAR_OGLE_SON_SONUC = "otomasyon_ogle_son_sonuc"

VARSAYILAN_SABLON = "Sayın {isim}, öğrenciniz {ogrenci_adi} sabah ilk saate gelmemiştir. Bilginize."
VARSAYILAN_SABLON_OGLE = "Sayın {isim}, öğrenciniz {ogrenci_adi} öğleden sonra derslere gelmemiştir. Bilginize."

_COZULMEMIS_ISIM_RE = re.compile(r"^No\s+\d+$")

_DURUM_ACIKLAMA = {
    "alinmadi": "Yoklama alınmamış",
    "tahta_ulasilamaz": "Tahta ulaşılamadı",
    "henuz_baslamadi": "Dersler henüz başlamadı",
    "tahta_atanmamis": "Sınıfa tahta atanmamış",
    "ders_yok_o_gun": "O gün ders yok",
    "veri_yok": "Panoda yoklama kaydı yok",
}

ESLESME_TAMAM = "tamam"
ESLESME_TELEFONSUZ = "telefonsuz"
ESLESME_YOK = "eslesmedi"


def bugun_istanbul() -> date:
    return datetime.now(_ISTANBUL).date()


def simdi_istanbul() -> datetime:
    return datetime.now(_ISTANBUL)


def okul_gunu_mu(hedef_tarih: date) -> bool:
    """Pazartesi=0 ... Cuma=4 okul günüdür (Cumartesi-Pazar False döner)."""
    return hedef_tarih.weekday() in (0, 1, 2, 3, 4)


def sablonu_oku(conn, servis: str = "ilk_ders") -> str:
    if servis in ("ogle", "ogleden_sonra"):
        return db.ayar_oku(conn, AYAR_OGLE_SABLON) or VARSAYILAN_SABLON_OGLE
    return db.ayar_oku(conn, AYAR_SABLON) or VARSAYILAN_SABLON


def otomasyon_aktif_mi(conn, servis: str = "ilk_ders") -> bool:
    if servis in ("ogle", "ogleden_sonra"):
        return db.ayar_oku(conn, AYAR_OGLE_AKTIF) == "1"
    return db.ayar_oku(conn, AYAR_AKTIF) == "1"


def son_sonuc_oku(conn, servis: str = "ilk_ders") -> dict | None:
    ayar_anahtari = AYAR_OGLE_SON_SONUC if servis in ("ogle", "ogleden_sonra") else AYAR_SON_SONUC
    ham = db.ayar_oku(conn, ayar_anahtari)
    if not ham:
        return None
    try:
        return json.loads(ham)
    except Exception:
        return None


def _ogrenciyi_eslestir(
    conn, ad_soyad: str, sinif_id: int | None, sinif_adi_ile: dict[int, str]
) -> tuple[str, dict | None, list[dict], str | None]:
    """İsim -> rehberdeki öğrenci -> telefonlu veliler.
    Döner: (eslesme_durumu, ogrenci|None, veliler, not).
    """
    if _COZULMEMIS_ISIM_RE.match(ad_soyad.strip()):
        return ESLESME_YOK, None, [], "Panoda öğrenci numarası çözülememiş"
    if sinif_id is None:
        return ESLESME_YOK, None, [], "Bu sınıf rehberde kayıtlı değil"

    ogrenci = db.kisi_bul_isimle(conn, ad_soyad, sinif_id, "ogrenci")
    if ogrenci is None:
        baska = db.kisi_bul_isimle_sinifsiz(conn, ad_soyad, "ogrenci")
        if baska is not None:
            baska_sinif = sinif_adi_ile.get(baska["sinif_id"], "?")
            return ESLESME_YOK, None, [], f"Rehberde {baska_sinif} sınıfında kayıtlı"
        return ESLESME_YOK, None, [], "Rehberde bu isimde öğrenci yok"

    veliler = db.veliler_ogrenci_ile(conn, ogrenci["id"])
    if not veliler:
        return ESLESME_TELEFONSUZ, ogrenci, [], None
    return ESLESME_TAMAM, ogrenci, veliler, None


def devamsizlar_derle(
    conn, ders_no: int = 1, tarih: str | None = None, sablon: str | None = None
) -> dict:
    """Belirtilen ders numarası (1: sabah ilk ders, 6: öğleden sonra ilk ders) için
    devamsızlık özetini derler.
    
    Yalnızca belirtilen `ders_no` ve `durum == 'alindi'` olan sınıflar işleme alınır.
    İzinli öğrenciler yok sayılmaz.
    6. ders için sabah 1. derste de devamsız olan öğrenciler işaretlenir.
    """
    hedef_tarih = tarih or bugun_istanbul().isoformat()
    if sablon:
        mesaj_sablonu = sablon
    else:
        mesaj_sablonu = sablonu_oku(conn, "ogle" if ders_no == 6 else "ilk_ders")

    siniflar = db.siniflar_listele(conn)
    sinif_id_ile = {s["ad"]: s["id"] for s in siniflar}
    sinif_adi_ile = {s["id"]: s["ad"] for s in siniflar}

    satirlar = yoklama_kaynak.gunun_satirlari(hedef_tarih)
    hedef_ders_satirlari = [s for s in satirlar if s.get("ders_no") == ders_no]

    # 6. ders için sabah 1. ders yoklama listesini de kontrol edelim
    sabah_yok_kumesi: set[tuple[str, str]] = set()
    if ders_no == 6:
        for s in satirlar:
            if s.get("ders_no") == 1 and s.get("durum") == yoklama_kaynak.DURUM_ALINDI:
                sinif_adi = s["sinif"]
                for isim in s.get("yok_isimleri", []):
                    sabah_yok_kumesi.add((sinif_adi, isim))

    gorulen_siniflar: dict[str, dict] = {}
    for s in hedef_ders_satirlari:
        gorulen_siniflar[s["sinif"]] = s

    dahil_siniflar: list[str] = []
    haric_siniflar: list[dict] = []

    for sinif_ad in sorted(sinif_id_ile.keys(), key=db._sinif_sira_anahtari):
        if not db._SINIF_AD_RE.match(sinif_ad):
            continue  # Personel / Bilinmeyen Sınıf
        satir = gorulen_siniflar.get(sinif_ad)
        if not satir:
            haric_siniflar.append(
                {
                    "sinif": sinif_ad,
                    "sebep": "veri_yok",
                    "aciklama": f"Panoda {ders_no}. derse ait kayıt yok",
                }
            )
        elif satir["durum"] != yoklama_kaynak.DURUM_ALINDI:
            sebep = satir["durum"]
            haric_siniflar.append(
                {
                    "sinif": sinif_ad,
                    "sebep": sebep,
                    "aciklama": _DURUM_ACIKLAMA.get(sebep, sebep),
                }
            )
        else:
            dahil_siniflar.append(sinif_ad)

    ogrenciler: list[dict] = []
    gonderilecek_smsler: list[dict] = []
    izinli_sayisi = 0
    yalnizca_ogle_sayisi = 0

    for sinif_ad in dahil_siniflar:
        satir = gorulen_siniflar[sinif_ad]
        izinliler = set(satir.get("izinli_isimleri", []))
        yoklar = satir.get("yok_isimleri", [])

        for ad_soyad in yoklar:
            if ad_soyad in izinliler:
                izinli_sayisi += 1
                continue

            durum, ogrenci, veliler, not_metni = _ogrenciyi_eslestir(
                conn, ad_soyad, sinif_id_ile.get(sinif_ad), sinif_adi_ile
            )

            sabah_da_yok = (sinif_ad, ad_soyad) in sabah_yok_kumesi if ders_no == 6 else False
            if ders_no == 6 and not sabah_da_yok:
                yalnizca_ogle_sayisi += 1

            ogrenci_kayit = {
                "sinif": sinif_ad,
                "ad_soyad": ad_soyad,
                "eslesme_durumu": durum,
                "eslesme_notu": not_metni,
                "ogrenci_kisi_id": ogrenci["id"] if ogrenci else None,
                "veliler": veliler,
                "sabah_da_yok": sabah_da_yok,
            }
            ogrenciler.append(ogrenci_kayit)

            if durum == ESLESME_TAMAM:
                for v in veliler:
                    kisisel_mesaj = gonderim.kisisellestir(
                        mesaj_sablonu, v["ad_soyad"], ogrenci["ad_soyad"]
                    )
                    gonderilecek_smsler.append(
                        {
                            "veli_kisi_id": v["id"],
                            "veli_ad": v["ad_soyad"],
                            "veli_telefon": v["telefon"],
                            "veli_rol": v.get("veli_rol"),
                            "ogrenci_ad": ogrenci["ad_soyad"],
                            "sinif": sinif_ad,
                            "mesaj": kisisel_mesaj,
                            "sabah_da_yok": sabah_da_yok,
                        }
                    )

    ogrenciler.sort(key=lambda o: (db._sinif_sira_anahtari(o["sinif"]), o["ad_soyad"]))
    gonderilecek_smsler.sort(
        key=lambda s: (db._sinif_sira_anahtari(s["sinif"]), s["ogrenci_ad"], s["veli_ad"])
    )

    return {
        "ders_no": ders_no,
        "tarih": hedef_tarih,
        "bugun_mu": hedef_tarih == bugun_istanbul().isoformat(),
        "sablon": mesaj_sablonu,
        "dahil_siniflar": dahil_siniflar,
        "haric_siniflar": haric_siniflar,
        "ogrenciler": ogrenciler,
        "gonderilecek_smsler": gonderilecek_smsler,
        "toplam_ogrenci": len(ogrenciler),
        "ulasilabilir_ogrenci": sum(
            1 for o in ogrenciler if o["eslesme_durumu"] == ESLESME_TAMAM
        ),
        "toplam_veli_sms": len(gonderilecek_smsler),
        "telefonsuz_sayisi": sum(
            1 for o in ogrenciler if o["eslesme_durumu"] == ESLESME_TELEFONSUZ
        ),
        "eslesmeyen_sayisi": sum(
            1 for o in ogrenciler if o["eslesme_durumu"] == ESLESME_YOK
        ),
        "izinli_sayisi": izinli_sayisi,
        "yalnizca_ogle_sayisi": yalnizca_ogle_sayisi,
    }


def ilk_ders_devamsizlar(
    conn, tarih: str | None = None, sablon: str | None = None
) -> dict:
    return devamsizlar_derle(conn, ders_no=1, tarih=tarih, sablon=sablon)


def ogle_devamsizlar(
    conn, tarih: str | None = None, sablon: str | None = None
) -> dict:
    return devamsizlar_derle(conn, ders_no=6, tarih=tarih, sablon=sablon)


def otomasyon_calistir(
    conn,
    kuru: bool = False,
    tetikleyen: str = "otomasyon",
    tarih: str | None = None,
    bekleme_sn: float = 2.0,
    servis: str = "ilk_ders",
) -> dict:
    """Devamsızlık SMS servisini yürütür.
    
    servis="ilk_ders": Sabah 09:00 1. ders devamsızlık servisi.
    servis="ogle": Öğleden sonra 14:00 6. ders devamsızlık servisi.

    kuru=True ise gerçek SMS göndermez ve son çalışma tarihini güncellemez.
    kuru=False ise gönderim yapar, veritabanına loglar ve son çalışma tarihini kaydeder.
    """
    hedef_tarih = tarih or bugun_istanbul().isoformat()
    is_ogle = servis in ("ogle", "ogleden_sonra")
    ayar_son_tarih = AYAR_OGLE_SON_TARIH if is_ogle else AYAR_SON_TARIH
    ayar_son_sonuc = AYAR_OGLE_SON_SONUC if is_ogle else AYAR_SON_SONUC
    oto_onek = "oto6_" if is_ogle else "oto1_"
    servis_adi = "ogle" if is_ogle else "ilk_ders"

    son_tarih = db.ayar_oku(conn, ayar_son_tarih)

    if not kuru and son_tarih == hedef_tarih and tetikleyen == "otomatik_zamanlayici":
        logger.info(f"Otomasyon ({servis_adi}) {hedef_tarih} için zaten çalışmış, mükerrer gönderim atlandı.")
        return {
            "durum": "zaten_calisti",
            "servis": servis_adi,
            "mesaj": f"{hedef_tarih} tarihinde otomasyon ({servis_adi}) zaten çalıştırılmış.",
            "tarih": hedef_tarih,
        }

    if is_ogle:
        derleme = ogle_devamsizlar(conn, tarih=hedef_tarih)
    else:
        derleme = ilk_ders_devamsizlar(conn, tarih=hedef_tarih)

    gonderilecekler = derleme["gonderilecek_smsler"]

    if kuru:
        return {
            "durum": "simulasyon",
            "servis": servis_adi,
            "kuru_calistirma": True,
            "tarih": hedef_tarih,
            "derleme": derleme,
            "gonderilecek_adet": len(gonderilecekler),
        }

    gonderim_id = f"{oto_onek}{uuid.uuid4().hex[:8]}"
    basarili_sayisi = 0
    hatali_sayisi = 0
    sms_denendi = False

    if gonderilecekler:
        logger.info(
            f"Otomasyon ({servis_adi} - {tetikleyen}) başlatılıyor: {len(gonderilecekler)} veliye SMS gönderilecek. "
            f"Gonderim ID: {gonderim_id}"
        )
        kisiler_listesi = [
            (item["veli_ad"], item["veli_telefon"], item["mesaj"])
            for item in gonderilecekler
        ]

        def _kaydet(isim: str, telefon: str, mesaj: str, durum: str, hata_metni: str | None) -> None:
            nonlocal basarili_sayisi, hatali_sayisi, sms_denendi
            if durum == "gonderildi":
                basarili_sayisi += 1
            else:
                hatali_sayisi += 1
            # "BAĞLANTI HATASI" önekli satırları toplu_gonder yalnızca send_sms
            # HİÇ çağrılmadan kaydeder; diğer her satır modemin SMS'i almış
            # olabileceği bir denemedir.
            if durum == "gonderildi" or not (hata_metni or "").startswith("BAĞLANTI HATASI"):
                sms_denendi = True
            db.gonderim_kaydet(conn, gonderim_id, isim, telefon, mesaj, durum, hata_metni)

        try:
            ayarlar = sms_gonderici.modem_ayarlarini_yukle()
            sms_gonderici.toplu_gonder(
                ayarlar,
                kisiler_listesi,
                _kaydet,
                # None verilince toplu_gonder ilk `.is_set()`te AttributeError
                # fırlatıp HİÇ SMS göndermiyordu (2026-09-25'te bulundu). Otomasyonun
                # durdurma düğmesi yok — hiç set edilmeyen bir Event yeterli.
                durdur_bayragi=threading.Event(),
                bekleme_sn=bekleme_sn,
            )
        except Exception as exc:
            # 2026-09-28'den sonra toplu_gonder bağlantı hatalarında artık
            # kendisi her aliciyi tek tek "hata" kaydediyor ve normalde
            # buraya düşmüyor — yine de beklenmeyen bir hata (ör. bug)
            # fırlatırsa yalnızca HENÜZ kaydedilmemiş kalanları işaretle,
            # zaten _kaydet'ten geçmiş olanları ÇİFT KAYDETME.
            logger.error(f"Otomasyon SMS gönderiminde hata oluştu: {exc}")
            kaydedilen = basarili_sayisi + hatali_sayisi
            for k in kisiler_listesi[kaydedilen:]:
                _kaydet(k[0], k[1], k[2], "hata", str(exc))

    # 2026-09-28: hiç SMS gitmediyse (basarili_sayisi == 0, ör. proxy
    # düşükken tüm gönderim "hata" ile sonuçlandı) AYAR_SON_TARIH YAZILMAZ —
    # aksi halde `otomasyon_arkaplan_dongusu`'nun penceresindeki
    # 30 saniyelik tekrar deneme döngüsü "bugün zaten çalışmış" sanıp asla
    # tekrar denemiyordu (DECISIONS.md 2026-09-28). En az bir SMS gittiyse
    # (kısmi başarı dahil) mükerrer gönderimi önlemek için son tarih yine de
    # yazılır. gonderilecekler boşsa (gönderilecek kimse yoktu) davranış
    # değişmez, son tarih her zaman yazılır.
    # Koşul "hiç SMS DENENMEDİ" (sms_denendi) — "hiç başarılı yok" değil:
    # send_sms zaman aşımı gibi hatalarda modem SMS'i göndermiş olabilir,
    # o durumda tekrar denemek veliye 30 sn'de bir mükerrer SMS demektir.
    sonuc_durum = "tamamlandi"
    if gonderilecekler and not sms_denendi:
        sonuc_durum = "basarisiz"
    else:
        db.ayar_yaz(conn, ayar_son_tarih, hedef_tarih)

    sonuc_ozet = {
        "gonderim_id": gonderim_id,
        "servis": servis_adi,
        "tarih": hedef_tarih,
        "calisma_zamani": simdi_istanbul().strftime("%Y-%m-%d %H:%M:%S"),
        "tetikleyen": tetikleyen,
        "ogrenci_sayisi": derleme["toplam_ogrenci"],
        "veli_sms_sayisi": len(gonderilecekler),
        "basarili_sayisi": basarili_sayisi,
        "hatali_sayisi": hatali_sayisi,
        "dahil_sinif_sayisi": len(derleme["dahil_siniflar"]),
        "haric_sinif_sayisi": len(derleme["haric_siniflar"]),
        "durum": sonuc_durum,
    }
    db.ayar_yaz(conn, ayar_son_sonuc, json.dumps(sonuc_ozet, ensure_ascii=False))

    return {
        "durum": sonuc_durum,
        "servis": servis_adi,
        "gonderim_id": gonderim_id,
        "ozet": sonuc_ozet,
        "derleme": derleme,
    }


# 2026-09-25: gönderim (`toplu_gonder`: SMS başına time.sleep + 8 bağlantı
# denemesi) async route/döngü İÇİNDEN doğrudan çağrılınca tüm 8020 event
# loop'unu gönderim bitene kadar donduruyordu. Artık asyncio.to_thread ile
# ayrı thread'de koşuyor. sqlite3 bağlantısı oluşturulduğu thread'e bağlı
# olduğu için bağlantı thread'in İÇİNDE açılır. Kilit: otomatik zamanlayıcı
# ile manuel tetik artık aynı anda koşabildiği için, aynı velilere iki kez
# SMS gitmesini engeller (manuel tetik günlük idempotency kontrolünü
# bilerek atlıyor — bkz. otomasyon_calistir).
_CALISMA_KILIDI = threading.Lock()


def otomasyon_calistir_thread(servis: str = "ilk_ders", **kwargs) -> dict:
    """`await asyncio.to_thread(otomasyon_calistir_thread, ...)` için."""
    if not _CALISMA_KILIDI.acquire(blocking=False):
        return {"durum": "calisiyor", "mesaj": "Otomasyon şu anda zaten çalışıyor."}
    try:
        conn = db.baglanti()
        try:
            return otomasyon_calistir(conn, servis=servis, **kwargs)
        finally:
            conn.close()
    finally:
        _CALISMA_KILIDI.release()


async def otomasyon_arkaplan_dongusu() -> None:
    """Arka planda koşan zamanlayıcı döngüsü.
    
    Her 30 saniyede bir İstanbul saatini kontrol eder.
    Hafta içi okul günlerinde (Pzt-Cum):
      - 09:00 - 09:10 penceresinde Sabah İlk Ders Otomasyonu (1. Ders)
      - 14:00 - 14:10 penceresinde Öğleden Sonra Otomasyonu (6. Ders)
    aktif ve o gün henüz çalışmamışsa devreye girer.
    """
    logger.info("Otomasyon arka plan zamanlayıcı döngüsü başlatıldı.")
    while True:
        try:
            await asyncio.sleep(30)
            simdi = simdi_istanbul()
            bugun = simdi.date()

            # Hafta sonu mu?
            if not okul_gunu_mu(bugun):
                continue

            # Sabah 09:00 - 09:10 zaman penceresi (1. Ders)
            if simdi.hour == 9 and 0 <= simdi.minute <= 10:
                conn = db.baglanti()
                try:
                    if otomasyon_aktif_mi(conn, "ilk_ders"):
                        son_tarih = db.ayar_oku(conn, AYAR_SON_TARIH)
                        if son_tarih != bugun.isoformat():
                            logger.info(f"Saat {simdi.strftime('%H:%M:%S')} - 09:00 Sabah Yoklama Otomasyonu tetikleniyor...")
                            await asyncio.to_thread(
                                otomasyon_calistir_thread, servis="ilk_ders", kuru=False, tetikleyen="otomatik_zamanlayici"
                            )
                finally:
                    conn.close()

            # Öğleden sonra 14:00 - 14:10 zaman penceresi (6. Ders)
            if simdi.hour == 14 and 0 <= simdi.minute <= 10:
                conn = db.baglanti()
                try:
                    if otomasyon_aktif_mi(conn, "ogle"):
                        son_tarih = db.ayar_oku(conn, AYAR_OGLE_SON_TARIH)
                        if son_tarih != bugun.isoformat():
                            logger.info(f"Saat {simdi.strftime('%H:%M:%S')} - 14:00 Öğleden Sonra Yoklama Otomasyonu tetikleniyor...")
                            await asyncio.to_thread(
                                otomasyon_calistir_thread, servis="ogle", kuru=False, tetikleyen="otomatik_zamanlayici"
                            )
                finally:
                    conn.close()

        except asyncio.CancelledError:
            logger.info("Otomasyon arka plan döngüsü durduruldu.")
            break
        except Exception as e:
            logger.error(f"Otomasyon arka plan döngüsünde beklenmeyen hata: {e}", exc_info=True)

