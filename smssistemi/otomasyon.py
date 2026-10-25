"""Devamsızlık SMS Otomasyonu ve Zamanlayıcı Servisi.

Pazartesi-Cuma günleri her AKTİF kural (`otomasyon_kurallari`: saat + ders no + şablon) kendi
saatinden itibaren PENCERE_DK dakika içinde o dersin yoklamasını kontrol eder ve gelmeyen
öğrencilerin velilerine otomatik SMS gönderir. Kurallar panelden eklenir/silinir (2026-10-25);
ilk kurulumda eski iki servis (09:00/1. ders, 14:00/6. ders) kural 1 ve 2 olarak taşınır.

Tasarım ve Güvenlik İlkeleri:
1. Yalnızca ilgili derste `durum == 'alindi'` olan sınıflar işlenir. Yoklaması
   alınmamış veya tahtasına ulaşılamamış sınıflar hariç tutulur (yanlış SMS önleme).
2. İzinli öğrenciler (`izinli_isimleri`) devamsız sayılmaz, SMS gönderilmez.
3. Bir öğrencinin kayıtlı her iki velisine de (anne ve baba) kişiselleştirilmiş
   ayrı SMS gider.
4. Aynı gün aynı derse mükerrer otomatik gönderim yapılmaz (ders başına `otomasyon_ders{N}_son_tarih`).
5. Her kural bağımsız açılır/kapatılır; yeni kural KAPALI eklenir.
6. Kuru çalıştırma (dry-run / simülasyon) desteği ile test edilebilir.
"""

import asyncio
import json
import logging
import re
import threading
import uuid
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

import db
import gonderim
import sms_gonderici
import yoklama_kaynak

logger = logging.getLogger("smssistemi.otomasyon")

_ISTANBUL = ZoneInfo("Europe/Istanbul")

VARSAYILAN_SABLON = "Sayın {isim}, öğrenciniz {ogrenci_adi} sabah ilk saate gelmemiştir. Bilginize."
VARSAYILAN_SABLON_DERS = "Sayın {isim}, öğrenciniz {ogrenci_adi} bugün {ders_no}. derse gelmemiştir. Bilginize."

PENCERE_DK = 10  # kural saatinden itibaren bu kadar dakika içinde tetiklenir (eski 09:00-09:10 penceresi)
DERS_NO_AZAMI = 12
SABLON_AZAMI = 480
AD_AZAMI = 60
_SAAT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Panel API (dashboard Bugün kartı) eski 'ilk_ders'/'ogle' adlarını kullanır: taşınan kural 1 ve 2.
SERVIS_KURAL = {"ilk_ders": 1, "ogle": 2}


class KuralHatasi(ValueError):
    pass

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


def varsayilan_sablon(ders_no: int) -> str:
    return VARSAYILAN_SABLON if ders_no == 1 else VARSAYILAN_SABLON_DERS.replace("{ders_no}", str(ders_no))


def ders_son_tarih_anahtari(ders_no: int) -> str:
    return f"otomasyon_ders{ders_no}_son_tarih"


def ders_son_tarih(conn, ders_no: int) -> str:
    return db.ayar_oku(conn, ders_son_tarih_anahtari(ders_no)) or ""


def _kural_sozluk(satir) -> dict:
    k = dict(satir)
    k["aktif"] = bool(k["aktif"])
    try:
        k["son_sonuc"] = json.loads(k["son_sonuc"]) if k["son_sonuc"] else None
    except ValueError:
        k["son_sonuc"] = None
    return k


def kurallar(conn) -> list[dict]:
    satirlar = conn.execute("SELECT * FROM otomasyon_kurallari ORDER BY saat, ders_no").fetchall()
    return [_kural_sozluk(s) for s in satirlar]


def kural_getir(conn, kural_id: int) -> dict | None:
    satir = conn.execute("SELECT * FROM otomasyon_kurallari WHERE id = ?", (kural_id,)).fetchone()
    return _kural_sozluk(satir) if satir else None


