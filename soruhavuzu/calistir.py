"""soruhavuzu/calistir.py — soru havuzu komutları.

kur      şemayı kurar
katalog  kaynak birimlerini ekler (GPU kullanmaz)
uret     ders saati dışında çalışır. Başlangıçta ve (pencere hâlâ açıksa) üretim
         döngüsü bitince SINIRLI artımlı AGY denetimi yapar (en az onaylı soru olan
         (sınıf, ders) önce); bütün birimler bitince kalan her şeyi denetler.
         Her pakette ders saati yeniden kontrol edilir.
denetle  AGY ile tüm 'uretildi' soruları tek seferde denetler (elle; sınırsız)
durum    özet sayılar (sınıf başına onaylı dahil)"""

import sys
import time
from pathlib import Path

import psycopg2

from soruhavuzu import denetci, kaynaklar, tekrar, uretici, vt, zaman

VERI = Path("/mnt/farabi-data/farabi")

# Artımlı denetim bütçesi (uret içinde, tur başına); hangisi önce dolarsa durur.
DENETIM_AZAMI_PAKET = 8  # paket = 100 soru
DENETIM_AZAMI_DK = 45


def uret(conn) -> None:
    eleyici = tekrar.Eleyici(tekrar._gomucu())
    eleyici.yukle(conn)
    # Hafta içi pencere sabah 07:30'da kapandığı için döngü sonunda denetime zaman kalmaz;
    # bu yüzden üretimden ÖNCE de (ders saati dışındayken) sınırlı bir dilim denetlenir.
    denetle(conn, DENETIM_AZAMI_PAKET, DENETIM_AZAMI_DK, ders_saati_kontrol=True)
    while zaman.uretim_serbest():
        birim = vt.siradaki_birim(conn)
        if birim is None:
            print(
                "[uret] bütün birimler işlendi — AGY tek seferlik denetim başlıyor",
                flush=True,
            )
            denetle(conn, ders_saati_kontrol=True)
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
    denetle(conn, DENETIM_AZAMI_PAKET, DENETIM_AZAMI_DK, ders_saati_kontrol=True)


def denetle(
    conn,
    azami_paket: int | None = None,
    azami_dk: float | None = None,
    ders_saati_kontrol: bool = False,
    paket_fn=None,
    simdi=time.monotonic,
) -> None:
    """azami_paket/azami_dk verilirse sınırlı çalışır; ders_saati_kontrol=True ise her
    paketten önce zaman.uretim_serbest() bakılır ve ders saati başlayınca hemen durulur."""
    paket_fn = paket_fn or denetci.paket_denetle
    ardisik_bos = 0
    paket_sayisi = 0
    t0 = simdi()
    while True:
        if ders_saati_kontrol and not zaman.uretim_serbest():
            print("[denetle] ders saati — durduruldu", flush=True)
            return
        if azami_paket is not None and paket_sayisi >= azami_paket:
            print(f"[denetle] paket sınırı ({azami_paket}) doldu", flush=True)
            return
        if azami_dk is not None and (simdi() - t0) >= azami_dk * 60:
            print(f"[denetle] süre sınırı ({azami_dk} dk) doldu", flush=True)
            return
        n = paket_fn(conn)
        paket_sayisi += 1
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
        cur.execute(
            "SELECT sinif, count(*) FILTER (WHERE durum='onayli'), "
            "count(*) FILTER (WHERE durum='uretildi') FROM soru GROUP BY 1 ORDER BY 1"
        )
        for sinif, onayli, bekleyen in cur.fetchall():
            print(f"sinif {sinif}: onaylı {onayli}, denetim bekleyen {bekleyen}")


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
