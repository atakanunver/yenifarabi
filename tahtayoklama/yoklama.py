"""
tahtayoklama/yoklama.py — Dokunmatik akıllı tahta yoklama arayüzü.

Farabi'den TAMAMEN BAĞIMSIZ, ayrı bir program (2026-08-18, kullanıcı kararı):
Farabi'nin actions/registry'sine hiç girmez, `client/`'a bağlı değildir,
kendi başına çalışır. Farabi'nin sesli yoklaması ("Arkadaşlar, derse
gelmeyen öğrencilerin isimlerini söyler misiniz?" — core/prompt.txt) bu
sistemden habersizdir ve DEĞİŞMEDİ; ikisi paralel, birbirinden bağımsız
iki yoklama yoludur.

Kiosk kilitleme YOK (kullanıcı kararı, 2026-08-18) — pencere normal,
kapatılabilir. **Ama doğrudan TAM EKRAN açılır** (2026-08-19, gerçek tahta
testi sonrası) — öğretmen elle "Tam Ekran"a basmak zorunda kalmasın diye.

GÜNCELLEME (2026-08-19, gerçek tahta testi sonrası):
- **4 sütun** ızgara — 20 öğrenci tam ekrana sığıyor (önceden 3'tü).
- **Ders saatine göre otomatik dönem tespiti**: `data/zil.json` (Farabi'nin
  `client/config/zil.json`'undan BAĞIMSIZ bir kopya — bu tahtalarda Farabi
  hiç kurulu olmayabilir, bkz. o dosyanın açıklaması) okunur, o anki saate
  göre "kaçıncı derste olduğumuz" bulunur (`_simdiki_ders`). "08:30 → 1.
  ders", "08:40 → hâlâ 1. ders (öğrenci geç gelmiş olabilir)" gibi —
  ölçüt basitçe "şu an hangi dersin [başlangıç, bitiş) aralığındayız".
- **Kayıt artık DERS BAZLI**: `data/kayitlar/<tarih>_<sinif>_ders<no>.json`
  — bir günde en fazla 8 kayıt (bir tanesi her ders saati için). Dönem
  değiştiğinde önceki dersin ekrandaki hâli KAYBOLMASIN diye otomatik
  kaydedilir (öğretmen "Kaydet"e basmayı unutsa bile).
- **10 dakika kuralı**: bir ders başladıktan 10 dakika sonra hâlâ o ders
  için kayıt yoksa, pencere öne getirilir (`raise_`/`activateWindow`) —
  30 saniyede bir çalışan bir zamanlayıcıyla kontrol edilir.

VERİ MODELİ:
- Sınıf listesi (roster): `data/roster/<sinif>.json` — {"sinif": "9-A",
  "ogrenciler": [{"no": 1, "ad_soyad": "..."}, ...]}. Kaynak: okulun
  e-Okul/MEB PDF çıktısı, `pdf_disari_aktar.py` ile bu JSON'a çevrilir
  (elle de yazılabilir, aynı şema).
- Yoklama kaydı: `data/kayitlar/<tarih>_<sinif>_ders<no>.json`.

DURUM: üç hâlli — var (yeşil) → yok (kırmızı) → izinli (gri) → var — her
dokunuşta döner. Varsayılan hepsi "var" (istisnaları işaretlemek, herkesi
tek tek işaretlemekten daha hızlı).
"""

import json
import sys
from datetime import datetime, time as dtime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
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
ZIL_DOSYASI = BASE_DIR / "data" / "zil.json"

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
SUTUN = 4

# Bir ders başladıktan sonra bu kadar dakika geçtiyse ve hâlâ kayıt yoksa
# pencere öne getirilir.
UYARI_ESIGI_DK = 10
# Periyodik kontrol aralığı (saniye) — dönem değişimini/10dk eşiğini yakalamak
# için 30sn yeterince sık, sürekli CPU harcamayacak kadar seyrek.
KONTROL_ARALIGI_MS = 30_000


