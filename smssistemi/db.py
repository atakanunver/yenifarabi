"""SQLite bağlantı yardımcıları ve şema — smssistemi'nin tek durum kaynağı.
tahtayoklama/dashboard'un db.py deseninin bağımsız kopyası (kod paylaşımı
yok, bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md)."""

import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB_YOLU = Path(__file__).resolve().parent / "veri" / "smssistemi.db"
YEDEK_DIZINI = Path(__file__).resolve().parent / "veri" / "yedek"
_ISTANBUL = ZoneInfo("Europe/Istanbul")
_UTC = ZoneInfo("UTC")


def utc_str_to_istanbul_str(deger: str | None) -> str | None:
    """`gonderimler.zaman`/`ilk_zaman` gibi `datetime('now')` (UTC, bkz.
    SEMA) ile yazılmış 'YYYY-MM-DD HH:MM:SS' damgalarını, YALNIZCA
    GÖRÜNTÜLEME için Europe/Istanbul'a çevirir. DB'deki ham değer hiç
    değişmez — karşılaştırma/sıralama/idempotency kontrolleri (ör.
    oturum süresi, `otomasyon_ilk_ders_son_tarih`) hâlâ UTC ile çalışır,
    yalnızca kullanıcıya dönen satırlarda (gonderim_satirlari,
    gonderim_ozetleri) çağrılır. Ayrıştırılamayan/boş değer olduğu gibi
    döner (savunmacı — 2026-09-28 saat karmaşası kaydı, DECISIONS.md)."""
    if not deger:
        return deger
    try:
        an = datetime.strptime(deger, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_UTC)
    except ValueError:
        return deger
    return an.astimezone(_ISTANBUL).strftime("%Y-%m-%d %H:%M:%S")

# `kisiler` tablosunun KANONİK gövdesi — tek yerden yönetilir, hem SEMA
# (sıfırdan kurulumda) hem migration (eski kurulumu bu şekle getirirken)
# aynı tanımı kullanır. 2026-09-20'de 'personel' + `dogum_tarihi` eklendi
# (docs/superpowers/plans/2026-09-20-dogum-gunleri-modulu.md §2).
_KISILER_TABLO_GOVDESI = """(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_soyad        TEXT NOT NULL,
    telefon         TEXT,
    sinif_id        INTEGER NOT NULL REFERENCES siniflar (id),
    tur             TEXT NOT NULL CHECK (tur IN ('ogrenci', 'veli', 'personel')),
    ogrenci_kisi_id INTEGER REFERENCES kisiler (id),
    dogum_tarihi    TEXT,
    okul_no         INTEGER,
    veli_rol        TEXT
)"""

SEMA = f"""
CREATE TABLE IF NOT EXISTS gonderimler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gonderim_id   TEXT NOT NULL,
    isim          TEXT,
    telefon       TEXT NOT NULL,
    mesaj         TEXT NOT NULL,
    durum         TEXT NOT NULL,
    hata_metni    TEXT,
    zaman         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oturumlar (
    token             TEXT PRIMARY KEY,
    olusturma_zamani  TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS siniflar (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    ad  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS kisiler {_KISILER_TABLO_GOVDESI};

CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT NOT NULL
);
"""

_VARSAYILAN_SINIFLAR = ["9-A", "9-B", "10-A", "10-B", "11-A", "11-B", "12-A", "12-B"]

# Doğum günleri modülü (2026-09-20, docs/superpowers/plans/
# 2026-09-20-dogum-gunleri-modulu.md) — bilinçli seçim: 'personel' de bu
# tabloya eklendi, ayrı bir DB/tablo AÇILMADI (öğrenci+veli+personel zaten
# aynı "kime SMS atılabilir" kavramının parçası). "Personel" ve "Bilinmeyen
# Sınıf" gerçek sınıf DEĞİL, kişi-sınıf FK'sinin NOT NULL kalması için
# gereken sahte satırlar — NULL yapılsaydı kisiler_listele()'nin INNER
# JOIN'i bu kişileri sessizce listeden düşürürdü.
_PERSONEL_SINIF_ADI = "Personel"
_BILINMEYEN_SINIF_ADI = "Bilinmeyen Sınıf"

