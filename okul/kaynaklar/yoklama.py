"""Tahta yoklaması (yoklama_pano.db) — salt-okunur.

Pano gelmeyenleri İSİMLE tutar (yok_isimleri JSON listesi). Eşleme:
okul_no → pano ogrenciler (aynı sınıf, no) → ad_soyad → normalize edilmiş isim.
Aynı sınıfta aynı normalize isme sahip iki öğrenci varsa veri hiç gösterilmez
(yanlış çocuğa devamsızlık yazmaktansa boş göstermek), eslesmeyenler()'de raporlanır.
"""

import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass

from ayarlar import AYAR
from metin import normalize_isim

from kaynaklar import KaynakHatasi


@dataclass(frozen=True)
class Devamsizlik:
    tarih: str
    ders_no: int
    tur: str  # "yok" | "izinli"


@contextmanager
def _baglan():
    yol = AYAR.pano_db_yolu
    if not yol.exists():
        raise KaynakHatasi("yoklama veritabanı bulunamadı")
    try:
        c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama veritabanı açılamadı: {e}") from e
    try:
        yield c
    finally:
        c.close()


def _isimler(alan: str | None) -> list[str]:
    try:
        liste = json.loads(alan or "[]")
    except ValueError:
        return []
    return [str(x) for x in liste if str(x).strip()]


def _pano_ogrencileri(c: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """(sınıf, no, ad_soyad) — id sırasıyla."""
    return c.execute(
        "SELECT s.ad, o.no, o.ad_soyad FROM ogrenciler o JOIN siniflar s ON s.id = o.sinif_id"
        " ORDER BY o.id"
    ).fetchall()


def _yoklamalar(c: sqlite3.Connection, sinif: str | None, baslangic: str | None):
    sql = "SELECT tarih, sinif, ders_no, yok_isimleri, izinli_isimleri FROM yoklama_onbellek WHERE durum = 'alindi'"
    params: list = []
    if sinif:
        sql += " AND sinif = ?"
        params.append(sinif)
    if baslangic:
        sql += " AND tarih >= ?"
        params.append(baslangic)
    return c.execute(sql + " ORDER BY tarih DESC, ders_no", params).fetchall()


def devamsizlik(
    okul_no: int, sinif: str, baslangic: str | None = None
) -> list[Devamsizlik]:
    try:
        with _baglan() as c:
            ogrenciler = [o for o in _pano_ogrencileri(c) if o[0] == sinif]
            ad = next((a for _, no, a in ogrenciler if no == okul_no), None)
            if ad is None:
                return []
            hedef = normalize_isim(ad)
            if sum(1 for _, _, a in ogrenciler if normalize_isim(a) == hedef) > 1:
                return []
            sonuc = []
            for tarih, _, ders_no, yok, izinli in _yoklamalar(c, sinif, baslangic):
                if hedef in {normalize_isim(x) for x in _isimler(yok)}:
                    sonuc.append(Devamsizlik(tarih, ders_no, "yok"))
                elif hedef in {normalize_isim(x) for x in _isimler(izinli)}:
                    sonuc.append(Devamsizlik(tarih, ders_no, "izinli"))
            return sonuc
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e


def sinif_yok_sayilari(baslangic: str) -> dict[str, int]:
    """Sınıf başına 'yok' yazılan ders-saati sayısı (izinli hariç)."""
    try:
        with _baglan() as c:
            sayac: Counter = Counter()
            for _, sinif, _, yok, _ in _yoklamalar(c, None, baslangic):
                sayac[sinif] += len(_isimler(yok))
            return dict(sayac)
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e


def eslesmeyenler(platform: dict[int, str], baslangic: str) -> list[dict]:
    """platform: okul_no → sınıf (okul.db). Yöneticiye gösterilecek tutarsızlıklar."""
    try:
        with _baglan() as c:
            ogrenciler = _pano_ogrencileri(c)
            yoklamalar = _yoklamalar(c, None, baslangic)
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e

    sonuc: list[dict] = []
    sinif_isimleri: dict[str, Counter] = defaultdict(Counter)
    ilk_yazim: dict[tuple[str, str], str] = {}
    for sinif, no, ad in ogrenciler:
        n = normalize_isim(ad)
        sinif_isimleri[sinif][n] += 1
        ilk_yazim.setdefault((sinif, n), ad)
        if no not in platform:
            sonuc.append(
                _kayit(
                    "platformda_yok",
                    sinif,
                    ad,
                    f"pano no {no} platformda kayıtlı değil",
                )
            )
        elif platform[no] != sinif:
            sonuc.append(
                _kayit(
                    "sinif_farkli",
                    sinif,
                    ad,
                    f"no {no}: panoda {sinif}, platformda {platform[no]}",
                )
            )

    for sinif, sayac in sinif_isimleri.items():
        for n, adet in sayac.items():
            if adet > 1:
                sonuc.append(
                    _kayit(
                        "ayni_isim",
                        sinif,
                        ilk_yazim[(sinif, n)],
                        f"sınıfta {adet} öğrenci aynı isimde",
                    )
                )

    goruldu = set()
    for _, sinif, _, yok, izinli in yoklamalar:
        for isim in _isimler(yok) + _isimler(izinli):
            n = normalize_isim(isim)
            if n not in sinif_isimleri[sinif] and (sinif, n) not in goruldu:
                goruldu.add((sinif, n))
                sonuc.append(
                    _kayit(
                        "yoklamada_var_listede_yok",
                        sinif,
                        isim,
                        "yoklamadaki isim sınıf listesinde yok",
                    )
                )
    return sonuc


def _kayit(tur: str, sinif: str, isim: str, aciklama: str) -> dict:
    return {"tur": tur, "sinif": sinif, "isim": isim, "aciklama": aciklama}
