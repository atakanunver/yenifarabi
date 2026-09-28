"""Sistem Durumu — Farabi sunucusunun donanım/servis durumunu salt-okunur
şekilde toplar (Sistem Durumu sayfası + kenar çubuğundaki mini rozet).

Hiçbir komut sudo gerektirmez: `systemctl show` bir D-Bus okuma
sorgusudur, root gerekmez (2026-09-18'de doğrulandı). ssh_istemci.py'deki
"paramiko yok, hafif tut" konvansiyonuna uygun şekilde subprocess ile CLI
araçları (sensors, nvidia-smi, systemctl, psql, journalctl) çağrılır — yeni
bir pip bağımlılığı (ör. psutil, psycopg2) eklenmedi.

2026-09-25 — "Farabi Central Health" genişletmesi (bkz. kök webmimari.md):
- Toplama artık İSTEK BAŞINA değil, lifespan'da başlayan TEK bir arka plan
  görevinde (`toplayici_dongusu`, 15 sn). kenar.js her dashboard sayfasında
  30 sn'de bir `/api/sistem-durumu` çağırıyor; istekler yalnızca önbellekteki
  son ölçümü okur, kaç sekme açık olursa olsun yük sabit kalır.
- Yavaş/dış kontroller (uzak makineler, Ollama journal'ı) ve HTTP/SQL
  sağlık yoklamaları 60 sn önbellekli — her yoklama hedef servisin journal'ına
  bir erişim satırı yazıyor; 15 sn'de bir servis başına günde ~9 bin satır
  eklenip CLAUDE.md'nin "birincil kanıt" saydığı logları boğuyordu (ölçüldü).
  CPU/RAM/GPU/disk/process bilgisi 15 sn'de kalır.
- Son 30 dk trendi bellekte bir ring buffer'da (120 × 15 sn) — tablo/DB yok,
  servis restart'ında sıfırlanır (bilinçli).
- SALT OKUNUR: hiçbir fonksiyon servis başlatmaz/durdurmaz, config yazmaz.
  SMS modemine ASLA bağlanılmaz (tek oturum kısıtı, canlı gönderimle
  çakışabilir) — yalnızca Müdür PC'deki köprü proxy'sinin portuna TCP.
- Birimlerin `Environment`'ı API'ye KONULMAZ (ollama'nınki proxy
  parolası içeriyor) — yalnızca port ve GPU numarası çıkarılır."""

import asyncio
import collections
import json
import os
import re
import shutil
import socket
import time
import urllib.error
import urllib.request

KOMUT_ZAMAN_ASIMI_SN = 4
HTTP_ZAMAN_ASIMI_SN = 3
TOPLAMA_ARALIGI_SN = 15
YAVAS_KONTROL_ARALIGI_SN = 60
BAYAT_SN = 60  # önbellek bundan eskiyse istek anında yeniden toplanır
TREND_NOKTA = 120  # 120 × 15 sn = 30 dk
OLLAMA_API = "http://127.0.0.1:11434/api/tags"
OLLAMA_PS_API = "http://127.0.0.1:11434/api/ps"

# (systemd birimi, etiket, HTTP sağlık yolu). Port koddan DEĞİL, birimin
# ExecStart/Environment'ından (postgres için postgresql.conf'tan) okunur.
SERVISLER = [
    ("farabi-yoklama-dashboard", "Yoklama Panosu", "/giris"),
    ("farabi-api", "Farabi RAG API", "/ready"),
    ("farabi-smssistemi", "SMS Sistemi", "/giris"),
    ("ollama", "Ollama", "/api/version"),
    ("open-webui", "Open WebUI", "/health"),
    ("postgresql@18-main", "PostgreSQL", None),  # HTTP yok — SQL ile yoklanır
    ("chrony", "Zaman Senkronu (chrony)", None),
]
VARSAYILAN_PORTLAR = {"ollama": 11434}
POSTGRES_CONF = "/etc/postgresql/18/main/postgresql.conf"

