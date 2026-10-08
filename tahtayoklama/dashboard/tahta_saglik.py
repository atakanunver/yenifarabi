"""Tahta donanım sağlığı (2026-10-08): nabızla gelen ölçümleri doğrular,
uyarı üretir, Sistem Durumu sayfası için listeler.

Ölçümü `tahta_istemci.py::saglik_olc` yapar (tahta, sistem python3). Tahtaya
GÜVENİLMEZ: gelen her alan beyaz listeden geçer, tipi/aralığı denetlenir,
geçersiz alan sessizce düşer. Salt-okunur izleme — hiçbir şey tetiklemez.
"""

import json
import math
import sqlite3

# Uyarı eşikleri
SICAKLIK_HATA_C = 85
SICAKLIK_UYARI_C = 75
BELLEK_HATA_MB = 300      # boş bellek bunun ALTINDA ise
BELLEK_UYARI_MB = 600
TAKAS_UYARI_MB = 1000     # takas kullanımı bu değer ve üstü ise
DOKUNMATIK_KOPMA_UYARI = 3
CEVRIMDISI_SN = 180       # nabız bundan eskiyse çevrimdışı
GECMIS_GUN = 14

_ONDALIKLI = {"sicaklik_c": (-20, 150), "yuk1": (0, 1000)}
_TAMSAYI = {
    "bellek_bos_mb": (0, 1_000_000), "takas_mb": (0, 1_000_000),
    "calisma_sn": (0, 10**9), "oom_sayisi": (0, 1_000_000),
    "dokunmatik_kopma": (0, 1_000_000),
}
_MANTIKSAL = ("dokunmatik_var",)


def _sayi_mi(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def saglik_temizle(ham) -> dict:
    """Beyaz liste + tip/aralık denetimi. Geçersiz alan düşer; dict değilse {}."""
    if not isinstance(ham, dict):
        return {}
    temiz: dict = {}
    for ad, (alt, ust) in _ONDALIKLI.items():
        d = ham.get(ad)
        if _sayi_mi(d) and alt <= d <= ust:
            temiz[ad] = float(d) if ad == "yuk1" else d
    for ad, (alt, ust) in _TAMSAYI.items():
        d = ham.get(ad)
        if isinstance(d, int) and not isinstance(d, bool) and alt <= d <= ust:
            temiz[ad] = d
    for ad in _MANTIKSAL:
        if isinstance(ham.get(ad), bool):
            temiz[ad] = ham[ad]
    aid = ham.get("acilis_id")
    if isinstance(aid, str) and 0 < len(aid) <= 64:
        temiz["acilis_id"] = aid
    return temiz


def uyarilar(saglik: dict, nabiz_yasi_sn: float) -> list[dict]:
    """[{"seviye": "uyari"|"hata", "mesaj": str}]. Çevrimdışı tahtada yalnızca
    tek hata (eski ölçümler yanıltıcı olur)."""
    if nabiz_yasi_sn > CEVRIMDISI_SN:
        dk = int(nabiz_yasi_sn // 60)
        return [{"seviye": "hata", "mesaj": f"Çevrimdışı (son nabız {dk} dk önce)"}]
    liste: list[dict] = []

    def ekle(seviye: str, mesaj: str) -> None:
        liste.append({"seviye": seviye, "mesaj": mesaj})

    sic = saglik.get("sicaklik_c")
    if sic is not None:
        if sic >= SICAKLIK_HATA_C:
            ekle("hata", f"Çok sıcak: {sic:g} °C")
        elif sic >= SICAKLIK_UYARI_C:
            ekle("uyari", f"Sıcaklık yüksek: {sic:g} °C")
    bos = saglik.get("bellek_bos_mb")
    if bos is not None:
        if bos < BELLEK_HATA_MB:
            ekle("hata", f"Boş bellek kritik: {bos} MB")
        elif bos < BELLEK_UYARI_MB:
            ekle("uyari", f"Boş bellek az: {bos} MB")
    takas = saglik.get("takas_mb")
    if takas is not None and takas >= TAKAS_UYARI_MB:
        ekle("uyari", f"Takas kullanımı yüksek: {takas} MB")
    oom = saglik.get("oom_sayisi")
    if oom is not None and oom > 0:
        ekle("hata", f"Açılıştan beri {oom} kez bellek doldu (program kapatıldı)")
    kopma = saglik.get("dokunmatik_kopma")
    if kopma is not None and kopma >= DOKUNMATIK_KOPMA_UYARI:
        ekle("uyari", f"Dokunmatik {kopma} kez koptu")
    if saglik.get("dokunmatik_var") is False:
        ekle("uyari", "Dokunmatik aygıt görünmüyor")
    return liste


def _durum(saglik: dict, yas: float, uyarilar_: list[dict]) -> str:
    if not saglik:
        return "veri_yok"
    if yas > CEVRIMDISI_SN:
        return "cevrimdisi"
    if any(u["seviye"] == "hata" for u in uyarilar_):
        return "hata"
    return "uyari" if uyarilar_ else "iyi"


def liste(conn: sqlite3.Connection) -> list[dict]:
    """tahta_nabiz'daki her tahta için bir kayıt (tahta_ad sırasıyla)."""
    satirlar = conn.execute(
        "SELECT tahta_ad, son_gorulme, saglik, "
        "       CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', son_gorulme) AS INTEGER) AS yas "
        "FROM tahta_nabiz ORDER BY tahta_ad"
    ).fetchall()
    maks = {
        r["tahta_ad"]: r["m"]
        for r in conn.execute(
            "SELECT tahta_ad, MAX(sicaklik_c) AS m FROM tahta_saglik_gecmis "
            "WHERE zaman >= datetime('now', '-24 hours') GROUP BY tahta_ad"
        )
    }
    sonuc = []
    for r in satirlar:
        try:
            saglik = json.loads(r["saglik"]) if r["saglik"] else {}
        except ValueError:
            saglik = {}
        if not isinstance(saglik, dict):
            saglik = {}
        yas = max(0, r["yas"] or 0)
        u = uyarilar(saglik, yas) if saglik else []
        sonuc.append({
            "tahta_ad": r["tahta_ad"],
            "son_gorulme": r["son_gorulme"],
            "nabiz_yasi_sn": yas,
            "saglik": saglik,
            "sicaklik_24s_max": maks.get(r["tahta_ad"]),
            "uyarilar": u,
            "durum": _durum(saglik, yas, u),
        })
    return sonuc


def gecmisi_buda(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM tahta_saglik_gecmis WHERE zaman < datetime('now', ?)",
        (f"-{GECMIS_GUN} days",))
