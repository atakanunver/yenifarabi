"""Veli izin talebi: veli çocuğu için devamsızlık izni ister, yönetici onaylar/reddeder.

- Gün sayısı sunucuda hesaplanır: iş günü (hafta sonu + config/takvim.json tatilleri hariç, kaynaklar.zil.tatil_adi).
- 20 gün özürlü hakkı = öğretim yılındaki ONAYLI taleplerin gün toplamı; aşım yalnız uyarıdır, engel değildir.
- Bildirimler (SMS, push, Telegram) arka planda; hiçbiri talebi/onayı bozmaz. Push ve Telegram SABİT metin (ad/neden yok).
"""

import logging
import sqlite3
from datetime import date, timedelta

import db
import dosyalar
import izin_pdf
import push
import zaman
from ayarlar import AYAR
from kaynaklar import sms, telegram
from kaynaklar import zil as zil_kaynak

log = logging.getLogger("okul.izin")

# kod -> (seçenek adı, dilekçe cümlesindeki biçim)
NEDENLER = {
    "saglik": ("Sağlık durumu", "sağlık durumu"),
    "ailevi": ("Ailevi mazeret", "ailevi mazeret"),
    "vefat": ("Vefat", "vefat"),
    "resmi": ("Resmî işlem", "resmî işlem"),
    "diger": ("Diğer", ""),
}
DURUMLAR = {"bekliyor": "Bekliyor", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}
METIN_AZAMI = 300
ARALIK_AZAMI = 30  # takvim günü
SAAT_AZAMI = 3  # veli başına saatte en çok talep
OZURLU_HAK = 20
EK_KLASOR = "izin"


class IzinHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def tarih_coz(s: str) -> date:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        raise IzinHatasi("Geçerli bir tarih seçin.") from None


def is_gunu(bas: date, bit: date) -> int:
    """bas..bit (dahil) arasındaki okul günü sayısı."""
    n, g = 0, bas
    while g <= bit:
        if zil_kaynak.tatil_adi(g) is None:
            n += 1
        g += timedelta(days=1)
    return n


