"""Öğretmenin sınıfa PDF göndermesi ve PDF'ten foto teslimli ödev (mantık katmanı)."""

import sqlite3
from datetime import timedelta

import dosyalar
import odevler
import yetki
import zaman

AZAMI_BASLIK = 120


class PdfHatasi(ValueError):
    pass


def _ad(dosya_adi: str) -> str:
    return (dosya_adi or "belge.pdf").replace("\\", "/").rsplit("/", 1)[-1][:150]


def gonder(
    conn: sqlite3.Connection,
    k: sqlite3.Row,
    sinif: str,
    ders: str,
    baslik: str,
    dosya_adi: str,
    veri: bytes,
) -> int:
    """PDF'i sınıfa gönderir. Yetkisiz (sınıf/ders atanmamış) → PermissionError."""
    if not sinif or not ders or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise PermissionError
    baslik = baslik.strip() or _ad(dosya_adi).rsplit(".", 1)[0]
    yeni = dosyalar.pdf_kaydet(veri)
    cur = conn.execute(
        "INSERT INTO sinif_pdf (ogretmen_id, sinif, ders, baslik, dosya_adi, depo_adi, boyut, zaman)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (k["id"], sinif, ders, baslik[:AZAMI_BASLIK], _ad(dosya_adi), yeni.depo_adi, yeni.boyut, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


SORU_SEVIYELER = (9, 10, 11)  # 12. sınıf dondurulmuş (soruhavuzu.vt.DONDURULMUS_SINIFLAR ile aynı kural); seneye hepsi Maarif
ZAMAN_ASIMI_SAAT = 6  # 'isleniyor' bu kadar süre takılı kalırsa yeniden sıraya girer


def soru_iste(conn: sqlite3.Connection, k: sqlite3.Row, pdf_id: int, bas: str, bit: str, kvkk: bool) -> None:
    """PDF'in soru havuzuna katkı için işlenmesini ister (yalnızca 9-10-11; PDF'in sahibi ya da yönetici)."""
    p = pdf_getir(conn, pdf_id)
    if p is None or (k["rol"] != "yonetici" and p["ogretmen_id"] != k["id"]):
        raise PermissionError
    if not kvkk:
        raise PdfHatasi("PDF'te öğrenci/veli kişisel verisi olmadığını onaylayın.")
    try:
        seviye = int(p["sinif"].split("-", 1)[0])
    except ValueError:
        seviye = 0
    if seviye not in SORU_SEVIYELER:
        raise PdfHatasi("Soru havuzuna katkı yalnızca 9, 10 ve 11. sınıflar için açık.")
    if p["soru_durum"] in ("bekliyor", "isleniyor"):
        raise PdfHatasi("Bu PDF zaten sırada.")
    b, e = sayfa_araligi(bas, bit)
    conn.execute(
        "UPDATE sinif_pdf SET soru_uret = 1, soru_durum = 'bekliyor', soru_bas = ?, soru_bit = ?,"
        " soru_onayli = 0, soru_red = 0, soru_not = NULL, soru_zaman = ? WHERE id = ?",
        (b, e, zaman.simdi_str(), pdf_id),
    )
    conn.commit()


def bekleyen_istekler(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """soruhavuzu gece turu için: sırada bekleyenler + 6 saatten uzun 'isleniyor' kalanlar."""
    sinir = (zaman.simdi() - timedelta(hours=ZAMAN_ASIMI_SAAT)).strftime(zaman.BICIM)
    return conn.execute(
        "SELECT id, sinif, ders, baslik, soru_bas, soru_bit FROM sinif_pdf WHERE soru_uret = 1 AND"
        " (soru_durum = 'bekliyor' OR (soru_durum = 'isleniyor' AND soru_zaman < ?)) ORDER BY id",
        (sinir,),
    ).fetchall()


def soru_sonucu(
    conn: sqlite3.Connection, pdf_id: int, durum: str, onayli: int = 0, red: int = 0, not_: str = ""
) -> bool:
    if durum not in ("bekliyor", "isleniyor", "bitti", "hata"):
        raise PdfHatasi("Geçersiz durum.")
    cur = conn.execute(
        "UPDATE sinif_pdf SET soru_durum = ?, soru_onayli = ?, soru_red = ?, soru_not = ?, soru_zaman = ?"
        " WHERE id = ? AND soru_uret = 1",
        (durum, int(onayli), int(red), (not_ or "")[:300], zaman.simdi_str(), pdf_id),
    )
    conn.commit()
    return cur.rowcount == 1


def pdf_getir(conn: sqlite3.Connection, pdf_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sinif_pdf WHERE id = ?", (pdf_id,)).fetchone()


def pdf_gorebilir(conn: sqlite3.Connection, k: sqlite3.Row, pdf_id: int) -> sqlite3.Row | None:
    """Sahibi öğretmen, yönetici ya da PDF'in sınıfındaki öğrenci; diğer herkes için None (404)."""
    p = pdf_getir(conn, pdf_id)
    if p is None:
        return None
    if k["rol"] == "yonetici" or (k["rol"] == "ogretmen" and k["id"] == p["ogretmen_id"]):
        return p
    if k["rol"] == "ogrenci":
        o = yetki.ogrenci_kaydi(conn, k["id"])
        if o is not None and o["sinif"] == p["sinif"]:
            return p
    return None


def ogretmen_pdfleri(conn: sqlite3.Connection, k: sqlite3.Row) -> list[sqlite3.Row]:
    sql = "SELECT * FROM sinif_pdf"
    if k["rol"] == "yonetici":
        return conn.execute(sql + " ORDER BY zaman DESC").fetchall()
    return conn.execute(sql + " WHERE ogretmen_id = ? ORDER BY zaman DESC", (k["id"],)).fetchall()


def sinif_pdfleri(conn: sqlite3.Connection, sinif: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT p.*, u.ad_soyad AS ogretmen FROM sinif_pdf p JOIN kullanici u ON u.id = p.ogretmen_id"
        " WHERE p.sinif = ? ORDER BY p.zaman DESC",
        (sinif,),
    ).fetchall()


def pdf_sil(conn: sqlite3.Connection, k: sqlite3.Row, pdf_id: int) -> bool:
    p = pdf_getir(conn, pdf_id)
    if p is None or (k["rol"] != "yonetici" and p["ogretmen_id"] != k["id"]):
        return False
    conn.execute("DELETE FROM sinif_pdf WHERE id = ?", (pdf_id,))  # odev_pdf bağları CASCADE
    conn.commit()
    dosyalar.sil("pdf", p["depo_adi"])
    return True


def sayfa_araligi(bas: str, bit: str) -> tuple[int | None, int | None]:
    def _n(x: str) -> int | None:
        x = (x or "").strip()
        if not x:
            return None
        if not x.isdigit() or not 1 <= int(x) <= 9999:
            raise PdfHatasi("Sayfa numarası geçersiz.")
        return int(x)

    b, e = _n(bas), _n(bit)
    if b is None and e is not None:
        b = e
    if b is not None and e is None:
        e = b
    if b is not None and e < b:
        raise PdfHatasi("Bitiş sayfası başlangıçtan küçük olamaz.")
    return b, e


def odev_ver(
    conn: sqlite3.Connection,
    k: sqlite3.Row,
    pdf: sqlite3.Row,
    baslik: str,
    aciklama: str,
    teslim: str,
    bas: str,
    bit: str,
) -> int:
    b, e = sayfa_araligi(bas, bit)
    if not aciklama.strip():
        s = f"s. {b}-{e}" if b != e else f"s. {b}" if b else ""
        aciklama = (
            f"Ekteki PDF'in {s} sorularını çözün; cevaplarınızı fotoğrafını çekip bu sayfadan yükleyin."
            if s
            else "Ekteki PDF'teki soruları çözün; cevaplarınızı fotoğrafını çekip bu sayfadan yükleyin."
        )
    try:
        odev_id = odevler.odev_olustur(
            conn, k["id"], pdf["sinif"], pdf["ders"], "klasik", baslik, aciklama, teslim, []
        )
    except odevler.OdevHatasi as ex:
        raise PdfHatasi(str(ex)) from ex
    conn.execute(
        "INSERT INTO odev_pdf (odev_id, pdf_id, sayfa_bas, sayfa_bit) VALUES (?, ?, ?, ?)",
        (odev_id, pdf["id"], b, e),
    )
    conn.commit()
    return odev_id


def odev_eki(conn: sqlite3.Connection, odev_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT op.sayfa_bas, op.sayfa_bit, p.id AS pdf_id, p.baslik FROM odev_pdf op"
        " JOIN sinif_pdf p ON p.id = op.pdf_id WHERE op.odev_id = ?",
        (odev_id,),
    ).fetchone()


def foto_yukle(conn: sqlite3.Connection, odev: sqlite3.Row, ogrenci_id: int, veri: bytes) -> None:
    if odev["tur"] != "klasik":
        raise PdfHatasi("Bu ödev foto ile teslim edilmez.")
    yeni = dosyalar.odev_foto_kaydet(veri)
    eski = conn.execute(
        "SELECT depo_adi FROM odev_foto WHERE odev_id = ? AND ogrenci_id = ?", (odev["id"], ogrenci_id)
    ).fetchone()
    conn.execute(
        "INSERT INTO odev_foto (odev_id, ogrenci_id, depo_adi, tur, zaman) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (odev_id, ogrenci_id) DO UPDATE SET depo_adi = excluded.depo_adi,"
        " tur = excluded.tur, zaman = excluded.zaman",
        (odev["id"], ogrenci_id, yeni.depo_adi, yeni.tur, zaman.simdi_str()),
    )
    odevler.yapti_isaretle(conn, odev, ogrenci_id)  # commit eder
    if eski:
        dosyalar.sil("odev_foto", eski["depo_adi"])


def foto_getir(conn: sqlite3.Connection, odev_id: int, ogrenci_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM odev_foto WHERE odev_id = ? AND ogrenci_id = ?", (odev_id, ogrenci_id)
    ).fetchone()


def foto_gorebilir(
    conn: sqlite3.Connection, k: sqlite3.Row, odev_id: int, ogrenci_id: int
) -> sqlite3.Row | None:
    """Fotoyu yalnızca öğrencinin kendisi, ödevin sahibi öğretmen ve yönetici görür (veli görmez)."""
    f = foto_getir(conn, odev_id, ogrenci_id)
    odev = odevler.odev_getir(conn, odev_id)
    if f is None or odev is None:
        return None
    if k["rol"] == "yonetici" or (k["rol"] == "ogretmen" and odev["ogretmen_id"] == k["id"]):
        return f
    if k["rol"] == "ogrenci":
        o = yetki.ogrenci_kaydi(conn, k["id"])
        if o is not None and o["id"] == ogrenci_id:
            return f
    return None


def odev_silinirken(conn: sqlite3.Connection, odev_id: int) -> None:
    """Ödev silinmeden ÖNCE çağrılır: foto dosyalarını diskten kaldırır (kayıtlar CASCADE ile gider)."""
    for r in conn.execute("SELECT depo_adi FROM odev_foto WHERE odev_id = ?", (odev_id,)).fetchall():
        dosyalar.sil("odev_foto", r["depo_adi"])
