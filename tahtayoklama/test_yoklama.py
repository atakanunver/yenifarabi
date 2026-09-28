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

import os
import socket
import sys
import uuid
from pathlib import Path

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
