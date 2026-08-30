"""
core/ders_motoru.py — Dersin akışını KOD yürütür, model değil.

Neden var
---------
Modelin işleyen bir saati yok: `[CURRENT DATE & TIME]` `_build_config` içinde
oturum başına bir kez kuruluyor, dakikaların aktığını göremiyor. Bu yüzden
`core/prompt.txt` v2.0'daki bütün tempo kuralları "adım tabanlı" yazılmak
zorunda kaldı ("her çözülen örnekten sonra"), çünkü "beş dakika sonra"
diyebilecek bir merci yoktu. Bu modül o merci.

İki temel kural
---------------
1. **Durumu bu modül belirler, model değil.** Model durumu değiştiremez;
   durum değişince bilgilendirilir. Ders yapısının modelin o anki sezgisine
   bırakılması, sınıfta özetin atlanması ya da quizin hiç yapılmaması demek.
2. **Öğretmen her zaman kazanır.** `mudahale()` akışı duraklatır, `gec()` adımı
   zorlar. Öğretmenin önüne geçen bir akış motoru, sınıfta zarar verir.

GÖZLEMCİ KİPİ (artık varsayılan DEĞİL — bkz. main.py)
------------------------------------------------------
`enjekte=False` iken motor yalnız hesaplar, loglar ve arayüze yazar; oturuma
hiçbir şey göndermez. Bu, önce gerçek derste izlenip sonra enjeksiyonun
açılması için bilinçli bir ara adımdı: ders akışına müdahale eden bir
değişikliği doğrudan sınıfa vermek, hatanın bedelini öğrenciye ödetmek
olurdu. **O geçiş yapıldı** — `main.py::FarabiLive.__init__` artık
`enjekte=True` sabit geçiyor, gerçek varsayılan ENJEKSİYON AÇIK (`main.py`
kendi yorumunda bunu doğru anlatır). Bu docstring 2026-08-30'da bir
doküman↔kod denetiminde eski hâliyle bulundu, düzeltildi — modülün kendisi
hâlâ `enjekte` parametresini kabul ediyor (gözlemci kipi hâlâ mümkün,
yalnızca artık varsayılan değil).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime

from core import zil
from core.logger import get_logger

log = get_logger("ders_motoru")

# ── Adımlar ────────────────────────────────────────────────────────────────
BEKLIYOR            = "BEKLIYOR"
YOKLAMA             = "YOKLAMA"
ISINMA              = "ISINMA"
TEKRAR              = "TEKRAR"
ANLATIM             = "ANLATIM"
REHBERLI_ALISTIRMA  = "REHBERLI_ALISTIRMA"
BAGIMSIZ_CALISMA    = "BAGIMSIZ_CALISMA"
DEGERLENDIRME       = "DEGERLENDIRME"
OZET                = "OZET"
ODEV                = "ODEV"
BITTI               = "BITTI"

SIRA = [BEKLIYOR, YOKLAMA, ISINMA, TEKRAR, ANLATIM, REHBERLI_ALISTIRMA,
        BAGIMSIZ_CALISMA, DEGERLENDIRME, OZET, ODEV, BITTI]

# Ders sonuna bu kadar dakika kalınca özete geçilir. 40 dakikalık derste
# özet + ödev için ayrılan pay; zil çaldığında yarım kalmasın diye.
OZET_ESIGI_DK = 8

# Öğretmen müdahalesi ne kadar süreyle önerileri susturur.
# Kalıcı kilit OLMAMALI: paneldeki "devam et" düğmesi kaldırıldığı için
# bayrağı elle kaldıracak bir denetim kalmadı; kilitli kalırsa motor bir daha
# hiç öneri üretmez ve sessizce ölür.
MUDAHALE_SURESI_DK = 5

# Modele SÜRE HABERİ verilecek eşikler. Kalan dakika her dakika değişiyor;
# her değişimde mesaj göndermek dersin ortasına dakikada bir müdahale demek
# ve modeli sürekli "yeni girdi geldi" durumuna sokuyordu. Haber yalnız bu
# eşikler geçilirken ve adım değişince gider.
SURE_ESIKLERI = (20, 10, 5, 2)

# Bu adımlarda özet uyarısı anlamsız (zaten sonundayız)
_SON_ADIMLAR = {OZET, ODEV, BITTI}


@dataclass
class DersDurumu:
    """Dersin o anki hâli. Arayüz ve log bunu okur."""
    sinif: str = ""
    kip: str = "ogretmenli"
    kazanim_kodu: str = ""
    ders_adi: str = ""
    konu: str = ""
    adim: str = BEKLIYOR
    adim_baslangic: str = ""
    ders_no: int | None = None
    kalan_dk: int | None = None
    kitap_sayfasi: str = ""
    tamamlanan_adimlar: list = field(default_factory=list)
    kontrol_dogru: int = 0
    kontrol_toplam: int = 0
    degerlendirme_yapildi: bool = False
    ogretmen_mudahalesi: bool = False
    mudahale_zamani: str = ""
    duraklatildi: bool = False

    def sozluk(self) -> dict:
        return asdict(self)


class DersMotoru:
    """
    Deterministik ders akışı. Dışarıdan yalnız üç şey tetikler:
    zaman (`guncelle`), öğretmen (`gec`, `mudahale`) ve olaylar
    (`kontrol_sonucu`, `arac_kullanildi`).
    """

    def __init__(self, kip: str = "ogretmenli", cerceve: dict | None = None,
                 sinif: str = "", enjekte: bool = False):
        self.enjekte = enjekte          # False = gözlemci kipi
        self.durum = DersDurumu(
            sinif=sinif,
            kip=kip,
            ders_adi=(cerceve or {}).get("subject", "") or "",
            konu=(cerceve or {}).get("topic", "") or "",
            kazanim_kodu=(cerceve or {}).get("kazanim_kodu", "") or "",
        )
        self._son_bildirilen: tuple | None = None

    # ── Zaman ──────────────────────────────────────────────────────────────
    def guncelle(self, simdi: datetime | None = None) -> DersDurumu:
        """Zil çizelgesinden ders no ve kalan süreyi tazele."""
        simdi = simdi or datetime.now()
        if self.durum.ogretmen_mudahalesi and self._mudahale_suresi_doldu(simdi):
            self.mudahale(False)
        d = zil.ders_durumu(simdi)
        self.durum.ders_no = d.get("ders_no")
        self.durum.kalan_dk = d.get("kalan_dk")
        if d.get("tur") == "ders" and self.durum.adim == BEKLIYOR:
            self._ayarla(YOKLAMA, kaynak="zil")
        elif d.get("tur") in ("teneffus", "ogle", "sonra") and \
                self.durum.adim not in (BEKLIYOR, BITTI):
            self._ayarla(BITTI, kaynak="zil")
        return self.durum

    # ── Geçişler ───────────────────────────────────────────────────────────
    def gec(self, adim: str, kaynak: str = "ogretmen") -> DersDurumu:
        """Adımı doğrudan ayarla. Öğretmen komutu buradan gelir ve her zaman geçer."""
        if adim not in SIRA:
            raise ValueError(f"Bilinmeyen adım: {adim}")
        self._ayarla(adim, kaynak=kaynak)
        return self.durum

    def ilerle(self, kaynak: str = "motor") -> DersDurumu:
        """Sıradaki adıma geç. Son adımdaysa yerinde kalır."""
        i = SIRA.index(self.durum.adim)
        if i < len(SIRA) - 1:
            self._ayarla(SIRA[i + 1], kaynak=kaynak)
        return self.durum

    def mudahale(self, acik: bool = True, simdi: datetime | None = None) -> DersDurumu:
        """
        Öğretmen araya girdi: motor bir süre öneri üretmez.

        Süreli, kalıcı değil (MUDAHALE_SURESI_DK). Öğretmenin bayrağı elle
        kaldırması gerekmemeli; unutulan bir kilit, motoru dersin geri
        kalanında sessizce devre dışı bırakır.
        """
        self.durum.ogretmen_mudahalesi = acik
        self.durum.mudahale_zamani = (simdi or datetime.now()).isoformat(timespec="seconds") if acik else ""
        log.info("Öğretmen müdahalesi: %s", "açık" if acik else "kapandı")
        return self.durum

    def duraklat(self, acik: bool = True) -> DersDurumu:
        """
        Öğretmen DURDUR'a bastı. Müdahaleden farkı: bu KALICIDIR.

        Süreli olan, yazılı komutların ardından motorun bir süre susmasıdır.
        Durdurma ise bilinçli bir emirdir ve yalnızca DEVAM ET kaldırır —
        kendiliğinden devam eden bir ders, öğretmenin durdurma sebebini
        (sınıfa biri girdi, telefon çaldı) hiçe sayar.
        """
        self.durum.duraklatildi = acik
        log.info("Ders %s", "DURAKLATILDI" if acik else "devam ediyor")
        return self.durum

    def _mudahale_suresi_doldu(self, simdi: datetime) -> bool:
        if not self.durum.mudahale_zamani:
            return True
        try:
            baslangic = datetime.fromisoformat(self.durum.mudahale_zamani)
        except ValueError:
            return True
        return (simdi - baslangic).total_seconds() >= MUDAHALE_SURESI_DK * 60

    def _ayarla(self, adim: str, kaynak: str) -> None:
        if adim == self.durum.adim:
            return
        onceki = self.durum.adim
        if onceki not in (BEKLIYOR,) and onceki not in self.durum.tamamlanan_adimlar:
            self.durum.tamamlanan_adimlar.append(onceki)
        self.durum.adim = adim
        self.durum.adim_baslangic = datetime.now().isoformat(timespec="seconds")
        if adim == DEGERLENDIRME:
            self.durum.degerlendirme_yapildi = True
        log.info("Ders adımı: %s → %s (%s)", onceki, adim, kaynak)

    # ── Sinyaller ──────────────────────────────────────────────────────────
    def kontrol_sonucu(self, dogru: int, toplam: int) -> None:
        """Kontrol noktası / mini değerlendirme sonucu."""
        self.durum.kontrol_dogru += max(0, dogru)
        self.durum.kontrol_toplam += max(0, toplam)

    @property
    def kontrol_oran(self) -> float | None:
        if not self.durum.kontrol_toplam:
            return None
        return self.durum.kontrol_dogru / self.durum.kontrol_toplam

    # ── Öneri (kural motorunun çekirdeği) ──────────────────────────────────
    def oneri(self) -> dict | None:
        """
        "Şimdi ne yapılmalı?" — deterministik kurallar. Model bunu üretmez,
        alır. Öneri listesi KAPALI: her biri arayüzde gösterilebilir ve
        loglanabilir bir eylemdir.

        Dönen: {"eylem": ..., "gerekce": ...} ya da None.
        """
        d = self.durum
        if d.duraklatildi:
            return {"eylem": "DURAKLAT", "gerekce": "Öğretmen dersi durdurdu."}
        if d.ogretmen_mudahalesi:
            return {"eylem": "DURAKLAT", "gerekce": "Öğretmen araya girdi."}

        if d.kalan_dk is not None and d.kalan_dk <= OZET_ESIGI_DK \
                and d.adim not in _SON_ADIMLAR and d.adim != BEKLIYOR:
            return {"eylem": "ADIM_OZET",
                    "gerekce": f"Ders bitmesine {d.kalan_dk} dakika kaldı."}

        oran = self.kontrol_oran
        if oran is not None and d.kontrol_toplam >= 2 and oran < 0.5:
            return {"eylem": "FARKLI_ANLATIM",
                    "gerekce": f"Kontrol noktası oranı düşük ({d.kontrol_dogru}/{d.kontrol_toplam})."}

        if d.adim == BAGIMSIZ_CALISMA and not d.degerlendirme_yapildi \
                and d.kalan_dk is not None and d.kalan_dk <= OZET_ESIGI_DK + 7:
            return {"eylem": "KONTROL_SORUSU",
                    "gerekce": "Değerlendirme henüz yapılmadı, süre daralıyor."}

        return None

    # ── Dışarıya verilen metinler ──────────────────────────────────────────
    def _sure_bandi(self) -> int | None:
        """Kalan süreyi eşiğe yuvarla — dakika başı haber gitmesin."""
        if self.durum.kalan_dk is None:
            return None
        for esik in SURE_ESIKLERI:
            if self.durum.kalan_dk <= esik:
                return esik
        return 99

    def hud_satiri(self) -> str:
        """Arayüzün sol panelinde tek satır."""
        d = self.durum
        parcalar = [d.adim.replace("_", " ")]
        if d.kalan_dk is not None:
            parcalar.append(f"{d.kalan_dk} dk")
        if d.kazanim_kodu:
            parcalar.append(d.kazanim_kodu)
        return "  ·  ".join(parcalar)

    def enjeksiyon_metni(self) -> str | None:
        """
        Oturuma gönderilecek [DERS DURUMU] bloğu. GÖZLEMCİ kipinde None döner.

        Aynı içerik iki kez gönderilmez: modelin bağlamını değişmemiş durumla
        doldurmak, hem jeton israfı hem de dikkat dağıtır.
        """
        if not self.enjekte or self.durum.duraklatildi:
            return None
        d = self.durum
        oneri = self.oneri()
        imza = (d.adim, self._sure_bandi(), d.degerlendirme_yapildi,
                (oneri or {}).get("eylem"))
        if imza == self._son_bildirilen:
            return None
        self._son_bildirilen = imza

        satirlar = [f"[DERS DURUMU] adım: {d.adim}"]
        if d.kalan_dk is not None:
            satirlar.append(f"kalan süre: {d.kalan_dk} dakika")
        if d.kazanim_kodu or d.konu:
            satirlar.append(f"kazanım: {d.kazanim_kodu} {d.konu}".strip())
        if d.kontrol_toplam:
            satirlar.append(f"kontrol noktası: {d.kontrol_dogru}/{d.kontrol_toplam}")
        if oneri:
            satirlar.append(f"öneri: {oneri['eylem']} — {oneri['gerekce']}")
        satirlar.append("Bu bir durum bilgisidir. Sesli olarak 'anladım' deme, "
                        "selamlama yapma; planını buna göre sürdür.")
        return "\n".join(satirlar)
