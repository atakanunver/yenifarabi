"""
actions/geogebra.py — GeoGebra'yı tahtada açar ve Farabi'nin CANLI yönetmesini sağlar.

GeoGebra bir yapay zekâ değil, Farabi'nin matematik görselleştirme aracı:
model `f(x)=a(x-h)^2+k` yazar, sürgüleri kurar, derste "şimdi a'yı 3 yapıyorum"
deyip değeri kendisi değiştirir. Öğrenci de sürgüleri tahtada eliyle oynatır.

NASIL ÇALIŞIR — tarayıcı + yerel köprü, QtWebEngine YOK:

  1. Süreç içinde yalnızca 127.0.0.1'e bağlı küçük bir HTTP sunucusu başlar
     (stdlib, ayrı iş parçacığı). GeoGebra'nın çevrimdışı paketini
     (Math Apps Bundle) ve `/farabi.html` sayfasını sunar.
  2. Sayfa Chrome'da `--app` kipinde açılır: adres çubuğu, sekme, bağlantı
     yok — site_goster'ın "öğrenciye tarayıcı verme" ilkesi korunur.
     Ayrı `--user-data-dir` sayesinde bu Chrome kendi sürecidir; PID'i
     pencereyle ilişkili kalır (pencere_kapat'taki xdg-open sorunu yok).
  3. Sayfa `/komut`'u yoklar, gelen GeoGebra komutlarını `evalCommand` ile
     uygular ve her komutun başarılı olup olmadığını `/sonuc`'a bildirir.
     Araç bu yanıtı bekler — model yanlış yazılmış bir komutu HATA olarak
     görür ve düzeltebilir, "çizdim" diye yalan söylemez.

Neden QtWebEngine değil: client venv'inde yok; 7 tahtanın her birine
~100 MB ek paket demek. Chrome tahtalarda zaten kurulu.

PAKET YOLU: paket (~120 MB) git'e GİRMEZ. Asıl kaynak sunucudur
(`<sunucu_url>/geogebra/`, server/main.py'deki StaticFiles bağlaması):
köprü istenen dosyayı sunucudan çeker ve `icerik/onbellek/geogebra/`'ya
yazar — ilk açılıştan sonra tahta sunucuya gitmeden yükler. Geliştirme
için `GEOGEBRA_YOLLARI`'nda tam bir yerel paket varsa o önceliklidir.
"""

import json
import queue
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GEOGEBRA_YOLLARI = [
    Path(__file__).resolve().parent.parent / "icerik" / "geogebra" / "GeoGebra",
    Path.home() / "geogebra" / "bundle" / "GeoGebra",
]
ONBELLEK = Path(__file__).resolve().parent.parent / "icerik" / "onbellek" / "geogebra"
SUNUCU_ZAMAN_ASIMI = 20

PROFIL_DIZINI = Path.home() / ".cache" / "farabi-geogebra-chrome"
UYGULAMALAR = ("graphing", "geometry", "3d", "classic")
PENCERE_BASLIGI = "Farabi GeoGebra"

YANIT_BEKLEME = 5.0        # sayfa hazırken komutların uygulanması (ms düzeyinde)
# Yeni açılan sayfanın /komut'a ilk gelişi için süre. Ölçüm (fenlab, 2026-09-25):
# temiz Chrome + diskteki paket ~3 sn, sunucudan soğuk ~4 sn. Gelmezse Chrome
# BİR KEZ yeniden açılır — GeoGebra'nın parça yükleyicisi (GWT deferredjs) aynı
# Chrome içinde sayfa yeniden yüklenince ya da dosyalar ağdan yavaş gelince
# zaman zaman takılıyor ve o pencere kendini toparlamıyor; temiz açılış
# ~25 denemede hiç takılmadı.
ILK_DENEME = 8.0

