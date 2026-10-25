"""otomasyon.py birim testleri."""

import json
from datetime import date
from unittest.mock import patch

import pytest

import db
import otomasyon
import yoklama_kaynak


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_yolu = tmp_path / "test_otomasyon.db"
    yedek_dizini = tmp_path / "yedek"
    monkeypatch.setattr(db, "DB_YOLU", db_yolu)
    monkeypatch.setattr(db, "YEDEK_DIZINI", yedek_dizini)
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


def test_okul_gunu_mu():
    pazartesi = date(2026, 9, 21)
    cuma = date(2026, 9, 25)
    cumartesi = date(2026, 9, 26)
    pazar = date(2026, 9, 27)

    assert otomasyon.okul_gunu_mu(pazartesi) is True
    assert otomasyon.okul_gunu_mu(cuma) is True
    assert otomasyon.okul_gunu_mu(cumartesi) is False
    assert otomasyon.okul_gunu_mu(pazar) is False


def test_ilk_ders_devamsizlar_ve_veliler(test_db, monkeypatch):
    # Öğrenci ve velilerini ekle
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]
    sinif_10a = siniflar["10-A"]

    # 9-A'da Ali Kaya (anne ve baba telefonlu)
    ali_id = db.kisi_ekle(
        test_db, "Ali Kaya", None, sinif_9a, "ogrenci", okul_no=101
    )
    db.kisi_ekle(
        test_db, "Fatma Kaya", "05321112233", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="anne"
    )
    db.kisi_ekle(
        test_db, "Mehmet Kaya", "05322223344", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="baba"
    )

    # 9-A'da Veli Çelik (telefonsuz velili veya velisiz)
    db.kisi_ekle(
        test_db, "Veli Çelik", None, sinif_9a, "ogrenci", okul_no=102
    )

    # 9-A'da Can Demir (izinli)
    can_id = db.kisi_ekle(
        test_db, "Can Demir", None, sinif_9a, "ogrenci", okul_no=103
    )
    db.kisi_ekle(
        test_db, "Ayşe Demir", "05323334455", sinif_9a, "veli", ogrenci_kisi_id=can_id, veli_rol="anne"
    )

    # Sahte yoklama satırları
    sahte_satirlar = [
        # 9-A 1. ders: alındı, Ali Kaya ve Veli Çelik yok, Can Demir izinli ve yok
        {
            "sinif": "9-A",
            "ders_no": 1,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya", "Veli Çelik", "Can Demir"],
            "izinli_isimleri": ["Can Demir"],
            "kaydedilme_saati": "08:25",
        },
        # 9-A 2. ders: (1. ders derlemesinde DİKKATE ALINMAMALI)
        {
            "sinif": "9-A",
            "ders_no": 2,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "09:15",
        },
        # 10-A 1. ders: tahta ulaşılamaz (HARİÇ TUTULMALI, devamsız üretmemeli)
        {
            "sinif": "10-A",
            "ders_no": 1,
            "durum": "tahta_ulasilamaz",
            "yok_isimleri": ["Ahmet Yılmaz"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "08:15",
        },
    ]

    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    sonuc = otomasyon.devamsizlar_derle(test_db, ders_no=1, tarih="2026-09-25")

    assert "9-A" in sonuc["dahil_siniflar"]
    haric_isimler = [h["sinif"] for h in sonuc["haric_siniflar"]]
    assert "10-A" in haric_isimler

    # Can Demir izinli olduğu için SMS listesinde olmamalı!
    ogrenci_adlari = [o["ad_soyad"] for o in sonuc["ogrenciler"]]
    assert "Ali Kaya" in ogrenci_adlari
    assert "Veli Çelik" in ogrenci_adlari
    assert "Can Demir" not in ogrenci_adlari
    assert sonuc["izinli_sayisi"] == 1

    # Ali Kaya'nın 2 velisine de SMS çıkmalı
    smsler = sonuc["gonderilecek_smsler"]
    assert len(smsler) == 2
    veli_adlari = {s["veli_ad"] for s in smsler}
    assert "Fatma Kaya" in veli_adlari
    assert "Mehmet Kaya" in veli_adlari

    for s in smsler:
        assert "Ali Kaya" in s["mesaj"]
        assert s["veli_ad"] in s["mesaj"]


def test_otomasyon_calistir_kuru(test_db, monkeypatch):
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [])
    sonuc = otomasyon.otomasyon_calistir(test_db, 1, kuru=True, tarih="2026-09-25")
    assert sonuc["durum"] == "simulasyon"
    assert sonuc["kuru_calistirma"] is True
    # Kuru çalıştırma son tarihi güncellemez
    assert otomasyon.ders_son_tarih(test_db, 1) == ""


