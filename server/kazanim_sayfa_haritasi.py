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


# ---------------------------------------------------------------- numarasız (ünite + alt başlık) İçindekiler
# felsefe-11 (2026-11-26 OCR): "1. ÜNİTE: AD 13" + numarasız BÜYÜK HARFLİ alt başlıklar ("ÇEVRE ETİĞİ 25").
# Yalnız numaralı yol hiç bölüm bulamazsa ve ≥2 ünite satırı varsa kullanılır.

_UNITE_SATIRI = re.compile(r"^\s*(\d{1,2})\s*\.\s*ÜN[İI]TE\s*:\s*(.+?)[\s.…]*(\d{1,3})\s*$")
_SAYFALI_SATIR = re.compile(r"^\s*(.*?\S)[\s.…]*?\s(\d{1,3})\s*$")
_KALIP = ("giris", "hatirlama", "on degerlendirme", "dusunme koprusu", "ekler", "sozluk",
          "kitap kaynakcasi", "kaynakca", "cevap anahtari", "gorsel genel ag", "turkiye nin mulki",
          "turk dunyasi haritasi")


def _kalip_mi(baslik: str) -> bool:
    n = " ".join(norm(baslik).split())
    return "olcme ve degerlendirme" in n or n.startswith(_KALIP)


def _buyuk_baslik(metin: str) -> str | None:
    """Sondaki OCR çöpünü ("smear mrs", "<a") atıp harflerin ≥%70'i büyükse başlığı döndürür."""
    parca = metin.split()
    while parca and (not any(c.isalpha() for c in parca[-1]) or any(c.islower() for c in parca[-1])):
        parca.pop()
    baslik = _temiz(" ".join(parca))
    harf = [c for c in baslik if c.isalpha()]
    return baslik if harf and sum(c.isupper() for c in harf) / len(harf) >= 0.7 else None


def uniteli_icindekiler(metin: str) -> list[dict]:
    """→ [{"tur": "unite"|"baslik"|"kalip", "unite": int, "baslik", "sayfa": basılı}].
    Alt başlıklar son görülen üniteye bağlanır; sayfası ünite başından küçük satır (OCR bozuk)
    atılır; küçük harfli alt-alt başlıklar ("Mutluluk ve Hayat İlişkisi") ne bölüm ne sınırdır."""
    girdiler: list[dict] = []
    unite = None
    for satir in metin.split("\n"):
        m = _UNITE_SATIRI.match(satir)
        if m:
            unite = {"tur": "unite", "unite": int(m.group(1)), "baslik": _temiz(m.group(2)),
                     "sayfa": int(m.group(3))}
            girdiler.append(unite)
            continue
        s = _SAYFALI_SATIR.match(satir)
        if not s:
            continue
        sayfa = int(s.group(2))
        if _kalip_mi(s.group(1)):
            girdiler.append({"tur": "kalip", "unite": unite["unite"] if unite else None,
                             "baslik": _temiz(s.group(1)), "sayfa": sayfa})
            continue
        baslik = _buyuk_baslik(s.group(1))
        if unite and baslik and sayfa >= unite["sayfa"]:
            girdiler.append({"tur": "baslik", "unite": unite["unite"], "baslik": baslik, "sayfa": sayfa})
    return girdiler


def baslik_satiri_ara(sayfalar: dict, baslik: str, bas: int, son: int) -> int | None:
    """Gövdede `baslik`ın başlık satırı olarak geçtiği ilk sayfa: satır (ya da iki satırın
    birleşimi) normalize eşit ya da iki yönde de ≥0.8 kelime örtüşmesi."""
    hedef_n, hedef_k = norm(baslik).split(), kelimeler(baslik)
    for p in range(bas, son + 1):
        satirlar = [s for s in _metin(sayfalar, p).split("\n") if s.strip()]
        for i, s in enumerate(satirlar):
            for aday in (s, " ".join(satirlar[i:i + 2])):
                if norm(aday).split() == hedef_n:
                    return p
                ak = kelimeler(aday)
                ortak = len(hedef_k & ak)
                if hedef_k and ak and ortak / len(hedef_k) >= 0.8 and ortak / len(ak) >= 0.8:
                    return p
    return None


