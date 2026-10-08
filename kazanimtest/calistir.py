"""kazanimtest/calistir.py — Kazanım testi hattı.

  server/venv/bin/python -m kazanimtest.calistir uret [--tarih YYYY-MM-DD] [--sinif 9-A]
                                                       [--ders biyoloji] [--kuru] [--sms | --sms-test]
  server/venv/bin/python -m kazanimtest.calistir durum
  server/venv/bin/python -m kazanimtest.calistir sonuc          # Form gönderimleri → form_cevap (son `sonuc_gun` gün)
  server/venv/bin/python -m kazanimtest.calistir analiz         # form_cevap → <cikti_dizini>/rapor/<sinif>.json
  server/venv/bin/python -m kazanimtest.calistir anlik-doldur   # eski kayıtlara sorular anlık görüntüsü

Sıra: hedef → aday seçimi → agy → Excel/Word → Google Form → kayıt → (SMS).
--kuru: yalnızca Excel/Word; Form, SMS ve DB kaydı yok. Bir sınıfta hata → loglanır, diğerleri sürer.
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from . import agy_secim, analiz, anlik, cikti, google_form, hedef, kayit, secici, sonuc

log = logging.getLogger("kazanimtest")
AYAR = Path(__file__).with_name("config") / "ayar.json"
TR = ZoneInfo("Europe/Istanbul")
GOSTERIM = {"edebiyat": "Edebiyat", "cografya": "Coğrafya", "din": "Din", "tarih": "Tarih"}


def ders_gosterim(anahtar: str) -> str:
    return GOSTERIM.get(anahtar, anahtar.capitalize())


def ayar_oku(yol: Path = AYAR) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def sms_metni_parcala(kayitlar: list[tuple[str, str]], azami: int = 300) -> list[str]:
    """[(ders adı, link)] → ≤azami karakterlik SMS metinleri (aynı sınıf, tek SMS; sığmazsa bölünür)."""
    onek = "Bugünkü kazanım testleriniz: "
    parcalar: list[str] = []
    simdiki = ""
    for ad, link in kayitlar:
        oge = f"{ad} {link}"
        aday = (simdiki + ", " if simdiki else onek) + oge
        if simdiki and len(aday) > azami:
            parcalar.append(simdiki)
            aday = onek + oge
        simdiki = aday
    if simdiki:
        parcalar.append(simdiki)
    return parcalar


def sms_gonder(gizli: dict, ayar: dict, sinif: str, metin: str, istemci=None, test_telefon: str | None = None) -> str:
    k = istemci or httpx
    taban = ayar.get("sms_url", "http://127.0.0.1:8020")
    baslik = {"X-Sms-Arac-Key": gizli["sms_arac_anahtar"]}
    govde = {"sinif": sinif, "metin": metin}
    if test_telefon:
        govde["test_telefon"] = test_telefon  # doluysa SMS yalnızca bu numaraya gider
    t = k.post(f"{taban}/api/arac/ogrenci-taslak", json=govde, headers=baslik, timeout=30)
    t.raise_for_status()
    tid = t.json().get("taslak_id")
    if tid is None:
        raise RuntimeError(f"SMS taslağı oluşmadı: {t.text[:200]}")
    g = k.post(f"{taban}/api/arac/ogrenci-gonder", json={"taslak_id": tid}, headers=baslik, timeout=60)
    g.raise_for_status()
    return str(tid)


def hedef_isle(h, ayar: dict, gizli: dict | None, farabi_conn, havuz_conn, kuru: bool) -> dict | None:
    """Tek (sınıf, ders) için testi üretir. Dönen: {'kayit': var olan/yeni form_testi satırı veya None}."""
    if not kuru:
        eski = kayit.var_mi(havuz_conn, h.sinif, h.ders, h.hafta)
        if eski:
            log.info("%s %s hafta %s: test zaten var, atlandı", h.sinif, h.ders, h.hafta)
            return eski
    n = int(ayar.get("soru_sayisi", 10))
    adaylar = secici.adaylar(farabi_conn, havuz_conn, h.duzey, h.ders, "\n".join(h.kazanimlar), int(ayar.get("aday_azami", 30)))
    if len(adaylar) < int(ayar.get("min_soru", 5)):
        log.warning("%s %s: yeterli aday yok (%d) — atlandı", h.sinif, h.ders, len(adaylar))
        return None
    sorular = agy_secim.sec(h.kazanimlar, adaylar, n, zaman_asimi_sn=int(ayar.get("agy_zaman_asimi_sn", 600)))
    baslik = f"{h.sinif} {ders_gosterim(h.ders)} — Hafta {h.hafta} Kazanım Testi"
    taban = cikti.dosya_tabani(ayar["cikti_dizini"], h.tarih, h.sinif, h.ders)
    xlsx = cikti.excel_yaz(taban, baslik, sorular)
    cikti.word_yaz(taban, baslik, sorular)
    log.info("%s %s: %d soru, dosya %s", h.sinif, h.ders, len(sorular), xlsx)
    if kuru:
        return None
    aciklama = "Okul numaranızı yazıp soruları cevaplayın. " + " | ".join(h.kazanimlar)[:300]
    form = google_form.form_olustur(gizli, baslik, aciklama, sorular)
    idler = [s["kimlik"] for s in sorular]
    try:  # anlık görüntü başarısızsa kayıt yine yazılır (sorular NULL → `anlik-doldur` sonra tamamlar)
        goruntu = anlik.olustur(sorular, h.kazanimlar)
    except Exception:
        log.exception("%s %s: soru anlık görüntüsü üretilemedi", h.sinif, h.ders)
        goruntu = None
    if not kayit.kaydet(havuz_conn, h.sinif, h.ders, h.hafta, "\n".join(h.kazanimlar), idler, form, xlsx, sorular=goruntu):
        log.warning("%s %s: kayıt çakıştı (başka süreç yazmış)", h.sinif, h.ders)
    kayit.kullanim_artir(havuz_conn, idler)
    return kayit.var_mi(havuz_conn, h.sinif, h.ders, h.hafta)


def sinif_sms(sinif: str, satirlar: list[dict], ayar: dict, gizli: dict, havuz_conn, test: bool = False) -> None:
    test_telefon = gizli.get("test_telefon") if test else None
    if test and not test_telefon:
        raise RuntimeError("--sms-test için gizli.json::test_telefon yok; SMS atılmadı")
    bekleyen = [s for s in satirlar if (test or not s.get("sms_gonderim_id")) and (s.get("form_kisa_url") or s.get("form_url"))]
    if not bekleyen:
        return
    cift = [(ders_gosterim(s["ders"]), s.get("form_kisa_url") or s["form_url"]) for s in bekleyen]
    idler = [s["id"] for s in bekleyen]
    # Tüm parçalar gitmeden işaretleme yapılmaz; her parça kendi gruplarını işaretler.
    for parca in sms_metni_parcala(cift, int(ayar.get("sms_azami_karakter", 300))):
        grup = [i for (ad, link), i in zip(cift, idler) if f"{ad} {link}" in parca]
        gid = sms_gonder(gizli, ayar, sinif, parca, test_telefon=test_telefon)
        if not test:  # deneme gönderimi gerçek gönderimi engellemesin
            kayit.sms_isaretle(havuz_conn, grup, gid)


def uret(gun: date, sinif=None, ders=None, kuru=False, sms=False, ayar=None, sms_test=False) -> int:
    ayar = ayar or ayar_oku()
    hedefler = hedef.hedefler(gun, ayar, sinif, ders)
    if not hedefler:
        log.info("%s için hedef yok (beyaz liste: %s)", gun, ayar.get("dersler"))
        return 0
    gizli = None if kuru else google_form.gizli_oku()
    farabi_conn = secici.baglan(ayar.get("farabi_db", "farabi"))
    havuz_conn = secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    hata = 0
    sinif_kayitlari: dict[str, list[dict]] = {}
    for h in hedefler:
        try:
            satir = hedef_isle(h, ayar, gizli, farabi_conn, havuz_conn, kuru)
            if satir:
                sinif_kayitlari.setdefault(h.sinif, []).append(satir)
        except Exception:
            hata += 1
            log.exception("%s %s işlenemedi — sonrakine geçiliyor", h.sinif, h.ders)
            for c in (farabi_conn, havuz_conn):
                try:
                    c.rollback()
                except Exception:  # noqa: BLE001
                    log.debug("rollback başarısız")
    if (sms or sms_test) and not kuru:
        for sn, satirlar in sinif_kayitlari.items():
            try:
                sinif_sms(sn, satirlar, ayar, gizli, havuz_conn, test=sms_test)
            except Exception:
                hata += 1
                log.exception("%s SMS gönderilemedi", sn)
    farabi_conn.close()
    havuz_conn.close()
    return hata


def durum() -> None:
    ayar = ayar_oku()
    print("beyaz liste:", ayar.get("dersler"), "| soru sayısı:", ayar.get("soru_sayisi"))
    conn = secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    for r in kayit.son_kayitlar(conn):
        print(r["id"], r["sinif"], r["ders"], f"h{r['hafta']}", r["durum"], r["form_kisa_url"] or r["form_url"])
    conn.close()


def sonuc_cek() -> int:
    ayar = ayar_oku()
    gizli = google_form.gizli_oku()
    conn = secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    try:
        return sonuc.calis(conn, gizli, int(ayar.get("sonuc_gun", 30)))
    finally:
        conn.close()


def analiz_calistir() -> int:
    ayar = ayar_oku()
    conn = secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    try:
        return analiz.rapor_yaz(conn, ayar)
    finally:
        conn.close()


def anlik_doldur() -> int:
    ayar = ayar_oku()
    farabi_conn = secici.baglan(ayar.get("farabi_db", "farabi"))
    havuz_conn = secici.baglan(ayar.get("havuz_db", "soru_havuzu"))
    try:
        ok, atlanan = anlik.doldur(farabi_conn, havuz_conn, kayit)
    finally:
        farabi_conn.close()
        havuz_conn.close()
    log.info("anlık görüntü: %d doldurulan, %d atlanan", ok, atlanan)
    return 1 if atlanan else 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="kazanimtest")
    alt = ap.add_subparsers(dest="komut", required=True)
    u = alt.add_parser("uret")
    u.add_argument("--tarih", type=date.fromisoformat, default=None)
    u.add_argument("--sinif")
    u.add_argument("--ders")
    u.add_argument("--kuru", action="store_true")
    u.add_argument("--sms", action="store_true")
    u.add_argument("--sms-test", action="store_true", help="SMS yalnızca gizli.json::test_telefon'a gider")
    alt.add_parser("durum")
    alt.add_parser("sonuc")
    alt.add_parser("anlik-doldur")
    alt.add_parser("analiz")
    a = ap.parse_args(argv)
    if a.komut == "durum":
        durum()
        return 0
    if a.komut == "sonuc":
        return 1 if sonuc_cek() else 0
    if a.komut == "analiz":
        return 1 if analiz_calistir() else 0
    if a.komut == "anlik-doldur":
        return anlik_doldur()
    hata = uret(a.tarih or datetime.now(TR).date(), a.sinif, a.ders, a.kuru, a.sms, sms_test=a.sms_test)
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