_SAYFA = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>__BASLIK__</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:#fff}#ggb{width:100vw;height:100vh}</style>
<script src="/GeoGebra/deployggb.js"></script>
</head><body><div id="ggb"></div>
<script>
const SURUM = __SURUM__;
// Köprü, /sonuc'u gelmemiş paketi bir sonraki /komut'ta YENİDEN gönderir
// (yerel bağlantıda nadiren "Failed to fetch": köprü yanıtı yazdığı hâlde
// sayfaya ulaşmıyor). Uygulanmış paket tekrar uygulanmaz — sonucu yeniden
// bildirilir, adsız nesneler (Circle(A,2)) çift oluşmaz.
const bitti = new Map();
function bildir(id, sonuclar) {
  fetch("/sonuc", {method: "POST", body: JSON.stringify({id, sonuclar})}).catch(() => {});
}
// Her adım ayrı try/catch: bir istisna /sonuc'u hiç göndertmezse araç
// "yanıt vermedi" der, model de neyin bozulduğunu bilemez.
function uygula(paket) {
  if (bitti.has(paket.id)) return bildir(paket.id, bitti.get(paket.id));
  const api = window.ggbApplet, sonuclar = [];
  if (paket.temizle) {
    try { api.newConstruction(); }
    catch (e) { sonuclar.push({komut: "temizle", tamam: false, hata: String(e)}); }
  }
  for (const k of paket.komutlar) {
    try { sonuclar.push({komut: k, tamam: !!api.evalCommand(k)}); }
    catch (e) { sonuclar.push({komut: k, tamam: false, hata: String(e)}); }
  }
  for (const [ad, deger] of Object.entries(paket.degerler || {})) {
    const s = {komut: ad + " = " + deger, tamam: false};
    try {
      if (api.exists(ad)) { api.setValue(ad, deger); s.tamam = true; }
      else s.hata = "böyle bir nesne yok";
    } catch (e) { s.hata = String(e); }
    sonuclar.push(s);
  }
  bitti.set(paket.id, sonuclar);
  bildir(paket.id, sonuclar);
}
function hata_bildir(yer, e) {
  fetch("/hata", {method: "POST", body: yer + ": " + e}).catch(() => {});
}
async function dongu() {
  while (true) {
    let r, paket;
    try { r = await fetch("/komut?surum=" + SURUM); }
    catch (e) { hata_bildir("fetch", e); await new Promise(t => setTimeout(t, 1000)); continue; }
    if (r.status === 410) { location.reload(); return; }
    if (r.status !== 200) continue;
    try { paket = await r.json(); }
    catch (e) { hata_bildir("json", e); continue; }
    try { uygula(paket); }
    catch (e) { hata_bildir("uygula", e); }
  }
}
const app = new GGBApplet({
  appName: "__UYGULAMA__", width: innerWidth, height: innerHeight,
  language: "tr", showToolBar: true, showAlgebraInput: true, showMenuBar: false,
  enableShiftDragZoom: true, showResetIcon: true, scaleContainerClass: "",
  appletOnLoad: () => dongu(),
}, true);
app.setHTML5Codebase("/GeoGebra/HTML5/5.0/web3d/");
window.addEventListener("load", () => app.inject("ggb"));
</script></body></html>
"""


class _Kopru:
    """Tek süreçlik durum: HTTP sunucusu, Chrome süreci, komut kuyruğu."""

    def __init__(self):
        self.kilit = threading.Lock()
        self.sunucu: ThreadingHTTPServer | None = None
        self.chrome: subprocess.Popen | None = None
        self.paket_yolu: Path | None = None
        self.uygulama = "graphing"
        self.surum = 0                 # uygulama değişince sayfa yeniden yüklenir
        self.kuyruk: queue.Queue = queue.Queue()
        self.yanitlar: dict[int, list] = {}
        self.yanit_olayi = threading.Condition()
        self.sayac = 0
        self.teslim: dict[int, dict] = {}   # sayfaya gönderilmiş, /sonuc'u gelmemiş paketler
        self.vazgecilen: set[int] = set()   # araç zaman aşımıyla döndü — artık uygulanmasın
        self.son_hata = ""             # sayfanın /hata ile bildirdiği son JS hatası
        self.hazir_surum = -1          # /komut'a en son gelen GÜNCEL sayfanın sürümü
        self.acilis = 0.0              # Chrome'un açıldığı an (monotonic)

    def sayfa_hazir(self) -> bool:
        return self.hazir_surum == self.surum

    def port(self) -> int:
        return self.sunucu.server_address[1]


_K = _Kopru()


def _isleyici_sinifi():
    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _gonder(self, kod: int, govde: bytes = b"", tur: str = "text/plain"):
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(govde)
            except (BrokenPipeError, ConnectionResetError):
                pass               # kapanmış pencerenin bekleyen isteği

        def do_GET(self):
            yol = self.path.split("?", 1)[0]
            if yol == "/farabi.html":
                sayfa = (_SAYFA.replace("__UYGULAMA__", _K.uygulama)
                              .replace("__SURUM__", str(_K.surum))
                              .replace("__BASLIK__", PENCERE_BASLIGI))
                return self._gonder(200, sayfa.encode(), "text/html; charset=utf-8")
            if yol == "/komut":
                istenen = self.path.partition("surum=")[2]
                with _K.yanit_olayi:
                    if istenen != str(_K.surum):
                        return self._gonder(410)
                    if _K.hazir_surum != _K.surum:
                        _K.hazir_surum = _K.surum
                        _K.yanit_olayi.notify_all()
                # Sayfa sırayla çalışır: yeni /komut geldiyse önceki paketle işi
                # bitmiştir — /sonuc'u hâlâ yoksa paket ya da sonucu yolda kaybolmuştur.
                with _K.yanit_olayi:
                    bekleyen = next(iter(_K.teslim.values()), None)
                if bekleyen is not None:
                    return self._gonder(200, json.dumps(bekleyen).encode(), "application/json")
                try:
                    paket = _K.kuyruk.get(timeout=20)
                except queue.Empty:
                    return self._gonder(204)
                with _K.yanit_olayi:
                    if paket["id"] in _K.vazgecilen:
                        _K.vazgecilen.discard(paket["id"])
                        return self._gonder(204)
                    if istenen != str(_K.surum):
                        # beklerken pencere kapandı/yeniden açıldı: paket yeni sayfanındır
                        _K.kuyruk.put(paket)
                        eski = True
                    else:
                        _K.teslim[paket["id"]] = paket
                        eski = False
                if eski:
                    return self._gonder(410)
                return self._gonder(200, json.dumps(paket).encode(), "application/json")
            if yol.startswith("/GeoGebra/"):
                return self._dosya(yol[len("/GeoGebra/"):])
            return self._gonder(404)

        def do_POST(self):
            if self.path == "/hata":
                uzunluk = int(self.headers.get("Content-Length") or 0)
                _K.son_hata = self.rfile.read(uzunluk).decode("utf-8", "replace")[:300]
                return self._gonder(204)
            if self.path != "/sonuc":
                return self._gonder(404)
            uzunluk = int(self.headers.get("Content-Length") or 0)
            try:
                veri = json.loads(self.rfile.read(uzunluk))
                with _K.yanit_olayi:
                    if _K.teslim.pop(int(veri["id"]), None) is not None:
                        _K.yanitlar[int(veri["id"])] = veri.get("sonuclar") or []
                    _K.yanit_olayi.notify_all()
            except Exception:
                return self._gonder(400)
            return self._gonder(204)

        def _dosya(self, goreli: str):
            kok = (_K.paket_yolu or ONBELLEK).resolve()
            hedef = (kok / goreli).resolve()
            if kok not in hedef.parents:
                return self._gonder(404)
            if not hedef.is_file() and (_K.paket_yolu is not None or not _sunucudan_cek(goreli, hedef)):
                return self._gonder(404)
            tur = {
                ".js": "application/javascript", ".mjs": "application/javascript",
                ".css": "text/css", ".html": "text/html", ".json": "application/json",
                ".svg": "image/svg+xml", ".png": "image/png", ".gif": "image/gif",
                ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
                ".wasm": "application/wasm",
            }.get(hedef.suffix.lower(), "application/octet-stream")
            return self._gonder(200, hedef.read_bytes(), tur)

    return Isleyici


def _paket_bul() -> Path | None:
    for yol in GEOGEBRA_YOLLARI:
        if (yol / "deployggb.js").is_file():
            return yol
    return None


def _sunucudan_cek(goreli: str, hedef: Path) -> bool:
    """Dosyayı sunucudan önbelleğe indirir. Yarım dosya bırakmaz."""
    try:
        import requests
        from core import tahta
        yanit = requests.get(f"{tahta.sunucu_url()}/geogebra/{goreli}",
                             timeout=SUNUCU_ZAMAN_ASIMI)
        if yanit.status_code != 200:
            return False
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = hedef.with_name(hedef.name + f".{threading.get_ident()}.tmp")
        gecici.write_bytes(yanit.content)
        gecici.replace(hedef)
        return True
    except Exception:
        return False


def _chrome_yolu() -> str | None:
    for ad in ("google-chrome", "chromium", "chromium-browser"):
        yol = shutil.which(ad)
        if yol:
            return yol
    return None


def _sunucu_hazirla() -> str | None:
    """Sunucuyu (gerekirse) başlatır. Hata varsa açıklama döner."""
    if _K.sunucu is not None:
        return None
    _K.paket_yolu = _paket_bul()
    if _K.paket_yolu is None and not (ONBELLEK / "deployggb.js").is_file() \
            and not _sunucudan_cek("deployggb.js", ONBELLEK / "deployggb.js"):
        return ("GeoGebra açılamadı: paket ne bu tahtada ne de sunucuda bulundu. "
                "Sınıfa teknik sorundan bahsetme, konuyu tahtada anlatmaya devam et.")
    _K.sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _isleyici_sinifi())
    _K.sunucu.daemon_threads = True
    threading.Thread(target=_K.sunucu.serve_forever, daemon=True,
                     name="geogebra-kopru").start()
    return None


def _pencere_acik() -> bool:
    return _K.chrome is not None and _K.chrome.poll() is None


def _pencere_ac() -> str | None:
    chrome = _chrome_yolu()
    if chrome is None:
        return "Tahtada Chrome bulunamadı, GeoGebra açılamıyor."
    PROFIL_DIZINI.mkdir(parents=True, exist_ok=True)
    # Kapanan pencerenin /komut isteği köprüde hâlâ kuyrukta bekliyor olabilir
    # (pencere X ile de kapanabilir, _kapat'tan geçmeden). Sürüm değişince o
    # istek yeni paketi alırsa geri koyar ve 410 döner — paket kaybolmaz.
    with _K.yanit_olayi:
        _K.surum += 1
    _K.acilis = time.monotonic()
    _K.chrome = subprocess.Popen(
        [chrome, f"--app=http://127.0.0.1:{_K.port()}/farabi.html",
         f"--user-data-dir={PROFIL_DIZINI}", "--start-maximized",
         "--no-first-run", "--no-default-browser-check", "--disable-translate"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return None


def _chrome_durdur():
    # Sürüm ÖNCE artar: kapanmakta olan sayfanın o an gelen /komut'u paketi
    # almasın (alırsa geri koyar), eski sayfa "hazır" sayılmasın.
    with _K.yanit_olayi:
        _K.surum += 1
    if _pencere_acik():
        _K.chrome.terminate()
        try:
            _K.chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _K.chrome.kill()
    _K.chrome = None


def _kapat() -> str:
    if not _pencere_acik():
        return "GeoGebra zaten açık değil."
    _chrome_durdur()
    return "GeoGebra kapatıldı."


def _sayfa_bekle() -> bool:
    """
    Açık sayfanın hazır olmasını (/komut'a gelmesini) bekler. ILK_DENEME içinde
    gelmezse Chrome'u bir kez temiz açar. Kuyruktaki paket beklemede kalır —
    takılan sayfa /komut'a hiç gelmediği için onu almamıştır.
    """
    for deneme in range(2):
        with _K.yanit_olayi:
            while not _K.sayfa_hazir():
                kalan = _K.acilis + ILK_DENEME - time.monotonic()
                if kalan <= 0:
                    break
                _K.yanit_olayi.wait(kalan)
            if _K.sayfa_hazir():
                return True
        if deneme == 0:
            with _K.kilit:
                if not _K.sayfa_hazir():
                    _chrome_durdur()
                    if _pencere_ac():
                        return False
    return False


def _kuyrugu_bosalt():
    with _K.yanit_olayi:
        _K.teslim.clear()
    while True:
        try:
            _K.kuyruk.get_nowait()
        except queue.Empty:
            return


def geogebra(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    if p.get("kapat"):
        with _K.kilit:
            return _kapat()

    komutlar = [str(k).strip() for k in (p.get("komutlar") or []) if str(k).strip()]
    ham = p.get("degerler") or []
    if isinstance(ham, dict):
        ham = [{"ad": k, "deger": v} for k, v in ham.items()]
    degerler = {}
    for ad, deger in ((d.get("ad"), d.get("deger")) for d in ham if isinstance(d, dict)):
        try:
            degerler[str(ad)] = float(deger)
        except (TypeError, ValueError):
            return f"'{ad}' için sayı olmayan bir değer verildi: {deger!r}"
    uygulama = (p.get("uygulama") or "").strip().lower() or None
    if uygulama and uygulama not in UYGULAMALAR:
        return f"Bilinmeyen GeoGebra uygulaması '{uygulama}'. Seçenekler: {', '.join(UYGULAMALAR)}."
    temizle = bool(p.get("temizle"))

    with _K.kilit:
        hata = _sunucu_hazirla()
        if hata:
            log(f"[GeoGebra] {hata}")
            return hata

        if uygulama and uygulama != _K.uygulama:
            # Sayfayı aynı Chrome'da yeniden yüklemek yerine pencereyi temiz açar:
            # yeniden yükleme GeoGebra'nın parça yükleyicisini sık sık takıyor.
            _K.uygulama = uygulama
            _chrome_durdur()

        yeni_acildi = False
        if not _pencere_acik():
            _kuyrugu_bosalt()
            hata = _pencere_ac()
            if hata:
                log(f"[GeoGebra] {hata}")
                return hata
            yeni_acildi = True

        paket_id = None
        if komutlar or degerler or temizle:
            _K.sayac += 1
            paket_id = _K.sayac
            _K.kuyruk.put({"id": paket_id, "komutlar": komutlar,
                           "degerler": degerler, "temizle": temizle})

    if not _sayfa_bekle():
        log("[GeoGebra] sayfa yüklenmedi (yeniden açma dahil)")
        return ("GeoGebra açılamadı (sayfa yüklenmedi). Sınıfa teknik sorundan "
                "bahsetme, konuyu tahtada anlatmaya devam et.")
    if paket_id is None:
        log(f"[GeoGebra] {_K.uygulama} açıldı")
        return f"GeoGebra ({_K.uygulama}) tahtada açıldı."

    log(f"[GeoGebra] {len(komutlar)} komut, {len(degerler)} değer gönderildi")
    son = time.monotonic() + YANIT_BEKLEME
    with _K.yanit_olayi:
        while paket_id not in _K.yanitlar:
            kalan = son - time.monotonic()
            if kalan <= 0:
                if _K.teslim.pop(paket_id, None) is None:
                    _K.vazgecilen.add(paket_id)   # kuyrukta: çıkınca atılsın
                log(f"[GeoGebra] yanıt yok (sayfa hatası: {_K.son_hata or '-'})")
                return ("GeoGebra komutlara yanıt vermedi. Bir kez daha dene; "
                        "yine olmazsa sınıfa teknik sorundan bahsetme, konuyu "
                        "tahtada anlatmaya devam et.")
            _K.yanit_olayi.wait(kalan)
        sonuclar = _K.yanitlar.pop(paket_id)

    basarisiz = [s["komut"] + (f" ({s['hata']})" if s.get("hata") else "")
                 for s in sonuclar if not s.get("tamam")]
    ozet = "GeoGebra tahtada " + ("açıldı ve " if yeni_acildi else "") + \
        f"{len(sonuclar) - len(basarisiz)}/{len(sonuclar)} komut uygulandı."
    if basarisiz:
        ozet += (" BAŞARISIZ olanlar (GeoGebra sözdizimini düzeltip yeniden "
                 "gönder, çalışmayanı çizilmiş gibi anlatma): " + "; ".join(basarisiz))
    return ozet
