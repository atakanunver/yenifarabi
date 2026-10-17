"""acil_alarm.py — tahta masaüstündeki "ACİL ALARM" simgesi (2026-10-16).

3 sn basılı tut → ekrandan PIN → Farabi'ye POST /api/acil/tahta-alarm. Kimlik
tahta_istemci.py'nin istemci.json'undaki token; PIN tahtada saklanmaz, sunucu
doğrular. Sunucu: konumlu SMS (tüm personel) + kilit-kapı (zil + tüm tahtalar).
Çalıştırma: ~/tahtayoklama/venv/bin/python3 ~/tahtayoklama/acil_alarm.py
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

AYAR_DOSYASI = Path(__file__).resolve().parent / "istemci.json"
BASILI_TUT_MS = 3000
KENDILIGINDEN_KAPAN_MS = 90_000

STIL = """
QWidget { background: #1a0006; color: white; font-family: Arial; }
QPushButton { background: #333; border: 0; border-radius: 12px; font-size: 34px; min-height: 90px; }
QPushButton#alarm { background: #c00020; font-size: 40px; font-weight: bold; min-height: 260px; }
QPushButton#gonder { background: #c00020; font-weight: bold; }
QPushButton#vazgec { background: #444; font-size: 24px; min-height: 60px; }
QLabel { font-size: 26px; }
QLabel#pin { font-size: 48px; letter-spacing: 12px; }
QProgressBar { min-height: 26px; border-radius: 8px; background: #333; }
QProgressBar::chunk { background: #ff4d4d; border-radius: 8px; }
"""


def alarm_gonder(pin: str) -> tuple[bool, str]:
    try:
        ayar = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
        istek = urllib.request.Request(
            ayar["sunucu"].rstrip("/") + "/api/acil/tahta-alarm",
            data=json.dumps({"pin": pin}).encode(),
            headers={
                "Authorization": f"Bearer {ayar['token']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        acici = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )  # LAN, proxy yok
        with acici.open(istek, timeout=25) as yanit:
            veri = json.loads(yanit.read())
        ek = " (TATBİKAT)" if veri.get("tatbikat") else ""
        return True, "ALARM İLETİLDİ" + ek + "\nKapıyı kilitleyin, sessiz kalın."
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return False, "PIN hatalı."
        if e.code == 429:
            return False, "Çok fazla yanlış PIN.\n10 dakika bekleyin."
        return (
            False,
            f"Sunucu hatası ({e.code}).\nHemen 112'yi arayın, idareye haber verin.",
        )
    except Exception:
        return False, "Sunucuya ulaşılamadı!\nHemen 112'yi arayın, idareye haber verin."


class Pencere(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ACİL ALARM")
        self.setStyleSheet(STIL)
        self.pin = ""
        self.yerlesim = QVBoxLayout(self)
        self.yerlesim.setContentsMargins(40, 30, 40, 30)
        self.yerlesim.setSpacing(16)
        self.gecen_ms = 0
        self.zamanlayici = QTimer(self, interval=50, timeout=self._ilerle)
        QTimer.singleShot(KENDILIGINDEN_KAPAN_MS, self.close)
        self._basili_tut_ekrani()

    def _temizle(self):
        while self.yerlesim.count():
            w = self.yerlesim.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _vazgec_ekle(self):
        b = QPushButton("Vazgeç / Kapat", objectName="vazgec")
        b.clicked.connect(self.close)
        self.yerlesim.addWidget(b)

    def _basili_tut_ekrani(self):
        self._temizle()
        bilgi = QLabel(
            "Tehlike varsa düğmeye 3 saniye BASILI TUTUN.\n"
            "Okul genelinde kilit-kapı başlar ve tüm personele SMS gider."
        )
        bilgi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alarm = QPushButton("ACİL ALARM", objectName="alarm")
        self.alarm.pressed.connect(self._basladi)
        self.alarm.released.connect(self._birakildi)
        self.ilerleme = QProgressBar(maximum=BASILI_TUT_MS, textVisible=False)
        for w in (bilgi, self.alarm, self.ilerleme):
            self.yerlesim.addWidget(w)
        self._vazgec_ekle()

    def _basladi(self):
        self.gecen_ms = 0
        self.zamanlayici.start()

    def _birakildi(self):
        self.zamanlayici.stop()
        if self.gecen_ms < BASILI_TUT_MS:
            self.ilerleme.setValue(0)

    def _ilerle(self):
        self.gecen_ms += 50
        self.ilerleme.setValue(self.gecen_ms)
        if self.gecen_ms >= BASILI_TUT_MS:
            self.zamanlayici.stop()
            self._pin_ekrani()

    def _pin_ekrani(self, mesaj: str = "Öğretmen PIN'ini girin"):
        self._temizle()
        self.pin = ""
        self.mesaj = QLabel(mesaj, alignment=Qt.AlignmentFlag.AlignCenter)
        self.pin_etiket = QLabel(
            "", objectName="pin", alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.yerlesim.addWidget(self.mesaj)
        self.yerlesim.addWidget(self.pin_etiket)
        tus_kutusu = QWidget()
        izgara = QGridLayout(tus_kutusu)
        tuslar = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "GÖNDER"]
        for i, t in enumerate(tuslar):
            b = QPushButton(t, objectName="gonder" if t == "GÖNDER" else "")
            b.clicked.connect(lambda _=False, t=t: self._tus(t))
            izgara.addWidget(b, i // 3, i % 3)
        self.yerlesim.addWidget(tus_kutusu)
        self._vazgec_ekle()

    def _tus(self, t: str):
        if t == "Sil":
            self.pin = self.pin[:-1]
        elif t == "GÖNDER":
            if not self.pin:
                return
            self.mesaj.setText("Gönderiliyor…")
            QApplication.processEvents()
            basarili, metin = alarm_gonder(self.pin)
            if basarili:
                self._sonuc_ekrani(metin)
            else:
                self._pin_ekrani(metin)
            return
        elif len(self.pin) < 8:
            self.pin += t
        self.pin_etiket.setText("●" * len(self.pin))

    def _sonuc_ekrani(self, metin: str):
        self._temizle()
        etiket = QLabel(metin, alignment=Qt.AlignmentFlag.AlignCenter)
        etiket.setStyleSheet("font-size: 40px; font-weight: bold;")
        self.yerlesim.addWidget(etiket)
        self._vazgec_ekle()
        QTimer.singleShot(8000, self.close)


def main() -> int:
    uygulama = QApplication(sys.argv)
    p = Pencere()
    p.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    p.showFullScreen()
    return uygulama.exec()


if __name__ == "__main__":
    sys.exit(main())
