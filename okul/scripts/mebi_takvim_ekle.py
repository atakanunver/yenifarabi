"""MEBİ 2026-2027 YKS deneme takvimini sınav takvimine ve 11/12 şubelerine duyuru olarak girer.

Kullanım (okul/ dizininden):
    venv/bin/python scripts/mebi_takvim_ekle.py [--kuru]
--kuru: hiçbir şey yazmaz, yalnız ne ekleneceğini yazar.
Tekrar çalıştırılırsa aynı başlıklı sınav/duyuru atlanır (hiçbir şey silinmez, güncellenmez).
Pano ve tahta hatırlatmaları bu satırlardan `sinavlar.yaklasan_denemeler` ile türetilir.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import push
import sinavlar
import zaman

YAZAR = "atakan"  # rotalar/duyuru_api.py ile aynı yönetici
DUZEYLER = "11,12"
ACIKLAMA = "TYT · AYT · YDT oturumları — mebi.eba.gov.tr › Denemeler/Taramalar"
TAKVIM = [
    ("2026-09-21", "2026-09-27"),
    ("2026-10-12", "2026-10-18"),
    ("2026-11-09", "2026-11-15"),
    ("2026-12-14", "2026-12-20"),
    ("2027-01-11", "2027-01-17"),
    ("2027-02-15", "2027-02-21"),
    ("2027-03-15", "2027-03-21"),
    ("2027-04-12", "2027-04-18"),
    ("2027-05-10", "2027-05-16"),
    ("2027-05-17", "2027-05-23"),
    ("2027-05-31", "2027-06-06"),
    ("2027-06-07", "2027-06-13"),
]
DUYURU_BASLIK = "MEBİ 2026-2027 YKS Deneme Takvimi"
DUYURU_BITIS = "2027-06-13 23:59:59"


def _baslik(n: int) -> str:
    return f"MEBİ {n}. YKS Denemesi"


def _duyuru_metni() -> str:
    satirlar = [
        f"{n}. Deneme: {sinavlar.deneme_araligi(t, b)} {b[:4]}" for n, (t, b) in enumerate(TAKVIM, 1)
    ]
    return (
        "\n".join(satirlar)
        + "\n\nTüm denemeler TYT, AYT ve YDT oturumlarından oluşur."
        + "\nDenemelere mebi.eba.gov.tr adresindeki Denemeler/Taramalar modülünden erişilir."
    )


def main(argv: list[str]) -> int:
    if not set(argv) <= {"--kuru"}:
        print(__doc__)
        return 2
    kuru = "--kuru" in argv
    conn = db.baglanti()
    try:
        yazar = conn.execute(
            "SELECT id FROM kullanici WHERE kullanici_adi = ? AND rol = 'yonetici' AND aktif = 1", (YAZAR,)
        ).fetchone()
        if yazar is None:
            print(f"Yönetici '{YAZAR}' bulunamadı.")
            return 1
        yid = yazar["id"]
        simdi = zaman.simdi_str()
        mevcut = {r[0] for r in conn.execute("SELECT baslik FROM sinav WHERE tur = 'deneme'")}
        yeni_sinav = [(n, t, b) for n, (t, b) in enumerate(TAKVIM, 1) if _baslik(n) not in mevcut]
        subeler = [
            r[0]
            for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci WHERE sinif LIKE '11-%' OR sinif LIKE '12-%'")
        ]
        subeler.sort()
        var = {
            r[0]
            for r in conn.execute(
                "SELECT hedef FROM duyuru WHERE baslik = ? AND hedef_tur = 'sinif'", (DUYURU_BASLIK,)
            )
        }
        yeni_duyuru = [s for s in subeler if s not in var]
        print(f"Eklenecek deneme: {len(yeni_sinav)} ({', '.join(str(n) for n, _, _ in yeni_sinav) or '-'})")
        print(f"Duyuru eklenecek şubeler: {', '.join(yeni_duyuru) or '-'}")
        if kuru:
            print("\n" + _duyuru_metni())
            return 0
        conn.executemany(
            "INSERT INTO sinav (yazar_id, tur, baslik, duzeyler, tarih, bitis, aciklama, olusturma)"
            " VALUES (?, 'deneme', ?, ?, ?, ?, ?, ?)",
            [(yid, _baslik(n), DUZEYLER, t, b, ACIKLAMA, simdi) for n, t, b in yeni_sinav],
        )
        metin = _duyuru_metni()
        conn.executemany(
            "INSERT INTO duyuru (yazar_id, baslik, metin, hedef_tur, hedef, yayin, bitis)"
            " VALUES (?, ?, ?, 'sinif', ?, ?, ?)",
            [(yid, DUYURU_BASLIK, metin, s, simdi, DUYURU_BITIS) for s in yeni_duyuru],
        )
        conn.commit()
        # Birden çok şubeye giren öğretmen/yönetici tek bildirim alsın.
        alicilar = {i for s in yeni_duyuru for i in push.duyuru_alicilari(conn, "sinif", s, yid)}
        print("Push:", push.gonder(conn, alicilar, "duyuru"))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
