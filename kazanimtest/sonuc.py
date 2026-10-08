"""kazanimtest/sonuc.py — Google Form gönderimlerini form_cevap tablosuna çeker (gece, proxy üzerinden).

Kurallar: aynı okul_no birden çok gönderirse EN ERKEN zamanlı gönderim sayılır; DB'de zaten satırı olan
(form, okul_no, soru_sira) için ON CONFLICT DO NOTHING → ilk yazılan kalır (sonradan gelen daha erken
zamanlı olsa bile dokunulmaz). Şık metni anlık görüntüdeki seçeneklerle strip() eşitliğiyle eşlenir;
bulunamazsa secilen NULL, dogru False. Sayıya çevrilemeyen okul_no atlanır ve sayılır.
"""

import logging
from datetime import datetime

from . import google_form, kayit

log = logging.getLogger("kazanimtest")


def okul_no_coz(ham) -> int | None:
    s = str(ham or "").strip()
    try:
        return int(s)
    except ValueError:
        try:
            f = float(s)
        except ValueError:
            return None
        return int(f) if f.is_integer() else None


def cevaplari_coz(sorular: list[dict], cevaplar: list[dict]) -> tuple[list[tuple], dict]:
    """Ham gönderimler → [(okul_no, soru_sira, secilen|None, dogru, zaman)] + istatistik."""
    ist = {"gonderim": len(cevaplar), "gecersiz_no": 0, "eslesmeyen_sik": 0, "tekrar": 0}
    sirali = sorted(cevaplar, key=lambda c: datetime.fromisoformat(str(c["zaman"]).replace("Z", "+00:00")))
    gorulen: set[int] = set()
    satirlar: list[tuple] = []
    for c in sirali:
        no = okul_no_coz(c.get("okul_no"))
        if no is None or no < 0:
            ist["gecersiz_no"] += 1
            continue
        if no in gorulen:
            ist["tekrar"] += 1
            continue
        gorulen.add(no)
        zaman = datetime.fromisoformat(str(c["zaman"]).replace("Z", "+00:00"))
        secimler = c.get("secimler") or []
        for sira, s in enumerate(sorular):
            metin = secimler[sira] if sira < len(secimler) else None
            secilen = None
            if metin is not None:
                oz = [str(x).strip() for x in s["secenekler"]]
                if str(metin).strip() in oz:
                    secilen = oz.index(str(metin).strip())
                else:
                    ist["eslesmeyen_sik"] += 1
            satirlar.append((no, sira, secilen, secilen is not None and secilen == int(s["dogru_index"]), zaman))
    return satirlar, ist


def form_isle(conn, gizli: dict, k: dict, istemci=None) -> dict:
    sorular = k.get("sorular")
    if not sorular:
        raise RuntimeError("anlık görüntü yok (önce `calistir anlik-doldur`)")
    cevaplar = google_form.sonuclari_al(gizli, k["form_id"], istemci)
    satirlar, ist = cevaplari_coz(sorular, cevaplar)
    ist["yeni_cevap"] = kayit.cevap_yaz(conn, k["id"], satirlar)
    return ist


def calis(conn, gizli: dict, gun: int = 30, istemci=None) -> int:
    """Hata sayısını döner (bir formdaki hata diğerlerini durdurmaz)."""
    hata = 0
    for k in kayit.son_gun_formlari(conn, gun):
        try:
            ist = form_isle(conn, gizli, k, istemci)
            log.info("form_testi %s (%s %s h%s): %s", k["id"], k["sinif"], k["ders"], k["hafta"], ist)
        except Exception:
            hata += 1
            log.exception("form_testi %s sonuç çekilemedi — sonrakine geçiliyor", k.get("id"))
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                log.debug("rollback başarısız")
    return hata
