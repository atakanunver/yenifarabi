"""server/ders_hafizasi.py — "Geçen ders ne işlemiştik" tarzı sorular için
Farabi'nin KENDİ geçmiş ders kayıtlarını okur.

client/actions/ders_hafizasi.py'den taşındı (2026-08-18, server-taşıma).
Davranış BİREBİR korunur — yalnızca kaynak dizin değişti: eskiden client
kendi yerel `logs/ders/*.txt`'ine bakıyordu, şimdi `POST /api/egitim/
ders_kaydi_yedek`'in zaten doldurduğu `yedekler/ders_kaydi/<derslik>/`'e
bakıyor (main.py'deki YEDEK_DIR ile aynı dizin, aynı dosya adı biçimi
`<timestamp>_<derslik>.txt` — `_ders_kaydini_yedekle` içeriği birebir
kopyalıyor). `_norm`/`_kelimeler` merkezi `metin_araclari`'den — burada
tekrar tanımlanmadı.

`ders` ile farkı: `ders_icerigi` KİTAPTAN konu anlatımı getirir; bu araç
kitaba hiç bakmaz, yalnızca bu tahtanın daha önce işlediği derslerin metin
kaydına bakar.

Şu an SÜREN dersin kendi dosyası (`guncel_dosya`, client bildirir) HER ZAMAN
hariç tutulur — Farabi kendi kendini "geçmiş ders" saymaz.
"""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import auth
from metin_araclari import kelimeler as _kelimeler

# FAZ 1 (IMPLEMENT) — bkz. icerik.py'deki aynı değişikliğin notu.
router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

YEDEK_DIR = Path(__file__).resolve().parent / "yedekler" / "ders_kaydi"
MAX_KARAKTER = 6000  # ders_icerigi/yks_sorulari ile aynı bütçe

_CERCEVE_RE = re.compile(r"ÇERÇEVE: ders=(.*?) konu=(.*)")
_BASLIK_RE = re.compile(r"^(?:#.*\n)+", re.M)
_AYIRAC_RE = re.compile(r"^-{10,}$\n?", re.M)
# Aynı allowlist ders_kaydi_yedek'te (main.py) kullanılan — "/" yok, çok
# segmentli traversal engellenir; bare ".." için resolve+containment
# kontrolü aşağıda AYRICA yapılıyor (regex tek başına yeterli değil, bkz.
# main.py::ders_kaydi_yedek'teki geçmiş bug notu).
_GUVENLI_AD = re.compile(r"^[A-Za-z0-9ÇĞİÖŞÜçğıöşü_.-]+$")


class HafizaIstek(BaseModel):
    derslik: str = Field(..., max_length=50)
    ders: str = Field("", max_length=100)
    konu: str = Field("", max_length=200)
    guncel_dosya: str = Field("", max_length=200)


def _tarih_etiketi(dosya: Path) -> str:
    """Dosya adındaki zaman damgasını okunur bir etikete çevirir.
    Ayrıştıramazsa dosya adının kendisini döner — asla patlamaz."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})", dosya.stem)
    if not m:
        return dosya.stem
    yil, ay, gun, saat, dk, _sn = m.groups()
    return f"{gun}.{ay}.{yil} {saat}:{dk}"


def _gecmis_dosyalar(dizin: Path, guncel_adi: str) -> list[Path]:
    """Bu derslikteki tüm yedek ders dosyaları, şu an süren oturum hariç,
    dosya adına göre (zaman damgası öneki sayesinde kronolojik) sıralı."""
    if not dizin.exists():
        return []
    dosyalar = sorted(dizin.glob("*.txt"))
    return [d for d in dosyalar if d.name != guncel_adi]


def _cerceveler(icerik: str) -> list[tuple[str, str]]:
    """Bir dosyadaki tüm ÇERÇEVE satırlarını (ders, konu) çiftleri olarak döner."""
    return [(ders.strip(), konu.strip()) for ders, konu in _CERCEVE_RE.findall(icerik)]


def _govde_kirp(icerik: str) -> str:
    """Başlık/ayıraç satırlarını atar, MAX_KARAKTER'e kırpar."""
    govde = _AYIRAC_RE.sub("", _BASLIK_RE.sub("", icerik)).strip()
    if len(govde) > MAX_KARAKTER:
        govde = govde[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"
    return govde


@router.post("/api/egitim/ders_hafizasi")
def ders_hafizasi(istek: HafizaIstek):
    if not _GUVENLI_AD.match(istek.derslik):
        raise HTTPException(status_code=400, detail="Geçersiz derslik")
    yedek_dir_r = YEDEK_DIR.resolve()
    dizin = (YEDEK_DIR / istek.derslik).resolve()
    if not dizin.is_relative_to(yedek_dir_r):
        raise HTTPException(status_code=400, detail="Geçersiz derslik")

    ders = istek.ders.strip()
    konu = istek.konu.strip()

    adaylar = _gecmis_dosyalar(dizin, istek.guncel_dosya)
    if not adaylar:
        return {"metin": ("Bu tahtada henüz kayıtlı geçmiş bir ders yok, "
                           "efendim — hatırlayabileceğim bir şey bulamadım.")}

    if konu or ders:
        sorgu_kelimeler = _kelimeler(f"{ders} {konu}")
        en_iyi: tuple[float, Path, tuple[str, str]] | None = None
        for dosya in adaylar:
            try:
                icerik = dosya.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for cerceve in _cerceveler(icerik):
                cerceve_kelimeler = _kelimeler(" ".join(cerceve))
                if not cerceve_kelimeler or not sorgu_kelimeler:
                    continue
                ortak = len(sorgu_kelimeler & cerceve_kelimeler)
                if ortak == 0:
                    continue
                puan = ortak / len(sorgu_kelimeler)
                if en_iyi is None or puan >= en_iyi[0]:
                    en_iyi = (puan, dosya, cerceve)
        if en_iyi is None:
            return {"metin": (f"'{konu or ders}' konusuyla eşleşen geçmiş bir "
                               f"ders kaydı bulamadım, efendim.")}
        _puan, secilen, _cerceve_secilen = en_iyi
    else:
        secilen = adaylar[-1]

    try:
        icerik = secilen.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"metin": "Geçmiş ders kaydı okunamadı, efendim."}

    cerceveler = _cerceveler(icerik)
    konu_ozeti = (", ".join(f"{d} — {k}" for d, k in cerceveler if d or k)
                  or "konu belirtilmemiş")
    govde = _govde_kirp(icerik)

    first_ders = ""
    first_konu = ""
    if cerceveler:
        first_ders, first_konu = cerceveler[0]

    return {
        "metin": (
            f"[Geçmiş ders: {_tarih_etiketi(secilen)}] İşlenen konu(lar): {konu_ozeti}\n\n"
            f"Aşağıdaki metin o dersin HAM kaydıdır (kelimesi kelimesine SINIFA "
            f"OKUMA) — öğretmene kısa, konuşma diliyle bir hatırlatma yap: "
            f"'geçen ders (tarih) şunları işlemiştik: …' tarzında, 2-3 cümleyi "
            f"geçmeyecek şekilde özetle.\n\n{govde}"
        ),
        "ders": first_ders,
        "konu": first_konu
    }
