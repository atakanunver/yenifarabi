"""kazanimtest/aylik.py — aylık öğrenci/veli kazanım raporu (Faz 2 adım 5).

analiz.sinif_analizi(ay aralığı) → öğrenci başına rapor verisi → aylik_rapor (token) → Apps Script
her öğrenci için Google Dokümanı (islem:"rapor_yaz") → isteğe bağlı kişiye özel SMS (kisisel-taslak/-gonder).

GİZLİLİK: Google'a giden veri YALNIZCA sinif + okul_no + kazanım sonuçları. İsim/telefon bu modülde
HİÇ yoktur; `{ad}` yer tutucusu SMS metninde olduğu gibi smssistemi'ne gider, orada doldurulur.
"""

import logging
import secrets
from datetime import date, datetime, timedelta

import httpx

from . import analiz, google_form

log = logging.getLogger("kazanimtest")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
         "Kasım", "Aralık"]
VARSAYILAN_SABLON = "{ad} için {ay_adi} kazanım raporu: {link}"
VARSAYILAN_GECERLILIK_GUN = 90
AD_AZAMI = 45  # SMS uzunluk denetiminde {ad} yerine konan en kötü durum uzunluğu
_SIRA = {"eksik": 0, "orta": 1, "az_veri": 2, "guclu": 3}


def ay_araligi(ay: str | None = None, bugun: date | None = None) -> tuple[date, date]:
    """"2026-10" → (2026-10-01, 2026-10-31). ay None ise bugüne göre (Europe/Istanbul) ÖNCEKİ ay."""
    if ay is None:
        bugun = bugun or datetime.now(analiz.TR).date()
        onceki_son = bugun.replace(day=1) - timedelta(days=1)
        return onceki_son.replace(day=1), onceki_son
    yil, ayno = (int(x) for x in ay.split("-"))
    bas = date(yil, ayno, 1)
    sonraki = date(yil + (ayno == 12), ayno % 12 + 1, 1)
    return bas, sonraki - timedelta(days=1)


def ay_anahtari(bas: date) -> str:
    return f"{bas.year}-{bas.month:02d}"


def ay_adi(bas: date) -> str:
    return f"{AYLAR[bas.month - 1]} {bas.year}"


def _oran(d: int, n: int) -> float:
    return round(d / n, 3) if n else 0.0


def _kaz_adi(satir: str) -> str:
    return "Diğer sorular" if satir == analiz.YOK else satir


def rapor_verisi(a: dict, bas: date, ders_gosterim=None) -> list[dict]:
    """analiz.sinif_analizi çıktısı → katılan her öğrenci için rapor verisi (İSİMSİZ)."""
    ders_gosterim = ders_gosterim or (lambda x: x)
    sinif_ders: dict[str, list[int]] = {}
    for k in a["kazanimlar"]:
        s = sinif_ders.setdefault(k["ders"], [0, 0])  # [doğru, cevap]
        s[0] += round(k["dogru_orani"] * k["cevap_sayisi"])
        s[1] += k["cevap_sayisi"]
    sinif_genel = _oran(sum(v[0] for v in sinif_ders.values()), sum(v[1] for v in sinif_ders.values()))
    raporlar = []
    for o in a["ogrenciler"]:
        if not o["toplam"]:
            continue  # teste katılmamış → rapor yok
        gruplar: dict[str, list[dict]] = {}
        for k in o["kazanimlar"]:
            gruplar.setdefault(k["ders"], []).append(k)
        dersler, eksikler, gucluler = [], [], []
        for ders in sorted(gruplar, key=ders_gosterim):
            ks = gruplar[ders]
            sd = sinif_ders.get(ders, [0, 0])
            kaz = [{"kazanim_satiri": _kaz_adi(k["kazanim_satiri"]), "oran": k["oran"], "durum": k["durum"],
                    "sayfalar": k["sayfalar"]} for k in sorted(ks, key=lambda k: (_SIRA[k["durum"]], k["oran"]))]
            dersler.append({"ders": ders_gosterim(ders), "oran": _oran(sum(k["dogru"] for k in ks), sum(k["soru"] for k in ks)),
                            "sinif_orani": _oran(*sd), "kazanimlar": kaz})
            gd = ders_gosterim(ders)
            for k in kaz:
                if k["durum"] == "eksik":
                    eksikler.append({"ders": gd, "kazanim_satiri": k["kazanim_satiri"], "sayfalar": k["sayfalar"]})
                elif k["durum"] == "guclu":
                    gucluler.append({"ders": gd, "kazanim_satiri": k["kazanim_satiri"]})
        raporlar.append({"sinif": a["sinif"], "okul_no": o["okul_no"], "ay": ay_anahtari(bas), "ay_adi": ay_adi(bas),
                         "genel": {"oran": o["oran"], "sinif_orani": sinif_genel, "test_sayisi": o["test_sayisi"]},
                         "dersler": dersler, "eksikler": eksikler, "gucluler": gucluler})
    return raporlar


