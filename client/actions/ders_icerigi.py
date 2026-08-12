"""
actions/ders_icerigi.py — Öğretmenin verdiği derse/konuya ait kitap sayfalarını getirir.

Oturum çerçevesi (hangi ders, konu, kazanım) burada çözülmez: ders adı
programdan, konu/kazanım öğretmenden gelir. Bu araç kitap iskeletidir. Yıllık
plan bu zincirde hiç yer almaz — ders yalnızca kitaplar üzerinden işlenir:
konu/kazanım öğretmenden gelir, kitaba doğrudan o konuyla bakılır.

İçerik zinciri (öğretmen konu verdikten sonra):

    ders + konu (+ tema) -> kitaplar.json -> cilt + sayfa aralığı
                                    ↓
                              sayfa metni (icerik/metin/)

Neden araç, neden sistem promptu değil:
Bir bölüm 13-37 bin token. Personası 1.400 token olan bir öğretmenin
talimatlarını 37 bin token kitapla boğmak, "cevabı doğrudan verme" kuralını
gürültüde kaybettirir. İçerik yalnızca gerektiğinde, yalnızca o konunun
sayfaları kadar yüklenir.

YALNIZ DÜZ METİN. Sayfalar `tools/kitap_metin.py` ile bir kez, çevrimdışı ve
API'siz metne çevrilir (`icerik/metin/<kitap>.json`); çalışma anında PDF
açılmaz. Sayfaları Gemini'ye görüntü olarak okutan eski yol kaldırıldı: kota
harcıyordu ve derste ölçülen en kötü hâli 20 saniyede zaman aşımıydı.

MEB matematik/fizik kitaplarının sembol fontu bozuk kodlanmış. Çevirici iki
katmanlı davranır: tek anlamlı bozukluklar onarılır (R"R -> R→R, x!R -> x ∈ R,
6x -> ∀x), çok anlamlı olanlar ('#', '$') TAHMİN EDİLMEZ, sayılır. Şüpheli
sembol taşıyan sayfalarda araç çıktısına uyarı eklenir ve model formülü sembol
sembol okumaz. Bir eşitsizliğin yönünü yanlış öğretmek, sembolü hiç
göstermemekten kötüdür.

Sayfa seçimi yalnız kelime-örtüşme yöntemiyle yapılır — semantik/embedding
araması yok, bilinçli olarak (kurulumu ağırlaştıran sentence-transformers/
torch bağımlılığı kaldırıldı).

Hazırlık (çalışma anında değil, bir kez):
    python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json
    python tools/kitap_metin.py kitaplar/ --json icerik/metin

NOT (2026-08-11/12): `KITAP_PATH`, `_json_oku`, `_ders_eslesir` artık bu
dosyanın DIŞINDAN da import ediliyor (`actions/kitap_sorusu.py`,
`actions/pdf_sayfa.py`) — alt çizgili olmalarına rağmen artık harici
çağıranları var. Bu üçünü yeniden adlandırmak/imzasını değiştirmek o iki
aracı da sessizce bozar.
"""

import json
import re
import unicodedata
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent
KITAP_PATH  = BASE_DIR / "icerik" / "kitaplar.json"
ONBELLEK    = BASE_DIR / "icerik" / "onbellek"

# Sınıfa okunacak metnin üst sınırı. ~1.500 token: personayı bastırmadan
# bir kazanımı anlatmaya yeter.
MAX_KARAKTER   = 6000
VARSAYILAN_SAYFA = 6          # kazanım başına getirilecek sayfa sayısı
# Sayfa seçimi için taranacak azami sayfa sayısı — ders anındaki en kötü
# hâli sabitler (ölçüm: sınırsızken 233 sayfalık bölüm 55,4 sn).
TARAMA_SINIRI  = 60

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

# Kitap sayfası getirilemediğinde modele dönen cümle.
#
# Eskiden burada "Kazanıma göre anlatıma devam et." yazıyordu ve bu, "kendi
# bildiğinle anlat" olarak okunuyordu. 10. sınıf ölçümünde bu dal ISTISNA
# DEĞİL, NORMAL yoldu (742 ders haftasının %94,3'ü), yani aracın kendi dönüş
# metni modeli doğaçlamaya salıyordu. Metin artık SINIRLAYICI: kazanım
# metninin dışına çıkma, uydurma, gerekirse aracı daha dar çağır.
_SINIRLI_DEVAM = (
    "KISIT: Kitap sayfası getirilemedi. Elindeki plan ve kazanım metni "
    "çerçevendir; onun dışına çıkma ve kitapta olmayan sayfa/alıntı UYDURMA. "
    "Sınıfa teknik sorun anlatma. Anlatıma devam et: konuyu kazanım metnine "
    "sadık kalarak `web_search` ile araştırıp derinleştirebilirsin — kitap "
    "zaten iskelet verir, anlatım senindir. Kitap sayfası gerçekten gerekiyorsa "
    "ders_icerigi'ni farklı bir tema ya da konu adıyla yeniden çağır."
)


