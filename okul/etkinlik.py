"""Hızlı Etkinlik Atama: öğretmen tek adımda sınıfa 3/5/10 soruluk havuz testi atar.

Mevcut test ödevi altyapısını kullanır (odevler.odev_olustur): öğrenciler ödev listesinde görür, sonuçlar
öğretmenin ödev sayfasında ve kazanım raporlarında yer alır. Sorular onaylı havuzdan rastgele seçilir
(salt-okunur); aynı sınıfa daha önce atanan sorular mümkünse tekrarlanmaz. Yetki: yalnızca kendi
sınıf+dersi (yönetici hepsi); yetkisiz 404 (rota).
"""

import sqlite3
from datetime import datetime, timedelta

import odevler
import soru_bildirim
import zaman
from kaynaklar import arena_soru

ADETLER = (3, 5, 10)
SURELER = {"bugun": ("Bugün", 0), "yarin": ("Yarın", 1), "uc_gun": ("3 gün içinde", 3)}
HIZLI_ETIKET = "Hızlı etkinlik"
TEKRAR_SN = 60  # aynı etkinliğin çift tıklama ile iki kez atanmasını önler


class EtkinlikHatasi(Exception):
    pass


def _atanmis_idler(conn: sqlite3.Connection, sinif: str) -> list[int]:
    idler = []
    for r in conn.execute(
        "SELECT s.kaynak FROM odev_soru s JOIN odev o ON o.id = s.odev_id WHERE o.sinif = ? AND s.kaynak LIKE 'havuz:%'",
        (sinif,),
    ):
        try:
            idler.append(int(r[0].split(":", 1)[1]))
        except ValueError:
            continue
    return idler


def hizli_ata(
    conn: sqlite3.Connection,
    ogretmen_id: int,
    sinif: str,
    ders: str,
    havuz_ders: str,
    adet: int,
    sure: str,
    not_: str = "",
    kazanim: dict | None = None,
) -> int:
    """Test ödevi oluşturur ve id'sini döner. Aynı öğretmen aynı etkinliği 60 sn içinde tekrar atarsa mevcut olan döner."""
    if adet not in ADETLER:
        raise EtkinlikHatasi("Soru sayısı 3, 5 ya da 10 olmalı.")
    if sure not in SURELER:
        raise EtkinlikHatasi("Geçersiz teslim süresi.")
    if not havuz_ders or not sinif or not ders:
        raise EtkinlikHatasi("Sınıf, ders ve soru havuzu dersi seçilmeli.")
    simdi = zaman.simdi()
    baslik = f"{HIZLI_ETIKET}: {ders} {adet} soru" + (f" · {kazanim['kod']}" if kazanim else "")
    onceki = conn.execute(
        "SELECT id, olusturma FROM odev WHERE ogretmen_id = ? AND sinif = ? AND ders = ? AND baslik = ?"
        " ORDER BY id DESC LIMIT 1",
        (ogretmen_id, sinif, ders, baslik),
    ).fetchone()
    if onceki and (simdi - datetime.strptime(onceki["olusturma"], zaman.BICIM)).total_seconds() < TEKRAR_SN:
        return onceki["id"]
    seviye = int(sinif.split("-", 1)[0])
    ek = {"kazanim_id": kazanim["id"]} if kazanim else {}
    sorular = arena_soru.sorular(seviye, havuz_ders, _atanmis_idler(conn, sinif), adet, yasak=soru_bildirim.gizli_idler(conn), **ek)
    if len(sorular) < adet:
        raise EtkinlikHatasi(
            "Bu kazanım için havuzda yeterli onaylı soru yok." if kazanim else "Bu ders için havuzda yeterli onaylı soru yok."
        )
    teslim = (simdi + timedelta(days=SURELER[sure][1])).strftime("%Y-%m-%d")
    aciklama = (not_ or "").strip()[:500]
    return odevler.odev_olustur(
        conn, ogretmen_id, sinif, ders, "test", baslik, aciklama, teslim,
        [
            {"metin": s["soru"], "siklar": s["secenekler"], "dogru": s["dogru_index"],
             "kazanim": (kazanim["kod"] if kazanim else s["konu"]) or "", "kaynak": f"havuz:{s['id']}"}
            for s in sorular
        ],
    )