def _gs(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def ogretim_yili(t: date) -> tuple[str, str]:
    """1 Eylül – 31 Ağustos."""
    y = t.year if t.month >= 9 else t.year - 1
    return f"{y}-09-01", f"{y + 1}-08-31"


def kullanilan_gun(conn: sqlite3.Connection, ogrenci_id: int, t: date | None = None) -> int:
    bas, bit = ogretim_yili(t or zaman.simdi().date())
    return conn.execute(
        "SELECT COALESCE(SUM(gun), 0) FROM izin_talep WHERE ogrenci_id = ? AND durum = 'onaylandi'"
        " AND baslangic BETWEEN ? AND ?",
        (ogrenci_id, bas, bit),
    ).fetchone()[0]


def hak_ozeti(conn: sqlite3.Connection, ogrenci_id: int, t: date | None = None, ek: int = 0) -> dict:
    """ek: henüz onaylanmamış talebin günü (yönetici detayında 'onaylanırsa' görünümü için)."""
    kullanilan = kullanilan_gun(conn, ogrenci_id, t)
    return {
        "hak": OZURLU_HAK,
        "kullanilan": kullanilan,
        "kalan": max(OZURLU_HAK - kullanilan, 0),
        "asim": kullanilan + ek > OZURLU_HAK,
        "ek": ek,
    }


def mazeret_metni(neden_tur: str, neden_metin: str) -> str:
    if neden_tur == "diger":
        return neden_metin
    dilekce = NEDENLER[neden_tur][1]
    return f"{dilekce} ({neden_metin})" if neden_metin else dilekce


def _pdf_alanlari(t: dict) -> dict:
    bugun = t["olusturma"][:10]
    if t["bitis"] < bugun:
        fiil = "edememiştir"
    elif t["baslangic"] > bugun:
        fiil = "edemeyecektir"
    else:
        fiil = "edememiştir/edemeyecektir"
    return {
        "okul_adi": AYAR.okul_adi,
        "sinif": t["sinif"],
        "okul_no": t["okul_no"],
        "ogrenci": t["ogrenci_ad"],
        "baslangic": _gs(t["baslangic"]),
        "bitis": _gs(t["bitis"]),
        "gun": t["gun"],
        "mazeret": mazeret_metni(t["neden_tur"], t["neden_metin"]),
        "fiil": fiil,
        "tarih": _gs(bugun),
        "veli": t["veli_ad"],
        "telefon": t["veli_telefon"] or "",
        "ek_var": bool(t["ek_depo"]),
    }


def olustur(
    conn: sqlite3.Connection,
    veli_id: int,
    ogrenci_id: int,
    baslangic: str,
    bitis: str,
    neden_tur: str,
    neden_metin: str,
    ek_veri: bytes | None = None,
) -> int:
    """Sahiplik (veli_ogrenci) çağıranda doğrulanmış olmalı; yine de burada tekrar bakılır (404)."""
    if not conn.execute(
        "SELECT 1 FROM veli_ogrenci WHERE veli_id = ? AND ogrenci_id = ?", (veli_id, ogrenci_id)
    ).fetchone():
        raise IzinHatasi("Bulunamadı.", 404)
    bas, bit = tarih_coz(baslangic), tarih_coz(bitis)
    if bas > bit:
        raise IzinHatasi("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
    if (bit - bas).days + 1 > ARALIK_AZAMI:
        raise IzinHatasi(f"Tek talepte en çok {ARALIK_AZAMI} günlük aralık seçilebilir.")
    if neden_tur not in NEDENLER:
        raise IzinHatasi("Bir mazeret seçin.")
    metin = " ".join((neden_metin or "").split())
    if len(metin) > METIN_AZAMI:
        raise IzinHatasi(f"Açıklama en çok {METIN_AZAMI} karakter olabilir.")
    if neden_tur == "diger" and not metin:
        raise IzinHatasi("'Diğer' seçildiğinde mazereti yazmalısınız.")
    gun = is_gunu(bas, bit)
    if gun == 0:
        raise IzinHatasi("Seçilen tarihlerde okul günü yok (hafta sonu ya da tatil).")
    saat_once = (zaman.simdi() - timedelta(hours=1)).strftime(zaman.BICIM)
    if conn.execute(
        "SELECT COUNT(*) FROM izin_talep WHERE veli_id = ? AND olusturma >= ?", (veli_id, saat_once)
    ).fetchone()[0] >= SAAT_AZAMI:
        raise IzinHatasi("Bir saatte en çok 3 talep gönderebilirsiniz; biraz sonra tekrar deneyin.", 429)
    ek = None
    if ek_veri:
        try:
            ek = dosyalar.izin_eki_kaydet(ek_veri)
        except dosyalar.DosyaHatasi as e:
            raise IzinHatasi(str(e)) from None
    cur = conn.execute(
        "INSERT INTO izin_talep (veli_id, ogrenci_id, baslangic, bitis, gun, neden_tur, neden_metin, ek_depo, ek_tur,"
        " olusturma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            veli_id, ogrenci_id, bas.isoformat(), bit.isoformat(), gun, neden_tur, metin,
            ek.depo_adi if ek else None, ek.tur if ek else None, zaman.simdi_str(),
        ),
    )
    talep_id = cur.lastrowid
    conn.commit()
    try:
        veri = izin_pdf.uret(_pdf_alanlari(detay(conn, talep_id)))
        if veri:
            pdf = dosyalar.izin_pdf_kaydet(veri)
            conn.execute("UPDATE izin_talep SET pdf_depo = ? WHERE id = ?", (pdf.depo_adi, talep_id))
            conn.commit()
    except Exception as e:  # noqa: BLE001 — PDF olmasa da talep geçerli
        log.warning("izin PDF'i üretilemedi: %s", type(e).__name__)
    return talep_id


_SECIM = (
    "SELECT t.*, o.ad_soyad AS ogrenci_ad, o.sinif, o.okul_no, v.ad_soyad AS veli_ad, v.telefon AS veli_telefon,"
    " y.ad_soyad AS karar_veren_ad"
    " FROM izin_talep t JOIN ogrenci o ON o.id = t.ogrenci_id JOIN kullanici v ON v.id = t.veli_id"
    " LEFT JOIN kullanici y ON y.id = t.karar_veren"
)


def _kayit(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["neden_ad"] = NEDENLER[d["neden_tur"]][0]
    d["mazeret"] = mazeret_metni(d["neden_tur"], d["neden_metin"])
    d["durum_ad"] = DURUMLAR[d["durum"]]
    d["baslangic_g"], d["bitis_g"] = _gs(d["baslangic"]), _gs(d["bitis"])
    return d


def detay(conn: sqlite3.Connection, talep_id: int) -> dict | None:
    r = conn.execute(_SECIM + " WHERE t.id = ?", (talep_id,)).fetchone()
    return _kayit(r) if r else None


def veli_detay(conn: sqlite3.Connection, veli_id: int, talep_id: int) -> dict | None:
    """Yalnız velinin KENDİ talebi (başka velinin talebi None → 404)."""
    d = detay(conn, talep_id)
    return d if d and d["veli_id"] == veli_id else None


def veli_talepleri(conn: sqlite3.Connection, veli_id: int, ogrenci_id: int) -> list[dict]:
    return [
        _kayit(r)
        for r in conn.execute(
            _SECIM + " WHERE t.veli_id = ? AND t.ogrenci_id = ? ORDER BY t.id DESC LIMIT 50", (veli_id, ogrenci_id)
        )
    ]


def liste(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Yönetici listesi: bekleyen önce, sonra en yeni."""
    return [
        _kayit(r)
        for r in conn.execute(_SECIM + " ORDER BY (t.durum = 'bekliyor') DESC, t.id DESC LIMIT ?", (limit,))
    ]


def bekleyen_sayisi(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM izin_talep WHERE durum = 'bekliyor'").fetchone()[0]


def karar_ver(conn: sqlite3.Connection, talep_id: int, yonetici_id: int, onay: bool) -> dict:
    """Yalnız bekleyen talep karara bağlanır (çift tıklamada ikinci SMS gitmesin)."""
    d = detay(conn, talep_id)
    if d is None:
        raise IzinHatasi("Bulunamadı.", 404)
    if d["durum"] != "bekliyor":
        raise IzinHatasi("Bu talep zaten yanıtlandı.", 409)
    conn.execute(
        "UPDATE izin_talep SET durum = ?, karar_veren = ?, karar_zamani = ? WHERE id = ? AND durum = 'bekliyor'",
        ("onaylandi" if onay else "reddedildi", yonetici_id, zaman.simdi_str(), talep_id),
    )
    conn.commit()
    return detay(conn, talep_id)


def sil(conn: sqlite3.Connection, talep_id: int) -> dict:
    """Yönetici kaydı kalıcı siler (ör. mükerrer talep; onaylıysa 20 gün hakkından düşer). Ek ve PDF de silinir."""
    d = detay(conn, talep_id)
    if d is None:
        raise IzinHatasi("Bulunamadı.", 404)
    conn.execute("DELETE FROM izin_talep WHERE id = ?", (talep_id,))
    conn.commit()
    dosyalar.sil(EK_KLASOR, d["ek_depo"])
    dosyalar.sil(EK_KLASOR, d["pdf_depo"])
    return d


def onayli_siniflar(conn: sqlite3.Connection, tarih: str) -> dict[str, list[str]]:
    """O gün onaylı izinli öğrencilerin okul numaraları, sınıfa göre."""
    sonuc: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT DISTINCT o.sinif, o.okul_no FROM izin_talep t JOIN ogrenci o ON o.id = t.ogrenci_id"
        " WHERE t.durum = 'onaylandi' AND t.baslangic <= ? AND t.bitis >= ? ORDER BY o.sinif, o.okul_no",
        (tarih, tarih),
    ):
        sonuc.setdefault(r["sinif"], []).append(str(r["okul_no"]))
    return sonuc


# --- Bildirim metinleri + arka plan görevleri ---


def talep_sms_metni(d: dict) -> str:
    return (
        f"Veli izin talebi: {d['veli_ad']}, {d['ogrenci_ad']} ({d['sinif']}), {d['baslangic_g']}-{d['bitis_g']}"
        f" {d['gun']} gün, neden: {d['mazeret']}"
    )[: sms.BILDIRIM_AZAMI]


def telegram_metni(d: dict) -> str:
    """SABİT metin: yalnız sınıf (Telegram bulut; ad/neden gitmez)."""
    return f"📋 Veli izin talebi: yeni talep ({d['sinif']}). Ayrıntı: Dijital Okul > Veli izin talepleri"


def onay_sms_metni(d: dict) -> str:
    return (
        f"Sayın veli, {d['ogrenci_ad']} için {d['baslangic_g']}-{d['bitis_g']} izin talebiniz onaylanmıştır."
        f" {AYAR.okul_adi}"
    ).strip()[: sms.BILDIRIM_AZAMI]


def _guvenli(ad: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 — bildirim asıl işlemi bozmaz
        log.warning("izin bildirimi (%s) gönderilemedi: %s", ad, type(e).__name__)


def _talep_oku(talep_id: int) -> dict | None:
    conn = db.baglanti()
    try:
        return detay(conn, talep_id)
    finally:
        conn.close()


def talep_bildir(talep_id: int) -> None:
    """BackgroundTasks: personel SMS'i + yönetici push'u + Telegram. Asla istisna fırlatmaz."""
    try:
        d = _talep_oku(talep_id)
    except Exception as e:  # noqa: BLE001
        log.warning("izin talebi okunamadı: %s", type(e).__name__)
        return
    if d is None:
        return
    if AYAR.izin_sms_telefon:
        _guvenli("sms", sms.bildirim_gonder, AYAR.izin_sms_telefon, talep_sms_metni(d))
    _guvenli("push", push.izin_talep_bildir)
    _guvenli("telegram", telegram.gonder, telegram_metni(d))


def sonuc_bildir(talep_id: int) -> None:
    """BackgroundTasks: onayda veliye SMS + push, rette yalnız push."""
    try:
        d = _talep_oku(talep_id)
    except Exception as e:  # noqa: BLE001
        log.warning("izin talebi okunamadı: %s", type(e).__name__)
        return
    if d is None:
        return
    if d["durum"] == "onaylandi" and d["veli_telefon"]:
        _guvenli("sms", sms.bildirim_gonder, d["veli_telefon"], onay_sms_metni(d))
    _guvenli("push", push.izin_sonuc_bildir, d["veli_id"])
