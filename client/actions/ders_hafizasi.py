"""
actions/ders_hafizasi.py — "Geçen ders ne işlemiştik" tarzı sorular için
Farabi'nin KENDİ geçmiş ders kayıtlarını (core/transcript.py) okur.

`ders_icerigi` ile farkı: ders_icerigi KİTAPTAN konu anlatımı getirir; bu
araç kitaba hiç bakmaz, yalnızca Farabi'nin bu tahtada daha önce işlediği
derslerin metin kaydına (logs/ders/*.txt) bakar. `kitap_sorusu` ile farkı:
o sunucudaki RAG'a gider, bu tamamen yerel ve çevrimdışıdır.

TASARIM (2026-08-12, kullanıcı onaylı): ayrı bir "özet" dosyası YOK — tek
kaynak `core/transcript.py`'nin ders-başına yazdığı dosyalar, iki farklı
kullanım (ders kaydı + bu hatırlama aracı). Özetleme burada YAPILMAZ; bu
araç yalnızca ilgili geçmiş dersin ham kaydını (bağlam için kırpılmış)
getirir, kısa bir özete çevirmek modelin işi — `yks_sorulari`/`kitap_sorusu`
ile aynı "ham kaynağı getir, modele özetlet" deseni.

Her ders dosyası `ÇERÇEVE: ders=… konu=…` satırlarıyla bölümlere ayrılır
(`core.transcript.log_frame`, `actions/ders_icerigi.py`'den çağrılır — hem
yazılı panelden hem sesli "Farabi, …" hitabından gelen çerçeveler aynı
noktadan geçtiği için ikisini de yakalar). `konu` verilirse en iyi eşleşen
bölüm bulunur; verilmezse en SON ders dosyasının tamamı döner.

Şu an SÜREN dersin kendi dosyası (`core.transcript.session_file()`) HER
ZAMAN hariç tutulur — Farabi kendi kendini "geçmiş ders" saymaz.

Bu araç SORU SUNUM PROTOKOLÜ'ne tabi DEĞİLDİR (bir soru sunmuyor, bir bilgi
sorgusuna cevap veriyor) — `kitap_sorusu` gibi hemen cevap verir, sessizlik
beklemez.
"""

import re
import unicodedata
from pathlib import Path

from core import transcript

MAX_KARAKTER = 6000  # ders_icerigi/yks_sorulari ile aynı bütçe

_CERCEVE_RE = re.compile(r"ÇERÇEVE: ders=(.*?) konu=(.*)")
_BASLIK_RE  = re.compile(r"^(?:#.*\n)+", re.M)
_AYIRAC_RE  = re.compile(r"^-{10,}$\n?", re.M)
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "")).translate(_TR).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _kelimeler(s: str) -> set[str]:
    """Anlamlı kelimeler (kısa bağlaçlar atılır)."""
    return {k for k in _norm(s).split() if len(k) > 3}


def _tarih_etiketi(dosya: Path) -> str:
    """Dosya adındaki zaman damgasını okunur bir etikete çevirir.
    Ayrıştıramazsa dosya adının kendisini döner — asla patlamaz."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})", dosya.stem)
    if not m:
        return dosya.stem
    yil, ay, gun, saat, dk, _sn = m.groups()
    return f"{gun}.{ay}.{yil} {saat}:{dk}"


def _gecmis_dosyalar(guncel: Path) -> list[Path]:
    """logs/ders/ altındaki tüm ders dosyaları, şu an süren oturum hariç,
    dosya adına göre (zaman damgası öneki sayesinde kronolojik) sıralı."""
    if not transcript.LOG_DIR.exists():
        return []
    dosyalar = sorted(transcript.LOG_DIR.glob("*.txt"))
    return [d for d in dosyalar if d.resolve() != guncel.resolve()]


def _cerceveler(icerik: str) -> list[tuple[str, str]]:
    """Bir dosyadaki tüm ÇERÇEVE satırlarını (ders, konu) çiftleri olarak döner."""
    return [(ders.strip(), konu.strip()) for ders, konu in _CERCEVE_RE.findall(icerik)]


def _govde_kirp(icerik: str) -> str:
    """Başlık/ayıraç satırlarını atar, MAX_KARAKTER'e kırpar."""
    govde = _AYIRAC_RE.sub("", _BASLIK_RE.sub("", icerik)).strip()
    if len(govde) > MAX_KARAKTER:
        govde = govde[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"
    return govde


def ders_hafizasi(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    ders = (p.get("ders") or "").strip()
    konu = (p.get("konu") or "").strip()

    guncel = transcript.session_file()
    adaylar = _gecmis_dosyalar(guncel)
    if not adaylar:
        return ("Bu tahtada henüz kayıtlı geçmiş bir ders yok, efendim — "
                "hatırlayabileceğim bir şey bulamadım.")

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
            return (f"'{konu or ders}' konusuyla eşleşen geçmiş bir ders kaydı "
                     f"bulamadım, efendim.")
        _puan, secilen, cerceve_secilen = en_iyi
        log(f"[Ders Hafızası] eşleşti: {secilen.name} · {cerceve_secilen}")
    else:
        secilen = adaylar[-1]
        log(f"[Ders Hafızası] konu verilmedi, en son ders: {secilen.name}")

    try:
        icerik = secilen.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "Geçmiş ders kaydı okunamadı, efendim."

    cerceveler = _cerceveler(icerik)
    konu_ozeti = (", ".join(f"{d} — {k}" for d, k in cerceveler if d or k)
                  or "konu belirtilmemiş")
    govde = _govde_kirp(icerik)

    return (
        f"[Geçmiş ders: {_tarih_etiketi(secilen)}] İşlenen konu(lar): {konu_ozeti}\n\n"
        f"Aşağıdaki metin o dersin HAM kaydıdır (kelimesi kelimesine SINIFA "
        f"OKUMA) — öğretmene kısa, konuşma diliyle bir hatırlatma yap: "
        f"'geçen ders (tarih) şunları işlemiştik: …' tarzında, 2-3 cümleyi "
        f"geçmeyecek şekilde özetle.\n\n{govde}"
    )
