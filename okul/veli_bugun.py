"""Veli ana ekranı (sade, büyük yazı): "Şimdi", "Yapılması gerekenler", "Bugün ve yarın".

Yalnızca gerçek kayıtlardan. "Okulda" iddiası YOK: yoklama isimle tutulduğundan eşleşmeyen kayıt yanlış bilgi verir;
gösterilen şey ders programı (şu an hangi ders) ve gerçek devamsızlık kaydıdır.
"""

import sqlite3
from datetime import date, timedelta

import duyurular
import onay
import zaman
from kaynaklar import KaynakHatasi, program, zil
from rotalar import ortak

MAX_GOREV = 4
SINAV_GUN = 3
ODEV_GUN = 2
GUN_ADI = program.GUN_ADLARI


def _dersler(sinif: str, tarih: date) -> list[dict]:
    """O günün dersleri: [{no, ders, bas, bit}]. Program ya da zil okunamazsa/okul günü değilse boş."""
    try:
        if zil.tatil_adi(tarih):
            return []
        saatler = {no: (b, t) for no, b, t in zil.gunun_dersleri(tarih)}
        return [
            {"no": no, "ders": ders, "bas": saatler.get(no, ("", ""))[0], "bit": saatler.get(no, ("", ""))[1]}
            for no, ders in program.bugun(sinif, tarih)
        ]
    except KaynakHatasi:
        return []


def simdi(cocuk: sqlite3.Row, an=None) -> dict:
    """{'tur', 'baslik', 'alt'}: o an hangi ders (ya da neden ders yok)."""
    an = an or zaman.simdi()
    try:
        durum = zil.durum(an)
    except KaynakHatasi:
        return {"tur": "yok", "baslik": "", "alt": ""}
    tur = durum["tur"]
    if tur == "tatil":
        return {"tur": "tatil", "baslik": "Bugün okul tatil", "alt": durum["metin"]}
    if tur == "ders":
        ders = next((d for d in _dersler(cocuk["sinif"], an.date()) if d["no"] == durum["no"]), None)
        if ders:
            return {"tur": "ders", "baslik": f"Şu an {ders['no']}. ders: {ders['ders'].title()}", "alt": f"{ders['bas']} - {ders['bit']}"}
        return {"tur": "ders", "baslik": f"Şu an {durum['no']}. ders saati", "alt": f"{durum['bas']} - {durum['bit']}"}
    if tur in ("teneffus", "ogle"):
        return {"tur": tur, "baslik": "Şu an teneffüs" if tur == "teneffus" else "Şu an öğle arası", "alt": durum["metin"]}
    if tur == "once":
        return {"tur": tur, "baslik": "Dersler henüz başlamadı", "alt": durum["metin"]}
    if tur == "bitti":
        return {"tur": tur, "baslik": "Bugünkü dersler bitti", "alt": ""}
    return {"tur": "yok", "baslik": "", "alt": ""}


def bugun_yok(devamsizlik, bugun: str) -> list[int]:
    """Bugün 'yok' yazılan ders numaraları (yoklama eşleşmediyse/okunamadıysa boş)."""
    return sorted(d.ders_no for d in (devamsizlik or []) if d.tarih == bugun and d.tur == "yok")


def akis(cocuk: sqlite3.Row, an=None) -> dict:
    """{'bugun': [...], 'yarin': {'etiket', 'dersler'} | None}"""
    an = an or zaman.simdi()
    saat = an.strftime("%H:%M")
    bugun = _dersler(cocuk["sinif"], an.date())
    for d in bugun:
        d["gecti"] = bool(d["bit"]) and d["bit"] <= saat
        d["simdi"] = bool(d["bas"]) and d["bas"] <= saat < d["bit"]
    yarin = None
    for gun in range(1, 8):
        t = an.date() + timedelta(days=gun)
        dersler = _dersler(cocuk["sinif"], t)
        if dersler:
            yarin = {"etiket": "Yarın" if gun == 1 else GUN_ADI[program.GUNLER[t.weekday()]], "dersler": dersler}
            break
    return {"bugun": bugun, "yarin": yarin}


def gorevler(conn: sqlite3.Connection, k: sqlite3.Row, cocuk: sqlite3.Row) -> dict:
    """Yapılması gerekenler: onay bekleyen > okunmamış duyuru > yaklaşan ödev > yaklaşan sınav. Her birinin tek eylemi vardır."""
    ogr = f"?ogr={cocuk['id']}"
    tum: list[dict] = []
    simdi_ = zaman.simdi()
    try:
        for t in onay.bekleyenler(conn, cocuk):
            tum.append({"baslik": f"Onayınız bekleniyor: {t['baslik']}", "alt": f"Son tarih {t['son_tarih'][8:]}.{t['son_tarih'][5:7]}.{t['son_tarih'][:4]}", "href": "/veli/onaylar" + ogr, "acil": True, "etiket": "ONAY"})
        for d in duyurular.okunmamis(conn, k, 2):
            tum.append({"baslik": f"Yeni duyuru: {d['baslik']}", "alt": d["yazar"], "href": "/duyurular", "acil": False, "etiket": "DUYURU"})
        sinir = (simdi_ + timedelta(days=ODEV_GUN)).strftime(zaman.BICIM)
        for o in ortak.bekleyen_odevler(conn, cocuk):
            if o["teslim"] <= sinir:
                tum.append({"baslik": f"Ödev: {o['baslik']}", "alt": f"{o['ders'].title()} · teslim {o['teslim'][8:10]}.{o['teslim'][5:7]}.{o['teslim'][:4]}", "href": "/veli/odevler" + ogr, "acil": o["teslim"] < simdi_.strftime(zaman.BICIM), "etiket": "ÖDEV"})
        for s in ortak.yaklasan_sinavlar(conn, cocuk["sinif"], SINAV_GUN):
            tum.append({"baslik": f"Sınav: {s['baslik']}", "alt": (s["ders"] or "").title() + f" · {s['tarih'][8:]}.{s['tarih'][5:7]}.{s['tarih'][:4]}", "href": "/veli/sinavlar" + ogr, "acil": False, "etiket": "SINAV"})
    except Exception:  # noqa: BLE001 — tek kaynağın hatası ana ekranı düşürmesin
        pass
    return {"gorevler": tum[:MAX_GOREV], "fazla": max(len(tum) - MAX_GOREV, 0)}