def test_otomasyon_calistir_canli_ve_idempotent(test_db, monkeypatch):
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]

    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, sinif_9a, "ogrenci", okul_no=105)
    db.kisi_ekle(
        test_db, "Selin Aras", "05329998877", sinif_9a, "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne"
    )

    sahte_satirlar = [
        {
            "sinif": "9-A",
            "ders_no": 1,
            "durum": "alindi",
            "yok_isimleri": ["Deniz Aras"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "08:30",
        }
    ]
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    gonderilenler = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilenler.append((isim, tel, msg))
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    # 1. Çalıştırma: Gönderim yapmalı
    sonuc1 = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc1["durum"] == "tamamlandi"
    assert len(gonderilenler) == 1
    assert gonderilenler[0][0] == "Selin Aras"
    assert otomasyon.ders_son_tarih(test_db, 1) == "2026-09-25"

    son_sonuc = otomasyon.kural_getir(test_db, 1)["son_sonuc"]
    assert son_sonuc["veli_sms_sayisi"] == 1
    assert son_sonuc["basarili_sayisi"] == 1

    # 2. Çalıştırma: Aynı gün ikinci kez çalışırsa idempotent olmalı, tekrar SMS göndermemeli!
    sonuc2 = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc2["durum"] == "zaten_calisti"
    # Hala 1 olmalı, artmamış olmalı
    assert len(gonderilenler) == 1


def test_otomasyon_baglanti_hatasinda_son_tarih_yazilmaz_ve_tekrar_dener(test_db, monkeypatch):
    """2026-09-28 canlı olayının regresyon testi: Müdür PC proxy'si
    düşünce (_baglan hep başarısız), otomasyon o gün için dersin son tarihini
    YAZMAMALI — aksi halde arka plan döngüsü 09:00-09:10 penceresinde bir
    daha denemiyordu. Her alıcı kendi telefonuyla 'hata' kaydedilmeli ki
    /tekrar-gonder ile kurtarılabilsin (db.gonderim_basarisizlari telefon
    boşları filtreler)."""
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]
    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, sinif_9a, "ogrenci", okul_no=105)
    db.kisi_ekle(
        test_db, "Selin Aras", "05329998877", sinif_9a, "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne"
    )
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Deniz Aras"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])
    monkeypatch.setattr(otomasyon.sms_gonderici, "modem_ayarlarini_yukle", lambda: {})
    monkeypatch.setattr(
        otomasyon.sms_gonderici, "_baglan",
        lambda ayarlar: (_ for _ in ()).throw(RuntimeError("proxy erişilemedi")),
    )

    sonuc1 = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-28", bekleme_sn=0
    )

    assert sonuc1["durum"] == "basarisiz"
    assert sonuc1["ozet"]["basarili_sayisi"] == 0
    assert sonuc1["ozet"]["hatali_sayisi"] == 1

    # Son tarih YAZILMADI — mükerrer gönderim önleyici tetiklenmemeli.
    assert otomasyon.ders_son_tarih(test_db, 1) == ""
    son_sonuc = otomasyon.kural_getir(test_db, 1)["son_sonuc"]
    assert son_sonuc["durum"] == "basarisiz"

    # Kaydedilen satır telefon dolu — /tekrar-gonder ile kurtarılabilir.
    basarisizlar = db.gonderim_basarisizlari(test_db, sonuc1["gonderim_id"])
    assert basarisizlar == [("Selin Aras", "05329998877", basarisizlar[0][2])]

    # İkinci (30 sn sonraki) otomatik deneme "zaten_calisti" DEMEMELİ, tekrar denemeli.
    sonuc2 = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-28", bekleme_sn=0
    )
    assert sonuc2["durum"] != "zaten_calisti"


