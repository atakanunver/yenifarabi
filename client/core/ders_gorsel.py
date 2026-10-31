"""core/ders_gorsel.py — Ders görseli için saf mantık ve durum makinesi.

Farabi UI ve PyQt6'dan tamamen bağımsızdır. Modül seviyesinde ve fonksiyon
içlerinde PyQt6 import edilmez.

Temel işlevler:
- 160x90 gri fark (int16 fark / 255.0)
- 64-bit yatay dHash
- Karar durum makinesi (aday tespiti, kararlılık süresi, son gönderilen benzerlik, kota, asgari aralık)
- Pencere politikası (aktif pencere, masaüstü/panel filtresi, Farabi tespiti, gizlilik filtresi)
- WebP kodlama (<= 960 px, q=60)
- HTTP gönderim (multipart image + metadata {"sira": n})
- 10 dakikalık servis metrikleri
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, features

# Gizlilik filtresi kalıpları (client/ui.py ile birebir uyumlu)
_EKRAN_GIZLI_KELIMELER = ("yoklama", "e-okul", "eokul", "mebbis", "tahtayoklama")
_TR_KUCUK_HARF = str.maketrans({"İ": "i", "I": "ı"})


PIKSEL_ESIGI = 24


def fark(a: np.ndarray, b: np.ndarray) -> float:
    """Belirgin değişen piksel oranı (0..1).

    Ortalama gri fark, benzer düzenli metin sayfalarının geçişinde (gerçek PDF'te
    0.017–0.027) eşiğin altında kalıyordu; değişen piksel oranı aynı geçişte 0.04–0.06.
    """
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("Kare boyutları uyuşmuyor")
    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIKSEL_ESIGI).mean())


def dhash(kare: np.ndarray) -> int:
    """Ek bağımlılık olmadan 64 bit yatay fark özeti."""
    if kare.ndim != 2 or min(kare.shape) < 9:
        raise ValueError("Geçersiz kare")
    y = np.linspace(0, kare.shape[0] - 1, 8, dtype=int)
    x = np.linspace(0, kare.shape[1] - 9 + 8, 9, dtype=int) if kare.shape[1] < 9 else np.linspace(0, kare.shape[1] - 1, 9, dtype=int)
    kucuk = kare[np.ix_(y, x)]
    bits = (kucuk[:, 1:] > kucuk[:, :-1]).ravel()
    sonuc = 0
    for bit in bits:
        sonuc = (sonuc << 1) | int(bit)
    return sonuc


@dataclass
class Karar:
    """Ders görseli kararlılık ve tekilleştirme durum makinesi."""
    degisim_esigi: float = 0.02
    benzerlik_esigi: float = 0.01
    hash_esigi: int = 4
    sabit_saniye: float = 5.0
    asgari_aralik: float = 30.0
    kota: int = 20

    def __post_init__(self) -> None:
        self.onceki: np.ndarray | None = None
        self.son_gonderilen: np.ndarray | None = None
        self.degisim_zamani: float | None = None
        self.son_gonderim: float | None = None
        self.adet = 0
        self.ders: object = None

    def sifirla(self, ders: object) -> None:
        self.__post_init__()
        self.ders = ders

    def incele(self, kare: np.ndarray, simdi: float, ders: object) -> bool:
        """Kareyi değerlendirir. Gönderim adayı ve kararlıysa True döndürür."""
        if kare.shape != (90, 160) or kare.dtype != np.uint8:
            raise ValueError("160x90 uint8 gri kare gerekli")
        if ders != self.ders:
            self.sifirla(ders)
        if self.onceki is None:
            self.onceki = kare.copy()
            self.degisim_zamani = simdi
            return False
        if fark(kare, self.onceki) >= self.degisim_esigi:
            self.onceki = kare.copy()
            self.degisim_zamani = simdi
            return False
        if self.degisim_zamani is None or (simdi - self.degisim_zamani) < self.sabit_saniye:
            return False
        if self.adet >= self.kota:
            return False
        if self.son_gonderim is not None and (simdi - self.son_gonderim) < self.asgari_aralik:
            return False
        if self.son_gonderilen is not None:
            fark_degeri = fark(kare, self.son_gonderilen)
            hash_farki = (dhash(kare) ^ dhash(self.son_gonderilen)).bit_count()
            if fark_degeri < self.benzerlik_esigi and hash_farki <= self.hash_esigi:
                return False
        return True

    def gonderildi(self, kare: np.ndarray, simdi: float, basarili: bool = True) -> None:
        """Gönderim denendiğinde referansı günceller.
        Başarılıysa adet artar, başarısızsa adet artmaz ama kare referans olur (tekrar denenmez).
        """
        self.son_gonderilen = kare.copy()
        self.son_gonderim = simdi
        if basarili:
            self.adet += 1

    def gonderim_basarisiz(self, kare: np.ndarray, simdi: float) -> None:
        """Başarısız gönderimde kareyi referans yapar; aynı aday tekrar denenmez."""
        self.gonderildi(kare, simdi, basarili=False)


def baslik_gizli_mi(baslik: str) -> bool:
    """Başlık gizlilik filtresine takılıyor mu?"""
    # TR çevirisi "MEBBİS"i yakalar ama ASCII "MEBBIS"i "mebbıs" yapar; ikisine de bak.
    ham = baslik or ""
    adaylar = (ham.translate(_TR_KUCUK_HARF).lower(), ham.lower())
    return any(k in b for b in adaylar for k in _EKRAN_GIZLI_KELIMELER)


def baslik_farabi_mi(baslik: str) -> bool:
    """Pencere başlığı Farabi'ye mi ait?"""
    b = (baslik or "").strip()
    return b.startswith(("FARABİ", "FARABI")) or b.lower().startswith("farabi")


