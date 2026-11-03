"""Sınav takvimi: yazılılar (görevli öğretmen, kendi sınıf-dersi) ve genel deneme sınavları (düzey bazlı)."""

import sqlite3
from datetime import date, datetime, timedelta

import yetki
import zaman
from metin import sinif_seviyesi, tr_kucuk

DUZEYLER = (9, 10, 11, 12)


class SinavHatasi(ValueError):
    pass


class YetkiYok(SinavHatasi):
    pass


def _tarih(s: str) -> str:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise SinavHatasi("Sınav tarihini seçin.") from None


def _bitis(s, tarih: str) -> str | None:
    """Deneme haftasının son günü (isteğe bağlı); başlangıçtan önce olamaz."""
    if not (s or "").strip():
        return None
    try:
        b = date.fromisoformat(s.strip()).isoformat()
    except ValueError:
        raise SinavHatasi("Bitiş tarihi geçersiz.") from None
    if b < tarih:
        raise SinavHatasi("Bitiş tarihi başlangıçtan önce olamaz.")
    return None if b == tarih else b


def _ders_no(s) -> int | None:
    if s in (None, ""):
        return None
    try:
        n = int(s)
    except (TypeError, ValueError):
        raise SinavHatasi("Ders saati 1-10 arasında olmalı.") from None
    if not 1 <= n <= 10:
        raise SinavHatasi("Ders saati 1-10 arasında olmalı.")
    return n


def _duzeyler(liste) -> str:
    try:
        secili = sorted({int(x) for x in liste if str(x).strip()})
    except ValueError:
        raise SinavHatasi("Geçersiz sınıf düzeyi.") from None
    if any(d not in DUZEYLER for d in secili):
        raise SinavHatasi("Geçersiz sınıf düzeyi.")
    return ",".join(map(str, secili))  # boş = tüm okul