def test_otomasyon_kismi_basaridan_sonra_son_tarih_yazilir(test_db, monkeypatch):
    """En az bir SMS gittiyse (kısmi başarı dahil) mükerrer gönderimi
    önlemek için son tarih yine de yazılmalı."""
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]
    ogr1 = db.kisi_ekle(test_db, "Deniz Aras", None, sinif_9a, "ogrenci", okul_no=105)
    db.kisi_ekle(test_db, "Selin Aras", "05329998877", sinif_9a, "veli", ogrenci_kisi_id=ogr1, veli_rol="anne")
    ogr2 = db.kisi_ekle(test_db, "Kaan Öz", None, sinif_9a, "ogrenci", okul_no=106)
    db.kisi_ekle(test_db, "Berk Öz", "05329998866", sinif_9a, "veli", ogrenci_kisi_id=ogr2, veli_rol="baba")
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi",
        "yok_isimleri": ["Deniz Aras", "Kaan Öz"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        # İlk alıcıya gider, ikincide bağlantı tamamen kopar (toplu_gonder
        # kendi içinde kalanları "hata" kaydeder — burada da aynısını simüle et).
        callback(*kisiler[0], "gonderildi", None)
        callback(*kisiler[1], "hata", "BAĞLANTI HATASI (gönderim sırasında): koptu")

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    sonuc = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25", bekleme_sn=0
    )

    assert sonuc["durum"] == "tamamlandi"
    assert sonuc["ozet"]["basarili_sayisi"] == 1
    assert sonuc["ozet"]["hatali_sayisi"] == 1
    assert otomasyon.ders_son_tarih(test_db, 1) == "2026-09-25"


def test_otomasyon_sms_denendi_ama_hepsi_hata_ise_son_tarih_yazilir(test_db, monkeypatch):
    """Bağlantı kuruldu, send_sms her alıcıda hata verdi (ör. modem kabul edip
    zaman aşımına düştü — SMS aslında gitmiş olabilir). Bu durumda 09:00-09:10
    döngüsü yeniden DENEMEMELİ, yoksa veliye 30 sn'de bir mükerrer SMS gider.
    Yeniden deneme yalnızca hiçbir SMS denenmediyse (bağlantı hatası) yapılır."""
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    ogr = db.kisi_ekle(test_db, "Deniz Aras", None, siniflar["9-A"], "ogrenci", okul_no=105)
    db.kisi_ekle(test_db, "Selin Aras", "05329998877", siniflar["9-A"], "veli", ogrenci_kisi_id=ogr, veli_rol="anne")
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Deniz Aras"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        callback(*kisiler[0], "hata", "Read timed out")

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    sonuc = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25", bekleme_sn=0
    )

    assert sonuc["ozet"]["basarili_sayisi"] == 0
    assert sonuc["durum"] == "tamamlandi"
    assert otomasyon.ders_son_tarih(test_db, 1) == "2026-09-25"


def test_otomasyon_gercek_toplu_gonder_ile_sms_gonderir(test_db, monkeypatch):
    """toplu_gonder MOCK'LANMADAN (yalnızca modem bağlantısı sahte): 2026-09-25'e
    kadar otomasyon durdur_bayragi=None veriyordu, toplu_gonder ilk .is_set()'te
    patlıyor ve HİÇ SMS gitmiyordu — mock'lu testler bunu göremiyordu."""
    from unittest.mock import MagicMock

    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, siniflar["9-A"], "ogrenci", okul_no=105)
    db.kisi_ekle(
        test_db, "Selin Aras", "05329998877", siniflar["9-A"], "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne"
    )
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Deniz Aras"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])

    class SahteBaglanti:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    gonderilen = []
    sahte_client = MagicMock()
    sahte_client.sms.send_sms.side_effect = lambda tel, msg, text_mode=None: gonderilen.append(tel)
    monkeypatch.setattr(otomasyon.sms_gonderici, "modem_ayarlarini_yukle", lambda: {})
    monkeypatch.setattr(otomasyon.sms_gonderici, "_baglan", lambda ayarlar: SahteBaglanti())
    monkeypatch.setattr(otomasyon.sms_gonderici, "Client", lambda conn: sahte_client)

    sonuc = otomasyon.otomasyon_calistir(
        test_db, 1, kuru=False, tetikleyen="manuel_arayuz", tarih="2026-09-25", bekleme_sn=0
    )
    assert gonderilen == [["05329998877"]]
    assert sonuc["ozet"]["basarili_sayisi"] == 1
    assert sonuc["ozet"]["hatali_sayisi"] == 0


