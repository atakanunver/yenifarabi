"""
actions/yks_sorulari.py — Konuyla ilgili YKS (TYT/AYT) çıkmış sorularını
PDF SAYFASI olarak (görüntü, bütünlük korunarak) gösterir, TEK SEFERDE TEK
SORU — sıradaki soruya yalnızca açık bir komutla geçilir.

YKS/ klasörüne atılan geçmiş sınav PDF'leri `tools/yks_metin.py` ile
çevrimdışı, API'siz düz metne çevrilir (`icerik/yks_metin/<dosya>.txt`,
sayfa işaretli — `===SAYFA n===`, PDF'in kendi 1-indeksli sayfa numarası).
Bu araç o metni konuyla eşleştirmek için okur (kelime örtüşmesi), ama
GÖSTERİM için asıl PDF'in o sayfasını `pdf_sayfa.py`'nin render fonksiyonuyla
görüntüye çevirir — soru metne dönüştürülüp yeniden akıtılmaz, sınav
PDF'lerindeki şekil/tablo/denklem olduğu gibi kalır.

SORUNUN KENDİSİ ham PDF metnidir, ÇÖZÜM İÇERMEZ — kaynak PDF'ler "tamamı
video çözümlü" diye pazarlanan derlemeler, yazılı çözüm taşımıyor. Çözümü/
doğru şıkkı üretmek modelin işi: `aciklama` (actions/kayit.py) ve
core/prompt.txt'teki SORU SUNUM PROTOKOLÜ modele bunu sınıfa okuyup adım
adım çözmesini, ARADA SUS'up beklemesini söyler.

SIRALI SUNUM (2026-08-12 eklendi) — kullanıcı isteği: "komut gelmeden
sıradaki soruya asla geçilmesin". Bir konu arandığında eşleşen adaylardan
İLKİ gösterilir ve modül-seviyesi `_OTURUM` içinde saklanır (süreç ömrü
boyunca, `_METIN_ONBELLEK` gibi diğer önbellek desenleriyle aynı). Bir
SONRAKİ soru YALNIZCA `sonraki=true` ile açıkça istenirse gösterilir — bu
da yalnızca core/prompt.txt'in SESLİ HİTAP/SORU SUNUM PROTOKOLÜ kurallarına
göre öğretmen komutu (`[ÖĞRETMEN KOMUTU]` ya da sesli "Farabi, …") geldiğinde
modelin kendi kendine çağırdığı bir yol — kod bunu ZORLAMAZ (Gemini Live'ın
kendisi karar verir), yalnızca "hangi soru sırada" durumunu tutar.

İndeks yoksa (tools/yks_metin.py hiç çalıştırılmamış) araç DOĞAÇLAMA YAPMAZ:
sınırlı bir mesajla döner — bkz. ders_icerigi.py'deki aynı ilke.

Hazırlık (çalışma anında değil, bir kez):
    python tools/yks_metin.py YKS/ --txt icerik/yks_metin
"""

import re
import unicodedata
from pathlib import Path

from actions.pdf_sayfa import render_pdf_sayfa

BASE_DIR  = Path(__file__).resolve().parent.parent
METIN_DIR = BASE_DIR / "icerik" / "yks_metin"
YKS_DIR   = BASE_DIR / "YKS"
ONBELLEK_DIR = BASE_DIR / "icerik" / "onbellek" / "yks_sayfa"

# ders_icerigi ile aynı bütçe (~1.500 token) — personayı bastırmasın.
MAX_KARAKTER    = 6000
VARSAYILAN_ADET = 3
AZAMI_ADET      = 6

_SAYFA_AYIR = re.compile(r"\n\n===SAYFA (\d+)===\n\n")
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# Süreç ömrü boyunca bir "soru dizisi" oturumu — sıradaki soruya yalnızca
# açık komutla geçmek için. Bkz. modül dokümanı.
_OTURUM: dict = {"adaylar": [], "index": -1}


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