def uniteli_bolumler(sayfalar: dict, toc_bas: int, n: int, offset: int,
                     aranacak: list[tuple[int, str]] | None = None) -> list[dict]:
    """Numarasız İçindekiler → bölümler [{"no": "<ünite>.<sıra>", "baslik", "ilk_sayfa", "son_sayfa"}].
    İçindekiler `toc_bas`tan ünite satırı süren sayfalara taşar. `aranacak` (ünite, plan konusu):
    İçindekiler'de bulunmayan (OCR bozuk / sayfasız) alt başlık o ünitenin gövdesinde aranır."""
    girdiler: list[dict] = []
    p = toc_bas
    while p < toc_bas + 4:
        g = uniteli_icindekiler(_metin(sayfalar, p))
        if p > toc_bas and not any(x["tur"] == "unite" for x in g):
            break
        girdiler += g
        p += 1
    unite_bas = {x["unite"]: x["sayfa"] + offset for x in girdiler if x["tur"] == "unite"}
    if len(unite_bas) < 2:
        return []
    sinirlar = {x["sayfa"] + offset for x in girdiler}
    bolumler = [{"unite": x["unite"], "baslik": x["baslik"], "ilk_sayfa": x["sayfa"] + offset}
                for x in girdiler if x["tur"] == "baslik"]
    acilis = ("giris", "hatirlama", "on degerlendirme", "dusunme koprusu")
    for u in dict.fromkeys(u for u, _k in aranacak or []):
        eksik = [k for uu, k in aranacak if uu == u
                 and not any(b["unite"] == u and baslik_puani(k, b["baslik"]) >= 0.5 for b in bolumler)]
        if not eksik:
            continue
        sonraki = [s for k, s in unite_bas.items() if k > u]
        u_son = (min(sonraki) - 1) if sonraki else n
        if u in unite_bas:
            u_bas = unite_bas[u]
        else:  # ünite satırı da okunamamış: önceki son sınırdan sonrası
            u_bas = max((s for s in sinirlar if s <= u_son), default=0) + 1
        kalip = [x["sayfa"] + offset for x in girdiler if x["tur"] == "kalip" and x["unite"] == u
                 and u_bas <= x["sayfa"] + offset <= u_son and not _olcme_mi(x["baslik"])]
        if not kalip:  # açılış sayfaları (GİRİŞ … DÜŞÜNME KÖPRÜSÜ) gövdeden
            kalip = [p for p in range(u_bas, u_son + 1) for s in _metin(sayfalar, p).split("\n")
                     if " ".join(norm(s).split()) in acilis]
        bas = (max(kalip) + 1) if kalip else u_bas + 1  # ünite kapağındaki konu listesini atla
        bulunan = []
        for konu in eksik:
            ilk = baslik_satiri_ara(sayfalar, konu, bas, u_son)
            bulunan.append([konu, ilk])
        # başlık satırı OCR'da kaybolmuş ilk konu: açılış sayfalarından hemen sonra başlar
        ilk_bilinen = min([b["ilk_sayfa"] for b in bolumler if b["unite"] == u]
                          + [i for _k, i in bulunan if i], default=None)
        if kalip and bulunan[0][1] is None and (ilk_bilinen is None or bas < ilk_bilinen):
            bulunan[0][1] = bas
        for konu, ilk in bulunan:
            if ilk:
                bolumler.append({"unite": u, "baslik": konu, "ilk_sayfa": ilk})
                sinirlar.add(ilk)
    tum = sorted(sinirlar | set(unite_bas.values()))
    sonuc, sira = [], {}
    for b in sorted(bolumler, key=lambda b: b["ilk_sayfa"]):
        sira[b["unite"]] = sira.get(b["unite"], 0) + 1
        sonraki = [s for s in tum if s > b["ilk_sayfa"]]
        sonuc.append({"no": f"{b['unite']}.{sira[b['unite']]}", "baslik": b["baslik"],
                      "ilk_sayfa": b["ilk_sayfa"], "son_sayfa": (sonraki[0] - 1) if sonraki else n})
    return sonuc


def kitap_bolumleri(kitap: dict, metin_dizini: Path = METIN_DIZINI,
                    aranacak: list[tuple[int, str]] | None = None) -> dict:
    """Kitap kaydı → {"bolumler": [...], "offset", "offset_orani", "toc": [PDF sayfaları]}.
    Numaralı bölüm hiç yoksa numarasız ünite/alt başlık İçindekiler'i denenir (`aranacak`:
    gövdede aranacak (ünite, plan konusu) çiftleri)."""
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
    bolumler = bolum_araliklari(girdiler, offset or 0, n, tema_sonlari)
    if not bolumler and toc:
        bolumler = uniteli_bolumler(sayfalar, toc[0], n, offset or 0, aranacak)
    return {"bolumler": bolumler, "offset": offset, "offset_orani": oran, "toc": toc}


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