def _dogrula(ad: str, saat: str, ders_no, sablon: str) -> tuple[str, str, int, str]:
    saat = (saat or "").strip()
    if not _SAAT_RE.match(saat):
        raise KuralHatasi("Saat SS:DD biçiminde olmalı (örn. 09:00).")
    try:
        ders_no = int(ders_no)
    except (TypeError, ValueError):
        raise KuralHatasi("Ders numarası bir sayı olmalı.") from None
    if not 1 <= ders_no <= DERS_NO_AZAMI:
        raise KuralHatasi(f"Ders numarası 1 ile {DERS_NO_AZAMI} arasında olmalı.")
    sablon = (sablon or "").strip()
    if not sablon:
        raise KuralHatasi("Mesaj şablonu boş olamaz.")
    if len(sablon) > SABLON_AZAMI:
        raise KuralHatasi(f"Mesaj şablonu en çok {SABLON_AZAMI} karakter olabilir.")
    ad = " ".join((ad or "").split())[:AD_AZAMI] or f"{ders_no}. ders"
    return ad, saat, ders_no, sablon


def _ders_cakisiyor_mu(conn, ders_no: int, haric_id: int | None = None) -> bool:
    return conn.execute(
        "SELECT 1 FROM otomasyon_kurallari WHERE ders_no = ? AND id IS NOT ?", (ders_no, haric_id)
    ).fetchone() is not None


def kural_ekle(conn, ad: str, saat: str, ders_no, sablon: str) -> int:
    """Yeni kural KAPALI eklenir; açmak ayrı ve bilinçli bir adımdır."""
    ad, saat, ders_no, sablon = _dogrula(ad, saat, ders_no, sablon)
    if _ders_cakisiyor_mu(conn, ders_no):
        raise KuralHatasi(f"{ders_no}. ders için zaten bir otomasyon var; onu düzenleyin.")
    imlec = conn.execute(
        "INSERT INTO otomasyon_kurallari (ad, saat, ders_no, sablon, aktif) VALUES (?, ?, ?, ?, 0)",
        (ad, saat, ders_no, sablon),
    )
    conn.commit()
    return imlec.lastrowid


def kural_guncelle(conn, kural_id: int, ad: str, saat: str, ders_no, sablon: str) -> None:
    if kural_getir(conn, kural_id) is None:
        raise KuralHatasi("Otomasyon bulunamadı.")
    ad, saat, ders_no, sablon = _dogrula(ad, saat, ders_no, sablon)
    if _ders_cakisiyor_mu(conn, ders_no, kural_id):
        raise KuralHatasi(f"{ders_no}. ders için zaten başka bir otomasyon var.")
    conn.execute(
        "UPDATE otomasyon_kurallari SET ad = ?, saat = ?, ders_no = ?, sablon = ? WHERE id = ?",
        (ad, saat, ders_no, sablon, kural_id),
    )
    conn.commit()


def kural_aktif_yaz(conn, kural_id: int, aktif: bool) -> bool:
    imlec = conn.execute("UPDATE otomasyon_kurallari SET aktif = ? WHERE id = ?", (1 if aktif else 0, kural_id))
    conn.commit()
    return imlec.rowcount == 1


def kural_sil(conn, kural_id: int) -> bool:
    imlec = conn.execute("DELETE FROM otomasyon_kurallari WHERE id = ?", (kural_id,))
    conn.commit()
    return imlec.rowcount == 1


def son_sonuc_oku(conn, servis: str = "ilk_ders") -> dict | None:
    """Eski servis adıyla (panel API): taşınan kural 1/2'nin son sonucu; kural silindiyse None."""
    kural = kural_getir(conn, SERVIS_KURAL.get(servis, 0))
    return kural["son_sonuc"] if kural else None


