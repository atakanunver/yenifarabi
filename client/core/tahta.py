"""
core/tahta.py — Tahtanın kimliği: hangi derslikte olduğu, hangi sunucuya
bağlı olduğu.

Her akıllı tahta belirli bir sınıfta durur (10-A, 11-B, 12-C…). Bu bilgi üç
yerde kullanılır:

  1. Arayüzde görünür — hangi tahtaya baktığını bilmek için.
  2. Sistem promptuna girer — Farabi hangi sınıfa ders verdiğini bilir.
  3. Plan aramasını daraltır — derslik 10-A ise `ders_icerigi` sınıfı 10
     olarak varsayar; öğretmenin her seferinde "10. sınıf" demesi gerekmez.

`config/api_keys.json` içindeki `derslik` alanından okunur, elle yazılır.

`sunucu_url()` de aynı dosyadan okunur (`sunucu_url` alanı, boşsa
`http://127.0.0.1:8000`'e düşer) — tek makinede geliştirirken localhost
yeterliydi, ama server okul sunucu odasına taşınınca (2026-08-12 kararı)
her tahtanın hangi sunucuya bağlanacağını bilmesi gerekiyor. Bu modülün
"tahta kimliği" kapsamına giriyor: derslik "bu tahta neresi" sorusuna
cevapken, sunucu_url "bu tahta kime bağlı" sorusuna cevap veriyor — ikisi de
aynı config dosyasında, board-özel ayar.
"""

import json
import re
from pathlib import Path

from core.version import VERSION, major_version

BASE_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# "10-A", "10A", "10 A", "12-c" -> ("10", "A")
_DERSLIK_RE = re.compile(r"^\s*(\d{1,2})\s*[-/ ]?\s*([A-Za-zÇĞİÖŞÜçğıöşü]?)\s*$")


def derslik() -> str:
    """Tahtanın bulunduğu derslik, örn. '10-A'. Tanımsızsa boş dize."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get("derslik", "")).strip()
    except Exception:
        return ""
    if not ham:
        return ""
    m = _DERSLIK_RE.match(ham)
    if not m:
        return ham          # beklenmedik biçim: olduğu gibi göster
    sinif, sube = m.group(1), m.group(2).upper()
    return f"{sinif}-{sube}" if sube else sinif


def sinif_duzeyi() -> str:
    """
    Derslikten sınıf düzeyini çıkar: '10-A' -> '10'.

    `ders_icerigi` bunu varsayılan sınıf filtresi olarak kullanır; böylece
    tahta 10-A'daysa plan aramasında 10. sınıf kendiliğinden seçilir.
    """
    d = derslik()
    m = re.match(r"^(\d{1,2})", d)
    return m.group(1) if m else ""


def etiket() -> str:
    """Arayüzde gösterilecek etiket. Tanımsızsa uyarı metni döner."""
    d = derslik()
    return d if d else "DERSLİK TANIMSIZ"


def sunucu_url() -> str:
    """Bu tahtanın bağlanacağı Farabi Brain sunucusunun adresi (şema+host+port,
    sonunda / yok). Config'te `sunucu_url` boş/yoksa localhost'a düşer —
    tek makinelik geliştirme/test kurulumunda hâlâ çalışsın diye."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get("sunucu_url", "")).strip()
    except Exception:
        ham = ""
    return ham.rstrip("/") or "http://127.0.0.1:8000"


def tahta_anahtari() -> str:
    """Bu tahtanın `server/auth.py::dogrula_tahta` ile eşleşen kimlik anahtarı
    (FAZ 1). Config'teki `tahta_anahtari` alanından okunur — tanımsız/boşsa
    boş dize döner (server tarafında `board_keys`'e karşılık gelen değer
    henüz üretilmemiş/dağıtılmamış olabilir; bu fonksiyon fail-closed değil,
    yalnızca sessizce "anahtar yok" bildirir, `auth_headers()` bunu header
    eklememe kararına çevirir)."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get("tahta_anahtari", "")).strip()
    except Exception:
        return ""
    return ham


def auth_headers() -> dict:
    """`server/`'a yapılan her istekte eklenecek header sözlüğü. Anahtar
    tanımsızsa BOŞ sözlük döner (boş değerli bir `X-Farabi-Board-Key` header'ı
    DEĞİL) — sunucu tarafı `FARABI_AUTH_REQUIRED=0` iken zaten hiç
    doğrulamıyor, bu geçiş döneminde header'ın hiç gitmemesi de gitmesi de
    aynı sonucu verir; `FARABI_AUTH_REQUIRED=1` olduğunda ise boş bir header
    göndermek de eksik header göndermek de aynı 401'i alır — davranış farkı
    yok, yalnızca gereksiz bir header'dan kaçınıyoruz."""
    anahtar = tahta_anahtari()
    headers = {"X-Farabi-Client-Version": VERSION}
    if anahtar:
        headers["X-Farabi-Board-Key"] = anahtar
    return headers


def sunucu_surumu_dogrula() -> str | None:
    """Sunucu ile MAJOR sürüm uyumluluğunu istemci başlarken doğrular."""
    import requests

    try:
        response = requests.get(
            f"{sunucu_url()}/api/version", headers=auth_headers(), timeout=10
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Sürüm kontrolü için sunucuya ulaşılamadı: {exc}") from exc

    if response.status_code == 426:
        try:
            detail = response.json()["detail"]
            server_version = detail["server_version"]
        except (KeyError, TypeError, ValueError):
            server_version = "bilinmiyor"
        raise RuntimeError(
            "MAJOR sürüm uyumsuzluğu: "
            f"istemci {VERSION}, sunucu {server_version}. "
            "İstemci ve sunucu birlikte güncellenmelidir."
        )

    try:
        response.raise_for_status()
        veri = response.json()
        server_version = veri["server_version"]
    except (KeyError, ValueError, requests.RequestException) as exc:
        raise RuntimeError(f"Geçersiz sürüm kontrolü yanıtı: {exc}") from exc

    try:
        if major_version(server_version) != major_version(VERSION):
            raise RuntimeError(
                "MAJOR sürüm uyumsuzluğu: "
                f"istemci {VERSION}, sunucu {server_version}. "
                "İstemci ve sunucu birlikte güncellenmelidir."
            )
    except ValueError as exc:
        raise RuntimeError(
            f"Sunucu geçersiz semantic version bildirdi: {server_version!r}"
        ) from exc

    return veri.get("uyari")
