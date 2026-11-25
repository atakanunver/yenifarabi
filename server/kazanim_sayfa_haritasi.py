"""server/kazanim_sayfa_haritasi.py — yıllık plan kazanımı → ders kitabı PDF sayfa aralığı.

Neden (2026-11-25): konu artık yıllık plandan geliyor; `icerik.py` kitapta yalnız tema
düzeyinde (kitaplar.json `bolumler`, 50-130 sayfa) bölüm bulabiliyordu. Kitapların
İçindekiler sayfalarında "1.2. BAŞLIK ....... 22" satırları var ve bölüm numarası Maarif
kazanım koduyla aynı (`BİY.9.1.2` ↔ `1.2.`). Bu betik:
  1. Her kitabın İçindekiler'ini (PDF s.~7-10, metin JSON'undan) `(bölüm_no, başlık,
     basılı_sayfa)` olarak ayrıştırır; sayfası İçindekiler'de olmayan bölümü gövde
     sayfalarında başlık satırından arar;
  2. basılı→PDF sayfa farkını (offset) gövde sayfalarının ilk/son satırındaki basılı
     numaradan çoğunlukla bulur;
  3. aralık: ilk = basılı + offset, son = sonraki numaralı bölüm / "Ölçme ve Değerlendirme"
     başlangıcı − 1 (yoksa tema sonu ya da kitap sonu);
  4. kazanım kodunu bölüm numarasına indirger (`yontem: "kod"`); kodsuz ya da kodu tutmayan
     kazanımda plan konusu ↔ bölüm başlığı kelime örtüşmesi ≥0.5 (`yontem: "baslik"`).
Eşlenemeyen kazanım kayıtlara girmez, raporda listelenir. Çıktıda `bolumler` anahtarı
YOKTUR (icerik._elle_eslemeler onu tema eşlemesi sayar).

Çıktı: /mnt/farabi-data/farabi/icerik/eslemeler/kazanim_sayfa.json
  {"_aciklama": [...], "_uretim": ..., "_tarih": "YYYY-AA-GG", "kayitlar": [{"sinif", "ders",
   "hafta", "kazanim_kodu", "kazanim", "plan_konu", "plan_tema", "kitap", "bolum_no",
   "baslik", "ilk_sayfa", "son_sayfa", "yontem"}]}

Kullanım (server/ dizininden, yeniden çalıştırılabilir):
  venv/bin/python kazanim_sayfa_haritasi.py --kuru              # yalnızca rapor
  venv/bin/python kazanim_sayfa_haritasi.py --rapor /tmp/r.txt  # JSON'u yazar, raporu da kaydeder
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from icerik import ESLEME_DIR, KITAP_PATH, METIN_DIZINI, _ders_eslesir
from kazanim import VERI_DIR
from metin_araclari import kelimeler, norm

PLAN = VERI_DIR / "kazanimlar.json"
CIKTI = ESLEME_DIR / "kazanim_sayfa.json"

_SINIFLAR = {"9", "10", "11", "12"}
_ORTAKLIK_YOK = "kod-başlık kelime ortaklığı yok"
_DERS_GURULTU = {"sinif", "ders", "kitabi", "meb", "t", "c"}  # kitaplar.json ders adındaki ekler
_OCR_IZI = "[SAYFADAKİ GÖRSEL"  # metin JSON'unda OCR eki; İçindekiler'i ikinci kez (bozuk) içerir
# "1.2. Başlık" / "3.1.Yeşil" / "1.1.\t" — en az iki numara; "1. Tema" eşleşmez.
_NUMARALI = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})+)\.?(?:\s+|(?=[^\d\s.])|$)(.*)$")
# satır sonunda nokta dolgusu / sekme / çoklu boşluktan sonra gelen sayfa numarası
_SON_SAYFA = re.compile(r"^(.*?)(?:[.…\ufffd]{2,}|\t|\s{2,}| )[\s.…\ufffd\t \x08]*(\d{1,3})\s*$")
_YALNIZ_SAYI = re.compile(r"^[\s\t \x08]*(\d{1,3})[\s\t \x08]*$")
_DOLGU = re.compile(r"[.…\ufffd]{2,}.*$")  # \ufffd: din-10 dolgusu bozuk karakter
_TEMA_SATIRI = re.compile(r"^(\d+\s+)?(tema|unite)(\s+\d+)?$")
_KOD = re.compile(
    r"^\s*((?:[A-ZÇĞİÖŞÜ]+\d*\.)?\d+(?:\.[0-9A-Z]+)*)\.?(?=\s)")


# ---------------------------------------------------------------- İçindekiler

def _temiz(s: str) -> str:
    return re.sub(r"[\s \x08]+", " ", _DOLGU.sub("", s)).strip(" .\t")


def _olcme_mi(s: str) -> bool:
    return "olcme ve degerlendirme" in norm(s)


def icindekiler_ayristir(metin: str) -> list[dict]:
    """Tek İçindekiler sayfası → [{"no": "1.2"|None, "baslik", "sayfa": basılı int|None}].
    `no` None olanlar "Ölçme ve Değerlendirme" satırlarıdır (yalnız aralık sınırı).
    Başlık en çok 3 satıra bölünebilir; sayfa numarası aynı satırda (nokta dolgusu/sekme
    sonrası) ya da tek başına sonraki satırda olabilir. Sütunlu dizgide (felsefe-10,
    matematik_9) numaralar dolgulu satırlardan SONRA blok hâlinde gelir: sayfasız dolgulu
    satırlar sıraya alınır, sonraki tek-sayı satırları sırayla (azalmayan) atanır."""
    metin = metin.split(_OCR_IZI, 1)[0]
    girdiler: list[dict] = []
    kuyruk: list[dict] = []  # sayfası sonradan gelecek dolgulu satırlar (girdi ya da yer tutucu)
    son_atanan = 0
    bekleyen: dict | None = None
    devam = 0

    def _bitir(sayfa: int | None) -> None:
        nonlocal bekleyen
        if bekleyen is not None:
            bekleyen["baslik"] = _temiz(bekleyen.pop("_ham"))
            bekleyen["sayfa"] = sayfa
            dolgu = bekleyen.pop("_dolgu")
            if sayfa is not None:
                kuyruk.clear()  # satır içi numara: sütunlu dizgi değil
            elif dolgu:
                kuyruk.append(bekleyen)
            if bekleyen["baslik"] or sayfa is not None:
                girdiler.append(bekleyen)
        bekleyen = None

    for satir in metin.split("\n"):
        m = _NUMARALI.match(satir)
        olcme = not m and _olcme_mi(satir)
        sm = _YALNIZ_SAYI.match(satir)
        if m or olcme:
            _bitir(None)
            govde = m.group(2) if m else satir
            bekleyen = {"no": m.group(1) if m else None, "_ham": "", "_dolgu": False}
            devam = 0
        elif bekleyen is None:
            if sm and kuyruk and int(sm.group(1)) >= son_atanan:
                son_atanan = int(sm.group(1))
                kuyruk.pop(0)["sayfa"] = son_atanan
            elif _DOLGU.search(satir) and not _SON_SAYFA.match(satir):
                kuyruk.append({})  # numarasız sayfasız satır ("Alıştırmalar ....."): yer tutucu
            continue
        else:
            govde = satir
            if sm:
                _bitir(int(sm.group(1)))
                continue
            if not satir.strip(" \t\u2002\x08"):
                continue
            if _TEMA_SATIRI.match(norm(satir)) or re.match(r"^\s*\d+\.\s*(tema|ünite)", satir, re.IGNORECASE):
                bekleyen = None  # "1.1.\nTEMA\nTepki" gibi tema açılışı: bölüm değil
                continue
            devam += 1
            if devam > 3:
                _bitir(None)
                continue
        ss = _SON_SAYFA.match(govde)
        if ss:
            bekleyen["_ham"] += " " + ss.group(1)
            _bitir(int(ss.group(2)))
        else:
            bekleyen["_ham"] += " " + govde
            if _DOLGU.search(govde):
                bekleyen["_dolgu"] = True
                _bitir(None)  # sayfasız dolgu: başlık bitti, numara sonradan gelebilir
    _bitir(None)
    return girdiler


def icindekiler_sayfalari(sayfalar: dict, ust: int = 16) -> list[int]:
    """İçindekiler PDF sayfaları: "içindekiler" geçen ilk sayfadan (yoksa sayfalı numaralı
    ≥3 girdisi olan ilk sayfadan) başlayıp sayfalı numaralı girdisi süren ardışık blok."""
    def _sayfali(p: int) -> int:
        return sum(1 for g in icindekiler_ayristir(_metin(sayfalar, p))
                   if g["no"] and g["sayfa"] is not None)

    bas = next((p for p in range(1, ust) if "icindekiler" in norm(_metin(sayfalar, p))), None)
    if bas is None:
        bas = next((p for p in range(1, ust) if _sayfali(p) >= 3), None)
    if bas is None:
        return []
    blok = [bas]
    while blok[-1] + 1 < ust and _sayfali(blok[-1] + 1) >= 1:
        blok.append(blok[-1] + 1)
    return blok


def _metin(sayfalar: dict, p: int) -> str:
    return (sayfalar.get(str(p)) or {}).get("metin", "") or ""


# ---------------------------------------------------------------- offset / gövde arama

def offset_hesapla(sayfalar: dict, bas: int, son: int) -> tuple[int | None, float]:
    """Gövde sayfalarının ilk/son satırındaki basılı numaradan PDF−basılı farkı (çoğunluk)
    ve o farkın tutarlılık oranı. Ölçüm yoksa (None, 0.0)."""
    farklar: Counter = Counter()
    for p in range(bas, son + 1):
        satirlar = [s for s in _metin(sayfalar, p).split("\n") if s.strip()]
        for s in satirlar[:1] + satirlar[-1:]:
            if re.fullmatch(r"\s*\d{1,3}\s*", s):
                fark = p - int(s)
                if -5 <= fark <= 40:
                    farklar[fark] += 1
                    break
    if not farklar:
        return None, 0.0
    fark, adet = farklar.most_common(1)[0]
    return fark, adet / sum(farklar.values())


def govde_ara(sayfalar: dict, no: str, baslik: str, bas: int, son: int) -> int | None:
    """İçindekiler'de sayfası olmayan bölümün başladığı PDF sayfası: satırı `no.` ile başlayan
    ve başlığıyla ≥0.5 kelime örtüşen ilk sayfa. Üç ve daha çok farklı bölüm numarası
    sıralayan sayfalar (tema açılışı listeleri) atlanır."""
    hedef = kelimeler(baslik)
    desen = re.compile(rf"^\s*{re.escape(no)}\.?\s+(.*)$")
    for p in range(bas, son + 1):
        satirlar = _metin(sayfalar, p).split("\n")
        numaralar = {m.group(1) for s in satirlar if (m := _NUMARALI.match(s))}
        if len(numaralar) >= 3:
            continue
        for i, s in enumerate(satirlar):
            m = desen.match(s)
            if not m:
                continue
            aday = kelimeler(" ".join([m.group(1)] + satirlar[i + 1:i + 3]))
            if not hedef or len(hedef & aday) / len(hedef) >= 0.5:
                return p
    return None


# ---------------------------------------------------------------- bölüm aralıkları

def bolum_araliklari(girdiler: list[dict], offset: int, sayfa_sayisi: int,
                     tema_sonlari: dict[str, int] | None = None) -> list[dict]:
    """İki ("1.2") ve üç ("1.2.3") düzeyli bölümler için PDF aralığı. `girdiler`de `pdf` (PDF
    sayfası) dolu olmalı ya da `sayfa` (basılı) + offset. Bir bölümün sonu: kendi düzeyinde
    ya da daha üstteki bir sonraki numaralı bölümün ya da "Ölçme ve Değerlendirme" satırının
    başlangıcı − 1; sonrası yoksa tema sonu (kitaplar.json) / kitap sonu."""
    tema_sonlari = tema_sonlari or {}

    def _pdf(g: dict) -> int | None:
        if g.get("pdf") is not None:
            return g["pdf"]
        return g["sayfa"] + offset if g.get("sayfa") is not None else None

    def _derin(g: dict) -> int:
        return g["no"].count(".") + 1 if g["no"] else 0

    bolumler = []
    for g in girdiler:
        if _derin(g) not in (2, 3):
            continue
        ilk = _pdf(g)
        if ilk is None or not 1 <= ilk <= sayfa_sayisi:
            continue
        sonraki = sorted(p for h in girdiler if _derin(h) <= _derin(g)
                         and (p := _pdf(h)) is not None and ilk < p <= sayfa_sayisi)
        if sonraki:
            son = sonraki[0] - 1
        else:
            ts = tema_sonlari.get(g["no"].split(".")[0])
            son = ts if ts and ts >= ilk else sayfa_sayisi
        bolumler.append({"no": g["no"], "baslik": g["baslik"], "ilk_sayfa": ilk,
                         "son_sayfa": son})
    return bolumler


def kitap_bolumleri(kitap: dict, metin_dizini: Path = METIN_DIZINI) -> dict:
    """Kitap kaydı → {"bolumler": [...], "offset", "offset_orani", "toc": [PDF sayfaları]}."""
    yol = metin_dizini / f"{Path(kitap['dosya']).stem}.json"
    try:
        sayfalar = json.loads(yol.read_text(encoding="utf-8"))["sayfalar"]
    except (OSError, ValueError, KeyError):
        return {"bolumler": [], "offset": None, "offset_orani": 0.0, "toc": [], "hata": "metin yok"}
    n = int(kitap.get("sayfa_sayisi") or max((int(k) for k in sayfalar), default=0))
    toc = icindekiler_sayfalari(sayfalar)
    girdiler: list[dict] = []
    gorulen: dict[str, dict] = {}
    for p in toc:
        for g in icindekiler_ayristir(_metin(sayfalar, p)):
            if g["no"] is None:
                girdiler.append(g)
            elif g["no"] not in gorulen:
                gorulen[g["no"]] = g
                girdiler.append(g)
            elif gorulen[g["no"]]["sayfa"] is None and g["sayfa"] is not None:
                gorulen[g["no"]].update(g)
    govde_bas = (toc[-1] + 1) if toc else 1
    offset, oran = offset_hesapla(sayfalar, govde_bas, n)
    for g in girdiler:
        if g["no"] and g["no"].count(".") in (1, 2) and (g["sayfa"] is None or offset is None):
            g["pdf"] = govde_ara(sayfalar, g["no"], g["baslik"], govde_bas, n)
    tema_sonlari = {str(b.get("no")): int(b["son_sayfa"]) for b in kitap.get("bolumler", [])
                    if b.get("son_sayfa")}
    return {"bolumler": bolum_araliklari(girdiler, offset or 0, n, tema_sonlari),
            "offset": offset, "offset_orani": oran, "toc": toc}


# ---------------------------------------------------------------- kod / başlık eşleme

def kazanim_kodu(metin: str) -> str | None:
    """Kazanım metninin başındaki kod ("BİY.9.1.2. ..." → "BİY.9.1.2"); en az iki parça."""
    m = _KOD.match(metin or "")
    if not m or "." not in m.group(1):
        return None
    return m.group(1)


def kod_normalle(kod: str | None) -> str | None:
    """Kazanım kodu → İçindekiler bölüm numarası. Belirsiz biçimde None (başlık yoluna düşer).
    BİY.9.1.2→1.2, MAT.11.1.1→1.1, PSK.1.1→1.1, 9.1.1→1.1, 12.1.1.1→1.1, 1.1→1.1;
    TDE2.1, A.2.1, 11.1.1.1.1, ENG.8.1.R3 → None."""
    if not kod:
        return None
    parca = kod.split(".")
    if re.fullmatch(r"[A-ZÇĞİÖŞÜ]{2,}", parca[0]):
        sayilar = parca[1:]
        if not all(p.isdigit() for p in sayilar):
            return None
        if len(sayilar) == 3 and sayilar[0] in _SINIFLAR:
            return f"{sayilar[1]}.{sayilar[2]}"
        if len(sayilar) == 2 and sayilar[0] not in _SINIFLAR:
            return f"{sayilar[0]}.{sayilar[1]}"
        return None
    if not all(p.isdigit() for p in parca):
        return None
    if len(parca) in (3, 4) and parca[0] in _SINIFLAR:
        return f"{parca[1]}.{parca[2]}"
    if len(parca) == 2 and parca[0] not in _SINIFLAR:
        return f"{parca[0]}.{parca[1]}"
    return None


def _kodsuz(metin: str) -> str:
    kod = kazanim_kodu(metin)
    return metin[len(kod):].lstrip(". ").strip() if kod else (metin or "").strip()


def sorgular(plan_konu: str, kazanim: str) -> list[str]:
    """Başlık yolu için aday sorgular: plan konusu, parantezsiz hâli ve ":"/"•" parçaları,
    sonra kodsuz kazanım metni. Plan konusu çoğu zaman "Ana: Alt (ayrıntı, ...)" biçiminde
    uzun; tüm metinle örtüşme oranı eşiğin altında kalıyordu."""
    adaylar = [plan_konu]
    sade = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", re.sub(r"\([^()]*\)", " ", plan_konu or ""))
    sade = re.sub(r"[(\[][^()\[\]]*$", " ", sade)  # plan metni "…" ile kesilmiş: kapanmamış parantez
    sade = re.sub(r"[()\[\]…]", " ", sade)
    adaylar.append(sade)
    adaylar += re.split(r"[:•]", sade)
    adaylar.append(_kodsuz(kazanim))
    return [a.strip() for a in dict.fromkeys(adaylar) if a and a.strip()]


def baslik_puani(sorgu: str, baslik: str) -> float:
    """`icerik._esleme_bolumu` ölçütü: normalize eşitlik → 2.0 (her orandan üstün),
    yoksa |sorgu∩başlık| / |sorgu| (kelimeler: `metin_araclari.kelimeler`)."""
    sorgu_n, sorgu_k = norm(sorgu).split(), kelimeler(sorgu)
    if not sorgu_n:
        return 0.0
    if norm(baslik).split() == sorgu_n:
        return 2.0
    return len(sorgu_k & kelimeler(baslik)) / len(sorgu_k) if sorgu_k else 0.0


def baslik_esle(sorgu: str, bolumler: list[dict]) -> tuple[dict, float] | None:
    """En yüksek puanlı bölüm (eşit puanda daha derin/dar olan); puan ≥ 0.5 değilse None."""
    en_iyi, puan = None, 0.0
    for b in bolumler:
        p = baslik_puani(sorgu, b["baslik"])
        if p > puan or (en_iyi and p == puan and b["no"].count(".") > en_iyi["no"].count(".")):
            en_iyi, puan = b, p
    return (en_iyi, puan) if en_iyi and puan >= 0.5 else None


def aday_kitaplar(kitaplar: list[dict], sinif: str, ders: str) -> list[dict]:
    return [k for k in kitaplar if str(k.get("sinif")) == str(sinif)
            and _ders_eslesir(ders, k.get("ders", ""))]


def kazanim_esle(sinif: str, ders: str, hafta: str, kazanim: str, konu: dict,
                 adaylar: list[dict], bolum_haritasi: dict[str, list[dict]]) -> dict | None:
    """Tek kazanımı eşler; kayıt (+ `_supheli` notları) ya da None.
    Kod adayı: kodun bölüm numarası (aday kitaplardan başlığı kazanıma en çok benzeyen).
    Başlık adayı: plan konusu / kazanım ↔ başlık puanı ≥ 0.5 olan en iyi bölüm (üç düzey dahil).
    Başlık adayı, kod adayının kendi başlık puanından KESİN yüksekse kazanır: kazanım
    numarası ile kitap bölüm numarası her derste örtüşmüyor (fizik-10 2.2 "İş, enerji ve güç"
    kazanımı kitapta 2.1; biyoloji-9 1.6 organik moleküller kitapta 2.2)."""
    kod = kazanim_kodu(kazanim)
    no = kod_normalle(kod)
    plan_konu = (konu or {}).get("konu", "") or ""
    plan_tema = (konu or {}).get("tema", "") or ""
    metin_k = kelimeler(_kodsuz(kazanim)) | kelimeler(plan_konu)
    aday_sorgular = sorgular(plan_konu, kazanim)

    def _puan(b: dict) -> float:
        return max((baslik_puani(q, b["baslik"]) for q in aday_sorgular), default=0.0)

    secim, yontem, kod_puan = None, None, -1.0
    if no:
        bulunan = [(k, b) for k in adaylar for b in bolum_haritasi.get(k["dosya"], [])
                   if b["no"] == no]
        if bulunan:
            secim = max(bulunan, key=lambda kb: (_puan(kb[1]), len(metin_k & kelimeler(kb[1]["baslik"]))))
            yontem, kod_puan = "kod", _puan(secim[1])
    en_iyi = None
    for sorgu in aday_sorgular:
        for k in adaylar:
            r = baslik_esle(sorgu, bolum_haritasi.get(k["dosya"], []))
            if r and (en_iyi is None or (r[1], r[0]["no"].count("."))
                      > (en_iyi[2], en_iyi[1]["no"].count("."))):
                en_iyi = (k, r[0], r[1])
    if en_iyi and en_iyi[2] > kod_puan and (secim is None or en_iyi[1] is not secim[1]):
        secim, yontem = (en_iyi[0], en_iyi[1]), "baslik"
    if secim is None:
        return None
    kitap, bolum = secim
    supheli = []
    if yontem == "kod" and not metin_k & kelimeler(bolum["baslik"]):
        supheli.append(_ORTAKLIK_YOK)
    uzunluk = bolum["son_sayfa"] - bolum["ilk_sayfa"] + 1
    if uzunluk < 1 or uzunluk > 40:
        supheli.append(f"aralık {uzunluk} sayfa")
    return {"sinif": str(sinif), "ders": ders, "hafta": str(hafta), "kazanim_kodu": kod,
            "kazanim": kazanim, "plan_konu": plan_konu, "plan_tema": plan_tema,
            "kitap": kitap["dosya"], "bolum_no": bolum["no"], "baslik": bolum["baslik"],
            "ilk_sayfa": bolum["ilk_sayfa"], "son_sayfa": bolum["son_sayfa"],
            "yontem": yontem, "_supheli": supheli}


def _hafta_sirasi(h: str):
    return (0, int(h)) if str(h).isdigit() else (1, str(h))


def harita_uret(plan: dict, kitaplar: list[dict], bolum_haritasi: dict[str, list[dict]]
                ) -> tuple[list[dict], dict, list[str], list[str], list[str]]:
    """→ (kayıtlar, {(sınıf, ders): [eşlenen, toplam, kitaplı_mı, kodlu]}, eşlenemeyen, şüpheli,
    alınmayan). Kod-başlık kelime ortaklığı olmayan (ve başlık yolunun da bulamadığı) eşleme
    tabloya ALINMAZ (kullanıcı kararı 2026-11-25): sunucu o kazanım için eski eşlemeye düşer."""
    kayitlar, oran, eslenemeyen, supheliler, alinmayan = [], {}, [], [], []
    konular = plan.get("konular", {})
    for sinif, dersler in plan.get("kazanimlar", {}).items():
        for ders, haftalar in dersler.items():
            adaylar = aday_kitaplar(kitaplar, sinif, ders)
            for k in adaylar:
                fazla = set(norm(k.get("ders", "")).split()) - set(norm(ders).split()) - _DERS_GURULTU
                if any(not w.isdigit() for w in fazla):  # "matematik" planı ↔ "temel matematik" kitabı
                    supheliler.append(f"{sinif} {ders}: kitap dersi farklı → {k['dosya']} "
                                      f"({k.get('ders', '')})")
            sayac = oran.setdefault((sinif, ders), [0, 0, bool(adaylar), 0])
            for hafta in sorted(haftalar, key=_hafta_sirasi):
                kazanim = haftalar[hafta]
                if not isinstance(kazanim, str) or not kazanim.strip():
                    continue
                sayac[1] += 1
                if kod_normalle(kazanim_kodu(kazanim)):
                    sayac[3] += 1
                konu = (konular.get(sinif, {}).get(ders, {}) or {}).get(hafta) or {}
                kayit = kazanim_esle(sinif, ders, hafta, kazanim, konu, adaylar, bolum_haritasi)
                etiket = f"{sinif} {ders} h{hafta}: {kazanim[:70]}"
                if kayit is None:
                    if adaylar:
                        eslenemeyen.append(etiket)
                    continue
                notlar = kayit.pop("_supheli")
                yer = f"{etiket} → {kayit['kitap']} {kayit['bolum_no']} s.{kayit['ilk_sayfa']}-{kayit['son_sayfa']}"
                if _ORTAKLIK_YOK in notlar:
                    alinmayan.append(f"{yer}: {'; '.join(notlar)}")
                    continue
                sayac[0] += 1
                supheliler += [f"{yer}: {s}" for s in notlar]
                kayitlar.append(kayit)
    return kayitlar, oran, eslenemeyen, supheliler, alinmayan


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yazmadan rapor bas")
    ap.add_argument("--rapor", type=Path, help="raporu bu dosyaya da yaz")
    arg = ap.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    kitaplar = json.loads(KITAP_PATH.read_text(encoding="utf-8")).get("kitaplar", [])
    satirlar: list[str] = ["# Kitaplar"]
    bolum_haritasi: dict[str, list[dict]] = {}
    for k in kitaplar:
        kb = kitap_bolumleri(k)
        bolum_haritasi[k["dosya"]] = kb["bolumler"]
        notlar = []
        if kb.get("hata"):
            notlar.append(kb["hata"])
        if kb["offset"] is None:
            notlar.append("ŞÜPHELİ: offset ölçülemedi")
        elif kb["offset_orani"] < 0.6:
            notlar.append(f"ŞÜPHELİ: offset tutarsız (%{kb['offset_orani'] * 100:.0f})")
        satirlar.append(f"{k['dosya']}: İçindekiler s.{kb['toc']}, offset {kb['offset']} "
                        f"(%{kb['offset_orani'] * 100:.0f}), {len(kb['bolumler'])} bölüm"
                        + (f" — {'; '.join(notlar)}" if notlar else ""))

    kayitlar, oran, eslenemeyen, supheliler, alinmayan = harita_uret(plan, kitaplar, bolum_haritasi)

    satirlar.append("\n# Ders başına eşleme (eşlenen/toplam, kodlu kazanım sayısı)")
    top_e = top_t = 0
    for (sinif, ders), (e, t, kitapli, kodlu) in sorted(
            oran.items(), key=lambda x: (int(x[0][0]), x[0][1])):
        if not kitapli:
            continue
        satirlar.append(f"{sinif:>2} {ders:<34} {e:>3}/{t:<3} %{100 * e / max(t, 1):5.1f}  kodlu={kodlu}")
        if kodlu and sinif in {"9", "10", "11"}:
            top_e, top_t = top_e + e, top_t + t
    kitapsiz = sorted(f"{s} {d}" for (s, d), v in oran.items() if not v[2])
    satirlar.append(f"Kodlu Maarif (9-11, kitaplı) toplam: {top_e}/{top_t} "
                    f"%{100 * top_e / max(top_t, 1):.1f}")
    satirlar.append(f"Kitabı olmayan dersler ({len(kitapsiz)}): {', '.join(kitapsiz)}")
    satirlar.append(f"\n# Eşlenemeyen (kitabı olan derslerde) — {len(eslenemeyen)}")
    satirlar += [f"  {s}" for s in eslenemeyen]
    satirlar.append(f"\n# Tabloya alınmadı (şüpheli) — {len(alinmayan)}")
    satirlar += [f"  {s}" for s in alinmayan]
    satirlar.append(f"\n# Şüpheli (tabloda, işaretli) — {len(supheliler)}")
    satirlar += [f"  {s}" for s in supheliler]
    satirlar.append(f"\nToplam kayıt: {len(kayitlar)}")
    rapor = "\n".join(satirlar)
    print(rapor)
    if arg.rapor:
        arg.rapor.write_text(rapor + "\n", encoding="utf-8")
    if arg.kuru:
        return 0
    cikti = {
        "_aciklama": [
            "Yıllık plan kazanımı → ders kitabı PDF sayfa aralığı (sayfalar PDF sayfası, 1 tabanlı).",
            "yontem: 'kod' = kazanım kodu ↔ İçindekiler bölüm no; 'baslik' = plan konusu ↔ başlık örtüşmesi.",
            "Otomatik üretilir; elle düzeltme kazanim_sayfa_elle.json'a yazılır.",
        ],
        "_uretim": "server/kazanim_sayfa_haritasi.py",
        "_tarih": datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat(),
        "kayitlar": kayitlar,
    }
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(cikti, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
