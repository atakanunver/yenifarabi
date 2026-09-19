"""Sistem Durumu — Farabi sunucusunun donanım/servis durumunu salt-okunur
şekilde toplar (Sistem Durumu sayfası + kenar çubuğundaki mini rozet).

Hiçbir komut sudo gerektirmez: `systemctl is-active` bir D-Bus okuma
sorgusudur, root gerekmez (2026-09-18'de doğrulandı). ssh_istemci.py'deki
"paramiko yok, hafif tut" konvansiyonuna uygun şekilde subprocess ile CLI
araçları (sensors, nvidia-smi, systemctl) çağrılır — yeni bir pip
bağımlılığı (ör. psutil) eklenmedi."""

import asyncio
import json
import os
import shutil
import urllib.error
import urllib.request

KOMUT_ZAMAN_ASIMI_SN = 4
OLLAMA_API = "http://127.0.0.1:11434/api/tags"

SERVISLER = [
    ("farabi-yoklama-dashboard", "Yoklama Panosu"),
    ("farabi-api", "Farabi RAG API"),
    ("ollama", "Ollama"),
    ("open-webui", "Open WebUI"),
    ("postgresql@18-main", "PostgreSQL"),
    ("chrony", "Zaman Senkronu (chrony)"),
]


async def _komut(*args: str) -> str | None:
    try:
        surec = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(surec.communicate(), timeout=KOMUT_ZAMAN_ASIMI_SN)
        return stdout.decode("utf-8", "replace").strip()
    except (OSError, asyncio.TimeoutError):
        return None


async def _cpu_bilgisi() -> dict:
    sonuc: dict = {"sicaklik_c": None, "fanlar": []}
    ham = await _komut("sensors", "-j")
    if not ham:
        return sonuc
    try:
        veri = json.loads(ham)
    except json.JSONDecodeError:
        return sonuc

    for cip, alanlar in veri.items():
        if not cip.startswith(("k10temp", "coretemp")):
            continue
        for etiket in ("Tctl", "Package id 0", "Tdie"):
            alt = alanlar.get(etiket)
            if not isinstance(alt, dict):
                continue
            for anahtar, deger in alt.items():
                if anahtar.endswith("_input"):
                    sonuc["sicaklik_c"] = round(deger)
                    break
            if sonuc["sicaklik_c"] is not None:
                break

    for cip, alanlar in veri.items():
        if not cip.startswith(("nct", "it87", "w83")):
            continue
        for anahtar, alt in alanlar.items():
            if not (anahtar.startswith("fan") and isinstance(alt, dict)):
                continue
            rpm = alt.get(f"{anahtar}_input")
            if rpm:
                sonuc["fanlar"].append({"ad": anahtar.replace("fan", "Fan "), "rpm": round(rpm)})
    return sonuc


async def _gpu_bilgisi() -> list[dict]:
    ham = await _komut(
        "nvidia-smi",
        "--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total,fan.speed",
        "--format=csv,noheader,nounits",
    )
    if not ham:
        return []
    sonuc = []
    for satir in ham.splitlines():
        parcalar = [p.strip() for p in satir.split(",")]
        if len(parcalar) != 7:
            continue
        idx, ad, sicaklik, kullanim, bellek_kullanim, bellek_toplam, fan = parcalar
        try:
            sonuc.append({
                "index": int(idx),
                "ad": ad,
                "sicaklik_c": int(sicaklik),
                "kullanim_yuzde": int(kullanim),
                "bellek_kullanim_mb": int(bellek_kullanim),
                "bellek_toplam_mb": int(bellek_toplam),
                "fan_yuzde": int(fan) if fan.isdigit() else None,
            })
        except ValueError:
            continue
    return sonuc


def _bellek_bilgisi() -> dict:
    degerler: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for satir in f:
                anahtar, _, deger = satir.partition(":")
                if anahtar in ("MemTotal", "MemAvailable"):
                    degerler[anahtar] = int(deger.strip().split()[0])  # kB
    except OSError:
        return {"toplam_gb": None, "kullanilan_gb": None, "yuzde": 0}
    toplam_kb = degerler.get("MemTotal", 0)
    musait_kb = degerler.get("MemAvailable", 0)
    kullanilan_kb = max(toplam_kb - musait_kb, 0)
    return {
        "toplam_gb": round(toplam_kb / 1024 / 1024, 1),
        "kullanilan_gb": round(kullanilan_kb / 1024 / 1024, 1),
        "yuzde": round(100 * kullanilan_kb / toplam_kb) if toplam_kb else 0,
    }


def _disk_bilgisi() -> dict:
    toplam, kullanilan, _bos = shutil.disk_usage("/")
    return {
        "toplam_gb": round(toplam / 1024**3),
        "kullanilan_gb": round(kullanilan / 1024**3),
        "yuzde": round(100 * kullanilan / toplam) if toplam else 0,
    }


def _yukleme_ve_calisma_suresi() -> dict:
    yuk1, yuk5, yuk15 = os.getloadavg()
    try:
        with open("/proc/uptime") as f:
            saniye = float(f.read().split()[0])
    except OSError:
        saniye = 0.0
    gun = int(saniye // 86400)
    saat = int((saniye % 86400) // 3600)
    dakika = int((saniye % 3600) // 60)
    return {
        "yukleme": {"bir_dk": round(yuk1, 2), "bes_dk": round(yuk5, 2), "onbes_dk": round(yuk15, 2)},
        "calisma_suresi": f"{gun}g {saat}s {dakika}dk" if gun else f"{saat}s {dakika}dk",
    }


async def _servis_durumlari() -> list[dict]:
    async def tek(birim: str, etiket: str) -> dict:
        durum = await _komut("systemctl", "is-active", birim)
        return {"birim": birim, "etiket": etiket, "durum": durum or "bilinmiyor", "aktif": durum == "active"}
    return list(await asyncio.gather(*(tek(b, e) for b, e in SERVISLER)))


def _ollama_modelleri() -> list[str] | None:
    try:
        with urllib.request.urlopen(OLLAMA_API, timeout=3) as yanit:
            veri = json.loads(yanit.read())
        return [m.get("name", "?") for m in veri.get("models", [])]
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


async def durum_topla() -> dict:
    cpu, gpu, servisler, ollama = await asyncio.gather(
        _cpu_bilgisi(),
        _gpu_bilgisi(),
        _servis_durumlari(),
        asyncio.to_thread(_ollama_modelleri),
    )
    veri = {
        "cpu": cpu,
        "gpu": gpu,
        "bellek": _bellek_bilgisi(),
        "disk": _disk_bilgisi(),
        "servisler": servisler,
        "ollama_modelleri": ollama,
    }
    veri.update(_yukleme_ve_calisma_suresi())
    return veri