# Dış makineler — adresler llm-cluster-wiki'den (nodes/omv-debian.md,
# nodes/zil.md, nodes/mudur-pc.md). `beklenen`: "ayakta" sayılan HTTP kodları
# (zil paneli Basic Auth'lu → 401 = ayakta).
UZAK_SERVISLER = [
    {"anahtar": "tts", "ad": "TTS Sunucusu (Chatterbox)", "makine": "debian",
     "host": "192.168.23.251", "port": 5002, "yol": "/saglik", "beklenen": (200,)},
    {"anahtar": "zil", "ad": "Zil Paneli", "makine": "zil",
     "host": "192.168.23.230", "port": 8090, "yol": "/", "beklenen": (200, 401)},
    {"anahtar": "sms_kopru", "ad": "SMS Köprüsü (Müdür PC proxy → modem)", "makine": "mudur-pc",
     "host": "192.168.23.243", "port": 8080, "yol": None, "beklenen": ()},
]

YAVAS_MS = 1000  # bundan yavaş HTTP yanıtı "yavaş" sayılır

_son_olcum: dict | None = None
_son_olcum_zamani = 0.0
_toplama_kilidi = asyncio.Lock()
_trend: collections.deque = collections.deque(maxlen=TREND_NOKTA)
_onceki: dict = {}  # CPU/disk/servis sayaçlarının bir önceki örneği
_yavas_onbellek: dict = {"zaman": 0.0, "uzak": [], "ollama_log": None, "modeller": None,
                         "ollama_ps": {"erisilebilir": False, "ms": None, "yuklu": []}}
_uzak_son_basari: dict[str, float] = {}


async def _komut(*args: str, zaman_asimi: float = KOMUT_ZAMAN_ASIMI_SN) -> str | None:
    try:
        surec = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(surec.communicate(), timeout=zaman_asimi)
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


