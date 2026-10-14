"""Velilerden modeme gelen SMS'ler -> `veli_mesajlari` tablosu (saf mantık + poller).

Akış (sms_gonderici.gelen_kutusunu_isle ile): gelen kutusunu oku -> DB'ye
INSERT OR IGNORE + commit -> satırın DB'de olduğunu doğrula -> ANCAK SONRA
modemden sil. Hata olursa mesaj modemde kalır (kayıp yok). Çoklu worker'da
mükerrer yazımı UNIQUE(telefon, modem_zaman, metin) engeller.
Gizlilik: log'a mesaj metni / telefon numarası YAZILMAZ, yalnızca sayılar.
Otomatik hiçbir kişi silinmez/engellenmez; çıkış talebi yalnızca işaretlenir.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone

import db
import gonderim
import sms_gonderici

log = logging.getLogger("smssistemi.veli_mesaj")

POLL_SANIYE = 60
BILDIRIM_AZAMI_DENEME = 3
BILDIRIM_TOPLU_LIMIT = 20
BILDIRIM_METIN_AZAMI = 100
BILDIRIM_TOPLAM_AZAMI = 300

# Türkçe karakterden bağımsız karşılaştırılır (ASCII yazılmış SMS'ler de yakalanır).
CIKIS_ANAHTARLARI = (
    "çıkar", "istemiyorum", "istemiyoruz", "durdur", "iptal",
    "gönderm", "rahatsız", "listeden", "abonelik", "stop",
)

_ASCII_KATLA = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def tr_kucuk(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("I", "ı").replace("İ", "i").lower()


def _katla(s: str | None) -> str:
    return tr_kucuk(s).translate(_ASCII_KATLA)


_CIKIS_KATLANMIS = tuple(_katla(a) for a in CIKIS_ANAHTARLARI)


def cikis_talebi_mi(metin: str | None) -> bool:
    m = _katla(metin)
    return any(a in m for a in _CIKIS_KATLANMIS)


def ulusal(telefon: str) -> str:
    """+905XXXXXXXXX / 905... / 05... biçimlerini tek biçime (05XXXXXXXXX) indirger;
    10 haneden kısaysa normalize hâliyle bırakır."""
    t = gonderim.normalize_phone(telefon or "")
    rakam = "".join(c for c in t if c.isdigit())
    return "0" + rakam[-10:] if len(rakam) >= 10 else t


def son4(telefon: str) -> str:
    rakam = "".join(c for c in telefon if c.isdigit())
    return rakam[-4:]


def telefon_maskele(telefon: str) -> str:
    return "*******" + son4(telefon)


def rehber_eslestir(conn, telefon: str) -> dict:
    """Normalize numarayı rehberdeki kisiler.telefon ile eşler.
    Dönen: {kisi_id, kisi_ad, kisi_tur, sinif} (eşleşme yoksa hepsi None)."""
    bos = {"kisi_id": None, "kisi_ad": None, "kisi_tur": None, "sinif": None}
    satirlar = conn.execute(
        "SELECT k.id, k.ad_soyad, k.telefon, k.tur, s.ad AS sinif, o.ad_soyad AS ogrenci_ad "
        "FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
        "LEFT JOIN kisiler o ON o.id = k.ogrenci_kisi_id "
        "WHERE k.telefon IS NOT NULL AND k.telefon != '' ORDER BY k.id"
    ).fetchall()
    eslesen = [r for r in satirlar if ulusal(r["telefon"]) == telefon]
    if not eslesen:
        return bos
    ilk = eslesen[0]
    ad = ilk["ad_soyad"]
    if ilk["tur"] == "veli":
        ogrenciler = []
        for r in eslesen:
            if r["tur"] == "veli" and r["ogrenci_ad"] and r["ogrenci_ad"] not in ogrenciler:
                ogrenciler.append(r["ogrenci_ad"])
        if ogrenciler:
            ad = f"{ad} (veli — {', '.join(ogrenciler)})"
    return {"kisi_id": ilk["id"], "kisi_ad": ad, "kisi_tur": ilk["tur"], "sinif": ilk["sinif"]}


def mesajlari_kaydet(conn, ham_mesajlar: list[dict], yonetim_telefonlari: set[str]) -> list[int]:
    """Ham modem mesajlarını DB'ye yazar, commit eder, DB'de olduğunu doğrular.
    Dönen: DB'de doğrulanmış mesajların modem Index'leri (silinebilir olanlar).
    Teslim raporları (SmsType 7/8) ve numarasız/boş mesajlar atlanır, modemde kalır."""
    yonetim_telefonlari = {ulusal(t) for t in yonetim_telefonlari}
    yazilacak = []
    for m in ham_mesajlar:
        try:
            index = int(m.get("Index"))
        except (TypeError, ValueError):
            continue
        if str(m.get("SmsType", "")) in ("7", "8"):
            continue
        ham_tel = str(m.get("Phone") or "").strip()
        telefon = ulusal(ham_tel)
        if not telefon and ham_tel:
            telefon = ham_tel[:20]  # alfanümerik gönderen (ör. firma adı): spam kuralı (a) yakalar
        metin = str(m.get("Content") or "")
        if not telefon or not metin:
            continue
        zaman = str(m.get("Date") or "") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        yazilacak.append((index, telefon, metin, zaman))

    engelliler = {r["telefon"] for r in conn.execute("SELECT telefon FROM engelli_gonderenler")}
    for _index, telefon, metin, zaman in yazilacak:
        e = rehber_eslestir(conn, telefon)
        spam, spam_neden = 0, None
        if telefon not in yonetim_telefonlari:  # idare numaraları ASLA spam olmaz
            if telefon in engelliler:
                spam, spam_neden = 1, "engelli"
            elif e["kisi_id"] is None and not gonderim.is_valid_phone(telefon):
                spam, spam_neden = 1, "sistem numarası"
        conn.execute(
            "INSERT OR IGNORE INTO veli_mesajlari "
            "(telefon, metin, modem_zaman, kisi_id, kisi_ad, kisi_tur, sinif, cikis_talebi, bildirim_durum, "
            "okundu, spam, spam_neden) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                telefon, metin, zaman, e["kisi_id"], e["kisi_ad"], e["kisi_tur"], e["sinif"],
                1 if cikis_talebi_mi(metin) else 0,
                # idare numarası ve spam: bildirim döngüsünü engelle
                2 if (telefon in yonetim_telefonlari or spam) else 0,
                1 if spam else 0, spam, spam_neden,
            ),
        )
    conn.commit()

    dogrulanan = []
    for index, telefon, metin, zaman in yazilacak:
        var = conn.execute(
            "SELECT 1 FROM veli_mesajlari WHERE telefon = ? AND modem_zaman = ? AND metin = ?",
            (telefon, zaman, metin),
        ).fetchone()
        if var:
            dogrulanan.append(index)
    return dogrulanan


SPAM_SAKLAMA_GUN = 7


def spam_temizle(conn) -> int:
    """7 günden eski spam satırlarını siler (alinma UTC). Dönen: silinen sayısı."""
    cur = conn.execute(
        "DELETE FROM veli_mesajlari WHERE spam = 1 AND alinma < datetime('now', ?)",
        (f"-{SPAM_SAKLAMA_GUN} days",),
    )
    conn.commit()
    return cur.rowcount


def bildirim_metni(satirlar: list[dict]) -> str:
    """Tek özet SMS: 'Veli mesajı: <ad veya numara son 4>: <metin ≤100 kr>' (+N yeni mesaj)."""
    ilk = satirlar[0]
    etiket = (ilk.get("kisi_ad") or f"numara {son4(ilk['telefon'])}")[:60]
    metin = " ".join(str(ilk["metin"]).split())[:BILDIRIM_METIN_AZAMI]
    sonuc = f"Veli mesajı: {etiket}: {metin}"
    if len(satirlar) > 1:
        sonuc += f" +{len(satirlar) - 1} yeni mesaj"
    return sonuc[:BILDIRIM_TOPLAM_AZAMI]


def bildirim_gonder(conn, ayarlar: dict, yonetim: list[tuple[str, str]]) -> int:
    """bildirim_durum=0 satırlar için idareye TEK özet SMS. Dönen: işlenen satır sayısı.
    Modem kilidi alınamazsa tur atlanır (0)."""
    if not yonetim:
        return 0
    satirlar = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM veli_mesajlari WHERE bildirim_durum = 0 ORDER BY id LIMIT ?",
            (BILDIRIM_TOPLU_LIMIT,),
        ).fetchall()
    ]
    if not satirlar:
        return 0
    if not sms_gonderici.modem_kilidi.acquire(blocking=False):
        return 0
    try:
        metin = bildirim_metni(satirlar)
        gid = "vm_" + uuid.uuid4().hex[:9]
        sonuclar: list[str] = []

        def cb(isim, telefon, mesaj, durum, hata):
            db.gonderim_kaydet(conn, gid, isim, telefon, mesaj, durum, hata)
            sonuclar.append(durum)

        try:
            sms_gonderici.toplu_gonder(
                ayarlar, [(ad, tel, metin) for ad, tel in yonetim], cb, threading.Event(), 2.0
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("bildirim gönderimi hata verdi (%s)", type(exc).__name__)
    finally:
        sms_gonderici.modem_kilidi.release()

    ids = [s["id"] for s in satirlar]
    marka = ",".join("?" * len(ids))
    if "gonderildi" in sonuclar:
        conn.execute(f"UPDATE veli_mesajlari SET bildirim_durum = 1 WHERE id IN ({marka})", ids)
    else:
        conn.execute(
            f"UPDATE veli_mesajlari SET bildirim_deneme = bildirim_deneme + 1 WHERE id IN ({marka})", ids
        )
        conn.execute(
            f"UPDATE veli_mesajlari SET bildirim_durum = 2 WHERE id IN ({marka}) AND bildirim_deneme >= ?",
            ids + [BILDIRIM_AZAMI_DENEME],
        )
    conn.commit()
    return len(ids)


def tur_calistir() -> dict:
    """Tek poller turu (senkron). Dönen: sadece sayılar."""
    import arac_api  # geç içe aktarma: döngüsel bağımlılık riskini önler

    ozet = {"silinen": None, "bildirilen": 0}
    yonetim = arac_api.yonetim_alicilari()
    yonetim_tel = {ulusal(tel) for _ad, tel in yonetim}
    ayarlar = sms_gonderici.modem_ayarlarini_yukle()

    def isleyici(mesajlar: list[dict]) -> list[int]:
        conn = db.baglanti()
        try:
            return mesajlari_kaydet(conn, mesajlar, yonetim_tel)
        finally:
            conn.close()

    ozet["silinen"] = sms_gonderici.gelen_kutusunu_isle(ayarlar, isleyici)
    conn = db.baglanti()
    try:
        spam_temizle(conn)
        ozet["bildirilen"] = bildirim_gonder(conn, ayarlar, yonetim)
    finally:
        conn.close()
    return ozet


async def gelen_kutusu_dongusu() -> None:
    log.info("Veli mesajı poller'ı başlatıldı (%d sn).", POLL_SANIYE)
    while True:
        try:
            await asyncio.sleep(POLL_SANIYE)
            ozet = await asyncio.to_thread(tur_calistir)
            if ozet["silinen"] or ozet["bildirilen"]:
                log.info("veli mesajı turu: silinen=%s bildirilen=%s", ozet["silinen"], ozet["bildirilen"])
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 - mesaj/numara sızdırmamak için yalnızca tür
            log.warning("veli mesajı turu başarısız (%s)", type(exc).__name__)
