"""Veli onay/izin belgeleri (gezi izni, toplantı katılımı...). Yazar: yönetici (tüm okul ya da sınıf) ya da öğretmen (kendi sınıfı).

Veli çocuk başına Evet/Hayır yanıtlar; son tarihe kadar değiştirebilir. Veli yalnızca KENDİ çocuğunun talebini ve yanıtını görür.
Yazar, hedef öğrencilerin yanıtını adlarıyla görür (kimin yanıtlamadığını takip için); başka kimse göremez.
"""

import sqlite3

import yetki
import zaman

BASLIK_AZAMI = 120
ACIKLAMA_AZAMI = 2000
YANITLAR = {"evet": "Onaylıyorum", "hayir": "Onaylamıyorum"}


class OnayHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def _bugun() -> str:
    return zaman.simdi().strftime("%Y-%m-%d")


def olustur(conn: sqlite3.Connection, k: sqlite3.Row, baslik: str, aciklama: str, hedef_tur: str, hedef: str | None, son_tarih: str) -> int:
    baslik, aciklama = (baslik or "").strip(), (aciklama or "").strip()
    if not baslik:
        raise OnayHatasi("Başlık boş olamaz.")
    if len(baslik) > BASLIK_AZAMI or len(aciklama) > ACIKLAMA_AZAMI:
        raise OnayHatasi("Başlık ya da açıklama çok uzun.")
    if len(son_tarih or "") != 10 or son_tarih < _bugun():
        raise OnayHatasi("Son tarih bugün ya da sonrası olmalı.")
    siniflar = yetki.kullanici_siniflari(conn, k)  # None = tüm okul (yönetici)
    if hedef_tur == "okul":
        if siniflar is not None:
            raise OnayHatasi("Tüm okula yalnızca yönetici onay isteyebilir.", 404)
        hedef = None
    elif hedef_tur == "sinif":
        var = conn.execute("SELECT 1 FROM ogrenci WHERE sinif = ? LIMIT 1", (hedef,)).fetchone() if hedef else None
        if not var or (siniflar is not None and hedef not in siniflar):
            raise OnayHatasi("Bu sınıf için onay isteyemezsiniz.", 404)
    else:
        raise OnayHatasi("Geçersiz hedef.")
    cur = conn.execute(
        "INSERT INTO onay_talep (yazar_id, baslik, aciklama, hedef_tur, hedef, son_tarih, olusturma) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (k["id"], baslik, aciklama, hedef_tur, hedef, son_tarih, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def cocuk_talepleri(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> list[dict]:
    """Çocuğa yönelik talepler + velinin yanıtı. Önce bekleyenler (son tarihi yakın olan önce), sonra yanıtlananlar/kapananlar."""
    bugun = _bugun()
    sonuc = []
    for r in conn.execute(
        "SELECT t.*, u.ad_soyad AS yazar, y.yanit FROM onay_talep t JOIN kullanici u ON u.id = t.yazar_id"
        " LEFT JOIN onay_yanit y ON y.talep_id = t.id AND y.ogrenci_id = ?"
        " WHERE t.hedef_tur = 'okul' OR (t.hedef_tur = 'sinif' AND t.hedef = ?)",
        (ogrenci["id"], ogrenci["sinif"]),
    ):
        d = dict(r)
        d["acik"] = d["son_tarih"] >= bugun
        d["bekliyor"] = d["acik"] and d["yanit"] is None
        sonuc.append(d)
    sonuc.sort(key=lambda d: (not d["bekliyor"], not d["acik"], d["son_tarih"] if d["acik"] else _ters(d["son_tarih"])))
    return sonuc


def _ters(tarih: str) -> str:
    return "".join(chr(255 - ord(c)) for c in tarih)  # kapanmışlar yeniden eskiye


def bekleyenler(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> list[dict]:
    return [d for d in cocuk_talepleri(conn, ogrenci) if d["bekliyor"]]


def yanitla(conn: sqlite3.Connection, veli: sqlite3.Row, ogr_id: int, talep_id: int, yanit: str) -> None:
    cocuk = next((c for c in yetki.veli_cocuklari(conn, veli["id"]) if c["id"] == ogr_id), None)
    if cocuk is None:
        raise OnayHatasi("Bulunamadı.", 404)
    talep = next((t for t in cocuk_talepleri(conn, cocuk) if t["id"] == talep_id), None)
    if talep is None:
        raise OnayHatasi("Bulunamadı.", 404)
    if yanit not in YANITLAR:
        raise OnayHatasi("Geçersiz yanıt.")
    if not talep["acik"]:
        raise OnayHatasi("Bu belgenin yanıt süresi dolmuş.", 410)
    conn.execute(
        "INSERT INTO onay_yanit (talep_id, ogrenci_id, veli_id, yanit, zaman) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(talep_id, ogrenci_id) DO UPDATE SET yanit = excluded.yanit, veli_id = excluded.veli_id, zaman = excluded.zaman",
        (talep_id, ogr_id, veli["id"], yanit, zaman.simdi_str()),
    )
    conn.commit()


def getir(conn: sqlite3.Connection, k: sqlite3.Row, talep_id: int) -> sqlite3.Row | None:
    """Yazarın kendi talebi (yönetici hepsini görür)."""
    t = conn.execute("SELECT t.*, u.ad_soyad AS yazar FROM onay_talep t JOIN kullanici u ON u.id = t.yazar_id WHERE t.id = ?", (talep_id,)).fetchone()
    if t is None or (k["rol"] != "yonetici" and t["yazar_id"] != k["id"]):
        return None
    return t


def sonuc(conn: sqlite3.Connection, talep: sqlite3.Row) -> dict:
    sql = (
        "SELECT g.id, g.okul_no, g.ad_soyad, g.sinif, y.yanit FROM ogrenci g"
        " LEFT JOIN onay_yanit y ON y.talep_id = ? AND y.ogrenci_id = g.id"
    )
    par: list = [talep["id"]]
    if talep["hedef_tur"] == "sinif":
        sql += " WHERE g.sinif = ?"
        par.append(talep["hedef"])
    satirlar = conn.execute(sql + " ORDER BY g.sinif, g.okul_no", par).fetchall()
    return {
        "satirlar": satirlar,
        "evet": sum(1 for s in satirlar if s["yanit"] == "evet"),
        "hayir": sum(1 for s in satirlar if s["yanit"] == "hayir"),
        "bekleyen": sum(1 for s in satirlar if s["yanit"] is None),
    }


def listele(conn: sqlite3.Connection, k: sqlite3.Row, limit: int = 50) -> list[dict]:
    kosul, par = ("", []) if k["rol"] == "yonetici" else ("WHERE t.yazar_id = ?", [k["id"]])
    sonuc_listesi = []
    for t in conn.execute(
        f"SELECT t.*, u.ad_soyad AS yazar FROM onay_talep t JOIN kullanici u ON u.id = t.yazar_id {kosul} ORDER BY t.id DESC LIMIT ?",
        [*par, limit],
    ):
        d = dict(t)
        d.update({k_: v for k_, v in sonuc(conn, t).items() if k_ != "satirlar"})
        sonuc_listesi.append(d)
    return sonuc_listesi