def _roster_listesi() -> list[str]:
    """data/roster/ altındaki sınıf dosyalarının adları (uzantısız)."""
    if not ROSTER_DIR.exists():
        return []
    return sorted(p.stem for p in ROSTER_DIR.glob("*.json"))


def _roster_yukle(sinif: str) -> list[dict]:
    yol = ROSTER_DIR / f"{sinif}.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return veri.get("ogrenciler", [])


def _zil_yukle() -> dict:
    if not ZIL_DOSYASI.exists():
        return {"dersler": []}
    return json.loads(ZIL_DOSYASI.read_text(encoding="utf-8"))


def _saat_ayristir(s: str) -> dtime:
    saat, dakika = s.split(":")
    return dtime(int(saat), int(dakika))


def _simdiki_ders(zil: dict, simdi: dtime) -> int | None:
    """Şu an hangi dersin [başlangıç, bitiş) aralığındayız — yoksa None
    (teneffüs/öğle arası/ders dışı)."""
    for ders in zil.get("dersler", []):
        baslangic = _saat_ayristir(ders["baslangic"])
        bitis = _saat_ayristir(ders["bitis"])
        if baslangic <= simdi < bitis:
            return ders["no"]
    return None


def _ders_baslangicindan_gecen_dk(zil: dict, ders_no: int, simdi: dtime) -> int:
    for ders in zil.get("dersler", []):
        if ders["no"] == ders_no:
            baslangic = _saat_ayristir(ders["baslangic"])
            simdi_dk = simdi.hour * 60 + simdi.minute
            baslangic_dk = baslangic.hour * 60 + baslangic.minute
            return simdi_dk - baslangic_dk
    return 0


def _kayit_yolu(sinif: str, ders_no: int, tarih: str) -> Path:
    return KAYIT_DIR / f"{tarih}_{sinif}_ders{ders_no}.json"


