"""PDF'ten çıkan deneme JSON'unu okul.db öğrencileriyle eşler; eşleşenleri DB kimliğiyle (okul_no, ad, şube) yeniden yazar.

Kullanım (okul/ dizininden):
    venv/bin/python scripts/deneme_eslestir.py ham.json eslesmis.json
Kurallar (kullanıcı onaylı, 2026-10-29), yanlış çocuğa karne gitmesin diye muhafazakâr:
  tam    : okul_no DB'de var, ad ve şube aynı (PDF şubesi 'XX' ise şube yok sayılır).
  adla   : okul_no 0/DB'de yok -> normalize ad DB'de TAM OLARAK 1 öğrenciyle aynıysa o öğrenci.
  benzer : okul_no DB'de var, şube aynı/XX, PDF adı DB adıyla örtüşüyor (ortak sözcük, sözcük öneki ya da bitişik yazım).
Diğerleri atlanır ve rapora (okul_no + PDF adı) yazılır; deneme_yukle.py'ye yalnız eşleşenler gider.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ayarlar import AYAR
from metin import normalize_isim, tr_kucuk

_KATLA = str.maketrans("ıçğöşü", "icgosu")  # PDF'te büyük harfte noktalar/aksanlar düşmüş olabilir


def _sozcukler(ad: str) -> list[str]:
    return [t for t in normalize_isim(ad).translate(_KATLA).split() if t]


def _sube_uyar(pdf_sinif: str, db_sinif: str) -> bool:
    p = tr_kucuk(pdf_sinif or "").replace(" ", "")
    return p.endswith("xx") or p == tr_kucuk(db_sinif or "").replace(" ", "")


def _benzer(pdf_ad: str, db_ad: str) -> bool:
    p, d = _sozcukler(pdf_ad), _sozcukler(db_ad)
    if not p or not d:
        return False
    for t in p:
        if t in d or (len(t) >= 3 and any(x.startswith(t) for x in d)):
            return True
    bp, bd = "".join(p), "".join(d)
    return len(bp) >= 5 and (bp in bd or bd in bp)


def eslestir(pdf_ogrenciler: list[dict], db_ogrenciler: list[dict]) -> tuple[list[dict], dict]:
    no_ile = {o["okul_no"]: o for o in db_ogrenciler}
    ad_ile: dict[str, list[dict]] = {}
    for o in db_ogrenciler:
        ad_ile.setdefault(normalize_isim(o["ad_soyad"]), []).append(o)
    sonuc, rapor = [], {"tam": 0, "adla": 0, "benzer": 0, "eslesmeyen": []}
    for s in pdf_ogrenciler:
        no = s.get("okul_no")
        db = no_ile.get(no)
        tur = None
        if db is not None and normalize_isim(s["ad_soyad"]) == normalize_isim(db["ad_soyad"]) and _sube_uyar(s["sinif"], db["sinif"]):
            tur = "tam"
        elif db is not None and _sube_uyar(s["sinif"], db["sinif"]) and _benzer(s["ad_soyad"], db["ad_soyad"]):
            tur = "benzer"
        elif db is None:
            adaylar = ad_ile.get(normalize_isim(s["ad_soyad"]), [])
            if len(adaylar) == 1:
                db, tur = adaylar[0], "adla"
        if tur is None:
            rapor["eslesmeyen"].append({"okul_no": no, "ad_soyad": s["ad_soyad"], "sinif": s["sinif"]})
            continue
        rapor[tur] += 1
        sonuc.append({**s, "okul_no": db["okul_no"], "ad_soyad": db["ad_soyad"], "sinif": db["sinif"]})
    return sonuc, rapor


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    belge = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"file:{AYAR.db_yolu}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        db = [dict(r) for r in conn.execute("SELECT okul_no, ad_soyad, sinif FROM ogrenci")]
    finally:
        conn.close()
    yeni, r = eslestir(belge["ogrenciler"], db)
    belge["ogrenciler"] = yeni
    Path(argv[1]).write_text(json.dumps(belge, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{belge['ad']}: tam={r['tam']} adla={r['adla']} benzer={r['benzer']} atlanan={len(r['eslesmeyen'])}")
    for x in r["eslesmeyen"]:
        print("  atlandı:", x["okul_no"], x["ad_soyad"], x["sinif"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