def yazili_ekle(
    conn, k, sinif, ders, tarih, ders_no=None, aciklama="", baslik=""
) -> int:
    ders = tr_kucuk((ders or "").strip())
    if not sinif or not ders or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise YetkiYok("Bu sınıf ve derse sınav giremezsiniz.")
    baslik = (baslik or "").strip() or f"{ders[:1].upper()}{ders[1:]} yazılısı"
    cur = conn.execute(
        "INSERT INTO sinav (yazar_id, tur, baslik, sinif, ders, tarih, ders_no, aciklama, olusturma)"
        " VALUES (?, 'yazili', ?, ?, ?, ?, ?, ?, ?)",
        (
            k["id"],
            baslik[:120],
            sinif,
            ders,
            _tarih(tarih),
            _ders_no(ders_no),
            (aciklama or "").strip()[:1000],
            zaman.simdi_str(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def deneme_ekle(conn, k, baslik, tarih, duzeyler, aciklama="", bitis="") -> int:
    if k["rol"] not in ("ogretmen", "yonetici"):
        raise YetkiYok("Deneme sınavı giremezsiniz.")
    baslik = (baslik or "").strip()
    if not baslik:
        raise SinavHatasi("Deneme sınavının adını yazın (ör. 1. TYT Denemesi).")
    tarih = _tarih(tarih)
    cur = conn.execute(
        "INSERT INTO sinav (yazar_id, tur, baslik, duzeyler, tarih, bitis, aciklama, olusturma)"
        " VALUES (?, 'deneme', ?, ?, ?, ?, ?, ?)",
        (
            k["id"],
            baslik[:120],
            _duzeyler(duzeyler),
            tarih,
            _bitis(bitis, tarih),
            (aciklama or "").strip()[:1000],
            zaman.simdi_str(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def getir(conn, sinav_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()


def duzenleyebilir(k, s) -> bool:
    return s is not None and (
        k["rol"] == "yonetici" or (k["rol"] == "ogretmen" and s["yazar_id"] == k["id"])
    )


def guncelle(
    conn, k, sinav_id: int, tarih, ders_no=None, aciklama="", baslik="", duzeyler=None,
    bitis="",
) -> None:
    s = getir(conn, sinav_id)
    if not duzenleyebilir(k, s):
        raise YetkiYok("Bu sınavı düzenleyemezsiniz.")
    if s["tur"] == "deneme":
        if not (baslik or "").strip():
            raise SinavHatasi("Deneme sınavının adını yazın.")
        tarih = _tarih(tarih)
        conn.execute(
            "UPDATE sinav SET baslik = ?, tarih = ?, bitis = ?, duzeyler = ?, aciklama = ? WHERE id = ?",
            (
                baslik.strip()[:120],
                tarih,
                _bitis(bitis, tarih),
                _duzeyler(duzeyler or []),
                (aciklama or "").strip()[:1000],
                sinav_id,
            ),
        )
    else:
        conn.execute(
            "UPDATE sinav SET baslik = ?, tarih = ?, ders_no = ?, aciklama = ? WHERE id = ?",
            (
                (baslik or "").strip()[:120] or s["baslik"],
                _tarih(tarih),
                _ders_no(ders_no),
                (aciklama or "").strip()[:1000],
                sinav_id,
            ),
        )
    conn.commit()


def sil(conn, k, sinav_id: int) -> bool:
    if not duzenleyebilir(k, getir(conn, sinav_id)):
        return False
    conn.execute("DELETE FROM sinav WHERE id = ?", (sinav_id,))
    conn.commit()
    return True


def deneme_duzeyi_kapsar(s, seviye: int) -> bool:
    return not s["duzeyler"] or str(seviye) in s["duzeyler"].split(",")


def sinif_sinavlari(
    conn, sinif: str, baslangic: str | None = None
) -> list[sqlite3.Row]:
    """Bir sınıfın öğrencisinin göreceği sınavlar: o sınıfın yazılıları + düzeyini kapsayan denemeler."""
    sql = "SELECT s.*, u.ad_soyad AS yazar FROM sinav s JOIN kullanici u ON u.id = s.yazar_id"
    params: list = []
    if baslangic:
        sql += " WHERE COALESCE(s.bitis, s.tarih) >= ?"  # süren deneme haftası düşmesin
        params.append(baslangic)
    seviye = sinif_seviyesi(sinif)
    return [
        s
        for s in conn.execute(
            sql + " ORDER BY s.tarih, s.ders_no IS NULL, s.ders_no", params
        )
        if (s["tur"] == "yazili" and s["sinif"] == sinif)
        or (s["tur"] == "deneme" and deneme_duzeyi_kapsar(s, seviye))
    ]


def ogretmen_sinavlari(conn, k, baslangic: str) -> list[sqlite3.Row]:
    """Öğretmen: kendi girdikleri + görevli sınıflarının yazılıları + tüm denemeler. Yönetici: hepsi."""
    satirlar = conn.execute(
        "SELECT s.*, u.ad_soyad AS yazar FROM sinav s JOIN kullanici u ON u.id = s.yazar_id"
        " WHERE COALESCE(s.bitis, s.tarih) >= ? ORDER BY s.tarih, s.ders_no IS NULL, s.ders_no",
        (baslangic,),
    ).fetchall()
    if k["rol"] == "yonetici":
        return satirlar
    siniflar = set(yetki.ogretmen_siniflari(conn, k["id"]))
    return [
        s
        for s in satirlar
        if s["yazar_id"] == k["id"] or s["tur"] == "deneme" or s["sinif"] in siniflar
    ]


def kalan_gun(tarih: str) -> int:
    return (date.fromisoformat(tarih) - zaman.simdi().date()).days


def yaklasan_denemeler(conn, gun: int = 3) -> list[sqlite3.Row]:
    """Başlangıcına `gun` gün ya da daha az kalmış veya haftası süren denemeler (pano + tahta)."""
    bugun = zaman.simdi().date()
    return conn.execute(
        "SELECT * FROM sinav WHERE tur = 'deneme' AND tarih <= ? AND COALESCE(bitis, tarih) >= ?"
        " ORDER BY tarih, id",
        ((bugun + timedelta(days=gun)).isoformat(), bugun.isoformat()),
    ).fetchall()


AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık")


def _gun_ay(t: str) -> str:
    d = date.fromisoformat(t)
    return f"{d.day} {AYLAR[d.month - 1]}"


def deneme_araligi(tarih: str, bitis: str | None) -> str:
    """'9–15 Kasım', '31 Mayıs – 6 Haziran' ya da tek gün '9 Kasım'."""
    son = bitis or tarih
    bas, bit = date.fromisoformat(tarih), date.fromisoformat(son)
    if bas == bit:
        return _gun_ay(tarih)
    if bas.month == bit.month:
        return f"{bas.day}–{_gun_ay(son)}"
    return f"{_gun_ay(tarih)} – {_gun_ay(son)}"


def deneme_durumu(s) -> str:
    """'9–15 Kasım · 3 gün kaldı' / 'bugün başlıyor' / 'sürüyor, son gün 15 Kasım'."""
    son = s["bitis"] or s["tarih"]
    aralik = deneme_araligi(s["tarih"], s["bitis"])
    g = kalan_gun(s["tarih"])
    if g > 0:
        durum = f"{g} gün kaldı"
    elif g == 0:
        durum = "bugün başlıyor"
    elif kalan_gun(son) == 0:
        durum = "son gün bugün"
    else:
        durum = f"sürüyor, son gün {_gun_ay(son)}"
    return f"{aralik} · {durum}"


YKS_AY_GUN = (6, 20)  # YKS her yıl yaklaşık 19-20 Haziran'da yapılır


def yks_tarihi(seviye: int) -> date:
    """9-12. sınıf öğrencisinin YKS'ye gireceği (tahmini) tarih: 12. sınıfını bitirdiği haziran."""
    bugun = zaman.simdi().date()
    akademik_baslangic = bugun.year if bugun.month >= 9 else bugun.year - 1
    return date(akademik_baslangic + 13 - seviye, *YKS_AY_GUN)