def _ogrenciyi_eslestir(
    conn,
    ad_soyad: str,
    sinif_id: int | None,
    sinif_adi_ile: dict[int, str],
    okul_no: int | None = None,
) -> tuple[str, dict | None, list[dict], str | None]:
    """Okul no (varsa) veya İsim -> rehberdeki öğrenci -> telefonlu veliler.
    Döner: (eslesme_durumu, ogrenci|None, veliler, not).
    """
    if sinif_id is None:
        if _COZULMEMIS_ISIM_RE.match(ad_soyad.strip()):
            return ESLESME_YOK, None, [], "Panoda öğrenci numarası çözülememiş"
        return ESLESME_YOK, None, [], "Bu sınıf rehberde kayıtlı değil"

    ogrenci = None
    if okul_no is not None:
        ogrenci = db.kisi_bul_okul_no(conn, okul_no, sinif_id)
        if ogrenci is None:
            baska_no = db.kisi_bul_okul_no(conn, okul_no)
            if baska_no is not None:
                baska_sinif = sinif_adi_ile.get(baska_no["sinif_id"], "?")
                return ESLESME_YOK, None, [], f"Rehberde {baska_sinif} sınıfında kayıtlı"

    if ogrenci is None:
        if _COZULMEMIS_ISIM_RE.match(ad_soyad.strip()):
            return ESLESME_YOK, None, [], "Panoda öğrenci numarası çözülememiş"
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
    """Belirtilen ders numarası için devamsızlık özetini derler.

    Yalnızca belirtilen `ders_no` ve `durum == 'alindi'` olan sınıflar işleme alınır.
    İzinli öğrenciler devamsız sayılmaz.
    1'den büyük derslerde sabah 1. derste de devamsız olan öğrenciler işaretlenir.
    """
    hedef_tarih = tarih or bugun_istanbul().isoformat()
    mesaj_sablonu = sablon or varsayilan_sablon(ders_no)

    siniflar = db.siniflar_listele(conn)
    sinif_id_ile = {s["ad"]: s["id"] for s in siniflar}
    sinif_adi_ile = {s["id"]: s["ad"] for s in siniflar}

    satirlar = yoklama_kaynak.gunun_satirlari(hedef_tarih)
    hedef_ders_satirlari = [s for s in satirlar if s.get("ders_no") == ders_no]

    # Sonraki dersler için sabah 1. ders yoklama listesini de kontrol edelim
    sabah_yok_kumesi: set[tuple[str, str]] = set()
    sabah_yok_no_kumesi: set[tuple[str, int]] = set()
    if ders_no > 1:
        for s in satirlar:
            if s.get("ders_no") == 1 and s.get("durum") == yoklama_kaynak.DURUM_ALINDI:
                sinif_adi = s["sinif"]
                for isim in s.get("yok_isimleri", []):
                    sabah_yok_kumesi.add((sinif_adi, isim))
                for no in s.get("yok_nolari") or []:
                    sabah_yok_no_kumesi.add((sinif_adi, no))

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
    sabah_gelen_sayisi = 0

    for sinif_ad in dahil_siniflar:
        satir = gorulen_siniflar[sinif_ad]
        izinliler = set(satir.get("izinli_isimleri", []))
        izinli_nolari = set(satir.get("izinli_nolari") or [])
        yoklar = satir.get("yok_isimleri", [])
        yok_nolari = satir.get("yok_nolari") or []
        es_uzunluk = len(yok_nolari) == len(yoklar)

        for idx, ad_soyad in enumerate(yoklar):
            okul_no = yok_nolari[idx] if es_uzunluk else None
            if ad_soyad in izinliler or (okul_no is not None and okul_no in izinli_nolari):
                izinli_sayisi += 1
                continue

            durum, ogrenci, veliler, not_metni = _ogrenciyi_eslestir(
                conn, ad_soyad, sinif_id_ile.get(sinif_ad), sinif_adi_ile, okul_no=okul_no
            )
            gorunen_ad = (
                ogrenci["ad_soyad"]
                if ogrenci and _COZULMEMIS_ISIM_RE.match(ad_soyad.strip())
                else ad_soyad
            )

            sabah_da_yok = (
                (
                    (sinif_ad, ad_soyad) in sabah_yok_kumesi
                    or (okul_no is not None and (sinif_ad, okul_no) in sabah_yok_no_kumesi)
                )
                if ders_no > 1
                else False
            )
            if ders_no > 1 and not sabah_da_yok:
                sabah_gelen_sayisi += 1

            ogrenci_kayit = {
                "sinif": sinif_ad,
                "ad_soyad": gorunen_ad,
                "okul_no": okul_no or (ogrenci["okul_no"] if ogrenci else None),
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
        "sabah_gelen_sayisi": sabah_gelen_sayisi,
    }