def _sure_metni(saniye: float) -> str:
    gun = int(saniye // 86400)
    saat = int((saniye % 86400) // 3600)
    dakika = int((saniye % 3600) // 60)
    return f"{gun}g {saat}s {dakika}dk" if gun else f"{saat}s {dakika}dk"


def _yukleme_ve_calisma_suresi() -> dict:
    yuk1, yuk5, yuk15 = os.getloadavg()
    try:
        with open("/proc/uptime") as f:
            saniye = float(f.read().split()[0])
    except OSError:
        saniye = 0.0
    return {
        "yukleme": {"bir_dk": round(yuk1, 2), "bes_dk": round(yuk5, 2), "onbes_dk": round(yuk15, 2)},
        "calisma_suresi": _sure_metni(saniye),
    }


# ---------- Sayaç farkı ile ölçülenler (CPU %, disk I/O) ----------

def _cpu_sayaclari() -> tuple[int, int] | None:
    try:
        with open("/proc/stat") as f:
            alanlar = [int(x) for x in f.readline().split()[1:]]
    except (OSError, ValueError):
        return None
    bosta = alanlar[3] + (alanlar[4] if len(alanlar) > 4 else 0)  # idle + iowait
    return sum(alanlar), bosta


def _disk_sayaclari() -> dict[str, tuple[int, int, int]]:
    """Fiziksel diskler (loop/dm/ram hariç): (okunan sektör, yazılan sektör, io_ticks ms)."""
    sonuc = {}
    try:
        fiziksel = {d for d in os.listdir("/sys/block") if not d.startswith(("loop", "dm-", "ram", "zram"))}
        with open("/proc/diskstats") as f:
            for satir in f:
                p = satir.split()
                if len(p) >= 13 and p[2] in fiziksel:
                    sonuc[p[2]] = (int(p[5]), int(p[9]), int(p[12]))
    except (OSError, ValueError):
        pass
    return sonuc


def _sayac_farklari(simdi: float) -> dict:
    """CPU kullanım yüzdesi ve disk I/O (MB/s, %meşguliyet) — önceki örneğe göre."""
    cpu = _cpu_sayaclari()
    disk = _disk_sayaclari()
    sonuc: dict = {"cpu_kullanim_yuzde": None, "disk_io": []}
    onceki_zaman = _onceki.get("zaman")
    if onceki_zaman and cpu and _onceki.get("cpu"):
        toplam_fark = cpu[0] - _onceki["cpu"][0]
        bosta_fark = cpu[1] - _onceki["cpu"][1]
        if toplam_fark > 0:
            sonuc["cpu_kullanim_yuzde"] = round(100 * (toplam_fark - bosta_fark) / toplam_fark, 1)
    if onceki_zaman:
        gecen = simdi - onceki_zaman
        for ad, (oku, yaz, mesgul) in sorted(disk.items()):
            eski = _onceki.get("disk", {}).get(ad)
            if not eski or gecen <= 0:
                continue
            sonuc["disk_io"].append({
                "ad": ad,
                "okuma_mb_s": round((oku - eski[0]) * 512 / gecen / 1024**2, 2),
                "yazma_mb_s": round((yaz - eski[1]) * 512 / gecen / 1024**2, 2),
                "mesgul_yuzde": min(100, round((mesgul - eski[2]) / (gecen * 1000) * 100, 1)),
            })
    _onceki.update({"zaman": simdi, "cpu": cpu, "disk": disk})
    return sonuc


# ---------- Servisler: process + HTTP ----------

def _ortam_degiskeni(ortam: str, ad: str) -> str | None:
    """`systemctl show -p Environment` satırından tek değişkeni çeker (son tanım kazanır)."""
    bulunan = None
    for parca in ortam.split():
        if parca.startswith(ad + "="):
            bulunan = parca.split("=", 1)[1]
    return bulunan


def _postgres_portu() -> int | None:
    try:
        with open(POSTGRES_CONF) as f:
            for satir in f:
                m = re.match(r"\s*port\s*=\s*(\d+)", satir)
                if m:
                    return int(m.group(1))
    except OSError:
        return None
    return 5432


def _port_bul(birim: str, exec_start: str, ortam: str) -> int | None:
    m = re.search(r"--port[ =](\d+)", exec_start)
    if m:
        return int(m.group(1))
    host = _ortam_degiskeni(ortam, "OLLAMA_HOST")
    if host and re.search(r":(\d+)$", host):
        return int(host.rsplit(":", 1)[1])
    port = _ortam_degiskeni(ortam, "PORT")
    if port and port.isdigit():
        return int(port)
    if birim.startswith("postgresql"):
        return _postgres_portu()
    return VARSAYILAN_PORTLAR.get(birim)


async def _systemd_ozellikleri() -> dict[str, dict]:
    """Tüm birimler için TEK `systemctl show` çağrısı (eskiden birim başına bir is-active)."""
    ham = await _komut(
        "systemctl", "show", *(b for b, _, _ in SERVISLER),
        "-p", "Id", "-p", "ActiveState", "-p", "MainPID", "-p", "MemoryCurrent",
        "-p", "CPUUsageNSec", "-p", "ActiveEnterTimestampMonotonic",
        "-p", "ExecStart", "-p", "Environment",
    )
    sonuc: dict[str, dict] = {}
    if not ham:
        return sonuc
    for blok in ham.split("\n\n"):
        ozellik = {}
        for satir in blok.splitlines():
            anahtar, _, deger = satir.partition("=")
            ozellik[anahtar] = deger
        birim_id = ozellik.get("Id", "")
        if birim_id:
            sonuc[birim_id.removesuffix(".service")] = ozellik
    return sonuc


def _tamsayi(deger: str | None) -> int | None:
    try:
        return int(deger) if deger not in (None, "", "[not set]") else None
    except ValueError:
        return None


def _http_prob(url: str, zaman_asimi: float = HTTP_ZAMAN_ASIMI_SN) -> dict:
    """Proxy'yi bilerek atlar (yerel/LAN adresleri). Yanıt gövdesi okunmaz."""
    acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    baslangic = time.perf_counter()
    try:
        with acici.open(url, timeout=zaman_asimi) as yanit:
            kod = yanit.status
            govde = yanit.read(65536)
    except urllib.error.HTTPError as e:
        kod, govde = e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        sebep = getattr(e, "reason", e)
        return {"kod": None, "ms": None, "hata": "zaman aşımı" if "timed out" in str(sebep) else str(sebep)[:80]}
    return {"kod": kod, "ms": round((time.perf_counter() - baslangic) * 1000, 1), "hata": None, "_govde": govde}


def _tcp_prob(host: str, port: int, zaman_asimi: float = HTTP_ZAMAN_ASIMI_SN) -> dict:
    baslangic = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=zaman_asimi):
            pass
    except OSError as e:
        return {"kod": None, "ms": None, "hata": "zaman aşımı" if isinstance(e, TimeoutError) else str(e)[:80]}
    return {"kod": "tcp", "ms": round((time.perf_counter() - baslangic) * 1000, 1), "hata": None}


def _http_sonucu(prob: dict, beklenen: tuple = (200,)) -> dict:
    ayakta = prob["kod"] == "tcp" or prob["kod"] in beklenen
    return {
        "durum": "up" if ayakta else "down",
        "kod": prob["kod"],
        "ms": prob["ms"],
        "hata": prob["hata"] if not ayakta else None,
    }


async def _sql_prob() -> dict:
    """PostgreSQL için "HTTP" karşılığı: `SELECT 1` gidiş-dönüş süresi."""
    baslangic = time.perf_counter()
    ham = await _komut("psql", "-h", "127.0.0.1", "-U", "farabi", "-d", "farabi", "-AtqX",
                       "-c", "SELECT 1")
    if ham != "1":
        return {"durum": "down", "kod": None, "ms": None, "hata": "psql bağlantısı kurulamadı"}
    return {"durum": "up", "kod": "sql", "ms": round((time.perf_counter() - baslangic) * 1000, 1), "hata": None}


async def _chrony_prob() -> dict:
    ham = await _komut("chronyc", "-n", "tracking")
    if not ham:
        return {"durum": "down", "kod": None, "ms": None, "hata": "chronyc yanıt vermedi"}
    sapma = re.search(r"System time\s*:\s*([\d.]+) seconds (fast|slow)", ham)
    sicrama = re.search(r"Leap status\s*:\s*(.+)", ham)
    normal = sicrama and sicrama.group(1).strip() == "Normal"
    return {
        "durum": "up" if normal else "down",
        "kod": "ntp",
        "ms": round(float(sapma.group(1)) * 1000, 3) if sapma else None,  # saat sapması (ms)
        "hata": None if normal else f"Leap status: {sicrama.group(1).strip() if sicrama else '?'}",
    }


def _saglik_etiketi(aktif: bool, http: dict | None) -> str:
    if not aktif:
        return "hata"
    if http is None:
        return "ok"
    if http["durum"] != "up":
        return "hata"
    if http["kod"] not in ("ntp",) and http["ms"] is not None and http["ms"] > YAVAS_MS:
        return "yavas"
    return "ok"


async def _servis_durumlari(simdi_mono_us: int, simdi: float, http_yenile: bool = True) -> list[dict]:
    ozellikler = await _systemd_ozellikleri()
    onceki_cpu: dict = _onceki.get("servis_cpu", {})
    yeni_cpu: dict = {}

    async def http_kontrol(birim: str, port: int | None, yol: str | None) -> dict | None:
        if birim.startswith("postgresql"):
            return await _sql_prob()
        if birim == "chrony":
            return await _chrony_prob()
        if yol is None or port is None:
            return None
        prob = await asyncio.to_thread(_http_prob, f"http://127.0.0.1:{port}{yol}")
        return _http_sonucu(prob)

    satirlar = []
    for birim, etiket, yol in SERVISLER:
        oz = ozellikler.get(birim, {})
        durum = oz.get("ActiveState") or "bilinmiyor"
        aktif = durum == "active"
        pid = _tamsayi(oz.get("MainPID"))
        port = _port_bul(birim, oz.get("ExecStart", ""), oz.get("Environment", ""))
        bellek = _tamsayi(oz.get("MemoryCurrent"))
        cpu_ns = _tamsayi(oz.get("CPUUsageNSec"))
        baslangic_us = _tamsayi(oz.get("ActiveEnterTimestampMonotonic"))

        cpu_yuzde = None
        if cpu_ns is not None:
            yeni_cpu[birim] = (cpu_ns, simdi)
            eski = onceki_cpu.get(birim)
            if eski and simdi > eski[1] and cpu_ns >= eski[0]:
                # tek çekirdeğe göre yüzde (top/htop gibi) — 24 çekirdekte üst sınır %2400
                cpu_yuzde = round((cpu_ns - eski[0]) / ((simdi - eski[1]) * 1e9) * 100, 1)

        satirlar.append({
            "birim": birim,
            "etiket": etiket,
            "durum": durum,
            "aktif": aktif,
            "pid": pid if pid else None,
            "port": port,
            "cpu_yuzde": cpu_yuzde,
            "ram_mb": round(bellek / 1024**2) if bellek else None,
            "calisma_suresi": _sure_metni((simdi_mono_us - baslangic_us) / 1e6)
            if aktif and baslangic_us else None,
            "_yol": yol,
        })

    onceki_http: dict = _onceki.get("servis_http", {})
    http_sonuclari = await asyncio.gather(*(
        # önbellek yalnızca BAŞARILI sonuç için — düşen servis her turda yeniden
        # yoklanır, toparlanınca 15 sn içinde görünür (başarısız yoklama log yazmaz)
        (http_kontrol(s["birim"], s["port"], s["_yol"])
         if http_yenile or onceki_http.get(s["birim"], {}).get("durum") != "up"
         else asyncio.sleep(0, onceki_http[s["birim"]]))
        if s["aktif"] else asyncio.sleep(0, None)
        for s in satirlar
    ))
    _onceki["servis_http"] = {s["birim"]: h for s, h in zip(satirlar, http_sonuclari) if h is not None}
    for satir, http in zip(satirlar, http_sonuclari):
        satir.pop("_yol")
        satir["http"] = http
        satir["saglik"] = _saglik_etiketi(satir["aktif"], http)

    _onceki["servis_cpu"] = yeni_cpu
    # Ollama'nın hangi GPU'yu gördüğü (CUDA_VISIBLE_DEVICES, PCI sırası = nvidia-smi index)
    _onceki["gpu_eslesme"] = {
        birim: _ortam_degiskeni(oz.get("Environment", ""), "CUDA_VISIBLE_DEVICES")
        for birim, oz in ozellikler.items()
        if _ortam_degiskeni(oz.get("Environment", ""), "CUDA_VISIBLE_DEVICES")
    }
    return satirlar


# ---------- Uzak servisler (60 sn önbellek) ----------

def _uzak_kontrol(tanim: dict) -> dict:
    if tanim["yol"] is None:
        prob = _tcp_prob(tanim["host"], tanim["port"])
        yontem = "TCP"
    else:
        prob = _http_prob(f"http://{tanim['host']}:{tanim['port']}{tanim['yol']}")
        yontem = "HTTP"
    sonuc = _http_sonucu(prob, tanim["beklenen"])
    if sonuc["durum"] == "up":
        _uzak_son_basari[tanim["anahtar"]] = time.time()
    return {
        "anahtar": tanim["anahtar"],
        "ad": tanim["ad"],
        "makine": tanim["makine"],
        "adres": f"{tanim['host']}:{tanim['port']}",
        "yontem": yontem,
        "http": sonuc,
        "son_basari": _uzak_son_basari.get(tanim["anahtar"]),
        "saglik": "ok" if sonuc["durum"] == "up" else "hata",
    }


# ---------- AI / Ollama ----------

def _ollama_modelleri() -> list[str] | None:
    try:
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with acici.open(OLLAMA_API, timeout=3) as yanit:
            veri = json.loads(yanit.read())
        return [m.get("name", "?") for m in veri.get("models", [])]
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def _ollama_ps() -> dict:
    prob = _http_prob(OLLAMA_PS_API)
    if prob["kod"] != 200:
        return {"erisilebilir": False, "ms": None, "yuklu": []}
    try:
        veri = json.loads(prob["_govde"])
    except (json.JSONDecodeError, ValueError):
        return {"erisilebilir": False, "ms": prob["ms"], "yuklu": []}
    yuklu = []
    for m in veri.get("models", []):
        boyut = m.get("size") or 0
        vram = m.get("size_vram") or 0
        yuklu.append({
            "ad": m.get("name", "?"),
            "boyut_gb": round(boyut / 1e9, 2),
            "vram_gb": round(vram / 1e9, 2),
            "gpu_yuzde": round(100 * vram / boyut) if boyut else None,
            "context": m.get("context_length"),
            # KEEP_ALIVE=-1 → expires_at yüzyıllar sonrası (ör. 2319) = kalıcı yüklü
            "kalici": str(m.get("expires_at", ""))[:4].isdigit() and int(str(m["expires_at"])[:4]) > 2100,
        })
    return {"erisilebilir": True, "ms": prob["ms"], "yuklu": yuklu}


_GIN_RE = re.compile(r'\|\s*(\d{3})\s*\|\s*([\dµmsh.]+)\s*\|\s*([^|]*)\|\s*POST\s+"/api/(chat|generate)"')


def _sure_saniye(metin: str) -> float | None:
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?([\d.]+)(ms|µs|s)", metin.strip())
    if not m:
        return None
    deger = float(m.group(3))
    deger = deger / 1000 if m.group(4) == "ms" else deger / 1e6 if m.group(4) == "µs" else deger
    return deger + 60 * int(m.group(2) or 0) + 3600 * int(m.group(1) or 0)


async def _ollama_log_ozeti() -> dict | None:
    """Son 30 dk'nın GERÇEK istek süreleri — Ollama API'si aktif istek/kuyruk
    bilgisi vermiyor, bu yüzden journal'daki GIN satırlarından çıkarılır."""
    ham = await _komut("journalctl", "-u", "ollama", "--since", "-30min", "-o", "cat",
                       "--no-pager", zaman_asimi=6)
    if ham is None:
        return None
    sureler, yukleme, kirpma = [], 0, 0
    for satir in ham.splitlines():
        m = _GIN_RE.search(satir)
        if m:
            s = _sure_saniye(m.group(2))
            if s is not None:
                sureler.append(s)
        elif "load_tensors: loading model tensors" in satir:
            yukleme += 1
        elif "truncating input prompt" in satir:
            kirpma += 1
    sureler.sort()
    return {
        "istek_sayisi": len(sureler),
        "p50_sn": round(sureler[len(sureler) // 2], 2) if sureler else None,
        "maks_sn": round(sureler[-1], 2) if sureler else None,
        "model_yukleme": yukleme,
        "kirpilan_prompt": kirpma,
    }


# ---------- Veritabanı + RAG metrikleri (tek psql çağrısı) ----------

_DB_SORGU = """
SELECT json_build_object(
  'boyut_mb', round(pg_database_size('farabi') / 1048576.0),
  'baglanti', (SELECT count(*) FROM pg_stat_activity WHERE datname = 'farabi'),
  'aktif_baglanti', (SELECT count(*) FROM pg_stat_activity
                     WHERE datname = 'farabi' AND state = 'active' AND pid <> pg_backend_pid()),
  'maks_baglanti', current_setting('max_connections')::int,
  'uzun_sorgu', (SELECT count(*) FROM pg_stat_activity WHERE state = 'active'
                 AND pid <> pg_backend_pid() AND now() - query_start > interval '5 seconds'),
  'en_uzun_sorgu_sn', (SELECT round(coalesce(max(extract(epoch FROM now() - query_start)), 0)::numeric, 1)
                       FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()),
  'cache_hit', (SELECT round(100.0 * blks_hit / nullif(blks_hit + blks_read, 0), 2)
                FROM pg_stat_database WHERE datname = 'farabi'),
  'pgvector', (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
  'pgvector_calisiyor', ('[1,0]'::vector <=> '[1,0]'::vector) = 0,
  'rag_24s', (SELECT json_build_object(
      'n', count(*),
      'n_ok', count(*) FILTER (WHERE sonuc = 'ok'),
      'retrieval_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY retrieval_ms) FILTER (WHERE sonuc = 'ok'),
      'rerank_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY rerank_ms) FILTER (WHERE sonuc = 'ok'),
      'llm_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_toplam_ms) FILTER (WHERE sonuc = 'ok'),
      'toplam_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY toplam_ms) FILTER (WHERE sonuc = 'ok'),
      'toplam_p90', percentile_cont(0.9) WITHIN GROUP (ORDER BY toplam_ms) FILTER (WHERE sonuc = 'ok'))
    FROM metrik WHERE ts > now() - interval '24 hours'),
  'rag_7g', (SELECT json_build_object(
      'n', count(*),
      'n_ok', count(*) FILTER (WHERE sonuc = 'ok'),
      'retrieval_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY retrieval_ms) FILTER (WHERE sonuc = 'ok'),
      'rerank_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY rerank_ms) FILTER (WHERE sonuc = 'ok'),
      'llm_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_toplam_ms) FILTER (WHERE sonuc = 'ok'),
      'toplam_p50', percentile_cont(0.5) WITHIN GROUP (ORDER BY toplam_ms) FILTER (WHERE sonuc = 'ok'),
      'toplam_p90', percentile_cont(0.9) WITHIN GROUP (ORDER BY toplam_ms) FILTER (WHERE sonuc = 'ok'))
    FROM metrik WHERE ts > now() - interval '7 days'),
  'rag_son', (SELECT row_to_json(m) FROM (
      SELECT extract(epoch FROM ts)::bigint AS zaman, sonuc, retrieval_ms, rerank_ms,
             llm_toplam_ms, toplam_ms
      FROM metrik ORDER BY id DESC LIMIT 1) m),
  'rag_30dk', (SELECT coalesce(json_agg(json_build_array(extract(epoch FROM ts)::bigint, toplam_ms)
                                        ORDER BY ts), '[]'::json)
               FROM metrik WHERE ts > now() - interval '30 minutes' AND toplam_ms IS NOT NULL)
)
"""


async def _veritabani_bilgisi() -> dict:
    baslangic = time.perf_counter()
    ham = await _komut("psql", "-h", "127.0.0.1", "-U", "farabi", "-d", "farabi", "-AtqX",
                       "-c", _DB_SORGU)
    if not ham:
        return {"erisilebilir": False}
    try:
        veri = json.loads(ham)
    except json.JSONDecodeError:
        return {"erisilebilir": False}
    veri["erisilebilir"] = True
    veri["sorgu_ms"] = round((time.perf_counter() - baslangic) * 1000, 1)
    return veri


# ---------- Sağlık özeti ----------

def _ozet(mesajlar: list[tuple[str, str]]) -> dict:
    durum = "ok"
    if any(seviye == "hata" for seviye, _ in mesajlar):
        durum = "hata"
    elif any(seviye == "uyari" for seviye, _ in mesajlar):
        durum = "uyari"
    return {"durum": durum, "mesajlar": [m for _, m in mesajlar]}


def _esik(deger, uyari, hata, ad: str, birim: str, liste: list) -> None:
    if deger is None:
        return
    if deger >= hata:
        liste.append(("hata", f"{ad} {deger}{birim}"))
    elif deger >= uyari:
        liste.append(("uyari", f"{ad} {deger}{birim}"))


def _saglik_ozeti(v: dict) -> dict:
    sistem: list = []
    _esik(v["cpu"].get("sicaklik_c"), 80, 90, "CPU sıcaklığı", "°C", sistem)
    _esik(v["bellek"].get("yuzde"), 85, 95, "RAM", "%", sistem)
    _esik(v["disk"].get("yuzde"), 85, 95, "Disk", "%", sistem)
    for g in v["gpu"]:
        _esik(g["sicaklik_c"], 80, 88, f"GPU{g['index']} sıcaklığı", "°C", sistem)
    for d in v.get("disk_io", []):
        _esik(d["mesgul_yuzde"], 80, 95, f"{d['ad']} meşguliyet", "%", sistem)

    servis: list = []
    for s in v["servisler"]:
        if not s["aktif"]:
            servis.append(("hata", f"{s['etiket']}: {s['durum']}"))
        elif s["saglik"] == "hata":
            servis.append(("hata", f"{s['etiket']}: process ayakta, sağlık kontrolü başarısız"))
        elif s["saglik"] == "yavas":
            servis.append(("uyari", f"{s['etiket']}: yavaş yanıt ({s['http']['ms']} ms)"))

    ai: list = []
    o = v["ai"]
    if not o["erisilebilir"]:
        ai.append(("hata", "Ollama API'ye ulaşılamıyor"))
    elif not o["yuklu"]:
        ai.append(("uyari", "Model VRAM'da değil — ilk istek soğuk yükleme bekler (~3.5 sn)"))
    for m in o["yuklu"]:
        if m["gpu_yuzde"] is not None and m["gpu_yuzde"] < 100:
            ai.append(("uyari", f"{m['ad']} %{100 - m['gpu_yuzde']} CPU'ya taşmış"))
    log = o.get("log")
    if log and log["kirpilan_prompt"]:
        ai.append(("uyari", f"Son 30 dk'da {log['kirpilan_prompt']} prompt context sınırında kırpıldı"))

    db: list = []
    d = v["veritabani"]
    if not d.get("erisilebilir"):
        db.append(("hata", "PostgreSQL sorgusu başarısız"))
    else:
        if d.get("uzun_sorgu"):
            db.append(("uyari", f"{d['uzun_sorgu']} sorgu 5 sn'den uzun sürüyor"))
        if d.get("cache_hit") is not None and d["cache_hit"] < 95:
            db.append(("uyari", f"Cache hit %{d['cache_hit']}"))
        if not d.get("pgvector_calisiyor"):
            db.append(("hata", "pgvector çalışmıyor"))

    ag: list = []
    for u in v["uzak_servisler"]:
        if u["saglik"] != "ok":
            ag.append(("uyari", f"{u['ad']}: {u['http']['hata'] or 'erişilemiyor'}"))

    return {
        "sistem": _ozet(sistem),
        "servisler": _ozet(servis),
        "ai": _ozet(ai),
        "veritabani": _ozet(db),
        "ag": _ozet(ag),
    }


# ---------- Toplama ----------

async def _topla() -> dict:
    simdi = time.time()
    simdi_mono_us = int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1e6)

    yavas_yenile = simdi - _yavas_onbellek["zaman"] >= YAVAS_KONTROL_ARALIGI_SN
    yavas_gorevler = (
        asyncio.gather(*(asyncio.to_thread(_uzak_kontrol, t) for t in UZAK_SERVISLER)),
        _ollama_log_ozeti(),
        asyncio.to_thread(_ollama_modelleri),
        asyncio.to_thread(_ollama_ps),
    ) if yavas_yenile else ()

    cpu, gpu, servisler, veritabani, *yavas = await asyncio.gather(
        _cpu_bilgisi(),
        _gpu_bilgisi(),
        _servis_durumlari(simdi_mono_us, simdi, http_yenile=yavas_yenile),
        _veritabani_bilgisi(),
        *yavas_gorevler,
    )
    if yavas:
        _yavas_onbellek.update({"zaman": simdi, "uzak": list(yavas[0]), "ollama_log": yavas[1],
                                "modeller": yavas[2], "ollama_ps": yavas[3]})
    modeller = _yavas_onbellek["modeller"]
    ollama_ps = _yavas_onbellek["ollama_ps"]

    ollama_gpu = _onceki.get("gpu_eslesme", {}).get("ollama")
    ai = dict(ollama_ps)
    ai["log"] = _yavas_onbellek["ollama_log"]
    ai["gpu_index"] = int(ollama_gpu) if ollama_gpu and ollama_gpu.isdigit() else None
    ai["gpu"] = next((g for g in gpu if g["index"] == ai["gpu_index"]), None)
    ollama_servis = next((s for s in servisler if s["birim"] == "ollama"), None)
    ai["api_ms"] = ollama_servis["http"]["ms"] if ollama_servis and ollama_servis["http"] else None

    veri = {
        "olcum_zamani": simdi,
        "cpu": cpu,
        "gpu": gpu,
        "gpu_eslesme": _onceki.get("gpu_eslesme", {}),
        "bellek": _bellek_bilgisi(),
        "disk": _disk_bilgisi(),
        "servisler": servisler,
        "ollama_modelleri": modeller,
        "ai": ai,
        "veritabani": veritabani,
        "uzak_servisler": _yavas_onbellek["uzak"],
    }
    veri.update(_yukleme_ve_calisma_suresi())
    veri.update(_sayac_farklari(simdi))
    veri["saglik"] = _saglik_ozeti(veri)

    api = next((s for s in servisler if s["birim"] == "farabi-api"), None)
    _trend.append({
        "t": round(simdi),
        "cpu": veri["cpu_kullanim_yuzde"],
        "ram": veri["bellek"]["yuzde"],
        "gpu": {str(g["index"]): g["kullanim_yuzde"] for g in gpu},
        "vram": {str(g["index"]): round(100 * g["bellek_kullanim_mb"] / g["bellek_toplam_mb"])
                 for g in gpu if g["bellek_toplam_mb"]},
        "ollama_ms": ai["api_ms"],
        "api_ms": api["http"]["ms"] if api and api["http"] else None,
    })
    return veri


async def _topla_ve_kaydet() -> dict:
    global _son_olcum, _son_olcum_zamani
    async with _toplama_kilidi:
        if _son_olcum is not None and time.time() - _son_olcum_zamani < 1:
            return _son_olcum  # kilidi beklerken başkası zaten topladı
        _son_olcum = await _topla()
        _son_olcum_zamani = time.time()
        return _son_olcum


async def toplayici_dongusu() -> None:
    """Lifespan'da başlatılır. Hata olursa döngü ölmez (poller deseni, bkz. app.py)."""
    while True:
        try:
            await _topla_ve_kaydet()
        except Exception as e:  # noqa: BLE001 — izleme asla servisi düşürmemeli
            print(f"[sistem_durumu] toplama hatası: {e}")
        await asyncio.sleep(TOPLAMA_ARALIGI_SN)


def trend_verisi() -> list[dict]:
    return list(_trend)


async def durum_topla(trend: bool = False) -> dict:
    """Önbellekteki son ölçümü döner; önbellek yoksa/bayatsa hemen toplar."""
    if _son_olcum is None or time.time() - _son_olcum_zamani > BAYAT_SN:
        await _topla_ve_kaydet()
    veri = dict(_son_olcum)
    if trend:
        veri["trend"] = trend_verisi()
    return veri