def siniflar(conn, bas: date, bit: date) -> list[str]:
    """O ayda formu (form_testi) olan sınıflar."""
    with conn.cursor() as cur:
        cur.execute("SELECT sinif, olusturma FROM form_testi ORDER BY sinif")
        satirlar = cur.fetchall()
    return sorted({s for s, olus in satirlar if bas <= analiz._tr_gun(olus) <= bit})


def token_al(conn, ay: str, sinif: str, okul_no: int, son_gecerlilik: date, uretici=None) -> tuple[str, str | None]:
    """(token, sms_gonderim_id). (ay, okul_no) için MEVCUT token korunur (link değişmez); geçerlilik yenilenir."""
    uretici = uretici or (lambda: secrets.token_urlsafe(16))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO aylik_rapor (ay, sinif, okul_no, token, son_gecerlilik) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (ay, okul_no) DO UPDATE SET sinif=EXCLUDED.sinif, son_gecerlilik=EXCLUDED.son_gecerlilik "
            "RETURNING token, sms_gonderim_id",
            (ay, sinif, okul_no, uretici(), son_gecerlilik),
        )
        token, gid = cur.fetchone()
    conn.commit()
    return token, gid


def link_yaz(conn, linkler: dict[str, str]) -> None:
    """{token: doküman linki} → aylik_rapor.link (aynı token aynı doküman; tekrar güvenli)."""
    with conn.cursor() as cur:
        for token, link in linkler.items():
            cur.execute("UPDATE aylik_rapor SET link=%s WHERE token=%s", (link, token))
    conn.commit()


def sms_isaretle(conn, ay: str, okul_nolar: list[int], taslak_id: str, gonderim_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE aylik_rapor SET sms_taslak_id=%s, sms_gonderim_id=%s WHERE ay=%s AND okul_no = ANY(%s)",
                    (taslak_id, gonderim_id, ay, okul_nolar))
    conn.commit()


def sablon_doldur(sablon: str, ay_adi_: str, link: str) -> str:
    """{ay_adi} ve {link} burada doldurulur; {ad} OLDUĞU GİBİ kalır (smssistemi doldurur)."""
    return sablon.replace("{ay_adi}", ay_adi_).replace("{link}", link)


def sablon_sigiyor_mu(metin_sablon: str, azami: int = 300) -> bool:
    return len(metin_sablon.replace("{ad}", "X" * AD_AZAMI)) <= azami


def sms_kisisel(gizli: dict, ayar: dict, ogeler: list[dict], test_telefon: str | None = None, istemci=None) -> dict:
    """kisisel-taslak → kisisel-gonder. {taslak, gonderim_id}; taslakta alıcı yoksa RuntimeError."""
    k = istemci or httpx
    taban = ayar.get("sms_url", "http://127.0.0.1:8020")
    baslik = {"X-Sms-Arac-Key": gizli["sms_arac_anahtar"]}
    govde: dict = {"ogeler": ogeler}
    if test_telefon:
        govde["test_telefon"] = test_telefon
    t = k.post(f"{taban}/api/arac/kisisel-taslak", json=govde, headers=baslik, timeout=60)
    t.raise_for_status()
    taslak = t.json()
    if taslak.get("taslak_id") is None:
        raise RuntimeError(f"SMS taslağı oluşmadı: {t.text[:200]}")
    if taslak.get("bulunamayan") or taslak.get("alicisiz"):
        log.warning("kisisel-taslak: bulunamayan okul_no=%s, alıcısız okul_no=%s",
                    taslak.get("bulunamayan"), taslak.get("alicisiz"))
    g = k.post(f"{taban}/api/arac/kisisel-gonder", json={"taslak_id": taslak["taslak_id"]}, headers=baslik, timeout=120)
    g.raise_for_status()
    return {"taslak": taslak, "gonderim_id": str(g.json().get("gonderim_id"))}


