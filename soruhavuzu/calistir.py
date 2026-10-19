"""soruhavuzu/calistir.py — soru havuzu komutları.

kur      şemayı kurar
katalog  kaynak birimlerini ekler (GPU kullanmaz)
uret     ders saati dışında çalışır. Başlangıçta ve (pencere hâlâ açıksa) üretim
         döngüsü bitince SINIRLI artımlı AGY denetimi yapar (en az onaylı soru olan
         (sınıf, ders) önce); bütün birimler bitince kalan her şeyi denetler.
         Her pakette ders saati yeniden kontrol edilir.
siniflandir  kazanımsız onaylı soruları LLM ile kazanıma bağlar [--kuru] [--limit N] [--zorla]
sik-karistir  durum IN (uretildi, onayli, askida) soruların şıklarını kanonik sıraya geçirir [--kuru]
ogretmen-pdf  okulun /api/soru-istek kuyruğundaki öğretmen PDF'lerinden soru üretir (9-11; uret başında da çalışır)
geri-bildirim  okul /api/soru-bildirim kayıtlarını havuza işler; eşik aşan soru 'askida' (uret başında da çalışır)
sekil-tara  şekil/grafik/tablo atfı yapan onaylı/bekleyen soruları 'askida'ya alır [--uygula; yoksa kuru]
         (uret her turun başında uygular; geri al: sekil-geri-al <dosya>)
denetle  AGY ile tüm 'uretildi' soruları tek seferde denetler (elle; sınırsız)
durum    özet sayılar (sınıf başına onaylı dahil)"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from soruhavuzu import denetci, etiketle, kazanimlar, kaynak, kaynaklar, ogretmen_pdf, okul_bildirim, sekil, sik, siniflandir, tekrar, uretici, vt, zaman

VERI = Path("/mnt/farabi-data/farabi")
# Kaldığı yer işareti (2026-10-09): her kazanım sonunda yazılır, yeniden başlayınca okunur.
# Asıl gerçek kaynak veritabanıdır (soru.kazanim_id, kazanim.durum); bu dosya insan için okunur bir özet.
DURUM_DOSYASI = VERI / "soru_havuzu" / "uret_durum.json"


def _isaretle(k: dict, durum: str, eklenen: int = 0) -> None:
    """Son işlenen kazanımı durum dosyasına yazar. Yazılamazsa üretimi durdurmaz."""
    veri = {
        "guncelleme": datetime.now(zaman.TR).isoformat(timespec="seconds"),
        "son_kazanim_id": k["id"],
        "son_sinif": k["sinif"],
        "son_ders": k["ders"],
        "son_hafta": k["hafta"],
        "son_durum": durum,
        "son_eklenen": eklenen,
    }
    try:
        DURUM_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        DURUM_DOSYASI.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[uret] durum dosyası yazılamadı: {e}", flush=True)

# Artımlı denetim bütçesi (uret içinde, tur başına); hangisi önce dolarsa durur.
DENETIM_AZAMI_PAKET = 8  # paket = 100 soru
DENETIM_AZAMI_DK = 45


def uret(
    conn,
    ders_saati_kontrol: bool = True,
    sinif: int | None = None,
    farabi_conn=None,
    bulucu=None,
    ureten=None,
    bugun=None,
    denetim: bool = True,
) -> None:
    """2026-10-08: kazanım öncelikli — her soru bir kazanımla (spec soru-havuzu-kazanim-eslesmesi)."""
    bulucu = bulucu or kaynak.bul
    ureten = ureten or uretici.uret_kazanim
    gb = okul_bildirim.calistir(conn)  # öğrencilerin "soru bildir" kayıtları (okul kapalıysa atlanır)
    if gb and gb["askiya"]:
        print(f"[uret] öğrenci bildirimiyle {gb['askiya']} soru askıya alındı", flush=True)
    ogretmen_pdf.calistir(conn, ders_saati_kontrol=ders_saati_kontrol)  # öğretmen PDF'lerinden katkı (okul kapalıysa atlanır)
    r = sekil_tara(conn, uygula=True)  # aktarma betiklerinden sızan şekil atıflı soruları karantinaya al
    if r["bulunan"]:
        print(f"[uret] {len(r['bulunan'])} şekil atıflı soru askıya alındı ({r['dosya']})", flush=True)
    gomucu = tekrar._gomucu()
    eleyici = tekrar.Eleyici(gomucu)
    eleyici.yukle(conn)
    farabi_conn = farabi_conn or psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    haftalar = kazanimlar.haftalar()
    try:
        onceki = DURUM_DOSYASI.read_text(encoding="utf-8")
        print(f"[uret] önceki işaret: {' '.join(onceki.split())[:300]}", flush=True)
    except OSError:
        pass  # ilk çalıştırma ya da dosya yok: veritabanından devam edilir
    denenen: dict[int, int] = {}
    if ders_saati_kontrol and denetim:
        denetle(conn, DENETIM_AZAMI_PAKET, DENETIM_AZAMI_DK, ders_saati_kontrol=True)
    while not ders_saati_kontrol or zaman.uretim_serbest():
        gun = bugun or zaman.bugun_istanbul()
        k = vt.siradaki_kazanim(conn, gun, haftalar, {i for i, n in denenen.items() if n >= 2})
        if k is not None and sinif is not None and k["sinif"] != sinif:
            denenen[k["id"]] = 2
            continue
        if k is None:
            print("[uret] bütün kazanımlar hedefte ya da denendi — denetim", flush=True)
            try:  # sınıflandırma hatası gece üretimini düşürmesin
                siniflandir.calistir(conn, gomucu, ders_saati_kontrol=ders_saati_kontrol)
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"[uret] siniflandir HATA: {type(e).__name__}: {e}", flush=True)
            if denetim:
                denetle(conn, ders_saati_kontrol=ders_saati_kontrol)
            return
        denenen[k["id"]] = denenen.get(k["id"], 0) + 1
        t0 = time.perf_counter()
        try:
            kay = bulucu(farabi_conn, gomucu, k["sinif"], k["ders"], k["metin"])
            if kay is None:
                vt.kazanim_isaretle(conn, k["id"], "kaynak_yok")
                print(f"[uret] kaynak yok: {k['sinif']} {k['ders']} — {k['metin'][:60]}", flush=True)
                _isaretle(k, "kaynak_yok")
                continue
            bid = vt.birim_ekle(
                conn,
                "kitap",
                f"kazanim:{k['id']}:{','.join(map(str, kay['chunk_idler']))}",
                k["ders"],
                k["sinif"],
                kay["etiket"],
                kay["metin"],
            )
            if bid is None:  # aynı anahtar daha önce eklenmiş
                bid = vt.birim_bul(conn, f"kazanim:{k['id']}:{','.join(map(str, kay['chunk_idler']))}")
            eklenen = 0
            for s in ureten(k, kay):
                if not eleyici.kopya_mi(s["ders"], s["sinif"], s["soru"]):
                    vt.soru_ekle(conn, bid, s, kazanim_id=k["id"], kazanim_kaynak="uretim")
                    eklenen += 1
            print(
                f"[uret] {k['sinif']} {k['ders']} h{k['hafta']}: {eklenen} soru, "
                f"{time.perf_counter() - t0:.0f} sn — {k['metin'][:50]}",
                flush=True,
            )
            _isaretle(k, "uretim", eklenen)
        except Exception as e:  # noqa: BLE001 — tek kazanımın hatası geceyi durdurmasın
            conn.rollback()
            if hasattr(farabi_conn, "rollback"):
                farabi_conn.rollback()  # aborted işlem sonraki kazanımları bozmasın
            print(f"[uret] HATA kazanım {k['id']}: {type(e).__name__}: {e}", flush=True)
            _isaretle(k, "hata")
    print("[uret] ders saati penceresi — durduruldu", flush=True)
    if ders_saati_kontrol and denetim:
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


def sekil_tara(conn, uygula: bool = False, sinif: int | None = None) -> dict:
    """Şekil/grafik/tablo atfı yapıp şekli taşımayan soruları karantinaya (durum='askida') alır; silmez.
    Önceki durum JSON dosyasına yazılır (sekil-geri-al ile geri döner). Aktarma betikleri vt.soru_ekle'yi
    atlayıp doğrudan INSERT ettiği için tek geçit yerine her turda taranır (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sinif, ders, soru, secenekler, durum FROM soru WHERE durum IN ('onayli','uretildi') ORDER BY id"
        )
        satirlar = cur.fetchall()
    bulunan = []
    for sid, sn, ders, soru, sec, durum_ in satirlar:
        if sinif is not None and sn != sinif:
            continue
        m = sekil.eslesme(soru, sec)
        if m:
            bulunan.append({"id": sid, "sinif": sn, "ders": ders, "onceki": durum_, "eslesme": m, "soru": soru[:100]})
    dosya = None
    if uygula and bulunan:
        dosya = VERI / "soru_havuzu" / f"sekil_askida_{datetime.now():%Y%m%d_%H%M%S}.json"
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text(json.dumps(bulunan, ensure_ascii=False, indent=1), encoding="utf-8")
        with conn.cursor() as cur:
            for b in bulunan:
                cur.execute(
                    "UPDATE soru SET durum='askida', denetim_notu=%s, denetim_at=now() WHERE id=%s",
                    (f"sekil_atfi: {b['eslesme']}"[:200], b["id"]),
                )
        conn.commit()
    return {"bulunan": bulunan, "dosya": str(dosya) if dosya else None}


