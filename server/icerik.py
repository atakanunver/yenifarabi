"""server/icerik.py — kitap sayfa metni + PDF sayfa render.

client/actions/ders_icerigi.py ve client/actions/pdf_sayfa.py'den taşındı
(Farabi Kural 1: "client ince kalmalı, ağır iş sunucuda" — planlanan
server-taşıma, Faz 2). Eşleştirme mantığı (_bolum_bul, _esleme_bolumu,
_ilgili_sayfalar, render_pdf_sayfa) BİREBİR korunur — yalnızca dosya
konumları client/'a göreli değil DATA_DIR'e (kanonik NAS-benzeri konum,
/mnt/farabi-data/farabi) göreli, ve PyQt/player bağımlılığı kalkıp HTTP
request/response'a dönüştü.

"Brain karar verir, Client görüntüler" ilkesi (RAG endpoint'iyle aynı
ruhta): endpoint modele/sınıfa okunacak NİHAİ metni üretir, client yalnızca
bunu döndürür — eşleştirme/kırpma/uyarı mantığını client'ta tekrarlamaz.
"""

import json
import time
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import auth
from metin_araclari import kelimeler as _kelimeler
from metin_araclari import norm as _norm

# FAZ 1 (IMPLEMENT) — tek satır: bu router'daki TÜM route'lar artık
# auth.dogrula_tahta'dan geçer (server/auth.py). Endpoint fonksiyonlarının
# kendisi değişmedi.
router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

DATA_DIR = Path("/mnt/farabi-data/farabi")
KITAP_PATH = DATA_DIR / "icerik" / "kitaplar.json"
ONBELLEK = DATA_DIR / "icerik" / "onbellek"
ESLEME_DIR = DATA_DIR / "icerik" / "eslemeler"
METIN_DIZINI = DATA_DIR / "icerik" / "metin"
OZET_DIZINI = DATA_DIR / "icerik" / "ozet"
PDF_SAYFA_ONBELLEK = ONBELLEK / "pdf_sayfa"
YKS_SAYFA_ONBELLEK = ONBELLEK / "yks_sayfa"
SAYFA_ONBELLEK = ONBELLEK / "_sayfa_secimi.json"

MAX_KARAKTER = 6000
VARSAYILAN_SAYFA = 6
TARAMA_SINIRI = 60
ZOOM = 2.0

_SINIRLI_DEVAM = (
    "KISIT: Kitap sayfası getirilemedi. Elindeki plan ve kazanım metni "
    "çerçevendir; onun dışına çıkma ve kitapta olmayan sayfa/alıntı UYDURMA. "
    "Sınıfa teknik sorun anlatma. Anlatıma devam et: konuyu kazanım metnine "
    "sadık kalarak `web_search` ile araştırıp derinleştirebilirsin — kitap "
    "zaten iskelet verir, anlatım senindir. Kitap sayfası gerçekten gerekiyorsa "
    "ders_icerigi'ni farklı bir tema ya da konu adıyla yeniden çağır."
)

_GORUNEN_AD = {
    "BIYOLOJI":            "Biyoloji",
    "COGRAFYA":            "Coğrafya",
    "FELSEFE":             "Felsefe",
    "FIZIK":               "Fizik",
    "KIMYA":               "Kimya",
    "MATEMATIK":           "Matematik",
    "MATEMATIK TD":        "Temel Düzey Matematik",
    "TARIH":               "Tarih",
    "TDE":                 "Türk Dili ve Edebiyatı",
    "TDE SBL":             "Türk Dili ve Edebiyatı",
    "T C INKILAP TARIHI":  "T.C. İnkılap Tarihi ve Atatürkçülük",
    "DIN KULTURU":         "Din Kültürü ve Ahlak Bilgisi",
    "HAZIRLIK MATEMATIK":  "Hazırlık Matematik",
    "HAZIRLIK TDE":        "Hazırlık Türk Dili ve Edebiyatı",
    "HAZIRLIK TDE SBL":    "Hazırlık Türk Dili ve Edebiyatı",
}


def _ders_eslesir(sorgu: str | None, hedef: str) -> bool:
    if not sorgu:
        return True
    h = _norm(hedef)
    kelimeler = [k for k in _norm(sorgu).split() if k]
    return all(k in h for k in kelimeler) if kelimeler else True


def _json_oku(yol: Path):
    if not yol.exists():
        return None
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return None


def gorunen_ad(ders_kodu: str) -> str:
    kod = (ders_kodu or "").strip().upper()
    return _GORUNEN_AD.get(kod, kod.title())


