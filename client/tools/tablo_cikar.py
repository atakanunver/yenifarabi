#!/usr/bin/env python3
"""
tools/tablo_cikar.py — Ders kitabı PDF'lerindeki TABLOLARI yapılandırılmış
JSON'a çıkarır (offline, API yok). `kitap_metin.py`'nin CLI/kilit desenini
takip eder, ama tamamen ayrı bir çıktı: `icerik/metin/`'in düz sayfa metnine
dokunmaz, kardeşi `icerik/tablolar/`'a yazar.

Neden pdfplumber (kitap_metin.py fitz kullanıyor, burada DEĞİL): tablo
hücre/sütun yapısını (`find_tables`/`extract`) yalnızca pdfplumber veriyor,
fitz'te böyle bir API yok. kitap_metin.py'nin fitz'e geçiş gerekçesi (büyük
kitaplıkta OOM, bkz. o dosyanın docstring'i) TEK kitap + yalnızca-tablo
taraması için geçerli değil — burada aynı OOM riski yok, kitap başına bir
süreç, tüm kitaplığı aynı anda taramıyor.

KALİTE FİLTRESİ (2026-08-30, biyoloji-9.pdf s.1'de canlı bulundu):
`find_tables()` kapak sayfası gibi süslemeli/çizgili sayfalarda GERÇEK OLMAYAN
tablolar buluyor (ölçüldü: s.1'de 2 sahte "tablo", içerik başlık metni).
Gerçek bir tablo (ör. "Hücre Organelleri") ile ayırt etmek için: en az 2 satır
+ 2 sütun VE hücrelerin en az %50'si boş olmayan bir tablo, gerçek sayılır —
aksi hâlde atlanır, sayılmaz bile.

`metin_ozet`: tablo hücrelerinin düz, doğal dile çevrilmiş hâli — ham
"Organel | Görevi | Mitokondri | ATP üretimi" OCR-tarzı metin RAG için kötü
(kullanıcının kendi örneği); bunun yerine embedding'e giden şey "Tablo:
{başlık}. {satır1_hücre1} — {satır1_hücre2}. ..." şeklinde.

Kullanım:
    python tools/tablo_cikar.py kitaplar/biyoloji-9.pdf --json icerik/tablolar
    python tools/tablo_cikar.py kitaplar/ --json icerik/tablolar --zorla
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:      # Windows — kilitsiz devam
    fcntl = None

import pdfplumber

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

MIN_SATIR = 2
MIN_SUTUN = 2
MIN_DOLU_ORAN = 0.5


def _hucre_temiz(h) -> str:
    return (h or "").strip().replace("\n", " ")


def _gercek_tablo_mu(satirlar: list[list]) -> bool:
    if len(satirlar) < MIN_SATIR:
        return False
    sutun_sayisi = max((len(s) for s in satirlar), default=0)
    if sutun_sayisi < MIN_SUTUN:
        return False
    toplam = sum(len(s) for s in satirlar)
    dolu = sum(1 for s in satirlar for h in s if _hucre_temiz(h))
    return toplam > 0 and (dolu / toplam) >= MIN_DOLU_ORAN


def _baslik_tahmin_et(sayfa, tablo_bbox) -> str:
    """Tablonun ÜSTÜNDE, tabloya en yakın satırı başlık adayı olarak alır —
    best-effort, garanti değil, boş dönebilir."""
    ust_sinir = tablo_bbox[1]
    en_yakin, en_yakin_mesafe = "", float("inf")
    for satir in sayfa.extract_text_lines() if hasattr(sayfa, "extract_text_lines") else []:
        alt = satir.get("bottom", 0)
        if alt <= ust_sinir:
            mesafe = ust_sinir - alt
            if mesafe < en_yakin_mesafe and mesafe < 40:  # ~40pt içindeyse "yakın" say
                en_yakin_mesafe = mesafe
                en_yakin = satir.get("text", "").strip()
    return en_yakin


def _metin_ozet_uret(baslik: str, headers: list[str], govde: list[list[str]]) -> str:
    parcalar = [f"Tablo: {baslik}."] if baslik else ["Tablo."]
    baslik_var = any(_hucre_temiz(h) for h in headers)
    for satir in govde:
        hucreler = [_hucre_temiz(h) for h in satir if _hucre_temiz(h)]
        if not hucreler:
            continue
        if baslik_var and len(headers) == len(satir):
            eslesmis = [f"{_hucre_temiz(headers[i])}: {_hucre_temiz(satir[i])}"
                        for i in range(len(satir)) if _hucre_temiz(satir[i])]
            parcalar.append(" — ".join(eslesmis) + ".")
        else:
            parcalar.append(" — ".join(hucreler) + ".")
    return " ".join(parcalar)


def kitaptan_tablo_cikar(pdf_yolu: Path) -> dict:
    tablolar = []
    with pdfplumber.open(pdf_yolu) as pdf:
        toplam_sayfa = len(pdf.pages)
        for i, sayfa in enumerate(pdf.pages, start=1):
            try:
                bulunanlar = sayfa.find_tables()
            except Exception:
                continue
            for tno, t in enumerate(bulunanlar, start=1):
                try:
                    veri = t.extract()
                except Exception:
                    continue
                if not veri or not _gercek_tablo_mu(veri):
                    continue
                headers, govde = veri[0], veri[1:]
                baslik = _baslik_tahmin_et(sayfa, t.bbox)
                tablolar.append({
                    "sayfa": i,
                    "tablo_no": tno,
                    "baslik": baslik,
                    "headers": [_hucre_temiz(h) for h in headers],
                    "rows": [[_hucre_temiz(h) for h in satir] for satir in govde],
                    "metin_ozet": _metin_ozet_uret(baslik, headers, govde),
                })
    return {"kitap": pdf_yolu.name, "sayfa_sayisi": toplam_sayfa, "tablolar": tablolar}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ders kitabı PDF -> tablo JSON (API yok)")
    ap.add_argument("kaynak", help="PDF dosyası ya da klasör")
    ap.add_argument("--json", default="icerik/tablolar",
                    help="Hedef klasör (varsayılan: icerik/tablolar)")
    ap.add_argument("--zorla", action="store_true",
                    help="Zaten çıkarılmış (hedefte aynı adla json'u olan) "
                         "kitapları da yeniden işle.")
    a = ap.parse_args()

    kaynak = Path(a.kaynak)
    hedef = BASE_DIR / a.json if not Path(a.json).is_absolute() else Path(a.json)
    hedef.mkdir(parents=True, exist_ok=True)

    _kilit_tut = None
    if fcntl is not None:
        kilit_dosyasi = open(hedef / ".tablo_cikar.lock", "w")
        try:
            fcntl.flock(kilit_dosyasi, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _kilit_tut = kilit_dosyasi
        except OSError:
            print(f"Bu hedef için başka bir dönüştürme süreci zaten çalışıyor "
                  f"({hedef}), çıkılıyor.")
            return 0

    if kaynak.is_dir():
        pdfler = sorted(kaynak.glob("*.pdf"))
    elif kaynak.exists():
        pdfler = [kaynak]
    else:
        print(f"Bulunamadı: {kaynak}")
        return 1

    if not pdfler:
        print(f"{kaynak} içinde PDF yok.")
        return 1

    if not a.zorla:
        atlanan = [p for p in pdfler if (hedef / f"{p.stem}.json").exists()]
        if atlanan:
            print(f"{len(atlanan)} kitap zaten işlenmiş, atlanıyor (--zorla ile tekrar):")
            for p in atlanan:
                print(f"  = {p.name}")
            pdfler = [p for p in pdfler if p not in atlanan]
        if not pdfler:
            print("İşlenecek yeni kitap yok.")
            return 0

    print(f"{len(pdfler)} kitapta tablo aranıyor (yerel, API çağrısı yok)…\n")
    for pdf in pdfler:
        try:
            sonuc = kitaptan_tablo_cikar(pdf)
            (hedef / f"{pdf.stem}.json").write_text(
                json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {pdf.name:35s} {sonuc['sayfa_sayisi']:4} sayfa · "
                  f"{len(sonuc['tablolar']):3} gerçek tablo")
        except Exception as e:
            print(f"  ✖ {pdf.name}: {type(e).__name__}: {str(e)[:90]}")

    print(f"\nBitti → {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