def sekil_geri_al(conn, dosya: str) -> int:
    kayit = json.loads(Path(dosya).read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for b in kayit:
            cur.execute(
                "UPDATE soru SET durum=%s, denetim_notu=NULL WHERE id=%s AND durum='askida' "
                "AND denetim_notu LIKE 'sekil_atfi%%'",
                (b["onceki"], b["id"]),
            )
    conn.commit()
    return len(kayit)


def sik_karistir(conn, kuru: bool = False) -> dict:
    """Mevcut soruların şıklarını kanonik sıraya geçirir (tek işlemde); doğru şık metni korunur."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, soru, secenekler, dogru_index FROM soru "
            "WHERE durum IN ('uretildi','onayli','askida') ORDER BY id"
        )
        satirlar = cur.fetchall()
    once, sonra, degisen = [0] * 4, [0] * 4, []
    for sid, soru, sec, di in satirlar:
        yeni, yeni_di = sik.kanonik_sira(soru, sec, di)
        once[di] += 1
        sonra[yeni_di] += 1
        if yeni != sec:
            degisen.append((json.dumps(yeni, ensure_ascii=False), yeni_di, sid))
    if not kuru and degisen:
        with conn.cursor() as cur:
            for g in degisen:
                cur.execute("UPDATE soru SET secenekler=%s::jsonb, dogru_index=%s WHERE id=%s", g)
        conn.commit()
    return {"toplam": len(satirlar), "degisen": len(degisen), "once": once, "sonra": sonra}


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
    import argparse
    parser = argparse.ArgumentParser(prog="soruhavuzu")
    sub = parser.add_subparsers(dest="komut")
    sub.add_parser("kur")
    sub.add_parser("katalog")
    sub.add_parser("kazanim-yukle").add_argument("--kuru", action="store_true")
    sub.add_parser("etiketle").add_argument("--kuru", action="store_true")
    p_uret = sub.add_parser("uret")
    p_uret.add_argument("--sinif", type=int, default=None, help="Yalnızca belirtilen sınıf")
    p_uret.add_argument("--zorla", action="store_true", help="Ders saati kontrolünü atla")
    p_uret.add_argument("--denetimsiz", action="store_true", help="AGY denetimini atla (yalnızca üretim)")
    sub.add_parser("denetle")
    p_sin = sub.add_parser("siniflandir")
    p_sin.add_argument("--kuru", action="store_true")
    p_sin.add_argument("--limit", type=int, default=None)
    p_sin.add_argument("--zorla", action="store_true", help="Ders saati kontrolünü atla")
    p_sk = sub.add_parser("sekil-tara")
    p_sk.add_argument("--uygula", action="store_true")
    p_sk.add_argument("--sinif", type=int, default=None)
    sub.add_parser("geri-bildirim")
    p_op = sub.add_parser("ogretmen-pdf")
    p_op.add_argument("--zorla", action="store_true", help="Ders saati kontrolünü atla")
    sub.add_parser("sekil-geri-al").add_argument("dosya")
    sub.add_parser("sik-karistir").add_argument("--kuru", action="store_true")
    sub.add_parser("tekrar-temizle").add_argument("--kuru", action="store_true")
    sub.add_parser("durum")

    args = parser.parse_args()
    komut = args.komut or "durum"
    conn = vt.baglan()
    if komut == "kur":
        vt.sema_kur(conn)
    elif komut == "katalog":
        farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
        print(kaynaklar.katalogla(conn, farabi, VERI / "kazanim_test", VERI / "yks"))
    elif komut == "kazanim-yukle":
        satirlar, atlanan = kazanimlar.oku()
        if not args.kuru:
            for k in satirlar:
                vt.kazanim_upsert(conn, k)
        print(
            f"[kazanim-yukle] {len(satirlar)} satır{' (kuru)' if args.kuru else ''}; "
            f"eşlenemeyen ders: {sorted(atlanan)}",
            flush=True,
        )
    elif komut == "etiketle":
        s = etiketle.etiketle(conn, tekrar._gomucu(), kuru=args.kuru)
        for (sinif, ders), (et, top) in sorted(s["dagilim"].items()):
            print(f"  {sinif:>2} {ders:<10} {et:>4}/{top:<4}", flush=True)
        print(
            f"[etiketle] {s['etiketlenen']} etiketlendi, {s['etiketsiz']} etiketsiz"
            f"{' (kuru — yazılmadı)' if args.kuru else ''}",
            flush=True,
        )
    elif komut == "uret":
        uret(conn, ders_saati_kontrol=not args.zorla, sinif=args.sinif, denetim=not args.denetimsiz)
    elif komut == "denetle":
        denetle(conn)
    elif komut == "siniflandir":
        s = siniflandir.calistir(
            conn, tekrar._gomucu(), kuru=args.kuru, limit=args.limit, ders_saati_kontrol=not args.zorla
        )
        print(f"[siniflandir] bitti: {s}{' (kuru — yazılmadı)' if args.kuru else ''}", flush=True)
    elif komut == "sekil-tara":
        r = sekil_tara(conn, uygula=args.uygula, sinif=args.sinif)
        from collections import Counter
        for (sn, d, o), n in sorted(Counter((b["sinif"], b["ders"], b["onceki"]) for b in r["bulunan"]).items()):
            print(f"  {sn:>2} {d:<10} {o:<8} {n}")
        for b in r["bulunan"][:20]:
            print(f"  #{b['id']} [{b['eslesme']}] {b['soru']}")
        print(f"[sekil-tara] {len(r['bulunan'])} soru{' askıya alındı: ' + r['dosya'] if r['dosya'] else ' (kuru — yazılmadı)'}")
    elif komut == "ogretmen-pdf":
        print(f"[ogretmen-pdf] {ogretmen_pdf.calistir(conn, ders_saati_kontrol=not args.zorla)}")
    elif komut == "geri-bildirim":
        print(f"[geri-bildirim] {okul_bildirim.calistir(conn)}")
    elif komut == "sekil-geri-al":
        print(f"[sekil-geri-al] {sekil_geri_al(conn, args.dosya)} kayıt işlendi")
    elif komut == "sik-karistir":
        s = sik_karistir(conn, kuru=args.kuru)
        harf = "ABCD"
        print("önce :", " ".join(f"{h}={n}" for h, n in zip(harf, s["once"])))
        print("sonra:", " ".join(f"{h}={n}" for h, n in zip(harf, s["sonra"])))
        print(f"[sik-karistir] {s['degisen']}/{s['toplam']} satır değişti{' (kuru — yazılmadı)' if args.kuru else ''}")
    elif komut == "tekrar-temizle":
        n = tekrar.kopyalari_isaretle(conn, kuru=args.kuru)
        print(f"[tekrar-temizle] {n} birebir kopya{' (kuru — yazılmadı)' if args.kuru else ' kopya olarak işaretlendi'}")
    else:
        durum(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