def _katalog(kitaplar: dict, ders: str | None, sinif: str | None) -> str:
    satirlar: list[str] = []
    kts = []
    for k in kitaplar.get("kitaplar", []):
        if sinif and k.get("sinif") is not None and str(k["sinif"]) != str(sinif).strip():
            continue
        if not _ders_eslesir(ders, k.get("ders", "")):
            continue
        kts.append(k)

    if not kts:
        tumu = sorted({k.get("dosya", "") for k in kitaplar.get("kitaplar", [])})
        satirlar.append("Aradığın ders/sınıf için indekslenmiş kitap bulunamadı.")
        satirlar.append(f"Elimdeki kitaplar ({len(tumu)} adet):")
        satirlar += [f"  - {t}" for t in tumu[:40]]
        if len(tumu) > 40:
            satirlar.append(f"  … ve {len(tumu)-40} tane daha")
        return "\n".join(satirlar)

    satirlar.append("İndekslenmiş kitaplar:")
    for k in kts:
        bolumler = ", ".join(
            f"{b['no']}.{b['tur']} {b.get('ad','')[:26]}" for b in k.get("bolumler", [])[:8])
        satirlar.append(f"  - {k['dosya']} ({k.get('sayfa_sayisi','?')} sayfa): {bolumler}")

    satirlar.append("\nBir bölümü işlemek için konu ya da tema adını söyle.")
    return "\n".join(satirlar)


def _elle_eslemeler() -> list[dict]:
    kayitlar = []
    try:
        dosyalar = sorted(ESLEME_DIR.glob("*.json"))
    except Exception:
        return kayitlar
    for yol in dosyalar:
        veri = _json_oku(yol)
        if isinstance(veri, dict) and veri.get("bolumler"):
            kayitlar.append(veri)
    return kayitlar


def _kitap_kaydi(kitaplar: dict, esleme: dict) -> dict | None:
    dosya = esleme.get("kitap", "")
    for k in kitaplar.get("kitaplar", []):
        if k.get("dosya") == dosya:
            return {**k, "ders": esleme.get("ders", k.get("ders", "")),
                    "sinif": esleme.get("sinif", k.get("sinif"))}
    yol = DATA_DIR / "kitaplar" / dosya
    if not yol.exists():
        return None
    return {"dosya": dosya, "yol": str(yol), "ders": esleme.get("ders", ""),
            "sinif": esleme.get("sinif")}


def _esleme_bolumu(kitaplar: dict, tema: str, ders: str | None,
                    sinif: str | None) -> tuple[dict, dict] | None:
    tema_n = _norm(tema)
    tema_k = _kelimeler(tema)
    if not tema_n:
        return None
    for esleme in _elle_eslemeler():
        if sinif and str(esleme.get("sinif", "")).strip() and \
                str(esleme["sinif"]).strip() != str(sinif).strip():
            continue
        if not _ders_eslesir(ders, esleme.get("ders", "")):
            continue
        for bolum in esleme.get("bolumler", []):
            adaylar = [bolum.get("ad", "")] + list(bolum.get("temalar") or [])
            for aday in adaylar:
                aday_n = _norm(aday)
                if not aday_n:
                    continue
                ortak = tema_k & _kelimeler(aday)
                if aday_n == tema_n or (tema_k and len(ortak) / len(tema_k) >= 0.5):
                    kitap = _kitap_kaydi(kitaplar, esleme)
                    if kitap:
                        return kitap, {
                            "no":        bolum.get("no", 0),
                            "tur":       bolum.get("tur", "Bölüm"),
                            "ad":        bolum.get("ad", aday),
                            "ilk_sayfa": int(bolum["ilk_sayfa"]),
                            "son_sayfa": int(bolum["son_sayfa"]),
                            "yontem":    bolum.get("yontem", "metin"),
                        }
    return None


def _bolum_bul(kitaplar: dict, tema: str, ders: str | None,
               sinif: str | None) -> tuple[dict, dict] | None:
    elle = _esleme_bolumu(kitaplar, tema, ders, sinif)
    if elle:
        return elle
    tema_k = _kelimeler(tema)
    if not tema_k:
        return None
    en_iyi, en_iyi_puan = None, 0.0
    for kitap in kitaplar.get("kitaplar", []):
        if sinif and kitap.get("sinif") is not None:
            if str(kitap["sinif"]) != str(sinif).strip():
                continue
        if not _ders_eslesir(ders, kitap.get("ders", "")):
            continue
        for bolum in kitap.get("bolumler", []):
            ortak = tema_k & _kelimeler(bolum.get("ad", ""))
            if not ortak:
                continue
            puan = len(ortak) / len(tema_k)
            if puan > en_iyi_puan:
                en_iyi, en_iyi_puan = (kitap, bolum), puan
    return en_iyi if en_iyi_puan >= 0.5 else None


