"""Yoklama panosunun (`tahtayoklama/dashboard`, :8010) veritabanından SALT-OKUNUR
devamsızlık okuma — çapraz servis erişiminin TEK noktası.

⚠️ **Bilinçli mimari sapma (2026-09-23).** `CLAUDE.md`'deki "smssistemi ile
tahtayoklama/dashboard arasında kod/DB paylaşımı yok, tek bağ HMAC" kuralının
tek istisnası burasıdır. Alternatif (panoya HMAC imzalı `/api/devamsiz`
endpoint'i eklemek) kullanıcıya sunuldu, doğrudan okuma seçildi — gerekçe ve
geri dönüş yolu `DECISIONS.md` 2026-09-23 kaydında.

Sapmanın yarıçapı bilerek bu dosyaya hapsedilmiştir: panonun şeması bilen tek
modül bu. İleride HTTP+HMAC'e geçilmek istenirse yalnızca `gunun_satirlari`'nın
gövdesi değişir, `yoklama_mantik.py` ve `app.py` aynı kalır.

Bağlantı `mode=ro` ile açılır — bu süreçten panonun verisine yazmak mümkün değil.
"""

import json
import sqlite3
from pathlib import Path

# Panonun kendi `db.py:11`'indeki `DB_YOLU` ile aynı dosya. Sabit mutlak yol:
# iki servis ayrı dizinlerde koşuyor, göreli yol kırılgan olurdu. Testler bunu
# monkeypatch'ler (`db.DB_YOLU` deseninin eşi).
YOKLAMA_DB_YOLU = Path("/home/ata/farabi/tahtayoklama/dashboard/veri/yoklama_pano.db")

# `yoklama_onbellek.durum` değerleri — panonun `admin.py:28-34` listesiyle aynı.
# İsim dizileri YALNIZCA 'alindi' satırlarında anlamlıdır; panonun
# `yoklayici.py:126`'sı diğer tüm durumlarda boş dizi yazar, yani "kimse yok
# değil" ile "yoklama hiç alınmadı" ayırt edilemez. Bu ayrımı `yoklama_mantik`
# yapar, burası ham satırı olduğu gibi taşır.
DURUM_ALINDI = "alindi"


class YoklamaKaynakYok(RuntimeError):
    """Yoklama panosunun veritabanı okunamadı (dosya yok, izin yok, kilitli)."""


def _baglan() -> sqlite3.Connection:
    """Salt-okunur bağlantı. `mode=ro` olmayan bir yol asla açılmaz —
    pano DB'si başka bir servisin sahibi olduğu veridir."""
    if not YOKLAMA_DB_YOLU.exists():
        raise YoklamaKaynakYok(f"Yoklama veritabanı bulunamadı: {YOKLAMA_DB_YOLU}")
    try:
        conn = sqlite3.connect(f"file:{YOKLAMA_DB_YOLU}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise YoklamaKaynakYok(f"Yoklama veritabanı açılamadı: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _json_liste(deger) -> list[str]:
    """`yok_isimleri`/`izinli_isimleri` JSON dizisini listeye çevirir.
    Bozuk/boş değerde boş liste döner — devamsızlık listesi bir JSON hatası
    yüzünden komple çökmemeli."""
    if not deger:
        return []
    try:
        cozulen = json.loads(deger)
    except (ValueError, TypeError):
        return []
    return [str(x) for x in cozulen] if isinstance(cozulen, list) else []


def gunun_satirlari(tarih: str) -> list[dict]:
    """Verilen günün (YYYY-MM-DD) tüm yoklama satırlarını döndürür.

    Her satır bir (sınıf, ders) çiftidir: `{sinif, ders_no, durum,
    yok_isimleri: [...], izinli_isimleri: [...], kaydedilme_saati}`.
    Filtreleme YAPILMAZ — 'alinmadi'/'tahta_ulasilamaz' satırları da döner,
    çünkü üst katman "bu sınıfın yoklaması eksik" uyarısını bunlardan üretir.
    """
    conn = _baglan()
    try:
        satirlar = conn.execute(
            "SELECT sinif, ders_no, durum, yok_isimleri, izinli_isimleri, "
            "kaydedilme_saati FROM yoklama_onbellek WHERE tarih = ? "
            "ORDER BY sinif, ders_no",
            (tarih,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise YoklamaKaynakYok(f"Yoklama verisi okunamadı: {exc}") from exc
    finally:
        conn.close()

    return [
        {
            "sinif": s["sinif"],
            "ders_no": s["ders_no"],
            "durum": s["durum"],
            "yok_isimleri": _json_liste(s["yok_isimleri"]),
            "izinli_isimleri": _json_liste(s["izinli_isimleri"]),
            "kaydedilme_saati": s["kaydedilme_saati"],
        }
        for s in satirlar
    ]