def pid_farabi_mi(pid: int | None, cmdline_reader: Callable[[int], str] | None = None) -> bool:
    """Pencerenin ait olduğu süreç Farabi mi?"""
    if not pid or pid <= 0:
        return False
    try:
        if cmdline_reader is not None:
            cmd = cmdline_reader(pid)
            cwd = ""
        else:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode("utf-8", errors="replace")
            cwd = os.readlink(f"/proc/{pid}/cwd")
    except (OSError, UnicodeDecodeError):
        return False
    argv = [a for a in cmd.split("\0") if a]
    # farabi_start.sh `python3 main.py` ile client/ dizininden başlatır.
    return any(a.endswith("client/main.py") for a in argv) or (
        "main.py" in argv and cwd.rstrip("/").endswith("/client")
    )


def pencere_tipi_yasakli_mi(pencere_tipi: str) -> bool:
    """Masaüstü veya panel tipi pencere mi?"""
    yasaklar = ("_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK")
    return any(y in pencere_tipi for y in yasaklar)


@dataclass
class AktifPencere:
    win_id: str
    baslik: str = ""
    pencere_tipi: str = ""
    pid: int | None = None


def aktif_pencere_bilgisi(
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    timeout: float = 1.0,
) -> AktifPencere | None:
    """Aktif X11 pencere kimliği, başlığı, tipi ve PID bilgilerini xprop ile okur."""
    run_cmd = runner or subprocess.run
    try:
        root_res = run_cmd(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if root_res.returncode != 0:
            return None
        m_win = re.search(r"window id # (0x[0-9a-fA-F]+)", root_res.stdout)
        if not m_win:
            return None
        win_id = m_win.group(1)
        if int(win_id, 16) == 0:
            return None

        # Tip
        tip_res = run_cmd(
            ["xprop", "-id", win_id, "_NET_WM_WINDOW_TYPE"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        tip_str = tip_res.stdout if tip_res.returncode == 0 else ""

        # Başlık
        name_res = run_cmd(
            ["xprop", "-id", win_id, "_NET_WM_NAME"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        baslik = ""
        if name_res.returncode == 0:
            m_title = re.search(r'"(.*)"', name_res.stdout)
            if m_title:
                baslik = m_title.group(1)
        if not baslik:
            name_res2 = run_cmd(
                ["xprop", "-id", win_id, "WM_NAME"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if name_res2.returncode == 0:
                m_title2 = re.search(r'"(.*)"', name_res2.stdout)
                if m_title2:
                    baslik = m_title2.group(1)

        # PID
        pid = None
        pid_res = run_cmd(
            ["xprop", "-id", win_id, "_NET_WM_PID"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if pid_res.returncode == 0:
            m_pid = re.search(r"=\s*(\d+)", pid_res.stdout)
            if m_pid:
                pid = int(m_pid.group(1))

        return AktifPencere(win_id=win_id, baslik=baslik, pencere_tipi=tip_str, pid=pid)
    except (OSError, subprocess.SubprocessError):
        return None


def pencere_kabul_edilebilir_mi(
    pencere: AktifPencere | None,
    cmdline_reader: Callable[[int], str] | None = None,
) -> tuple[bool, str]:
    """Pencere yakalama şartlarına uyuyor mu?
    Dönüş: (kabul_mu, ret_nedeni)
    """
    if pencere is None or not pencere.win_id or int(pencere.win_id, 16) == 0:
        return False, "aktif_pencere_yok"
    if pencere_tipi_yasakli_mi(pencere.pencere_tipi):
        return False, "desktop_dock"
    if baslik_farabi_mi(pencere.baslik):
        return False, "farabi_onde"
    if pid_farabi_mi(pencere.pid, cmdline_reader=cmdline_reader):
        return False, "farabi_onde"
    if baslik_gizli_mi(pencere.baslik):
        return False, "gizlilik_filtresi"
    return True, "uygun"


def webp_destegi_var_mi() -> bool:
    """Pillow kütüphanesinin WebP desteğini doğrular."""
    try:
        return bool(features.check("webp"))
    except (ImportError, AttributeError, ValueError):
        return False


def webp_kodla(im: Image.Image, max_genislik: int = 960, kalite: int = 60) -> bytes:
    """Görüntüyü en çok max_genislik olacak şekilde orantılı küçültüp WebP kodlar."""
    if im.width > max_genislik:
        yeni_yukseklik = max(1, round(im.height * max_genislik / im.width))
        im = im.resize((max_genislik, yeni_yukseklik), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=kalite)
    return buf.getvalue()


def gonder(
    webp_bayt: bytes,
    sira: int,
    sunucu_url: str | None = None,
    headers: dict | None = None,
    timeout: float = 5.0,
    post_func: Callable[..., object] | None = None,
) -> bool:
    """Küçük WebP görüntüyü multipart POST /api/ders-gorsel'e gönderir.
    RAM'de en çok 1 tam kare tutulur, diske yazılmaz.
    """
    if sunucu_url is None:
        try:
            from core import tahta
            sunucu_url = tahta.sunucu_url()
        except (ImportError, AttributeError, KeyError, OSError):
            sunucu_url = "http://127.0.0.1:8000"

    if headers is None:
        try:
            from core import tahta
            headers = tahta.auth_headers()
        except (ImportError, AttributeError, KeyError, OSError):
            headers = {}

    url = f"{sunucu_url.rstrip('/')}/api/ders-gorsel"
    data = {"metadata": json.dumps({"sira": sira})}
    files = {"image": ("kare.webp", webp_bayt, "image/webp")}

    if post_func is not None:
        try:
            resp = post_func(url, data=data, files=files, headers=headers, timeout=timeout)
            if hasattr(resp, "status_code"):
                return 200 <= resp.status_code < 300
            return bool(resp)
        except (OSError, RuntimeError, ValueError):
            return False

    try:
        import requests
        resp = requests.post(
            url,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        return 200 <= resp.status_code < 300
    except (ImportError, OSError, RuntimeError, ValueError):
        return False


def get_rss_mib() -> float:
    """İşlemin RSS bellek miktarını MiB cinsinden döndürür."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return round(float(parts[1]) / 1024.0, 1)
    except (OSError, UnicodeDecodeError, ValueError, IndexError):
        # /proc okunamadıysa resource modülünü dene
        pass

    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
    except (ImportError, OSError, ValueError):
        return 0.0


@dataclass
class ServisMetrikleri:
    """10 dakikalık servis çalışma metrikleri toplayıcısı ve log üreticisi."""
    log_aralik_sn: float = 600.0
    son_log_zamani: float = field(default_factory=time.monotonic)
    tick_sayisi: int = 0
    atlananlar: dict[str, int] = field(default_factory=dict)
    aday_sayisi: int = 0
    gonderilen_sayisi: int = 0
    hata_sayisi: int = 0
    grab_sureleri: list[float] = field(default_factory=list)
    karsilastirma_sureleri: list[float] = field(default_factory=list)

    def tick_kaydet(self) -> None:
        self.tick_sayisi += 1

    def atla(self, neden: str) -> None:
        self.atlananlar[neden] = self.atlananlar.get(neden, 0) + 1

    def aday_kaydet(self) -> None:
        self.aday_sayisi += 1

    def gonderim_kaydet(self) -> None:
        self.gonderilen_sayisi += 1

    def hata_kaydet(self) -> None:
        self.hata_sayisi += 1

    def grab_sure_kaydet(self, ms: float) -> None:
        self.grab_sureleri.append(ms)

    def karsilastirma_sure_kaydet(self, ms: float) -> None:
        self.karsilastirma_sureleri.append(ms)

    def rapor_metni(self) -> str:
        grab_p50 = float(np.percentile(self.grab_sureleri, 50)) if self.grab_sureleri else 0.0
        grab_p95 = float(np.percentile(self.grab_sureleri, 95)) if self.grab_sureleri else 0.0
        kars_p95 = (
            float(np.percentile(self.karsilastirma_sureleri, 95))
            if self.karsilastirma_sureleri
            else 0.0
        )
        rss = get_rss_mib()
        atlanan_detay = (
            ", ".join(f"{k}: {v}" for k, v in sorted(self.atlananlar.items()))
            if self.atlananlar
            else "yok"
        )
        return (
            f"tick={self.tick_sayisi}, atlanan=({atlanan_detay}), "
            f"aday={self.aday_sayisi}, gönderilen={self.gonderilen_sayisi}, hata={self.hata_sayisi}, "
            f"grab_p50={grab_p50:.1f} grab_p95={grab_p95:.1f} "
            f"karsilastirma_p95={kars_p95:.1f} rss_mib={rss:.1f}"
        )

    def sifirla(self, simdi: float) -> None:
        self.son_log_zamani = simdi
        self.tick_sayisi = 0
        self.atlananlar.clear()
        self.aday_sayisi = 0
        self.gonderilen_sayisi = 0
        self.hata_sayisi = 0
        self.grab_sureleri.clear()
        self.karsilastirma_sureleri.clear()

    def kontrol_ve_raporla(self, simdi: float, zorla: bool = False) -> str | None:
        if zorla or (simdi - self.son_log_zamani >= self.log_aralik_sn):
            metin = self.rapor_metni()
            self.sifirla(simdi)
            return metin
        return None
