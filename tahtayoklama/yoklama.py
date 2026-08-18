"""
tahtayoklama/yoklama.py — Dokunmatik akıllı tahta yoklama arayüzü.

Farabi'den TAMAMEN BAĞIMSIZ, ayrı bir program (2026-08-18, kullanıcı kararı):
Farabi'nin actions/registry'sine hiç girmez, `client/`'a bağlı değildir,
kendi başına çalışır. Farabi'nin sesli yoklaması ("Arkadaşlar, derse
gelmeyen öğrencilerin isimlerini söyler misiniz?" — core/prompt.txt) bu
sistemden habersizdir ve DEĞİŞMEDİ; ikisi paralel, birbirinden bağımsız
iki yoklama yoludur.

Kiosk kilitleme YOK (kullanıcı kararı, 2026-08-18) — pencere normal, kapatılabilir,
tam ekran isteğe bağlı bir buton. Önceki bir taslakta önerilen Windows
Kiosk Mode / Assigned Access tavsiyeleri bu projeye uymuyordu (tahtalar
Linux — kök CLAUDE.md), o yüzden hiç uygulanmadı.

VERİ MODELİ:
- Sınıf listesi (roster): `data/roster/<sinif>.json` — {"sinif": "9-A",
  "ogrenciler": [{"no": 1, "ad_soyad": "..."}, ...]}. Kaynak: okulun
  e-Okul/MEB PDF çıktısı, `pdf_disari_aktar.py` ile bu JSON'a çevrilir
  (elle de yazılabilir, aynı şema).
- Yoklama kaydı: her "Kaydet" basışında `data/kayitlar/<tarih>_<sinif>.json`
  yazılır — o günün son durumu üzerine yazılır (aynı gün tekrar kaydedilirse
  güncellenir, çoğalmaz).

DURUM: üç hâlli — var (yeşil) → yok (kırmızı) → izinli (gri) → var — her
dokunuşta döner. Varsayılan hepsi "var" (istisnaları işaretlemek, herkesi
tek tek işaretlemekten daha hızlı).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent
ROSTER_DIR = BASE_DIR / "data" / "roster"
KAYIT_DIR = BASE_DIR / "data" / "kayitlar"

DURUM_SIRASI = ["var", "yok", "izinli"]
DURUM_RENK = {
    "var": "#2ecc71",
    "yok": "#e74c3c",
    "izinli": "#7f8c8d",
}
DURUM_ETIKET = {
    "var": "VAR",
    "yok": "YOK",
    "izinli": "İZİNLİ",
}

# Dokunmatik hedef boyutu — parmakla yanlış tuşa basmayı önlemek için.
KART_MIN_YUKSEKLIK = 90
KART_FONT_PT = 20


def _roster_listesi() -> list[str]:
    """data/roster/ altındaki sınıf dosyalarının adları (uzantısız)."""
    if not ROSTER_DIR.exists():
        return []
    return sorted(p.stem for p in ROSTER_DIR.glob("*.json"))


def _roster_yukle(sinif: str) -> list[dict]:
    yol = ROSTER_DIR / f"{sinif}.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return veri.get("ogrenciler", [])


class OgrenciKarti(QPushButton):
    """Bir öğrencinin dokunmatik yoklama kartı — üç hâl arasında döner."""

    def __init__(self, ogrenci: dict):
        super().__init__()
        self.no = ogrenci["no"]
        self.ad_soyad = ogrenci["ad_soyad"]
        self.durum = "var"
        self.setMinimumHeight(KART_MIN_YUKSEKLIK)
        self.clicked.connect(self._sonraki_duruma_gec)
        self._guncelle()

    def _sonraki_duruma_gec(self) -> None:
        i = DURUM_SIRASI.index(self.durum)
        self.durum = DURUM_SIRASI[(i + 1) % len(DURUM_SIRASI)]
        self._guncelle()

    def _guncelle(self) -> None:
        self.setText(f"{self.no}. {self.ad_soyad}\n[ {DURUM_ETIKET[self.durum]} ]")
        self.setStyleSheet(
            f"font-size: {KART_FONT_PT}pt; font-weight: bold; color: white; "
            f"background-color: {DURUM_RENK[self.durum]}; "
            f"border-radius: 12px; padding: 10px;"
        )


class YoklamaPenceresi(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Yoklama")
        self._tam_ekran = False
        self._kartlar: list[OgrenciKarti] = []
        self._kur_arayuz()
        self._sinif_degisti()
        self.resize(1000, 700)

    def _kur_arayuz(self) -> None:
        ana = QVBoxLayout(self)

        ust = QHBoxLayout()
        baslik = QLabel("YOKLAMA")
        baslik.setStyleSheet("font-size: 26pt; font-weight: bold;")
        ust.addWidget(baslik)

        ust.addStretch()

        ust.addWidget(QLabel("Sınıf:"))
        self.sinif_secici = QComboBox()
        self.sinif_secici.setMinimumHeight(50)
        self.sinif_secici.setStyleSheet("font-size: 16pt;")
        self.sinif_secici.addItems(_roster_listesi())
        self.sinif_secici.currentTextChanged.connect(self._sinif_degisti)
        ust.addWidget(self.sinif_secici)

        self.tam_ekran_dugmesi = QPushButton("⛶ Tam Ekran")
        self.tam_ekran_dugmesi.setMinimumSize(140, 50)
        self.tam_ekran_dugmesi.setStyleSheet("font-size: 14pt;")
        self.tam_ekran_dugmesi.clicked.connect(self._tam_ekrani_degistir)
        ust.addWidget(self.tam_ekran_dugmesi)

        ana.addLayout(ust)

        self.ozet_etiketi = QLabel()
        self.ozet_etiketi.setStyleSheet("font-size: 16pt; color: #ccc;")
        ana.addWidget(self.ozet_etiketi)

        self.izgara = QGridLayout()
        self.izgara.setSpacing(12)
        icerik = QWidget()
        icerik.setLayout(self.izgara)
        kaydirma = QScrollArea()
        kaydirma.setWidgetResizable(True)
        kaydirma.setWidget(icerik)
        ana.addWidget(kaydirma, stretch=1)

        kaydet = QPushButton("YOKLAMAYI KAYDET")
        kaydet.setMinimumHeight(70)
        kaydet.setStyleSheet(
            "font-size: 20pt; font-weight: bold; color: white; "
            "background-color: #2980b9; border-radius: 12px;"
        )
        kaydet.clicked.connect(self._kaydet)
        ana.addWidget(kaydet)

    def _sinif_degisti(self, *_args) -> None:
        sinif = self.sinif_secici.currentText()
        for i in reversed(range(self.izgara.count())):
            self.izgara.itemAt(i).widget().setParent(None)
        self._kartlar = []

        if not sinif:
            self.ozet_etiketi.setText(
                f"'{ROSTER_DIR}' altında sınıf listesi bulunamadı — "
                f"önce pdf_disari_aktar.py ile bir roster oluşturun."
            )
            return

        ogrenciler = _roster_yukle(sinif)
        SUTUN = 3
        for idx, ogrenci in enumerate(ogrenciler):
            kart = OgrenciKarti(ogrenci)
            kart.clicked.connect(self._ozeti_guncelle)
            self._kartlar.append(kart)
            self.izgara.addWidget(kart, idx // SUTUN, idx % SUTUN)
        self._ozeti_guncelle()

    def _ozeti_guncelle(self) -> None:
        toplam = len(self._kartlar)
        var = sum(1 for k in self._kartlar if k.durum == "var")
        yok = sum(1 for k in self._kartlar if k.durum == "yok")
        izinli = sum(1 for k in self._kartlar if k.durum == "izinli")
        self.ozet_etiketi.setText(
            f"Toplam: {toplam} · Var: {var} · Yok: {yok} · İzinli: {izinli}"
        )

    def _tam_ekrani_degistir(self) -> None:
        self._tam_ekran = not self._tam_ekran
        if self._tam_ekran:
            self.showFullScreen()
            self.tam_ekran_dugmesi.setText("⛶ Pencereye Dön")
        else:
            self.showNormal()
            self.tam_ekran_dugmesi.setText("⛶ Tam Ekran")

    def _kaydet(self) -> None:
        sinif = self.sinif_secici.currentText()
        if not sinif or not self._kartlar:
            return
        KAYIT_DIR.mkdir(parents=True, exist_ok=True)
        tarih = datetime.now().strftime("%Y-%m-%d")
        kayit = {
            "sinif": sinif,
            "tarih": tarih,
            "kaydedilme_saati": datetime.now().strftime("%H:%M:%S"),
            "durumlar": {str(k.no): k.durum for k in self._kartlar},
        }
        yol = KAYIT_DIR / f"{tarih}_{sinif}.json"
        yol.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "Kaydedildi", f"Yoklama kaydedildi:\n{yol.name}")


def main() -> int:
    app = QApplication(sys.argv)
    pencere = YoklamaPenceresi()
    pencere.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