def _norm(s: str) -> str:
    """Karşılaştırma için normalize: Türkçe harfler sadeleşir, noktalama gider."""
    s = unicodedata.normalize("NFC", (s or "")).translate(_TR).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _kelimeler(s: str) -> set[str]:
    """Anlamlı kelimeler (kısa bağlaçlar atılır)."""
    return {k for k in _norm(s).split() if len(k) > 3}


def _ders_eslesir(sorgu: str | None, hedef: str) -> bool:
    """
    Ders adı eşleştirmesi KELİME BAZLI yapılır, alt dize değil.

    Neden: "temel matematik" sorgusu, "Temel Düzey Matematik" planında
    bitişik geçmediği için alt dize aramasıyla BULUNAMIYORDU. Kullanıcı
    "temel matematik demiştim" dediğinde ortaya çıktı. Artık sorgunun her
    kelimesi hedefte geçiyorsa eşleşir; sıra ve araya giren kelimeler
    ("Düzey") sorun olmaz.
    """
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


# ── Ders adı normalizasyonu ─────────────────────────────────────────────────

# Sınıfa SESLİ okunacak adlar. `_norm` Türkçe harfleri düşürdüğü için üretilen
# kod adı "COGRAFYA"/"TDE" gibi çıkıyor; sınıfa "Tede" demek olmaz.
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


def gorunen_ad(ders_kodu: str) -> str:
    """Sınıfa okunacak ders adı. Bilinmiyorsa baş harfleri büyütülür."""
    kod = (ders_kodu or "").strip().upper()
    return _GORUNEN_AD.get(kod, kod.title())


def ders_kodu(ad: str) -> str:
    """
    Ters yön: insan yazımı ders adı -> plandaki kod. Ders programı dosyasında
    "türk dili ve edebiyatı" yazıyor, planda karşılığı "TDE"; ikisini
    birleştiren tek yer burasıdır (ikinci bir eş anlamlı tablosu tutulmaz).
    """
    n = _norm(ad)
    if not n:
        return ""
    for kod, gorunen in _GORUNEN_AD.items():
        if _norm(gorunen) == n or _norm(kod) == n:
            return kod
    return n.upper()


def _katalog(kitaplar: dict, ders: str | None, sinif: str | None) -> str:
    """
    Elde NE OLDUĞUNU listeler: hangi kitaplar indekslenmiş, hangi bölümleri
    var. Ders yalnızca kitaplar üzerinden işlenir — konu/kazanım öğretmenden
    gelir, burada tema/konu eşleşmediğinde öğretmene ne olduğunu gösterir.
    """
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


# ── Kitap tarafı ────────────────────────────────────────────────────────────

ESLEME_DIR = BASE_DIR / "icerik" / "eslemeler"


def _elle_eslemeler() -> list[dict]:
    """
    `icerik/eslemeler/*.json` — ELLE yazılmış tema → sayfa eşlemeleri.

    Neden var: kitap indeksi yayıncının sayfa üstbilgisinden üretiliyor ve bazı
    kitaplarda o üstbilgi ünite adı taşımıyor. Ölçüm: `fizik-10.pdf` indeksli,
    sayfa aralıkları doğru, ama dört ünitenin de adı "ÖLÇME VE DEĞERLENDİRME"
    olduğu için plan temalarıyla (KUVVET VE HAREKET, ENERJİ, ELEKTRİK,
    DALGALAR) eşleşme SIFIR. `cografya-10` ise tek bölüm hâlinde s.9-241,
    yani kitabın tamamı — sayfa seçimi ölçüldüğünde 55,4 saniye sürüyor.

    Bunu kodla tahmin etmeye çalışmak bitmeyen bir iş; kitap başına birkaç
    satır elle yazmak kesin sonuç verir ve otomatik indekse HER ZAMAN üstündür.

    Biçim (JSON — yeni bağımlılık istemesin diye YAML değil):

        {"kitap": "fizik-10.pdf", "ders": "fizik", "sinif": "10",
         "bolumler": [
           {"ad": "1. Ünite — Kuvvet ve Hareket",
            "temalar": ["KUVVET VE HAREKET"],
            "ilk_sayfa": 15, "son_sayfa": 108, "yontem": "gorsel"}
         ]}
    """
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


