"""
Ders motoru — dersin akışını kod yürütür, model değil.

Motorun tek işi deterministik olmak, o yüzden testleri de deterministik:
saat dışarıdan verilir, zil çizelgesi yamalanır.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ders_motoru as dm          # noqa: E402
from core.ders_motoru import DersMotoru     # noqa: E402


@pytest.fixture
def motor():
    return DersMotoru(kip="ogretmenli", cerceve={"subject": "Fizik",
                                                 "topic": "Sabit Hızlı Hareket",
                                                 "kazanim_kodu": "FİZ.10.1.1"},
                      sinif="10-A")


def _zil_yamala(monkeypatch, **durum):
    monkeypatch.setattr(dm.zil, "ders_durumu", lambda simdi=None: durum)


class TestAdimlar:
    def test_baslangicta_bekliyor(self, motor):
        assert motor.durum.adim == dm.BEKLIYOR

    def test_zil_calinca_yoklamaya_gecer(self, motor, monkeypatch):
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=35)
        motor.guncelle(datetime(2025, 10, 7, 10, 0))
        assert motor.durum.adim == dm.YOKLAMA
        assert motor.durum.kalan_dk == 35

    def test_teneffuste_ders_biter(self, motor, monkeypatch):
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=20)
        motor.guncelle()
        motor.gec(dm.ANLATIM)
        _zil_yamala(monkeypatch, tur="teneffus", ders_no=4, kalan_dk=None)
        motor.guncelle()
        assert motor.durum.adim == dm.BITTI

    def test_ilerle_sirayi_takip_eder(self, motor):
        motor.gec(dm.ANLATIM)
        motor.ilerle()
        assert motor.durum.adim == dm.REHBERLI_ALISTIRMA

    def test_tamamlanan_adimlar_biriktirilir(self, motor):
        motor.gec(dm.YOKLAMA)
        motor.gec(dm.ISINMA)
        motor.gec(dm.ANLATIM)
        assert motor.durum.tamamlanan_adimlar == [dm.YOKLAMA, dm.ISINMA]

    def test_bilinmeyen_adim_reddedilir(self, motor):
        with pytest.raises(ValueError):
            motor.gec("SOHBET")


class TestOneriler:
    def test_sure_bitince_ozet_onerilir(self, motor, monkeypatch):
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=5)
        motor.gec(dm.ANLATIM)
        motor.guncelle()
        assert motor.oneri()["eylem"] == "ADIM_OZET"

    def test_ozet_adimindayken_tekrar_onerilmez(self, motor, monkeypatch):
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=5)
        motor.gec(dm.OZET)
        motor.guncelle()
        assert motor.oneri() is None

    def test_dusuk_kontrol_orani_farkli_anlatim_getirir(self, motor, monkeypatch):
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=30)
        motor.gec(dm.ANLATIM)
        motor.guncelle()
        motor.kontrol_sonucu(dogru=1, toplam=6)
        assert motor.oneri()["eylem"] == "FARKLI_ANLATIM"

    def test_ogretmen_mudahalesi_her_seyi_yener(self, motor, monkeypatch):
        # Öğretmen araya girdiğinde motor öneri üretmez; sınıfın sahibi odur.
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=2)
        motor.gec(dm.ANLATIM)
        motor.guncelle()
        motor.mudahale(True)
        assert motor.oneri()["eylem"] == "DURAKLAT"


class TestEnjeksiyon:
    def test_gozlemci_kipinde_oturuma_hicbir_sey_gitmez(self, motor):
        motor.gec(dm.ANLATIM)
        assert motor.enjeksiyon_metni() is None

    def test_enjeksiyon_acikken_metin_uretilir(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=25)
        m.guncelle()
        metin = m.enjeksiyon_metni()
        assert metin and "[DERS DURUMU]" in metin and "25 dakika" in metin

    def test_ayni_durum_iki_kez_gonderilmez(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=25)
        m.guncelle()
        assert m.enjeksiyon_metni() is not None
        assert m.enjeksiyon_metni() is None      # değişmedi


class TestMudahaleSuresi:
    """
    Müdahale bayrağı SÜRELİ olmalı: paneldeki "devam et" düğmesi kaldırıldı,
    bayrağı elle indirecek bir denetim kalmadı. Kilitli kalırsa motor dersin
    geri kalanında hiç öneri üretmez.
    """

    def test_sure_dolunca_kendiliginden_kalkar(self, motor, monkeypatch):
        from datetime import timedelta
        t0 = datetime(2025, 11, 6, 10, 0)
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=5)
        motor.gec(dm.ANLATIM)
        motor.mudahale(True, simdi=t0)
        assert motor.durum.ogretmen_mudahalesi

        motor.guncelle(t0 + timedelta(minutes=dm.MUDAHALE_SURESI_DK + 1))
        assert not motor.durum.ogretmen_mudahalesi
        # bayrak kalkınca kural motoru yeniden konuşur
        assert motor.oneri()["eylem"] == "ADIM_OZET"

    def test_sure_dolmadan_susmaya_devam_eder(self, motor, monkeypatch):
        from datetime import timedelta
        t0 = datetime(2025, 11, 6, 10, 0)
        _zil_yamala(monkeypatch, tur="ders", ders_no=3, kalan_dk=5)
        motor.gec(dm.ANLATIM)
        motor.mudahale(True, simdi=t0)
        motor.guncelle(t0 + timedelta(minutes=1))
        assert motor.oneri()["eylem"] == "DURAKLAT"


class TestEnjeksiyonSikligi:
    """
    Bildirim SIK OLMAMALI. Kalan dakika her dakika değişiyor; imzaya girdiği
    için modele dakikada bir mesaj gidiyordu ve oturum sürekli "yeni girdi"
    durumundaydı. Haber yalnız adım değişince ve süre eşiği geçilince gider.
    """

    def test_dakika_degisimi_tek_basina_haber_uretmez(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=30)
        m.guncelle()
        assert m.enjeksiyon_metni() is not None      # ilk durum
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=29)
        m.guncelle()
        assert m.enjeksiyon_metni() is None          # yalnız dakika değişti

    def test_sure_esigi_gecilince_haber_gider(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=30)
        m.guncelle(); m.enjeksiyon_metni()
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=9)
        m.guncelle()
        metin = m.enjeksiyon_metni()
        assert metin and "9 dakika" in metin

    def test_haber_selamlamayi_yasaklar(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=25)
        m.guncelle()
        assert "selamlama yapma" in m.enjeksiyon_metni().lower()

    def test_duraklatilmisken_haber_gitmez(self, monkeypatch):
        m = DersMotoru(enjekte=True)
        _zil_yamala(monkeypatch, tur="ders", ders_no=1, kalan_dk=25)
        m.guncelle()
        m.duraklat(True)
        assert m.enjeksiyon_metni() is None