# derslik -> {ders(norm): dosya} — bir tahtada ders_icerigi'nin konuya göre
# SEÇTİĞİ kitabı hatırlar, pdf_sayfa aynı ders için birden çok kitap (ör.
# matematik_9.pdf/matematik_9_2.pdf, cilt 1/cilt 2) varken doğru cildi
# göstersin diye (bkz. _kitap_bul, aşağıda — 2026-08-30 hata: 9-A'da konu
# cilt 2'deydi, ders_icerigi doğru cildi okuyordu ama pdf_sayfa hep cilt
# 1'den sayfa gösteriyordu, aynı sayfa numarası iki kitapta bambaşka içerik).
_SON_KITAP: dict[str, dict[str, str]] = {}

_METIN_ONBELLEK: dict[str, dict] = {}


def _kitap_metni(pdf_yolu: Path) -> dict | None:
    ad = pdf_yolu.stem
    if ad in _METIN_ONBELLEK:
        return _METIN_ONBELLEK[ad]
    veri = _json_oku(METIN_DIZINI / f"{ad}.json")
    if veri and veri.get("sayfalar"):
        _METIN_ONBELLEK[ad] = veri
        return veri
    return None


def _kitap_ozeti(kitap_dosyasi: str) -> str:
    if not kitap_dosyasi:
        return ""
    veri = _json_oku(OZET_DIZINI / f"{Path(kitap_dosyasi).stem}.json")
    if not veri:
        return ""
    return (veri.get("ozet") or "").strip()


