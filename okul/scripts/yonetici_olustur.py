"""İlk yönetici hesabını açar (ya da mevcut hesabın şifresini ilk şifreye sıfırlar).

Kullanım (okul/ dizininden):
    venv/bin/python scripts/yonetici_olustur.py "Atakan Ünver" atakan
İlk şifre: ilk ad + 123 (ör. atakan123); ilk girişte değiştirilmesi zorunludur.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import db
import zaman
from metin import ilk_sifre


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ad, kadi = sys.argv[1].strip(), sys.argv[2].strip().lower()
    sifre = ilk_sifre(ad)
    db.sema_kur()
    conn = db.baglanti()
    try:
        mevcut = conn.execute(
            "SELECT * FROM kullanici WHERE kullanici_adi = ?", (kadi,)
        ).fetchone()
        if mevcut and mevcut["rol"] != "yonetici":
            sys.exit(f"'{kadi}' kullanıcı adı {mevcut['rol']} rolünde kullanılıyor.")
        if mevcut:
            conn.execute(
                "UPDATE kullanici SET ad_soyad = ?, sifre_hash = ?, sifre_degismeli = 1, aktif = 1 WHERE id = ?",
                (ad, auth.sifre_hashle(sifre), mevcut["id"]),
            )
            print(f"Yönetici güncellendi: {kadi}")
        else:
            conn.execute(
                "INSERT INTO kullanici (rol, ad_soyad, kullanici_adi, sifre_hash, sifre_degismeli, olusturma)"
                " VALUES ('yonetici', ?, ?, ?, 1, ?)",
                (ad, kadi, auth.sifre_hashle(sifre), zaman.simdi_str()),
            )
            print(f"Yönetici oluşturuldu: {kadi}")
        conn.commit()
        print(f"İlk şifre: {sifre} (ilk girişte değiştirilecek)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
