"""Öğretmenin soru havuzuna katkısı (V41).

1) Cevap anahtarlı çoktan seçmeli PDF: öğretmen yükler → `soru_katki` kuyruğu → soruhavuzu `katki` turu
   (2 dakikada bir) soruları ayırır, anahtarla eşler, havuza 'onayli' yazar ve sonucu buraya bildirir.
2) LLM ile şıklandırılmış açık uçlu sorular havuzda 'askida' bekler; o dersin öğretmeni onaylar/reddeder.
   Karar `soru_katki_karar`'a yazılır, havuza soruhavuzu uygular (okul havuza yazmaz).
"""

import re
import sqlite3
from datetime import timedelta

import dosyalar
import inceleme
import zaman
from kaynaklar import soru as havuz

AZAMI_BASLIK = 120
ZAMAN_ASIMI_DK = 30  # 'isleniyor' bu kadar takılı kalırsa yeniden sıraya girer
YONETICI_SEVIYELER = (9, 10, 11, 12)
_CIFT = re.compile(r"(\d{1,3})\s*[-.):]?\s*([A-Ea-e])(?![A-Za-zçğıöşüÇĞİÖŞÜ])")


class KatkiHatasi(ValueError):
    pass


def cevap_coz(metin: str) -> str:
    """'1-A 2-C …', '1.A', '1) a' ya da 'ACBD…' → 'ACBD…'. Boş → '' (anahtar PDF'in içinde aranır)."""
    metin = (metin or "").strip()
    if not metin:
        return ""
    if not re.search(r"\d", metin):
        harfler = re.sub(r"[\s,;.\-]", "", metin).upper()
        if not re.fullmatch(r"[A-E]+", harfler):
            raise KatkiHatasi("Cevap anahtarında yalnızca A-E harfleri olmalı.")
        return harfler
    ciftler = _CIFT.findall(metin)
    kalan = _CIFT.sub("", metin)
    if re.search(r"[0-9A-Za-z]", kalan):
        raise KatkiHatasi("Cevap anahtarı okunamadı. Örnek biçim: 1-A 2-C 3-B")
    nolar = [int(n) for n, _ in ciftler]
    if sorted(nolar) != list(range(1, len(nolar) + 1)):
        raise KatkiHatasi("Cevap anahtarında soru numaraları 1'den başlayıp eksiksiz sıralı olmalı.")
    return "".join(h.upper() for _, h in sorted(ciftler, key=lambda c: int(c[0])))


def secenekler(conn: sqlite3.Connection, k: sqlite3.Row) -> list[tuple[int, str]]:
    """Yükleme için (sınıf seviyesi, havuz dersi) seçenekleri: öğretmene kendi dersleri, yöneticiye hepsi."""
    if k["rol"] == "yonetici":
        return [(s, d) for s in YONETICI_SEVIYELER for d in sorted(havuz.GORUNEN_AD)]
    return inceleme.ciftler(conn, k["id"])


def gonder(conn, k, sinif: int, ders: str, baslik: str, dosya_adi: str, veri: bytes, cevap: str) -> int:
    if (sinif, ders) not in secenekler(conn, k):
        raise PermissionError
    anahtar = cevap_coz(cevap)
    ad = (dosya_adi or "sorular.pdf").replace("\\", "/").rsplit("/", 1)[-1][:150]
    baslik = (baslik.strip() or ad.rsplit(".", 1)[0])[:AZAMI_BASLIK]
    yeni = dosyalar.pdf_kaydet(veri)
    cur = conn.execute(
        "INSERT INTO soru_katki (ogretmen_id, sinif, ders, baslik, dosya_adi, depo_adi, cevap, zaman)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (k["id"], sinif, ders, baslik, ad, yeni.depo_adi, anahtar, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def katkilarim(conn, k) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM soru_katki WHERE ogretmen_id = ? ORDER BY id DESC LIMIT 50", (k["id"],)
    ).fetchall()


def getir(conn, katki_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM soru_katki WHERE id = ?", (katki_id,)).fetchone()


def bekleyenler(conn) -> list[dict]:
    """soruhavuzu turu için: sıradakiler + 30 dk'dan uzun 'isleniyor' kalanlar (kişi bilgisi yok)."""
    sinir = (zaman.simdi() - timedelta(minutes=ZAMAN_ASIMI_DK)).strftime(zaman.BICIM)
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, sinif, ders, baslik, cevap FROM soru_katki WHERE durum = 'bekliyor'"
            " OR (durum = 'isleniyor' AND islem_zaman < ?) ORDER BY id",
            (sinir,),
        )
    ]


def sonuc(conn, katki_id: int, durum: str, eklenen: int = 0, not_: str = "") -> bool:
    if durum not in ("isleniyor", "bitti", "hata"):
        raise KatkiHatasi("Geçersiz durum.")
    cur = conn.execute(
        "UPDATE soru_katki SET durum = ?, eklenen = ?, not_metni = ?, islem_zaman = ? WHERE id = ?",
        (durum, int(eklenen), (not_ or "")[:300], zaman.simdi_str(), katki_id),
    )
    conn.commit()
    return cur.rowcount == 1


def onay_bekleyenler(conn, k) -> list[dict]:
    """Öğretmenin derslerindeki, henüz karar verilmemiş 'askida' katkı soruları; havuz kapalıysa []."""
    ciftler = secenekler(conn, k)
    if not ciftler:
        return []
    karar = {r[0] for r in conn.execute("SELECT soru_id FROM soru_katki_karar")}
    try:
        sorular = havuz.onay_bekleyenler(ciftler)
    except havuz.KaynakHatasi:
        return []
    return [s for s in sorular if s["id"] not in karar]


def karar_ver(conn, k, soru_id: int, karar: str) -> None:
    if karar not in ("onay", "red"):
        raise KatkiHatasi("Geçersiz karar.")
    if soru_id not in {s["id"] for s in onay_bekleyenler(conn, k)}:
        raise PermissionError
    conn.execute(
        "INSERT OR IGNORE INTO soru_katki_karar (soru_id, ogretmen_id, karar, zaman) VALUES (?, ?, ?, ?)",
        (soru_id, k["id"], karar, zaman.simdi_str()),
    )
    conn.commit()


def uygulanacak_kararlar(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT soru_id, karar FROM soru_katki_karar WHERE uygulandi IS NULL")]


def kararlar_uygulandi(conn, idler: list[int]) -> int:
    cur = conn.executemany(
        "UPDATE soru_katki_karar SET uygulandi = ? WHERE soru_id = ? AND uygulandi IS NULL",
        [(zaman.simdi_str(), int(i)) for i in idler],
    )
    conn.commit()
    return cur.rowcount