def aylik(ay: str | None = None, sinif: str | None = None, sms: bool = False, sms_test: bool = False,
          kuru: bool = False, ayar: dict | None = None, havuz_conn=None, gizli: dict | None = None,
          istemci=None, bugun: date | None = None, ders_gosterim=None) -> int:
    """Hata sayısını döner. kuru: hesaplar + özet basar; Google/DB/SMS'e yazmaz."""
    from . import calistir, secici  # döngüsel içe aktarmayı önlemek için geç

    ayar = ayar or calistir.ayar_oku()
    ders_gosterim = ders_gosterim or calistir.ders_gosterim
    bas, bit = ay_araligi(ay, bugun)
    anahtar, adi = ay_anahtari(bas), ay_adi(bas)
    esikler = analiz.esikler_oku(ayar)
    gecerlilik = int(ayar.get("rapor_gecerlilik_gun", VARSAYILAN_GECERLILIK_GUN))
    sablon = ayar.get("rapor_sms_sablon", VARSAYILAN_SABLON)
    kendi_conn = havuz_conn is None
    conn = havuz_conn or secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    hata = 0
    raporlar: list[dict] = []
    try:
        for sn in siniflar(conn, bas, bit):
            if sinif and sn != sinif:
                continue
            try:
                a = analiz.sinif_analizi(conn, sn, bas, bit, esikler)
                r = rapor_verisi(a, bas, ders_gosterim)
                log.info("aylik %s %s: %d test, %d öğrenci raporlanıyor", sn, anahtar, len(a["testler"]), len(r))
                raporlar += r
            except Exception:
                hata += 1
                log.exception("%s aylık analizi başarısız — sonrakine geçiliyor", sn)
                conn.rollback()
        log.info("aylik %s: toplam %d rapor (teste katılmayanlara rapor yok)", anahtar, len(raporlar))
        if kuru or not raporlar:
            for r in raporlar:
                log.info("kuru: %s no %s — genel %%%d, eksik %d, güçlü %d", r["sinif"], r["okul_no"],
                         round(r["genel"]["oran"] * 100), len(r["eksikler"]), len(r["gucluler"]))
            return hata
        gizli = gizli or google_form.gizli_oku()
        son = (bugun or datetime.now(analiz.TR).date()) + timedelta(days=gecerlilik)
        sozlesme, yazilacak = {}, []
        for r in raporlar:
            token, gid = token_al(conn, anahtar, r["sinif"], r["okul_no"], son)
            sozlesme[r["okul_no"]] = (token, gid)
            yazilacak.append({"token": token, "ay": anahtar, "sinif": r["sinif"], "okul_no": r["okul_no"],
                              "son_gecerlilik": son.isoformat(), "veri": r})
        linkler = google_form.raporlari_yaz(gizli, yazilacak, istemci)
        link_yaz(conn, linkler)
        log.info("aylik %s: %d rapor Google Dokümanı olarak yazıldı", anahtar, len(linkler))
        if sms or sms_test:
            hata += _sms(conn, gizli, ayar, anahtar, adi, sablon, sozlesme, sms_test, istemci, linkler)
    finally:
        if kendi_conn:
            conn.close()
    return hata


def _sms(conn, gizli, ayar, anahtar, adi, sablon, sozlesme, test, istemci, linkler) -> int:
    test_telefon = gizli.get("test_telefon") if test else None
    if test and not test_telefon:
        raise RuntimeError("--sms-test için gizli.json::test_telefon yok; SMS atılmadı")
    ogeler = []
    for no, (token, gid) in sorted(sozlesme.items()):
        if gid and not test:
            continue  # zaten gönderilmiş
        ogeler.append({"okul_no": no, "metin_sablon": sablon_doldur(sablon, adi, linkler[token])})
    if not ogeler:
        log.info("aylik %s: gönderilecek SMS yok", anahtar)
        return 0
    azami = int(ayar.get("sms_azami_karakter", 300))
    if not all(sablon_sigiyor_mu(o["metin_sablon"], azami) for o in ogeler):
        raise RuntimeError(f"SMS metni {azami} karaktere sığmıyor (ad payı {AD_AZAMI}); SMS atılmadı")
    s = sms_kisisel(gizli, ayar, ogeler, test_telefon, istemci)
    log.info("aylik %s SMS: taslak %s, gönderim %s, %s", anahtar, s["taslak"].get("taslak_id"), s["gonderim_id"],
             {k: s["taslak"].get(k) for k in ("oge_sayisi", "alici_sayisi", "bulunamayan", "alicisiz")})
    if not test:  # deneme gönderimi gerçek gönderimi engellemesin
        atlanan = set(s["taslak"].get("bulunamayan") or []) | set(s["taslak"].get("alicisiz") or [])
        gonderilen = [o["okul_no"] for o in ogeler if o["okul_no"] not in atlanan]
        sms_isaretle(conn, anahtar, gonderilen, str(s["taslak"]["taslak_id"]), s["gonderim_id"])
    return 0
