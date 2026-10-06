#!/usr/bin/env python3
"""tahta_istemci.py — tahtada arka planda çalışan, sunucuyla HTTP konuşan
küçük istemci (2026-10-06). Sunucu tarafı: dashboard/tahta_api.py.

Neden ayrı süreç: yoklama.py (öğretmenin dokunduğu GUI) bilinçli olarak
ağdan izole kalır — bu istemci çökse/sunucu kapalı olsa bile yoklama
alınmaya devam eder (kök CLAUDE.md Kural 2). İstemci yoklama.py'nin
yazdığı dosyaları OKUR, yoklama.py'ye hiçbir şey söylemez.

Döngü:
- ~15 sn: data/kayitlar/ son 7 günün dosyalarını tarar; içerik özeti
  (sha256) son onaylanandan farklıysa POST /kayit (öğretmen aynı dersi
  yeniden kaydederse dosya üzerine yazılır → özet değişir → yeniden gider).
  Ayrı bir "giden kutusu" kopyası yok; kuyruk = kayitlar/ + durum dosyası.
- 60 sn: POST /nabiz.
- 10 dk (ve açılışta): GET /yapilandirma (ETag) → roster / zil.json /
  ders_programi.json / kazanimlar.json içerik farklıysa doğrulayıp atomik yazar.

Yalnızca standart kütüphane (sistem python3, 3.11). Proxy KULLANILMAZ
(okul ağı proxy'si LAN'daki sunucuya giden isteği bozmasın).
Ayar: ~/tahtayoklama/istemci.json {"sunucu": "http://...:8010", "token": "..."}
(0600, scripts/tahta_istemci_kur.py yazar). systemd --user birimi:
tahta-istemci.service.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

SURUM = "2"
BASE_DIR = Path(__file__).resolve().parent
AYAR_DOSYASI = BASE_DIR / "istemci.json"
DATA_DIR = BASE_DIR / "data"
KAYIT_DIR = DATA_DIR / "kayitlar"
ROSTER_DIR = DATA_DIR / "roster"
YEDEK_DIR = DATA_DIR / ".istemci_yedek"
DURUM_DOSYASI = DATA_DIR / ".istemci_durum.json"

KAYIT_ARALIGI_SN = 15
NABIZ_ARALIGI_SN = 60
YAPILANDIRMA_ARALIGI_SN = 600
GERIYE_GUN = 7
ZAMAN_ASIMI_SN = 8

_KAYIT_ADI_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_[A-Za-z0-9_-]+_ders\d+\.json$")
_SINIF_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_SAAT_RE = re.compile(r"^\d{2}:\d{2}$")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(mesaj: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {mesaj}", flush=True)


def ayar_yukle() -> dict:
    ayar = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
    if not ayar.get("sunucu") or not ayar.get("token"):
        raise ValueError("istemci.json eksik: sunucu/token")
    ayar["sunucu"] = ayar["sunucu"].rstrip("/")
    return ayar


def durum_yukle() -> dict:
    try:
        durum = json.loads(DURUM_DOSYASI.read_text(encoding="utf-8"))
        if isinstance(durum, dict):
            durum.setdefault("gonderilen", {})
            return durum
    except (OSError, ValueError):
        pass
    return {"gonderilen": {}, "etag": None}


def atomik_yaz(yol: Path, veri: bytes) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".tmp")
    gecici.write_bytes(veri)
    os.replace(gecici, yol)


def durum_kaydet(durum: dict) -> None:
    atomik_yaz(DURUM_DOSYASI, json.dumps(durum, ensure_ascii=False).encode("utf-8"))


def istek(ayar: dict, yontem: str, yol: str, govde: dict | None = None,
          basliklar: dict | None = None) -> tuple[int, dict, bytes]:
    """(durum_kodu, yanit_basliklari, govde). Ağ hatası → (0, {}, b'')."""
    h = {"Authorization": f"Bearer {ayar['token']}"}
    veri = None
    if govde is not None:
        veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    h.update(basliklar or {})
    req = urllib.request.Request(ayar["sunucu"] + yol, data=veri, headers=h, method=yontem)
    try:
        with _opener.open(req, timeout=ZAMAN_ASIMI_SN) as yanit:
            return yanit.status, dict(yanit.headers), yanit.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if e.fp else b""
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, {}, b""


# --- kayıt gönderimi -------------------------------------------------------

def kayitlari_gonder(ayar: dict, durum: dict) -> None:
    if not KAYIT_DIR.is_dir():
        return
    sinir = (date.today() - timedelta(days=GERIYE_GUN)).isoformat()
    gonderilen = durum["gonderilen"]
    degisti = False
    for yol in sorted(KAYIT_DIR.glob("*.json")):
        m = _KAYIT_ADI_RE.match(yol.name)
        if not m or m.group(1) < sinir:
            continue
        try:
            ham = yol.read_bytes()
        except OSError:
            continue
        ozet = hashlib.sha256(ham).hexdigest()
        if gonderilen.get(yol.name) == ozet:
            continue
        try:
            kayit = json.loads(ham)
        except ValueError:
            continue  # yoklama.py yazarken yakalandıysa bir sonraki turda
        kod, _, _ = istek(ayar, "POST", "/api/v1/tahta/kayit", kayit)
        if kod == 200:
            log(f"kayit gonderildi: {yol.name}")
            gonderilen[yol.name] = ozet
            degisti = True
        elif kod in (400, 413, 422):
            # Kalıcı ret — aynı içerik bir daha denenmez (SSH yedeği yine görür).
            log(f"kayit reddedildi ({kod}): {yol.name}")
            gonderilen[yol.name] = ozet
            degisti = True
        else:
            log(f"kayit gonderilemedi ({kod}): {yol.name} — sonra denenecek")
            break  # sunucu yoksa kalanları bu tur zorlamayalım
    # Eski girdileri buda
    for ad in [a for a in gonderilen if (_KAYIT_ADI_RE.match(a) or [None, ""])[1] < sinir]:
        del gonderilen[ad]
        degisti = True
    if degisti:
        durum_kaydet(durum)


# --- nabız -----------------------------------------------------------------

def yoklama_acik_mi() -> bool:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        if b"yoklama.py" in cmd and b"tahta_istemci" not in cmd:
            return True
    return False


def nabiz_gonder(ayar: dict) -> None:
    kod, _, _ = istek(ayar, "POST", "/api/v1/tahta/nabiz",
                      {"istemci_surum": SURUM, "yoklama_acik": yoklama_acik_mi()})
    if kod != 200:
        log(f"nabiz basarisiz ({kod})")


# --- yapılandırma ----------------------------------------------------------

def zil_gecerli(metin: str) -> bool:
    try:
        z = json.loads(metin)
        dersler = z["dersler"]
        if not isinstance(dersler, list) or not dersler:
            return False
        for d in dersler:
            if not isinstance(d["no"], int):
                return False
            if not (_SAAT_RE.match(d["baslangic"]) and _SAAT_RE.match(d["bitis"])):
                return False
        return True
    except (ValueError, KeyError, TypeError):
        return False


def ders_programi_gecerli(metin: str) -> bool:
    try:
        return isinstance(json.loads(metin).get("siniflar"), dict)
    except (ValueError, AttributeError):
        return False


def kazanimlar_gecerli(metin: str) -> bool:
    try:
        k = json.loads(metin)
        return isinstance(k.get("haftalar"), dict) and isinstance(k.get("kazanimlar"), dict)
    except (ValueError, AttributeError):
        return False


def roster_gecerli(metin: str, sinif: str) -> bool:
    try:
        r = json.loads(metin)
        return (r.get("sinif") == sinif and isinstance(r.get("ogrenciler"), list)
                and len(r["ogrenciler"]) > 0)
    except (ValueError, AttributeError):
        return False


def _yedekle(yol: Path) -> None:
    if yol.exists():
        YEDEK_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(yol, YEDEK_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{yol.name}")


def _farkliysa_yaz(yol: Path, metin: str) -> bool:
    veri = metin.encode("utf-8")
    try:
        if yol.read_bytes() == veri:
            return False
    except OSError:
        pass
    _yedekle(yol)
    atomik_yaz(yol, veri)
    return True


def yapilandirmayi_uygula(yap: dict) -> None:
    """Fail-safe: geçersiz/eksik alan → o dosyaya DOKUNMA. Roster None ise
    (sınıf atanmamış tahta, ör. fenlab) roster dizinine hiç dokunulmaz."""
    zil = yap.get("zil")
    if isinstance(zil, str) and zil_gecerli(zil):
        if _farkliysa_yaz(DATA_DIR / "zil.json", zil):
            log("zil.json guncellendi")
    dp = yap.get("ders_programi")
    if isinstance(dp, str) and ders_programi_gecerli(dp):
        if _farkliysa_yaz(DATA_DIR / "ders_programi.json", dp):
            log("ders_programi.json guncellendi")
    kz = yap.get("kazanimlar")
    if isinstance(kz, str) and kazanimlar_gecerli(kz):
        if _farkliysa_yaz(DATA_DIR / "kazanimlar.json", kz):
            log("kazanimlar.json guncellendi")
    sinif, roster = yap.get("sinif"), yap.get("roster")
    if (isinstance(sinif, str) and _SINIF_RE.match(sinif)
            and isinstance(roster, str) and roster_gecerli(roster, sinif)):
        if _farkliysa_yaz(ROSTER_DIR / f"{sinif}.json", roster):
            log(f"roster guncellendi: {sinif}")
        # admin.py SSH senkronuyla aynı kural: tahta TEK sınıf gösterir.
        # Silmek yerine yedeğe taşınır.
        for eski in ROSTER_DIR.glob("*.json"):
            if eski.name != f"{sinif}.json":
                _yedekle(eski)
                eski.unlink()
                log(f"eski roster kaldirildi (yedekte): {eski.name}")


def yapilandirma_cek(ayar: dict, durum: dict) -> None:
    basliklar = {"If-None-Match": durum["etag"]} if durum.get("etag") else {}
    kod, yanit_basliklari, govde = istek(ayar, "GET", "/api/v1/tahta/yapilandirma",
                                         basliklar=basliklar)
    if kod == 304:
        return
    if kod != 200:
        log(f"yapilandirma alinamadi ({kod})")
        return
    try:
        yap = json.loads(govde)
    except ValueError:
        log("yapilandirma bozuk JSON")
        return
    yapilandirmayi_uygula(yap)
    durum["etag"] = yanit_basliklari.get("ETag") or yanit_basliklari.get("etag")
    durum_kaydet(durum)


# --- ana döngü -------------------------------------------------------------

def main() -> int:
    try:
        ayar = ayar_yukle()
    except (OSError, ValueError) as e:
        log(f"ayar okunamadi: {e}")
        return 1
    log(f"tahta_istemci {SURUM} basladi, sunucu={ayar['sunucu']}")
    durum = durum_yukle()
    son_nabiz = son_yap = 0.0
    while True:
        simdi = time.monotonic()
        for ad, aralik, son, is_ in (
            ("yap", YAPILANDIRMA_ARALIGI_SN, son_yap, lambda: yapilandirma_cek(ayar, durum)),
            ("nabiz", NABIZ_ARALIGI_SN, son_nabiz, lambda: nabiz_gonder(ayar)),
        ):
            if son == 0.0 or simdi - son >= aralik:
                try:
                    is_()
                except Exception as e:  # noqa: BLE001 — döngü asla ölmemeli
                    log(f"{ad} hatasi: {e!r}")
                if ad == "yap":
                    son_yap = simdi
                else:
                    son_nabiz = simdi
        try:
            kayitlari_gonder(ayar, durum)
        except Exception as e:  # noqa: BLE001
            log(f"kayit hatasi: {e!r}")
        time.sleep(KAYIT_ARALIGI_SN)


if __name__ == "__main__":
    sys.exit(main())
