#!/usr/bin/env python3
"""okul-panel: tek dosyalık, bağımlılıksız yönetim paneli (stdlib).

Ayar ortam değişkenleriyle (/etc/okul-panel.env):
  PANEL_BASLIK, PANEL_PORT (9100), PANEL_KULLANICI (admin), PANEL_SIFRE,
  PANEL_SERVISLER  "birim1,birim2"   -> durum/log/yeniden başlat (beyaz liste)
  PANEL_SURECLER   "etiket=desen,.." -> yalnız durum (pgrep -f)
"""
import base64
import hmac
import html
import json
import os
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASLIK = os.environ.get("PANEL_BASLIK", "Okul Paneli")
PORT = int(os.environ.get("PANEL_PORT", "9100"))
KULLANICI = os.environ.get("PANEL_KULLANICI", "admin")
SIFRE = os.environ["PANEL_SIFRE"]
SERVISLER = [s for s in os.environ.get("PANEL_SERVISLER", "").split(",") if s]
SURECLER = dict(p.split("=", 1) for p in os.environ.get("PANEL_SURECLER", "").split(",") if "=" in p)


def calistir(komut, zaman=8):
    try:
        r = subprocess.run(komut, capture_output=True, text=True, timeout=zaman)
        return r.stdout.strip()
    except Exception as e:
        return f"hata: {e}"


def sistem():
    yuk = os.getloadavg()
    bellek = {}
    for satir in open("/proc/meminfo"):
        k, v = satir.split(":", 1)
        bellek[k] = int(v.split()[0]) // 1024
    toplam, bos = bellek["MemTotal"], bellek["MemAvailable"]
    disk = shutil.disk_usage("/")
    up = float(open("/proc/uptime").read().split()[0])
    veri = {
        "host": os.uname().nodename,
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "acik_kalma_saat": round(up / 3600, 1),
        "yuk": [round(x, 2) for x in yuk],
        "ram_mb": {"toplam": toplam, "kullanilan": toplam - bos},
        "disk_gb": {"toplam": disk.total // 2**30, "kullanilan": disk.used // 2**30},
        "servisler": {s: calistir(["systemctl", "is-active", s]) for s in SERVISLER},
        "surecler": {e: bool(calistir(["pgrep", "-f", d])) for e, d in SURECLER.items()},
    }
    gpu = calistir(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
                    "--format=csv,noheader,nounits"])
    if gpu and not gpu.startswith("hata"):
        veri["gpu"] = [satir.split(", ") for satir in gpu.splitlines()]
    return veri


