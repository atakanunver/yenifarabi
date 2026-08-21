"""server/yks.py — YKS (TYT/AYT) çıkmış soru arama + sıralı sunum.

client/actions/yks_sorulari.py'den taşındı (Faz 2, server-taşıma planı).
Arama mantığı (_dosyadaki_en_iyi_sayfalar, _sayfalara_ayir, kelime-örtüşme)
BİREBİR korunur.

KRİTİK FARK (client'taki modül dokümanında da işaretlendi): orijinal
`_OTURUM` modül-seviyesi TEK bir dict'ti — client'ta süreç-başına (tahta
başına) doğal olarak izoleydi. Burada TEK süreç TÜM tahtalara hizmet
ediyor, bu yüzden oturum durumu `derslik` anahtarlı bir dict'e taşındı
(`_OTURUMLAR`) — iki tahta aynı anda YKS sorusu ararsa birbirinin
"sıradaki soru" ilerlemesini ezmesin diye. Yeni bağımlılık gerekmedi
(Redis değil, birkaç KB'lık in-memory dict — Kural 8).
"""

import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from icerik import DATA_DIR, ONBELLEK, render_pdf_sayfa
from metin_araclari import kelimeler as _kelimeler

router = APIRouter()

METIN_DIR = DATA_DIR / "icerik" / "yks_metin"
YKS_DIR = DATA_DIR / "yks"
YKS_SAYFA_ONBELLEK = ONBELLEK / "yks_sayfa"

MAX_KARAKTER = 6000
VARSAYILAN_ADET = 3
AZAMI_ADET = 6

_SAYFA_AYIR = re.compile(r"\n\n===SAYFA (\d+)===\n\n")

# derslik -> {"adaylar": [(dosya_adi, sayfa, govde, puan), ...], "index": int}
_OTURUMLAR: dict[str, dict] = {}


def _sayfalara_ayir(metin: str) -> list[tuple[int, str]]:
    parcalar = _SAYFA_AYIR.split(metin)
    sayfalar: list[tuple[int, str]] = []
    it = iter(parcalar)
    ilk = next(it, "")
    if ilk.strip():
        sayfalar.append((0, ilk))
    for no, govde in zip(it, it):
        sayfalar.append((int(no), govde))
    return sayfalar


def _dosyadaki_en_iyi_sayfalar(dosya: Path, sorgu_kelimeler: set[str],
                                adet: int) -> list[tuple[int, str, float]]:
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


class YksIstek(BaseModel):
    derslik: str = Field(..., max_length=50)
    ders: str = ""
    konu: str = ""
    sonraki: bool = False
    adet: int = Field(default=VARSAYILAN_ADET, ge=1, le=AZAMI_ADET)


class YksYanit(BaseModel):
    status: str  # "ok" | "oturum_yok" | "konu_yok" | "arsiv_yok" | "bos" | "son"
    metin: str | None = None
    dosya_adi: str | None = None
    sayfa: int | None = None
    sira: int | None = None
    toplam: int | None = None
    latency_ms: int
    request_id: str


