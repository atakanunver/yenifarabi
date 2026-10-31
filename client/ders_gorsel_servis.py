"""ders_gorsel_servis.py — Bağımsız ekran gözlemcisi giriş noktası ve Qt yöneticisi.

X11 oturumunda systemd --user servisi olarak çalışır.
Farabi'den bağımsızdır; ders saatinde kararlı ekran görüntüsünü küçük WebP
olarak sunucuya (POST /api/ders-gorsel) iletir.

Config 'enabled' false ise PyQt6 ve core.ders_gorsel import edilmeden exit 0.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("ders_gorsel_servis")


def _hizli_config_kontrol(
    config_path: Path | None = None,
) -> tuple[dict | None, int]:
    """Hafif config kontrolü: core.ders_gorsel veya PyQt6 import ETMEDEN çalışır.

    Dönüş: (config_dict, exit_code)
    Eğer enabled değilse (None, 0) döner.
    Config bozuk veya okunamıyorsa (None, 0) döner (systemd çökme döngüsünü engellemek için).
    aralik_sn 4..10 dışındaysa 5'e çekilir.
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "api_keys.json"

    try:
        if not config_path.is_file():
            return None, 0
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        log.warning("Config okunamadı/bozuk: %s. Servis başlatılmıyor (exit 0).", exc)
        return None, 0

    if not isinstance(data, dict):
        return None, 0

    dg = data.get("ders_gorsel")
    if not isinstance(dg, dict) or dg.get("enabled") is not True:
        return None, 0

    aralik = dg.get("aralik_sn", dg.get("comparison_interval", 5))
    try:
        aralik = int(aralik)
        if not 4 <= aralik <= 10:
            aralik = 5
    except (TypeError, ValueError):
        aralik = 5

    return {"enabled": True, "aralik_sn": aralik}, 0


def _webp_kontrol() -> bool:
    """Pillow kütüphanesinin WebP desteğini doğrular."""
    try:
        from PIL import features

        return bool(features.check("webp"))
    except (ImportError, AttributeError, ValueError):
        return False