_AYARLAR_VARSAYILAN = {
    "sms_otomatik": "0",  # KAPALI — bkz. plan §9 R1, telefon listesi dolana kadar kasıtlı
    "dogum_sms_sablonu": (
        "Sevgili {isim}, dogum gununuzu kutlar, saglikli ve mutlu bir yil dileriz. Okul Idaresi"
    ),
    "otomasyon_ilk_ders_aktif": "0",  # KAPALI — ilk kurulumda pasif, kullanıcı butondan açar
    "otomasyon_ilk_ders_sablonu": (
        "Sayın {isim}, öğrenciniz {ogrenci_adi} sabah ilk saate gelmemiştir. Bilginize."
    ),
    "otomasyon_ilk_ders_son_tarih": "",
    "otomasyon_ilk_ders_son_sonuc": "",
}


def _tr_norm(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(s.replace("I", "ı").replace("İ", "i").lower().split())


def baglanti() -> sqlite3.Connection:
    DB_YOLU.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.create_function("tr_norm", 1, _tr_norm)
    return conn


def _dosya_yedekle(etiket: str) -> Path | None:
    """DB dosyasını (WAL içeriği checkpoint edilmiş hâliyle) veri/yedek/'e
    kopyalar. Dosya yoksa (ilk kurulum) None döner — yedeklenecek bir şey yok."""
    if not DB_YOLU.exists():
        return None
    YEDEK_DIZINI.mkdir(parents=True, exist_ok=True)
    bugun = datetime.now(_ISTANBUL).date().isoformat()
    hedef = YEDEK_DIZINI / f"smssistemi_{bugun}_{etiket}.db"
    gecici = sqlite3.connect(DB_YOLU)
    try:
        gecici.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        gecici.close()
    shutil.copy2(DB_YOLU, hedef)
    return hedef


def _kisiler_personel_migration(conn: sqlite3.Connection) -> None:
    """`tur` CHECK kısıtına 'personel' ekler. SQLite CHECK kısıtları
    ALTER TABLE ile değiştirilemediği için tabloyu yeniden kurar (resmi
    12 adımlı prosedür). İdempotan: `kisiler` tanımında zaten 'personel'
    geçiyorsa hiçbir şey yapmaz — semayi_kur() her başlangıçta çağrıldığı
    için bu koruma olmadan her restart'ta tablo yeniden kurulurdu.
    Bkz. docs/superpowers/plans/2026-09-20-dogum-gunleri-modulu.md §2.2."""
    tanim = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'kisiler'"
    ).fetchone()
    if tanim is None or "'personel'" in tanim["sql"]:
        return

    _dosya_yedekle("dogum_oncesi")

    conn.execute("PRAGMA foreign_keys = off")
    conn.execute("BEGIN")
    try:
        conn.execute(f"CREATE TABLE kisiler_yeni {_KISILER_TABLO_GOVDESI}")
        conn.execute(
            "INSERT INTO kisiler_yeni (id, ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id) "
            "SELECT id, ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id FROM kisiler"
        )
        conn.execute("DROP TABLE kisiler")
        conn.execute("ALTER TABLE kisiler_yeni RENAME TO kisiler")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = on")