def harita_uret(plan: dict, kitaplar: list[dict], bolum_haritasi: dict[str, list[dict]],
                tde_haritasi: dict[str, dict] | None = None
                ) -> tuple[list[dict], dict, list[str], list[str], list[str]]:
    """→ (kayıtlar, {(sınıf, ders): [eşlenen, toplam, kitaplı_mı, kodlu]}, eşlenemeyen, şüpheli,
    alınmayan). Kod-başlık kelime ortaklığı olmayan (ve başlık yolunun da bulamadığı) eşleme
    tabloya ALINMAZ (kullanıcı kararı 2026-11-25): sunucu o kazanım için eski eşlemeye düşer.
    Türk Dili ve Edebiyatı `tde_haritasi` (dosya → tde_kitap) ile metin adı yolundan eşlenir;
    plan teması yoksa önceki haftanın teması taşınır."""
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
            tde = norm(ders) == TDE_DERS
            tema_no = None
            for hafta in sorted(haftalar, key=_hafta_sirasi):
                kazanim = haftalar[hafta]
                if not isinstance(kazanim, str) or not kazanim.strip():
                    continue
                sayac[1] += 1
                if kod_normalle(kazanim_kodu(kazanim)):
                    sayac[3] += 1
                konu = (konular.get(sinif, {}).get(ders, {}) or {}).get(hafta) or {}
                if tde:
                    kayit = None
                    for k in adaylar:
                        yapi = (tde_haritasi or {}).get(k["dosya"]) or {"bolumler": [], "temalar": []}
                        tema_no = tde_plan_temasi(konu.get("tema", ""), kazanim, yapi["temalar"]) or tema_no
                        kayit = tde_kaydi(sinif, ders, hafta, kazanim, konu, k, yapi, tema_no)
                        if kayit:
                            kayit.pop("_adim")
                            break
                else:
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


# ---------------------------------------------------------------- Türk Dili ve Edebiyatı (metin adı)
# TDE kodları (TDE2.1 …) bölüm değil beceri kodudur (1 dinleme, 2 okuma, 3 konuşma, 4 yazma) ve her
# temada tekrar eder; kitap İçindekiler'inde numaralı bölüm yok. Bağ: plan konusundaki metin adı
# (“San’at”) ↔ İçindekiler'deki metin adı ("Okuma Sırası: “San’at”"), aynı tema içinde.

TDE_DERS = "turk dili ve edebiyati"
_TDE_KATLA = str.maketrans({"â": "a", "î": "i", "û": "u", "Â": "A", "Î": "I", "Û": "U", "\xad": None})
_TDE_BASLIK_ONEKI = ("okuma", "edebiyat atolyesi", "dinleme", "metin tahlili", "yazma",
                     "sozlu iletisim", "dil bilgisi")
_TDE_BECERI = {"1": "dinleme", "2": "okuma", "3": "konusma", "4": "yazma"}
_TDE_DURAK = {"metin", "tahlili", "okuma", "tema", "icerigine", "uygun", "edebiyat", "atolyesi",
              "yazma", "konusma", "dinleme", "izleme", "modlu", "sirasi", "oncesi", "sonrasi",
              "anlama", "anlatma", "yapabilme", "yazabilme", "hazirlayabilme", "temasinda"}


def _tn(s: str) -> str:
    return " ".join(norm((s or "").translate(_TDE_KATLA)).split())


def _tk(s: str) -> set[str]:
    return {k for k in _tn(s).split() if len(k) > 3}


def tde_tur(metin: str) -> str | None:
    """İçindekiler satırı bir TDE bölüm başlığıysa türü (okuma/dinleme/konusma/yazma/olcme/
    dilbilgisi), değilse None. "Okuma Öncesi/Sırası/Sonrası" alt satırdır."""
    n = _tn(metin)
    if re.search(r"\b(sirasi|oncesi|sonrasi)\b", n):
        return None
    if "olcme ve degerlendirme" in n:
        return "olcme"
    if not n.startswith(_TDE_BASLIK_ONEKI) or (n.startswith("sozlu iletisim") and n != "sozlu iletisim"):
        return None  # 11: "Sözlü İletişim Engellerini … Drama" bir etkinlik adı, başlık değil
    for anahtar, tur in (("dil bilgisi", "dilbilgisi"), ("dinleme", "dinleme"), ("yazma", "yazma"),
                         ("konusma", "konusma"), ("sozlu iletisim", "konusma"), ("okuma", "okuma")):
        if anahtar in n:
            return tur
    return None


