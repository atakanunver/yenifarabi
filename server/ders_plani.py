"""server/ders_plani.py — kitap sayfalarından 40 dakikalık ders planı.

Karar ve ölçüm: DECISIONS.md 2026-09-29 (kitap metni buluta gidebilir;
Fizik 10 s.14-22'de qwen2.5:14b yetersiz, deepseek en iyi). Plan:
docs/superpowers/plans/2026-09-29-ders-plani-hatti.md.

RAG soru-cevabı (rag.py) DEĞİL: orada cevap ≤3 cümle, sıcaklık ≤0,2 ve
kaynakta olmayan sayı gizlenir. Bir ders planı çözümlü örnek içerdiği için
bu kurallar burada uygulanamaz; yerine:
  - kitaptan gelen her bilgi "(PDF s. N)" atıflı,
  - modelin ürettiği her örnek "[ÜRETİLMİŞ ÖRNEK]" etiketli,
  - kitaptan gelmesi gereken 1.–2. bölümde kaynakta geçmeyen sayılar
    ENGELLENMEZ, `kontrol_uyarilari` olarak öğretmene/insan kontrolüne döner.

Kitap/bölüm/sayfa çözümü icerik.py'nin yardımcılarıyla yapılır (ders_icerigi
ile aynı eşleşme — iki ayrı eşleştirme mantığı olmasın).
"""

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import auth
import icerik
import saglayicilar

router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

PLAN_ONBELLEK = icerik.DATA_DIR / "icerik" / "ders_plani"
MAX_SAYFA = 12
KAYNAK_MAX_KARAKTER = 40_000  # ölçülen 9 sayfa ≈ 15,6k karakter; deepseek context'i geniş
ISTEM_SURUMU = "1"            # SISTEM/GOREV değişince artır → eski önbellek kullanılmaz

SISTEM = """Sen Türkiye'de MEB müfredatıyla ders veren deneyimli bir öğretmen ve ders planı yazarısın. Yalnızca Türkçe yaz.
KURALLAR:
1. Kavram, tanım, formül ve sayısal değerleri YALNIZCA <kaynak> içindeki kitap metninden al; her birinin yanına (PDF s. N) yaz. Kaynaktaki [s.N] etiketleri PDF sayfa numarasıdır.
2. Kaynakta olmayan bir formül veya tanım gerekiyorsa yazma; "Kitapta yok — öğretmen ekleyebilir" de.
3. Kendi ürettiğin her örnek soru ve sayının başına [ÜRETİLMİŞ ÖRNEK] yaz.
4. Kaynak metin PDF'ten çıkarıldı; semboller bozuk olabilir (ör. hız sembolü ϑ yerine 'c', kesir ve üsler satırlara dağılmış). Emin olmadığın sembolü veya formülü tahmin etme, "sembolü kitaptan kontrol edin" yaz.
5. Grafikleri kitap metnindeki anlatımdan tarif et; grafik üzerindeki sayısal değerleri metinde yoksa uydurma, "değerleri kitaptaki grafikten kontrol edin" yaz.
6. Formülleri LaTeX ($...$), tabloları Markdown ile yaz."""

GOREV = """<kaynak kitap="{kitap}" sayfalar="{sayfalar}" supheli_sembol="{supheli}">
{metin}
</kaynak>
Ders / sınıf: {ders} {sinif}
Konu: {konu}
Kazanım(lar): {kazanim}
Öğretmen taslağı: {taslak}

Aşağıdaki 4 başlığı AYNEN bu sırayla ve bu numaralarla üret:
1. KAVRAMLAR VE FORMÜL ANALİZİ — terim: tanım (PDF s. N); formüller $LaTeX$ + birim analizi (SI).
2. TAHTA TASARIMI — (a) Markdown tablo; (b) grafik: X/Y ekseni+birim, eğri türü, eğimin/alanın fiziksel anlamı.
3. 40 DAKİKALIK AKIŞ — 00–05 giriş sorusu | 05–20 kavramsal inşa, formülün adım adım çıkarılışı | 20–30 grafik yorumu + 1–2 aşamalı [ÜRETİLMİŞ ÖRNEK] çözüm | 30–37 sınıf içi pratik + en az 2 kavram yanılgısı | 37–40 iki cümlelik özet + sonraki derse ipucu sorusu.
4. REDAKSİYON — taslak varsa düzeltilmiş metin + kritik iyileştirmeler listesi; yoksa "Taslak verilmedi."
"""


