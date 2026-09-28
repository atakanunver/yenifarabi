"""Doğum günleri modülü için iş mantığı ve yardımcı fonksiyonlar.
- Dogum.xlsx'in openpyxl ile bağımlılıksız okunması
- Kişilerin kategorilere ayrılması:
    1. Zaten öğrencimiz olanlar (101 öğrenciyle ad-soyad eşleşenler -> doğrudan güncellenir, onaya gerek yok)
    2. Personel adayları (doğum yılı <= 2004 -> kolay onay/seçim listesi)
    3. Ayrılan/eski öğrenci adayları (doğum yılı > 2004, listede olmayanlar -> varsayılan seçili DEĞİL)
- Yaklaşan doğum günleri hesaplama
- İstatistik özetleri
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import openpyxl

import db

_ISTANBUL = ZoneInfo("Europe/Istanbul")
VARSAYILAN_EXCEL = Path(__file__).resolve().parent.parent / "dogum" / "Dogum.xlsx"

# Kullanıcı doğrulama kuralı: 13, 14, 15, 16, 17, 18, 19 yaşında olması öğrenci olduğunu gösterir.
# 20 yaş ve üzeri personeldir.
OGRENCI_MIN_YAS = 13
OGRENCI_MAX_YAS = 19


def ogrenci_yasi_mi(yas: int | None) -> bool:
    """13-19 yaş aralığı öğrenci olduğunu gösterir."""
    return yas is not None and OGRENCI_MIN_YAS <= yas <= OGRENCI_MAX_YAS


def personel_yasi_mi(yas: int | None) -> bool:
    """20 yaş ve üzeri personeldir."""
    return yas is not None and yas > OGRENCI_MAX_YAS


def _yil_cikar(deger) -> int | None:
    """Doğum tarihi hücresinden yılı çıkarır."""
    if deger is None:
        return None
    if isinstance(deger, (datetime, date)):
        return deger.year
    if isinstance(deger, str):
        parcalar = deger.strip().split("/")
        if len(parcalar) == 3 and parcalar[-1].isdigit():
            return int(parcalar[-1])
        parcalar_tire = deger.strip().split("-")
        if len(parcalar_tire) == 3 and parcalar_tire[0].isdigit():
            return int(parcalar_tire[0])
    return None


def excel_analiz_et(dosya_yolu: Path | str = VARSAYILAN_EXCEL, conn=None) -> dict:
    """Dogum.xlsx dosyasını okur ve mevcut veritabanı öğrencileriyle karşılaştırarak
    3 gruba ayırır:
      - eslesen_ogrenciler: Zaten sistemde olan aktif öğrenciler (onaya sunulmaz, doğrudan bağlanır)
      - personel_adaylari: Doğum yılı <= 2004 olan personel (varsayılan seçili)
      - ayrilan_ogrenci_adaylari: Doğum yılı > 2004 olup 101 öğrenci arasında bulunmayanlar (varsayılan seçili DEĞİL)
    """
    dosya_p = Path(dosya_yolu)
    if not dosya_p.is_file():
        return {
            "hata": f"Excel dosyası bulunamadı: {dosya_p}",
            "eslesen_ogrenciler": [],
            "personel_adaylari": [],
            "ayrilan_ogrenci_adaylari": [],
            "ozet": {"toplam_okunan": 0, "eslesen": 0, "personel": 0, "ayrilan": 0},
        }

    kendi_baglantisi = False
    if conn is None:
        conn = db.baglanti()
        kendi_baglantisi = True

    try:
        # Aktif öğrencileri al
        ogrenciler = conn.execute(
            "SELECT k.id, k.ad_soyad, k.dogum_tarihi, s.ad AS sinif_ad "
            "FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
            "WHERE k.tur = 'ogrenci'"
        ).fetchall()
        db_ogrenciler = {db._tr_norm(ogr["ad_soyad"]): dict(ogr) for ogr in ogrenciler}

        # Mevcut personelleri al (zaten eklenmişse tekrar çift eklenmesin diye)
        personeller = conn.execute(
            "SELECT k.id, k.ad_soyad, k.dogum_tarihi "
            "FROM kisiler k WHERE k.tur = 'personel'"
        ).fetchall()
        db_personeller = {db._tr_norm(p["ad_soyad"]): dict(p) for p in personeller}

        wb = openpyxl.load_workbook(dosya_p, data_only=True)
        sheet = wb["Sayfa1"] if "Sayfa1" in wb.sheetnames else wb.active
        rows = list(sheet.iter_rows(values_only=True))

        bugun_yil = datetime.now(_ISTANBUL).year

        eslesen_ogrenciler = []
        personel_adaylari = []
        ayrilan_ogrenci_adaylari = []

        for r in rows[1:]:
            if not r or len(r) < 5:
                continue
            ad = str(r[0]).strip() if r[0] is not None and str(r[0]).strip().lower() != "none" else ""
            soyad = str(r[1]).strip() if r[1] is not None and str(r[1]).strip().lower() != "none" else ""
            gun = r[3]
            ay = r[4]
            if not gun or gun == 0 or (not ad and not soyad):
                continue

            try:
                gun_int = int(gun)
                ay_int = int(ay)
            except (ValueError, TypeError):
                continue

            ad_soyad = f"{ad} {soyad}".strip()
            yil = _yil_cikar(r[2])
            iso_tarih = f"{yil:04d}-{ay_int:02d}-{gun_int:02d}" if yil else None
            yas = (bugun_yil - yil) if yil else None
            norm = db._tr_norm(ad_soyad)

            if norm in db_ogrenciler:
                ogr_info = db_ogrenciler[norm]
                eslesen_ogrenciler.append({
                    "ad_soyad": ogr_info["ad_soyad"],
                    "excel_ad_soyad": ad_soyad,
                    "kisi_id": ogr_info["id"],
                    "sinif_ad": ogr_info["sinif_ad"],
                    "mevcut_dogum_tarihi": ogr_info["dogum_tarihi"],
                    "yeni_dogum_tarihi": iso_tarih,
                    "yil": yil,
                    "ay": ay_int,
                    "gun": gun_int,
                    "yas": yas,
                })
            elif personel_yasi_mi(yas):
                mevcut = db_personeller.get(norm)
                personel_adaylari.append({
                    "ad_soyad": ad_soyad,
                    "kisi_id": mevcut["id"] if mevcut else None,
                    "zaten_kayitli": mevcut is not None,
                    "mevcut_dogum_tarihi": mevcut["dogum_tarihi"] if mevcut else None,
                    "dogum_tarihi": iso_tarih,
                    "yil": yil,
                    "ay": ay_int,
                    "gun": gun_int,
                    "yas": yas,
                })
            else:
                ayrilan_ogrenci_adaylari.append({
                    "ad_soyad": ad_soyad,
                    "dogum_tarihi": iso_tarih,
                    "yil": yil,
                    "ay": ay_int,
                    "gun": gun_int,
                    "yas": yas,
                })

        return {
            "dosya": str(dosya_p),
            "eslesen_ogrenciler": eslesen_ogrenciler,
            "personel_adaylari": sorted(personel_adaylari, key=lambda x: (x["yil"] or 9999, x["ad_soyad"])),
            "ayrilan_ogrenci_adaylari": sorted(ayrilan_ogrenci_adaylari, key=lambda x: (x["yil"] or 9999, x["ad_soyad"])),
            "ozet": {
                "toplam_okunan": len(eslesen_ogrenciler) + len(personel_adaylari) + len(ayrilan_ogrenci_adaylari),
                "eslesen": len(eslesen_ogrenciler),
                "personel": len(personel_adaylari),
                "ayrilan": len(ayrilan_ogrenci_adaylari),
            },
        }
    finally:
        if kendi_baglantisi:
            conn.close()


def aktarim_uygula(
    conn,
    secilen_personeller: list[str] | set[str] | None = None,
    secilen_ayrilanlar: list[str] | set[str] | None = None,
    dosya_yolu: Path | str = VARSAYILAN_EXCEL,
) -> dict:
    """Kullanıcı tercihlerine göre içe aktarımı güvenli bir transaction içinde uygular:
    - 1. eslesen_ogrenciler: Zaten öğrencimiz olanlar doğrudan güncellenir (onay gerekmez).
    - 2. secilen_personeller: Yalnızca kullanıcının işaretlediği/onayladığı personel eklenir.
    - 3. secilen_ayrilanlar: Kullanıcının işaretlediği eski/ayrılan öğrenciler eklenir (işaretsizler atlanır).
    """
    analiz = excel_analiz_et(dosya_yolu, conn=conn)
    if "hata" in analiz:
        return {"hata": analiz["hata"]}

    secilen_personel_set = set(secilen_personeller or [])
    secilen_ayrilan_set = set(secilen_ayrilanlar or [])

    personel_sinif_id = db.sinif_ekle(conn, "Personel")
    bilinmeyen_sinif_id = db.sinif_ekle(conn, "Bilinmeyen Sınıf")

    eslesen_guncellendi = 0
    personel_eklendi = 0
    personel_guncellendi = 0
    ayrilan_eklendi = 0
    atlanan_personel = 0
    atlanan_ayrilan = 0

    # 1. Zaten öğrencimiz olanlar (Doğrudan güncelle, kullanıcıyı uğraştırma)
    for ogr in analiz["eslesen_ogrenciler"]:
        if ogr["yeni_dogum_tarihi"]:
            db.kisi_dogum_tarihi_guncelle(conn, ogr["kisi_id"], ogr["yeni_dogum_tarihi"])
            eslesen_guncellendi += 1

    # 2. Personel adayları (İnsanın onayladıkları)
    for p in analiz["personel_adaylari"]:
        ad = p["ad_soyad"]
        if ad in secilen_personel_set:
            bulunan = db.kisi_bul_isimle_sinifsiz(conn, ad, "personel")
            if bulunan is not None:
                db.kisi_dogum_tarihi_guncelle(conn, bulunan["id"], p["dogum_tarihi"])
                personel_guncellendi += 1
            else:
                yeni_id = db.kisi_ekle(conn, ad, None, personel_sinif_id, "personel")
                db.kisi_dogum_tarihi_guncelle(conn, yeni_id, p["dogum_tarihi"])
                personel_eklendi += 1
        else:
            atlanan_personel += 1

    # 3. Ayrılan / Listede olmayan öğrenci adayları (Yalnızca seçilenler)
    for a in analiz["ayrilan_ogrenci_adaylari"]:
        ad = a["ad_soyad"]
        if ad in secilen_ayrilan_set:
            bulunan = db.kisi_bul_isimle_sinifsiz(conn, ad, "ogrenci")
            if bulunan is not None:
                db.kisi_dogum_tarihi_guncelle(conn, bulunan["id"], a["dogum_tarihi"])
            else:
                yeni_id = db.kisi_ekle(conn, ad, None, bilinmeyen_sinif_id, "ogrenci")
                db.kisi_dogum_tarihi_guncelle(conn, yeni_id, a["dogum_tarihi"])
                ayrilan_eklendi += 1
        else:
            atlanan_ayrilan += 1

    conn.commit()

    return {
        "eslesen_guncellendi": eslesen_guncellendi,
        "personel_eklendi": personel_eklendi,
        "personel_guncellendi": personel_guncellendi,
        "atlanan_personel": atlanan_personel,
        "ayrilan_eklendi": ayrilan_eklendi,
        "atlanan_ayrilan": atlanan_ayrilan,
        "toplam_islenen": eslesen_guncellendi + personel_eklendi + personel_guncellendi + ayrilan_eklendi,
    }


def yaklasan_dogum_gunleri(conn, gun_sayisi: int = 30) -> list[dict]:
    """Önümüzdeki `gun_sayisi` gün içinde doğum günü olan kişileri döner.
    Gün farkı ve yeni yaş hesaplanır, en yakın tarihten uzağa doğru sıralanır."""
    kisiler = db.dogum_tarihli_kisiler(conn)
    bugun = datetime.now(_ISTANBUL).date()

    sonuclar = []
    for k in kisiler:
        dt_str = k.get("dogum_tarihi")
        if not dt_str:
            continue
        try:
            parcalar = dt_str.split("-")
            d_yil = int(parcalar[0])
            d_ay = int(parcalar[1])
            d_gun = int(parcalar[2])
        except (ValueError, IndexError):
            continue

        # Bu yılki doğum günü
        try:
            bu_yil_dogum = date(bugun.year, d_ay, d_gun)
        except ValueError:
            # 29 Şubat artık olmayan yılda 28 Şubat'a yuvarlanır
            bu_yil_dogum = date(bugun.year, 2, 28)

        if bu_yil_dogum < bugun:
            # Bu yılki geçti, sonraki yıla bak
            try:
                sonraki_dogum = date(bugun.year + 1, d_ay, d_gun)
            except ValueError:
                sonraki_dogum = date(bugun.year + 1, 2, 28)
            fark = (sonraki_dogum - bugun).days
            yeni_yas = (bugun.year + 1) - d_yil
            hedef_tarih = sonraki_dogum
        else:
            fark = (bu_yil_dogum - bugun).days
            yeni_yas = bugun.year - d_yil
            hedef_tarih = bu_yil_dogum

        if 0 <= fark <= gun_sayisi:
            sonuclar.append({
                "id": k["id"],
                "ad_soyad": k["ad_soyad"],
                "telefon": k.get("telefon"),
                "tur": k.get("tur"),
                "sinif_id": k.get("sinif_id"),
                "sinif_ad": k.get("sinif_ad"),
                "dogum_tarihi": dt_str,
                "hedef_tarih": hedef_tarih.isoformat(),
                "kalan_gun": fark,
                "yeni_yas": yeni_yas,
            })

    sonuclar.sort(key=lambda x: (x["kalan_gun"], x["ad_soyad"]))
    return sonuclar


def dogum_gunu_istatistikleri(conn) -> dict:
    """Dashboard KPI şeridi için gerekli özet verileri üretir."""
    bugun = datetime.now(_ISTANBUL).date()

    # Toplam kişi ve doğum tarihi durumu (öğrenci + personel)
    satir = conn.execute(
        "SELECT "
        "  COUNT(*) AS toplam, "
        "  SUM(CASE WHEN dogum_tarihi IS NOT NULL THEN 1 ELSE 0 END) AS tanimli, "
        "  SUM(CASE WHEN dogum_tarihi IS NULL THEN 1 ELSE 0 END) AS eksik, "
        "  SUM(CASE WHEN tur = 'ogrenci' THEN 1 ELSE 0 END) AS ogrenci_sayisi, "
        "  SUM(CASE WHEN tur = 'personel' THEN 1 ELSE 0 END) AS personel_sayisi "
        "FROM kisiler WHERE tur IN ('ogrenci', 'personel')"
    ).fetchone()

    toplam = satir["toplam"] if satir else 0
    tanimli = satir["tanimli"] if (satir and satir["tanimli"]) else 0
    eksik = satir["eksik"] if (satir and satir["eksik"]) else 0
    ogrenci_sayisi = satir["ogrenci_sayisi"] if (satir and satir["ogrenci_sayisi"]) else 0
    personel_sayisi = satir["personel_sayisi"] if (satir and satir["personel_sayisi"]) else 0

    # Bugün doğanlar
    bugun_doganlar = db.dogum_gunu_olanlar(conn, bugun.month, bugun.day)

    # Bu ay doğanlar
    bu_ay_str = f"{bugun.month:02d}-"
    bu_ay_satir = conn.execute(
        "SELECT COUNT(*) AS sayi FROM kisiler "
        "WHERE tur IN ('ogrenci', 'personel') AND substr(dogum_tarihi, 6, 3) = ?",
        (bu_ay_str,),
    ).fetchone()
    bu_ay_sayisi = bu_ay_satir["sayi"] if bu_ay_satir else 0

    # Yaklaşan 7 gün ve 30 gün
    yaklasan_7 = yaklasan_dogum_gunleri(conn, gun_sayisi=7)
    yaklasan_30 = yaklasan_dogum_gunleri(conn, gun_sayisi=30)

    # Ayarlar
    sms_otomatik = db.ayar_oku(conn, "sms_otomatik") or "0"
    dogum_sms_sablonu = (
        db.ayar_oku(conn, "dogum_sms_sablonu")
        or "Sevgili {isim}, dogum gununuzu kutlar, saglikli ve mutlu bir yil dileriz. Okul Idaresi"
    )

    return {
        "toplam": toplam,
        "tanimli": tanimli,
        "eksik": eksik,
        "ogrenci_sayisi": ogrenci_sayisi,
        "personel_sayisi": personel_sayisi,
        "bugun_doganlar": bugun_doganlar,
        "bugun_sayisi": len(bugun_doganlar),
        "bu_ay_sayisi": bu_ay_sayisi,
        "yaklasan_7": yaklasan_7,
        "yaklasan_30": yaklasan_30,
        "sms_otomatik": sms_otomatik,
        "dogum_sms_sablonu": dogum_sms_sablonu,
    }