class OgrenciKarti(QPushButton):
    """Bir öğrencinin dokunmatik yoklama kartı — üç hâl arasında döner."""

    def __init__(self, ogrenci: dict, durum: str = "var"):
        super().__init__()
        self.no = ogrenci["no"]
        self.ad_soyad = ogrenci["ad_soyad"]
        self.durum = durum
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
        self._kartlar: list[OgrenciKarti] = []
        self._aktif_ders_no: int | None = None
        self._zil = _zil_yukle()
        self._kur_arayuz()
        self._sinif_degisti()
        self.showFullScreen()

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._periyodik_kontrol)
        self._zamanlayici.start(KONTROL_ARALIGI_MS)

    def _kur_arayuz(self) -> None:
        ana = QVBoxLayout(self)

        ust = QHBoxLayout()
        self.baslik_etiketi = QLabel("YOKLAMA")
        self.baslik_etiketi.setStyleSheet("font-size: 26pt; font-weight: bold;")
        ust.addWidget(self.baslik_etiketi)

        ust.addStretch()

        ust.addWidget(QLabel("Sınıf:"))
        self.sinif_secici = QComboBox()
        self.sinif_secici.setMinimumHeight(50)
        self.sinif_secici.setStyleSheet("font-size: 16pt;")
        self.sinif_secici.addItems(_roster_listesi())
        self.sinif_secici.currentTextChanged.connect(self._sinif_degisti)
        ust.addWidget(self.sinif_secici)

        self.tam_ekran_dugmesi = QPushButton("⛶ Pencereye Dön")
        self.tam_ekran_dugmesi.setMinimumSize(160, 50)
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

    # ------------------------------------------------------------------
    # Dönem/ders takibi
    # ------------------------------------------------------------------

    def _periyodik_kontrol(self) -> None:
        simdi = datetime.now().time()
        yeni_ders_no = _simdiki_ders(self._zil, simdi)

        if yeni_ders_no != self._aktif_ders_no:
            # Dönem değişti — eski dersin ekrandaki hâli kaybolmasın diye
            # önce otomatik kaydet, sonra yeni dersi yükle.
            if self._aktif_ders_no is not None:
                self._kaydet(sessiz=True)
            self._aktif_ders_no = yeni_ders_no
            self._ders_grubunu_yukle()

        if yeni_ders_no is not None:
            gecen_dk = _ders_baslangicindan_gecen_dk(self._zil, yeni_ders_no, simdi)
            if gecen_dk >= UYARI_ESIGI_DK and not self._bugun_kayit_var_mi():
                self._pencereyi_one_getir()

        self._baslik_guncelle()

    def _bugun_kayit_var_mi(self) -> bool:
        sinif = self.sinif_secici.currentText()
        if not sinif or self._aktif_ders_no is None:
            return False
        tarih = datetime.now().strftime("%Y-%m-%d")
        return _kayit_yolu(sinif, self._aktif_ders_no, tarih).exists()

    def _pencereyi_one_getir(self) -> None:
        if self.isMinimized():
            self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def _baslik_guncelle(self) -> None:
        if self._aktif_ders_no is not None:
            self.baslik_etiketi.setText(f"YOKLAMA — {self._aktif_ders_no}. Ders")
        else:
            self.baslik_etiketi.setText("YOKLAMA — ders saati dışı")

    # ------------------------------------------------------------------
    # Sınıf/ders yükleme
    # ------------------------------------------------------------------

    def _sinif_degisti(self, *_args) -> None:
        simdi = datetime.now().time()
        self._aktif_ders_no = _simdiki_ders(self._zil, simdi)
        self._ders_grubunu_yukle()
        self._baslik_guncelle()

    def _ders_grubunu_yukle(self) -> None:
        """Seçili sınıf + aktif ders için kartları kurar — o ders için
        daha önce kayıt varsa onu yükler, yoksa hepsini 'var' başlatır."""
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

        onceki_durumlar: dict[str, str] = {}
        if self._aktif_ders_no is not None:
            tarih = datetime.now().strftime("%Y-%m-%d")
            yol = _kayit_yolu(sinif, self._aktif_ders_no, tarih)
            if yol.exists():
                try:
                    onceki_durumlar = json.loads(yol.read_text(encoding="utf-8")).get("durumlar", {})
                except (json.JSONDecodeError, OSError):
                    onceki_durumlar = {}

        ogrenciler = _roster_yukle(sinif)
        for idx, ogrenci in enumerate(ogrenciler):
            durum = onceki_durumlar.get(str(ogrenci["no"]), "var")
            kart = OgrenciKarti(ogrenci, durum=durum)
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
        if self.isFullScreen():
            self.showNormal()
            self.tam_ekran_dugmesi.setText("⛶ Tam Ekran")
        else:
            self.showFullScreen()
            self.tam_ekran_dugmesi.setText("⛶ Pencereye Dön")

    def _kaydet(self, sessiz: bool = False) -> None:
        sinif = self.sinif_secici.currentText()
        if not sinif or not self._kartlar or self._aktif_ders_no is None:
            if not sessiz:
                QMessageBox.warning(
                    self, "Kaydedilemedi",
                    "Şu an ders saati dışındayız, hangi ders için kaydedileceği belli değil."
                )
            return
        KAYIT_DIR.mkdir(parents=True, exist_ok=True)
        tarih = datetime.now().strftime("%Y-%m-%d")
        kayit = {
            "sinif": sinif,
            "tarih": tarih,
            "ders_no": self._aktif_ders_no,
            "kaydedilme_saati": datetime.now().strftime("%H:%M:%S"),
            "durumlar": {str(k.no): k.durum for k in self._kartlar},
        }
        yol = _kayit_yolu(sinif, self._aktif_ders_no, tarih)
        yol.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
        if not sessiz:
            QMessageBox.information(self, "Kaydedildi", f"Yoklama kaydedildi:\n{yol.name}")


def main() -> int:
    app = QApplication(sys.argv)
    pencere = YoklamaPenceresi()
    pencere.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
