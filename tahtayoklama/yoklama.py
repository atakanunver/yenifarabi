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
- **Izgara sütun sayısı VE kart yüksekliği artık DİNAMİK** (2026-09-06'da
  sabit "4 sütun / 90px" değerlerinden değiştirildi — 9-A'nın 1360px
  genişliğinde yatay kaydırmaya, 20 öğrencilik bir sınıfta da dikey
  kaydırmaya yol açıyordu; kullanıcı: "20 kişi ekrana sığmıyor").
  `_duzen_hesapla` hem pencere genişliğine HEM yüksekliğine HEM sınıf
  mevcuduna göre sütun sayısını ve kart boyutunu (gerekirse font boyutunu
  da, bkz. `OgrenciKarti._guncelle`) hesaplar; hedef, sınıfın tamamının TEK
  ekranda, kaydırma gerekmeden görünmesidir. Pencere yeniden boyutlandığında
  (`resizeEvent` → `_izgarayi_yeniden_diz`) kartlar YENİDEN OLUŞTURULMADAN
  boyutlanır, kaydedilmemiş işaretlemeler KORUNUR.
- **Ders saatine göre otomatik dönem tespiti**: `data/zil.json` (Farabi'nin
  `client/config/zil.json`'undan BAĞIMSIZ bir kopya — bu tahtalarda Farabi
  hiç kurulu olmayabilir, bkz. o dosyanın açıklaması) okunur, o anki saate
  göre "kaçıncı derste olduğumuz" bulunur (`_simdiki_ders`). "08:30 → 1.
  ders", "08:40 → hâlâ 1. ders (öğrenci geç gelmiş olabilir)" gibi —
  ölçüt basitçe "şu an hangi dersin [başlangıç, bitiş) aralığındayız".
- **Kayıt artık DERS BAZLI**: `data/kayitlar/<tarih>_<sinif>_ders<no>.json`
  — bir günde en fazla 8 kayıt (bir tanesi her ders saati için).
- **10 dakika kuralı**: bir ders başladıktan 10 dakika sonra hâlâ o ders
  için kayıt yoksa, pencere öne getirilir (`raise_`/`activateWindow`) —
  30 saniyede bir çalışan bir zamanlayıcıyla kontrol edilir.

GÜNCELLEME (2026-09-28, "yoklama panoda görünmüyor" şikâyeti sonrası kök
neden düzeltmesi — ayrıntı kök `DECISIONS.md` 2026-09-28):
- **Tek örnek (single instance) koruması eklendi.** Masaüstü simgesine
  çift dokunulup ikinci bir pencere açılması, dokunulmamış arka plan
  penceresinin öğretmenin gerçek kaydının üzerine "herkes var" yazmasına
  yol açan senaryolardan biriydi. Artık ikinci bir başlatma yeni pencere
  AÇMAZ — zaten çalışan bir örneğe (varsa) `QLocalServer`/`QLocalSocket`
  (PyQt6.QtNetwork) ile "öne getir" mesajı gönderir ve kendisi hemen çıkar
  (bkz. `_tekil_ornek_sunucusu_baslat`).
- **Otomatik sessiz kayıt KALDIRILDI.** Eskiden dönem değiştiğinde önceki
  dersin ekrandaki hâli `_kaydet(sessiz=True)` ile otomatik yazılıyordu —
  bu, teneffüste yapılan işaretlemelerin ders başlarken sıfırlanıp sonra
  otomatik "herkes var" olarak kaydedilmesine yol açıyordu. Artık kayıt
  YALNIZCA öğretmen "YOKLAMAYI KAYDET"e basınca yazılır; dönem değiştiğinde
  yalnızca yeni dersin grubu yüklenir, hiçbir dosyaya otomatik yazma olmaz.