def _devam_mi(onceki: str, satir: str) -> bool:
    return (onceki.count("“") > onceki.count("”") or onceki.count("(") > onceki.count(")")
            or onceki.endswith(("\xad", "-")) or satir[:1] in "”)(" or satir[:1].islower())


def tde_icindekiler(metin: str) -> list[dict]:
    """TDE İçindekiler sayfası → [{"metin", "sayfa": basılı}] (sıra korunur). Sayfa numarası aynı
    satırda (nokta dolgusu) ya da sonraki satırda tek başına; metin adı açık tırnak/parantez ya da
    tirele sonraki satıra taşabilir; taşan satır öncekinin tekrarıysa ("Picasso’nun Hatları /
    Picasso’nun Hatları”") atılır."""
    metin = metin.split(_OCR_IZI, 1)[0]
    girdiler: list[dict] = []
    tampon = ""
    for ham in metin.split("\n"):
        satir = ham.replace(" ", " ").strip()
        if not satir:
            continue
        sm = _YALNIZ_SAYI.match(satir)
        if sm:
            if tampon:
                girdiler.append({"metin": _temiz(tampon), "sayfa": int(sm.group(1))})
            tampon = ""
            continue
        ss = _SON_SAYFA.match(satir)
        govde = ss.group(1) if ss else satir
        if tampon and _devam_mi(tampon, satir):
            yeni = _tn(govde.strip("“”\" "))
            if not (yeni and _tn(tampon).endswith(yeni)):
                tampon = (tampon[:-1] if tampon.endswith(("\xad", "-")) else tampon + " ") + govde
        else:
            tampon = govde
        if ss:
            girdiler.append({"metin": _temiz(tampon), "sayfa": int(ss.group(2))})
            tampon = ""
    return girdiler


def _metin_adi(metin: str) -> str:
    ad = metin.split(":", 1)[1] if re.search(r"sırası\s*:", metin, re.IGNORECASE) else metin
    return ad.strip(" “”\"")


def tde_bolumleri(girdiler: list[dict], offset: int, sayfa_sayisi: int,
                  temalar: list[dict]) -> list[dict]:
    """Bölüm başlıkları + altlarındaki metin adları → [{"tur", "etiket", "tema", "ilk_sayfa",
    "son_sayfa", "adlar"}]. Tema: kitaplar.json tema aralığı (PDF) bölüm başlangıcını içeren tema.
    Son sayfa: sonraki bölüm başlığı − 1, tema sonunu aşmaz."""
    bolumler: list[dict] = []
    for g in girdiler:
        tur = tde_tur(g["metin"])
        if tur:
            bolumler.append({"tur": tur, "etiket": g["metin"], "ilk_sayfa": g["sayfa"] + offset,
                             "adlar": []})
        elif bolumler and not re.search(r"\b(tema|unite)", _tn(g["metin"])):
            bolumler[-1]["adlar"].append(_metin_adi(g["metin"]))
    bolumler = [b for b in bolumler if 1 <= b["ilk_sayfa"] <= sayfa_sayisi]
    baslar = sorted(b["ilk_sayfa"] for b in bolumler)
    for b in bolumler:
        tema = next((t for t in temalar if t["ilk_sayfa"] <= b["ilk_sayfa"] <= t["son_sayfa"]), None)
        b["tema"] = int(tema["no"]) if tema else None
        sonraki = [s for s in baslar if s > b["ilk_sayfa"]]
        son = sonraki[0] - 1 if sonraki else sayfa_sayisi
        b["son_sayfa"] = min(son, tema["son_sayfa"]) if tema else son
    return bolumler


