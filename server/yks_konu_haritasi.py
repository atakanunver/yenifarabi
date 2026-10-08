"""server/yks_konu_haritasi.py — YKS çıkmış soru PDF'lerinden sayfa→konu haritası.

Neden (2026-10-08): `yks.py` sayfaları yalnızca kelime torbasıyla puanlıyordu;
"dörtgenlerde açı" isteğinde kapak sayfası döndü. PDF'lerde iki konu kaynağı var:
  1. PDF yer imleri (TOC) — kaba bölüm başlıkları;
  2. sayfanın üstündeki BEYAZ + KALIN küçük punto "konu bantları"
     (ör. "Üçgen, Çokgen, Dörtgen, Özel Dörtgenler").
Bir sayfanın konusu: o sayfadaki bant(lar); yoksa önceki en yakın bant (ileri taşıma).
Cevap anahtarı bölgesinden itibaren hiçbir sayfa aday değildir.

Çıktı: /mnt/farabi-data/farabi/icerik/eslemeler/yks_konu.json
  {dosya_stem: {"sayfa_konu": {"<sayfa>": ["konu", ...]}, "cevap_anahtari_baslangic": int|null}}

Kullanım (server/ dizininden, yeniden çalıştırılabilir):
  venv/bin/python yks_konu_haritasi.py --kuru   # yalnızca özet
  venv/bin/python yks_konu_haritasi.py          # JSON'u yazar
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

DATA_DIR = Path("/mnt/farabi-data/farabi")
YKS_DIR = DATA_DIR / "yks"
CIKTI = DATA_DIR / "icerik" / "eslemeler" / "yks_konu.json"

_GURULTU = {"toplam", "sayfa", "unite", "konu", "kahve"}
_YIL = re.compile(r"^\d{4}(\s*[-–]\s*\w+)?$")
_KUCUK_HARF_BASLAR = re.compile(r"^[a-zçğıöşü]")
_BAGLAC_BITER = re.compile(r"(,|-|–|\bve|\bile|\bveya)\s*$", re.IGNORECASE)


def _norm_kisa(s: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9 ]+", "", s.translate(tr).lower()).strip()


def _bantlar(sayfa) -> list[tuple[float, float, str]]:
    """Sayfadaki (y0, x0, metin) konu bandı span'leri — beyaz, kalın, küçük punto, üst bölge."""
    cikti = []
    for blok in sayfa.get_text("dict")["blocks"]:
        for satir in blok.get("lines", []):
            for sp in satir["spans"]:
                m = sp["text"].strip()
                if (sp["color"] == 16777215 and "Bold" in sp["font"]
                        and 8 < sp["size"] < 11 and sp["bbox"][1] < 120 and len(m) > 3):
                    cikti.append((sp["bbox"][1], sp["bbox"][0], m))
    cikti.sort()
    return cikti


def _birlestir(spanlar: list[tuple[float, float, str]]) -> list[str]:
    """Çok satıra bölünmüş etiketleri birleştirir: aynı sütunda (x yakın), alt satırda
    (y farkı küçük) ve (küçük harfle başlıyor ya da önceki bağlaç/virgülle bitiyor)."""
    etiketler: list[list] = []  # [y_son, x, metin]
    for y, x, m in spanlar:
        for e in etiketler:
            if 0 < y - e[0] <= 16 and abs(x - e[1]) < 80 and (
                    _KUCUK_HARF_BASLAR.match(m) or _BAGLAC_BITER.search(e[2])
                    or len(m.split()) == 1):
                e[0], e[2] = y, f"{e[2]} {m}"
                break
        else:
            etiketler.append([y, x, m])
    return [e[2] for e in etiketler]


def _temizle(etiket: str) -> list[str]:
    """Gürültüyü at; '• alt konu' madde imlerini ayrı konu olarak döndür."""
    parcalar = [p.strip(" •·\t") for p in re.split(r"\s*[•·]\s*", etiket) if p.strip(" •·\t")]
    sonuc = []
    for p in parcalar:
        n = _norm_kisa(p)
        if not n or n in _GURULTU or _YIL.match(p) or len(n) < 4:
            continue
        sonuc.append(p)
    return sonuc


def _buyuk_harf_mi(s: str) -> bool:
    harfler = [c for c in s if c.isalpha()]
    return bool(harfler) and all(c == c.upper() for c in harfler)


def dosya_haritasi(pdf: Path) -> dict:
    d = pymupdf.open(pdf)
    n = len(d)
    toc = d.get_toc()
    cevap = next((t[2] for t in toc if _norm_kisa(t[1]).startswith("cevap anahtar")), None)
    toc_sayfa: dict[int, list[str]] = {}
    ders_adi_sayfalari: set[int] = set()
    for _sev, baslik, sayfa in toc:
        if sayfa < 1:
            continue
        if _norm_kisa(baslik).startswith("cevap anahtar"):
            continue
        if _buyuk_harf_mi(baslik):
            ders_adi_sayfalari.add(sayfa)  # ders bölümü başlangıcı: konu değil, taşıma sıfırlanır
        else:
            toc_sayfa.setdefault(sayfa, []).append(baslik)

    bant_sayfa: dict[int, list[str]] = {}
    sinir_adayi = None  # TOC'ta 'cevap anahtarı' yoksa: sondaki ders-adı bantları
    for i in range(n):
        sp = _bantlar(d[i])
        if (cevap is None and sinir_adayi is None and i >= n * 0.8
                and any(60 < y < 70 and _buyuk_harf_mi(m) and _norm_kisa(m) not in _GURULTU
                        for y, _x, m in sp)):
            sinir_adayi = i + 1
        etk = []
        for e in _birlestir(sp):
            etk.extend(_temizle(e))
        if etk:
            bant_sayfa[i + 1] = etk
    if cevap is None:
        cevap = sinir_adayi

    sayfa_konu: dict[str, list[str]] = {}
    tasinan: list[str] = []
    son = (cevap - 1) if cevap else n
    for s in range(1, son + 1):
        if s in ders_adi_sayfalari:
            tasinan = []
        yeni = bant_sayfa.get(s) or toc_sayfa.get(s)
        if yeni:
            tasinan = list(dict.fromkeys(yeni))
        if tasinan:
            sayfa_konu[str(s)] = tasinan
    return {"sayfa_konu": sayfa_konu, "cevap_anahtari_baslangic": cevap}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yazmadan özet bas")
    arg = ap.parse_args()
    harita = {}
    for pdf in sorted(YKS_DIR.glob("*.pdf")):
        harita[pdf.stem] = h = dosya_haritasi(pdf)
        sk = h["sayfa_konu"]
        print(f"{pdf.stem}: {len(sk)} sayfada konu, cevap_anahtari={h['cevap_anahtari_baslangic']}")
    if arg.kuru:
        return 0
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps(harita, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