def otomasyon_calistir(
    conn,
    kural_id: int,
    kuru: bool = False,
    tetikleyen: str = "otomasyon",
    tarih: str | None = None,
    bekleme_sn: float = 2.0,
) -> dict:
    """Bir devamsızlık SMS kuralını yürütür.

    kuru=True ise gerçek SMS göndermez ve son çalışma tarihini güncellemez.
    kuru=False ise gönderim yapar, veritabanına loglar ve dersin son çalışma tarihini kaydeder.
    Otomatik zamanlayıcı aynı gün aynı derse ikinci kez göndermez; elle tetik bu kontrolü
    bilerek atlar (arayüz onay ister).
    """
    kural = kural_getir(conn, kural_id)
    if kural is None:
        return {"durum": "kural_yok", "mesaj": "Otomasyon bulunamadı."}
    hedef_tarih = tarih or bugun_istanbul().isoformat()
    ders_no = kural["ders_no"]

    if not kuru and ders_son_tarih(conn, ders_no) == hedef_tarih and tetikleyen == "otomatik_zamanlayici":
        logger.info(f"Otomasyon ({ders_no}. ders) {hedef_tarih} için zaten çalışmış, mükerrer gönderim atlandı.")
        return {
            "durum": "zaten_calisti",
            "kural_id": kural_id,
            "mesaj": f"{hedef_tarih} tarihinde {ders_no}. ders otomasyonu zaten çalıştırılmış.",
            "tarih": hedef_tarih,
        }

    derleme = devamsizlar_derle(conn, ders_no=ders_no, tarih=hedef_tarih, sablon=kural["sablon"])
    gonderilecekler = derleme["gonderilecek_smsler"]

    if kuru:
        return {
            "durum": "simulasyon",
            "kural_id": kural_id,
            "kuru_calistirma": True,
            "tarih": hedef_tarih,
            "derleme": derleme,
            "gonderilecek_adet": len(gonderilecekler),
        }

    gonderim_id = f"oto{ders_no}_{uuid.uuid4().hex[:8]}"
    basarili_sayisi = 0
    hatali_sayisi = 0
    sms_denendi = False

    if gonderilecekler:
        logger.info(
            f"Otomasyon ({ders_no}. ders - {tetikleyen}) başlatılıyor: {len(gonderilecekler)} veliye SMS gönderilecek. "
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
    # düşükken tüm gönderim "hata" ile sonuçlandı) dersin son tarihi YAZILMAZ —
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
        db.ayar_yaz(conn, ders_son_tarih_anahtari(ders_no), hedef_tarih)

    sonuc_ozet = {
        "gonderim_id": gonderim_id,
        "kural_id": kural_id,
        "ders_no": ders_no,
        "tarih": hedef_tarih,
        "calisma_zamani": simdi_istanbul().strftime("%Y-%m-%d %H:%M:%S"),
        "tetikleyen": tetikleyen,
        "ogrenci_sayisi": derleme["toplam_ogrenci"],
        "veli_sms_sayisi": len(gonderilecekler),
        "basarili_sayisi": basarili_sayisi,
        "hatali_sayisi": hatali_sayisi,
        "dahil_sinif_sayisi": len(derleme["dahil_siniflar"]),
        "haric_sinif_sayisi": len(derleme["haric_siniflar"]),
        "haric_sebepleri": dict(Counter(h["sebep"] for h in derleme["haric_siniflar"])),
        "durum": sonuc_durum,
    }
    conn.execute(
        "UPDATE otomasyon_kurallari SET son_sonuc = ? WHERE id = ?",
        (json.dumps(sonuc_ozet, ensure_ascii=False), kural_id),
    )
    conn.commit()

    return {
        "durum": sonuc_durum,
        "kural_id": kural_id,
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


def otomasyon_calistir_thread(kural_id: int, **kwargs) -> dict:
    """`await asyncio.to_thread(otomasyon_calistir_thread, ...)` için."""
    if not _CALISMA_KILIDI.acquire(blocking=False):
        return {"durum": "calisiyor", "mesaj": "Otomasyon şu anda zaten çalışıyor."}
    try:
        conn = db.baglanti()
        try:
            return otomasyon_calistir(conn, kural_id, **kwargs)
        finally:
            conn.close()
    finally:
        _CALISMA_KILIDI.release()


def pencerede_mi(saat: str, simdi: datetime) -> bool:
    """Kural saati ile saat+PENCERE_DK (dahil) arasında mı? Eski 09:00-09:10 penceresinin genellemesi."""
    sa, dk = (int(p) for p in saat.split(":"))
    fark = simdi.hour * 60 + simdi.minute - (sa * 60 + dk)
    return 0 <= fark <= PENCERE_DK


def tetiklenecek_kurallar(conn, simdi: datetime) -> list[int]:
    """Şu an penceresinde olan, aktif ve dersi bugün henüz gönderilmemiş kuralların kimlikleri."""
    bugun = simdi.date().isoformat()
    return [
        k["id"]
        for k in kurallar(conn)
        if k["aktif"] and pencerede_mi(k["saat"], simdi) and ders_son_tarih(conn, k["ders_no"]) != bugun
    ]


async def otomasyon_arkaplan_dongusu() -> None:
    """Arka planda koşan zamanlayıcı döngüsü.

    Her 30 saniyede bir İstanbul saatini kontrol eder. Hafta içi okul günlerinde her aktif
    kural kendi saatinden itibaren PENCERE_DK dakika içinde, dersi o gün henüz gönderilmemişse
    devreye girer (gönderim hiç denenemediyse pencere içinde yeniden dener).
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

            conn = db.baglanti()
            try:
                hedefler = tetiklenecek_kurallar(conn, simdi)
            finally:
                conn.close()
            for kural_id in hedefler:
                logger.info(f"Saat {simdi.strftime('%H:%M:%S')} - devamsızlık otomasyonu (kural {kural_id}) tetikleniyor...")
                await asyncio.to_thread(
                    otomasyon_calistir_thread, kural_id, kuru=False, tetikleyen="otomatik_zamanlayici"
                )

            # Doğum günü SMS'i 09:30 - 09:40 (dogum_sms.py; ana şalter sms_otomatik, gerçek gönderim dogum_sms_gercek)
            if simdi.hour == 9 and 30 <= simdi.minute <= 40:
                conn = db.baglanti()
                try:
                    acik = db.ayar_oku(conn, "sms_otomatik") == "1"
                finally:
                    conn.close()
                if acik:
                    import dogum_sms  # döngüsel içe aktarmayı önler: dogum_sms otomasyon'u içe aktarır

                    await asyncio.to_thread(dogum_sms.calistir_thread, tetikleyen="otomatik_zamanlayici")

        except asyncio.CancelledError:
            logger.info("Otomasyon arka plan döngüsü durduruldu.")
            break
        except Exception as e:
            logger.error(f"Otomasyon arka plan döngüsünde beklenmeyen hata: {e}", exc_info=True)