def tde_kitap(kitap: dict, metin_dizini: Path = METIN_DIZINI) -> dict:
    """TDE kitabı → {"bolumler", "temalar", "offset", "toc"}."""
    yol = metin_dizini / f"{Path(kitap['dosya']).stem}.json"
    try:
        sayfalar = json.loads(yol.read_text(encoding="utf-8"))["sayfalar"]
    except (OSError, ValueError, KeyError):
        return {"bolumler": [], "temalar": [], "offset": None, "toc": []}
    n = int(kitap.get("sayfa_sayisi") or max((int(k) for k in sayfalar), default=0))

    def _baslik_sayisi(p: int) -> int:
        return sum(1 for g in tde_icindekiler(_metin(sayfalar, p)) if tde_tur(g["metin"]))

    bas = next((p for p in range(1, 16) if "icindekiler" in norm(_metin(sayfalar, p))
                and _baslik_sayisi(p) >= 3), None)
    toc = []
    if bas is not None:
        toc = [bas]
        while toc[-1] + 1 < 16 and _baslik_sayisi(toc[-1] + 1) >= 3:
            toc.append(toc[-1] + 1)
    girdiler = [g for p in toc for g in tde_icindekiler(_metin(sayfalar, p))]
    offset, _oran = offset_hesapla(sayfalar, (toc[-1] + 1) if toc else 1, n)
    temalar = [{"no": b.get("no"), "ad": b.get("ad", ""), "ilk_sayfa": int(b["ilk_sayfa"]),
                "son_sayfa": int(b["son_sayfa"])} for b in kitap.get("bolumler", [])
               if b.get("ilk_sayfa") and b.get("son_sayfa")]
    return {"bolumler": tde_bolumleri(girdiler, offset or 0, n, temalar), "temalar": temalar,
            "offset": offset, "toc": toc}


def tde_plan_temasi(plan_tema: str, kazanim: str, temalar: list[dict]) -> int | None:
    """Plan teması numarası: "1. TEMA: …" → 1; yoksa kazanımdaki “Tema Adı” temasında → kitap teması."""
    m = re.search(r"(\d+)\s*(tema|unite)\b", _tn(plan_tema))
    if m:
        return int(m.group(1))
    for ad in re.findall(r"“([^”]+)”", kazanim or ""):
        for t in temalar:
            if _tn(t["ad"]) == _tn(ad):
                return int(t["no"])
    return None


def tde_plan_turu(konu: str, kazanim: str) -> str | None:
    """Plan konusundaki etkinlik türü; konu yoksa TDE beceri kodu (TDE2.1 → okuma)."""
    kelime = set(_tn(konu).split())
    if "olcme" in kelime and "degerlendirme" in kelime:
        return "olcme"
    for tur in ("dinleme", "yazma", "konusma", "okuma"):
        if tur in kelime:
            return tur
    m = re.match(r"\s*TDE(\d)\.", kazanim or "")
    return _TDE_BECERI.get(m.group(1)) if m else None


def tde_esle(konu: str, kazanim: str, tema_no: int | None, yapi: dict
             ) -> tuple[dict, str | None, str] | None:
    """Aynı temadaki bölümlerden seçim → (bölüm, metin adı|None, adım). Adımlar:
    'tirnak' plan konusundaki tırnaklı ad ↔ İçindekiler metin adı (aynı tema, tür serbest);
    'ad' tırnaksız konu kelimeleri metin adının ≥ yarısını kapsar (aynı tür);
    'tur' türün tek bölümü / kelimesi en çok tutan bölüm / hepsi birleşik aralık."""
    if tema_no is None:
        return None
    tema_b = [b for b in yapi["bolumler"] if b["tema"] == tema_no]
    tur = tde_plan_turu(konu, kazanim)
    en_iyi = None
    for ad in re.findall(r"[“\"]([^”\"]+)[”\"]", konu or ""):
        for b in tema_b:
            for a in b["adlar"]:
                p = baslik_puani(_tn(ad), _tn(a))
                if p >= 0.5 and (en_iyi is None or p > en_iyi[2]):
                    en_iyi = (b, a, p)
    if en_iyi:
        return en_iyi[0], en_iyi[1], "tirnak"
    sorgu_k = _tk(konu) - _TDE_DURAK
    turdekiler = [b for b in tema_b if b["tur"] == tur]
    for b in turdekiler:
        for a in b["adlar"]:
            ak = _tk(a) - _TDE_DURAK
            p = len(sorgu_k & ak) / len(ak) if ak else 0.0
            if p >= 0.5 and (en_iyi is None or p > en_iyi[2]):
                en_iyi = (b, a, p)
    if en_iyi:
        return en_iyi[0], en_iyi[1], "ad"
    if not turdekiler:
        return None
    puanli = [(len(sorgu_k & (_tk(b["etiket"] + " " + " ".join(b["adlar"])) - _TDE_DURAK)), b)
              for b in turdekiler]
    enc = max(p for p, _b in puanli)
    secilen = [b for p, b in puanli if p == enc]
    if len(secilen) == 1:
        return secilen[0], None, "tur"
    birlesik = {**secilen[0], "etiket": f"{secilen[0]['etiket']} (+{len(secilen) - 1} bölüm)",
                "son_sayfa": secilen[-1]["son_sayfa"]}
    return birlesik, None, "tur"


