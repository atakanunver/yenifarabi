"""Öğrenci ana ekranı: "Bugün ne yapacağım?" görev listesi (yalnızca gerçek kayıtlardan; görev uydurulmaz).

Sıra (öncelik): vadesi yaklaşan/geçmiş ödev > Günlük Görev > yaklaşan sınav için tekrar > haftalık hedef koy
> Arena'nın önerdiği tekrar. Her görevin tek, net bir eylemi (bağlantısı) vardır. Yapılabilecek bir şey yoksa
liste boş döner ve ekran "bugün için bekleyen bir şey yok" der.
"""

import sqlite3
from datetime import datetime, timedelta

import anket
import arena
import kisisel
import odevler
import zaman
from rotalar import ortak

MAX_GOREV = 3
SINAV_GUN = 7  # sınav bu kadar gün içindeyse tekrar görevi çıkar
ODEV_SAAT_ACIL = 24


def _odev_gorevleri(conn: sqlite3.Connection, ogrenci: sqlite3.Row, simdi: datetime) -> tuple[list[dict], int]:
    bekleyen = [o for o in odevler.ogrenci_odevleri(conn, ogrenci) if o["durum"] is None]
    bekleyen.sort(key=lambda o: o["teslim"])  # en yakın vade önce, geçmiş vadeler en başta
    sinir = (simdi + timedelta(hours=ODEV_SAAT_ACIL)).strftime(zaman.BICIM)
    liste = []
    for o in bekleyen[:2]:
        gecti = o["teslim"] < simdi.strftime(zaman.BICIM)
        liste.append({
            "tur": "odev", "baslik": o["baslik"], "alt": f"{o['ders']} · {'Test' if o['tur'] == 'test' else 'Ödev'}",
            "href": f"/ogrenci/odev/{o['id']}", "odev": o, "acil": gecti or o["teslim"] <= sinir,
        })
    return liste, max(len(bekleyen) - 2, 0)


def gorevler(conn: sqlite3.Connection, ogrenci: sqlite3.Row, kilit: dict | None = None, arena_gorevi: bool = True) -> dict:
    """{'gorevler': [...], 'fazla_odev': n, 'tamamlanan': [...], 'arena': durum}.
    kilit: maraton.kilit() sonucu (ders saatinde None değil); Arena görevinde bilgi olarak kullanılır."""
    simdi = zaman.simdi()
    kid = ogrenci["kullanici_id"]
    liste, fazla = _odev_gorevleri(conn, ogrenci, simdi)
    tamam: list[str] = []
    gd = arena.gorev_durumu(conn, kid, ogrenci["sinif"]) if arena.duzey_uygun(ogrenci["sinif"]) else None
    if gd and arena_gorevi:
        if gd["durum"] in ("hazir", "devam"):
            liste.append({
                "tur": "arena", "baslik": "Günlük Görev" + (" (devam et)" if gd["durum"] == "devam" else ""),
                "alt": f"{gd['soru_sayisi']} soru · yaklaşık {gd['dk']} dakika · süre sınırı yok",
                "href": f"/ogrenci/arena/{gd['tur_id']}" if gd["durum"] == "devam" else "/ogrenci/arena", "acil": False,
            })
        elif gd["durum"] == "kilit":
            liste.append({"tur": "arena", "baslik": "Günlük Görev", "alt": f"Ders sırasında kapalı · {gd['kilit_bit']}'de açılır",
                          "href": "", "acil": False, "kilitli": True})
        elif gd["durum"] == "tamam":
            tamam.append(f"Günlük Görev tamamlandı ({gd['dogru']}/{gd['soru_sayisi']} doğru)")
        # 'yetersiz' / 'kaynak_yok': yapılabilir bir şey yok → görev gösterilmez
    if kid:
        for a in anket.kullanicinin_anketleri(conn, conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone())["bekleyen"][:1]:
            liste.append({"tur": "anket", "baslik": f"Anket: {a['baslik']}", "alt": "Yanıtların anonim kaydedilir",
                          "href": f"/anket/{a['id']}", "acil": False})
    for s in ortak.yaklasan_sinavlar(conn, ogrenci["sinif"], SINAV_GUN):
        g = (datetime.strptime(s["tarih"], "%Y-%m-%d").date() - simdi.date()).days  # noqa: DTZ007
        liste.append({
            "tur": "sinav", "baslik": f"{s['baslik']} yaklaşıyor",
            "alt": ("Bugün" if g == 0 else ("Yarın" if g == 1 else f"{g} gün sonra")) + " · kısa bir tekrar iyi gelir",
            "href": "/ogrenci/sinavlar", "acil": g <= 1,
        })
        break  # tek sınav hatırlatması yeter
    if kid and kisisel.bu_hafta(conn, ogrenci)["hedef"] is None:
        liste.append({"tur": "hedef", "baslik": "Bu hafta için hedef koy", "alt": "Kendi hedefini sen belirlersin",
                      "href": "/ogrenci/hedefim", "acil": False})
    if kid:
        for t in arena.tekrar_onerileri(conn, kid, 1):
            liste.append({"tur": "tekrar", "baslik": "Tekrar edebileceğin kazanım", "alt": f"{t['kod']} · {t['metin']}",
                          "href": "/ogrenci/arena", "acil": False})
    liste.sort(key=lambda g: (not g.get("acil"), 0))  # sıralama kararlı: acil olanlar öne, kalanlar yukarıdaki sırada
    bugun = simdi.strftime("%Y-%m-%d")
    teslim = conn.execute(
        "SELECT count(*) FROM odev_teslim WHERE ogrenci_id = ? AND substr(zaman, 1, 10) = ?", (ogrenci["id"], bugun)
    ).fetchone()[0]
    if teslim:
        tamam.append(f"Bugün {teslim} ödev teslim ettin")
    return {"gorevler": liste[:MAX_GOREV], "fazla_odev": fazla, "tamamlanan": tamam, "arena": gd}
