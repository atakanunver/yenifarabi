"""tahta_kaydi.py — server/tahtalar.json'daki tahta kayıt defterini okur.

Bu dosyaya hiçbir YAZMA yapılmaz (bkz. admin.py'nin server/tahtalar.json
için aynı ilkesi) — panonun kendi SQLite `tahtalar` tablosundan tamamen
bağımsız, ayrı bir kayıt defteri. Kasıtlı: bu liste zaten SSH-anahtarlı
erişimin tek doğru kaynağı (bkz. tahta-ssh.sh), ikinci bir kopyaya
(senkron dışı kalma riskiyle) gerek yok — uzaktan_yonetim.py bunu kullanır.
"""

import json
import re
from pathlib import Path

TAHTALAR_JSON = Path(__file__).resolve().parents[2] / "server" / "tahtalar.json"

_SINIF_AD_RE = re.compile(r"^(\d+)-([A-Za-z]+)$")


def _sira_anahtari(ad: str) -> tuple[int, int, str]:
    """'9-A' gibi adları sayı+şubeye göre sıralar; 'tahta-234' gibi
    eşleşmeyenler sona, kendi aralarında alfabetik."""
    eslesme = _SINIF_AD_RE.match(ad)
    if eslesme:
        return (0, int(eslesme.group(1)), eslesme.group(2))
    return (1, 0, ad)


def tahtalari_yukle() -> list[dict]:
    veri = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
    tahtalar = [
        {
            "ad": ad,
            "ip": kayit["ip"],
            "kullanici": kayit.get("kullanici", "ogretmen"),
            "admin": kayit.get("admin"),
        }
        for ad, kayit in veri.items()
        if not ad.startswith("_")
    ]
    tahtalar.sort(key=lambda t: _sira_anahtari(t["ad"]))
    return tahtalar