def semayi_kur() -> None:
    conn = baglanti()
    try:
        conn.executescript(SEMA)
        mevcut_sutunlar = [r["name"] for r in conn.execute("PRAGMA table_info(kisiler)").fetchall()]
        if "ogrenci_kisi_id" not in mevcut_sutunlar:
            conn.execute("ALTER TABLE kisiler ADD COLUMN ogrenci_kisi_id INTEGER REFERENCES kisiler (id)")
        conn.commit()

        _kisiler_personel_migration(conn)

        mevcut_sutunlar = [r["name"] for r in conn.execute("PRAGMA table_info(kisiler)").fetchall()]
        if "dogum_tarihi" not in mevcut_sutunlar:
            conn.execute("ALTER TABLE kisiler ADD COLUMN dogum_tarihi TEXT")
            conn.commit()
        if "okul_no" not in mevcut_sutunlar:
            conn.execute("ALTER TABLE kisiler ADD COLUMN okul_no INTEGER")
            conn.commit()
        if "veli_rol" not in mevcut_sutunlar:
            conn.execute("ALTER TABLE kisiler ADD COLUMN veli_rol TEXT")
            conn.commit()

        if conn.execute("SELECT COUNT(*) FROM siniflar").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO siniflar (ad) VALUES (?)", [(ad,) for ad in _VARSAYILAN_SINIFLAR]
            )
        sinif_ekle(conn, _PERSONEL_SINIF_ADI)
        sinif_ekle(conn, _BILINMEYEN_SINIF_ADI)

        for anahtar, deger in _AYARLAR_VARSAYILAN.items():
            conn.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES (?, ?)", (anahtar, deger))

        conn.commit()
    finally:
        conn.close()


def gonderim_kaydet(
    conn: sqlite3.Connection,
    gonderim_id: str,
    isim: str,
    telefon: str,
    mesaj: str,
    durum: str,
    hata_metni: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, hata_metni) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (gonderim_id, isim, telefon, mesaj, durum, hata_metni),
    )
    conn.commit()