def sayfa(v):
    e = html.escape
    sat = "".join(
        f"<tr><td>{e(s)}</td><td class={'ok' if d == 'active' else 'kotu'}>{e(d)}</td>"
        f"<td><a href='/log/{e(s)}'>log</a> "
        f"<form method=post action='/restart/{e(s)}' style=display:inline "
        f"onsubmit=\"return confirm('{e(s)} yeniden başlatılsın mı?')\"><button>Yeniden başlat</button></form></td></tr>"
        for s, d in v["servisler"].items())
    sat += "".join(
        f"<tr><td>{e(k)} (süreç)</td><td class={'ok' if d else 'kotu'}>{'çalışıyor' if d else 'YOK'}</td><td></td></tr>"
        for k, d in v["surecler"].items())
    gpu = "".join(f"<li>{e(g[0])}: {e(g[1])}/{e(g[2])} MB, {e(g[3])}°C, %{e(g[4])}</li>" for g in v.get("gpu", []))
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=30><title>{e(BASLIK)}</title>
<style>body{{font:15px system-ui;max-width:760px;margin:1rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}
td{{border-bottom:1px solid #ddd;padding:.4rem}}.ok{{color:#0a0}}.kotu{{color:#c00;font-weight:600}}</style>
<h1>{e(BASLIK)}</h1><p><a href=/pano>Pano yönetimi →</a></p><p>{e(v['host'])} · {e(v['zaman'])} · açık {v['acik_kalma_saat']} saat</p>
<p>Yük {v['yuk']} · RAM {v['ram_mb']['kullanilan']}/{v['ram_mb']['toplam']} MB · Disk {v['disk_gb']['kullanilan']}/{v['disk_gb']['toplam']} GB</p>
<ul>{gpu}</ul><table>{sat}</table>"""


# ---------------------------------------------------------------- pano yönetimi (2026-10-26)
# /pano: nöbetçi çizelgesi, slayt resimleri, ilginç bilgiler, YKS sayacı. Dosyalar PANO_WEB (varsayılan
# /home/atakan/web) altında; pano (tekhtml) bunları kendisi okur. Her yazım: yedek + atomik + sahip düzeltme.
import re
import shutil as _shutil
import urllib.parse
from datetime import date
from email.parser import BytesParser
from email.policy import HTTP

RESIM_LIMIT = 6 * 1024 * 1024
RESIM_ADEDI = 40
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum"]
YEDEK_ADEDI = 5


def pano_web():
    return os.environ.get("PANO_WEB", "/home/atakan/web")


def _sahip_duzelt(yol):
    ad = os.environ.get("PANO_SAHIP", "atakan")
    if os.geteuid() == 0:
        try:
            _shutil.chown(yol, ad, ad)
        except (LookupError, OSError):
            pass


def _yedekle(yol):
    if not os.path.exists(yol):
        return
    yedek = f"{yol}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    _shutil.copy2(yol, yedek)
    _sahip_duzelt(yedek)
    eskiler = sorted(f for f in os.listdir(os.path.dirname(yol)) if f.startswith(os.path.basename(yol) + ".bak-"))
    for f in eskiler[:-YEDEK_ADEDI]:
        os.unlink(os.path.join(os.path.dirname(yol), f))


def _json_oku(ad, varsayilan):
    try:
        with open(os.path.join(pano_web(), "data", ad), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def _json_yaz(ad, veri):
    yol = os.path.join(pano_web(), "data", ad)
    _yedekle(yol)
    with open(yol + ".tmp", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
    os.replace(yol + ".tmp", yol)
    _sahip_duzelt(yol)


class PanoHatasi(ValueError):
    pass


def _metin(v, ust, ad):
    v = "".join(c for c in (v or "") if c >= " ").strip()
    if len(v) > ust:
        raise PanoHatasi(f"{ad} en fazla {ust} karakter olabilir.")
    return v


def nobetci_kaydet(form):
    cfg = _json_oku("config.json", {})
    cizelge = cfg.get("nobetci_cizelge") or {}
    yeni = {}
    for i, yer in enumerate(cizelge):
        yeni[yer] = [_metin(form.get(f"n_{i}_{g}", [""])[0], 40, "Ad") for g in range(5)]
    cfg["nobetci_cizelge"] = yeni
    _json_yaz("config.json", cfg)
    return "Nöbetçi çizelgesi kaydedildi."


def yks_kaydet(form):
    try:
        ay, gun = int(form["ay"][0]), int(form["gun"][0])
        date(2024, ay, gun)  # artık yıl: 29 Şubat da geçerli
    except (KeyError, ValueError):
        raise PanoHatasi("Geçerli bir ay/gün girin.") from None
    saat = (form.get("saat", [""])[0]).strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", saat):
        raise PanoHatasi("Saat SS:DD biçiminde olmalı.")
    cfg = _json_oku("config.json", {})
    cfg.update(yks_ay=ay, yks_gun=gun, yks_saat=saat)
    _json_yaz("config.json", cfg)
    return "YKS sayacı kaydedildi."


def slayt_sn_kaydet(form):
    try:
        sn = int(form["slayt_sn"][0])
    except (KeyError, ValueError):
        raise PanoHatasi("Süre sayı olmalı.") from None
    if not 2 <= sn <= 60:
        raise PanoHatasi("Slayt süresi 2-60 saniye olmalı.")
    cfg = _json_oku("config.json", {})
    cfg["slayt_sn"] = sn
    _json_yaz("config.json", cfg)
    return "Slayt süresi kaydedildi."


def bilgiler_kaydet(form):
    ks, ms = form.get("k", []), form.get("m", [])
    liste = []
    for k, m in zip(ks, ms):
        m = _metin(m, 300, "Bilgi")
        if m:
            liste.append({"k": _metin(k, 30, "Başlık") or "GENEL", "m": m})
    if len(liste) > 200:
        raise PanoHatasi("En fazla 200 bilgi.")
    if not liste:
        raise PanoHatasi("Liste boş olamaz.")
    _json_yaz("bilgiler.json", liste)
    return f"{len(liste)} bilgi kaydedildi."


def _resim_uzantisi(b):
    if b[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return ".webp"
    return None


def _resim_klasoru():
    return os.path.join(pano_web(), "panoresim")


def resim_listesi():
    try:
        return sorted(f for f in os.listdir(_resim_klasoru()) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    except OSError:
        return []


def resim_yukle(dosya_adi, veri):
    if len(veri) > RESIM_LIMIT:
        raise PanoHatasi("Resim en fazla 6 MB olabilir.")
    uzanti = _resim_uzantisi(veri)
    if not uzanti:
        raise PanoHatasi("Yalnızca JPG, PNG veya WEBP yüklenebilir.")
    kok = re.sub(r"[^\w\-]+", "-", os.path.splitext(os.path.basename(dosya_adi or ""))[0]).strip("-")[:60] or "resim"
    if len(resim_listesi()) >= RESIM_ADEDI:
        raise PanoHatasi(f"En fazla {RESIM_ADEDI} resim olabilir; önce silin.")
    klasor = _resim_klasoru()
    os.makedirs(klasor, exist_ok=True)
    ad, n = kok + uzanti, 1
    while os.path.exists(os.path.join(klasor, ad)):
        n += 1
        ad = f"{kok}-{n}{uzanti}"
    yol = os.path.join(klasor, ad)
    with open(yol, "wb") as f:
        f.write(veri)
    _sahip_duzelt(yol)
    return f"{ad} yüklendi."


def resim_sil(ad):
    if ad not in resim_listesi():  # yalnız klasörde listeli ad; yol ayracı/.. zaten eşleşmez
        raise PanoHatasi("Resim bulunamadı.")
    cop = os.path.join(os.path.dirname(pano_web().rstrip("/")), "panoresim-silinen")  # web/ dışı: sunulmaz, geri alınabilir
    os.makedirs(cop, exist_ok=True)
    hedef = os.path.join(cop, f"{time.strftime('%Y%m%d-%H%M%S')}-{ad}")
    _shutil.move(os.path.join(_resim_klasoru(), ad), hedef)
    return f"{ad} silindi (yedek: panoresim-silinen)."


def multipart_dosya(basliklar, govde):
    """-> (alan_adi->[değer], dosya_adi, bayt) ilk dosya alanı; stdlib email ayrıştırıcısı."""
    mesaj = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + basliklar.get("Content-Type", "").encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + govde)
    for parca in mesaj.iter_parts():
        if parca.get_filename():
            return parca.get_filename(), parca.get_payload(decode=True) or b""
    raise PanoHatasi("Dosya seçilmedi.")


def senkron_durumu():
    yol = os.path.join(pano_web(), "data", "program.json")
    try:
        dk = (time.time() - os.path.getmtime(yol)) / 60
    except OSError:
        dk = None
    return dk, _json_oku("config.json", {}).get("farabi_url", "")


def pano_sayfasi(mesaj="", hata="", host="kiosk.local"):
    e = html.escape
    cfg = _json_oku("config.json", {})
    dk, url = senkron_durumu()
    if dk is None:
        durum = "<p class=kotu>Program verisi hiç alınmamış.</p>"
    elif dk > 15:
        durum = f"<p class=kotu>Farabi verisi {int(dk)} dakikadır güncellenmiyor. Adres: {e(url)}</p>"
    else:
        durum = f"<p class=ok>Farabi verisi {int(dk)} dk önce alındı.</p>"
    nb = "<tr><th></th>" + "".join(f"<th>{g}</th>" for g in GUNLER) + "</tr>"
    for i, (yer, adlar) in enumerate((cfg.get("nobetci_cizelge") or {}).items()):
        nb += f"<tr><td>{e(yer)}</td>" + "".join(
            f"<td><input name=n_{i}_{g} value=\"{e((adlar + [''] * 5)[g])}\" maxlength=40></td>" for g in range(5)) + "</tr>"
    resim = "".join(
        f"<li><img src=\"http://{e(host)}:5000/panoresim/{urllib.parse.quote(r)}\" height=60 alt=\"\"> {e(r)} "
        f"<form method=post action=/pano/resim-sil style=display:inline "
        f"onsubmit=\"return confirm('Silinsin mi?')\"><input type=hidden name=ad value=\"{e(r)}\"><button>Sil</button></form></li>"
        for r in resim_listesi())
    bilgi = "".join(
        f"<tr><td><input name=k value=\"{e(b.get('k', ''))}\" size=10></td>"
        f"<td><input name=m value=\"{e(b.get('m', ''))}\" size=70></td></tr>"
        for b in _json_oku("bilgiler.json", []) + [{}])
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(BASLIK)} · Pano</title>
<style>body{{font:15px system-ui;max-width:900px;margin:1rem auto;padding:0 1rem}}td,th{{padding:.25rem;text-align:left}}
.ok{{color:#0a0}}.kotu{{color:#c00;font-weight:600}}.mesaj{{background:#e8f6ef;padding:.5rem;border-radius:6px}}
.hata{{background:#fdecea;color:#c00;padding:.5rem;border-radius:6px}}fieldset{{margin:1rem 0}}ul{{padding-left:1rem}}</style>
<h1>Pano yönetimi</h1><p><a href=/>← Sunucu durumu</a></p>
{f'<p class=mesaj>{e(mesaj)}</p>' if mesaj else ''}{f'<p class=hata>{e(hata)}</p>' if hata else ''}
<fieldset><legend>Durum</legend>{durum}<p>Pano içeriği birkaç dakika içinde kendiliğinden yenilenir.</p></fieldset>
<form method=post action=/pano/nobetci><fieldset><legend>Nöbetçi çizelgesi</legend><table>{nb}</table><button>Kaydet</button></fieldset></form>
<fieldset><legend>Slayt resimleri</legend><ul>{resim or '<li>Resim yok.</li>'}</ul>
<form method=post action=/pano/resim-yukle enctype=multipart/form-data><input type=file name=dosya accept=".jpg,.jpeg,.png,.webp" required>
<button>Yükle</button> <small>JPG/PNG/WEBP, en fazla 6 MB</small></form>
<form method=post action=/pano/slayt-sn>Her resim <input name=slayt_sn type=number min=2 max=60 value="{e(str(cfg.get('slayt_sn', 6)))}" style=width:4em> sn
<button>Kaydet</button></form></fieldset>
<form method=post action=/pano/yks><fieldset><legend>YKS sayacı</legend>Ay <input name=ay type=number min=1 max=12 value="{e(str(cfg.get('yks_ay', 6)))}" style=width:4em>
Gün <input name=gun type=number min=1 max=31 value="{e(str(cfg.get('yks_gun', 20)))}" style=width:4em>
Saat <input name=saat value="{e(str(cfg.get('yks_saat', '10:15')))}" size=5> <button>Kaydet</button></fieldset></form>
<form method=post action=/pano/bilgiler><fieldset><legend>İlginç bilgiler (son satır yeni bilgi; metni boşaltılan satır silinir)</legend>
<table>{bilgi}</table><button>Kaydet</button></fieldset></form>"""


def pano_post(yol, basliklar, govde):
    """/pano/* POST'ları. -> (mesaj, hata). Gövde okunmuş bayt."""
    try:
        if yol == "/pano/resim-yukle":
            ad, veri = multipart_dosya(basliklar, govde)
            return resim_yukle(ad, veri), ""
        form = urllib.parse.parse_qs(govde.decode("utf-8", "replace"), keep_blank_values=True)
        islem = {"/pano/nobetci": nobetci_kaydet, "/pano/yks": yks_kaydet, "/pano/slayt-sn": slayt_sn_kaydet,
                 "/pano/bilgiler": bilgiler_kaydet, "/pano/resim-sil": lambda f: resim_sil(f.get("ad", [""])[0])}.get(yol)
        if islem is None:
            return None
        return islem(form), ""
    except PanoHatasi as h:
        return "", str(h)


class Isleyici(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yetkili(self):
        b = self.headers.get("Authorization", "")
        if b.startswith("Basic "):
            try:
                k, _, s = base64.b64decode(b[6:]).decode().partition(":")
                ok_k = hmac.compare_digest(k, KULLANICI)
                ok_s = hmac.compare_digest(s, SIFRE)
                if ok_k and ok_s:
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{BASLIK}"')
        self.end_headers()
        return False

    def _gonder(self, kod, icerik, tur="text/html; charset=utf-8"):
        veri = icerik.encode()
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(veri)))
        self.end_headers()
        self.wfile.write(veri)

    def do_GET(self):
        if not self._yetkili():
            return
        yol = urlparse(self.path).path
        if yol == "/":
            self._gonder(200, sayfa(sistem()))
        elif yol == "/pano":
            q = urllib.parse.parse_qs(urlparse(self.path).query)
            host = (self.headers.get("Host", "kiosk.local")).split(":")[0]
            self._gonder(200, pano_sayfasi(q.get("m", [""])[0], q.get("h", [""])[0], host))
        elif yol == "/api/durum":
            self._gonder(200, json.dumps(sistem(), ensure_ascii=False), "application/json")
        elif yol.startswith("/log/") and yol[5:] in SERVISLER:
            cikti = calistir(["journalctl", "-u", yol[5:], "-n", "80", "--no-pager"])
            self._gonder(200, f"<pre style='white-space:pre-wrap'>{html.escape(cikti)}</pre><a href=/>geri</a>")
        else:
            self._gonder(404, "yok")

    def do_POST(self):
        if not self._yetkili():
            return
        yol = urlparse(self.path).path
        origin = self.headers.get("Origin", "")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            return self._gonder(403, "origin")
        if yol.startswith("/pano/"):
            uzunluk = int(self.headers.get("Content-Length", "0") or 0)
            if uzunluk > RESIM_LIMIT + 65536:
                kalan = min(uzunluk, 32 * 1024 * 1024)  # tarayıcı yazarken bağlantı kopmasın: okuyup at
                while kalan > 0:
                    kalan -= len(self.rfile.read(min(65536, kalan)))
                return self._gonder(413, "çok büyük")
            sonuc = pano_post(yol, self.headers, self.rfile.read(uzunluk))
            if sonuc is None:
                return self._gonder(404, "yok")
            mesaj, hata = sonuc
            self.send_response(303)
            self.send_header("Location", "/pano?" + urllib.parse.urlencode({"m": mesaj, "h": hata}))
            self.end_headers()
        elif yol.startswith("/restart/") and yol[9:] in SERVISLER:
            subprocess.run(["systemctl", "restart", yol[9:]], timeout=60)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self._gonder(404, "yok")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Isleyici).serve_forever()