def x11_hazir_mi(timeout: float = 1.0) -> bool:
    """X11 sunucusuna erişilebiliyor mu?"""
    if not os.environ.get("DISPLAY"):
        return False
    try:
        res = subprocess.run(
            ["xprop", "-root"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def x11_bekle(
    kontrol_fonk: Callable[[], bool] = x11_hazir_mi,
    bekleme_sn: float = 30.0,
    max_deneme: int | None = None,
) -> bool:
    """X'e bağlanamazsa bekleme_sn sn bekleyip yeniden dener (çökme döngüsü yok)."""
    deneme = 0
    while True:
        if kontrol_fonk():
            return True
        deneme += 1
        if max_deneme is not None and deneme >= max_deneme:
            return False
        log.warning(
            "X11 bağlantısı kurulamadı (deneme %d), %s sn bekleniyor...",
            deneme,
            bekleme_sn,
        )
        time.sleep(bekleme_sn)


def olustur_servis_sinifi():
    """PyQt6 mevcutken servis sınıfını tanımlar."""
    import numpy as np
    from core import zil
    from core.ders_gorsel import (
        Karar,
        ServisMetrikleri,
        aktif_pencere_bilgisi,
        gonder,
        pencere_kabul_edilebilir_mi,
        webp_kodla,
    )
    from core.logger import get_logger
    from PIL import Image
    from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QGuiApplication, QImage

    class DersGorselServis(QObject):
        """Tahta masaüstünde ders saatinde kararlı ekran karelerini yakalayan Qt yöneticisi."""

        grab_iste_sig = pyqtSignal(object, object)  # (pencere_A, durum)

        def __init__(self, config: dict):
            super().__init__()
            self.aralik_sn = config.get("aralik_sn", 5)
            self.karar = Karar()
            self.metrikler = ServisMetrikleri(log_aralik_sn=600.0)
            self.executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="ders-gorsel-worker"
            )
            self.mesgul = False

            self.grab_iste_sig.connect(self._on_grab_requested)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._on_tick)
            self.timer.start(self.aralik_sn * 1000)

            app = QGuiApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self._on_kapat)

        def _on_kapat(self) -> None:
            self.timer.stop()
            self.executor.shutdown(wait=False, cancel_futures=True)

        # Qt slot'u ve worker sınırları: yakalanmayan istisna PyQt6'da süreci düşürür,
        # worker'da ise `mesgul` takılı kalıp servisi sessizce durdurur.
        def _on_tick(self) -> None:
            try:
                self.metrikler.tick_kaydet()
                rapor = self.metrikler.kontrol_ve_raporla(time.monotonic())
                if rapor:
                    get_logger("ders_gorsel").info("DersGorsel metrik: %s", rapor)

                if self.mesgul:
                    self.metrikler.atla("mesgul")
                    return

                durum = zil.ders_durumu()
                if durum.get("tur") != "ders" or not durum.get("ders_no"):
                    self.metrikler.atla("ders_disi")
                    return

                self.mesgul = True
                self.executor.submit(self._worker_adim_1, durum)
            except Exception:  # noqa: BLE001
                get_logger("ders_gorsel").exception("Tick hatası")
                self.metrikler.hata_kaydet()
                self.mesgul = False

        def _worker_adim_1(self, durum: dict) -> None:
            try:
                pencere_a = aktif_pencere_bilgisi(timeout=1.0)
                kabul, neden = pencere_kabul_edilebilir_mi(pencere_a)
                if not kabul:
                    self.metrikler.atla(neden)
                    self.mesgul = False
                    return
                self.grab_iste_sig.emit(pencere_a, durum)
            except Exception:  # noqa: BLE001
                get_logger("ders_gorsel").exception("Pencere kontrolü (adım 1) hatası")
                self.metrikler.hata_kaydet()
                self.mesgul = False

        def _on_grab_requested(self, pencere_a, durum: dict) -> None:
            try:
                t0 = time.perf_counter()
                screen = QGuiApplication.primaryScreen()
                if screen is None:
                    self.metrikler.atla("ekran_yok")
                    self.mesgul = False
                    return
                pix = screen.grabWindow(0)
                if pix.isNull():
                    self.metrikler.atla("kare_bos")
                    self.mesgul = False
                    return
                img = pix.toImage()
                del pix
                grab_ms = (time.perf_counter() - t0) * 1000.0
                self.metrikler.grab_sure_kaydet(grab_ms)
                self.executor.submit(self._worker_adim_2, img, pencere_a, durum)
            except Exception:  # noqa: BLE001
                get_logger("ders_gorsel").exception("Ekran yakalama hatası")
                self.metrikler.hata_kaydet()
                self.mesgul = False

        def _worker_adim_2(self, img: QImage, pencere_a, durum: dict) -> None:
            try:
                pencere_b = aktif_pencere_bilgisi(timeout=1.0)
                if pencere_b is None or pencere_a.win_id != pencere_b.win_id:
                    self.metrikler.atla("yaris")
                    return
                kabul_b, neden_b = pencere_kabul_edilebilir_mi(pencere_b)
                if not kabul_b:
                    self.metrikler.atla(neden_b)
                    return

                t_kars_0 = time.perf_counter()
                thumb = (
                    img.scaled(
                        160,
                        90,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )
                    .convertToFormat(QImage.Format.Format_Grayscale8)
                )
                ptr = thumb.constBits()
                ptr.setsize(thumb.sizeInBytes())
                kare_160_90 = (
                    np.frombuffer(ptr, np.uint8)
                    .reshape((90, thumb.bytesPerLine()))[:, :160]
                    .copy()
                )
                del thumb

                now = time.monotonic()
                ders_kimlik = (time.strftime("%Y-%m-%d"), durum.get("ders_no"))
                kararli = self.karar.incele(kare_160_90, now, ders_kimlik)
                kars_ms = (time.perf_counter() - t_kars_0) * 1000.0
                self.metrikler.karsilastirma_sure_kaydet(kars_ms)

                if not kararli:
                    self.metrikler.atla("kararsiz_veya_benzer")
                    return

                self.metrikler.aday_kaydet()

                rgb = img.convertToFormat(QImage.Format.Format_RGB888)
                del img
                ptr_rgb = rgb.constBits()
                ptr_rgb.setsize(rgb.sizeInBytes())
                arr = (
                    np.frombuffer(ptr_rgb, np.uint8)
                    .reshape((rgb.height(), rgb.bytesPerLine()))[:, : rgb.width() * 3]
                    .reshape((rgb.height(), rgb.width(), 3))
                )
                # arr, rgb'nin belleğine bakan görünüm (sip.voidptr sahipliği tutmaz):
                # kopya rgb serbest bırakılmadan önce alınmalı.
                pil_im = Image.fromarray(arr.copy(), "RGB")
                del arr, rgb

                webp_bayt = webp_kodla(pil_im, max_genislik=960, kalite=60)
                del pil_im

                sira = self.karar.adet + 1
                basarili = gonder(webp_bayt, sira=sira, timeout=5.0)
                if basarili:
                    self.karar.gonderildi(kare_160_90, now, basarili=True)
                    self.metrikler.gonderim_kaydet()
                else:
                    self.karar.gonderim_basarisiz(kare_160_90, now)
                    self.metrikler.hata_kaydet()
            except Exception:  # noqa: BLE001
                get_logger("ders_gorsel").exception("Kare işleme (adım 2) hatası")
                self.metrikler.hata_kaydet()
            finally:
                self.mesgul = False

    return DersGorselServis


def main() -> int:
    config, ret = _hizli_config_kontrol()
    if ret != 0 or config is None:
        return ret

    if not _webp_kontrol():
        log.warning("Pillow WebP desteği yok, servis sonlandırılıyor (exit 0).")
        return 0

    if not x11_bekle():
        log.error("X11 bağlantısı kurulamadı, çıkılıyor.")
        return 1

    try:
        from core.logger import get_logger
        from PyQt6.QtGui import QGuiApplication

        app_log = get_logger("ders_gorsel")
        app = QGuiApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        servis_cls = olustur_servis_sinifi()
        servis = servis_cls(config)
        app._ders_gorsel_servis = servis
        app_log.info(
            "Ders görseli servisi başlatıldı (aralık: %s sn)",
            config["aralik_sn"],
        )
        return app.exec()
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        log.warning("Ders görseli servisi başlatılamadı: %s (exit 0)", exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