- **Teneffüs/ders saati dışında yoklama alınamaz.** `_aktif_ders_no is
  None` iken öğrenci kartları ve "YOKLAMAYI KAYDET" düğmesi devre dışı
  kalır (bkz. `_girisleri_ayarla`) — bu, teneffüste yapılan işaretlemelerin
  ders başlarken sıfırlanmasının kök nedenini kapatır. Ders başladığında
  (dönem değişimi ile) tazeden etkinleşir.

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
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent
ROSTER_DIR = BASE_DIR / "data" / "roster"
KAYIT_DIR = BASE_DIR / "data" / "kayitlar"
ZIL_DOSYASI = BASE_DIR / "data" / "zil.json"
# tahta_istemci.py sunucudan çeker (2026-10-06). Yoksa/bozuksa başlıkta
# ders adı gösterilmez — yoklama bundan hiç etkilenmez.
DERS_PROGRAMI_DOSYASI = BASE_DIR / "data" / "ders_programi.json"
# Haftalık kazanım (yıllık planlardan, dashboard/scripts/kazanim_yukle.py
# üretir, tahta_istemci.py çeker). Yoksa/bozuksa ikinci satır boş kalır.
KAZANIM_DOSYASI = BASE_DIR / "data" / "kazanimlar.json"
_GUN_ANAHTARLARI = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma"}

# Tek örnek koruması için sabit yerel soket adı — bkz. _tekil_ornek_sunucusu_baslat.
TEKIL_ORNEK_SUNUCU_ADI = "tahtayoklama-yoklama"

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
# 2026-09-06: sabit yükseklik/sütun (KART_MIN_YUKSEKLIK=90, SUTUN=4) hem
# yatayda (9-A, 1360px genişlik) hem dikeyde (20 öğrenci ekrana sığmıyordu,
# kullanıcı geri bildirimi) taşmaya yol açıyordu. Artık hem sütun sayısı
# HEM kart yüksekliği, sınıf mevcuduna ve gerçek pencere boyutuna göre
# hesaplanıyor (bkz. _duzen_hesapla) — hedef, KAYDIRMA GEREKMEDEN tüm
# sınıfın tek ekrana sığması.
KART_FONT_PT = 16
MAKS_KART_YUKSEKLIK = 90
MIN_KART_YUKSEKLIK = 56
KART_HEDEF_GENISLIK = 320
MIN_KART_GENISLIK = 150
IZGARA_BOSLUK = 12
SUTUN_MIN = 2
SUTUN_MAKS = 5

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


def _ders_programi_yukle() -> dict:
    try:
        veri = json.loads(DERS_PROGRAMI_DOSYASI.read_text(encoding="utf-8"))
        return veri if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def _ders_adi_ham(program: dict, sinif: str, gun_no: int, ders_no: int) -> str | None:
    """Ders programındaki ham ders adı (küçük harf, ör. "matematik"). O
    gün/sınıf programda var ama bu ders boşsa ""; program/sınıf/gün hiç
    yoksa None. Hiçbir girdi istisna fırlatmaz."""
    try:
        gun = program.get("siniflar", {}).get(sinif, {}).get(_GUN_ANAHTARLARI.get(gun_no))
        if not isinstance(gun, dict):
            return None
        ad = gun.get(str(ders_no))
        return ad.strip() if isinstance(ad, str) else ""
    except AttributeError:
        return None


def _ders_adi(program: dict, sinif: str, gun_no: int, ders_no: int) -> str | None:
    """Başlıkta gösterilecek ders adı (büyük harf); boş ders "BOŞ", program
    yoksa None (başlıkta ad gösterilmez)."""
    ham = _ders_adi_ham(program, sinif, gun_no, ders_no)
    if ham is None:
        return None
    if not ham:
        return "BOŞ"
    # Türkçe büyük harf: str.upper() 'i'yi 'I' yapar.
    return ham.replace("i", "İ").replace("ı", "I").upper()


def _kazanim_yukle() -> dict:
    try:
        veri = json.loads(KAZANIM_DOSYASI.read_text(encoding="utf-8"))
        return veri if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def _kazanim(kazanimlar: dict, sinif: str, ders_adi_ham: str | None, bugun: date) -> str | None:
    """Bu haftanın kazanımı: `haftalar` (hafta no → o haftanın pazartesisi)
    içinde bugünü kapsayan hafta, `kazanimlar[düzey][ders][hafta]`. Düzey
    sınıf adından ("12-A" → "12"). Tatil haftası/eksik plan → None."""
    try:
        if not ders_adi_ham:
            return None
        duzey = sinif.split("-")[0]
        hafta = None
        for no, pazartesi in kazanimlar.get("haftalar", {}).items():
            baslangic = date.fromisoformat(pazartesi)
            if baslangic <= bugun < baslangic + timedelta(days=7):
                hafta = no
                break
        if hafta is None:
            return None
        metin = kazanimlar.get("kazanimlar", {}).get(duzey, {}).get(ders_adi_ham, {}).get(hafta)
        if not isinstance(metin, str):
            return None
        # Haftada birden fazla kazanım "\n" ile ayrılır (her biri tek satır).
        satirlar = [" ".join(s.split()) for s in metin.split("\n")]
        return "\n".join(s for s in satirlar if s) or None
    except (AttributeError, TypeError, ValueError):
        return None


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


