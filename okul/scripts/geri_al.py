"""Şema göçünü geri alır (acil durum). Kullanım:

    sudo systemctl stop farabi-okul          # önce servis durmalı
    cp veri/okul.db veri/yedek/okul_<tarih>.db   # (ya da sqlite3 .backup)
    venv/bin/python scripts/geri_al.py --hedef 6 [--db veri/okul.db] [--onayla]   # yalnızca V7+V8'i geri alır
    git checkout <eski-commit>               # eski kod, yeni şemayı beklemez
    sudo systemctl start farabi-okul

Eski kodu çalıştırmadan GOCLER'i geri almayın: yeni kod açılışta eksik göçü yeniden uygular.
--onayla olmadan yalnızca ne silineceğini (satır sayılarıyla) gösterir. Her adım tek işlemde çalışır.
Silinen tablolardaki veri kurtarılamaz: önce yedek alın.
DİKKAT: --hedef, geri dönmek istediğiniz user_version'dır. Çalışan üretimde V5 (Arena XP/rozet) ve V6 (deneme sonuçları)
CANLI VERİ tutar; --hedef 4 onları da siler. Önce kuru çalıştırmayı (--onayla olmadan) okuyun.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# user_version N'den N-1'e inmek için çalışan betik. Yeni göç eklenince buraya da eklenir.
GERI = {
    36: """
DROP TABLE IF EXISTS deneme_sinif_yorum;
DROP TABLE IF EXISTS deneme_pdf;
""",
    35: """
DROP TABLE IF EXISTS tesekkur;
DROP TABLE IF EXISTS bilmece_cevap;
DROP TABLE IF EXISTS bilmece_gun;
DROP TABLE IF EXISTS bilmece;
DELETE FROM bilgi_xp WHERE kaynak IN ('bilmece', 'tesekkur');
CREATE TABLE bilgi_xp_eski (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    kaynak        TEXT NOT NULL CHECK (kaynak IN ('arena_dogru', 'arena_bonus', 'maraton_tur', 'gayret')),
    ref           TEXT NOT NULL,
    miktar        INTEGER NOT NULL CHECK (miktar > 0),
    gun           TEXT NOT NULL,
    zaman         TEXT NOT NULL,
    UNIQUE (kullanici_id, kaynak, ref)
);
INSERT INTO bilgi_xp_eski SELECT id, kullanici_id, kaynak, ref, miktar, gun, zaman FROM bilgi_xp;
DROP TABLE bilgi_xp;
ALTER TABLE bilgi_xp_eski RENAME TO bilgi_xp;
CREATE INDEX bilgi_xp_kullanici ON bilgi_xp(kullanici_id);
""",
    34: """
ALTER TABLE sudoku_oyun DROP COLUMN ipucu;
ALTER TABLE sudoku_bot DROP COLUMN ipucu;
""",
    33: """
DELETE FROM bilgi_xp WHERE kaynak = 'gayret';
CREATE TABLE bilgi_xp_eski (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    kaynak        TEXT NOT NULL CHECK (kaynak IN ('arena_dogru', 'arena_bonus', 'maraton_tur')),
    ref           TEXT NOT NULL,
    miktar        INTEGER NOT NULL CHECK (miktar > 0),
    gun           TEXT NOT NULL,
    zaman         TEXT NOT NULL,
    UNIQUE (kullanici_id, kaynak, ref)
);
INSERT INTO bilgi_xp_eski SELECT id, kullanici_id, kaynak, ref, miktar, gun, zaman FROM bilgi_xp;
DROP TABLE bilgi_xp;
ALTER TABLE bilgi_xp_eski RENAME TO bilgi_xp;
CREATE INDEX bilgi_xp_kullanici ON bilgi_xp(kullanici_id);
""",
    32: """
ALTER TABLE sudoku_oyun DROP COLUMN tahta;
""",
    31: """
ALTER TABLE sudoku_bot DROP COLUMN tahta;
""",
    30: """
DROP TABLE IF EXISTS sudoku_bot;
""",
    29: """
DROP TABLE IF EXISTS onay_yanit;
DROP TABLE IF EXISTS onay_talep;
""",
    28: """
DROP TABLE IF EXISTS ogretmen_not;
DROP TABLE IF EXISTS ders_defteri;
""",
    27: """
DROP TABLE IF EXISTS kullanici_tema;
""",
    26: """
DROP TABLE IF EXISTS calisma_soru;
""",
    25: """
DROP TABLE IF EXISTS odev_uyari;
""",
    24: """
DROP TABLE IF EXISTS odev_hatirlatma;
""",
    23: """
DROP TABLE IF EXISTS soru_inceleme;
""",
    22: """
CREATE TABLE soru_bildirim_eski (
    id           INTEGER PRIMARY KEY,
    soru_id      INTEGER NOT NULL,
    kullanici_id INTEGER NOT NULL REFERENCES kullanici(id),
    tur          TEXT NOT NULL CHECK (tur IN ('sekil','cevap','anlasilmiyor')),
    zaman        TEXT NOT NULL,
    UNIQUE (soru_id, kullanici_id)
);
INSERT OR IGNORE INTO soru_bildirim_eski (id, soru_id, kullanici_id, tur, zaman)
    SELECT id, soru_id, kullanici_id, tur, zaman FROM soru_bildirim
    WHERE kullanici_id IS NOT NULL AND tur IN ('sekil','cevap','anlasilmiyor');
DROP TABLE soru_bildirim;
ALTER TABLE soru_bildirim_eski RENAME TO soru_bildirim;
CREATE INDEX soru_bildirim_soru ON soru_bildirim(soru_id);
""",
    21: """