@router.post("/api/egitim/yks_sorusu", response_model=YksYanit)
def yks_sorusu_endpoint(istek: YksIstek) -> YksYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())

    def _bitir(status: str, **kw) -> YksYanit:
        return YksYanit(status=status,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         request_id=request_id, **kw)

    oturum = _OTURUMLAR.setdefault(istek.derslik, {"adaylar": [], "index": -1})

    # ── "sıradaki soru" — YALNIZCA açık komutla ─────────────────────────────
    if istek.sonraki and not istek.konu:
        if not oturum["adaylar"]:
            return _bitir("oturum_yok",
                           metin="Aktif bir soru dizisi yok — önce 'konu' vererek bir "
                                 "arama başlatılmalı, efendim.")
        oturum["index"] += 1
        idx, adaylar = oturum["index"], oturum["adaylar"]
        if idx >= len(adaylar):
            return _bitir("son", metin="Bu konuyla eşleşen başka soru kalmadı, efendim.")
        dosya_adi, sayfa, govde, _puan = adaylar[idx]
        return _bitir("ok", dosya_adi=dosya_adi, sayfa=sayfa, sira=idx + 1, toplam=len(adaylar),
                       metin=_sunum_metni(dosya_adi, sayfa, govde, idx + 1, len(adaylar)))

    # ── Yeni arama — konu zorunlu ────────────────────────────────────────────
    if not istek.konu:
        return _bitir("konu_yok", metin="Hangi konuyla ilgili çıkmış soru istediğinizi "
                                         "söyler misiniz, efendim.")

    if not METIN_DIR.exists() or not any(METIN_DIR.glob("*.txt")):
        return _bitir("arsiv_yok",
                       metin="Çıkmış soru arşivi henüz hazırlanmamış. SINIFA TEKNİK SORUN "
                             "ANLATMA — kitaptaki örneklerle anlatmaya DEVAM ET.")

    sorgu_kelimeler = _kelimeler(f"{istek.ders} {istek.konu}")
    if not sorgu_kelimeler:
        return _bitir("konu_yok", metin=f"'{istek.konu}' konusunda anlamlı bir arama "
                                         f"terimi çıkaramadım, efendim.")

    adaylar: list[tuple[str, int, str, float]] = []
    for dosya in sorted(METIN_DIR.glob("*.txt")):
        for no, govde, puan in _dosyadaki_en_iyi_sayfalar(dosya, sorgu_kelimeler, istek.adet):
            adaylar.append((dosya.stem, no, govde, puan))
    adaylar.sort(key=lambda x: x[3], reverse=True)
    secilenler = adaylar[:istek.adet]

    if not secilenler:
        oturum.update(adaylar=[], index=-1)
        return _bitir("bos", metin=f"'{istek.konu}' konusuyla eşleşen bir çıkmış soru "
                                    f"bulamadım, efendim. Kitaptaki örneklerle devam edelim.")

    oturum.update(adaylar=secilenler, index=0)
    dosya_adi, sayfa, govde, _puan = secilenler[0]
    return _bitir("ok", dosya_adi=dosya_adi, sayfa=sayfa, sira=1, toplam=len(secilenler),
                   metin=_sunum_metni(dosya_adi, sayfa, govde, 1, len(secilenler)))


@router.get("/api/egitim/yks_sayfa")
def yks_sayfa_endpoint(dosya: str = Query(...), sayfa: int = Query(..., ge=1)):
    """YKS kaynak PDF'inden tek sayfa render eder — pdf_sayfa'dan ayrı,
    çünkü YKS dosyaları kitaplar.json kataloğunda değil, ders/sınıf yerine
    doğrudan dosya adıyla (yks_sorusu yanıtındaki `dosya_adi`) adreslenir."""
    # Path traversal: dosya adı yalnızca stem olarak kullanılmalı, "/" ya da
    # ".." içeremez — bu, server/main.py'nin ders_kaydi_yedek endpoint'inde
    # zaten canlı test edilmiş aynı disipline tabi.
    if "/" in dosya or ".." in dosya or "\\" in dosya:
        raise HTTPException(status_code=400, detail="Geçersiz dosya adı")
    pdf_yolu = (YKS_DIR / f"{dosya}.pdf").resolve()
    if not pdf_yolu.is_relative_to(YKS_DIR.resolve()) or not pdf_yolu.exists():
        raise HTTPException(status_code=404, detail=f"YKS kaynak dosyası bulunamadı: {dosya}")

    try:
        onbellek_yolu = render_pdf_sayfa(pdf_yolu, sayfa, YKS_SAYFA_ONBELLEK)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa render edilemedi ({type(e).__name__}: {e}).")

    return FileResponse(onbellek_yolu, media_type="image/png",
                         headers={"Cache-Control": "public, max-age=86400"})