def tde_kaydi(sinif: str, ders: str, hafta: str, kazanim: str, konu: dict, kitap: dict,
              yapi: dict, tema_no: int | None) -> dict | None:
    plan_konu = (konu or {}).get("konu", "") or ""
    r = tde_esle(plan_konu, kazanim, tema_no, yapi)
    if r is None:
        return None
    bolum, ad, adim = r
    supheli = []
    uzunluk = bolum["son_sayfa"] - bolum["ilk_sayfa"] + 1
    if uzunluk < 1 or uzunluk > 40:
        supheli.append(f"aralık {uzunluk} sayfa")
    return {"sinif": str(sinif), "ders": ders, "hafta": str(hafta),
            "kazanim_kodu": kazanim_kodu(kazanim), "kazanim": kazanim, "plan_konu": plan_konu,
            "plan_tema": (konu or {}).get("tema", "") or "", "kitap": kitap["dosya"],
            "bolum_no": f"TEMA{tema_no}/" + re.sub(r"\s+", "", bolum["etiket"]),
            "baslik": bolum["etiket"] + (f" — {ad}" if ad else ""),
            "ilk_sayfa": bolum["ilk_sayfa"], "son_sayfa": bolum["son_sayfa"],
            "yontem": "metin_adi", "_supheli": supheli, "_adim": adim}


# ---------------------------------------------------------------- main

def _plan_konulari(plan: dict, kitap: dict, kitaplar: list[dict]) -> list[tuple[int, str]]:
    """Kitabın aday olduğu (sınıf, ders) planlarından (kod ünitesi, konu) çiftleri."""
    cift = []
    for sinif, dersler in plan.get("kazanimlar", {}).items():
        for ders, haftalar in dersler.items():
            if kitap not in aday_kitaplar(kitaplar, sinif, ders):
                continue
            for hafta, kazanim in haftalar.items():
                no = kod_normalle(kazanim_kodu(kazanim if isinstance(kazanim, str) else ""))
                konu = ((plan.get("konular", {}).get(sinif, {}).get(ders) or {}).get(hafta) or {}).get("konu")
                if no and konu:
                    cift.append((int(no.split(".")[0]), konu))
    return list(dict.fromkeys(cift))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yazmadan rapor bas")
    ap.add_argument("--rapor", type=Path, help="raporu bu dosyaya da yaz")
    arg = ap.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    kitaplar = json.loads(KITAP_PATH.read_text(encoding="utf-8")).get("kitaplar", [])
    satirlar: list[str] = ["# Kitaplar"]
    bolum_haritasi: dict[str, list[dict]] = {}
    tde_haritasi: dict[str, dict] = {}
    for k in kitaplar:
        kb = kitap_bolumleri(k, aranacak=_plan_konulari(plan, k, kitaplar))
        bolum_haritasi[k["dosya"]] = kb["bolumler"]
        if norm(k.get("ders", "")) == TDE_DERS:
            tk = tde_kitap(k)
            tde_haritasi[k["dosya"]] = tk
            satirlar.append(f"{k['dosya']}: TDE İçindekiler s.{tk['toc']}, offset {tk['offset']}, "
                            f"{len(tk['bolumler'])} bölüm, "
                            f"{sum(len(b['adlar']) for b in tk['bolumler'])} metin adı")
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

    kayitlar, oran, eslenemeyen, supheliler, alinmayan = harita_uret(plan, kitaplar, bolum_haritasi, tde_haritasi)

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
            ("yontem: 'metin_adi' = TDE: plan konusundaki metin adı/etkinlik türü ↔ İçindekiler (aynı tema); "
             "bolum_no 'TEMA<n>/<bölüm başlığı>'."),
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
