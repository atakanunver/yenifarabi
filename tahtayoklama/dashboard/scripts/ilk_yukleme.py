"""Tek seferlik DB tohumlama — server/tahtalar.json + tahtayoklama/data/roster/
+ networkobjects.seed.json'dan dashboard'un kendi SQLite DB'sini doldurur.

Kullanım: dashboard/ dizininden `venv/bin/python scripts/ilk_yukleme.py`

Bu betik idempotent DEĞİL kasıtlı olarak basit tutuldu — DB zaten doluysa
UNIQUE kısıtları hata verir. Zaten dolu bir DB'yi yeniden tohumlamak
istemiyorsanız veri/yoklama_pano.db'yi silip yeniden çalıştırın.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
TAHTAYOKLAMA_DIR = DASHBOARD_DIR.parent
SERVER_DIR = TAHTAYOKLAMA_DIR.parent / "server"

TAHTALAR_JSON = SERVER_DIR / "tahtalar.json"
ROSTER_DIR = TAHTAYOKLAMA_DIR / "data" / "roster"
NETWORKOBJECTS_SEED = DASHBOARD_DIR / "config" / "networkobjects.seed.json"

# yoklama.py'yi çalıştıran python yolu tahtadan tahtaya farklı — canlı SSH ile
# doğrulandı (2026-08-23): yalnızca 9-A Farabi'nin client venv'ini kullanıyor,
# geri kalan 6 tahtanın (9-B/10-A/11-A/11-B/12-A/12-B) kendi
# ~/tahtayoklama/venv'i var (bkz. db.py'deki python_yolu sütun açıklaması).
PYTHON_YOLU_ISTISNA = {
    "9-A": "/home/ogretmen/farabi/client/venv/bin/python",
}
PYTHON_YOLU_VARSAYILAN = "/home/ogretmen/tahtayoklama/venv/bin/python"


def _mac_haritasi() -> dict[str, str]:
    """HostAddress -> MacAddress. networkobjects.seed.json yalnızca bir kerelik,
    statik bir Windows dışa aktarımı — canlı bir kaynak değil."""
    if not NETWORKOBJECTS_SEED.exists():
        return {}
    veri = json.loads(NETWORKOBJECTS_SEED.read_text(encoding="utf-8"))
    return {
        girdi["HostAddress"]: girdi["MacAddress"]
        for girdi in veri
        if girdi.get("Type") == 2 and "HostAddress" in girdi
    }


def main() -> None:
    db.semayi_kur()
    conn = db.baglanti()

    if not TAHTALAR_JSON.exists():
        print(f"HATA: {TAHTALAR_JSON} bulunamadı.", file=sys.stderr)
        sys.exit(1)

    tahtalar_veri = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
    mac_haritasi = _mac_haritasi()

    sinif_id_by_ad: dict[str, int] = {}

    # 1) Rosterlardan sınıfları + öğrencileri yükle.
    for roster_yolu in sorted(ROSTER_DIR.glob("*.json")):
        if roster_yolu.stem.endswith(".example"):
            continue
        roster = json.loads(roster_yolu.read_text(encoding="utf-8"))
        sinif_adi = roster["sinif"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO siniflar (ad) VALUES (?)", (sinif_adi,)
        )
        satir = conn.execute(
            "SELECT id FROM siniflar WHERE ad = ?", (sinif_adi,)
        ).fetchone()
        sinif_id = satir["id"]
        sinif_id_by_ad[sinif_adi] = sinif_id

        for ogrenci in roster.get("ogrenciler", []):
            conn.execute(
                "INSERT OR IGNORE INTO ogrenciler (sinif_id, no, ad_soyad, cinsiyet) "
                "VALUES (?, ?, ?, ?)",
                (sinif_id, ogrenci["no"], ogrenci["ad_soyad"], ogrenci.get("cinsiyet")),
            )
        print(f"sınıf yüklendi: {sinif_adi} ({len(roster.get('ogrenciler', []))} öğrenci)")

    # 2) Tahtaları ekle, adı eşleşen sınıfa bağla.
    for ad, bilgi in tahtalar_veri.items():
        if ad.startswith("_"):
            continue
        ip = bilgi["ip"]
        sinif_id = sinif_id_by_ad.get(ad)
        mac = mac_haritasi.get(ip)
        python_yolu = PYTHON_YOLU_ISTISNA.get(ad, PYTHON_YOLU_VARSAYILAN)
        conn.execute(
            "INSERT OR IGNORE INTO tahtalar (ad, ip, mac, ssh_kullanici, python_yolu, sinif_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ad, ip, mac, bilgi.get("kullanici", "ogretmen"), python_yolu, sinif_id),
        )
        durum = f"-> sınıf {ad}" if sinif_id else "(sınıf atanmadı)"
        print(f"tahta yüklendi: {ad} ({ip}) {durum}")

    conn.commit()
    conn.close()
    print("Tohumlama tamamlandı.")


if __name__ == "__main__":
    main()
