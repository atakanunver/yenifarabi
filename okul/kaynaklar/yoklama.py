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


def _nolar(alan: str | None) -> set[int] | None:
    if alan is None:
        return None
    try:
        liste = json.loads(alan)
    except ValueError:
        return None
    if not isinstance(liste, list):
        return None
    sonuc: set[int] = set()
    for x in liste:
        try:
            sonuc.add(int(x))
        except (TypeError, ValueError):
            continue
    return sonuc


def _pano_ogrencileri(c: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """(sınıf, no, ad_soyad) — id sırasıyla."""
    return c.execute(
        "SELECT s.ad, o.no, o.ad_soyad FROM ogrenciler o JOIN siniflar s ON s.id = o.sinif_id"
        " ORDER BY o.id"
    ).fetchall()


def _yoklamalar(c: sqlite3.Connection, sinif: str | None, baslangic: str | None):
    sutunlar = {r[1] for r in c.execute("PRAGMA table_info(yoklama_onbellek)").fetchall()}
    no_sec = (
        "yok_nolari, izinli_nolari"
        if "yok_nolari" in sutunlar and "izinli_nolari" in sutunlar
        else "NULL, NULL"
    )
    sql = (
        f"SELECT tarih, sinif, ders_no, yok_isimleri, izinli_isimleri, {no_sec}"
        " FROM yoklama_onbellek WHERE durum = 'alindi'"
    )
    params: list = []
    if sinif:
        sql += " AND sinif = ?"
        params.append(sinif)
    if baslangic:
        sql += " AND tarih >= ?"
        params.append(baslangic)
    return c.execute(sql + " ORDER BY tarih DESC, ders_no", params).fetchall()


def _eslestir(
    okul_no: int, ogrenciler: list[tuple[str, int, str]], yoklamalar: list
) -> list[Devamsizlik]:
    """Bir öğrencinin devamsızlıkları. ogrenciler: kendi sınıfının pano öğrencileri; yoklamalar: o sınıfın kayıtları."""
    ad = next((a for _, no, a in ogrenciler if no == okul_no), None)
    if ad is None:
        return []
    hedef = normalize_isim(ad)
    ayni_isim_var = sum(1 for _, _, a in ogrenciler if normalize_isim(a) == hedef) > 1
    sonuc = []
    for tarih, _, ders_no, yok, izinli, yok_no_ham, izinli_no_ham in yoklamalar:
        yok_nolar = _nolar(yok_no_ham)
        izinli_nolar = _nolar(izinli_no_ham)
        if yok_nolar is not None or izinli_nolar is not None:
            if yok_nolar and okul_no in yok_nolar:
                sonuc.append(Devamsizlik(tarih, ders_no, "yok"))
            elif izinli_nolar and okul_no in izinli_nolar:
                sonuc.append(Devamsizlik(tarih, ders_no, "izinli"))
            continue
        if ayni_isim_var:
            continue
        if hedef in {normalize_isim(x) for x in _isimler(yok)}:
            sonuc.append(Devamsizlik(tarih, ders_no, "yok"))
        elif hedef in {normalize_isim(x) for x in _isimler(izinli)}:
            sonuc.append(Devamsizlik(tarih, ders_no, "izinli"))
    return sonuc


def devamsizlik(
    okul_no: int, sinif: str, baslangic: str | None = None
) -> list[Devamsizlik]:
    try:
        with _baglan() as c:
            ogrenciler = [o for o in _pano_ogrencileri(c) if o[0] == sinif]
            return _eslestir(okul_no, ogrenciler, _yoklamalar(c, sinif, baslangic))
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e


def sinif_devamsizlik(sinif: str, baslangic: str) -> dict[int, list[Devamsizlik]]:
    """okul_no → devamsızlıklar (yalnızca pano'da eşleşen öğrenciler; kaydı olmayanın listesi boştur)."""
    try:
        with _baglan() as c:
            ogrenciler = [o for o in _pano_ogrencileri(c) if o[0] == sinif]
            yoklamalar = _yoklamalar(c, sinif, baslangic)
            return {no: _eslestir(no, ogrenciler, yoklamalar) for _, no, _ in ogrenciler}
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e


def ozet(kayitlar: dict[int, list[Devamsizlik]], bugun: str, esik_gun: int = 3) -> dict[str, list[tuple[int, int]]]:
    """(okul_no, sayı) listeleri: 'bugun' = bugün 'yok' yazılan ders sayısı; 'tekrar' = 'yok' olunan farklı gün sayısı >= esik_gun."""
    bugun_yok, tekrar = [], []
    for no, liste in sorted(kayitlar.items()):
        yok = [x for x in liste if x.tur == "yok"]
        if sayi := sum(1 for x in yok if x.tarih == bugun):
            bugun_yok.append((no, sayi))
        if (gun := len({x.tarih for x in yok})) >= esik_gun:
            tekrar.append((no, gun))
    return {"bugun": bugun_yok, "tekrar": sorted(tekrar, key=lambda t: -t[1])}


def sinif_yok_sayilari(baslangic: str) -> dict[str, int]:
    """Sınıf başına 'yok' yazılan ders-saati sayısı (izinli hariç)."""
    try:
        with _baglan() as c:
            sayac: Counter = Counter()
            for _, sinif, _, yok, _, _, _ in _yoklamalar(c, None, baslangic):
                sayac[sinif] += len(_isimler(yok))
            return dict(sayac)
    except sqlite3.Error as e:
        raise KaynakHatasi(f"yoklama okunamadı: {e}") from e


def eslesmeyenler(platform: dict[int, str], baslangic: str) -> list[dict]:
    """platform: okul_no → sınıf (okul.db). Yöneticiye gösterilecek tutarsızlıklar."""
    try:
        with _baglan() as c:
            ogrenciler = _pano_ogrencileri(c)
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

    return sonuc


def _kayit(tur: str, sinif: str, isim: str, aciklama: str) -> dict:
    return {"tur": tur, "sinif": sinif, "isim": isim, "aciklama": aciklama}
