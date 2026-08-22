from __future__ import annotations

# Hazırlayan: MEB Atakan ÜNVER

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from core import zil
except Exception:      # zil.json yoksa arayüz çalışmaya devam etsin
    zil = None
try:
    from core import tahta
except Exception:
    tahta = None

from core import anahtar

import psutil

from PyQt6.QtCore import (
    QPointF, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
    QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()

# Tercih edilen boyut; gerçek boyut ekrana göre kısılır (bkz. _pencere_boyu).
# Önceki sabit 980x700 küçük/ölçekli ekranlarda taşıyordu.
_TERCIH_W, _TERCIH_H   = 980, 700
_MIN_W,     _MIN_H     = 788, 460   # 788 = sol 148 + sağ 340 + merkez
_LEFT_W  = 148
_RIGHT_W = 300

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# NOT (2026-08-14, server-taşıma): `_terminalde_calistir` ve onu çağıran
# `_TERMINALLER` listesi kaldırıldı — tek kullanım yeri, kaldırılan yerel
# içerik dönüştürme düğmeleriydi (KİTAPLARI METNE DÖNÜŞTÜR vb., bkz.
# _mikrofon_kalibre'nin altındaki not). Terminal açma ihtiyacı kalmadı.


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # HiDPI ölçeklemede mantıksal ekran küçülüyor (ör. 1104x590) ve
        # 300'lük dikey minimum tüm pencereyi ekranın dışına taşırıyordu.
        # HUD daralabilir; kırpılmasındansa küçülmesi yeğdir.
        self.setMinimumSize(200, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        # ── Animated GIF core (rendered in the centre of the HUD) ──────────────
        # Frames are pre-processed in a background thread so startup never freezes.
        # The black background of the GIF is keyed out (alpha = brightness) so only
        # the glowing ring shows and composites cleanly over the HUD.
        self._gif_raw: list[bytes] | None = None     # PNG bytes per frame (built off-thread)
        self._gif_durations: list[int]    = []        # ms per frame
        self._gif_pix: dict[int, QPixmap] = {}         # lazy QPixmap cache (main thread)
        self._gif_ready   = False
        self._gif_idx     = 0
        self._gif_acc     = 0.0                         # accumulated ms toward next frame
        self._load_gif_async(self._find_gif_path())

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    # ── Animated GIF support ──────────────────────────────────────────────────
    def _find_gif_path(self) -> str | None:
        """Merkez HUD animasyonunu bul (proje kökünde Farabi.gif)."""
        for name in ("Farabi.gif", "farabi.gif", "FARABI.gif", "face.gif"):
            cand = BASE_DIR / name
            if cand.exists():
                return str(cand)
        return None

    def _load_gif_async(self, path: str | None):
        if not path:
            return

        def worker():
            try:
                from PIL import Image, ImageSequence, ImageChops
                import io
                im      = Image.open(path)
                target  = 380                  # render size of each square frame
                raw, durs = [], []
                for frame in ImageSequence.Iterator(im):
                    f = frame.convert("RGBA")
                    w, h = f.size
                    s = min(w, h)              # centre-crop to a square
                    left, top = (w - s) // 2, (h - s) // 2
                    f = f.crop((left, top, left + s, top + s)).resize(
                        (target, target), Image.LANCZOS
                    )
                    # Key out black: alpha = max(r,g,b) → glow keeps its soft falloff
                    r, g, b, _ = f.split()
                    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
                    f.putalpha(mx)
                    buf = io.BytesIO(); f.save(buf, format="PNG")
                    raw.append(buf.getvalue())
                    durs.append(int(frame.info.get("duration", 70) or 70))
                self._gif_raw       = raw
                self._gif_durations = durs
                self._gif_ready     = bool(raw)
                print(f"[HUD] GIF ready: {len(raw)} frames")
            except Exception as e:
                print(f"[HUD] GIF load failed: {e}")
                self._gif_ready = False

        threading.Thread(target=worker, daemon=True).start()

    def _has_gif(self) -> bool:
        return bool(self._gif_ready and self._gif_raw)

    def _gif_pixmap(self, idx: int) -> QPixmap | None:
        """Lazily build (and cache) the QPixmap for a frame on the main thread."""
        if not self._gif_raw:
            return None
        px = self._gif_pix.get(idx)
        if px is None:
            px = QPixmap()
            px.loadFromData(self._gif_raw[idx])
            self._gif_pix[idx] = px
        return px

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0

        # advance the centre GIF based on the fixed 16 ms tick (smooth, drift-free)
        if self._has_gif():
            self._gif_acc += 16.0
            dur = self._gif_durations[self._gif_idx] if self._gif_durations else 70
            # speed the loop up a touch while speaking for an energetic feel
            if self.speaking:
                dur = max(30, int(dur * 0.7))
            if self._gif_acc >= dur:
                self._gif_acc = 0.0
                self._gif_idx = (self._gif_idx + 1) % len(self._gif_raw)

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31
        _gif   = self._has_gif()

        # halo glow (suppressed when the GIF ring is the centrepiece)
        if not _gif:
            for i in range(10):
                r   = r_face * (1.8 - i * 0.08)
                frc = 1.0 - i / 10
                a   = max(0, min(255, int(self._halo * 0.085 * frc)))
                col = qcol(C.MUTED_C if self.muted else C.PRI, a)
                p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings (hidden behind the GIF to keep the centre clean)
        if not _gif:
            for idx, (r_frac, w_r, arc_l, gap) in enumerate(
                [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
            ):
                ring_r = fw * r_frac
                base   = self._rings[idx]
                a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
                col    = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
                p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
                angle = base
                rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
                while angle < base + 360:
                    p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                    angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # centre element: animated GIF → static face → procedural orb (fallback chain)
        if _gif:
            gpx = self._gif_pixmap(self._gif_idx)
            if gpx is not None:
                gsz    = int(fw * 0.74 * self._scale)
                scaled = gpx.scaled(
                    gsz, gsz,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # mute tint: drop toward red by compositing when muted
                p.setOpacity(0.55 if self.muted else 1.0)
                p.drawPixmap(int(cx - gsz / 2), int(cy - gsz / 2), scaled)
                p.setOpacity(1.0)
        elif self._face_px:
            fsz    = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.27 * self._scale)
            oc    = (200, 0, 50) if self.muted else (0, 60, 110)
            for i in range(8, 0, -1):
                r2  = int(orb_r * i / 8)
                frc = i / 8
                a   = max(0, min(255, int(self._halo * 1.1 * frc)))
                p.setBrush(QBrush(QColor(int(oc[0]*frc), int(oc[1]*frc), int(oc[2]*frc), a)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(C.PRI, min(255, int(self._halo * 2))), 1))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 80, cy - 14, 160, 28),
                       Qt.AlignmentFlag.AlignCenter, "FARABİ")

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MİKROFON KAPALI", qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  ANLATIYOR",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  DÜŞÜNÜYOR",  qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  İŞLİYOR",    qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  DİNLİYOR",   qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif self.speaking:
                hgt = random.randint(3, 20)
                cl  = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl  = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

        # Akan altyazı (Gemini Live output_transcription parça parça gelir):
        # `_canli_pos`, o turun metninin belgede BAŞLADIĞI konumu tutar; her
        # güncellemede o konumdan belge sonuna kadarki metin SİLİNİP yeniden
        # yazılır — yazma-makinesi kuyruğu (`_queue`/`_step`) gibi yeni satır
        # AÇILMAZ. main.py, transkripsiyon parçası geldikçe bunu çağırır;
        # sonuç ses çalınmadan ÖNCE ekranda okunabilir olur (bkz. main.py
        # _receive_audio, 2026-08-11 karar: "önce metin, sonra ses").
        self._canli_pos    = None
        self._canli_prefix = ""

    def append_log(self, text: str):
        self._sig.emit(text)

    def canli_satir_baslat(self, prefix: str) -> None:
        """Akan altyazı için yeni, boş bir satır aç. `prefix` ör. 'Farabi: '."""
        # Yazma-makinesi kuyruğunda bekleyen bir şey varsa önce onu bitir —
        # aksi hâlde canlı satır, henüz yazılmamış eski bir satırın ortasına
        # karışır.
        self._queue.clear()
        self._typing = False
        self._tmr.stop()

        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        if self.toPlainText() and not self.toPlainText().endswith("\n"):
            cur.insertText("\n")
        self._canli_prefix = prefix
        fmt = cur.charFormat()
        fmt.setForeground(QBrush(qcol(C.PRI)))
        cur.insertText(prefix, fmt)
        self._canli_pos = cur.position()
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def canli_satir_guncelle(self, metin_simdiye_kadar: str) -> None:
        """Akan satırın içeriğini büyüt — `canli_satir_baslat` çağrılmadıysa
        kendisi başlatır (savunma; main.py normalde önce başlatır)."""
        if self._canli_pos is None:
            self.canli_satir_baslat(self._canli_prefix or "Farabi: ")
        cur = self.textCursor()
        cur.setPosition(self._canli_pos)
        cur.movePosition(cur.MoveOperation.End, cur.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        fmt = cur.charFormat()
        fmt.setForeground(QBrush(qcol(C.PRI)))
        cur.insertText(metin_simdiye_kadar, fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def canli_satir_bitir(self) -> None:
        """Turu kapat: sonraki satırın bu akan satıra karışmaması için \\n ekler."""
        if self._canli_pos is None:
            return
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText("\n")
        self.setTextCursor(cur)
        self._canli_pos = None

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("farabi:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    """
    Tek satırlık dosya ekle düğmesi. Eskiden 100px'lik çizilmiş bir
    sürükle-bırak paneliydi (dashed border animasyonu, dosya kartı vb.) —
    sağ panelde diğer araç düğmeleriyle birlikte yer sıkıştırıyordu.
    Sürükle-bırak hâlâ çalışır (widget'ın tamamı kabul eder), sadece görsel
    ağırlığı gitti. current_file()/clear_file() imzası aynı kaldı — main.py
    ve FarabiUI.current_file bu widget'a değişmeden bağlı.
    """
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._current_file: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._btn = QPushButton("📎  DOSYA EKLE")
        self._btn.setFixedHeight(26)
        self._btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                padding: 2px 6px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.PRI}; border: 1px solid {C.PRI_DIM};
                                 background: {C.PRI_GHO}; }}
        """)
        self._btn.clicked.connect(self._browse)
        layout.addWidget(self._btn)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._btn.setText("📎  DOSYA EKLE")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Farabi için dosya seç", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        name  = Path(path).name
        short = name if len(name) <= 22 else name[:19] + "..."
        self._btn.setText(f"📎  {short}")
        self.file_selected.emit(path)


class _CizilebilirGorsel(QLabel):
    """PDF/YKS sayfası gösteren QLabel — üstüne parmakla/kalemle çizim ve
    silgi desteği (2026-08-14 eklendi, Faz 11).

    Yalnızca dokunmatik KALEM/SİLGİ/TEMİZLE düğmeleriyle (bkz. MainWindow
    `_cizim_modu_ayarla`) açılıp kapanır — SESLİ KOMUTLA AÇILMAZ, `actions/
    kayit.py`'ye bir tool olarak EKLENMEDİ (kullanıcı kararı: yanlış ses
    tanıma tetiklemesi riski taşımasın). Model bu katmanın varlığından
    habersizdir, salt öğretmenin dokunmatik etkileşimidir.

    GEÇİCİ: kaydedilmez. `taban_ayarla()` her yeni sayfa/zoom değişiminde
    (bkz. MainWindow._olcekle_goruntu) çağrılır ve önceki çizimi sıfırlar —
    bilinçli, kalıcılık istenmedi (kullanıcı kararı). Zoom sırasında çizim
    kaybolur; bu bir kısıt değil, "geçici" tasarımın doğal sonucu.
    """

    KALEM_RENK     = QColor("#ff3355")
    KALEM_KALINLIK = 4
    SILGI_KALINLIK = 28

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.cizim_modu: str = "kapali"   # "kapali" | "kalem" | "silgi"
        self._taban_pixmap: QPixmap | None = None
        self._son_nokta = None

    def taban_ayarla(self, pixmap: QPixmap) -> None:
        """Yeni/yeniden ölçeklenmiş TEMİZ sayfa görüntüsünü ayarlar — silginin
        geri döneceği referans budur. Önceki çizim (varsa) burada kaybolur."""
        self._taban_pixmap = QPixmap(pixmap)
        self.setPixmap(pixmap)
        self._son_nokta = None

    def temizle(self) -> None:
        if self._taban_pixmap is not None:
            self.setPixmap(QPixmap(self._taban_pixmap))

    def mousePressEvent(self, e):
        if self.cizim_modu == "kapali" or self.pixmap() is None:
            super().mousePressEvent(e)
            return
        self._son_nokta = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self.cizim_modu == "kapali" or self.pixmap() is None or self._son_nokta is None:
            super().mouseMoveEvent(e)
            return
        yeni = e.position().toPoint()
        pm = QPixmap(self.pixmap())
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.cizim_modu == "kalem":
            p.setPen(QPen(self.KALEM_RENK, self.KALEM_KALINLIK,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawLine(self._son_nokta, yeni)
        elif self._taban_pixmap is not None:
            # Silgi: iz üzerindeki alanı TEMİZ tabandan geri kopyalar
            # (saydamlaştırma değil — sayfa görüntüsünün alfa kanalı yok).
            yol = QPainterPath()
            yol.moveTo(QPointF(self._son_nokta))
            yol.lineTo(QPointF(yeni))
            genisletici = QPainterPathStroker()
            genisletici.setWidth(self.SILGI_KALINLIK)
            genisletici.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setClipPath(genisletici.createStroke(yol))
            p.drawPixmap(0, 0, self._taban_pixmap)
        p.end()
        self.setPixmap(pm)
        self._son_nokta = yeni

    def mouseReleaseEvent(self, e):
        if self.cizim_modu == "kapali":
            super().mouseReleaseEvent(e)
        self._son_nokta = None


class MainWindow(QMainWindow):
    _log_sig     = pyqtSignal(str)
    _state_sig   = pyqtSignal(str)
    _content_sig = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _image_content_sig = pyqtSignal(str, str)  # (title, image_path) — thread-safe image display
    _mute_sig    = pyqtSignal(bool)       # thread-safe mute toggle (asyncio loop thread → Qt thread)
    _gemini_oturum_sig = pyqtSignal(bool)  # True: Live oturumu açıldı, False: kapandı
    _live_baslat_sig = pyqtSignal(str)    # akan altyazı: yeni satır başlat (prefix, ör. "Farabi: ")
    _live_guncelle_sig = pyqtSignal(str)  # akan altyazı: satırın içeriğini büyüt (yeni satır AÇMADAN)
    _live_bitir_sig = pyqtSignal()        # akan altyazı: turu kapat (asyncio loop thread → Qt thread)
    _oto_baslat_sig = pyqtSignal()        # otomatik başlatma tetiği (asyncio loop thread → Qt thread)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("FARABİ — Yapay Zekâ Öğretmen")
        self.setMinimumSize(_MIN_W, _MIN_H)

        # Ekrana sığdır. Kullanılabilir alan HiDPI ölçeklemede beklenenden
        # çok küçük olabiliyor: geliştirme makinesinde 2208x1242 fiziksel
        # ekran, 2x ölçekle 1104x590 MANTIKSAL alana düşüyor. Eski sabit
        # 980x700 bu yüzden ekranın dışına taşıyordu.
        ekran = QApplication.primaryScreen().availableGeometry()
        g = min(_TERCIH_W, max(_MIN_W, int(ekran.width()  * 0.94)))
        y = min(_TERCIH_H, max(_MIN_H, int(ekran.height() * 0.94)))
        # Hiçbir koşulda ekranı aşma — kırpılmaktansa küçül.
        g = min(g, ekran.width())
        y = min(y, ekran.height())
        self.resize(g, y)
        # Ekranın kendi konumunu da hesaba kat (çoklu monitör)
        self.move(ekran.x() + (ekran.width()  - g) // 2,
                  ekran.y() + (ekran.height() - y) // 2)

        self.on_text_command  = None
        # Öğretmen paneli komutları — main.py bunu bağlar; bağlanmazsa komut
        # normal metin yolundan gider (panel her hâlükârda çalışır).
        self.on_teacher_command = None
        # Dersi öğretmen başlatır (çift tık). main.py bunu bağlar; bağlanmazsa
        # düğme sessizce hiçbir şey yapmaz, arayüz yine çalışır.
        self.on_session_start = None
        # Ders dili — DERSİ BAŞLAT'tan ÖNCE seçilir. Gemini Live'da bir
        # bağlantının system_instruction'ı bağlantı kurulduktan sonra
        # değiştirilemez, bu yüzden ders başladıktan sonra bu değer okunmaz
        # (main.py yalnız _build_config() içinde, ilk bağlantıdan önce okur).
        # Varsayılan "tr" — hiçbir dil düğmesine basılmazsa mevcut davranış.
        self.ders_dili: str = "tr"
        self._kazanim_metni: str = ""
        self._duraklatildi: bool = False
        # Günün plan adayları — "dersi değiştir" bunlardan seçtirir.
        self._ders_adaylari: list[str] = []
        self._muted           = False
        self._current_file: str | None = None

        # Gemini Live kullanım göstergesi (HUD, sol panel). Gerçek kota SDK
        # üzerinden okunamıyor (bkz. CLAUDE.md "Provider notes ve API kotası"
        # — bu yüzden gerçek "kalan" değil, kendi ölçtüğümüz bir tahmin: bu
        # süreç içinde bugün açık kalan oturumların toplam süresi. Gün
        # değişince sıfırlanır; süreç yeniden başlarsa da sıfırlanır (henüz
        # diske yazılmıyor — kalıcı bir bütçe/dashboard talep gelirse eklenir).
        self._gunluk_kullanim_tarih     = time.strftime("%Y-%m-%d")
        self._gunluk_kullanim_toplam_sn = 0.0
        self._oturum_baslangic_ts: float | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # Center column: HUD on top + Ders Kaydı (activity log) below — the
        # big central display. The content panel ("bilgi ekranı") now lives
        # in the right sidebar corner instead, see _build_right_panel.
        _center = QWidget()
        _center.setStyleSheet(f"background: {C.BG};")
        _center_lay = QVBoxLayout(_center)
        _center_lay.setContentsMargins(0, 0, 0, 0)
        _center_lay.setSpacing(0)
        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # HUD orb capped: it used to fill everything not claimed by the
        # (usually-hidden) content panel, so any real content — a book
        # page, an exam question with şıklar — got squeezed into a strip
        # a few lines tall. The centre column is becoming a presentation
        # surface; the orb is a status indicator on top of it, not the
        # main event.
        self.hud.setMaximumHeight(320)
        _center_lay.addWidget(self.hud, stretch=0)
        _center_lay.addWidget(self._build_log_panel(), stretch=1)
        body.addWidget(_center, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._image_content_sig.connect(self._show_image)
        self._mute_sig.connect(self._set_muted)
        self._gemini_oturum_sig.connect(self._on_gemini_oturum_degisti)
        self._live_baslat_sig.connect(self._log.canli_satir_baslat)
        self._live_guncelle_sig.connect(self._log.canli_satir_guncelle)
        self._live_bitir_sig.connect(self._log.canli_satir_bitir)
        self._oto_baslat_sig.connect(self._dersi_baslat)

        self._ready = self._check_config()
        if not self._ready:
            self._log.append_log(
                "ERR: config/api_keys.json yok ya da geçerli bir Gemini anahtarı "
                "içermiyor. Otomatik kurulum penceresi kaldırıldı — dosyayı elle "
                "oluşturun: config/api_keys.example.json'ı config/api_keys.json "
                "olarak kopyalayıp gemini_api_keys alanını doldurun, sonra Farabi'yi "
                "yeniden başlatın.")

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_close_content = QShortcut(QKeySequence("Escape"), self)
        sc_close_content.activated.connect(self._content_panel.hide)

    # NOT (2026-08-14, server-taşıma): İçerik hazırlık kontrolü ve kitaplar.json
    # tazeleme buradan kaldırıldı — PDF→metin dönüşümü, indeksleme ve kitap
    # kataloğu artık tamamen server tarafında (`server/icerik.py`,
    # `/mnt/farabi-data/farabi/`), tek bir yerde, tüm tahtalar için bir kez
    # yapılıyor. Bu tahtanın kendi `kitaplar/`/`icerik/` dizinleri artık yok
    # (Kural 1: client ince kalmalı) — burada tekrar taramanın hiçbir faydası
    # kalmadı.

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event) -> None:
        """Pencere kapanınca (X, Alt+F4, WM) arka planda main.py'nin asenkron
        oturum döngüsü ayrı bir iş parçacığında çalışmaya devam ediyordu ve
        artık var olmayan bu pencereye `set_state`/`write_log` ile dokunmaya
        çalışıyordu — `RuntimeError: wrapped C/C++ object ... has been
        deleted`. Bu, o anki TaskGroup'u çökertip yeniden-bağlanma döngüsüne
        düşüyordu; her deneme aynı ölü pencereye dokunup aynı hatayı tekrar
        üretiyordu, süreç CPU yakan ama hiçbir log basmayan, öğretmenin hiçbir
        düğmesinin (DURDUR/DEVAM/DERSİ BAŞLAT dahil, çünkü pencere zaten yok)
        işe yaramadığı bir hayalet halde askıda kalıyordu (canlı tahtada
        gözlemlendi, 2026-08-17). Pencere kapanınca süreç de TAMAMEN kapanmalı;
        `_temiz_kapan`'ın kullandığı `os._exit` kaçınma gerekçesi (transkript
        yazımını atlar) burada geçerli değil — kullanıcı zaten pencereyi
        kapatarak oturumu bitiriyor, tamamlanmamış bir transkript kapanışı
        askıda kalan bir süreçten daha iyi bir sonuç."""
        os._exit(0)

    def _gunluk_kullanim_gunu_kontrol(self):
        """Gün değiştiyse bugünkü toplamı sıfırlar (açık bir oturum varsa
        ondan bu yana geçen süreyi kaybetmeden, şimdiden yeniden saymaya
        başlar)."""
        bugun = time.strftime("%Y-%m-%d")
        if bugun != self._gunluk_kullanim_tarih:
            self._gunluk_kullanim_tarih     = bugun
            self._gunluk_kullanim_toplam_sn = 0.0
            if self._oturum_baslangic_ts is not None:
                self._oturum_baslangic_ts = time.time()

    def _on_gemini_oturum_degisti(self, acildi: bool):
        """main.py'nin oturum_baslandi()/oturum_kapandi() bildirimleri —
        asyncio döngü iş parçacığından sinyal yoluyla gelir (Qt widget'larına
        doğrudan başka bir iş parçacığından dokunulamaz)."""
        self._gunluk_kullanim_gunu_kontrol()
        if acildi:
            self._oturum_baslangic_ts = time.time()
        elif self._oturum_baslangic_ts is not None:
            self._gunluk_kullanim_toplam_sn += time.time() - self._oturum_baslangic_ts
            self._oturum_baslangic_ts = None

        # DERSİ BAŞLAT ısınma göstergesi — yalnız öğretmen düğmeye zaten
        # basmışsa (düğme kilitliyse) metni günceller; ders hiç
        # başlatılmadan gelen bir bildirimde (olmaz ama savunma) dokunmaz.
        if not self._baslat_btn.isEnabled():
            if acildi:
                self._baslat_btn.setText("▶▶  DERS BAŞLADI")
            else:
                self._baslat_btn.setText("🔄  YENİDEN BAĞLANIYOR…")

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")

        self._gunluk_kullanim_gunu_kontrol()
        toplam_sn = self._gunluk_kullanim_toplam_sn
        if self._oturum_baslangic_ts is not None:
            toplam_sn += time.time() - self._oturum_baslangic_ts
        h, m = int(toplam_sn // 3600), int((toplam_sn % 3600) // 60)
        self._gemini_sure_lbl.setText(f"BUGÜN  {h:02d}:{m:02d}")

        try:
            n = anahtar.adet()
            self._gemini_anahtar_lbl.setText(
                f"ANAHTAR  {anahtar.durum()}" if n else "ANAHTAR  —")
        except Exception:
            self._gemini_anahtar_lbl.setText("ANAHTAR  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge("MUALLİM-İ SÂNÎ", C.PRI_DIM))
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        title_row = QHBoxLayout(); title_row.setSpacing(6)
        title_row.addStretch()
        flag = QLabel("🇹🇷")
        flag.setFont(QFont("Noto Color Emoji", 13))
        flag.setStyleSheet("background: transparent;")
        title_row.addWidget(flag)
        title = QLabel("FARABİ")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        title_row.addWidget(title)
        title_row.addStretch()
        mid.addLayout(title_row)
        sub = QLabel("Yapay Zekâ Öğretmen Yardımcısı")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _zaman_guncelle(self):
        """Saat, tarih ve kaçıncı ders satırlarını yeniler (saniyede bir)."""
        import time as _t
        self._saat_lbl.setText(_t.strftime("%H:%M:%S"))
        if zil is None:
            self._tarih_lbl.setText("")
            self._ders_lbl.setText("")
            return
        try:
            self._tarih_lbl.setText(zil.tarih_metni())
            durum = zil.ders_durumu()
            self._ders_lbl.setText(durum.get("kisa", ""))
            # Ders sırasında yeşil, ders dışında soluk
            renk = C.GREEN if durum.get("tur") == "ders" else C.TEXT_DIM
            self._ders_lbl.setStyleSheet(
                f"color: {renk}; background: transparent; border: none;")
        except Exception:
            pass

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SİSTEM")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)

        # ── Tarih / saat / kaçıncı ders ────────────────────────────────────
        lay.addSpacing(4)
        zaman_panel = QWidget()
        zaman_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        # Sıkışmaya karşı taban yükseklik: dört satır (derslik, saat, tarih,
        # ders) üst üste binip okunamaz hale geliyordu.
        zaman_panel.setMinimumHeight(104)
        zp = QVBoxLayout(zaman_panel)
        zp.setContentsMargins(6, 5, 6, 5)
        zp.setSpacing(2)

        derslik_ad = tahta.etiket() if tahta else ""
        self._derslik_lbl = QLabel(derslik_ad)
        self._derslik_lbl.setFont(QFont("Courier New", 17, QFont.Weight.Bold))
        renk = C.ACC if derslik_ad and "TANIMSIZ" not in derslik_ad else "#ff6688"
        self._derslik_lbl.setStyleSheet(
            f"color: {renk}; background: transparent; border: none;")
        self._derslik_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._derslik_lbl.setToolTip("Bu tahtanın bulunduğu derslik "
                                     "(config/api_keys.json -> derslik)")
        zp.addWidget(self._derslik_lbl)

        ayirici = QLabel("")
        ayirici.setFixedHeight(1)
        ayirici.setStyleSheet(f"background: {C.BORDER}; border: none;")
        zp.addWidget(ayirici)
        zp.addSpacing(2)

        self._saat_lbl = QLabel("--:--:--")
        self._saat_lbl.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        self._saat_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        self._saat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zp.addWidget(self._saat_lbl)

        self._tarih_lbl = QLabel("")
        self._tarih_lbl.setFont(QFont("Courier New", 7))
        self._tarih_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._tarih_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tarih_lbl.setWordWrap(True)
        zp.addWidget(self._tarih_lbl)

        self._ders_lbl = QLabel("")
        self._ders_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._ders_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        self._ders_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ders_lbl.setWordWrap(True)
        zp.addWidget(self._ders_lbl)

        lay.addWidget(zaman_panel)
        self._zaman_guncelle()
        self._zaman_tmr = QTimer(self)
        self._zaman_tmr.timeout.connect(self._zaman_guncelle)
        self._zaman_tmr.start(1000)

        # ── Gemini kullanım göstergesi ───────────────────────────────────
        # Gerçek API kotası SDK üzerinden okunamıyor (bkz. CLAUDE.md);
        # BUGÜN satırı bu süreçte bugün açık kalan Live oturumlarının
        # toplam süresi, ANAHTAR satırı core/anahtar.py havuzunda hangi
        # anahtarın aktif olduğu ("2/10" gibi) — ikisi de tahmin/durum
        # bilgisi, kesin "kalan kota" değil.
        lay.addSpacing(4)
        gemini_panel = QWidget()
        gemini_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        gp = QVBoxLayout(gemini_panel)
        gp.setContentsMargins(6, 5, 6, 5)
        gp.setSpacing(3)

        gp_hdr = QLabel("◈ GEMINI")
        gp_hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        gp_hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        gp.addWidget(gp_hdr)

        self._gemini_sure_lbl = QLabel("BUGÜN  --")
        self._gemini_sure_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._gemini_sure_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        self._gemini_sure_lbl.setToolTip(
            "Bu süreçte bugün açık kalan Gemini Live oturumlarının toplam "
            "süresi — gerçek API kotası değil, yerel bir kullanım göstergesi.")
        gp.addWidget(self._gemini_sure_lbl)

        self._gemini_anahtar_lbl = QLabel("ANAHTAR  --")
        self._gemini_anahtar_lbl.setFont(QFont("Courier New", 8))
        self._gemini_anahtar_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._gemini_anahtar_lbl.setToolTip(
            "config/api_keys.json havuzunda aktif anahtar sırası "
            "(core/anahtar.py) — kaç anahtar tanımlı, şu an hangisi kullanılıyor.")
        gp.addWidget(self._gemini_anahtar_lbl)

        lay.addWidget(gemini_panel)

        lay.addStretch()

        # Alttaki üç dekoratif rozet ("YAPAY ZEKÂ AKTİF" / "BAĞLANTI GÜVENLİ" /
        # "MUALLİM-İ SÂNÎ") kaldırıldı: ~100 piksel dikey yer yiyorlardı ve
        # hiçbir bilgi taşımıyorlardı — "BAĞLANTI GÜVENLİ" doğrulanmış bir
        # durum bile değildi. HiDPI ekranda (kullanılabilir yükseklik 590)
        # o yer derslik/saat/ders paneline gerekiyor; bilgi dekorasyondan
        # önce gelir. Durum göstergesi zaten HUD'un altında.
        return w

    def _build_log_panel(self) -> QWidget:
        """Ders Kaydı — activity log, now the big central display."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 6, 12, 8)
        lay.setSpacing(5)

        hdr = QLabel("▸ DERS KAYDI")
        hdr.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(hdr)

        self._log = LogWidget()
        self._log.setFont(QFont("Courier New", 12))
        lay.addWidget(self._log, stretch=1)
        return w

    def _arac_dugmesi(self, lay, metin: str) -> QPushButton:
        """Sağ paneldeki içerik-hazırlık düğmelerinin ortak görünümü
        (kalibrasyon, kitap/YKS dönüştürme, sembol temizleme, özet çıkarma)."""
        btn = QPushButton(metin)
        btn.setFixedHeight(26)
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.ACC2};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border: 1px solid {C.BORDER_B}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; }}
        """)
        lay.addWidget(btn)
        return btn

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        # Bilgi ekranı (content panel) artık burada değil — tam ekran bir
        # overlay olarak central widget'a bağlı, bkz. _build_content_panel.
        # Eskiden sağ sidebar'ın köşesinde ~300px'lik kompakt bir kutuydu;
        # YKS geçmiş sorular gibi uzun metinler orada okunamıyordu ("küçük ve
        # görünmez geliyor").
        self._content_panel = self._build_content_panel()

        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("Dosya yok")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep_ogr = QFrame(); sep_ogr.setFrameShape(QFrame.Shape.HLine)
        sep_ogr.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep_ogr)

        lay.addWidget(_sec("ÖĞRETMEN PANELİ"))
        lay.addLayout(self._build_ogretmen_paneli())

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("ÖĞRETMEN GİRİŞİ  ·  YAZILAN = TALİMAT"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("🎙  MİKROFON AÇIK")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        self._kalibre_btn = self._arac_dugmesi(lay, "📊  MİKROFONU KALİBRE ET")
        self._kalibre_btn.clicked.connect(self._mikrofon_kalibre)

        # NOT (2026-08-14, server-taşıma): "KİTAPLARI METNE DÖNÜŞTÜR", "YKS
        # SORULARINI METNE DÖNÜŞTÜR", "ŞÜPHELİ SEMBOLLERİ TEMİZLE", "KİTAP
        # ÖZETİ ÇIKAR" düğmeleri kaldırıldı — bu tahtanın artık kendi
        # kitaplar/YKS/icerik dizini yok, tüm içerik hazırlama tek noktadan
        # (server/) yapılıyor, tahta başına tetiklenen bir şey değil.


        fs_btn = QPushButton("⛶  TAM EKRAN  [F11]")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    # ── Öğretmen paneli ────────────────────────────────────────────────────
    #
    # Öğretmen dersin sahibidir; Farabi'yi istediği anda yönlendirebilmeli.
    # Buradaki her düğme oturuma [ÖĞRETMEN KOMUTU] etiketli bir talimat
    # gönderir. Etiket şart: aynı cümleyi bir öğrenci de yazabilir, ama
    # "cevabı göster" komutu yalnızca öğretmenden gelirse üç adım kuralını
    # geçersiz kılar (core/prompt.txt, ÖĞRETMEN KOMUTLARI bölümü).
    #
    # Mikrofon susturma bilerek buraya konmadı: zaten mute düğmesi ve F4 var,
    # aynı işi yapan ikinci bir denetim karışıklık üretir.
    # Panelde YALNIZCA iki düğme var: durdur ve devam et.
    #
    # Karar: dersi sanal öğretmen planlar ve anlatır; 40 dakikanın akışı
    # onundur. Öğretmenin sürekli müdahale etmesi gereken bir sistem, zaten
    # işini yapmıyor demektir. Konu/kazanım/ders değiştirme düğmeleri de
    # kaldırıldı — bunlar gerektiğinde giriş kutusuna yazılır ve zaten
    # [ÖĞRETMEN KOMUTU] olarak gider.
    #
    # Durdur/devam düğme olarak kalır çünkü acil olduğu an klavyeye yazacak
    # vakit yoktur: sınıfa biri girer, telefon çalar, öğrenci fenalaşır.
    OGRETMEN_KOMUTLARI = [
        ("⏸  DURDUR", "durdur",
         "Dersi burada duraklat. Konuşmayı bitir, yeni konu açma, soru sorma "
         "ve sessizce bekle. 'Devam et' denene kadar kendiliğinden devam etme."),
        ("▶  DEVAM ET", "devam",
         "Derse devam et. Tek cümleyle bağla ve sürdür; sınıfa ne yaptığınızı "
         "sorma."),
    ]

    def _build_ogretmen_paneli(self) -> QGridLayout:
        izgara = QGridLayout()
        izgara.setSpacing(4)
        stil = f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                padding: 2px 4px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.PRI}; border: 1px solid {C.PRI_DIM};
                                 background: {C.PRI_GHO}; }}
            QPushButton:pressed {{ background: {C.PRI_DIM}; color: {C.DARK}; }}
        """
        self._ogretmen_btn_stili = stil
        self._ogretmen_btns: dict[str, QPushButton] = {}
        for i, (etiket, anahtar, _) in enumerate(self.OGRETMEN_KOMUTLARI):
            b = QPushButton(etiket)
            b.setFixedHeight(26)
            b.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(stil)
            b.clicked.connect(lambda _=False, a=anahtar: self._ogretmen_komutu(a))
            izgara.addWidget(b, i // 2, i % 2)
            self._ogretmen_btns[anahtar] = b

        # ── DERSİ BAŞLAT ─────────────────────────────────────────────────────
        # Panelde bilerek yalnızca DURDUR/DEVAM ET vardı; bu üçüncü düğmenin
        # gerekçesi ayrı: oturum artık kendiliğinden açılmıyor, çünkü açık
        # duran canlı ses oturumu ücretli ve tahta gece/tatil bağlı kalıyordu.
        #
        # ÇİFT tıklama isteniyor, tek tık değil: tahta dokunmatik ve sınıftaki
        # herhangi bir öğrenci geçerken tek tıkla ders başlatabilirdi.
        self._baslat_btn = QPushButton("▶▶  DERSİ BAŞLAT  (çift tıkla)")
        self._baslat_btn.setFixedHeight(30)
        self._baslat_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._baslat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._baslat_btn.setStyleSheet(stil + f"""
            QPushButton {{ color: {C.ACC}; border: 1px solid {C.ACC}; }}
        """)
        # Tek tık bilerek bağlanmıyor; yalnızca çift tık başlatır.
        self._baslat_btn.mouseDoubleClickEvent = (
            lambda _e: self._dersi_baslat())
        izgara.addWidget(self._baslat_btn, 1, 0, 1, 2)

        # ── Ders dili ─────────────────────────────────────────────────────
        # DERSİ BAŞLAT'tan ÖNCE seçilir — bkz. self.ders_dili tanımındaki not
        # (system_instruction bağlantı kurulduktan sonra değiştirilemez).
        # Seçili olmayan hâl Türkçe'dir; mevcut davranış hiç dokunulmadan
        # aynı kalır. Basılı düğme vurgulanır, DERSİ BAŞLAT'tan sonra ikisi
        # de kilitlenir (dil artık değişemez).
        self._dil_btns: dict[str, QPushButton] = {}
        for etiket, kod in [("🇬🇧  İNGİLİZCE", "en"), ("🇩🇪  ALMANCA", "de")]:
            b = QPushButton(etiket)
            b.setFixedHeight(24)
            b.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kod: self._ders_dili_sec(k))
            self._dil_btns[kod] = b
        izgara.addWidget(self._dil_btns["en"], 2, 0)
        izgara.addWidget(self._dil_btns["de"], 2, 1)
        self._dil_dugmelerini_boya()
        return izgara

    def _dil_dugmelerini_boya(self) -> None:
        secili_stil = f"""
            QPushButton {{
                background: {C.PRI}; color: {C.DARK};
                border: none; border-radius: 3px; font-weight: bold;
            }}
        """
        for kod, b in self._dil_btns.items():
            b.setStyleSheet(secili_stil if self.ders_dili == kod else self._ogretmen_btn_stili)

    def _ders_dili_sec(self, kod: str) -> None:
        # Aynı düğmeye ikinci basış Türkçeye (varsayılana) döner.
        self.ders_dili = "tr" if self.ders_dili == kod else kod
        self._dil_dugmelerini_boya()
        gorunen = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca"}[self.ders_dili]
        self._log.append_log(f"SYS: Ders dili — {gorunen}.")

    def _dersi_baslat(self) -> None:
        """Öğretmen çift tıkladı — oturumu başlat ve düğmeyi kapat.

        Düğme metni ANINDA "DERS BAŞLADI" oluyordu, ama Gemini Live bağlantısı
        o an henüz açılmamış oluyordu (`main.py.run()` bağlantıyı arka plan
        iş parçacığında kurar, birkaç saniye sürebilir) — öğretmen "başladı"
        yazısını görüyor, Farabi ise hâlâ sessiz bağlanıyordu. Sınıfta bu
        "gecikme" gibi hissediliyordu. Şimdi düğme önce ISINIYOR'da bekler;
        gerçekten "DERS BAŞLADI" yazısı yalnız oturum fiilen açıldığında
        (`_on_gemini_oturum_degisti`, main.py'nin `oturum_baslandi()`
        bildirimiyle) görünür."""
        if not self.on_session_start:
            # Sessiz return öğretmeni kör ederdi; log'a yaz ki bağlanmamış
            # callback (FarabiUI köprüsü unutulursa) hemen görünsün.
            self._log.append_log(
                "SYS: DERSİ BAŞLAT tıklandı ama oturum henüz hazır değil.")
            return
        self._baslat_btn.setEnabled(False)
        self._baslat_btn.setText("⏳  ISINIYOR…")
        for b in self._dil_btns.values():          # dil artık değişemez, bkz. yukarıdaki not
            b.setEnabled(False)
        self._log.append_log("SYS: Ders başlatılıyor (öğretmen) — bağlanılıyor…")
        threading.Thread(target=self.on_session_start, daemon=True).start()

    def _durdur_gorunumu(self) -> None:
        """Duraklatılmışken DURDUR düğmesi yanar, DEVAM ET öne çıkar."""
        durdur = self._ogretmen_btns.get("durdur")
        devam  = self._ogretmen_btns.get("devam")
        if not durdur or not devam:
            return
        if self._duraklatildi:
            durdur.setText("⏸  DURAKLATILDI")
            durdur.setStyleSheet(durdur.styleSheet() +
                                 f"QPushButton {{ color: {C.ACC2}; }}")
            devam.setStyleSheet(devam.styleSheet() +
                                f"QPushButton {{ color: {C.PRI}; "
                                f"border: 1px solid {C.PRI}; }}")
        else:
            durdur.setText("⏸  DURDUR")
            durdur.setStyleSheet(self._ogretmen_btn_stili)
            devam.setStyleSheet(self._ogretmen_btn_stili)

    def _ogretmen_komutu(self, anahtar: str) -> None:
        """Panel düğmesi → oturuma öğretmen talimatı."""
        metin = dict((a, m) for _, a, m in self.OGRETMEN_KOMUTLARI).get(anahtar)
        veri: dict = {}

        if not metin:
            return

        # Duraklatma görünür olmalı: öğretmen dersin durduğunu ekrandan
        # görmeli, Farabi'nin susmasından tahmin etmemeli.
        self._duraklatildi = (anahtar == "durdur")
        self._durdur_gorunumu()

        etiketli = f"[ÖĞRETMEN KOMUTU] {metin}"
        self._log.append_log(f"ÖĞRETMEN: {metin[:70]}")
        if self.on_teacher_command:
            threading.Thread(target=self.on_teacher_command,
                             args=(anahtar, etiketli, veri), daemon=True).start()
        elif self.on_text_command:
            threading.Thread(target=self.on_text_command,
                             args=(etiketli,), daemon=True).start()

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Talimat yaz…  (öğretmen)")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Bilgi ekranı — ders_icerigi/web_search/yks_sorulari/site_goster
        sonuçları. TAM EKRAN bir overlay: central widget'ın doğrudan çocuğu,
        hiçbir layout'a eklenmez — konumu _show_content()/resizeEvent()
        içinde elle central.rect()'e eşitlenir ve raise_() ile öne alınır.

        Eskiden sağ sidebar'ın köşesinde ~300px'lik kompakt bir kutuydu;
        YKS geçmiş sorular gibi uzun/okunması gereken metinler orada
        "küçük ve görünmez" kalıyordu — bir sınıfın önünde tahtadan okunacak
        büyüklükte değildi. show_content() aracın (actions/*.py) kendi
        fonksiyonu içinde, model konuşmaya başlamadan ÖNCE senkron çağrılıyor
        (bkz. actions/yks_sorulari.py, ders_icerigi.py) — bu yüzden sırayı
        değiştirmeye gerek yok, sadece görünür/büyük hâle getirmek yetti.

        Varsayılan gizli.
        """
        w = QWidget(self.centralWidget())
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.DARK};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 18, 28, 22)
        lay.setSpacing(10)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(8)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont("Courier New", 9))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        # Sağ üstte, belirgin — asıl şikayet konusu buydu: eski ✕ 20x18px'ti
        # ve köşede kayboluyordu.
        dismiss = QPushButton("✕  KAPAT")
        dismiss.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        dismiss.setFixedHeight(32)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 0 12px;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.RED}; background: #3a0f14; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        # Tam ekran, büyük font — tahtadan okunacak (özellikle YKS sorularının
        # tam metni). Eski 9pt sidebar boyutundan kalkıldı.
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont("Courier New", 15))
        self._content_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL2};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 16px 22px;
                line-height: 1.5;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 10px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 5px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display, stretch=1)

        # ── image display (pdf_sayfa) ────────────────────────────────────────
        # Aynı overlay'i metinle paylaşır — ikisi asla aynı anda görünmez,
        # _show_content/_show_image birbirini kapatır. QLabel + setPixmap:
        # QTextEdit'in aksine görüntüyü olduğu gibi (yeniden akış olmadan)
        # gösterir — PDF sayfasındaki şekil/tablo bozulmasın diye. QScrollArea
        # içine alınmış: yakınlaştırılan bir sayfa panelden taşınca kaydırma
        # çubukları/dokunmatik kaydırmayla gezilebilsin (tahtada bir soruyu
        # rahat göstermek için — 2026-08-12 istek).
        zoom_row = QHBoxLayout(); zoom_row.setSpacing(6)
        self._resim_uzaklastir_btn = QPushButton("−")
        self._resim_sigdir_btn     = QPushButton("⛶ SIĞDIR")
        self._resim_yakinlastir_btn = QPushButton("+")
        for b, genislik in ((self._resim_uzaklastir_btn, 44),
                            (self._resim_sigdir_btn, 104),
                            (self._resim_yakinlastir_btn, 44)):
            b.setFixedSize(genislik, 30)
            b.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL}; color: {C.TEXT};
                    border: 1px solid {C.BORDER_B}; border-radius: 4px;
                }}
                QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM};
                                     background: {C.PRI_GHO}; }}
            """)
            zoom_row.addWidget(b)
        zoom_row.addStretch()

        # ── Kalem/Silgi/Temizle (2026-08-14, Faz 11) ────────────────────────
        # Yalnızca dokunmatik buton — sesli komutla açılmaz (kullanıcı kararı).
        # Basılı olan mod vurgulanır (kendi kendini/diğerini kapatan toggle).
        def _arac_btn_stili(aktif: bool) -> str:
            if aktif:
                return (f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                        f"border: 1px solid {C.PRI}; border-radius: 4px; }}")
            return (f"QPushButton {{ background: {C.PANEL}; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER_B}; border-radius: 4px; }} "
                    f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; "
                    f"background: {C.PRI_GHO}; }}")
        self._cizim_arac_btn_stili = _arac_btn_stili

        self._kalem_btn  = QPushButton("✏  KALEM")
        self._silgi_btn  = QPushButton("🧹  SİLGİ")
        self._cizim_temizle_btn = QPushButton("🗑  TEMİZLE")
        for b in (self._kalem_btn, self._silgi_btn, self._cizim_temizle_btn):
            b.setFixedSize(88, 30)
            b.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_arac_btn_stili(False))
            zoom_row.addWidget(b)
        self._kalem_btn.clicked.connect(lambda: self._cizim_modu_ayarla("kalem"))
        self._silgi_btn.clicked.connect(lambda: self._cizim_modu_ayarla("silgi"))
        self._cizim_temizle_btn.clicked.connect(self._cizim_temizle)

        self._image_zoom_row = QWidget()
        self._image_zoom_row.setLayout(zoom_row)
        self._image_zoom_row.hide()
        self._resim_uzaklastir_btn.clicked.connect(self._resim_uzaklastir)
        self._resim_sigdir_btn.clicked.connect(self._resim_sigdir)
        self._resim_yakinlastir_btn.clicked.connect(self._resim_yakinlastir)
        lay.addWidget(self._image_zoom_row)

        self._image_display = _CizilebilirGorsel()
        self._image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._image_scroll = QScrollArea()
        self._image_scroll.setWidgetResizable(False)
        self._image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_scroll.setWidget(self._image_display)
        self._image_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px; }}
            QScrollBar:vertical {{ background: {C.BG}; width: 10px; border: none; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 5px; min-height: 24px; }}
            QScrollBar:horizontal {{ background: {C.BG}; height: 10px; border: none; }}
            QScrollBar::handle:horizontal {{ background: {C.BORDER_B}; border-radius: 5px; min-width: 24px; }}
        """)
        self._image_scroll.hide()
        self._scroller_aktif = False
        try:
            # Dokunmatik tahtada parmakla sürükleyerek kaydırma — yalnızca
            # kaydırma çubuğunu tutmak yerine, görüntünün HERHANGİ bir
            # yerinden sürüklenebilsin.
            #
            # NOT (2026-08-15, canlı testte bulundu): bu gesture aktifken
            # KALEM/SİLGİ hiç çalışmıyordu — QScroller viewport üzerindeki
            # tüm sol-tık sürükleme olaylarını kaydırma jesti için yakalayıp
            # `_CizilebilirGorsel.mousePressEvent/mouseMoveEvent`'e hiç
            # ulaştırmıyor. Çözüm: çizim modu açıldığında `ungrabGesture` ile
            # geçici olarak bırakılıyor, kapatılınca `grabGesture` ile geri
            # alınıyor — bkz. `_cizim_modu_ayarla`. `_scroller_aktif` bu
            # ungrab/grab çağrılarının güvenle yapılabileceğini işaretler
            # (QScroller kurulamadıysa ikisi de atlanır).
            from PyQt6.QtWidgets import QScroller
            QScroller.grabGesture(self._image_scroll.viewport(),
                                  QScroller.ScrollerGestureType.LeftMouseButtonGesture)
            self._scroller_aktif = True
        except Exception:
            pass  # dokunmatik kaydırma olmadan da kaydırma çubukları çalışır
        self._image_pixmap_ham: QPixmap | None = None
        self._image_zoom: float | None = None   # None = genişliğe sığdır (varsayılan)
        lay.addWidget(self._image_scroll, stretch=1)

        hint = QLabel("[ESC]  ya da  ✕ KAPAT  ile ekranı kapat")
        hint.setFont(QFont("Courier New", 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(hint)

        return w

    def _position_content_panel(self):
        """Overlay'i central widget'ın tamamına eşitler. show_content() ve
        resizeEvent() ikisinden de çağrılır — pencere yeniden boyutlanırken
        overlay açık kalmışsa geride kalmasın diye."""
        self._content_panel.setGeometry(self.centralWidget().rect())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._content_panel.isVisible():
            self._position_content_panel()
            if self._image_scroll.isVisible() and self._image_zoom is None:
                # Yalnızca hâlâ "sığdır" modundaysa yeniden hesapla — kullanıcı
                # elle yakınlaştırdıysa (zoom artık None değil) pencere yeniden
                # boyutlanınca seçtiği zoom seviyesi ELİNDEN ALINMAMALI.
                self._olcekle_goruntu()

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel
        as a full-screen overlay, above the HUD/log panel/sidebars."""
        import time as _time
        self._image_zoom_row.hide()
        self._image_scroll.hide()
        self._cizim_modu_ayarla("kapali")  # metne geçince çizim modu kapanır
        self._content_display.show()
        self._content_title_lbl.setText(title.upper()[:32])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        # Scroll to top
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        self._position_content_panel()
        self._content_panel.raise_()
        self._content_panel.show()

    def _olcekle_goruntu(self):
        """Ham pixmap'i `self._image_zoom` oranında yeniden çizer.

        `_image_zoom is None` → "sığdır" modu: panel GENİŞLİĞİNE göre oran
        hesaplanır (yükseklik kaydırmayla gezilir — sayfalar genelde
        portre). Bir sayı verildiğinde (+/- düğmeleri) o oranda sabit kalır;
        görüntü panelden taşarsa QScrollArea kaydırma çubuklarını/dokunmatik
        kaydırmayı kendiliğinden gösterir.
        """
        if self._image_pixmap_ham is None:
            return
        viewport_genislik = self._image_scroll.viewport().width()
        if viewport_genislik <= 1:
            return
        if self._image_zoom is None:
            oran = viewport_genislik / self._image_pixmap_ham.width()
        else:
            oran = self._image_zoom
        hedef_genislik = max(50, int(self._image_pixmap_ham.width() * oran))
        olcekli = self._image_pixmap_ham.scaledToWidth(
            hedef_genislik, Qt.TransformationMode.SmoothTransformation)
        # taban_ayarla (setPixmap değil): silginin geri döneceği TEMİZ
        # referansı da günceller, önceki çizimi sıfırlar (zoom değiştiyse
        # eski ölçekteki çizim zaten anlamsız kalırdı — bkz. _CizilebilirGorsel).
        self._image_display.taban_ayarla(olcekli)
        self._image_display.resize(olcekli.size())

    def _resim_yakinlastir(self):
        taban = self._image_zoom
        if taban is None and self._image_pixmap_ham is not None:
            # "sığdır" modundan çıkarken o anki fiili oranı taban al —
            # aksi hâlde ilk tıkta genişliğe-sığdırdan değil 1.0'dan
            # başlayıp beklenmedik bir sıçrama olurdu.
            vp = self._image_scroll.viewport().width()
            taban = vp / self._image_pixmap_ham.width() if vp > 1 else 1.0
        self._image_zoom = min(4.0, (taban or 1.0) * 1.25)
        self._olcekle_goruntu()

    def _resim_uzaklastir(self):
        taban = self._image_zoom or 1.0
        self._image_zoom = max(0.25, taban / 1.25)
        self._olcekle_goruntu()

    def _resim_sigdir(self):
        self._image_zoom = None
        self._olcekle_goruntu()

    def _cizim_modu_ayarla(self, mod: str):
        """KALEM/SİLGİ düğmesine basıldı — aynı moda tekrar basmak KAPATIR
        (toggle), farklı bir moda basmak geçiş yapar. Yalnızca dokunmatik
        buton; sesli komutla tetiklenmez (bkz. _CizilebilirGorsel dokümanı)."""
        yeni_mod = "kapali" if self._image_display.cizim_modu == mod else mod
        self._image_display.cizim_modu = yeni_mod
        self._kalem_btn.setStyleSheet(self._cizim_arac_btn_stili(yeni_mod == "kalem"))
        self._silgi_btn.setStyleSheet(self._cizim_arac_btn_stili(yeni_mod == "silgi"))

        # QScroller'ın sol-tık sürükleme jesti çizimle ÇAKIŞIYOR — aktifken
        # mouse olayları _image_display'e hiç ulaşmıyordu (2026-08-15, canlı
        # testte bulundu). Çizim modundayken jest geçici bırakılır, kapanınca
        # geri alınır.
        if not self._scroller_aktif:
            return
        from PyQt6.QtWidgets import QScroller
        viewport = self._image_scroll.viewport()
        if yeni_mod == "kapali":
            QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        else:
            QScroller.ungrabGesture(viewport)

    def _cizim_temizle(self):
        self._image_display.temizle()

    def _show_image(self, title: str, image_path: str):
        """Slot — runs on Qt main thread. `pdf_sayfa` aracının render ettiği
        PNG'yi aynı tam-ekran overlay'de gösterir (metin panelinin yerine),
        zoom +/- düğmeleri ve kaydırılabilir bir alan içinde."""
        import time as _time
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._log_sig.emit(f"ERR: PDF sayfa görüntüsü yüklenemedi — {image_path}")
            return
        self._image_pixmap_ham = pixmap
        self._image_zoom = None  # her yeni sayfa "sığdır" ile başlar
        self._content_display.hide()
        self._image_zoom_row.show()
        self._image_scroll.show()
        self._content_title_lbl.setText(title.upper()[:32])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._position_content_panel()
        self._content_panel.raise_()
        self._content_panel.show()
        # setGeometry() sonrası viewport boyutu SENKRON bitmeyebilir — ilk
        # gösterimde .width() eski/sıfır dönebilir. Olay döngüsüne bir tık
        # bırakıp öyle ölçekle (diğer ertelenmiş UI güncellemeleriyle aynı
        # desen, bkz. _kalibre_mikrofon).
        QTimer.singleShot(0, self._olcekle_goruntu)

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mikrofon  ·  [F11] Tam Ekran"))
        lay.addStretch()
        lay.addWidget(_fl("FARABİ  ·  SINIF ÖĞRETMEN ASİSTANI"))
        lay.addStretch()
        lay.addWidget(_fl("MUALLİM-İ SÂNÎ", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Farabi'ye ne yapacağını söyle")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _mikrofon_kalibre(self):
        """
        Mikrofon kalibrasyonu: önce sessizlik, sonra konuşma ölçülür ve oran
        raporlanır. Mutlak eşik kullanılmaz — gürültü tabanı her tahtada ve
        her kazanç ayarında farklı (bkz. tools/mikrofon_test.py).

        Ölçüm arka planda yapılır; arayüz donmaz. Sonuç içerik panelinde.
        """
        self._kalibre_btn.setEnabled(False)
        self._kalibre_btn.setText("… ÖLÇÜLÜYOR")
        self._log.append_log("SYS: Mikrofon kalibrasyonu başladı.")

        def _bitti(basli: str, metin: str):
            self._content_sig.emit(basli, metin)
            self._kalibre_btn.setEnabled(True)
            self._kalibre_btn.setText("📊  MİKROFONU KALİBRE ET")

        def _calis():
            try:
                import numpy as _np, sounddevice as _sd
            except Exception as e:
                # `e`, except bloğu bitince Python tarafından otomatik silinir
                # (CPython: `del e`) — QTimer.singleShot ile ERTELENEN lambda
                # çalıştığında `e` artık yok, "free variable" NameError'ı
                # fırlatıyordu (ölçüldü, pyflakes + manuel tekrar üretim,
                # 2026-08-11). Mesajı düz bir stringe önceden çevirip lambda'ya
                # ONU vermek gerekiyor.
                hata = str(e)
                self._log_sig.emit(f"ERR: kalibrasyon — ses kütüphanesi yok ({hata})")
                QTimer.singleShot(0, lambda: _bitti(
                    "MİKROFON KALİBRASYONU", f"Ses kütüphanesi yüklenemedi: {hata}"))
                return

            def _olc(sn):
                r = _sd.rec(int(sn * 16000), samplerate=16000, channels=1,
                            dtype="int16")
                _sd.wait()
                d = _np.asarray(r, dtype=_np.float64).flatten()
                # Akış açılışındaki "pop" ölçümü bozuyor — ilk 0.3 sn atılır
                d = d[4800:] if d.size > 9600 else d
                return float(_np.sqrt((d ** 2).mean())), int(_np.abs(d).max())

            try:
                self._log_sig.emit("SYS: 1/2 — SESSİZ KALIN (4 saniye)")
                taban, _ = _olc(4)
                self._log_sig.emit("SYS: 2/2 — ŞİMDİ KONUŞUN (5 saniye)")
                ses, ses_tepe = _olc(5)
            except Exception as e:
                hata = str(e)          # bkz. yukarıdaki `_calis` — aynı "free variable" nedeni
                self._log_sig.emit(f"ERR: kalibrasyon — mikrofon açılamadı ({hata})")
                QTimer.singleShot(0, lambda: _bitti(
                    "MİKROFON KALİBRASYONU", f"Mikrofon açılamadı: {hata}"))
                return

            oran = ses / taban if taban > 0 else float("inf")
            satir = [
                f"Gürültü tabanı : rms {int(taban)}",
                f"Konuşma        : rms {int(ses)}   tepe {ses_tepe}",
                f"Oran           : {oran:.1f}x",
                "",
            ]
            if ses_tepe >= 32000:
                satir += ["SONUÇ: KIRPILMA — kazanç çok yüksek, sinyal bozuluyor.",
                          "  pactl set-source-volume @DEFAULT_SOURCE@ 70%"]
                kisa = "KIRPILMA"
            elif oran >= 3.0 and ses >= 1500:
                satir += ["SONUÇ: MİKROFON İYİ. Bu tahta derse hazır."]
                kisa = f"İYİ ({oran:.1f}x)"
            elif oran >= 3.0:
                satir += [f"SONUÇ: Ses ayrışıyor ama seviye düşük (rms {int(ses)};",
                          "sağlıklı aralık 1500-8000). Transkripsiyon zayıf olabilir.",
                          "Harici mikrofon önerilir (CLAUDE.md, Mikrofon bölümü)"]
                kisa = f"ZAYIF ({oran:.1f}x)"
            else:
                satir += ["SONUÇ: Konuşma ortam sesinden AYRIŞMIYOR.",
                          "Bu tahta derse hazır değil. Kontrol:",
                          "  1) Donanım mikrofon anahtarı",
                          "  2) pactl get-source-mute @DEFAULT_SOURCE@",
                          "  3) Harici mikrofon (CLAUDE.md, Mikrofon bölümü)"]
                kisa = f"YETERSİZ ({oran:.1f}x)"

            self._log_sig.emit(f"SYS: Mikrofon kalibrasyonu — {kisa}")
            QTimer.singleShot(0, lambda: _bitti(
                "MİKROFON KALİBRASYONU", "\n".join(satir)))

        threading.Thread(target=_calis, daemon=True).start()

    # NOT (2026-08-14, server-taşıma): `_terminalde_donustur`,
    # `_kitaplari_donustur`, `_yks_donustur`, `_api_calisan_dugmeyi_baslat`,
    # `_sembolleri_temizle`, `_kitap_ozeti_cikar` buradan kaldırıldı — hepsi
    # bu tahtanın artık var olmayan yerel `kitaplar/`/`YKS/`/`icerik/`
    # dizinlerine karşı `tools/*.py` script'lerini terminal'de çalıştıran
    # düğme handler'larıydı. İçerik hazırlama artık tamamen server'da,
    # tek bir yerde (bkz. docs/mimari.md, server/icerik.py).

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Mikrofon kapatıldı.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Mikrofon açıldı.")

    def _set_muted(self, v: bool):
        """Slot for `_mute_sig` — lets code running off the Qt thread (the
        asyncio session loop) request a mute change without touching widgets
        directly."""
        if v != self._muted:
            self._toggle_mute()

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MİKROFON KAPALI")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 3px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MİKROFON AÇIK")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _send(self):
        """
        Klavyeden gelen her giriş ÖĞRETMENDEN sayılır.

        Sınıfta klavye tahtanın başındadır; öğrenci sesle konuşur, yazan kişi
        öğretmendir. Bu yüzden yazılan metin bir öğrenci sorusu gibi değil,
        [ÖĞRETMEN KOMUTU] etiketiyle TALİMAT olarak gider — Farabi tartışmadan
        uygular (core/prompt.txt, ÖĞRETMEN KOMUTLARI).
        """
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"ÖĞRETMEN: {txt}")
        etiketli = f"[ÖĞRETMEN KOMUTU] {txt}"
        hedef = self.on_teacher_command or self.on_text_command
        if hedef is self.on_teacher_command and hedef:
            threading.Thread(target=hedef, args=("yazili", etiketli, None),
                             daemon=True).start()
        elif hedef:
            threading.Thread(target=hedef, args=(etiketli,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        """
        config/api_keys.json'da kullanılabilir bir Gemini anahtarı var mı?

        core.anahtar.anahtarlar() ile aynı okuma yolunu kullanır — hem
        `gemini_api_keys` (havuz) hem eski tekil `gemini_api_key` alanını
        kabul eder. Eskiden yalnızca tekil alan + `os_system` aranıyordu ve
        bir İLK KURULUM penceresi eksikse dosyayı SIFIRDAN yazıyordu; bu,
        elle doldurulmuş `derslik`/`ders_kipi`/anahtar havuzunu sessizce
        siliyordu. Artık dosya yalnızca elle düzenlenir — bkz.
        config/api_keys.example.json; burada hiçbir şey yazılmaz.
        """
        try:
            from core import anahtar
            return anahtar.adet() > 0
        except Exception:
            return False

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class FarabiUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        # Signal, not a direct call: this setter is also reached from the
        # asyncio session loop thread (e.g. auto-mute on YouTube playback),
        # and `_toggle_mute` touches Qt widgets directly — must run on the
        # Qt thread.
        self._win._mute_sig.emit(bool(v))

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def oto_baslat(self):
        """
        PİLOT/TEST AŞAMASI (2026-08-15): tahta açılır açılmaz dersi otomatik
        başlatır, öğretmenin DERSİ BAŞLAT'a çift tıklamasını beklemez.
        Asyncio döngü iş parçacığından çağrılır; Qt widget'larına o
        iş parçacığından doğrudan dokunulamayacağı için sinyal üzerinden
        `MainWindow._dersi_baslat`'a (çift tıkla ile AYNI kod yolu — buton/dil
        kilitleme davranışı korunur) kuyruklanır.
        """
        self._win._oto_baslat_sig.emit()

    def canli_satir_baslat(self, prefix: str = "Farabi: "):
        self._win._live_baslat_sig.emit(prefix)

    def canli_satir_guncelle(self, metin_simdiye_kadar: str):
        self._win._live_guncelle_sig.emit(metin_simdiye_kadar)

    def canli_satir_bitir(self):
        self._win._live_bitir_sig.emit()

    def oturum_baslandi(self):
        """Gemini Live oturumu açıldı — HUD'daki BUGÜN sayacı başlasın."""
        self._win._gemini_oturum_sig.emit(True)

    def oturum_kapandi(self):
        """Oturum kapandı (yeniden bağlanma ya da ders bitişi) — geçen süre
        bugünkü toplama eklensin. Hiç açılmamış bir oturum için de güvenle
        çağrılabilir (main.py'nin finally bloğu her zaman çağırır)."""
        self._win._gemini_oturum_sig.emit(False)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    @property
    def on_teacher_command(self):
        return self._win.on_teacher_command

    @on_teacher_command.setter
    def on_teacher_command(self, cb):
        self._win.on_teacher_command = cb

    # on_text_command / on_teacher_command ile aynı köprü. Eskiden yoktu:
    # main.py `ui.on_session_start = …` yazıyor, düğme ise MainWindow'daki
    # alanı okuyordu — callback hiç ulaşmadığı için çift tık sessizce
    # hiçbir şey yapmıyordu (DURDUR/DEVAM çalışıyor, BAŞLAT çalışmıyor).
    @property
    def on_session_start(self):
        return self._win.on_session_start

    @on_session_start.setter
    def on_session_start(self, cb):
        self._win.on_session_start = cb

    @property
    def ders_dili(self) -> str:
        """'tr' (varsayılan) | 'en' | 'de' — DERSİ BAŞLAT'tan önce panelde
        seçilir, main.py yalnız ilk bağlantıda (_build_config) okur."""
        return self._win.ders_dili

    def set_ders_adaylari(self, adlar: list[str]) -> None:
        """Öğretmen panelindeki 'dersi değiştir' seçeneklerini doldur."""
        self._win._ders_adaylari = list(adlar or [])

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_image(self, title: str, image_path: str):
        """Thread-safe: display a rendered PDF page (pdf_sayfa) in the same
        full-screen overlay `show_content` uses, as an image instead of text."""
        self._win._image_content_sig.emit(title[:48], image_path)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")