def gonderim_satirlari(conn: sqlite3.Connection, gonderim_id: str) -> list[dict]:
    satirlar = conn.execute(
        "SELECT isim, telefon, durum, hata_metni, zaman FROM gonderimler "
        "WHERE gonderim_id = ? ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    sonuc = [dict(r) for r in satirlar]
    for r in sonuc:
        r["zaman"] = utc_str_to_istanbul_str(r["zaman"])
    return sonuc


def gonderim_ozetleri(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    # Sıralama (ORDER BY) ham UTC dizgisi üzerinde yapılır — kronolojik sıra
    # dönüşümden etkilenmez, yalnızca sonuçtaki görüntü metni çevrilir.
    satirlar = conn.execute(
        "SELECT gonderim_id, "
        "MIN(zaman) AS ilk_zaman, "
        "COUNT(*) AS toplam, "
        "SUM(CASE WHEN durum = 'gonderildi' THEN 1 ELSE 0 END) AS basarili, "
        "SUM(CASE WHEN durum = 'hata' THEN 1 ELSE 0 END) AS hatali "
        "FROM gonderimler GROUP BY gonderim_id ORDER BY ilk_zaman DESC LIMIT ?",
        (limit,),
    ).fetchall()
    sonuc = [dict(r) for r in satirlar]
    for r in sonuc:
        r["ilk_zaman"] = utc_str_to_istanbul_str(r["ilk_zaman"])
    return sonuc


def gonderim_basarisizlari(conn: sqlite3.Connection, gonderim_id: str) -> list[tuple[str, str, str]]:
    satirlar = conn.execute(
        "SELECT isim, telefon, mesaj FROM gonderimler "
        "WHERE gonderim_id = ? AND durum = 'hata' AND telefon != '' "
        "ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    return [(r["isim"], r["telefon"], r["mesaj"]) for r in satirlar]


# --- Rehber: sınıflar --------------------------------------------------


_SINIF_AD_RE = re.compile(r"^(\d+)-([A-Za-zÇĞİÖŞÜçğıöşü]+)$")


def _sinif_sira_anahtari(ad: str) -> tuple[int, int, str]:
    """'9-A' gibi adları sayı+şubeye göre sıralar ('10-A' 'ad' sütununda
    metinsel sıralamada '9-A'dan önce gelir) — dashboard'un
    `_sinif_sira_anahtari`'sıyla aynı desen, bağımsız kopya."""
    eslesme = _SINIF_AD_RE.match(ad)
    if eslesme:
        return (0, int(eslesme.group(1)), eslesme.group(2))
    return (1, 0, ad)


def siniflar_listele(conn: sqlite3.Connection) -> list[dict]:
    siniflar = [dict(r) for r in conn.execute("SELECT id, ad FROM siniflar")]
    siniflar.sort(key=lambda s: _sinif_sira_anahtari(s["ad"]))
    return siniflar


def sinif_ekle(conn: sqlite3.Connection, ad: str) -> int:
    conn.execute("INSERT OR IGNORE INTO siniflar (ad) VALUES (?)", (ad,))
    conn.commit()
    return conn.execute("SELECT id FROM siniflar WHERE ad = ?", (ad,)).fetchone()["id"]


def sinif_sil(conn: sqlite3.Connection, sinif_id: int) -> bool:
    """Sınıfta kayıtlı kişi varsa silmez, False döner (route bunu kullanıcıya bildirir)."""
    kullanimda = conn.execute(
        "SELECT COUNT(*) FROM kisiler WHERE sinif_id = ?", (sinif_id,)
    ).fetchone()[0]
    if kullanimda:
        return False
    conn.execute("DELETE FROM siniflar WHERE id = ?", (sinif_id,))
    conn.commit()
    return True


# --- Rehber: kişiler -----------------------------------------------------


def kisi_ekle(
    conn: sqlite3.Connection,
    ad_soyad: str,
    telefon: str | None,
    sinif_id: int,
    tur: str,
    ogrenci_kisi_id: int | None = None,
    okul_no: int | None = None,
    veli_rol: str | None = None,
) -> int:
    imlec = conn.execute(
        "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id, okul_no, veli_rol) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ad_soyad, telefon or None, sinif_id, tur, ogrenci_kisi_id, okul_no, veli_rol),
    )
    conn.commit()
    return imlec.lastrowid


def kisi_guncelle(
    conn: sqlite3.Connection,
    kisi_id: int,
    ad_soyad: str,
    telefon: str | None,
    sinif_id: int,
    tur: str,
    ogrenci_kisi_id: int | None = None,
    okul_no: int | None = None,
    veli_rol: str | None = None,
) -> None:
    conn.execute(
        "UPDATE kisiler SET ad_soyad = ?, telefon = ?, sinif_id = ?, tur = ?, "
        "ogrenci_kisi_id = ?, okul_no = ?, veli_rol = ? WHERE id = ?",
        (ad_soyad, telefon or None, sinif_id, tur, ogrenci_kisi_id, okul_no, veli_rol, kisi_id),
    )
    conn.commit()


def kisi_ogrenci_bagla(conn: sqlite3.Connection, veli_kisi_id: int, ogrenci_kisi_id: int | None) -> None:
    conn.execute(
        "UPDATE kisiler SET ogrenci_kisi_id = ? WHERE id = ? AND tur = 'veli'",
        (ogrenci_kisi_id, veli_kisi_id),
    )
    conn.commit()


def kisi_sil(conn: sqlite3.Connection, kisi_id: int) -> None:
    conn.execute("UPDATE kisiler SET ogrenci_kisi_id = NULL WHERE ogrenci_kisi_id = ?", (kisi_id,))
    conn.execute("DELETE FROM kisiler WHERE id = ?", (kisi_id,))
    conn.commit()


def kisi_bul_isimle(conn: sqlite3.Connection, ad_soyad: str, sinif_id: int, tur: str) -> dict | None:
    """Toplu yüklemede eşleştirme için — isim/sınıf/tür birebir (boşluk/büyük-küçük
    harf ve Türkçe karakter farkı gözetmeksizin) eşleşen kişiyi bulur."""
    satir = conn.execute(
        "SELECT id, ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id, okul_no, veli_rol FROM kisiler "
        "WHERE sinif_id = ? AND tur = ? AND tr_norm(ad_soyad) = tr_norm(?)",
        (sinif_id, tur, ad_soyad),
    ).fetchone()
    return dict(satir) if satir else None


def kisiler_listele(
    conn: sqlite3.Connection, sinif_id: int | None = None, tur: str | None = None
) -> list[dict]:
    kosullar = []
    degerler: list = []
    if sinif_id is not None:
        kosullar.append("k.sinif_id = ?")
        degerler.append(sinif_id)
    if tur is not None:
        kosullar.append("k.tur = ?")
        degerler.append(tur)
    kosul_str = f"WHERE {' AND '.join(kosullar)}" if kosullar else ""
    satirlar = conn.execute(
        f"SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.sinif_id, k.ogrenci_kisi_id, "
        f"k.dogum_tarihi, k.okul_no, k.veli_rol, s.ad AS sinif_ad, ogr.ad_soyad AS ogrenci_ad "
        f"FROM kisiler k "
        f"JOIN siniflar s ON s.id = k.sinif_id "
        f"LEFT JOIN kisiler ogr ON ogr.id = k.ogrenci_kisi_id "
        f"{kosul_str} ORDER BY s.ad, k.tur, k.ad_soyad",
        degerler,
    ).fetchall()
    return [dict(r) for r in satirlar]


def sinif_bazli_ogrenciler(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    satirlar = conn.execute(
        "SELECT id, ad_soyad, sinif_id, okul_no FROM kisiler WHERE tur = 'ogrenci' ORDER BY ad_soyad"
    ).fetchall()
    sonuc: dict[int, list[dict]] = {}
    for r in satirlar:
        sonuc.setdefault(r["sinif_id"], []).append({"id": r["id"], "ad_soyad": r["ad_soyad"]})
    return sonuc


def kisiler_id_ile(conn: sqlite3.Connection, kisi_ids: list[int]) -> list[dict]:
    if not kisi_ids:
        return []
    yer_tutucular = ",".join("?" for _ in kisi_ids)
    satirlar = conn.execute(
        f"SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.sinif_id, k.ogrenci_kisi_id, "
        f"k.okul_no, k.veli_rol, s.ad AS sinif_ad, ogr.ad_soyad AS ogrenci_ad "
        f"FROM kisiler k "
        f"JOIN siniflar s ON s.id = k.sinif_id "
        f"LEFT JOIN kisiler ogr ON ogr.id = k.ogrenci_kisi_id "
        f"WHERE k.id IN ({yer_tutucular}) AND k.telefon IS NOT NULL AND k.telefon != ''",
        kisi_ids,
    ).fetchall()
    return [dict(r) for r in satirlar]


def kisiler_telefonlu(conn: sqlite3.Connection, sinif_id: int, tur: str) -> list[tuple[str, str]]:
    """SMS hedefi doldurmak için — yalnızca telefonu dolu olan kişiler."""
    satirlar = conn.execute(
        "SELECT ad_soyad, telefon FROM kisiler "
        "WHERE sinif_id = ? AND tur = ? AND telefon IS NOT NULL AND telefon != '' "
        "ORDER BY ad_soyad",
        (sinif_id, tur),
    ).fetchall()
    return [(r["ad_soyad"], r["telefon"]) for r in satirlar]


# --- Ayarlar (global anahtar/değer) --------------------------------------


def veliler_ogrenci_ile(conn: sqlite3.Connection, ogrenci_kisi_id: int) -> list[dict]:
    """Bir öğrenciye bağlı, TELEFONU OLAN velileri döndürür (Yoklama SMS modülü).
    Bir öğrencinin birden çok velisi olabilir (anne/baba için ayrı satır açar);
    rehberde tekil alıcıdırlar. Telefonsuzlar burada süzülür — çağıran taraf
    'veli telefonu yoktur' durumunu boş listeden anlar."""
    satirlar = conn.execute(
        "SELECT id, ad_soyad, telefon, veli_rol FROM kisiler "
        "WHERE tur = 'veli' AND ogrenci_kisi_id = ? "
        "AND telefon IS NOT NULL AND telefon != '' ORDER BY id",
        (ogrenci_kisi_id,),
    ).fetchall()
    return [dict(r) for r in satirlar]


def ayar_oku(conn: sqlite3.Connection, anahtar: str) -> str | None:
    satir = conn.execute("SELECT deger FROM ayarlar WHERE anahtar = ?", (anahtar,)).fetchone()
    return satir["deger"] if satir else None


def ayar_yaz(conn: sqlite3.Connection, anahtar: str, deger: str) -> None:
    conn.execute(
        "INSERT INTO ayarlar (anahtar, deger) VALUES (?, ?) "
        "ON CONFLICT (anahtar) DO UPDATE SET deger = excluded.deger",
        (anahtar, deger),
    )
    conn.commit()


# --- Doğum günleri --------------------------------------------------------


def kisi_bul_isimle_sinifsiz(conn: sqlite3.Connection, ad_soyad: str, tur: str) -> dict | None:
    """`kisi_bul_isimle`'nin sınıftan bağımsız hâli — Dogum.xlsx gibi sınıf
    bilgisi içermeyen kaynaklardan eşleştirme için. Aynı ad+tür'e sahip
    BİRDEN FAZLA kişi varsa (iki ayrı sınıfta aynı isimli öğrenci) ilk
    bulunanı döner — bu bilinçli bir sınırlama, dogum_ice_aktar.py bu
    durumu özet raporunda ayrıca sayar (bkz. plan §4)."""
    satir = conn.execute(
        "SELECT id, ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id, dogum_tarihi FROM kisiler "
        "WHERE tur = ? AND tr_norm(ad_soyad) = tr_norm(?)",
        (tur, ad_soyad),
    ).fetchone()
    return dict(satir) if satir else None


def kisi_dogum_tarihi_guncelle(conn: sqlite3.Connection, kisi_id: int, iso_tarih: str | None) -> None:
    conn.execute("UPDATE kisiler SET dogum_tarihi = ? WHERE id = ?", (iso_tarih, kisi_id))
    conn.commit()


def dogum_gunu_olanlar(conn: sqlite3.Connection, ay: int, gun: int) -> list[dict]:
    """Verilen ay/gün (bugün) doğum günü olan öğrenci+personeli döner.
    Veli hariç tutulur (kullanıcı kararı — plan §10 madde 6). 29 Şubat'ta
    doğanlar, artık olmayan yıllarda 28 Şubat'ta da eşleşsin diye ayrıca
    aranır (veride bugün 29 Şubat kaydı yok, savunmacı davranış)."""
    mm_gg = f"{ay:02d}-{gun:02d}"
    kosullar = ["substr(k.dogum_tarihi, 6, 5) = ?"]
    degerler: list = [mm_gg]
    if ay == 2 and gun == 28:
        kosullar[0] = "(substr(k.dogum_tarihi, 6, 5) = ? OR substr(k.dogum_tarihi, 6, 5) = '02-29')"
    satirlar = conn.execute(
        f"SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.sinif_id, k.dogum_tarihi, s.ad AS sinif_ad "
        f"FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
        f"WHERE k.tur IN ('ogrenci', 'personel') AND {kosullar[0]} "
        f"ORDER BY k.ad_soyad",
        degerler,
    ).fetchall()
    return [dict(r) for r in satirlar]


def dogum_tarihli_kisiler(conn: sqlite3.Connection) -> list[dict]:
    """Yaklaşan doğum günleri hesaplaması için ham liste (ay/gün Python'da
    işlenir — yıl sonu sarması SQL'de kırılgan, bkz. plan §3)."""
    satirlar = conn.execute(
        "SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.sinif_id, k.dogum_tarihi, s.ad AS sinif_ad "
        "FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
        "WHERE k.tur IN ('ogrenci', 'personel') AND k.dogum_tarihi IS NOT NULL "
        "ORDER BY k.ad_soyad"
    ).fetchall()
    return [dict(r) for r in satirlar]