def _esleme_bolumu(kitaplar: dict, tema: str, ders: str | None,
                   sinif: str | None) -> tuple[dict, dict] | None:
    """Elle eşlemelerde tema ara. Bulursa otomatik indeksin önüne geçer."""
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


def _kitap_kaydi(kitaplar: dict, esleme: dict) -> dict | None:
    """Elle eşlemedeki kitabı indekste bul; yoksa kitaplar/ altında varsay."""
    dosya = esleme.get("kitap", "")
    for k in kitaplar.get("kitaplar", []):
        if k.get("dosya") == dosya:
            return {**k, "ders": esleme.get("ders", k.get("ders", "")),
                    "sinif": esleme.get("sinif", k.get("sinif"))}
    yol = BASE_DIR / "kitaplar" / dosya
    if not yol.exists():
        return None
    return {"dosya": dosya, "yol": str(yol), "ders": esleme.get("ders", ""),
            "sinif": esleme.get("sinif")}


def _bolum_bul(kitaplar: dict, tema: str, ders: str | None,
               sinif: str | None) -> tuple[dict, dict] | None:
    """Tema adına göre kitap + bölüm eşle. (kitap, bolum) döndürür."""
    # Elle eşleme her zaman önce gelir.
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

    # Yarıdan az örtüşme güvenilmez: yanlış temayı anlatmaktansa hiç anlatma
    return en_iyi if en_iyi_puan >= 0.5 else None


METIN_DIZINI = BASE_DIR / "icerik" / "metin"

# Çevrilmiş kitap metinleri süreç ömrü boyunca bellekte tutulur: bir kitap
# 0,5-2 MB JSON ve ders boyunca aynı kitaba defalarca bakılıyor.
_METIN_ONBELLEK: dict[str, dict] = {}


def _kitap_metni(pdf_yolu: Path) -> dict | None:
    """
    `tools/kitap_metin.py` ile üretilmiş sayfa metinlerini getir.

    Karar: sanal öğretmen yalnız DÜZ METİN kullanır. Sayfaları Gemini'ye
    görüntü olarak okutan eski yol kaldırıldı — kota harcıyordu ve ders
    ortasında ölçülen en kötü hâli 20 saniyede zaman aşımıydı. Metin
    çıkarma tamamen yerel ve önbellekli.

    Dönen: {"sayfalar": {"12": {"metin": ..., "supheli": n}}, ...} ya da None.
    None ise kitap henüz çevrilmemiştir; çağıran PDF'e düşer.
    """
    ad = pdf_yolu.stem
    if ad in _METIN_ONBELLEK:
        return _METIN_ONBELLEK[ad]
    veri = _json_oku(METIN_DIZINI / f"{ad}.json")
    if veri and veri.get("sayfalar"):
        _METIN_ONBELLEK[ad] = veri
        return veri
    return None


OZET_DIZINI = BASE_DIR / "icerik" / "ozet"


def _kitap_ozeti(kitap_dosyasi: str) -> str:
    """
    `tools/kitap_ozet.py` ile önceden üretilmiş kitap özetini getir (varsa).

    Üretilmemiş bir kitap için sessizce boş döner — özet isteğe bağlıdır,
    `ders_icerigi` özetsiz de çalışır. Bkz. tools/kitap_ozet.py.
    """
    if not kitap_dosyasi:
        return ""
    veri = _json_oku(OZET_DIZINI / f"{Path(kitap_dosyasi).stem}.json")
    if not veri:
        return ""
    return (veri.get("ozet") or "").strip()