ALTER TABLE sinif_pdf DROP COLUMN soru_zaman;
ALTER TABLE sinif_pdf DROP COLUMN soru_not;
ALTER TABLE sinif_pdf DROP COLUMN soru_red;
ALTER TABLE sinif_pdf DROP COLUMN soru_onayli;
ALTER TABLE sinif_pdf DROP COLUMN soru_bit;
ALTER TABLE sinif_pdf DROP COLUMN soru_bas;
ALTER TABLE sinif_pdf DROP COLUMN soru_durum;
ALTER TABLE sinif_pdf DROP COLUMN soru_uret;
""",
    20: """
DROP TABLE IF EXISTS soru_bildirim;
""",
    19: """
DROP TABLE IF EXISTS odev_foto;
DROP TABLE IF EXISTS odev_pdf;
DROP TABLE IF EXISTS sinif_pdf;
""",
    18: """
DROP TABLE IF EXISTS sudoku_oyun;
DROP TABLE IF EXISTS sudoku_duello;
""",
    17: """
DROP TABLE IF EXISTS acil_dis_olay;
""",
    16: """
DROP TABLE IF EXISTS acil_ogrenci;
""",
    15: """
DROP TABLE IF EXISTS acil_konum;
DROP TABLE IF EXISTS acil_olay;
""",
    14: """
DROP TABLE IF EXISTS kutu_kayit;
""",
    13: """
DROP TABLE IF EXISTS duyuru_okuma;
""",
    12: """
DROP TABLE IF EXISTS sohbet_okuma;
DROP TABLE IF EXISTS sohbet_mesaj;
""",
    11: """
DROP TABLE IF EXISTS push_abonelik;
""",
    10: """
DROP TABLE IF EXISTS avatar;
""",
    9: """
DROP TABLE IF EXISTS odul_hafta;
DROP TABLE IF EXISTS odul;
""",
    8: """
DROP TABLE IF EXISTS hedef;
""",
    7: """
DROP TABLE IF EXISTS anket_cevap;
DROP TABLE IF EXISTS anket_yanit;
DROP TABLE IF EXISTS anket_katilim;
DROP TABLE IF EXISTS anket_hedef;
DROP TABLE IF EXISTS anket_soru;
DROP TABLE IF EXISTS anket;
""",
    6: """
DROP TABLE IF EXISTS deneme_ogrenci;
DROP TABLE IF EXISTS deneme;
""",
    5: """
DROP TABLE IF EXISTS bilgi_rozet;
DROP TABLE IF EXISTS bilgi_xp;
DROP TABLE IF EXISTS bilgi_cevap;
DROP TABLE IF EXISTS bilgi_tur;
""",
}
TABLOLAR = {
    36: ["deneme_sinif_yorum", "deneme_pdf"],
    35: ["tesekkur", "bilmece_cevap", "bilmece_gun", "bilmece"],
    30: ["sudoku_bot"],
    29: ["onay_yanit", "onay_talep"],
    28: ["ogretmen_not", "ders_defteri"],
    27: ["kullanici_tema"],
    26: ["calisma_soru"],
    25: ["odev_uyari"],
    24: ["odev_hatirlatma"],
    23: ["soru_inceleme"],
    20: ["soru_bildirim"],
    19: ["odev_foto", "odev_pdf", "sinif_pdf"],
    18: ["sudoku_oyun", "sudoku_duello"],
    17: ["acil_dis_olay"],
    16: ["acil_ogrenci"],
    15: ["acil_konum", "acil_olay"],
    14: ["kutu_kayit"],
    13: ["duyuru_okuma"],
    12: ["sohbet_okuma", "sohbet_mesaj"],
    11: ["push_abonelik"],
    10: ["avatar"],
    9: ["odul_hafta", "odul"],
    8: ["hedef"],
    7: ["anket_cevap", "anket_yanit", "anket_katilim", "anket_hedef", "anket_soru", "anket"],
    6: ["deneme_ogrenci", "deneme"],
    5: ["bilgi_rozet", "bilgi_xp", "bilgi_cevap", "bilgi_tur"],
}


def geri_al(db_yolu: Path, hedef: int, onayla: bool) -> int:
    conn = sqlite3.connect(db_yolu)
    try:
        surum = conn.execute("PRAGMA user_version").fetchone()[0]
        if hedef >= surum:
            print(f"Zaten user_version={surum}; hedef {hedef} için yapılacak bir şey yok.")
            return 0
        for n in range(surum, hedef, -1):
            if n not in GERI:
                print(f"HATA: {n}. göç için geri alma betiği yok; durduruldu.", file=sys.stderr)
                return 2
        for n in range(surum, hedef, -1):
            for t in TABLOLAR.get(n, []):
                var = conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()
                adet = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if var else 0
                print(f"V{n}: {t} silinecek ({adet} satır)")
        if not onayla:
            print("Kuru çalıştırma: değişiklik yapılmadı. Uygulamak için --onayla ekleyin.")
            return 0
        for n in range(surum, hedef, -1):
            conn.executescript(f"BEGIN;\n{GERI[n]}\nPRAGMA user_version = {n - 1};\nCOMMIT;")
            print(f"V{n} geri alındı → user_version={n - 1}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hedef", type=int, required=True)
    ap.add_argument("--db", type=Path, default=Path(__file__).resolve().parent.parent / "veri" / "okul.db")
    ap.add_argument("--onayla", action="store_true")
    a = ap.parse_args()
    if not a.db.exists():
        sys.exit(f"Veritabanı yok: {a.db}")
    sys.exit(geri_al(a.db, a.hedef, a.onayla))
