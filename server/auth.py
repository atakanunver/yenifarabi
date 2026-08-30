"""server/auth.py — tahta (board) kimlik doğrulama (FAZ 1, IMPLEMENT).

FAZ0/FAZ0.5 analiz raporlarının ortak bulgusu: hiçbir `/api/egitim/*` /
`/api/client/*` endpoint'i isteğin gerçekten bir Farabi tahtasından gelip
gelmediğini doğrulamıyordu — `0.0.0.0`'a açık server'a LAN'daki herhangi bir
cihaz erişebiliyordu. Bu modül TEK, MERKEZİ bir FastAPI dependency
(`dogrula_tahta`) sağlar; her router bunu `APIRouter(dependencies=[...])`
ile TÜM route'larına uygular — endpoint fonksiyonlarının kendisi değişmez
(bkz. her router dosyasındaki tek satırlık değişiklik).

TASARIM KARARLARI (gerekçeleriyle):

1. **Anahtar deposu = mevcut `server/config/api_keys.json`, YENİ bir
   `board_keys` alanı.** Yeni bir secret-yönetim sistemi KURULMADI —
   `saglayicilar.py::_config_oku()` ile AYNI dosya, AYNI desen (gitignored
   JSON, `{"derslik": "anahtar", ...}` sözlüğü). Bu, "mevcut config
   mekanizmasına uygun ol, yeni sistem kurma" talimatının doğrudan
   karşılığı.
2. **Board identity SUNUCUDAN gelir, istemciden DEĞİL.** `TahtaKimligi.
   derslik`, eşleşen anahtarın `board_keys` sözlüğündeki KEY'inden gelir —
   isteğin gövdesinde/parametresinde istemcinin yazdığı bir `derslik`
   alanı asla identity olarak kabul edilmez (böyle bir alan zaten hiçbir
   endpoint'in body'sinde bu amaçla okunmuyor).
3. **`board_id` alanı bilerek `None`.** Kalıcı, sayısal bir tahta kimliği
   (DB'de bir `tahta` tablosu) bu fazın kapsamı dışında — mevcut
   `metrik`/`soru_log`'un `tahta_id INTEGER` kolonuyla `derslik` (TEXT)
   arasında hazır bir eşleme yok, bunu icat etmek büyük bir DB migrasyonu
   olurdu (kapsam dışı, bkz. FAZ 1 raporu §"BİLİNEN SINIRLAR"). `derslik`
   şu an için TEK güvenilir kimlik alanı.
4. **Varsayılan GÜVENLİ: `FARABI_AUTH_REQUIRED` verilmezse auth
   ZORUNLUDUR.** Yalnızca açıkça "0"/"false"/"no"/"kapali"/"hayir"
   verilirse KAPANIR — bu bir acil rollback anahtarı, kalıcı bir güvensiz
   varsayılan DEĞİL.
5. **Sabit-zamana yakın karşılaştırma** (`hmac.compare_digest`) — anahtar
   değeri LOGLANMAZ, yalnızca "başarılı"/"başarısız" ve (başarılıysa)
   hangi `derslik`'in eşleştiği loglanır.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Header, HTTPException

log = logging.getLogger("auth")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADER_ADI = "X-Farabi-Board-Key"


@dataclass(frozen=True)
class TahtaKimligi:
    """Doğrulanmış tahta kimliği. `board_id` şimdilik hep None — bkz. modül
    docstring'i, madde 3."""
    derslik: str
    board_id: int | None = None


def _auth_zorunlu() -> bool:
    """FARABI_AUTH_REQUIRED — verilmezse (veya tanınmayan bir değerse)
    VARSAYILAN AÇIK. Yalnızca açık bir "kapat" değeriyle KAPANIR — acil
    rollback için (bkz. FAZ 1 raporu "ROLLBACK"), kalıcı bir güvensiz
    varsayılan değil."""
    ham = os.environ.get("FARABI_AUTH_REQUIRED", "1").strip().lower()
    return ham not in ("0", "false", "no", "off", "kapali", "kapalı", "hayir", "hayır")


def _board_keys() -> dict[str, str]:
    """derslik -> anahtar. `server/config/api_keys.json`'daki YENİ
    `board_keys` alanından okunur (gitignored, saglayicilar.py'nin
    `_config_oku()`'suyla aynı dosya/desen). Dosya yoksa/bozuksa ya da
    alan boşsa boş sözlük döner — bu durumda HİÇBİR anahtar geçerli
    olmaz (fail-closed, "hata = kapalı" ilkesi, saglayicilar.py'nin
    kendi `_config_oku()`'sundaki "hata olursa boş sözlük" desenle aynı)."""
    try:
        veri = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    ham = veri.get("board_keys") or {}
    if not isinstance(ham, dict):
        return {}
    return {str(k): str(v) for k, v in ham.items() if str(v).strip()}


def dogrula_tahta(
    x_farabi_board_key: str | None = Header(default=None, alias=HEADER_ADI),
) -> TahtaKimligi | None:
    """FastAPI dependency — her router'a `APIRouter(dependencies=[Depends(
    dogrula_tahta)])` ile TEK SATIRDA uygulanır (bkz. her router
    dosyasındaki değişiklik). Header eksik/boş ya da hiçbir kayıtlı
    anahtarla eşleşmiyorsa 401 fırlatır. `FARABI_AUTH_REQUIRED=0` ile
    rollback modundaysa doğrulama hiç yapılmadan None döner (istek
    geçer) — bkz. `_auth_zorunlu()`.

    ÖNEMLİ: `x_farabi_board_key`'in KENDİSİ hiçbir log satırına yazılmaz
    (yalnızca başarı/başarısızlık ve — başarılıysa — hangi `derslik`)."""
    if not _auth_zorunlu():
        return None

    if not x_farabi_board_key:
        log.warning("board authentication failure — %s header eksik", HEADER_ADI)
        raise HTTPException(status_code=401, detail=f"{HEADER_ADI} eksik")

    for derslik, anahtar in _board_keys().items():
        if hmac.compare_digest(anahtar, x_farabi_board_key):
            log.info("board authentication success (derslik=%s)", derslik)
            return TahtaKimligi(derslik=derslik)

    log.warning("board authentication failure — geçersiz %s", HEADER_ADI)
    raise HTTPException(status_code=401, detail=f"Geçersiz {HEADER_ADI}")
