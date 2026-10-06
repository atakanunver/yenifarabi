"""soruhavuzu/calistir.py — soru havuzu komutları.

kur      şemayı kurar
katalog  kaynak birimlerini ekler (GPU kullanmaz)
uret     ders saati dışında birimleri yerel Ollama ile işler (pencere kapanınca çıkar);
         bütün birimler bitince AGY denetimini BİR KEZ başlatır
denetle  AGY ile tüm 'uretildi' soruları tek seferde denetler (elle de çalıştırılabilir)
durum    özet sayılar"""

import sys
import time
from pathlib import Path

import psycopg2

from soruhavuzu import denetci, kaynaklar, tekrar, uretici, vt, zaman

VERI = Path("/mnt/farabi-data/farabi")


def uret(conn) -> None:
    eleyici = tekrar.Eleyici(tekrar._gomucu())
    eleyici.yukle(conn)
    while zaman.uretim_serbest():
        birim = vt.siradaki_birim(conn)
        if birim is None:
            print(
                "[uret] bütün birimler işlendi — AGY tek seferlik denetim başlıyor",
                flush=True,
            )
            denetle(conn)
            return
        t0 = time.perf_counter()
        try:
            sorular = uretici.uret(birim)
            eklenen = 0
            for s in sorular:
                if not eleyici.kopya_mi(s["ders"], s["sinif"], s["soru"]):
                    vt.soru_ekle(conn, birim["id"], s)
                    eklenen += 1
            vt.birim_isaretle(conn, birim["id"], "islendi")
            print(
                f"[uret] {birim['anahtar']}: {eklenen}/{len(sorular)} soru, "
                f"{time.perf_counter() - t0:.0f} sn",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001 — tek birimin hatası geceyi durdurmasın
            conn.rollback()
            vt.birim_isaretle(
                conn, birim["id"], "hata", f"{type(e).__name__}: {e}"[:500]
            )
            print(
                f"[uret] HATA {birim['anahtar']}: {type(e).__name__}: {e}", flush=True
            )
    print("[uret] ders saati penceresi — durduruldu", flush=True)


def denetle(conn) -> None:
    ardisik_bos = 0
    while True:
        n = denetci.paket_denetle(conn)
        if n == 0 and not vt.denetlenecekler(conn, 1):
            print("[denetle] denetlenecek soru kalmadı", flush=True)
            return
        ardisik_bos = ardisik_bos + 1 if n == 0 else 0
        if ardisik_bos >= 3:
            print(
                "[denetle] AGY art arda 3 pakette karar dönmedi — çıkılıyor", flush=True
            )
            return
        print(f"[denetle] {n} karar", flush=True)


def durum(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tur, durum, count(*) FROM kaynak_birim GROUP BY 1,2 ORDER BY 1,2"
        )
        for satir in cur.fetchall():
            print("birim", *satir)
        cur.execute(
            "SELECT ders, sinif, durum, count(*) FROM soru GROUP BY 1,2,3 ORDER BY 1,2,3"
        )
        for satir in cur.fetchall():
            print("soru", *satir)


def main() -> int:
    komut = sys.argv[1] if len(sys.argv) > 1 else "durum"
    conn = vt.baglan()
    if komut == "kur":
        vt.sema_kur(conn)
    elif komut == "katalog":
        farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
        print(kaynaklar.katalogla(conn, farabi, VERI / "kazanim_test", VERI / "yks"))
    elif komut == "uret":
        uret(conn)
    elif komut == "denetle":
        denetle(conn)
    else:
        durum(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
