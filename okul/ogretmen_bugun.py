"""Öğretmen ana ekranı: "Bugün neler yapayım?" listesi (yalnızca gerçek kayıtlardan; görev uydurulmaz).

Sıra (öncelik): okunmamış duyuru > işlendi işaretlenmemiş geçmiş ders > teslim süresi dolan ödev > yaklaşan sınav
> günün soruları (inceleme) > "yapılacak" işaretli notlar. Her görevin tek bir eylemi (bağlantısı) vardır.
Hiçbiri yoksa liste boş döner ve ekran "bugün için bekleyen bir şey yok" der.
"""

import sqlite3
from datetime import timedelta

import duyurular
import inceleme
import notdefteri
import odevler
import sinavlar
import zaman

MAX_GOREV = 5
ODEV_GERIYE_GUN = 3  # teslim süresi bu kadar gün içinde dolmuş ödevler listelenir
SINAV_GUN = 7


def _duyuru(conn, k) -> list[dict]:
    return [
        {"tur": "duyuru", "baslik": f"Okunmamış duyuru: {d['baslik']}", "alt": d["yazar"], "href": "/duyurular", "acil": True}
        for d in duyurular.okunmamis(conn, k, 2)
    ]


def _defter(bekleyen: list[dict]) -> list[dict]:
    return [
        {
            "tur": "defter", "baslik": f"{d['sinif']} {d['ders']} dersinde kazanım işlendi mi?",
            "alt": f"{d['no']}. ders · {d['saat']}", "href": "/ogretmen#bugun-dersler", "acil": False,
        }
        for d in bekleyen[:2]
    ]


def _odev(conn, k, simdi) -> list[dict]:
    alt = (simdi - timedelta(days=ODEV_GERIYE_GUN)).strftime(zaman.BICIM)
    liste = []
    for o in odevler.ogretmen_odevleri(conn, k):
        if alt <= o["teslim"] <= simdi.strftime(zaman.BICIM) and o["teslim_sayisi"] < (o["sinif_mevcudu"] or 0):
            liste.append({
                "tur": "odev", "baslik": f"{o['sinif']} · {o['baslik']}: teslim süresi doldu",
                "alt": f"{o['teslim_sayisi']}/{o['sinif_mevcudu']} teslim · sonuçlara bak", "href": f"/ogretmen/odev/{o['id']}", "acil": False,
            })
    return liste[:2]


def _sinav(conn, k, simdi) -> list[dict]:
    liste = []
    for s in sinavlar.ogretmen_sinavlari(conn, k, simdi.date().isoformat()):
        kalan = sinavlar.kalan_gun(s["tarih"])
        if 0 <= kalan <= SINAV_GUN:
            ne = f"{s['sinif'] or 'Tüm düzeyler'} {s['baslik']}"
            liste.append({
                "tur": "sinav", "baslik": f"{ne} " + ("bugün" if kalan == 0 else f"{kalan} gün sonra"),
                "alt": "Sınav takvimi", "href": "/ogretmen/sinavlar", "acil": kalan <= 1,
            })
    return liste[:1]


def _inceleme(conn, k) -> list[dict]:
    kart = inceleme.kart(conn, k)
    if kart and kart["yapilan"] < kart["toplam"]:
        return [{
            "tur": "inceleme", "baslik": "Günün sorularını incele", "alt": f"{kart['yapilan']}/{kart['toplam']} tamamlandı",
            "href": "/ogretmen/inceleme", "acil": False,
        }]
    return []


def _notlar(conn, k) -> list[dict]:
    return [
        {"tur": "not", "baslik": n["metin"][:70] + ("…" if len(n["metin"]) > 70 else ""), "alt": "Notlarımdan · yapılacak",
         "href": f"/ogretmen/not/{n['id']}", "acil": False}
        for n in notdefteri.yapilacaklar(conn, k["id"])[:2]
    ]


def gorevler(conn: sqlite3.Connection, k: sqlite3.Row, defter_bekleyen: list[dict]) -> dict:
    """{'gorevler': [...en çok MAX_GOREV], 'fazla': n}. Kaynak hatası ana sayfayı bozmaz (o kaynak atlanır)."""
    simdi = zaman.simdi()
    tum: list[dict] = []
    for kaynak in (
        lambda: _duyuru(conn, k), lambda: _defter(defter_bekleyen), lambda: _odev(conn, k, simdi),
        lambda: _sinav(conn, k, simdi), lambda: _inceleme(conn, k), lambda: _notlar(conn, k),
    ):
        try:
            tum += kaynak()
        except Exception:  # noqa: BLE001 — tek kaynağın hatası (örn. soru havuzu erişilemez) listeyi düşürmesin
            continue
    return {"gorevler": tum[:MAX_GOREV], "fazla": max(len(tum) - MAX_GOREV, 0)}