SAYFA_ONBELLEK = ONBELLEK / "_sayfa_secimi.json"


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
    """
    Bölüm içinde konuya en yakın sayfaları kelime-örtüşme puanlamasıyla seç.

    Sonuç önbelleklenir: bu tarama bir temanın tüm sayfalarından metin
    çıkarıyor (80+ sayfa) ve tek başına 10 saniyeyi aşabiliyor. Sınıfta
    her istekte bunu yeniden yapmak kabul edilemez bir sessizlik demek.
    """
    konu_k = _kelimeler(konu)
    if not konu_k:
        return list(range(ilk, min(son, ilk + adet - 1) + 1))

    anahtar = f"{pdf_yolu.name}|{ilk}-{son}|{_norm(konu)}|{adet}"
    onb = _sayfa_onbellek_oku()
    if anahtar in onb:
        return onb[anahtar]

    # Kitap çevrilmişse tarama BELLEKTE yapılır: PDF açılmaz, sayfa
    # ayrıştırılmaz. Ölçülen fark büyük — PDF üzerinden 233 sayfalık bir
    # bölümü taramak 55,4 saniye sürüyordu.
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
        # Henüz çevrilmemiş kitap: PDF'e düş (tarama sınırıyla).
        import pdfplumber
        with pdfplumber.open(pdf_yolu) as pdf:
            son_gercek = min(son, len(pdf.pages))
            toplam = max(0, son_gercek - ilk + 1)
            adim = max(1, -(-toplam // TARAMA_SINIRI))     # tavan bölme
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
        # Ardışık okunabilirlik için sayfa sırasına geri diz
        secim = sorted(n for _, n in en_iyi)

    onb[anahtar] = secim
    _sayfa_onbellek_yaz(onb)
    return secim


# ── İçerik çıkarma ──────────────────────────────────────────────────────────

def _metin_cikar(pdf_yolu: Path, sayfalar: list[int]) -> tuple[str, int]:
    """
    Sayfa metinlerini getir. (metin, şüpheli_sembol_sayısı) döndürür.

    Önce çevrilmiş JSON (yerel, anında); yoksa PDF'ten çıkarma. Şüpheli
    sembol, `tools/kitap_metin.py`'nin sayıp DEĞİŞTİRMEDİĞİ '#' ve '$'
    işaretleridir: yönü belli olmayan bir eşitsizliği tahmin etmektense
    modele "bu sayfada sembol şüpheli" demek doğrudur.
    """
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


# NOT: Sayfaları Gemini'ye GÖRÜNTÜ olarak okutan yol (`_gorsel_cikar`)
# kaldırıldı. Karar: sanal öğretmen yalnız düz metin kullanır.
#
# Neden: her yeni tema için gerçek API çağrısı yakıyordu ve ders ortasında
# ölçülen en kötü hâli 20 saniyede zaman aşımıydı (31.07.2026 canlı oturum).
# Kitaplar artık `tools/kitap_metin.py` ile bir kez, çevrimdışı ve API'siz
# metne çevriliyor; bozuk sembol onarımı da orada yapılıyor.
#
# GERİ EKLEMEYİN. Bozuk sembol sorunu görüntüyle değil, iki katmanlı onarım +
# şüpheli sembol uyarısıyla çözülüyor (bkz. tools/kitap_metin.py).


# ── Ana giriş ───────────────────────────────────────────────────────────────

def ders_icerigi(parameters: dict | None = None, player=None,
                 speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    kitaplar = _json_oku(KITAP_PATH)

    if kitaplar is None:
        return ("Kitap indeksi bulunamadı. Hazırlamak için: "
                "python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json")

    ders  = (p.get("ders")  or "").strip() or None
    sinif = (p.get("sinif") or "").strip() or None
    # Sınıf belirtilmediyse tahtanın bulunduğu derslikten çıkar: tahta 10-A'da
    # ise 10. sınıf varsayılır ve öğretmenin her seferinde söylemesi gerekmez.
    if not sinif:
        try:
            from core import tahta
            sinif = tahta.sinif_duzeyi() or None
            if sinif:
                log(f"[Ders İçeriği] sınıf dersliktan alındı: {sinif}")
        except Exception:
            pass
    konu  = (p.get("konu")  or "").strip()
    tema  = (p.get("tema")  or "").strip()

    # Ders çerçevesi (ders/konu) burada resolve ediliyor — YAZILI panelden mi
    # yoksa SESLİ "Farabi, ..." hitabından mı geldiği fark etmez, ikisi de bu
    # noktaya ders_icerigi çağrısı olarak düşer (main.py'nin kendi regex'i
    # yalnızca yazılı paneli görür). ders_hafizasi.py bu satırı arayarak
    # hangi ders kaydının hangi konuyla ilgili olduğunu çözer.
    if ders or konu:
        try:
            from core import transcript
            transcript.log_frame(ders or "", tema or konu)
        except Exception:
            pass

    # Katalog kipi: "hangi kitaplar var", "bölümleri söyle"
    if p.get("liste"):
        log("[Ders İçeriği] katalog listeleniyor")
        sonuc = _katalog(kitaplar, ders, sinif)
        if player is not None and hasattr(player, "show_content"):
            player.show_content("MÜFREDAT — ELDEKİLER", sonuc)
        return sonuc

    # ── 1) Aranacak konu ─────────────────────────────────────────────────────
    # Ders yalnızca kitap üzerinden işlenir: çerçeve (ders, konu, kazanım)
    # öğretmenden gelir, burada yeniden çözülmez. tema verilmişse önceliklidir
    # (bölüm adına daha yakın); yoksa öğretmenin verdiği konu sorgu olur.
    sorgu = tema or konu
    if not sorgu:
        return ("Konu belirtilmedi. Öğretmenin verdiği konuyu 'konu' "
                "parametresiyle ver. Elimde ne olduğunu aşağıda listeliyorum.\n\n"
                + _katalog(kitaplar, ders, sinif))

    # ── 2) Kitap bölümü ─────────────────────────────────────────────────────
    eslesme = _bolum_bul(kitaplar, sorgu, ders, sinif)
    if not eslesme:
        satirlar = ["Kitap bölümü eşleşmedi.", f"Konu: {sorgu}"]
        satirlar.append(_SINIRLI_DEVAM)
        return "\n".join(satirlar)

    kitap, bolum = eslesme
    pdf_yolu = Path(kitap["yol"])
    if not pdf_yolu.is_absolute():
        pdf_yolu = BASE_DIR / pdf_yolu
    if not pdf_yolu.exists():
        return (f"Kitap dosyası bulunamadı: {pdf_yolu.name}. "
                f"kitaplar/ klasörüne kopyalanmış olmalı.")

    adet = int(p.get("sayfa_adedi") or VARSAYILAN_SAYFA)
    sayfalar = _ilgili_sayfalar(pdf_yolu, bolum["ilk_sayfa"], bolum["son_sayfa"],
                                konu or tema, max(1, min(adet, 12)))

    log(f"[Ders İçeriği] {kitap['dosya']} · {bolum['no']}. {bolum['tur']} "
        f"· s.{sayfalar[0]}-{sayfalar[-1]} · {bolum['yontem']}")

    # ── 3) İçeriği çıkar ────────────────────────────────────────────────────
    try:
        icerik, supheli = _metin_cikar(pdf_yolu, sayfalar)
        yontem_notu = ""
        if supheli:
            # Sembolü tahmin etmiyoruz; modele haber veriyoruz.
            yontem_notu = (
                f"UYARI: Bu sayfalarda {supheli} yerde sembol bozuk kodlanmış "
                f"('#' ve '$' işaretleri; ≤ mi ≥ mi belli değil). Formülü "
                f"sembol sembol OKUMA, sözle anlat. Bir eşitsizliğin yönü "
                f"gerekiyorsa kazanım metnine dayan, sayfadaki işarete güvenme."
            )
    except Exception as e:
        return (f"Kitap içeriği okunamadı ({type(e).__name__}: {e}). "
                f"Konu: {sorgu}. " + _SINIRLI_DEVAM)

    if not icerik.strip():
        return (f"{kitap['dosya']} s.{sayfalar[0]}-{sayfalar[-1]} boş döndü. "
                f"Konu: {sorgu}. " + _SINIRLI_DEVAM)

    kirpildi = len(icerik) > MAX_KARAKTER
    if kirpildi:
        icerik = icerik[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"

    # ── 4) Sonucu derle ─────────────────────────────────────────────────────
    bas = [f"DERS KİTABI İÇERİĞİ — {kitap.get('ders','')} {kitap.get('sinif','')}. sınıf",
           f"{bolum['no']}. {bolum['tur']}: {bolum.get('ad','')}",
           f"Kaynak: {kitap['dosya']}, sayfa {', '.join(str(n) for n in sayfalar)}"]
    ozet = _kitap_ozeti(kitap.get("dosya", ""))
    if ozet:
        bas.append(f"Kitap özeti: {ozet}")
    if konu:
        bas.append(f"Konu: {konu}")
    if yontem_notu:
        bas.append(yontem_notu)
    if kirpildi:
        bas.append("Not: içerik uzun olduğu için kısaltıldı; daha fazlası "
                   "gerekiyorsa sayfa_adedi ile yeniden isteyebilirsin.")

    sonuc = "\n".join(bas) + "\n\n" + icerik

    if player is not None and hasattr(player, "show_content"):
        player.show_content(
            f"{kitap.get('ders','ders').upper()} — {bolum.get('ad','')[:34]}", sonuc
        )
    return sonuc
