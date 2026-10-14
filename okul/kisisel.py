"""Kişisel Gelişim: öğrencinin kendi haftalık çalışma hedefi ve gerçek etkinliğe dayalı ilerleme.

İlkeler: ilerleme saklanmaz, `bilgi_tur` / `maraton` / `odev_teslim` kayıtlarından hesaplanır (uydurma ilerleme
yok); yalnızca öğrencinin kendisi görür, sıralama/karşılaştırma yoktur; "yapıldı" işaretli klasik ödev etkinlik
sayılmaz (öğrenci beyanı). Hedef bir kez konur; ilk etkinlikten sonra düşürülemez (rozet için kolay yol açılmasın).
Hedef rozetleri arena.ROZETLER ile aynı `bilgi_rozet` tablosunda tutulur.
"""

import sqlite3
from datetime import datetime, timedelta

import zaman

MIN_HEDEF, MAX_HEDEF = 1, 14
OLUSAN_HAFTA = 6  # geçmiş görünümünde gösterilen hafta sayısı


class HedefHatasi(Exception):
    pass


def hafta_basi(tarih: datetime | None = None) -> str:
    d = tarih or zaman.simdi()
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def _hafta_sonu(hb: str) -> str:
    return (datetime.strptime(hb, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")  # noqa: DTZ007


def etkinlik_sayisi(conn: sqlite3.Connection, ogrenci_id: int, kullanici_id: int, hb: str) -> dict:
    """Haftadaki gerçek etkinlikler: {'arena', 'maraton', 'test', 'toplam'}."""
    son = _hafta_sonu(hb)
    arena = conn.execute(
        "SELECT count(*) FROM bilgi_tur WHERE kullanici_id = ? AND durum = 'tamam' AND gun BETWEEN ? AND ?",
        (kullanici_id, hb, son),
    ).fetchone()[0]
    mar = conn.execute(
        "SELECT count(*) FROM maraton m WHERE m.kullanici_id = ? AND m.bitis IS NOT NULL"
        " AND substr(m.bitis, 1, 10) BETWEEN ? AND ?"
        " AND NOT EXISTS (SELECT 1 FROM maraton_soru s WHERE s.maraton_id = m.id AND s.cevap = -2)",
        (kullanici_id, hb, son),
    ).fetchone()[0]
    test = conn.execute(
        "SELECT count(*) FROM odev_teslim t JOIN odev o ON o.id = t.odev_id WHERE t.ogrenci_id = ? AND t.durum = 'tamam'"
        " AND o.tur = 'test' AND substr(t.zaman, 1, 10) BETWEEN ? AND ?",
        (ogrenci_id, hb, son),
    ).fetchone()[0]
    return {"arena": arena, "maraton": mar, "test": test, "toplam": arena + mar + test}


def hedef_getir(conn: sqlite3.Connection, kullanici_id: int, hb: str) -> int | None:
    r = conn.execute(
        "SELECT hedef_sayi FROM hedef WHERE kullanici_id = ? AND hafta_basi = ?", (kullanici_id, hb)
    ).fetchone()
    return r[0] if r else None


def hedef_koy(conn: sqlite3.Connection, ogrenci: sqlite3.Row, sayi: int) -> None:
    if not MIN_HEDEF <= sayi <= MAX_HEDEF:
        raise HedefHatasi(f"Hedef {MIN_HEDEF} ile {MAX_HEDEF} arasında olmalı.")
    kid, hb = ogrenci["kullanici_id"], hafta_basi()
    mevcut = hedef_getir(conn, kid, hb)
    if mevcut is not None and sayi < mevcut and etkinlik_sayisi(conn, ogrenci["id"], kid, hb)["toplam"] > 0:
        raise HedefHatasi("Bu hafta etkinlik yaptıktan sonra hedef düşürülemez; yükseltebilirsin.")
    conn.execute(
        "INSERT INTO hedef (kullanici_id, hafta_basi, hedef_sayi, olusturma) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (kullanici_id, hafta_basi) DO UPDATE SET hedef_sayi = excluded.hedef_sayi",
        (kid, hb, sayi, zaman.simdi_str()),
    )
    conn.commit()


def bu_hafta(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> dict:
    """{hafta_basi, hedef (None = konmamış), yapilan{...}, tamamlandi, kalan}. Hedef yoksa ilerleme yüzdesi yok."""
    hb = hafta_basi()
    hedef = hedef_getir(conn, ogrenci["kullanici_id"], hb)
    yapilan = etkinlik_sayisi(conn, ogrenci["id"], ogrenci["kullanici_id"], hb)
    return {
        "hafta_basi": hb, "hedef": hedef, "yapilan": yapilan,
        "tamamlandi": hedef is not None and yapilan["toplam"] >= hedef,
        "kalan": max(hedef - yapilan["toplam"], 0) if hedef is not None else None,
        "yuzde": min(100, round(100 * yapilan["toplam"] / hedef)) if hedef else None,
    }


def gecmis(conn: sqlite3.Connection, ogrenci: sqlite3.Row, n: int = OLUSAN_HAFTA) -> list[dict]:
    """Son n hafta (eskiden yeniye, bu hafta dahil): yapılan etkinlik ve varsa hedef. Hedefsiz hafta 'hedef: None'."""
    simdi = zaman.simdi()
    cikti = []
    for i in range(n - 1, -1, -1):
        hb = hafta_basi(simdi - timedelta(weeks=i))
        hedef = hedef_getir(conn, ogrenci["kullanici_id"], hb)
        yapilan = etkinlik_sayisi(conn, ogrenci["id"], ogrenci["kullanici_id"], hb)["toplam"]
        cikti.append({"hafta_basi": hb, "hedef": hedef, "yapilan": yapilan,
                      "tamam": hedef is not None and yapilan >= hedef, "su_an": i == 0})
    return cikti


def ulasilan_hafta_sayisi(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> int:
    """Hedefine ulaştığı farklı hafta sayısı (tüm geçmiş)."""
    sayi = 0
    for r in conn.execute("SELECT hafta_basi, hedef_sayi FROM hedef WHERE kullanici_id = ?", (ogrenci["kullanici_id"],)):
        if etkinlik_sayisi(conn, ogrenci["id"], ogrenci["kullanici_id"], r["hafta_basi"])["toplam"] >= r["hedef_sayi"]:
            sayi += 1
    return sayi


def rozet_kontrol(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> list[str]:
    """Hedef rozetleri (idempotent, commit eder). Dönen: bu çağrıda yeni kazanılan kodlar."""
    n = ulasilan_hafta_sayisi(conn, ogrenci)
    istenen = [k for k, esik in (("hedef_ilk", 1), ("hedef_uc", 3)) if n >= esik]
    yeni = []
    for kod in istenen:
        if conn.execute(
            "INSERT OR IGNORE INTO bilgi_rozet (kullanici_id, rozet_kodu, zaman) VALUES (?, ?, ?)",
            (ogrenci["kullanici_id"], kod, zaman.simdi_str()),
        ).rowcount == 1:
            yeni.append(kod)
    conn.commit()
    return yeni