class PlanIstek(BaseModel):
    ders: str = Field(..., min_length=1, max_length=60)
    sinif: str | None = None
    konu: str = Field(..., min_length=2, max_length=200)
    # Ünite/tema adı — konu ünite adıyla eşleşmiyorsa (ör. "Sabit Hızlı
    # Hareket" ⊂ "KUVVET VE HAREKET") kitap bölümü bununla bulunur.
    tema: str = Field(default="", max_length=200)
    kazanim: str = Field(default="", max_length=2000)
    taslak: str = Field(default="", max_length=20_000)
    ilk_sayfa: int | None = Field(default=None, ge=1)
    son_sayfa: int | None = Field(default=None, ge=1)
    sayfa_adedi: int = Field(default=9, ge=1, le=MAX_SAYFA)
    zorla: bool = False


class PlanYanit(BaseModel):
    status: str  # "ok" | "bulunamadi" | "hata"
    plan: str | None = None
    mesaj: str | None = None
    kitap: str | None = None
    sayfalar: list[int] = []
    supheli_sembol: int = 0
    kontrol_uyarilari: list[str] = []
    onbellekten: bool = False
    latency_ms: int
    request_id: str


_SAYI_RE = re.compile(r"\d+(?:[.,]\d+)?")
_BOLUM3_RE = re.compile(r"^\W*3\s*\.\s", re.MULTILINE)
_BASLIK_RE = re.compile(r"^\W*[12]\s*\.\s.*$", re.MULTILINE)
_ATIF_RE = re.compile(r"(?:PDF\s*)?s\.\s*\d+(?:\s*[-–]\s*\d+)?")


def kaynakta_olmayan_sayilar(plan: str, kaynak: str) -> list[str]:
    """1.–2. bölümde (kitaptan gelmesi gereken kısım) kaynakta geçmeyen
    sayılar. Başlık numaraları ve sayfa atıfları sayılmaz. Engellemez —
    yalnızca insan kontrolü için listeler (rag.py'nin sayı kontrolünün
    ders planına uyarlanmış, yumuşak hâli)."""
    m = _BOLUM3_RE.search(plan)
    kitap_kismi = plan[:m.start()] if m else plan
    kitap_kismi = _ATIF_RE.sub(" ", _BASLIK_RE.sub(" ", kitap_kismi))
    kaynak_sayilari = {n.replace(",", ".") for n in _SAYI_RE.findall(_ATIF_RE.sub(" ", kaynak))}
    eksik: list[str] = []
    for n in _SAYI_RE.findall(kitap_kismi):
        k = n.replace(",", ".")
        if k not in kaynak_sayilari and n not in eksik:
            eksik.append(n)
    return eksik