def _sayfa_onbellek_oku() -> dict:
    try:
        return json.loads(SAYFA_ONBELLEK.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sayfa_onbellek_yaz(harita: dict) -> None:
    try:
        ONBELLEK.mkdir(parents=True, exist_ok=True)
        SAYFA_ONBELLEK.write_text(json.dumps(harita, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    except Exception:
        pass


def _ilgili_sayfalar(pdf_yolu: Path, ilk: int, son: int, konu: str,
                      adet: int) -> list[int]:
    konu_k = _kelimeler(konu)
    if not konu_k:
        return list(range(ilk, min(son, ilk + adet - 1) + 1))

    anahtar = f"{pdf_yolu.name}|{ilk}-{son}|{_norm(konu)}|{adet}"
    onb = _sayfa_onbellek_oku()
    if anahtar in onb:
        return onb[anahtar]

    puanlar = []
    kitap_metni = _kitap_metni(pdf_yolu)
    if kitap_metni:
        sayfalar_v = kitap_metni["sayfalar"]
        for n in range(ilk, son + 1):
            kayit = sayfalar_v.get(str(n))
            if not kayit:
                continue
            metin = _norm(kayit.get("metin", ""))
            puanlar.append((sum(metin.count(k) for k in konu_k), n))
    else:
        import pdfplumber
        with pdfplumber.open(pdf_yolu) as pdf:
            son_gercek = min(son, len(pdf.pages))
            toplam = max(0, son_gercek - ilk + 1)
            adim = max(1, -(-toplam // TARAMA_SINIRI))
            for n in range(ilk, son_gercek + 1, adim):
                try:
                    metin = _norm(pdf.pages[n - 1].extract_text() or "")
                except Exception:
                    continue
                puanlar.append((sum(metin.count(k) for k in konu_k), n))

    if not puanlar or max(p for p, _ in puanlar) == 0:
        secim = list(range(ilk, min(son, ilk + adet - 1) + 1))
    else:
        en_iyi = sorted(puanlar, reverse=True)[:adet]
        secim = sorted(n for _, n in en_iyi)

    onb[anahtar] = secim
    _sayfa_onbellek_yaz(onb)
    return secim


def _metin_cikar(pdf_yolu: Path, sayfalar: list[int]) -> tuple[str, int]:
    kitap_metni = _kitap_metni(pdf_yolu)
    parcalar, supheli = [], 0

    if kitap_metni:
        for n in sayfalar:
            kayit = kitap_metni["sayfalar"].get(str(n))
            if not kayit:
                continue
            t = (kayit.get("metin") or "").strip()
            if t:
                parcalar.append(f"[s.{n}]\n{t}")
                supheli += int(kayit.get("supheli") or 0)
        return "\n\n".join(parcalar), supheli

    import pdfplumber
    with pdfplumber.open(pdf_yolu) as pdf:
        for n in sayfalar:
            if n - 1 >= len(pdf.pages):
                continue
            t = (pdf.pages[n - 1].extract_text() or "").strip()
            if t:
                parcalar.append(f"[s.{n}]\n{t}")
    return "\n\n".join(parcalar), supheli


def _kitap_yolu_coz(kitap: dict) -> Path:
    yol = Path(kitap["yol"])
    return yol if yol.is_absolute() else DATA_DIR / yol


# ── /api/egitim/ders_icerigi ────────────────────────────────────────────────

class KonuIstek(BaseModel):
    ders: str = ""
    sinif: str | None = None
    konu: str = ""
    tema: str = ""
    sayfa_adedi: int = Field(default=VARSAYILAN_SAYFA, ge=1, le=12)
    liste: bool = False
    # derslik: pdf_sayfa'nın AYNI ders için doğru kitabı (bkz. _SON_KITAP,
    # üstte) seçebilmesi için — auth kimliği (server/auth.py) henüz client'a
    # bağlanmadı (2026-08-30 doğrulandı: client hiç X-Farabi-Board-Key
    # göndermiyor), bu yüzden yks.py'nin `istek.derslik` deseniyle aynı
    # şekilde doğrudan client'tan alınır, auth'a bağımlı değil.
    derslik: str | None = None


class KonuYanit(BaseModel):
    status: str  # "ok" | "liste" | "bulunamadi" | "hata"
    metin: str | None = None
    baslik: str | None = None       # player.show_content başlığı (client bunu kullanır)
    latency_ms: int
    request_id: str


@router.post("/api/egitim/ders_icerigi", response_model=KonuYanit)
def ders_icerigi_endpoint(istek: KonuIstek) -> KonuYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())

    def _bitir(status: str, metin: str | None, baslik: str | None = None) -> KonuYanit:
        return KonuYanit(status=status, metin=metin, baslik=baslik,
                          latency_ms=int((time.perf_counter() - t0) * 1000),
                          request_id=request_id)

    kitaplar = _json_oku(KITAP_PATH)
    if kitaplar is None:
        raise HTTPException(status_code=503, detail="Kitap indeksi bulunamadı (icerik/kitaplar.json yok)")

    ders = istek.ders.strip() or None
    sinif = istek.sinif.strip() if istek.sinif else None
    konu = istek.konu.strip()
    tema = istek.tema.strip()

    if istek.liste:
        return _bitir("liste", _katalog(kitaplar, ders, sinif), "MÜFREDAT — ELDEKİLER")

    sorgu = tema or konu
    if not sorgu:
        return _bitir("bulunamadi",
                       "Konu belirtilmedi. Öğretmenin verdiği konuyu 'konu' "
                       "parametresiyle ver. Elimde ne olduğunu aşağıda listeliyorum.\n\n"
                       + _katalog(kitaplar, ders, sinif))

    eslesme = _bolum_bul(kitaplar, sorgu, ders, sinif)
    if not eslesme:
        return _bitir("bulunamadi", f"Kitap bölümü eşleşmedi.\nKonu: {sorgu}\n{_SINIRLI_DEVAM}")

    kitap, bolum = eslesme
    pdf_yolu = _kitap_yolu_coz(kitap)
    if not pdf_yolu.exists():
        return _bitir("bulunamadi", f"Kitap dosyası bulunamadı: {pdf_yolu.name}.")

    derslik = (istek.derslik or "").strip()
    if derslik and kitap.get("dosya"):
        _SON_KITAP.setdefault(derslik, {})[_norm(ders or kitap.get("ders", ""))] = kitap["dosya"]

    adet = max(1, min(istek.sayfa_adedi, 12))
    sayfalar = _ilgili_sayfalar(pdf_yolu, bolum["ilk_sayfa"], bolum["son_sayfa"],
                                 konu or tema, adet)

    try:
        icerik, supheli = _metin_cikar(pdf_yolu, sayfalar)
    except Exception as e:
        return _bitir("hata", f"Kitap içeriği okunamadı ({type(e).__name__}: {e}). "
                               f"Konu: {sorgu}. {_SINIRLI_DEVAM}")

    if not icerik.strip():
        return _bitir("bulunamadi",
                       f"{kitap['dosya']} s.{sayfalar[0]}-{sayfalar[-1]} boş döndü. "
                       f"Konu: {sorgu}. {_SINIRLI_DEVAM}")

    kirpildi = len(icerik) > MAX_KARAKTER
    if kirpildi:
        icerik = icerik[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"

    bas = [f"DERS KİTABI İÇERİĞİ — {kitap.get('ders','')} {kitap.get('sinif','')}. sınıf",
           f"{bolum['no']}. {bolum['tur']}: {bolum.get('ad','')}",
           f"Kaynak: {kitap['dosya']}, sayfa {', '.join(str(n) for n in sayfalar)}"]
    ozet = _kitap_ozeti(kitap.get("dosya", ""))
    if ozet:
        bas.append(f"Kitap özeti: {ozet}")
    if konu:
        bas.append(f"Konu: {konu}")
    if supheli:
        bas.append(
            f"UYARI: Bu sayfalarda {supheli} yerde sembol bozuk kodlanmış "
            f"('#' ve '$' işaretleri; ≤ mi ≥ mi belli değil). Formülü "
            f"sembol sembol OKUMA, sözle anlat. Bir eşitsizliğin yönü "
            f"gerekiyorsa kazanım metnine dayan, sayfadaki işarete güvenme."
        )
    if kirpildi:
        bas.append("Not: içerik uzun olduğu için kısaltıldı; daha fazlası "
                    "gerekiyorsa sayfa_adedi ile yeniden isteyebilirsin.")

    sonuc = "\n".join(bas) + "\n\n" + icerik
    baslik = f"{kitap.get('ders','ders').upper()} — {bolum.get('ad','')[:34]}"
    return _bitir("ok", sonuc, baslik)


# ── /api/egitim/pdf_sayfa ───────────────────────────────────────────────────

def render_pdf_sayfa(pdf_yolu: Path, sayfa: int, onbellek_dir: Path) -> Path:
    """Bir PDF'in TEK sayfasını PNG'ye render eder (varsa önbellekten döner).
    yks.py da bunu import eder — render mantığı iki yerde kopyalanmasın diye
    (client'taki orijinal gerekçeyle aynı)."""
    onbellek_dir.mkdir(parents=True, exist_ok=True)
    onbellek_yolu = onbellek_dir / f"{pdf_yolu.stem}_s{sayfa}.png"
    if onbellek_yolu.exists():
        return onbellek_yolu
    with fitz.open(str(pdf_yolu)) as pdf:
        if sayfa > len(pdf):
            raise ValueError(f"{pdf_yolu.name} yalnızca {len(pdf)} sayfa — {sayfa}. sayfa yok.")
        sayfa_nesnesi = pdf[sayfa - 1]
        pix = sayfa_nesnesi.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        pix.save(str(onbellek_yolu))
    return onbellek_yolu


def _kitap_bul(ders: str | None, sinif: str | None, tercih_dosya: str | None = None) -> dict | None:
    if not ders:
        return None
    kitaplar = _json_oku(KITAP_PATH)
    if not kitaplar:
        return None
    adaylar = []
    for k in kitaplar.get("kitaplar", []):
        if sinif and k.get("sinif") is not None and str(k["sinif"]) != str(sinif).strip():
            continue
        if not _ders_eslesir(ders, k.get("ders", "")):
            continue
        adaylar.append(k)
    if not adaylar:
        return None
    if tercih_dosya:
        for k in adaylar:
            if k.get("dosya") == tercih_dosya:
                return k
    return adaylar[0]


def _pdf_sayfa_kitap_coz(ders: str, sinif: str | None, derslik: str | None) -> dict | None:
    """`pdf_sayfa` ve `pdf_sayfa_metni` AYNI kitabı seçsin diye tek nokta —
    ikisi ayrı yerlerde bu mantığı tekrarlarsa tam da _kitap_bul/_bolum_bul
    senkronsuzluğunun (2026-08-30, madde 1, bu dosyanın başındaki not) aynı
    sınıf hatası burada da olurdu."""
    tercih_dosya = _SON_KITAP.get((derslik or "").strip(), {}).get(_norm(ders))
    return _kitap_bul(ders, sinif, tercih_dosya)


@router.get("/api/egitim/pdf_sayfa")
def pdf_sayfa_endpoint(
    sayfa: int = Query(..., ge=1),
    ders: str = Query(...),
    sinif: str | None = Query(default=None),
    derslik: str | None = Query(default=None),
):
    kitap = _pdf_sayfa_kitap_coz(ders, sinif, derslik)
    if not kitap:
        raise HTTPException(status_code=404, detail="Bu ders/sınıf için indekslenmiş kitap bulunamadı.")

    pdf_yolu = _kitap_yolu_coz(kitap)
    if not pdf_yolu.exists():
        raise HTTPException(status_code=404, detail=f"Kitap dosyası bulunamadı: {pdf_yolu.name}.")

    try:
        onbellek_yolu = render_pdf_sayfa(pdf_yolu, sayfa, PDF_SAYFA_ONBELLEK)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sayfa render edilemedi ({type(e).__name__}: {e}).")

    # NOT: kitap adı/dosya adı Türkçe karakter içerebilir (İ, ş, ğ...) — HTTP
    # header değerleri latin-1 ile sınırlı, bu yüzden başlığa KONMAZ. Client
    # zaten hangi ders/sınıf istediğini biliyor, ayrıca header'a gerek yok.
    return FileResponse(onbellek_yolu, media_type="image/png",
                         headers={"Cache-Control": "public, max-age=86400"})


class SayfaMetniYanit(BaseModel):
    status: str  # "ok" | "bulunamadi"
    metin: str | None = None


@router.get("/api/egitim/pdf_sayfa_metni", response_model=SayfaMetniYanit)
def pdf_sayfa_metni_endpoint(
    sayfa: int = Query(..., ge=1),
    ders: str = Query(...),
    sinif: str | None = Query(default=None),
    derslik: str | None = Query(default=None),
):
    """2026-08-30 eklendi — gerçek sınıf hatası: öğretmen doğrudan sayfa
    numarası söylediğinde (`pdf_sayfa` konu eşleşmesi OLMADAN çıplak
    çağrılıyor, bkz. `ders_icerigi`'nin aksine) Farabi o sayfanın METNİNİ
    hiç almıyordu — yalnızca PNG görüyordu, içeriği UYDURUYORDU (gerçek
    transkript: "Doğru metin bu mu?"). RAG Kuralları'ndaki "cevap sadece
    retrieval sonucundan üretilir" ilkesi bu yolda hiç uygulanmıyordu.
    Bu endpoint `pdf_sayfa`nın render ettiği AYNI kitap+sayfa için gerçek
    metni döner (`_pdf_sayfa_kitap_coz` ile aynı kitap seçimi, `_metin_cikar`
    ile aynı çıkarma altyapısı — ikisi de zaten vardı, yalnızca `pdf_sayfa`
    yoluna hiç bağlanmamışlardı). Görüntü endpoint'inin kendi sözleşmesi
    (PNG, FileResponse) BİLEREK değiştirilmedi — client iki ayrı çağrı yapar,
    protokolde kırılma yok."""
    kitap = _pdf_sayfa_kitap_coz(ders, sinif, derslik)
    if not kitap:
        return SayfaMetniYanit(status="bulunamadi", metin=None)

    pdf_yolu = _kitap_yolu_coz(kitap)
    if not pdf_yolu.exists():
        return SayfaMetniYanit(status="bulunamadi", metin=None)

    try:
        icerik, _supheli = _metin_cikar(pdf_yolu, [sayfa])
    except Exception:
        return SayfaMetniYanit(status="bulunamadi", metin=None)

    if not icerik.strip():
        return SayfaMetniYanit(status="bulunamadi", metin=None)

    # Kalite kapısı (2026-08-30, canlı test sırasında bulundu): `#`/`$`
    # şüpheli-sembol sayacı (`supheli`) BU tür bozulmayı YAKALAMAZ —
    # fizik_9.pdf'in dönüştürülmüş metninde sayfaların %55'i (150/273)
    # U+FFFD (REPLACEMENT CHARACTER) ile dolu, bazı sayfalarda oran %79'a
    # çıkıyor (yalnızca bu kitapta — diğer 18 kitabın hiçbirinde tek bir
    # kirli sayfa yok, ölçüldü). Modele "SAYFA METNİ" diye böyle bir bloğu
    # vermek, hiç vermemekten daha kötü — kirliyse "bulunamadı"ya düş.
    if icerik.count("�") / len(icerik) > 0.02:
        return SayfaMetniYanit(status="bulunamadi", metin=None)

    if len(icerik) > MAX_KARAKTER:
        icerik = icerik[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"
    return SayfaMetniYanit(status="ok", metin=icerik)
