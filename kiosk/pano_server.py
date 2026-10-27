#!/usr/bin/env python3
"""Kiosk dijital bilgi panosu — küçük, bağımlılıksız web servisi (yalnızca stdlib).

- LAN'dan  http://192.168.23.254:5000/  -> index.html (pano)
- localhost'tan (kiosk'un kendi Chrome'u) -> zemin.html (yüz tanıma penceresinin
  arkasındaki düz zemin; pano animasyonları kiosk CPU'sunu yormasın diye)
- /api/resimler -> panoresim/ klasöründeki slayt resimlerinin listesi
- Dizin listeleme kapalı; yalnızca `web/` içeriği sunulur.
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
ROOT = os.path.normpath(ROOT)
RESIM_UZANTI = (".jpg", ".jpeg", ".png", ".webp")
LOCAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def _atomik(ad, veri):
    yol = os.path.join(ROOT, "data", ad)
    with open(yol + ".tmp", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(yol + ".tmp", yol)


def _duyuru_metni(x):
    if isinstance(x, str):
        return x
    if not isinstance(x, dict):
        return ""
    if x.get("baslik") and x.get("metin"):
        return f"{x['baslik']}: {x['metin']}"
    return str(x.get("metin") or x.get("baslik") or x.get("title") or x.get("text") or "")


def senkron():
    """Farabi /api/pano -> data/{program,duyurular,belirli_gunler}.json (zil.json bilerek 1 kez elle çekildi) (5 dk'da bir).
    Hata olursa son iyi kopya kalır; Farabi'den boş/bozuk veri gelirse yazılmaz."""
    while True:
        try:
            with open(os.path.join(ROOT, "data", "config.json"), encoding="utf-8") as f:
                url = json.load(f).get("farabi_url")
            if url:
                with urllib.request.urlopen(url, timeout=10) as r:
                    v = json.load(r)
                if v.get("program", {}).get("siniflar"):
                    _atomik("program.json", v["program"])
                if isinstance(v.get("duyurular"), list):
                    # tümü duyurular_tum.json'da (panel listeler); kioskta görünen = tümü - /pano'da gizlenenler
                    tum = [m for m in map(_duyuru_metni, v["duyurular"]) if m]
                    _atomik("duyurular_tum.json", tum)
                    try:
                        with open(os.path.join(ROOT, "data", "duyuru_gizli.json"), encoding="utf-8") as f:
                            gizli = set(json.load(f))
                    except (OSError, ValueError):
                        gizli = set()
                    _atomik("duyurular.json", [m for m in tum if m not in gizli])
                if isinstance(v.get("belirli_gunler"), list):
                    _atomik("belirli_gunler.json", v["belirli_gunler"])
        except Exception as e:  # 2026-10-26: sessizce yutulan hata veri 1 hafta bayat kaldı (eski Farabi IP'si); journal'a yaz
            print("senkron hatası:", repr(e), file=sys.stderr, flush=True)
        time.sleep(300)


class Pano(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def do_GET(self):
        yol = self.path.split("?", 1)[0]
        if yol in ("/", "/index.html"):
            self.path = (
                "/zemin.html" if self.client_address[0] in LOCAL else "/index.html"
            )
        elif yol == "/api/resimler":
            return self._resimler()
        return super().do_GET()

    def _resimler(self):
        klasor = os.path.join(ROOT, "panoresim")
        try:
            dosyalar = sorted(
                f for f in os.listdir(klasor) if f.lower().endswith(RESIM_UZANTI)
            )
        except OSError:
            dosyalar = []
        govde = json.dumps(dosyalar).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(govde)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        if not self.path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "max-age=3600")
        super().end_headers()

    def log_message(self, *args):  # sessiz: disk/CPU harcama
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    threading.Thread(target=senkron, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Pano).serve_forever()
