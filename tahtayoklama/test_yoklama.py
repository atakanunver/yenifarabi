"""tahtayoklama/test_yoklama.py — yoklama.py için pytest testleri.

Ayrı bir geliştirici venv'inde (PyQt6 + pytest kurulu) çalıştırılır, üretim
tahtalarında ÇALIŞMAZ. `QT_QPA_PLATFORM=offscreen` ile ekran gerekmeden
koşar:

    QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tahtayoklama/test_yoklama.py -q

Kapsam (2026-09-28, "yoklama panoda görünmüyor" kök neden düzeltmesi —
ayrıntı kök `DECISIONS.md` 2026-09-28), bu dosya sırayla büyütüldü:
- Tek örnek (single instance) koruması: `_tekil_ornek_sunucusu_baslat`.
- Manuel kayıt dosyayı yazar; dönem geçişi (ders→teneffüs, ders N→N+1)
  HİÇBİR dosyaya otomatik yazmaz/üzerine yazmaz (regresyon testi —
  "çift pencere" ve "teneffüs işaretlemesi" senaryoları).
- Teneffüste kartlar/kaydet düğmesi devre dışı.

Python sürümü NOT: tahtalar Pardus ETAP 23 üzerinde daha eski bir Python
(muhtemelen 3.11) çalıştırıyor — burada 3.10'un ÜSTÜNDE sözdizimi
kullanılmaz (yoklama.py'nin kendisi de zaten `int | None` gibi 3.10+
sözdizimi kullanıyor, bu dosya da onunla aynı çizgide kalır)."""

import json
import os
import socket
import sys
import uuid
from datetime import datetime as _GercekDatetime
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yoklama  # QT_QPA_PLATFORM ayarından SONRA import edilmeli


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _benzersiz_soket_adi() -> str:
    return f"test-yoklama-{uuid.uuid4().hex}"


# ----------------------------------------------------------------------
# Sahte saat + geçici roster/zil ortamı (kayıt testleri için)
# ----------------------------------------------------------------------

