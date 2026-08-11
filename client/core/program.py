"""
core/program.py — Okulun ders programı: gün × ders saati × sınıf → hangi ders.

Neden var
---------
Bu veri hiçbir yerde yoktu. `config/zil.json` yalnızca zil saatlerini biliyor,
yıllık plan ise bir tarihe aynı anda dokuz ders düşürüyor (10. sınıf için
biyoloji, coğrafya, felsefe, fizik, kimya, matematik, tarih, TDE…). Sonuç:
Farabi sınıfa "bugün hangi dersteyiz?" diye soruyordu. Öğretmen bunu istemez;
tahta açıldığında **bilmelidir**:

    30 Temmuz · 3. ders · 9-A · Matematik · Üslü Sayılar

Eksik olan halka kod değil VERİYDİ. Okulun programı zaten var (idare yapıyor);
buraya bir kez yazılır.

Biçim (`config/ders_programi.json`)
-----------------------------------
    {
      "siniflar": {
        "9-A": {
          "pazartesi": {"1": "matematik", "2": "fizik"},
          "sali":      {"1": "matematik",
                        "7": {"ders": "matematik", "kip": "ogretmensiz"}}
        }
      }
    }

- Ders saati anahtarı `zil.json`'daki ders numarasıyla aynıdır.
- Bir saat yazılmamışsa o saat boştur (Farabi çerçeveyi plandan tahmin eder).
- Bir slot `kip` taşıyabilir: etüt, telafi ve boş dersler `ogretmensiz`'dir
  (kip ders programından türer).
"""

import json
from datetime import datetime
from pathlib import Path

from core import tahta, zil
from core.logger import get_logger

log = get_logger("program")

BASE_DIR     = Path(__file__).resolve().parent.parent
PROGRAM_PATH = BASE_DIR / "config" / "ders_programi.json"

# datetime.weekday() -> dosyadaki anahtar
GUN_ANAHTARI = ["pazartesi", "sali", "carsamba", "persembe", "cuma",
                "cumartesi", "pazar"]

# Dosyada "salı", "çarşamba" gibi Türkçe harfli yazımlar da kabul edilsin.
_ES_ANLAM = {
    "pazartesi": "pazartesi",
    "salı": "sali", "sali": "sali",
    "çarşamba": "carsamba", "carsamba": "carsamba",
    "perşembe": "persembe", "persembe": "persembe",
    "cuma": "cuma",
    "cumartesi": "cumartesi",
    "pazar": "pazar",
}


def cizelge() -> dict | None:
    """
    Ders programı dosyasını oku. Yoksa, bozuksa ya da HÂLÂ ÖRNEK ise None.

    `_ornek: true` taşıyan dosya kullanılmaz ve bu bilinçlidir: uydurma bir
    programla çalışmak, programsız çalışmaktan tehlikelidir. Farabi programa
    bakıp sınıfa "şu an 3. ders, matematik" diyor; veri örnekse bunu
    kendinden emin biçimde YANLIŞ söyler ve kimse fark etmez. Program yoksa
    ise dersi sınıfa sorar — dürüst davranış budur.
    """
    try:
        veri = json.loads(PROGRAM_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(veri, dict) and veri.get("_ornek"):
        log.warning("config/ders_programi.json HÂLÂ ÖRNEK verisi taşıyor "
                    "('_ornek': true). Okulun gerçek programı yazılıp bu satır "
                    "silinene kadar ders programı KULLANILMAYACAK; Farabi hangi "
                    "derste olduğunu sınıfa soracak.")
        return None
    return veri


def _gun_anahtari(simdi: datetime) -> str:
    return GUN_ANAHTARI[simdi.weekday()]


def _sinif_programi(sinif: str | None = None) -> dict | None:
    """Bu tahtanın sınıfına ait haftalık program."""
    c = cizelge()
    if not c:
        return None
    hedef = (sinif or tahta.derslik() or "").strip().upper()
    if not hedef:
        return None
    siniflar = c.get("siniflar") or {}
    for ad, program in siniflar.items():
        if str(ad).strip().upper() == hedef:
            return program
    return None


def _gunun_slotlari(program: dict, simdi: datetime) -> dict:
    """Gün adını esnek eşleştir ('salı' da olur, 'sali' da)."""
    istenen = _gun_anahtari(simdi)
    for ad, slotlar in program.items():
        if _ES_ANLAM.get(str(ad).strip().lower()) == istenen:
            return slotlar or {}
    return {}


def _slot_coz(ham) -> dict:
    """Slot ya düz ders adıdır ya da {'ders': ..., 'kip': ...} sözlüğü."""
    if isinstance(ham, dict):
        return {"ders": str(ham.get("ders", "")).strip(),
                "kip":  (str(ham.get("kip", "")).strip().lower() or None)}
    return {"ders": str(ham or "").strip(), "kip": None}


def simdiki_ders(simdi: datetime | None = None,
                 sinif: str | None = None) -> dict | None:
    """
    Şu an hangi ders? Program yoksa, gün yazılmamışsa ya da o saat boşsa None
    döner — o durumda Farabi bugünkü gibi çerçeveyi plandan çözer ve gerekirse
    sınıfa sorar. Program dosyası olmayan bir tahta ders yapamaz hâle gelmemeli.
    """
    simdi = simdi or datetime.now()
    program = _sinif_programi(sinif)
    if not program:
        return None

    durum = zil.ders_durumu(simdi)
    if durum.get("tur") != "ders" or not durum.get("ders_no"):
        return None

    slotlar = _gunun_slotlari(program, simdi)
    ham = slotlar.get(str(durum["ders_no"]))
    if ham is None:
        return None

    slot = _slot_coz(ham)
    if not slot["ders"]:
        return None

    slot.update({
        "ders_no":  durum["ders_no"],
        "kalan_dk": durum.get("kalan_dk"),
        "sinif":    (sinif or tahta.derslik() or "").strip(),
    })
    return slot


def gunun_programi(simdi: datetime | None = None,
                   sinif: str | None = None) -> list[dict]:
    """Bugünün bütün saatleri — arayüzde ve öğretmen panelinde göstermek için."""
    simdi = simdi or datetime.now()
    program = _sinif_programi(sinif)
    if not program:
        return []
    slotlar = _gunun_slotlari(program, simdi)
    sonuc = []
    for no, ham in sorted(slotlar.items(), key=lambda kv: int(kv[0])):
        slot = _slot_coz(ham)
        if slot["ders"]:
            sonuc.append({"ders_no": int(no), **slot})
    return sonuc


def kip(simdi: datetime | None = None, sinif: str | None = None) -> str | None:
    """
    O saatin ders kipi. Program söylemiyorsa None — çağıran config'e düşer.

    Etüt ve telafi saatlerinde sınıfta öğretmen yoktur; bunu programdan bilmek,
    her hafta config dosyası düzenlemekten iyidir.
    """
    slot = simdiki_ders(simdi, sinif)
    return slot.get("kip") if slot else None


def etiket(simdi: datetime | None = None, sinif: str | None = None) -> str:
    """Arayüz için tek satır: '3. ders · Matematik'. Yoksa boş dize."""
    slot = simdiki_ders(simdi, sinif)
    if not slot:
        return ""
    return f"{slot['ders_no']}. ders · {slot['ders'].title()}"