def test_ogle_devamsizlar_ve_veliler(test_db, monkeypatch):
    """Öğleden sonra 6. ders devamsızlık derlemesi, sabah durumu kontrolü ve veli eşleştirme."""
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]

    # 9-A: Ali Kaya (1. derste de yok, 6. derste de yok -> tüm gün yok)
    ali_id = db.kisi_ekle(test_db, "Ali Kaya", None, sinif_9a, "ogrenci", okul_no=201)
    db.kisi_ekle(test_db, "Fatma Kaya", "05321112233", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="anne")
    db.kisi_ekle(test_db, "Mehmet Kaya", "05322223344", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="baba")

    # 9-A: Selin Yılmaz (1. derste VARDI, 6. derste yok -> öğleden sonra kaçan)
    selin_id = db.kisi_ekle(test_db, "Selin Yılmaz", None, sinif_9a, "ogrenci", okul_no=202)
    db.kisi_ekle(test_db, "Murat Yılmaz", "05325556677", sinif_9a, "veli", ogrenci_kisi_id=selin_id, veli_rol="baba")

    # 9-A: Can Demir (6. derste izinli -> SMS gitmemeli)
    can_id = db.kisi_ekle(test_db, "Can Demir", None, sinif_9a, "ogrenci", okul_no=203)
    db.kisi_ekle(test_db, "Ayşe Demir", "05323334455", sinif_9a, "veli", ogrenci_kisi_id=can_id, veli_rol="anne")

    sahte_satirlar = [
        # 1. ders satırları: Ali Kaya yok
        {
            "sinif": "9-A",
            "ders_no": 1,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "08:30",
        },
        # 6. ders satırları: 9-A'da Ali Kaya, Selin Yılmaz ve Can Demir yok (Can Demir izinli)
        {
            "sinif": "9-A",
            "ders_no": 6,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya", "Selin Yılmaz", "Can Demir"],
            "izinli_isimleri": ["Can Demir"],
            "kaydedilme_saati": "13:40",
        },
        # 10-A 6. ders: tahta_ulasilamaz (HARİÇ TUTULMALI)
        {
            "sinif": "10-A",
            "ders_no": 6,
            "durum": "tahta_ulasilamaz",
            "yok_isimleri": ["Ahmet Yılmaz"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "13:35",
        },
    ]

    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    sonuc = otomasyon.devamsizlar_derle(
        test_db, ders_no=6, tarih="2026-09-25", sablon=otomasyon.kural_getir(test_db, 2)["sablon"]
    )

    assert "9-A" in sonuc["dahil_siniflar"]
    haric_isimler = [h["sinif"] for h in sonuc["haric_siniflar"]]
    assert "10-A" in haric_isimler

    assert sonuc["ders_no"] == 6
    assert sonuc["izinli_sayisi"] == 1
    assert sonuc["sabah_gelen_sayisi"] == 1  # Yalnızca Selin Yılmaz

    ogrenciler_dict = {o["ad_soyad"]: o for o in sonuc["ogrenciler"]}
    assert "Ali Kaya" in ogrenciler_dict
    assert "Selin Yılmaz" in ogrenciler_dict
    assert "Can Demir" not in ogrenciler_dict

    # Sabah durumu kontrolleri
    assert ogrenciler_dict["Ali Kaya"]["sabah_da_yok"] is True
    assert ogrenciler_dict["Selin Yılmaz"]["sabah_da_yok"] is False

    # SMS'ler: Ali Kaya'nın 2 velisi + Selin'in 1 velisi = 3 SMS
    smsler = sonuc["gonderilecek_smsler"]
    assert len(smsler) == 3
    veli_adlari = {s["veli_ad"] for s in smsler}
    assert "Fatma Kaya" in veli_adlari
    assert "Mehmet Kaya" in veli_adlari
    assert "Murat Yılmaz" in veli_adlari

    for s in smsler:
        assert "öğleden sonra" in s["mesaj"]


def test_otomasyon_calistir_ogle_canli_ve_idempotent(test_db, monkeypatch):
    """Öğle otomasyonunun çalışması, oto6_ ön eki, bağımsız son tarih ve mükerrer engeli."""
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]

    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, sinif_9a, "ogrenci", okul_no=105)
    db.kisi_ekle(test_db, "Selin Aras", "05329998877", sinif_9a, "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne")

    sahte_satirlar = [
        {
            "sinif": "9-A",
            "ders_no": 6,
            "durum": "alindi",
            "yok_isimleri": ["Deniz Aras"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "13:38",
        }
    ]
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    gonderilenler = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilenler.append((isim, tel, msg))
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    # 1. Kuru çalıştırma
    sonuc_kuru = otomasyon.otomasyon_calistir(test_db, 2, kuru=True, tarih="2026-09-25")
    assert sonuc_kuru["durum"] == "simulasyon"
    assert sonuc_kuru["kural_id"] == 2
    assert otomasyon.ders_son_tarih(test_db, 6) == ""

    # 2. Canlı çalıştırma
    sonuc1 = otomasyon.otomasyon_calistir(
        test_db, 2, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc1["durum"] == "tamamlandi"
    assert sonuc1["gonderim_id"].startswith("oto6_")
    assert sonuc1["kural_id"] == 2
    assert len(gonderilenler) == 1
    assert otomasyon.ders_son_tarih(test_db, 6) == "2026-09-25"

    son_sonuc = otomasyon.kural_getir(test_db, 2)["son_sonuc"]
    assert son_sonuc["veli_sms_sayisi"] == 1
    assert son_sonuc["ders_no"] == 6

    # 3. İkinci çalıştırma (idempotency)
    sonuc2 = otomasyon.otomasyon_calistir(
        test_db, 2, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc2["durum"] == "zaten_calisti"
    assert len(gonderilenler) == 1  # Tekrar SMS göndermedi


def test_sabah_ve_ogle_otomasyonlari_birbirinden_bagimsiz(test_db, monkeypatch):
    """Sabah otomasyonu çalışmış olsa bile öğle otomasyonu engellenmez; durumlar bağımsızdır."""
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [])

    # Sabahı çalışmış olarak işaretle
    db.ayar_yaz(test_db, otomasyon.ders_son_tarih_anahtari(1), "2026-09-25")
    assert otomasyon.ders_son_tarih(test_db, 1) == "2026-09-25"
    assert otomasyon.ders_son_tarih(test_db, 6) == ""

    # Öğle servisini çalıştır: sabahın bitmiş olması öğleyi bloklamamalı
    sonuc = otomasyon.otomasyon_calistir(
        test_db, 2, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc["durum"] == "tamamlandi"
    assert otomasyon.ders_son_tarih(test_db, 6) == "2026-09-25"



# --- Eklenip silinebilen kurallar (2026-10-25) --------------------------------


def _eski_kurulum(tmp_path, monkeypatch, ayarlar: dict):
    """Kurallar tablosu yokken (eski sürüm) ayarları yazılmış bir DB'yi taklit eder."""
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "eski.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    monkeypatch.setattr(db, "_otomasyon_kurallari_tasi", lambda conn: None)
    db.semayi_kur()
    conn = db.baglanti()
    for k, v in ayarlar.items():
        db.ayar_yaz(conn, k, v)
    conn.close()
    monkeypatch.undo()
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "eski.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")


def test_tasima_eski_servislerin_durumunu_korur(tmp_path, monkeypatch):
    sonuc = {"tarih": "2026-10-24", "veli_sms_sayisi": 3}
    _eski_kurulum(tmp_path, monkeypatch, {
        "otomasyon_ilk_ders_aktif": "1",
        "otomasyon_ilk_ders_sablonu": "Sabah özel {isim}",
        "otomasyon_ilk_ders_son_tarih": "2026-10-24",
        "otomasyon_ilk_ders_son_sonuc": json.dumps(sonuc),
        "otomasyon_ogle_aktif": "0",
    })
    db.semayi_kur()  # yeni sürümün ilk açılışı
    conn = db.baglanti()
    try:
        k1, k2 = otomasyon.kural_getir(conn, 1), otomasyon.kural_getir(conn, 2)
        assert (k1["saat"], k1["ders_no"], k1["aktif"], k1["sablon"]) == ("09:00", 1, True, "Sabah özel {isim}")
        assert k1["son_sonuc"] == sonuc
        assert (k2["saat"], k2["ders_no"], k2["aktif"]) == ("14:00", 6, False)
        # Taşıma günü aynı derse ikinci otomatik SMS gitmesin
        assert otomasyon.ders_son_tarih(conn, 1) == "2026-10-24"
        # İki kural da silinince yeniden açılışta geri gelmez
        otomasyon.kural_sil(conn, 1)
        otomasyon.kural_sil(conn, 2)
    finally:
        conn.close()
    db.semayi_kur()
    conn = db.baglanti()
    try:
        assert otomasyon.kurallar(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize("saat,ders,sablon,parca", [
    ("9:00", 3, "x", "Saat"),
    ("24:00", 3, "x", "Saat"),
    ("10:30", 0, "x", "Ders numarası"),
    ("10:30", "abc", "x", "Ders numarası"),
    ("10:30", 3, "   ", "boş"),
    ("10:30", 3, "x" * (otomasyon.SABLON_AZAMI + 1), "en çok"),
])
def test_kural_ekle_dogrulama(test_db, saat, ders, sablon, parca):
    with pytest.raises(otomasyon.KuralHatasi, match=parca):
        otomasyon.kural_ekle(test_db, "", saat, ders, sablon)


def test_kural_ekle_kapali_baslar_ve_ayni_derse_ikinci_kural_eklenemez(test_db):
    kid = otomasyon.kural_ekle(test_db, "", "10:30", "3", "Sayın {isim}")
    k = otomasyon.kural_getir(test_db, kid)
    assert (k["ad"], k["saat"], k["ders_no"], k["aktif"]) == ("3. ders", "10:30", 3, False)
    with pytest.raises(otomasyon.KuralHatasi, match="zaten"):
        otomasyon.kural_ekle(test_db, "", "11:00", 3, "x")
    with pytest.raises(otomasyon.KuralHatasi, match="zaten"):
        otomasyon.kural_guncelle(test_db, kid, "", "10:30", 1, "x")  # 1. ders kural 1'de


def test_silinip_yeniden_eklenen_kural_ayni_gun_ikinci_sms_atmaz(test_db, monkeypatch):
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    ogr = db.kisi_ekle(test_db, "Deniz Aras", None, siniflar["9-A"], "ogrenci", okul_no=105)
    db.kisi_ekle(test_db, "Selin Aras", "05329998877", siniflar["9-A"], "veli", ogrenci_kisi_id=ogr, veli_rol="Anne")
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Deniz Aras"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])
    gonderilen = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilen.append(tel)
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)
    otomasyon.otomasyon_calistir(test_db, 1, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25")
    otomasyon.kural_sil(test_db, 1)
    yeni = otomasyon.kural_ekle(test_db, "", "09:05", 1, "Tekrar {isim}")
    sonuc = otomasyon.otomasyon_calistir(test_db, yeni, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25")
    assert sonuc["durum"] == "zaten_calisti"
    assert gonderilen == ["05329998877"]


def test_tetiklenecek_kurallar_pencere_aktiflik_ve_gunluk_tek(test_db):
    from datetime import datetime

    kid = otomasyon.kural_ekle(test_db, "", "10:30", 3, "x")
    def an(s):
        return datetime.fromisoformat(f"2026-09-25T{s}:00")

    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:35")) == []  # kapalı
    otomasyon.kural_aktif_yaz(test_db, kid, True)
    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:29")) == []
    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:30")) == [kid]
    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:40")) == [kid]
    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:41")) == []
    db.ayar_yaz(test_db, otomasyon.ders_son_tarih_anahtari(3), "2026-09-25")
    assert otomasyon.tetiklenecek_kurallar(test_db, an("10:35")) == []


def test_sonraki_ders_kurali_sabah_gelenleri_ayirir_ve_varsayilan_sablon(test_db, monkeypatch):
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    for no, ad in ((301, "Ali Kaya"), (302, "Selin Yılmaz")):
        ogr = db.kisi_ekle(test_db, ad, None, siniflar["9-A"], "ogrenci", okul_no=no)
        db.kisi_ekle(test_db, ad + " Velisi", f"0532000{no}0", siniflar["9-A"], "veli", ogrenci_kisi_id=ogr)
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [
        {"sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Ali Kaya"], "izinli_isimleri": []},
        {"sinif": "9-A", "ders_no": 3, "durum": "alindi", "yok_isimleri": ["Ali Kaya", "Selin Yılmaz"],
         "izinli_isimleri": []},
    ])
    sonuc = otomasyon.devamsizlar_derle(test_db, ders_no=3, tarih="2026-09-25")
    assert sonuc["sabah_gelen_sayisi"] == 1
    assert {o["ad_soyad"]: o["sabah_da_yok"] for o in sonuc["ogrenciler"]} == {"Ali Kaya": True, "Selin Yılmaz": False}
    assert all("3. derse" in s["mesaj"] for s in sonuc["gonderilecek_smsler"])