def _kaynak_topla(istek: PlanIstek) -> tuple[dict, list[int], str, int] | str:
    """(kitap, sayfalar, metin, supheli) ya da kullanıcıya dönecek mesaj."""
    kitaplar = icerik._json_oku(icerik.KITAP_PATH)
    if kitaplar is None:
        return "Kitap indeksi bulunamadı (icerik/kitaplar.json)."
    ders = istek.ders.strip() or None
    sinif = istek.sinif.strip() if istek.sinif else None

    if istek.ilk_sayfa is not None and istek.son_sayfa is not None:
        if istek.son_sayfa < istek.ilk_sayfa:
            return "son_sayfa, ilk_sayfa'dan küçük olamaz."
        kitap = icerik._kitap_bul(ders, sinif)
        if not kitap:
            return f"Kitap bulunamadı: {istek.ders} {sinif or ''}".strip()
        son = min(istek.son_sayfa, istek.ilk_sayfa + MAX_SAYFA - 1)
        sayfalar = list(range(istek.ilk_sayfa, son + 1))
        pdf = icerik._kitap_yolu_coz(kitap)
    else:
        eslesme = icerik._bolum_bul(kitaplar, istek.tema.strip() or istek.konu, ders, sinif)
        if not eslesme:
            return (f"Kitap bölümü eşleşmedi: {istek.tema or istek.konu}. "
                    "Ünite adını 'tema' ile ya da sayfa aralığını ilk_sayfa/son_sayfa ile verin.")
        kitap, bolum = eslesme
        pdf = icerik._kitap_yolu_coz(kitap)
        sayfalar = icerik._ilgili_sayfalar(pdf, bolum["ilk_sayfa"], bolum["son_sayfa"],
                                           istek.konu, istek.sayfa_adedi)

    if not pdf.exists():
        return f"Kitap dosyası bulunamadı: {pdf.name}."
    metin, supheli = icerik._metin_cikar(pdf, sayfalar)
    if not metin.strip():
        return f"{pdf.name} s.{sayfalar[0]}-{sayfalar[-1]} boş döndü."
    if len(metin) > KAYNAK_MAX_KARAKTER:
        metin = metin[:KAYNAK_MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"
    return kitap, sayfalar, metin, supheli


def _onbellek_yolu(kitap_dosya: str, sayfalar: list[int], istek: PlanIstek) -> Path:
    anahtar = json.dumps([ISTEM_SURUMU, kitap_dosya, sayfalar, istek.konu,
                          istek.kazanim, istek.taslak], ensure_ascii=False)
    ozet = hashlib.sha256(anahtar.encode("utf-8")).hexdigest()[:16]
    return PLAN_ONBELLEK / Path(kitap_dosya).stem / f"{ozet}.json"


def ders_plani_uret(istek: PlanIstek) -> PlanYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())

    def _bitir(status: str, **alanlar) -> PlanYanit:
        return PlanYanit(status=status, latency_ms=int((time.perf_counter() - t0) * 1000),
                         request_id=request_id, **alanlar)

    try:
        kaynak = _kaynak_topla(istek)
    except Exception as e:
        return _bitir("hata", mesaj=f"Kitap içeriği okunamadı ({type(e).__name__}: {e}).")
    if isinstance(kaynak, str):
        return _bitir("bulunamadi", mesaj=kaynak)
    kitap, sayfalar, metin, supheli = kaynak
    ortak = {"kitap": kitap.get("dosya"), "sayfalar": sayfalar, "supheli_sembol": supheli}

    yol = _onbellek_yolu(kitap.get("dosya", ""), sayfalar, istek)
    if not istek.zorla and yol.exists():
        try:
            k = json.loads(yol.read_text(encoding="utf-8"))
            return _bitir("ok", plan=k["plan"], kontrol_uyarilari=k.get("kontrol_uyarilari", []),
                          onbellekten=True, **ortak)
        except Exception:
            pass  # bozuk önbellek → yeniden üret

    istem = GOREV.format(kitap=kitap.get("dosya"), sayfalar=f"{sayfalar[0]}-{sayfalar[-1]}",
                         supheli=supheli, metin=metin, ders=istek.ders, sinif=istek.sinif or "",
                         konu=istek.konu, kazanim=istek.kazanim or "belirtilmedi",
                         taslak=istek.taslak or "yok")
    try:
        plan = saglayicilar.metin_uret("ders_plani", istem, SISTEM)
    except Exception as e:
        return _bitir("hata", mesaj=f"Plan üretilemedi ({type(e).__name__}: {e}).", **ortak)

    uyarilar = [f"Kaynakta geçmeyen sayı (1.–2. bölüm): {n}"
                for n in kaynakta_olmayan_sayilar(plan, metin)]
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps({
            "plan": plan, "kontrol_uyarilari": uyarilar, "sayfalar": sayfalar,
            "konu": istek.konu, "olusturma": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # önbellek yazılamazsa plan yine döner
    return _bitir("ok", plan=plan, kontrol_uyarilari=uyarilar, **ortak)


@router.post("/api/egitim/ders_plani", response_model=PlanYanit)
def ders_plani_endpoint(istek: PlanIstek) -> PlanYanit:
    return ders_plani_uret(istek)
