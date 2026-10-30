"""Tahta duyuruları (2026-10-30): panelden yazılan kısa mesaj, tahtada sağ altta
dersi bölmeyen küçük bir pencere olarak görünür (tahtayoklama/announcement_agent.py).

İletim "tahta çeker": tahta_istemci.py birkaç saniyede bir `GET /api/v1/tahta/duyuru`
çağırır (bkz. tahta_api.py). Tahtaya inbound bağlantı ya da yeni bağımlılık yok.
Sesli okuma: idare/acil duyurularında metin yerel EMA Lightning TTS'e (debian:5002)
gönderilir, wav `veri/duyuru_ses/` altında saklanır, tahta indirip çalar. TTS
ulaşılamazsa duyuru sessiz gider (Farabi dersi bozmaz). Mesaj metni log'a YAZILMAZ
(öğrenci adı içerebilir).
"""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import db

TIPLER = ("bilgi", "idare", "acil")
TUM_OKUL = "tum-okul"
MESAJ_MAKS = 300
# Tahtada gösterim süresi (sn); acil = 0: manuel kapanana kadar.
SURE_SN = {"bilgi": 10, "idare": 15, "acil": 0}
# Tahta geç açılırsa eski duyuruyu görmesin: duyurunun geçerlilik süresi (dk).
GECERLILIK_DK = {"bilgi": 10, "idare": 30, "acil": 120}
# Sesli okuma sayısı: idare 1x, acil 3x, bilgi sessiz.
OKUMA_SAYISI = {"bilgi": 0, "idare": 1, "acil": 3}

TTS_URL = "http://debian.local:5002/konus"
TTS_ZAMAN_ASIMI_SN = 20
SES_DIZINI = db.DB_YOLU.parent / "duyuru_ses"
_SES_ADI_RE = re.compile(r"^[0-9]+\.wav$")
_KONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class DuyuruHatasi(ValueError):
    """Kullanıcıya gösterilecek Türkçe doğrulama mesajı."""


def mesaj_temizle(ham) -> str:
    metin = _KONTROL_RE.sub("", str(ham or "")).strip()
    if not metin:
        raise DuyuruHatasi("Duyuru metni boş.")
    if len(metin) > MESAJ_MAKS:
        raise DuyuruHatasi(f"Duyuru en çok {MESAJ_MAKS} karakter olabilir.")
    return metin


def tts_uret(metin: str) -> bytes | None:
    """EMA Lightning'den wav ister; ulaşılamazsa/bozuksa None (duyuru sessiz gider)."""
    istek = urllib.request.Request(
        TTS_URL,
        data=json.dumps({"text": metin, "hiz": 1.0}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(istek, timeout=TTS_ZAMAN_ASIMI_SN) as yanit:
            ses = yanit.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    return ses if ses[:4] == b"RIFF" else None


def olustur(conn, hedefler: list[str], mesaj: str, tip: str, sesli_oku: bool,
            ses: bytes | None) -> list[int]:
    """Her hedef için bir satır yazar; ses dosyası tek (ilk satırın id'siyle), diğer
    satırlar aynı dosyayı gösterir. Dönen: satır id'leri."""
    if tip not in TIPLER:
        raise DuyuruHatasi("Geçersiz duyuru tipi.")
    if not hedefler:
        raise DuyuruHatasi("Hedef yok.")
    sesli = int(bool(sesli_oku) and OKUMA_SAYISI[tip] > 0)
    idler: list[int] = []
    ses_adi = None
    for hedef in hedefler:
        imlec = conn.execute(
            "INSERT INTO duyuru (hedef, mesaj, tip, sesli_oku, bitis) "
            "VALUES (?, ?, ?, ?, datetime('now', ?))",
            (hedef, mesaj, tip, sesli, f"+{GECERLILIK_DK[tip]} minutes"),
        )
        idler.append(imlec.lastrowid)
    if sesli and ses:
        SES_DIZINI.mkdir(parents=True, exist_ok=True)
        ses_adi = f"{idler[0]}.wav"
        (SES_DIZINI / ses_adi).write_bytes(ses)
        conn.executemany("UPDATE duyuru SET ses_dosya = ? WHERE id = ?",
                         [(ses_adi, i) for i in idler])
    conn.commit()
    eskileri_buda(conn)
    return idler


def eskileri_buda(conn) -> None:
    """2 günden eski satırları ve hiçbir satırın göstermediği ses dosyalarını siler."""
    conn.execute("DELETE FROM duyuru WHERE olusturma < datetime('now', '-2 days')")
    conn.commit()
    if not SES_DIZINI.is_dir():
        return
    kullanilan = {r[0] for r in conn.execute(
        "SELECT DISTINCT ses_dosya FROM duyuru WHERE ses_dosya IS NOT NULL")}
    for dosya in SES_DIZINI.iterdir():
        if _SES_ADI_RE.match(dosya.name) and dosya.name not in kullanilan:
            dosya.unlink(missing_ok=True)


def hepsini_iptal_et(conn) -> int:
    imlec = conn.execute("UPDATE duyuru SET iptal = 1 WHERE iptal = 0 AND bitis > datetime('now')")
    conn.commit()
    return imlec.rowcount


# Bir duyuru bu tahtayı hedefler: tum-okul, tahta adı ya da tahtanın atanmış sınıfı.
_HEDEF_SQL = """(
    d.hedef = 'tum-okul' OR d.hedef = :tahta
    OR d.hedef = (SELECT s.ad FROM tahtalar t JOIN siniflar s ON s.id = t.sinif_id
                  WHERE t.ad = :tahta)
)"""


def tahta_icin(conn, tahta: str, son_id: int) -> dict:
    """{"duyurular": [id > son_id, geçerli, iptal olmayan], "iptal": [son 2 saatte iptal edilenler]}"""
    yeni = conn.execute(
        f"SELECT d.id, d.mesaj, d.tip, d.sesli_oku, d.ses_dosya FROM duyuru d "
        f"WHERE d.id > :son AND d.iptal = 0 AND d.bitis > datetime('now') AND {_HEDEF_SQL} "
        f"ORDER BY d.id LIMIT 10",
        {"son": son_id, "tahta": tahta},
    ).fetchall()
    iptal = conn.execute(
        f"SELECT d.id FROM duyuru d WHERE d.iptal = 1 "
        f"AND d.olusturma > datetime('now', '-2 hours') AND {_HEDEF_SQL}",
        {"tahta": tahta},
    ).fetchall()
    return {
        "duyurular": [
            {
                "id": r["id"], "mesaj": r["mesaj"], "tip": r["tip"],
                "sesli_oku": bool(r["sesli_oku"]), "ses": bool(r["ses_dosya"]),
                "sure_sn": SURE_SN[r["tip"]], "okuma_sayisi": OKUMA_SAYISI[r["tip"]],
            }
            for r in yeni
        ],
        "iptal": [r["id"] for r in iptal],
    }


def ses_yolu(conn, tahta: str, duyuru_id: int) -> Path | None:
    """Tahta bu duyurunun hedefindeyse ses dosyasının yolu (yoksa None)."""
    satir = conn.execute(
        f"SELECT d.ses_dosya FROM duyuru d WHERE d.id = :id AND d.ses_dosya IS NOT NULL "
        f"AND {_HEDEF_SQL}",
        {"id": duyuru_id, "tahta": tahta},
    ).fetchone()
    if satir is None or not _SES_ADI_RE.match(satir["ses_dosya"]):
        return None
    yol = SES_DIZINI / satir["ses_dosya"]
    return yol if yol.is_file() else None
