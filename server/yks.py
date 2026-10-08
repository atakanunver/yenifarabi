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

GEÇMİŞ-DERS TEKRARI ENGELLEME (2026-08-21 eklendi) — `_OTURUMLAR` yalnızca
SÜRECİN kendi ömrü boyunca bir "sıradaki soru" imleciydi, geçmiş derslere
hiç bakmıyordu; gerçek bir derste daha önce çözülmüş bir soru yeni soruymuş
gibi tekrar sunuldu. `yks_gosterim` tablosu (server/schema_yks_gosterim.sql)
artık HER `derslik`e GERÇEKTEN sunulan (dosya_adi, sayfa) çiftini kalıcı
olarak (süreç/gün-aşırı) tutuyor; yeni bir arama bu tabloyu sorgulayıp
sıralama/kırpmadan ÖNCE dışlıyor (`_daha_once_gosterildi_mi`/
`_gosterimi_kaydet`, fail-open — DB erişilemezse dedup sessizce atlanır,
YKS özelliğinin kendisi asla kilitlenmez).
"""

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import auth
import db
from icerik import DATA_DIR, ONBELLEK, render_pdf_sayfa
from metin_araclari import norm as _norm

# FAZ 1 (IMPLEMENT) — bkz. icerik.py'deki aynı değişikliğin notu.
router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])
log = logging.getLogger("yks")

METIN_DIR = DATA_DIR / "icerik" / "yks_metin"
YKS_DIR = DATA_DIR / "yks"
YKS_SAYFA_ONBELLEK = ONBELLEK / "yks_sayfa"

MAX_KARAKTER = 6000
VARSAYILAN_ADET = 3
AZAMI_ADET = 10  # 2026-10-08: öğretmen "10 soru" istedi (soru üretilmez, çıkmış soruya bakılır)

_SAYFA_AYIR = re.compile(r"\n\n===SAYFA (\d+)===\n\n")

# derslik -> {"adaylar": [(dosya_adi, sayfa, govde, puan, konu), ...], "index": int}
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


# 2026-08-30 — gerçek sınıf hatası: "tarih için soru getir" dedi,
# CIKMIS_SORULAR_...AYT_EA_1.txt gibi KARMA (Eşit Ağırlık: Türk Dili ve
# Edebiyatı + Tarih + Coğrafya + Felsefe tek dosyada) kaynaklardan Türk Dili
# sorusu geldi. `ders` o zamana kadar yalnızca kelime torbasına karışan bir
# skor önyargısıydı — dosya/sayfa hiç FİLTRELENMİYORDU. Bu tür dosyalarda
# her sayfa, o sayfanın ait olduğu bölümün adını (ör. "TÜRK DİLİ VE
# EDEBİYATI", "TARİH-1") kendi ilk satırında TEKRARLIYOR (doğrulandı:
# AYT_EA_1.txt'de "TARİH-1" s.77-98+ arası her sayfanın ilk satırı). Bu
# başlığı gerçek bir bölüm başlığına benziyorsa (kısa, büyük harf) sabit
# gerçek olarak alıp `ders` ile eşleşmiyorsa sayfayı TAMAMEN ELE — yalnızca
# skor önyargısı değil. Başlık belirsiz/yoksa (TYT gibi karışık dosyalarda
# temiz bölüm başlığı bulunmuyor, ölçüldü) ESKİ davranışa (filtre yok,
# yalnızca kelime skoru) düşülür — tek-konulu/başlıksız dosyalarda regresyon
# olmaz.
_BOLUM_BASLIGI = re.compile(r"^[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 .\-]{3,45}$")


def _sayfa_bolum_basligi(govde: str) -> str | None:
    for satir in govde.strip().splitlines()[:2]:
        satir = satir.strip()
        if satir and _BOLUM_BASLIGI.match(satir):
            return satir
    return None


def _ders_baslikla_eslesir(ders: str, baslik: str) -> bool:
    if not ders:
        return True
    ders_n, baslik_n = _norm(ders), _norm(baslik)
    return any(k in baslik_n for k in ders_n.split() if k)


# ── Konu haritası + soru sayfası filtresi + kök eşleşmesi (2026-10-08) ─────────
# Olay: tahtadan yks_sorulari(ders='matematik', konu='DÖRTGENLERDE AÇI') geldi,
# AYT_EA_1 s.113 (Matematik KAPAK sayfası) döndü, model soruyu uydurdu. Kök
# nedenler: (1) `ders` kelimesi her matematik sayfasında geçtiği için tüm
# sayfalar eşit puan alıyordu, (2) sayfanın soru içerip içermediği
# bakılmıyordu, (3) "dörtgenlerde"≠"dörtgen", "açı" len>3 ile atılıyordu,
# (4) alaka eşiği yoktu. Düzeltme: puan yalnızca `konu`dan; sayfa→konu haritası
# (server/yks_konu_haritasi.py) etiket olarak güçlü puan verir.
HARITA_YOLU = DATA_DIR / "icerik" / "eslemeler" / "yks_konu.json"
_HARITA_YUKLENMEDI = object()
_harita_onbellek = _HARITA_YUKLENMEDI

# Şık deseni (A) B) ...) ya da "2019-AYT" benzeri soru etiketi yoksa sayfa SORU
# DEĞİLDİR (kapak, TOPLAM tablosu, cevap anahtarı, dağılım dosyası).
_SIK = re.compile(r"(?<![0-9A-Za-zÇĞİÖŞÜçğıöşü])([A-E])\)")
_SORU_ETIKETI = re.compile(r"20\d\d\s*-\s*(?:TYT|AYT|YDT|MSÜ|MSU)")

_DURAK = frozenset((
    "ile", "ilgili", "soru", "sorusu", "sorular", "sorulari", "sorularini", "hakkinda",
    "konusu", "konular", "konusunda", "uzerine", "icin", "olan", "bir", "ve", "veya",
    "cikmis", "cikan", "yks", "tyt", "ayt", "ydt", "getir", "goster", "ver", "bul",
    "ornek", "lutfen", "bana", "the", "and", "for",
))


def _harita_yukle() -> dict:
    """Sayfa→konu haritasını tembel yükler. FAIL-OPEN: dosya yok/bozuksa uyarı
    loglar, {} döner (eski davranış: etiket/cevap-anahtarı bilgisi olmadan)."""
    global _harita_onbellek
    if _harita_onbellek is _HARITA_YUKLENMEDI:
        try:
            veri = json.loads(HARITA_YOLU.read_text(encoding="utf-8"))
            _harita_onbellek = veri if isinstance(veri, dict) else {}
        except FileNotFoundError:
            log.warning("YKS konu haritası yok (%s) — etiketsiz arama.", HARITA_YOLU)
            _harita_onbellek = {}
        except (OSError, ValueError) as e:
            log.warning("YKS konu haritası okunamadı (%s): %s: %s", HARITA_YOLU,
                        type(e).__name__, e)
            _harita_onbellek = {}
    return _harita_onbellek


def _jetonlar(s: str) -> list[str]:
    """Normalize, durak kelimesiz, ≥3 harfli, sıra korunur, tekrarsız."""
    gorulen: dict[str, None] = {}
    for k in _norm(s).split():
        if len(k) >= 3 and k not in _DURAK:
            gorulen.setdefault(k, None)
    return list(gorulen)


def _kelime_eslesir(a: str, b: str) -> bool:
    """Ek-toleranslı eşleşme: tam eşit; ≥5 harflide ortak önek ≥ max(5, 0,6×kısa)
    ('dortgen'~'dortgenlerde', 'dortgeninde'~'dortgenlerde'); 3 harflide ('aci')
    yalnızca kısa uzunun öneki ve uzun en çok 4 ek harfli ('acisi' evet);
    4 harflide en çok 2 ek harf ya da çoğul eki."""
    if a == b:
        return True
    k, u = (a, b) if len(a) <= len(b) else (b, a)
    if len(k) < 3 or k[0] != u[0]:
        return False
    if len(k) == 3:
        return u.startswith(k) and len(u) <= 7
    if len(k) == 4:  # 'dort'~'dortgen' yanlış pozitifi: yalnızca kısa ek / çoğul eki
        return u.startswith(k) and (len(u) <= 6 or u[4:] in ("ler", "lar", "leri", "lari"))
    return len(os.path.commonprefix((k, u))) >= max(5, 0.6 * len(k))


def _kumede_var(q: str, kume) -> bool:
    return q in kume or any(_kelime_eslesir(q, t) for t in kume)


def _soru_sayfasi_mi(govde: str) -> bool:
    return bool(_SORU_ETIKETI.search(govde)) or len(set(_SIK.findall(govde))) >= 2


def _dosyadaki_en_iyi_sayfalar(dosya: Path, sorgu: list[str], adet: int, ders: str = "",
                                harita: dict | None = None
                                ) -> list[tuple[int, str, float, list[str]]]:
    """(sayfa, gövde, puan, konu_etiketleri). `sorgu` = ders kelimeleri çıkarılmış
    konu jetonları. Eşik: en az bir sorgu kelimesi sayfa etiketiyle eşleşmeli YA
    DA gövdede tüm (≥2 ise en az 2) kelime geçmeli."""
    try:
        metin = dosya.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    harita = harita or {}
    sayfa_konu = harita.get("sayfa_konu") or {}
    cevap_bas = harita.get("cevap_anahtari_baslangic")
    n = len(sorgu)
    gerekli_govde = min(n, 2)
    sonuclar = []
    for no, govde in _sayfalara_ayir(metin):
        if cevap_bas and no >= cevap_bas:
            continue  # cevap anahtarı bölgesi — soru değil
        if not _soru_sayfasi_mi(govde):
            continue  # kapak / TOPLAM / dağılım — soru içermiyor
        baslik = _sayfa_bolum_basligi(govde)
        if baslik and not _ders_baslikla_eslesir(ders, baslik):
            continue  # bu sayfa AÇIKÇA başka bir dersin bölümünde — ele
        etiketler = sayfa_konu.get(str(no)) or []
        etiket_jeton = set(_jetonlar(" ".join(etiketler)))
        govde_jeton = {k for k in _norm(govde).split() if len(k) >= 3}
        e = sum(1 for q in sorgu if etiket_jeton and _kumede_var(q, etiket_jeton))
        g = sum(1 for q in sorgu if _kumede_var(q, govde_jeton))
        if e == 0 and g < gerekli_govde:
            continue
        puan = 2.0 * e / n + g / n
        sonuclar.append((no, govde.strip(), puan, etiketler))
    sonuclar.sort(key=lambda x: x[2], reverse=True)
    return sonuclar[:adet]


_BASLIK_ARTIGI = frozenset(("ea", "say", "soz", "ayt", "tyt", "ydt"))


def _govde_anahtari(govde: str) -> str:
    """Tekilleştirme anahtarı: sayfa başlığındaki dosyaya özgü kelimeler (EA/SAY…)
    atılır — 'AYT MATEMATİK EA 243.' ile '… SAY 243.' aynı sayfadır."""
    k = [t for t in _norm(govde).split() if t not in _BASLIK_ARTIGI]
    return " ".join(k)[:300]


def _daha_once_gosterildi_mi(derslik: str) -> set[tuple[str, int]]:
    """Bu derslike daha önce gösterilmiş (dosya_adi, sayfa) çiftleri —
    2026-08-21'de gerçek bir derste bildirilen hata: daha önce çözülmüş bir
    soru yeni soruymuş gibi tekrar sunuldu, çünkü hiçbir şey geçmiş derslere
    bakmıyordu. FAIL-OPEN: DB'ye erişilemezse boş küme döner, sessizce
    loglanır — dedup kontrolünün kendisi asla YKS özelliğini kilitleyemez
    ("Farabi asla dersi bozmaz", client_durum.py::heartbeat ile aynı
    tolerans)."""
    try:
        with db.baglanti() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT dosya_adi, sayfa FROM yks_gosterim WHERE derslik = %s",
                    (derslik,),
                )
                return {(r[0], r[1]) for r in cur.fetchall()}
    except Exception as e:
        log.warning("Geçmiş YKS gösterimleri okunamadı (derslik=%s): %s: %s",
                    derslik, type(e).__name__, e)
        return set()


def _gosterimi_kaydet(derslik: str, dosya_adi: str, sayfa: int, ders: str, konu: str) -> None:
    """Bir soru GERÇEKTEN sunulduğunda (yalnızca eşleştiğinde değil) çağrılır
    — kayıt gösterimden SONRA denenir, başarısız olursa sessizce loglanır,
    sorunun sınıfa gösterilmiş olması hiçbir şekilde etkilenmez."""
    try:
        with db.baglanti() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO yks_gosterim (derslik, dosya_adi, sayfa, ders, konu) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (derslik, dosya_adi, sayfa, ders, konu),
                )
            conn.commit()
    except Exception as e:
        log.warning("YKS gösterimi kaydedilemedi (derslik=%s, dosya=%s, sayfa=%s): %s: %s",
                    derslik, dosya_adi, sayfa, type(e).__name__, e)


def _sunum_metni(dosya_adi: str, sayfa: int, govde: str, sira: int, toplam: int,
                 konu: list[str] | None = None) -> str:
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

    konu_satiri = f"Sayfanın konusu: {'; '.join(konu)}\n" if konu else ""
    return (
        f"[{sira}/{toplam}. eşleşen soru] Kaynak: {dosya_adi} · sayfa {sayfa}\n"
        f"{konu_satiri}"
        f"Soru sayfa GÖRÜNTÜSÜ olarak ekranda (PDF bütünlüğü korunuyor, metne "
        f"çevrilmedi). Aşağıdaki metin YALNIZCA senin okuman için (ham PDF "
        f"metni; dizgi kaynaklı küçük bozukluklar olabilir, ÇÖZÜM İÇERMEZ):\n\n"
        f"{kirpildi_govde}\n\n"
        f"Bu sayfada birden çok soru olabilir; YALNIZCA yukarıdaki metinde açıkça "
        f"geçen soru(lar)ı oku, konuyla ilgili olanı seç. Metinde okunabilir bir "
        f"soru/şık yoksa ya da şekil gerekiyorsa soru, şekil, sayı veya şık "
        f"UYDURMA — 'soru ekranda, şekle bakalım' de.\n"
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
    status: str  # "ok" | "oturum_yok" | "konu_yok" | "arsiv_yok" | "bos" | "son" | "tekrar"
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

    oturum = _OTURUMLAR.setdefault(
        istek.derslik, {"adaylar": [], "index": -1, "ders": "", "konu": ""})

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
        dosya_adi, sayfa, govde, _puan, konu = adaylar[idx]
        _gosterimi_kaydet(istek.derslik, dosya_adi, sayfa, oturum["ders"], oturum["konu"])
        return _bitir("ok", dosya_adi=dosya_adi, sayfa=sayfa, sira=idx + 1, toplam=len(adaylar),
                       metin=_sunum_metni(dosya_adi, sayfa, govde, idx + 1, len(adaylar), konu))

    # ── Yeni arama — konu zorunlu ────────────────────────────────────────────
    if not istek.konu:
        return _bitir("konu_yok", metin="Hangi konuyla ilgili çıkmış soru istediğinizi "
                                         "söyler misiniz, efendim.")

    if not METIN_DIR.exists() or not any(METIN_DIR.glob("*.txt")):
        return _bitir("arsiv_yok",
                       metin="Çıkmış soru arşivi henüz hazırlanmamış. SINIFA TEKNİK SORUN "
                             "ANLATMA — kitaptaki örneklerle anlatmaya DEVAM ET.")

    # Puan yalnızca `konu`dan; ders adı kelimeleri ("matematik dörtgen" yazılırsa)
    # konu kelimelerinden de çıkarılır — her matematik sayfasında geçtiği için
    # ayırt edici değil. `ders` yalnızca başlık filtresinde kullanılır.
    ders_jeton = _jetonlar(istek.ders)
    sorgu_kelimeler = [k for k in _jetonlar(istek.konu)
                       if not any(_kelime_eslesir(k, d) for d in ders_jeton)]
    if not sorgu_kelimeler:
        return _bitir("konu_yok", metin=f"'{istek.konu}' konusunda anlamlı bir arama "
                                         f"terimi çıkaramadım, efendim.")

    harita = _harita_yukle()
    ham: list[tuple[str, int, str, float, list[str]]] = []
    for dosya in sorted(METIN_DIR.glob("*.txt")):
        # dosya başına 2×adet: dosyalar arası tekilleştirme sonrası da yetsin
        for no, govde, puan, konu in _dosyadaki_en_iyi_sayfalar(
                dosya, sorgu_kelimeler, istek.adet * 2, ders=istek.ders,
                harita=harita.get(dosya.stem)):
            ham.append((dosya.stem, no, govde, puan, konu))
    ham.sort(key=lambda x: x[3], reverse=True)  # kararlı: eşitte dosya/sayfa sırası
    # Aynı sayfa farklı dosyalarda tekrar edebiliyor (EA_1 s.181 = SAY s.79):
    # gövdenin normalize ilk ~300 karakteri aynıysa tek aday.
    adaylar, gorulen = [], set()
    for a in ham:
        anahtar = _govde_anahtari(a[2])
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        adaylar.append(a)

    if not adaylar:
        oturum.update(adaylar=[], index=-1)
        return _bitir("bos", metin=f"'{istek.konu}' konusuyla eşleşen bir çıkmış soru "
                                    f"bulamadım, efendim. Kitaptaki örneklerle devam edelim.")

    # 2026-08-21 hatası: daha önce (farklı bir derste bile) gösterilmiş bir
    # soru yeni soruymuş gibi tekrar sunulmuştu. Sıralama/kırpmadan ÖNCE
    # dışla — böylece listede daha aşağıda duran YENİ bir aday öne çıkabilir,
    # yalnızca ilk `adet` tanesini filtrelemekten farklı.
    gosterilmisler = _daha_once_gosterildi_mi(istek.derslik)
    yeni_adaylar = [a for a in adaylar if (a[0], a[1]) not in gosterilmisler]

    if not yeni_adaylar:
        oturum.update(adaylar=[], index=-1)
        return _bitir("tekrar",
                       metin=f"'{istek.konu}' konusuyla eşleşen sorular daha önceki bir "
                             f"derste işlenmişti — tekrar mı göstereyim, yoksa farklı bir "
                             f"konu mu seçelim, efendim?")

    secilenler = yeni_adaylar[:istek.adet]
    oturum.update(adaylar=secilenler, index=0, ders=istek.ders, konu=istek.konu)
    dosya_adi, sayfa, govde, _puan, konu = secilenler[0]
    _gosterimi_kaydet(istek.derslik, dosya_adi, sayfa, istek.ders, istek.konu)
    return _bitir("ok", dosya_adi=dosya_adi, sayfa=sayfa, sira=1, toplam=len(secilenler),
                   metin=_sunum_metni(dosya_adi, sayfa, govde, 1, len(secilenler), konu))


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