def _sunum_metni(dosya_adi: str, sayfa: int, govde: str, sira: int, toplam: int) -> str:
    kirpildi_govde = govde
    if len(kirpildi_govde) > MAX_KARAKTER:
        kirpildi_govde = kirpildi_govde[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"

    kalan = toplam - sira
    if kalan > 0:
        ilerleme_notu = (
            f"{kalan} soru daha eşleşti ama KOMUT GELMEDEN sıradakine "
            f"kendiliğinden GEÇME; öğretmen (sesli adınla ya da yazılı "
            f"panelden) 'sıradaki soru' derse `yks_sorulari`'ni "
            f"`sonraki: true` ile yeniden çağır."
        )
    else:
        ilerleme_notu = "Bu, eşleşen son soruydu."

    return (
        f"[{sira}/{toplam}. eşleşen soru] Kaynak: {dosya_adi} · sayfa {sayfa}\n"
        f"Soru sayfa GÖRÜNTÜSÜ olarak ekranda (PDF bütünlüğü korunuyor, metne "
        f"çevrilmedi). Aşağıdaki metin YALNIZCA senin okuman için (ham PDF "
        f"metni; dizgi kaynaklı küçük bozukluklar olabilir, ÇÖZÜM İÇERMEZ):\n\n"
        f"{kirpildi_govde}\n\n"
        f"SORU SUNUM PROTOKOLÜ'nü izle: soruyu ve varsa şıkları sözlü oku, "
        f"sonra SUS — cevap ya da öğretmen komutu gelene kadar BEKLE, çözümü "
        f"hemen anlatma. {ilerleme_notu}"
    )


def _sayfayi_goster(player, log, dosya_adi: str, sayfa: int) -> str | None:
    """PDF sayfasını render edip `player.show_image` ile gösterir. Başarısız
    olursa None döner (görüntü olmadan, yalnızca metinle devam edilir —
    sınıfa teknik sorun anlatılmaz, bkz. mimari.md §2)."""
    pdf_yolu = YKS_DIR / f"{dosya_adi}.pdf"
    if not pdf_yolu.exists():
        log(f"[YKS] kaynak PDF bulunamadı: {pdf_yolu.name}")
        return None
    try:
        onbellek_yolu = render_pdf_sayfa(pdf_yolu, sayfa, ONBELLEK_DIR)
    except Exception as e:
        log(f"[YKS] sayfa render hatası: {type(e).__name__}: {e}")
        return None
    if player is not None and hasattr(player, "show_image"):
        player.show_image(f"YKS — {dosya_adi[:24]} s.{sayfa}", str(onbellek_yolu))
    return str(onbellek_yolu)


def yks_sorulari(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    sonraki = bool(p.get("sonraki"))
    konu = (p.get("konu") or "").strip()
    ders = (p.get("ders") or "").strip()

    # ── "sıradaki soru" — YALNIZCA açık komutla, yeni arama başlatmaz ──────
    if sonraki and not konu:
        if not _OTURUM["adaylar"]:
            return ("Aktif bir soru dizisi yok — önce 'konu' vererek bir "
                    "arama başlatılmalı, efendim.")
        _OTURUM["index"] += 1
        idx, adaylar = _OTURUM["index"], _OTURUM["adaylar"]
        if idx >= len(adaylar):
            return "Bu konuyla eşleşen başka soru kalmadı, efendim."
        dosya_adi, sayfa, govde, _puan = adaylar[idx]
        log(f"[YKS] sıradaki soru: {idx + 1}/{len(adaylar)} · {dosya_adi} s.{sayfa}")
        _sayfayi_goster(player, log, dosya_adi, sayfa)
        return _sunum_metni(dosya_adi, sayfa, govde, idx + 1, len(adaylar))

    # ── Yeni arama — `konu` zorunlu ─────────────────────────────────────────
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

    try:
        adet = int(p.get("adet") or VARSAYILAN_ADET)
    except (TypeError, ValueError):
        adet = VARSAYILAN_ADET
    adet = max(1, min(adet, AZAMI_ADET))

    log(f"[YKS] Aranıyor: {konu}")

    adaylar: list[tuple[str, int, str, float]] = []
    for dosya in sorted(METIN_DIR.glob("*.txt")):
        for no, govde, puan in _dosyadaki_en_iyi_sayfalar(dosya, sorgu_kelimeler, adet):
            adaylar.append((dosya.stem, no, govde, puan))

    adaylar.sort(key=lambda x: x[3], reverse=True)
    secilenler = adaylar[:adet]

    if not secilenler:
        _OTURUM.update(adaylar=[], index=-1)
        return (
            f"'{konu}' konusuyla eşleşen bir çıkmış soru bulamadım, efendim. "
            f"Kitaptaki örneklerle devam edelim."
        )

    _OTURUM.update(adaylar=secilenler, index=0)

    dosya_adi, sayfa, govde, _puan = secilenler[0]
    log(f"[YKS] {len(secilenler)} soru eşleşti, ilk soru gösteriliyor: "
        f"{dosya_adi} s.{sayfa}")
    _sayfayi_goster(player, log, dosya_adi, sayfa)
    return _sunum_metni(dosya_adi, sayfa, govde, 1, len(secilenler))
