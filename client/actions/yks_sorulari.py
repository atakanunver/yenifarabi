"""
actions/yks_sorulari.py — Konuyla ilgili YKS (TYT/AYT) çıkmış sorularını getirir.

YKS/ klasörüne atılan geçmiş sınav PDF'leri `tools/yks_metin.py` ile
çevrimdışı, API'siz düz metne çevrilir (`icerik/yks_metin/<dosya>.txt`,
sayfa işaretli). Bu araç o metni okur, konuyla en çok kelime örtüşen
sayfaları seçer ve olduğu gibi döndürür.

SORUNUN KENDİSİ ham PDF metnidir, ÇÖZÜM İÇERMEZ — kaynak PDF'ler "tamamı
video çözümlü" diye pazarlanan derlemeler, yazılı çözüm taşımıyor. Çözümü/
doğru şıkkı üretmek modelin işi: `aciklama` (actions/kayit.py) modele bunu
sınıfa okuyup adım adım çözmesini söyler.

İndeks yoksa (tools/yks_metin.py hiç çalıştırılmamış) araç DOĞAÇLAMA YAPMAZ:
sınırlı bir mesajla döner — bkz. ders_icerigi.py'deki aynı ilke.

Hazırlık (çalışma anında değil, bir kez):
    python tools/yks_metin.py YKS/ --txt icerik/yks_metin
"""

import re
import unicodedata
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent
METIN_DIR = BASE_DIR / "icerik" / "yks_metin"

# ders_icerigi ile aynı bütçe (~1.500 token) — personayı bastırmasın.
MAX_KARAKTER    = 6000
VARSAYILAN_ADET = 3
AZAMI_ADET      = 6

_SAYFA_AYIR = re.compile(r"\n\n===SAYFA (\d+)===\n\n")
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "")).translate(_TR).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _kelimeler(s: str) -> set[str]:
    """Anlamlı kelimeler (kısa bağlaçlar atılır)."""
    return {k for k in _norm(s).split() if len(k) > 3}


def _sayfalara_ayir(metin: str) -> list[tuple[int, str]]:
    """'===SAYFA n===' işaretleriyle bölünmüş metni (sayfa_no, metin) çiftlerine ayır."""
    parcalar = _SAYFA_AYIR.split(metin)
    sayfalar: list[tuple[int, str]] = []
    it = iter(parcalar)
    ilk = next(it, "")
    if ilk.strip():
        sayfalar.append((0, ilk))
    for no, govde in zip(it, it):
        sayfalar.append((int(no), govde))
    return sayfalar


def _dosyadaki_en_iyi_sayfalar(
    dosya: Path, sorgu_kelimeler: set[str], adet: int
) -> list[tuple[int, str, float]]:
    try:
        metin = dosya.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    sonuclar = []
    for no, govde in _sayfalara_ayir(metin):
        sayfa_kelimeler = _kelimeler(govde)
        if not sayfa_kelimeler:
            continue
        ortak = len(sorgu_kelimeler & sayfa_kelimeler)
        if ortak == 0:
            continue
        puan = ortak / len(sorgu_kelimeler)
        sonuclar.append((no, govde.strip(), puan))
    sonuclar.sort(key=lambda x: x[2], reverse=True)
    return sonuclar[:adet]


def yks_sorulari(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    konu = (p.get("konu") or "").strip()
    ders = (p.get("ders") or "").strip()
    try:
        adet = int(p.get("adet") or VARSAYILAN_ADET)
    except (TypeError, ValueError):
        adet = VARSAYILAN_ADET
    adet = max(1, min(adet, AZAMI_ADET))

    if not konu:
        return "Hangi konuyla ilgili çıkmış soru istediğinizi söyler misiniz, efendim."

    if not METIN_DIR.exists() or not any(METIN_DIR.glob("*.txt")):
        return (
            "Çıkmış soru arşivi henüz hazırlanmamış "
            "(`python tools/yks_metin.py YKS/ --txt icerik/yks_metin` "
            "çalıştırılmalı). SINIFA TEKNİK SORUN ANLATMA — kitaptaki "
            "örneklerle anlatmaya DEVAM ET."
        )

    sorgu_kelimeler = _kelimeler(f"{ders} {konu}")
    if not sorgu_kelimeler:
        return f"'{konu}' konusunda anlamlı bir arama terimi çıkaramadım, efendim."

    log(f"[YKS] Aranıyor: {konu}")

    adaylar: list[tuple[str, int, str, float]] = []
    for dosya in sorted(METIN_DIR.glob("*.txt")):
        for no, govde, puan in _dosyadaki_en_iyi_sayfalar(dosya, sorgu_kelimeler, adet):
            adaylar.append((dosya.stem, no, govde, puan))

    adaylar.sort(key=lambda x: x[3], reverse=True)
    secilenler = adaylar[:adet]

    if not secilenler:
        return (
            f"'{konu}' konusuyla eşleşen bir çıkmış soru bulamadım, efendim. "
            f"Kitaptaki örneklerle devam edelim."
        )

    parcalar = [
        f"[{i}] Kaynak: {dosya_adi} · sayfa {no}\n{govde}"
        for i, (dosya_adi, no, govde, _puan) in enumerate(secilenler, 1)
    ]
    govde_metin = "\n\n".join(parcalar)
    kirpildi = len(govde_metin) > MAX_KARAKTER
    if kirpildi:
        govde_metin = govde_metin[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"

    onek = (
        f"'{konu}' konusuyla ilgili YKS arşivinden {len(secilenler)} soru sayfası "
        f"bulundu (ham PDF metni; dizgi kaynaklı küçük bozukluklar olabilir, "
        f"ÇÖZÜM İÇERMEZ). SORU SUNUM PROTOKOLÜ'nü izle: sınıfa sırayla oku (soru "
        f"+ varsa şıklar), sonra SUS ve cevap ya da öğretmen komutu gelene kadar "
        f"BEKLE — çözümü hemen anlatma.\n\n"
    )
    sonuc = onek + govde_metin

    baslik = f"📝 Çıkmış Sorular — {konu[:40]}"
    if player is not None and hasattr(player, "show_content"):
        player.show_content(baslik, sonuc)

    return sonuc