def _duzen_hesapla(genislik: int, yukseklik: int, ogrenci_sayisi: int) -> tuple[int, int, int]:
    """(sütun sayısı, kart genişliği, kart yüksekliği) döner — HEM yatayda
    HEM dikeyde kaydırma gerekmeden tüm sınıfın tek ekrana sığması hedefiyle.
    Önce genişliğe göre olabilecek EN FAZLA sütun seçilir (daha çok sütun =
    daha az satır = dikeyde sığma ihtimali daha yüksek); sonra o sütun
    sayısıyla kaç satır gerektiği hesaplanıp kart yüksekliği kalan dikey
    alana göre (MIN_KART_YUKSEKLIK..MAKS_KART_YUKSEKLIK arası) ayarlanır."""
    if ogrenci_sayisi <= 0 or genislik <= 0:
        return SUTUN_MIN, KART_HEDEF_GENISLIK, MAKS_KART_YUKSEKLIK

    sutun = genislik // (MIN_KART_GENISLIK + IZGARA_BOSLUK)
    sutun = max(SUTUN_MIN, min(SUTUN_MAKS, sutun, ogrenci_sayisi))
    kart_genislik = max(MIN_KART_GENISLIK, genislik // sutun - IZGARA_BOSLUK)

    satir = -(-ogrenci_sayisi // sutun)  # yukarı yuvarlama (ceil)
    if yukseklik > 0 and satir > 0:
        kart_yukseklik = (yukseklik - (satir - 1) * IZGARA_BOSLUK) // satir
        kart_yukseklik = max(MIN_KART_YUKSEKLIK, min(MAKS_KART_YUKSEKLIK, kart_yukseklik))
    else:
        kart_yukseklik = MAKS_KART_YUKSEKLIK

    return sutun, kart_genislik, kart_yukseklik


def _ad_sarmala(ad: str, kart_genislik: int, font_pt: int) -> str:
    """Uzun isimleri kart genişliğine göre satırlara böler — aksi halde
    tek satırlık isim metni kartın (dolayısıyla sütunun) sabit genişliğini
    taşıp yatay kaydırmaya/kesilmeye yol açıyordu. Karakter sayısı tahmini
    yerine gerçek font metrikleri kullanılır (kabaca tahmin, uzun isimlerde
    birkaç piksellik kesilmeye yol açıyordu — 2026-09-06, 9-A testinde
    görüldü)."""
    font = QFont()
    font.setPointSize(font_pt)
    font.setBold(True)
    metrikler = QFontMetrics(font)
    # padding (10px*2) + küçük güvenlik payı
    maks_genislik = max(40, kart_genislik - 30)
    if metrikler.horizontalAdvance(ad) <= maks_genislik:
        return ad
    kelimeler = ad.split(" ")
    satirlar: list[str] = []
    mevcut = ""
    for kelime in kelimeler:
        aday = f"{mevcut} {kelime}".strip()
        if metrikler.horizontalAdvance(aday) <= maks_genislik or not mevcut:
            mevcut = aday
        else:
            satirlar.append(mevcut)
            mevcut = kelime
    satirlar.append(mevcut)
    return "\n".join(satirlar)


def _tekil_ornek_sunucusu_baslat(adi: str = TEKIL_ORNEK_SUNUCU_ADI) -> tuple[QLocalServer | None, bool]:
    """Tek örnek (single instance) koruması — masaüstü simgesine çift
    dokunulup ikinci bir pencere açılması, dokunulmamış arka plan
    penceresinin öğretmenin gerçek kaydının üzerine yazmasına yol açıyordu
    (bkz. modül docstring'i, 2026-09-28). `(sunucu, cikilmali)` döner:

    - `cikilmali=True`: bu ikinci bir örnek — zaten çalışan bir örneğe
      "öne getir" mesajı gönderildi (ya da gönderilmeye çalışıldı).
      Çağıran hemen `sys.exit`/`return` etmeli, PENCERE AÇMAMALI.
    - `cikilmali=False, sunucu is not None`: bu ilk örnek, `sunucu` artık
      dinlemede — çağıran bu referansı YoklamaPenceresi'ne (ya da en azından
      `app.exec()` süresince canlı bir yere) vermeli, aksi halde
      çöp toplayıcı soketi kapatır.
    - `cikilmali=False, sunucu is None`: soket hiçbir şekilde kurulamadı
      (beklenmeyen ortam/izin sorunu) — tek-örnek koruması YOK, ama
      pencere normal açılır (Kural 2, "Farabi asla dersi bozmaz": eksik
      koruma, hiç açılmayan yoklama penceresinden daha az kötü).

    Sıra kasıtlı: ÖNCE `listen()` denenir. Başarısız olursa ÖNCE `connect`
    ile gerçekten canlı bir örnek olup olmadığı doğrulanır, `removeServer`
    yalnızca bağlantı da başarısız olursa (soket kalıntısı/çökmüş önceki
    örnek) çağrılır — tersi sıra (önce removeServer) çift dokunuşta bir
    yarış durumu yaratıp iki pencerenin de açılmasına yol açabilirdi."""
    sunucu = QLocalServer()
    if sunucu.listen(adi):
        return sunucu, False

    soket = QLocalSocket()
    soket.connectToServer(adi)
    if soket.waitForConnected(200):
        soket.write(b"one_getir\n")
        soket.waitForBytesWritten(200)
        soket.disconnectFromServer()
        soket.waitForDisconnected(200)
        return None, True

    # Bağlanılamadı: önceki örnek çökmüş, soket dosyası kalıntı — temizleyip
    # yeniden dinlemeyi dene.
    QLocalServer.removeServer(adi)
    sunucu = QLocalServer()
    if sunucu.listen(adi):
        return sunucu, False
    return None, False


class OgrenciKarti(QPushButton):
    """Bir öğrencinin dokunmatik yoklama kartı — üç hâl arasında döner."""

    def __init__(
        self,
        ogrenci: dict,
        durum: str = "var",
        genislik: int = KART_HEDEF_GENISLIK,
        yukseklik: int = MAKS_KART_YUKSEKLIK,
    ):
        super().__init__()
        self.no = ogrenci["no"]
        self.ad_soyad = ogrenci["ad_soyad"]
        self.durum = durum
        self.setFixedSize(genislik, yukseklik)
        self.clicked.connect(self._sonraki_duruma_gec)
        self._guncelle()

    def _sonraki_duruma_gec(self) -> None:
        i = DURUM_SIRASI.index(self.durum)
        self.durum = DURUM_SIRASI[(i + 1) % len(DURUM_SIRASI)]
        self._guncelle()

    def boyut_ayarla(self, genislik: int, yukseklik: int) -> None:
        """Durumu KORUYARAK kart boyutunu günceller (bkz.
        YoklamaPenceresi._izgarayi_yeniden_diz — pencere yeniden
        boyutlandığında kayıtsız işaretlemelerin kaybolmaması için kartlar
        yeniden OLUŞTURULMAZ, sadece yeniden boyutlandırılır)."""
        self.setFixedSize(genislik, yukseklik)
        self._guncelle()

    def _guncelle(self) -> None:
        # Kart kısaldığında (kalabalık sınıflarda tüm sınıf dikeyde de
        # sığsın diye) KART_FONT_PT metin taşabilir — yüksekliğe göre küçültülür.
        font_pt = max(10, min(KART_FONT_PT, self.height() // 3))
        dolgu = 4 if self.height() < MAKS_KART_YUKSEKLIK else 10
        ad_gosterim = _ad_sarmala(self.ad_soyad, self.width(), font_pt)
        self.setText(f"{self.no}. {ad_gosterim}\n[ {DURUM_ETIKET[self.durum]} ]")
        # QPushButton:disabled seçicisi — teneffüste kartlar devre dışıyken
        # (bkz. YoklamaPenceresi._girisleri_ayarla) görünüşte de farklı
        # olsun, aksi halde devre dışı kart etkin karttan ayırt edilemezdi.
        self.setStyleSheet(
            f"QPushButton {{ font-size: {font_pt}pt; font-weight: bold; color: white; "
            f"background-color: {DURUM_RENK[self.durum]}; "
            f"border-radius: 12px; padding: {dolgu}px; }}"
            f"QPushButton:disabled {{ background-color: #95a5a6; color: #ecf0f1; }}"
        )


class YoklamaPenceresi(QWidget):
    def __init__(self, tekil_ornek_sunucusu: QLocalServer | None = None):
        super().__init__()
        self.setWindowTitle("Yoklama")
        self._kartlar: list[OgrenciKarti] = []
        self._aktif_ders_no: int | None = None
        self._zil = _zil_yukle()
        self._ders_programi = _ders_programi_yukle()
        self._kazanimlar = _kazanim_yukle()
        self._kazanim_metni = ""
        self._kur_arayuz()
        self._sinif_degisti()
        self.showFullScreen()

        # Tek örnek koruması — bkz. _tekil_ornek_sunucusu_baslat. Referans
        # burada tutulmazsa Python çöp toplayıcısı sunucuyu kapatabilir.
        self._tekil_ornek_sunucusu = tekil_ornek_sunucusu
        if self._tekil_ornek_sunucusu is not None:
            self._tekil_ornek_sunucusu.newConnection.connect(self._tekil_ornek_bagli_geldi)

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._periyodik_kontrol)
        self._zamanlayici.start(KONTROL_ARALIGI_MS)

    def _tekil_ornek_bagli_geldi(self) -> None:
        """İkinci bir örnek başlatılmaya çalışıldığında (bkz.
        _tekil_ornek_sunucusu_baslat) çağrılır — mesajın İÇERİĞİ önemli
        değil, bağlantının kendisi zaten "öne getir" sinyalidir."""
        if self._tekil_ornek_sunucusu is None:
            return
        soket = self._tekil_ornek_sunucusu.nextPendingConnection()
        if soket is not None:
            soket.disconnected.connect(soket.deleteLater)
        self._pencereyi_one_getir()

    def _kur_arayuz(self) -> None:
        ana = QVBoxLayout(self)

        ust = QHBoxLayout()
        self.baslik_etiketi = QLabel("YOKLAMA")
        self.baslik_etiketi.setStyleSheet("font-size: 22pt; font-weight: bold;")
        ust.addWidget(self.baslik_etiketi)

        ust.addStretch()

        ust.addWidget(QLabel("Sınıf:"))
        self.sinif_secici = QComboBox()
        self.sinif_secici.setMinimumHeight(50)
        self.sinif_secici.setStyleSheet("font-size: 14pt;")
        self.sinif_secici.addItems(_roster_listesi())
        self.sinif_secici.currentTextChanged.connect(self._sinif_degisti)
        ust.addWidget(self.sinif_secici)

        self.tam_ekran_dugmesi = QPushButton("⛶ Pencereye Dön")
        self.tam_ekran_dugmesi.setMinimumSize(160, 50)
        self.tam_ekran_dugmesi.setStyleSheet("font-size: 12pt;")
        self.tam_ekran_dugmesi.clicked.connect(self._tam_ekrani_degistir)
        ust.addWidget(self.tam_ekran_dugmesi)

        ana.addLayout(ust)

        # Bu haftanın kazanımı — başlığın altında tek satır, küçük punto.
        # Uzunsa sağdan "…" ile kısaltılır; yatay boyut politikası Ignored
        # ki uzun metin pencereyi/düzeni genişletmesin.
        self.kazanim_etiketi = QLabel("")
        self.kazanim_etiketi.setStyleSheet("font-size: 13pt; color: #555;")
        self.kazanim_etiketi.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.kazanim_etiketi.setVisible(False)
        ana.addWidget(self.kazanim_etiketi)

        self.ozet_etiketi = QLabel()
        self.ozet_etiketi.setStyleSheet("font-size: 14pt;")
        ana.addWidget(self.ozet_etiketi)

        self.izgara = QGridLayout()
        self.izgara.setSpacing(IZGARA_BOSLUK)
        icerik = QWidget()
        icerik.setLayout(self.izgara)
        self._kaydirma = QScrollArea()
        self._kaydirma.setWidgetResizable(True)
        self._kaydirma.setWidget(icerik)
        ana.addWidget(self._kaydirma, stretch=1)

        self.kaydet_dugmesi = QPushButton("YOKLAMAYI KAYDET")
        self.kaydet_dugmesi.setMinimumHeight(70)
        self.kaydet_dugmesi.setStyleSheet(
            "QPushButton { font-size: 17pt; font-weight: bold; color: white; "
            "background-color: #2980b9; border-radius: 12px; }"
            "QPushButton:disabled { background-color: #95a5a6; color: #ecf0f1; }"
        )
        self.kaydet_dugmesi.clicked.connect(self._kaydet)
        ana.addWidget(self.kaydet_dugmesi)

    # ------------------------------------------------------------------
    # Dönem/ders takibi
    # ------------------------------------------------------------------

    def _periyodik_kontrol(self) -> None:
        simdi = datetime.now().time()
        yeni_ders_no = _simdiki_ders(self._zil, simdi)

        if yeni_ders_no != self._aktif_ders_no:
            # Dönem değişti — YALNIZCA yeni dersin grubu yüklenir. Eskiden
            # burada önceki dersin hâli otomatik kaydediliyordu
            # (_kaydet(sessiz=True)); bu KASITLI OLARAK kaldırıldı (bkz.
            # modül docstring'i, 2026-09-28) — kayıt yalnızca öğretmen
            # "YOKLAMAYI KAYDET"e basınca yazılır.
            self._aktif_ders_no = yeni_ders_no
            # İstemci programı gün içinde güncellemiş olabilir.
            self._ders_programi = _ders_programi_yukle()
            self._kazanimlar = _kazanim_yukle()
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
        kazanim = None
        if self._aktif_ders_no is not None:
            metin = f"YOKLAMA — {self._aktif_ders_no}. DERS"
            sinif = self.sinif_secici.currentText()
            simdi = datetime.now()
            ad = _ders_adi(self._ders_programi, sinif, simdi.isoweekday(), self._aktif_ders_no)
            if ad:
                metin += f" · {ad}"
            kazanim = _kazanim(
                self._kazanimlar, sinif,
                _ders_adi_ham(self._ders_programi, sinif, simdi.isoweekday(), self._aktif_ders_no),
                simdi.date(),
            )
            self.baslik_etiketi.setText(metin)
        else:
            self.baslik_etiketi.setText("YOKLAMA — BOŞ")
        self._kazanim_metni = kazanim or ""
        self._kazanim_etiketini_ciz()

    def _kazanim_etiketini_ciz(self) -> None:
        metin = self._kazanim_metni
        self.kazanim_etiketi.setVisible(bool(metin))
        self.kazanim_etiketi.setToolTip("\n".join(f"Kazanım: {k}" for k in metin.split("\n")) if metin else "")
        if not metin:
            self.kazanim_etiketi.setText("")
            return
        # Her kazanım kendi satırında, en fazla 2 satır (haftada 2+ kazanım
        # varsa — ör. matematik); fazlası ikinci satırın sonunda "(+N)".
        genislik = max(200, self.width() - 40)
        olcu = QFontMetrics(self.kazanim_etiketi.font())
        kazanimlar = metin.split("\n")
        satirlar = []
        for i, k in enumerate(kazanimlar[:2]):
            ek = f" (+{len(kazanimlar) - 2})" if i == 1 and len(kazanimlar) > 2 else ""
            satir = olcu.elidedText(f"Kazanım: {k}", Qt.TextElideMode.ElideRight,
                                    genislik - olcu.horizontalAdvance(ek))
            satirlar.append(satir + ek)
        self.kazanim_etiketi.setText("\n".join(satirlar))

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
            self._girisleri_ayarla()
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
        vp = self._kaydirma.viewport()
        genislik = vp.width() or self.width() or KART_HEDEF_GENISLIK * SUTUN_MIN
        yukseklik = vp.height() or self.height()
        sutun, kart_genislik, kart_yukseklik = _duzen_hesapla(genislik, yukseklik, len(ogrenciler))

        for idx, ogrenci in enumerate(ogrenciler):
            durum = onceki_durumlar.get(str(ogrenci["no"]), "var")
            kart = OgrenciKarti(ogrenci, durum=durum, genislik=kart_genislik, yukseklik=kart_yukseklik)
            kart.clicked.connect(self._ozeti_guncelle)
            self._kartlar.append(kart)
            self.izgara.addWidget(kart, idx // sutun, idx % sutun)
        self._girisleri_ayarla()
        self._ozeti_guncelle()

    def _girisleri_ayarla(self) -> None:
        """Teneffüste/ders saati dışında (`_aktif_ders_no is None`) öğrenci
        kartları ve "YOKLAMAYI KAYDET" düğmesi tıklanamaz olur — aksi
        halde öğretmen teneffüste yaptığı işaretlemeler ders başlayınca
        sıfırlanıp kafa karışıklığına yol açıyordu (bkz. modül docstring'i,
        2026-09-28). `_ders_grubunu_yukle` her çağrıldığında (açılış, sınıf
        değişimi, dönem geçişi) burası da çağrılır, bu yüzden ayrıca bir
        zamanlayıcı gerekmez."""
        aktif = self._aktif_ders_no is not None
        for kart in self._kartlar:
            kart.setEnabled(aktif)
        self.kaydet_dugmesi.setEnabled(aktif)

    def _izgarayi_yeniden_diz(self) -> None:
        """Kartları yeniden OLUŞTURMADAN (durumları koruyarak) pencere
        boyutu değiştiğinde düzeni günceller — bkz. resizeEvent.
        _ders_grubunu_yukle burada kullanılmaz, çünkü o kayıtlı yoklamayı
        diskten tekrar okur ve kaydedilmemiş işaretlemeleri sıfırlardı."""
        if not self._kartlar:
            return
        vp = self._kaydirma.viewport()
        genislik, yukseklik = vp.width(), vp.height()
        if genislik <= 0 or yukseklik <= 0:
            return
        sutun, kart_genislik, kart_yukseklik = _duzen_hesapla(genislik, yukseklik, len(self._kartlar))
        for idx, kart in enumerate(self._kartlar):
            kart.boyut_ayarla(kart_genislik, kart_yukseklik)
            self.izgara.addWidget(kart, idx // sutun, idx % sutun)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(50, self._izgarayi_yeniden_diz)
        if hasattr(self, "kazanim_etiketi"):
            self._kazanim_etiketini_ciz()

    def _ozeti_guncelle(self) -> None:
        if self._aktif_ders_no is None:
            self.ozet_etiketi.setText(
                '<span style="color:#000;">Teneffüs / ders saati dışı — '
                "yoklama ders başlayınca alınır.</span>"
            )
            return
        toplam = len(self._kartlar)
        var = sum(1 for k in self._kartlar if k.durum == "var")
        yok = sum(1 for k in self._kartlar if k.durum == "yok")
        izinli = sum(1 for k in self._kartlar if k.durum == "izinli")
        # Özet, tek düz renkte (#ccc) okunaksızdı (açık gri, açık arka plan
        # üzerinde) — her segment kendi durum rengiyle gösteriliyor artık.
        self.ozet_etiketi.setText(
            f'<span style="color:#000;">Toplam: {toplam}</span> · '
            f'<span style="color:{DURUM_RENK["var"]};">Var: {var}</span> · '
            f'<span style="color:{DURUM_RENK["yok"]};">Yok: {yok}</span> · '
            f'<span style="color:{DURUM_RENK["izinli"]};">İzinli: {izinli}</span>'
        )

    def _tam_ekrani_degistir(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.tam_ekran_dugmesi.setText("⛶ Tam Ekran")
        else:
            self.showFullScreen()
            self.tam_ekran_dugmesi.setText("⛶ Pencereye Dön")

    def _kaydet(self) -> None:
        """Yoklamayı diske yazar — YALNIZCA bu metot çağrıldığında (yani
        öğretmen "YOKLAMAYI KAYDET"e bastığında) dosya yazılır/üzerine
        yazılır; otomatik/sessiz bir çağıran YOKTUR (bkz. modül docstring'i,
        2026-09-28)."""
        sinif = self.sinif_secici.currentText()
        if not sinif or not self._kartlar or self._aktif_ders_no is None:
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
        QMessageBox.information(self, "Kaydedildi", f"Yoklama kaydedildi:\n{yol.name}")


def main() -> int:
    app = QApplication(sys.argv)

    # Tek örnek koruması — ikinci bir başlatma (masaüstü simgesine çift
    # dokunuş) yeni bir pencere AÇMAZ, ilk örneği öne getirtip kendisi çıkar.
    sunucu, cikilmali = _tekil_ornek_sunucusu_baslat()
    if cikilmali:
        return 0

    pencere = YoklamaPenceresi(tekil_ornek_sunucusu=sunucu)
    pencere.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