ZIL_ORNEGI = {
    "dersler": [
        {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
        {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
    ]
}

ROSTER_ORNEGI = {
    "sinif": "9-A",
    "ogrenciler": [
        {"no": 1, "ad_soyad": "Ali Veli"},
        {"no": 2, "ad_soyad": "Ayşe Yılmaz"},
    ],
}


class _SahteDatetime(_GercekDatetime):
    """`yoklama.datetime`'ı sabit bir saate iğnelemek için — `now()` GERÇEK
    bir `datetime` alt sınıfı döner (strftime/.time() vb. hepsi normal
    çalışır), yalnızca "şu an" testler boyunca sabitlenir."""

    _sabit_an = _GercekDatetime(2026, 9, 28, 8, 20, 0)  # noqa: DTZ001 — yoklama.py da tz-naive kullanıyor

    @classmethod
    def now(cls, tz=None):
        return cls._sabit_an


def _saat_ayarla(saat: int, dakika: int) -> None:
    _SahteDatetime._sabit_an = _GercekDatetime(2026, 9, 28, saat, dakika, 0)  # noqa: DTZ001


@pytest.fixture
def yoklama_ortami(tmp_path, monkeypatch, qapp):
    """Geçici bir veri dizini kurar (roster + zil.json), yoklama.py'nin
    modül sabitlerini (ROSTER_DIR/KAYIT_DIR/ZIL_DOSYASI) buraya
    yönlendirir, QMessageBox'ı sessizleştirir ve saati 1. ders içine
    (08:20) sabitler."""
    roster_dir = tmp_path / "roster"
    kayit_dir = tmp_path / "kayitlar"
    roster_dir.mkdir()
    zil_dosyasi = tmp_path / "zil.json"

    (roster_dir / "9-A.json").write_text(json.dumps(ROSTER_ORNEGI, ensure_ascii=False), encoding="utf-8")
    zil_dosyasi.write_text(json.dumps(ZIL_ORNEGI, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(yoklama, "ROSTER_DIR", roster_dir)
    monkeypatch.setattr(yoklama, "KAYIT_DIR", kayit_dir)
    monkeypatch.setattr(yoklama, "ZIL_DOSYASI", zil_dosyasi)
    # Varsayılan: ders programı YOK (gerçek data/ dosyası testlere sızmasın).
    monkeypatch.setattr(yoklama, "DERS_PROGRAMI_DOSYASI", tmp_path / "ders_programi.json")
    monkeypatch.setattr(yoklama, "KAZANIM_DOSYASI", tmp_path / "kazanimlar.json")
    monkeypatch.setattr(yoklama, "datetime", _SahteDatetime)
    _saat_ayarla(8, 20)

    # QMessageBox.information/warning gerçek pencere açar — testte engelle.
    monkeypatch.setattr(yoklama.QMessageBox, "information", MagicMock())
    monkeypatch.setattr(yoklama.QMessageBox, "warning", MagicMock())

    yield kayit_dir


# ----------------------------------------------------------------------
# Kayıt: manuel kaydet YAZAR, otomatik/dönem geçişi YAZMAZ
# ----------------------------------------------------------------------


class TestOtomatikKayitKaldirildi:
    def test_manuel_kaydet_dosya_yazar(self, yoklama_ortami):
        pencere = yoklama.YoklamaPenceresi()
        try:
            pencere.kaydet_dugmesi.click()
            yol = yoklama._kayit_yolu("9-A", 1, "2026-09-28")
            assert yol.exists()
            kayit = json.loads(yol.read_text(encoding="utf-8"))
            assert kayit["sinif"] == "9-A"
            assert kayit["ders_no"] == 1
            assert kayit["durumlar"] == {"1": "var", "2": "var"}
        finally:
            pencere.close()

    def test_donem_degisimi_ogretmenin_kaydinin_ustune_yazmaz(self, yoklama_ortami):
        """Regresyon (b): öğretmen 1. derste "1 numaralı öğrenci yok"
        işaretleyip kaydeder; ders 2'ye geçildiğinde 1. dersin kayıt
        dosyası DEĞİŞMEMELİ (eskiden _kaydet(sessiz=True) burada dosyanın
        üzerine "herkes var" yazıyordu)."""
        pencere = yoklama.YoklamaPenceresi()
        try:
            pencere._kartlar[0].click()  # var -> yok
            assert pencere._kartlar[0].durum == "yok"
            pencere.kaydet_dugmesi.click()

            yol = yoklama._kayit_yolu("9-A", 1, "2026-09-28")
            once_yazilan = yol.read_bytes()
            assert json.loads(once_yazilan)["durumlar"]["1"] == "yok"

            # Ders 2'ye geç (dönem değişimi) — _periyodik_kontrol'ü elle tetikle.
            _saat_ayarla(9, 5)
            pencere._periyodik_kontrol()

            assert pencere._aktif_ders_no == 2
            # 1. dersin kaydı bayt bayt AYNI kalmalı.
            assert yol.read_bytes() == once_yazilan
            # 2. ders için henüz hiçbir dosya YOK (otomatik yazma yok).
            assert not yoklama._kayit_yolu("9-A", 2, "2026-09-28").exists()
        finally:
            pencere.close()

    def test_derse_teneffuse_gecis_dosya_olusturmaz(self, yoklama_ortami):
        """Regresyon (a)/(b)'nin diğer ucu: ders bitip teneffüse
        girildiğinde de (yeni_ders_no None) hiçbir dosya oluşmamalı."""
        pencere = yoklama.YoklamaPenceresi()
        try:
            pencere._kartlar[1].click()  # var -> yok (kaydedilmeden)

            _saat_ayarla(8, 55)  # 1. ders bitti, 2. ders başlamadı -> teneffüs
            pencere._periyodik_kontrol()

            assert pencere._aktif_ders_no is None
            assert not yoklama._kayit_yolu("9-A", 1, "2026-09-28").exists()
        finally:
            pencere.close()


# ----------------------------------------------------------------------
# Teneffüste giriş devre dışı
# ----------------------------------------------------------------------


class TestTeneffusDevreDisi:
    def test_teneffuste_kartlar_ve_kaydet_devre_disi(self, yoklama_ortami):
        _saat_ayarla(8, 55)  # 1. ders bitti, 2. ders başlamadı -> teneffüs
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere._aktif_ders_no is None
            assert pencere.kaydet_dugmesi.isEnabled() is False
            for kart in pencere._kartlar:
                assert kart.isEnabled() is False
            # Devre dışı bir düğmede .click() hiçbir şey tetiklemez (Qt).
            durum_once = pencere._kartlar[0].durum
            pencere._kartlar[0].click()
            assert pencere._kartlar[0].durum == durum_once
            pencere.kaydet_dugmesi.click()
            assert not yoklama._kayit_yolu("9-A", 1, "2026-09-28").exists()
        finally:
            pencere.close()

    def test_ders_baslayinca_yeniden_etkinlesir(self, yoklama_ortami):
        _saat_ayarla(8, 55)  # teneffüs
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.kaydet_dugmesi.isEnabled() is False

            _saat_ayarla(9, 5)  # 2. ders
            pencere._periyodik_kontrol()

            assert pencere._aktif_ders_no == 2
            assert pencere.kaydet_dugmesi.isEnabled() is True
            for kart in pencere._kartlar:
                assert kart.isEnabled() is True
            # Artık gerçekten tıklanabilir/kaydedilebilir.
            pencere.kaydet_dugmesi.click()
            assert yoklama._kayit_yolu("9-A", 2, "2026-09-28").exists()
        finally:
            pencere.close()

    def test_acilista_ders_icindeyse_etkin(self, yoklama_ortami):
        """Başlangıçta (08:20, 1. ders) doğrudan etkin olmalı."""
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.kaydet_dugmesi.isEnabled() is True
            for kart in pencere._kartlar:
                assert kart.isEnabled() is True
        finally:
            pencere.close()

    def test_sinif_degisince_de_dogru_durum(self, yoklama_ortami):
        """Sınıf (combobox) değiştirildiğinde de giriş durumu güncellenmeli
        (bkz. _sinif_degisti -> _ders_grubunu_yukle)."""
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.kaydet_dugmesi.isEnabled() is True
            _saat_ayarla(8, 55)  # teneffüs
            pencere._sinif_degisti()
            assert pencere.kaydet_dugmesi.isEnabled() is False
        finally:
            pencere.close()


# ----------------------------------------------------------------------
# Tek örnek (single instance) koruması
# ----------------------------------------------------------------------


class TestTekilOrnek:
    def test_ilk_ornek_dinlemeye_baslar(self, qapp):
        adi = _benzersiz_soket_adi()
        sunucu, cikilmali = yoklama._tekil_ornek_sunucusu_baslat(adi)
        try:
            assert cikilmali is False
            assert sunucu is not None
            assert sunucu.isListening()
        finally:
            if sunucu is not None:
                sunucu.close()
            QLocalServer.removeServer(adi)

    def test_ikinci_ornek_ilkine_mesaj_gonderir_ve_cikmali_olur(self, qapp):
        adi = _benzersiz_soket_adi()
        sunucu1, cikilmali1 = yoklama._tekil_ornek_sunucusu_baslat(adi)
        assert cikilmali1 is False
        baglanti_geldi = []
        sunucu1.newConnection.connect(lambda: baglanti_geldi.append(True))
        try:
            sunucu2, cikilmali2 = yoklama._tekil_ornek_sunucusu_baslat(adi)
            assert cikilmali2 is True
            assert sunucu2 is None

            for _ in range(50):
                qapp.processEvents()
                if baglanti_geldi:
                    break
            assert baglanti_geldi, "ilk örnek ikinci örneğin bağlantısını hiç almadı"
        finally:
            sunucu1.close()
            QLocalServer.removeServer(adi)

    def test_kalintili_soket_temizlenir_ve_yeniden_dinlenir(self, qapp):
        adi = _benzersiz_soket_adi()
        # Gerçek soket dosyasının tam yolunu öğrenmek için bir prob sunucu
        # aç/kapat (temiz kapanış kendi dosyasını siler, sadece yol bilgisi
        # kalır).
        prob = QLocalServer()
        assert prob.listen(adi)
        yol = prob.fullServerName()
        prob.close()

        # Kalıntı (çökmüş önceki örnek) senaryosunu simüle et: ham bir
        # AF_UNIX soketi o path'e bind et, UNLINK ETMEDEN kapat — dosya
        # diskte kalır ama arkasında dinleyen kimse yok.
        ham = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ham.bind(yol)
        ham.close()
        assert Path(yol).exists()

        sunucu, cikilmali = yoklama._tekil_ornek_sunucusu_baslat(adi)
        try:
            assert cikilmali is False
            assert sunucu is not None
            assert sunucu.isListening()
        finally:
            if sunucu is not None:
                sunucu.close()
            QLocalServer.removeServer(adi)
            Path(yol).unlink(missing_ok=True)

    def test_ikinci_ornek_pencere_olusturmaz(self, qapp, monkeypatch):
        """main()'in kendisi: cikilmali=True dönerse YoklamaPenceresi HİÇ
        oluşturulmamalı."""
        adi = _benzersiz_soket_adi()
        sunucu1, _ = yoklama._tekil_ornek_sunucusu_baslat(adi)
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(yoklama, "_tekil_ornek_sunucusu_baslat", lambda *a, **k: (None, True))
                olusturuldu = []
                gercek_sinif = yoklama.YoklamaPenceresi

                class _Casus(gercek_sinif):
                    def __init__(self, *a, **k):
                        olusturuldu.append(True)
                        super().__init__(*a, **k)

                mp.setattr(yoklama, "YoklamaPenceresi", _Casus)
                mp.setattr(yoklama.sys, "argv", ["yoklama.py"])
                # QApplication zaten (qapp fixture'ıyla) var — main() kendi
                # QApplication(sys.argv) çağrısını yapınca PyQt6 "already
                # exists" hatası vermesin diye var olan örneği döndürüyoruz.
                mp.setattr(yoklama, "QApplication", lambda *a, **k: qapp)
                sonuc = yoklama.main()
                assert sonuc == 0
                assert olusturuldu == []
        finally:
            sunucu1.close()
            QLocalServer.removeServer(adi)


# ----------------------------------------------------------------------
# Başlık: ders adı (data/ders_programi.json) ve ders dışı "BOŞ" (2026-10-06)
# ----------------------------------------------------------------------


def _program_yaz(tmp_path, icerik) -> None:
    (tmp_path / "ders_programi.json").write_text(
        icerik if isinstance(icerik, str) else json.dumps(icerik, ensure_ascii=False),
        encoding="utf-8",
    )


class TestBaslikDersAdi:
    # 2026-09-28 Pazartesi; fixture saati 08:20 = 1. ders, sınıf 9-A.
    PROGRAM = {"siniflar": {"9-A": {"pazartesi": {"1": "ingilizce", "3": "din kültürü ve ahlak bilgisi"}}}}

    def test_ders_adi_turkce_buyuk_harfle_gorunur(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.baslik_etiketi.text() == "YOKLAMA — 1. DERS · İNGİLİZCE"
        finally:
            pencere.close()

    def test_programda_bos_ders_BOS_yazar(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        _saat_ayarla(9, 10)  # 2. ders — programda yok
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.baslik_etiketi.text() == "YOKLAMA — 2. DERS · BOŞ"
        finally:
            pencere.close()

    def test_ders_saati_disi_BOS(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        _saat_ayarla(8, 55)  # teneffüs
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.baslik_etiketi.text() == "YOKLAMA — BOŞ"
        finally:
            pencere.close()

    def test_program_yoksa_yalnizca_ders_no(self, yoklama_ortami):
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.baslik_etiketi.text() == "YOKLAMA — 1. DERS"
        finally:
            pencere.close()

    def test_bozuk_program_cokertmez(self, yoklama_ortami, tmp_path):
        for bozuk in ("{bozuk", "[]", json.dumps({"siniflar": []}),
                      json.dumps({"siniflar": {"9-A": {"pazartesi": ["x"]}}})):
            _program_yaz(tmp_path, bozuk)
            pencere = yoklama.YoklamaPenceresi()
            try:
                assert pencere.baslik_etiketi.text() == "YOKLAMA — 1. DERS"
            finally:
                pencere.close()

    def test_ders_adi_fonksiyonu_hafta_sonu_none(self):
        assert yoklama._ders_adi(self.PROGRAM, "9-A", 6, 1) is None
        assert yoklama._ders_adi(self.PROGRAM, "9-A", 1, 3) == "DİN KÜLTÜRÜ VE AHLAK BİLGİSİ"


# ----------------------------------------------------------------------
# Kazanım satırı (data/kazanimlar.json, 2026-10-06)
# ----------------------------------------------------------------------


class TestKazanimSatiri:
    PROGRAM = TestBaslikDersAdi.PROGRAM
    # 2026-09-28 Pazartesi = plan haftası 3 (pazartesisi 2026-09-28).
    KAZANIM = {
        "haftalar": {"2": "2026-09-21", "3": "2026-09-28"},
        "kazanimlar": {"9": {"ingilizce": {"3": "E9.1.L1. Students will be able to...",
                                            "2": "geçen hafta"}}},
    }

    def _kazanim_yaz(self, tmp_path, icerik):
        (tmp_path / "kazanimlar.json").write_text(
            icerik if isinstance(icerik, str) else json.dumps(icerik, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_bu_haftanin_kazanimi_gorunur(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        self._kazanim_yaz(tmp_path, self.KAZANIM)
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere._kazanim_metni == "E9.1.L1. Students will be able to..."
            assert pencere.kazanim_etiketi.text() == "Kazanım: E9.1.L1. Students will be able to..."
            assert not pencere.kazanim_etiketi.isHidden()
        finally:
            pencere.close()

    def test_ders_disi_ve_kazanim_yoksa_satir_gizli(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        self._kazanim_yaz(tmp_path, self.KAZANIM)
        _saat_ayarla(8, 55)  # teneffüs
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere._kazanim_metni == ""
            assert pencere.kazanim_etiketi.isHidden()
        finally:
            pencere.close()

    def test_bozuk_kazanim_dosyasi_cokertmez(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        for bozuk in ("{bozuk", "[]", json.dumps({"haftalar": {"3": "tarih-degil"}}),
                      json.dumps({"haftalar": [], "kazanimlar": {"9": []}})):
            self._kazanim_yaz(tmp_path, bozuk)
            pencere = yoklama.YoklamaPenceresi()
            try:
                assert pencere._kazanim_metni == ""
                assert pencere.baslik_etiketi.text() == "YOKLAMA — 1. DERS · İNGİLİZCE"
            finally:
                pencere.close()

    def test_kazanim_fonksiyonu_hafta_secimi(self):
        from datetime import date
        k = self.KAZANIM
        assert yoklama._kazanim(k, "9-A", "ingilizce", date(2026, 9, 25)) == "geçen hafta"
        assert yoklama._kazanim(k, "9-A", "ingilizce", date(2026, 10, 4)) == "E9.1.L1. Students will be able to..."
        assert yoklama._kazanim(k, "9-A", "ingilizce", date(2026, 10, 5)) is None  # plan haftası yok
        assert yoklama._kazanim(k, "10-A", "ingilizce", date(2026, 9, 28)) is None  # düzey yok
        assert yoklama._kazanim(k, "9-A", "", date(2026, 9, 28)) is None  # boş ders

    def test_haftada_iki_kazanim_iki_satir(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        k = json.loads(json.dumps(self.KAZANIM))
        k["kazanimlar"]["9"]["ingilizce"]["3"] = "9.1.1. Birinci\n9.1.2. İkinci"
        self._kazanim_yaz(tmp_path, k)
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.kazanim_etiketi.text() == "Kazanım: 9.1.1. Birinci\nKazanım: 9.1.2. İkinci"
        finally:
            pencere.close()

    def test_uc_kazanimda_ikinci_satir_arti_sayisi(self, yoklama_ortami, tmp_path):
        _program_yaz(tmp_path, self.PROGRAM)
        k = json.loads(json.dumps(self.KAZANIM))
        k["kazanimlar"]["9"]["ingilizce"]["3"] = "A\nB\nC"
        self._kazanim_yaz(tmp_path, k)
        pencere = yoklama.YoklamaPenceresi()
        try:
            assert pencere.kazanim_etiketi.text() == "Kazanım: A\nKazanım: B (+1)"
        finally:
            pencere.close()
