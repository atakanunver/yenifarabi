"""acil.py — Acil Durum tek düğme (2026-10-16, İl MEM Acil Durum Planı Eki).

/acil sayfasındaki üç düğme (Kilit-kapı / Tahliye / Tehlike geçti) aynı anda ve
BİRBİRİNDEN BAĞIMSIZ üç kanalı tetikler; biri başarısız olsa da diğerleri çalışır:
  1. Zil hoparlörleri — zil dashboard'unda önceden üretilip ONAYLANMIŞ anons
     (`POST /anons/cal/<id>`, Basic Auth). Ses seviyesi zil ayarlarındaki
     anons_ses_seviyesi'dir.
  2. SMS — tatbikatta yalnız 2 yöneticiye (`/api/arac/acil`), gerçek olayda
     rehberdeki tüm Personel'e (`personel-taslak` → `personel-gonder`).
  3. Tahtalar — öğretmen oturumunda Chrome kapatılıp /acil/ekran tam ekran (kiosk)
     açılır. Öğretmenin açık sekmeleri kapanır (kasıtlı: talimat ekranı önde olmalı).
Gizli değerler config/acil.json'da (gitignore). Her basış veri/acil_olaylar.jsonl'e
yazılır (ileride olay tutanağı için).
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import shlex
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import menu
import ssh_istemci
import tahta_api
import tahta_kaydi
import zil

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk  # taban.html kullanır

DIZIN = Path(__file__).resolve().parent
CONFIG = DIZIN / "config" / "acil.json"
OLAY_DOSYASI = DIZIN / "veri" / "acil_olaylar.jsonl"
ZIL_LOG = DIZIN / "veri" / "acil_zil.jsonl"  # tur tur zil günlüğü (panel olay listesini doldurmasın diye ayrı)
ISTANBUL = ZoneInfo("Europe/Istanbul")

TURLER = {
    "kilit": {
        "baslik": "KİLİT-KAPI",
        "renk": "#b00020",
        "siren": True,
        "anons": "Dikkat! Kilit-kapı uygulaması başlamıştır. Sınıflarınızda kalın, kapıları kilitleyin.",
        "adimlar": [
            "Koridordaki öğrencileri içeri alın",
            "Kapıyı kilitleyin; kilit yoksa masa-sıra ile barikat kurun",
            "Işıkları söndürün, perdeleri kapatın",
            "Kapı ve pencereden uzak, duvar dibinde, yere yakın bekleyin",
            "Tam sessizlik — telefonlar sessize",
            "Kapıyı resmi kimlik görmeden KİMSEYE açmayın",
            "Müdüre mesajla bildirin: sınıf, kaç kişi, yaralı var mı",
            '"Tehlike geçti" duyurulmadan sınıftan çıkmayın',
        ],
        "sms": "ACİL: Kilit-kapı uygulaması başladı. Sınıfınızda kalın, kapıyı kilitleyin, müdüre durum bildirin.",
    },
    "tahliye": {
        "baslik": "TAHLİYE",
        "renk": "#0d47a1",
        "siren": True,
        "anons": "Dikkat! Tahliye başlamıştır. Öğretmeninizle birlikte binayı sakin ve hızlı şekilde terk edin.",
        "adimlar": [
            "Eşyaları bırakın",
            "Çift sıra, hızlı ve sessiz çıkın",
            "Belirlenen güzergâhtan toplanma noktasına gidin",
            "Yoklama alın, eksik ve yaralıyı bildirin",
            "Öğrenciler veliye teslim edilene kadar dağılmayın",
        ],
        "sms": "ACİL: Tahliye başladı. Öğrencilerle toplanma noktasına gidin, yoklama alıp müdüre bildirin.",
    },
    "deprem": {
        "baslik": "DEPREM",
        "renk": "#5e1d8c",
        "siren": True,
        "anons": "Dikkat! Deprem! Çök, kapan, tutun. Sarsıntı bitene kadar sıraların altında kalın, sonra öğretmeninizle binayı terk edin.",
        "adimlar": [
            "ÇÖK – KAPAN – TUTUN: sıranın altına girin, başınızı koruyun",
            "Pencere, dolap ve raflardan uzak durun",
            "Sarsıntı bitene kadar yerinizde kalın, koşmayın",
            "Sarsıntı bitince öğretmeninizle sakin şekilde binayı terk edin",
            "Merdivende itişmeyin, asansör kullanmayın",
            "Toplanma alanında yoklama alın, eksik ve yaralıyı bildirin",
        ],
        "sms": "ACİL: Deprem. Çök-kapan-tutun; sarsıntı bitince öğrencilerle toplanma alanına çıkın, yoklama alıp bildirin.",
    },
    "yangin": {
        "baslik": "YANGIN",
        "renk": "#d84315",
        "siren": True,
        "anons": "Dikkat! Yangın alarmı! Öğretmeninizle birlikte en yakın çıkıştan, sakin ve hızlı şekilde binayı terk edin.",
        "adimlar": [
            "Eşyaları bırakın, hemen çıkın",
            "En yakın güvenli çıkışı kullanın",
            "Duman varsa eğilerek, ağzınızı ve burnunuzu kapatarak ilerleyin",
            "Kapıyı açmadan önce elinizin tersiyle sıcaklığını kontrol edin",
            "Toplanma noktasında yoklama alın, eksiği bildirin",
            "Binaya kesinlikle geri dönmeyin",
        ],
        "sms": "ACİL: Yangın alarmı. Öğrencileri en yakın çıkıştan tahliye edin, toplanma noktasında yoklama alıp bildirin.",
    },
    "gecti": {
        "baslik": "TEHLİKE GEÇTİ",
        "renk": "#1b7a35",
        "anons": "Tehlike geçmiştir. Lütfen yetkililerin yönlendirmesini bekleyin.",
        "adimlar": [
            "Sakin olun",
            "Yoklama alın",
            "Yetkililerin yönlendirmesini bekleyin",
        ],
        "sms": "Tehlike geçti. Yetkililerin yönlendirmesini bekleyin.",
    },
}
TATBIKAT_ONEKI = "TATBİKAT – "
# Asıl süreç /opt/google/chrome/chrome — "[g]oogle-chrome" yalnız sarmalayıcıyı
# yakalıyor, kiosk açık kalıyordu (2026-10-16, 9-A). Köşeli parantez: pkill kendi
# komut satırını eşlemesin.
CHROME_KAPAT = "pkill -f '[g]oogle-chrome'; pkill -f '[/]opt/google/chrome/chrome'"


def _ayarlar() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _dogrula(request: Request) -> None:
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


def _post(
    url: str, govde: dict | None, basliklar: dict, zaman_asimi: float = 10
) -> dict:
    veri = json.dumps(govde).encode() if govde is not None else b""
    istek = urllib.request.Request(url, data=veri, method="POST", headers=basliklar)
    acici = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )  # LAN, proxy yok
    with acici.open(istek, timeout=zaman_asimi) as yanit:
        return json.loads(yanit.read() or b"{}")


def _zil_istek(a: dict, yol: str, yontem: str = "POST", govde: dict | None = None):
    kimlik = base64.b64encode(f"{a['zil_kullanici']}:{a['zil_parola']}".encode()).decode()
    basliklar = {"Authorization": f"Basic {kimlik}"}
    if govde is not None:
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(
        a["zil_url"] + yol,
        data=json.dumps(govde).encode() if govde is not None else (b"" if yontem == "POST" else None),
        method=yontem, headers=basliklar,
    )
    acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # LAN, proxy yok
    with acici.open(istek, timeout=10) as yanit:
        return json.loads(yanit.read() or b"{}")


ANONS_TEKRAR = 20  # siren'li senaryoda anons sayısı (her anonstan önce siren); config "tekrar"
_zil_dur = threading.Event()  # çalışan tekrar döngüsünü keser


def _zil_kayit(**alanlar) -> None:
    """Zil turu günlüğü; hatası acil akışı bozmaz. Zil makinesindeki ~/ses/logs/acil.jsonl ile zaman damgasından eşleşir."""
    try:
        ZIL_LOG.parent.mkdir(exist_ok=True)
        zaman = datetime.now(ISTANBUL).isoformat(timespec="milliseconds")
        with ZIL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": zaman, **alanlar}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _zil_adim(a: dict, tur: str, tur_no: int, adim: str, yol: str) -> dict:
    """Tek zil isteği + günlük (süre, zilin yanıtı ya da hata)."""
    t0 = time.monotonic()
    try:
        yanit = _zil_istek(a, yol)
    except Exception as e:
        _zil_kayit(tur=tur, tur_no=tur_no, adim=adim, basarili=False, hata=str(e)[:200],
                   ms=round((time.monotonic() - t0) * 1000))
        raise
    _zil_kayit(tur=tur, tur_no=tur_no, adim=adim, basarili=True, yanit=yanit,
               ms=round((time.monotonic() - t0) * 1000))
    return yanit


def _zil_tekrar_durdur() -> None:
    _zil_kayit(adim="durdur_istegi")
    _zil_dur.set()


def _anons_sn(a: dict, tur: str) -> float:
    """Anonsun yaklaşık süresi (zil süre bildirmez): config "anons_sn"[tur] ya da metin uzunluğundan."""
    ayarli = a.get("anons_sn", {}).get(tur)
    return float(ayarli) if ayarli is not None else len(TURLER[tur]["anons"]) / 11 + 2


def _zil_tekrarla(a: dict, tur: str, anons_id: str, kalan: int, dur: threading.Event) -> None:
    """İlk siren+anonstan sonra kalan kez: siren → anons. Zil tek çalar olduğu için
    bir önceki anonsun bitmesi beklenir. Bir tur başarısız olsa sonrakiler denenir."""
    bekle = _anons_sn(a, tur)
    for i in range(kalan):
        tur_no = i + 2
        if dur.wait(bekle):
            _zil_kayit(tur=tur, tur_no=tur_no, adim="tekrar_kesildi")
            return
        try:
            _zil_adim(a, tur, tur_no, "siren", "/acil/siren-cal")
            if dur.wait(a.get("siren_sn", 8)):
                _zil_kayit(tur=tur, tur_no=tur_no, adim="tekrar_kesildi")
                return
            _zil_adim(a, tur, tur_no, "anons", f"/anons/cal/{anons_id}?acil=1")
        except Exception:
            log.exception("acil tekrar turu başarısız")
        bekle = _anons_sn(a, tur)


def _zil_cal(a: dict, tur: str) -> dict:
    """Siren'li senaryoda önce siren (siren_sn), sonra anons — zil tek çalar
    kullandığı için anons sireni keser. Anons yoksa siren yine çalmış olur.
    İlk tur burada (eşzamanlı); kalan tekrarlar arka plan iş parçacığında —
    yanıt dakikalarca beklemez. Önceki tekrar döngüsünü (ve 'Tehlike geçti') keser."""
    global _zil_dur
    _zil_dur.set()
    dur = _zil_dur = threading.Event()
    siren = TURLER[tur].get("siren")
    if siren:
        _zil_adim(a, tur, 1, "siren", "/acil/siren-cal")
        time.sleep(a.get("siren_sn", 8))
    anons_id = a.get("anons_idleri", {}).get(tur)
    if not anons_id:
        raise RuntimeError("Siren çaldı; bu senaryonun anonsu zilde henüz tanımlı değil." if siren
                           else "Anons zilde tanımlı değil.")
    sonuc = _zil_adim(a, tur, 1, "anons", f"/anons/cal/{anons_id}?acil=1")  # ?acil=1: zil acil ses seviyesi (%90) + mikser hazırlığı
    if not sonuc.get("tamam"):
        raise RuntimeError(sonuc.get("hata", "zil hatası"))
    tekrar = int(a.get("tekrar", ANONS_TEKRAR)) if siren else 1
    if tekrar > 1:
        threading.Thread(
            target=_zil_tekrarla, args=(a, tur, anons_id, tekrar - 1, dur), daemon=True
        ).start()
    return {"kanal": "Zil", "basarili": True,
            "detay": f"Siren + anons çalındı (toplam {tekrar} tur)." if tekrar > 1
            else ("Siren + anons" if siren else "Anons") + " çalındı."}


def _sms_gonder(a: dict, tur: str, tatbikat: bool, metin: str | None = None) -> dict:
    basliklar = {"X-Sms-Arac-Key": a["sms_anahtar"], "Content-Type": "application/json"}
    metin = metin or TURLER[tur]["sms"]
    if tatbikat:
        r = _post(
            f"{a['sms_url']}/api/arac/acil",
            {"metin": TATBIKAT_ONEKI + metin},
            basliklar,
        )
        if not r.get("alicilar"):
            raise RuntimeError("SMS alıcı listesi boş (yönetim).")
        return {
            "kanal": "SMS",
            "basarili": True,
            "detay": "Tatbikat: " + ", ".join(r.get("alicilar", [])),
        }
    # Gerçek olayda yönetim (+acil_ek) de alır; hatası personel gönderimini engellemez.
    yonetim_hata = None
    try:
        r = _post(f"{a['sms_url']}/api/arac/acil", {"metin": metin}, basliklar)
        yonetim = len(r.get("alicilar", []))
    except Exception as e:
        yonetim_hata = str(e)[:100]
    taslak = _post(
        f"{a['sms_url']}/api/arac/personel-taslak", {"metin": metin}, basliklar
    )
    if not taslak.get("alici_sayisi"):
        raise RuntimeError("SMS personel listesi boş.")
    _post(
        f"{a['sms_url']}/api/arac/personel-gonder",
        {"taslak_id": taslak["taslak_id"]},
        basliklar,
    )
    if yonetim_hata:
        raise RuntimeError(f"Personel gitti ({taslak['alici_sayisi']} kişi); yönetim SMS hatası: {yonetim_hata}")
    return {
        "kanal": "SMS",
        "basarili": True,
        "detay": f"Personel: {taslak['alici_sayisi']} kişi + yönetim: {yonetim}",
    }


async def _tahta_ekran_ac(t: dict, url: str) -> dict:
    ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
    if ortam is None:
        return {"tahta": t["ad"], "basarili": False, "detay": "Kapalı / oturum yok"}
    display, xauthority, _uid = ortam
    # Normal pencereli Chrome açıksa --kiosk yeni pencere açmaz → önce kapat.
    # AYRI çağrı: açma komutu "google-chrome" metnini içerdiği için aynı kabukta
    # `pkill -f` kabuğun kendisini öldürür (2026-10-16, 9-A'da yakalandı).
    await ssh_istemci.komut_calistir(
        t["ip"], t["kullanici"], CHROME_KAPAT + "; sleep 1; true"
    )
    # Singleton kilidini temizle (bkz. uzaktan_yonetim._web_ac_tek).
    komut = (
        f"rm -f /home/{t['kullanici']}/.config/google-chrome/Singleton*; "
        f"setsid env DISPLAY={display} XAUTHORITY={xauthority} "
        f"google-chrome --kiosk --no-first-run {shlex.quote(url)} "
        "</dev/null >/tmp/acil_chrome.log 2>&1 &"
    )
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], komut)
    return {
        "tahta": t["ad"],
        "basarili": sonuc.basarili,
        "detay": "Ekran açıldı" if sonuc.basarili else "SSH hatası",
    }


async def _tahta_ekran_kapat(t: dict) -> dict:
    sonuc = await ssh_istemci.komut_calistir(
        t["ip"], t["kullanici"], CHROME_KAPAT + "; true"
    )
    return {
        "tahta": t["ad"],
        "basarili": sonuc.basarili,
        "detay": "Kapatıldı" if sonuc.basarili else "Ulaşılamadı",
    }


def kaynak_adi(kaynak: str | None) -> str:
    """Panel/tahta/telegram/okul kaynak etiketini insan okuyacağı kısa ada çevirir (≤40 kr)."""
    k = str(kaynak or "makine")
    if k.startswith("panel"):
        return "Panel"
    if k.startswith("guvenlik"):
        return "Güvenlik (kapı)"
    if k.startswith("tahta:"):
        return f"Tahta {k[6:]}"
    if k.startswith("telegram:"):
        return f"Telegram: {k[9:]}"
    if k.startswith("okul:"):
        return f"Okul portalı: {k.split(':', 2)[-1]}"
    return k[:40]


def bildirim_metni(tur: str, tatbikat: bool, kaynak: str | None, saat: str, yanlis: bool = False) -> str:
    """Telegram (zil botu) bildirimi. ≤500 kr."""
    mod = "TATBİKAT" if tatbikat else "GERÇEK"
    kim = kaynak_adi(kaynak)
    if yanlis:
        return f"❎ YANLIŞ ALARM ({mod}) — iptal eden: {kim}, saat {saat}. Normal düzene dönülebilir."[:500]
    if tur == "gecti":
        return f"✅ ACİL DURUM SONA ERDİ ({mod}) — bildiren: {kim}, saat {saat}. Tehlike geçti."[:500]
    return f"🚨 ACİL DURUM: {TURLER[tur]['baslik']} — {mod} — başlatan: {kim}, saat {saat}."[:500]


def _telegram_bildir(a: dict, metin: str) -> dict:
    """Zil botuna (dosya tabanlı IPC, zil /acil/bildir) bildirim bırakır; bot yetkililere + isteğe bağlı gruba iletir."""
    r = _zil_istek(a, "/acil/bildir", "POST", {"metin": metin})
    if not r.get("tamam"):
        raise RuntimeError(r.get("hata", "zil bildirimi kabul etmedi"))
    return {"kanal": "Telegram", "basarili": True, "detay": "Bildirim zil botuna bırakıldı."}


def _okul_bildir(a: dict, tur: str, tatbikat: bool, kaynak: str | None, yanlis: bool = False) -> dict:
    """Okul portalına (push + kırmızı şerit) dış kaynaklı olay bildirir. Okul kendi tetiklediğini zaten kaydeder."""
    tur = "yanlis_alarm" if yanlis else tur
    _post(
        f"{a.get('okul_url', 'http://127.0.0.1:9090')}/acil/dis-olay",
        {"tur": tur, "tatbikat": tatbikat, "kaynak": kaynak_adi(kaynak)},
        {"X-Acil-Anahtar": a["makine_anahtar"], "Content-Type": "application/json"},
    )
    return {"kanal": "Okul portalı", "basarili": True, "detay": "Push + şerit tetiklendi."}


def _ek_kanallar(a: dict, tur: str, tatbikat: bool, kaynak: str | None, yanlis: bool = False) -> list:
    """Tüm modlarda çalışan bilgilendirme kanalları (bağımsız; biri düşse diğerleri çalışır)."""
    saat = datetime.now(ISTANBUL).strftime("%H:%M")
    gorevler = [_guvenli("Telegram", _telegram_bildir, a, bildirim_metni(tur, tatbikat, kaynak, saat, yanlis))]
    if not str(kaynak or "").startswith("okul:"):
        gorevler.append(_guvenli("Okul portalı", _okul_bildir, a, tur, tatbikat, kaynak, yanlis))
    return gorevler


async def _guvenli(adi: str, fonk, *args) -> dict:
    try:
        return await asyncio.to_thread(fonk, *args)
    except Exception as e:  # bir kanalın hatası diğerlerini durdurmaz
        return {"kanal": adi, "basarili": False, "detay": str(e)[:200]}


def _olay_yaz(kayit: dict) -> None:
    OLAY_DOSYASI.parent.mkdir(exist_ok=True)
    with OLAY_DOSYASI.open("a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


@router.get("/acil", response_class=HTMLResponse)
async def acil_sayfa(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "acil.html", {"turler": TURLER})


@router.get("/acil/ekran", response_class=HTMLResponse)
async def acil_ekran(request: Request, tur: str = "kilit", tatbikat: int = 0):
    """Tahtalarda tam ekran gösterilen talimat sayfası — tahtalar oturum açamadığı
    için kimlik istemez; yalnızca sabit metin içerir."""
    if tur not in TURLER:
        tur = "kilit"
    return templates.TemplateResponse(
        request, "acil_ekran.html", {"t": TURLER[tur], "tatbikat": bool(tatbikat)}
    )


@router.post("/api/acil/tetikle")
async def acil_tetikle(request: Request):
    _dogrula(request)
    govde = await request.json()
    tur = govde.get("tur")
    tatbikat = bool(govde.get("tatbikat", True))
    if tur not in TURLER:
        raise HTTPException(400, "Geçersiz tür.")
    kayit = await _baslat(
        _ayarlar(),
        tur,
        tatbikat,
        kaynak=f"panel:{request.client.host}" if request.client else "panel",
    )
    return JSONResponse(kayit)


async def _baslat(
    a: dict,
    tur: str,
    tatbikat: bool,
    kaynak: str | None,
    sms_metni: str | None = None,
    yalniz_sms: bool = False,
) -> dict:
    """Üç kanalı paralel başlatır, olayı günlüğe yazar. yalniz_sms: anons ve
    ekranlar zaten başlamışsa (art arda tahta alarmı) yalnız SMS gider."""
    url = f"{a['ekran_url']}?tur={tur}&tatbikat={int(tatbikat)}"
    tahtalar = [] if yalniz_sms else tahta_kaydi.tahtalari_yukle()
    gorevler = [_guvenli("SMS", _sms_gonder, a, tur, tatbikat, sms_metni), *_ek_kanallar(a, tur, tatbikat, kaynak)]
    if not yalniz_sms:
        gorevler.insert(0, _guvenli("Zil anonsu", _zil_cal, a, tur))
    sonuclar = await asyncio.gather(
        *gorevler, *(_tahta_ekran_ac(t, url) for t in tahtalar)
    )
    kayit = {
        "zaman": datetime.now(ISTANBUL).isoformat(timespec="seconds"),
        "tur": tur,
        "tatbikat": tatbikat,
        "istemci_ip": kaynak,
        "kanallar": list(sonuclar[: len(gorevler)]),
        "tahtalar": list(sonuclar[len(gorevler) :]),
    }
    _olay_yaz(kayit)
    return kayit


# --- Tahtadan alarm (masaüstü "ACİL ALARM" → acil_alarm.py) -------------------
# Kimlik tahtanın kendi token'ı (tahta_api._tahta_dogrula) — tahta adı istemciden
# ALINMAZ. PIN sunucuda doğrulanır (config/acil.json "pin_sha256"), tahtada durmaz.
UST_KAT = {"9-A", "9-B", "10-A", "12-B"}  # okul 2 katlı; diğerleri giriş katı
PIN_HATA_SINIRI = 5
PIN_KILIT_SN = 600
ART_ARDA_SN = 120  # bu süre içindeki ikinci tahta alarmı anonsu/ekranları tekrarlamaz
_pin_hatalari: dict[str, list[float]] = {}
_son_tahta_alarmi: list[float] = []
_arka_gorevler: set = set()


def kat_adi(tahta: str) -> str:
    return "üst kat" if tahta in UST_KAT else "giriş katı"


def tahta_alarm_metni(tahta: str, saat: str) -> str:
    return (
        f"ACİL ALARM: {tahta} ({kat_adi(tahta)}) tahtasından alarm verildi, saat {saat}. "
        "Kilit-kapı başladı. Sınıfınızda kalın, kapıyı kilitleyin."
    )


def pin_dogru_mu(tahta: str, pin: str, beklenen_ozet: str, simdi: float) -> bool:
    """Yanlış PIN'leri sayar; PIN_KILIT_SN içinde PIN_HATA_SINIRI yanlışta 429."""
    hatalar = [z for z in _pin_hatalari.get(tahta, []) if simdi - z < PIN_KILIT_SN]
    if len(hatalar) >= PIN_HATA_SINIRI:
        _pin_hatalari[tahta] = hatalar
        raise HTTPException(429, "Çok fazla yanlış PIN, 10 dakika bekleyin.")
    ozet = hashlib.sha256(str(pin).encode()).hexdigest()
    if hmac.compare_digest(ozet, beklenen_ozet):
        _pin_hatalari.pop(tahta, None)
        return True
    _pin_hatalari[tahta] = hatalar + [simdi]
    return False


@router.post("/api/acil/ekran-kapat")
async def acil_ekran_kapat_tahtadan(request: Request):
    """Kiosk talimat ekranındaki "Ekranı kapat (PIN)" — yalnız İSTEĞİ GÖNDEREN
    tahtanın ekranını kapatır. Kiosk sayfasında token yok; tahta, istek IP'sinin
    tahtalar.json'daki IP ile eşleşmesinden bulunur (2026-10-16: tahtada kapatma
    yolu yoktu, ekran kırmızı kaldı)."""
    ip = request.client.host if request.client else ""
    t = next((t for t in tahta_kaydi.tahtalari_yukle() if t["ip"] == ip), None)
    if t is None:
        raise HTTPException(403, "Bu istek bir tahtadan gelmiyor.")
    govde = await tahta_api._govde(request)
    zaman = datetime.now(ISTANBUL).isoformat(timespec="seconds")
    if not pin_dogru_mu(
        t["ad"], govde.get("pin", ""), _ayarlar()["pin_sha256"], time.monotonic()
    ):
        _olay_yaz({"zaman": zaman, "tur": "ekran_kapat_yanlis_pin", "tahta": t["ad"]})
        raise HTTPException(403, "PIN hatalı.")
    _olay_yaz({"zaman": zaman, "tur": "ekran_kapat_tahtadan", "tahta": t["ad"]})

    async def kapat():  # yanıt bu Chrome'a ulaşsın diye kısa gecikme
        await asyncio.sleep(1)
        await _tahta_ekran_kapat(t)

    gorev = asyncio.create_task(kapat())
    _arka_gorevler.add(gorev)  # referans tut: GC görevi yarıda bırakmasın
    gorev.add_done_callback(_arka_gorevler.discard)
    return JSONResponse({"tamam": True})


@router.post("/api/acil/tahta-alarm")
async def acil_tahta_alarm(request: Request):
    tahta = tahta_api._tahta_dogrula(request)
    govde = await tahta_api._govde(request)
    a = _ayarlar()
    simdi = time.monotonic()
    zaman = datetime.now(ISTANBUL)
    if not pin_dogru_mu(tahta, govde.get("pin", ""), a["pin_sha256"], simdi):
        _olay_yaz(
            {
                "zaman": zaman.isoformat(timespec="seconds"),
                "tur": "tahta_alarm_yanlis_pin",
                "tahta": tahta,
            }
        )
        raise HTTPException(403, "PIN hatalı.")
    tatbikat = bool(a.get("tahta_alarm_tatbikat", False))
    art_arda = bool(_son_tahta_alarmi) and simdi - _son_tahta_alarmi[-1] < ART_ARDA_SN
    _son_tahta_alarmi[:] = [simdi]
    kayit = await _baslat(
        a,
        "kilit",
        tatbikat,
        kaynak=f"tahta:{tahta}",
        sms_metni=tahta_alarm_metni(tahta, zaman.strftime("%H:%M")),
        yalniz_sms=art_arda,
    )
    return JSONResponse(
        {"tamam": True, "tatbikat": tatbikat, "kanallar": kayit["kanallar"]}
    )


@router.post("/api/acil/ekranlari-kapat")
async def acil_ekranlari_kapat(request: Request):
    _dogrula(request)
    sonuclar = await asyncio.gather(
        *(_tahta_ekran_kapat(t) for t in tahta_kaydi.tahtalari_yukle())
    )
    _olay_yaz(
        {
            "zaman": datetime.now(ISTANBUL).isoformat(timespec="seconds"),
            "tur": "ekranlari_kapat",
            "tahtalar": list(sonuclar),
        }
    )
    return JSONResponse({"tahtalar": list(sonuclar)})


# --- Yönetim paneli: durum, yanlış alarm, tahta alarm modu, zil (2026-10-16) ----------
ALARM_TURLERI = {"kilit", "tahliye", "deprem", "yangin"}
KAPATAN_TURLER = {"gecti", "yanlis_alarm", "ekranlari_kapat"}
YANLIS_ALARM_SMS = (
    "YANLIŞ ALARM: Az önceki acil durum uyarısı yanlıştır, olay yoktur. "
    "Normal düzene dönebilirsiniz."
)


def son_olaylar(n: int = 300) -> list[dict]:
    try:
        satirlar = OLAY_DOSYASI.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    olaylar = []
    for s in satirlar:
        try:
            olaylar.append(json.loads(s))
        except ValueError:
            continue
    return olaylar


def aktif_alarm(olaylar: list[dict]) -> dict | None:
    """En son alarm/kapatma olayına bakar: son anlamlı olay alarm ise aktiftir."""
    for o in reversed(olaylar):
        if o.get("tur") in KAPATAN_TURLER:
            return None
        if o.get("tur") in ALARM_TURLERI:
            return o
    return None


async def _yanlis_alarm(a: dict, kaynak: str | None, anons: bool = True) -> dict:
    son = aktif_alarm(son_olaylar()) or next(
        (o for o in reversed(son_olaylar()) if o.get("tur") in ALARM_TURLERI), {}
    )
    tatbikat = bool(son.get("tatbikat", True))

    def ses():
        _zil_tekrar_durdur()
        _zil_istek(a, "/youtube-cal/durdur")  # siren/anonsu keser
        if anons and a.get("anons_idleri", {}).get("gecti"):
            _zil_istek(a, f"/anons/cal/{a['anons_idleri']['gecti']}?acil=1")
            return {"kanal": "Zil", "basarili": True, "detay": "Ses durduruldu, 'Tehlike geçti' çalındı."}
        return {"kanal": "Zil", "basarili": True, "detay": "Ses durduruldu."}

    ek = _ek_kanallar(a, "gecti", tatbikat, kaynak, yanlis=True)
    sonuclar = await asyncio.gather(
        _guvenli("Zil", ses),
        _guvenli("SMS", _sms_gonder, a, "gecti", tatbikat, YANLIS_ALARM_SMS),
        *ek,
        *(_tahta_ekran_kapat(t) for t in tahta_kaydi.tahtalari_yukle()),
    )
    n_kanal = 2 + len(ek)
    kayit = {
        "zaman": datetime.now(ISTANBUL).isoformat(timespec="seconds"),
        "tur": "yanlis_alarm",
        "tatbikat": tatbikat,
        "istemci_ip": kaynak,
        "kanallar": list(sonuclar[:n_kanal]),
        "tahtalar": list(sonuclar[n_kanal:]),
    }
    _olay_yaz(kayit)
    return kayit


@router.get("/api/acil/durum")
async def acil_durum(request: Request):
    _dogrula(request)
    olaylar = son_olaylar()
    return JSONResponse({
        "aktif": aktif_alarm(olaylar),
        "olaylar": [
            {k: o.get(k) for k in ("zaman", "tur", "tatbikat", "istemci_ip", "tahta", "kanallar")}
            for o in reversed(olaylar[-25:])
        ],
        "tahta_alarm_tatbikat": bool(_ayarlar().get("tahta_alarm_tatbikat", False)),
        "turler": {k: {"baslik": v["baslik"], "renk": v["renk"]} for k, v in TURLER.items()},
    })


@router.post("/api/acil/yanlis-alarm")
async def acil_yanlis_alarm(request: Request):
    _dogrula(request)
    govde = await request.json()
    kaynak = f"panel:{request.client.host}" if request.client else "panel"
    return JSONResponse(await _yanlis_alarm(_ayarlar(), kaynak, bool(govde.get("anons", True))))


@router.post("/api/acil/tahta-modu")
async def acil_tahta_modu(request: Request):
    _dogrula(request)
    tatbikat = bool((await request.json()).get("tatbikat", True))
    a = _ayarlar()
    a["tahta_alarm_tatbikat"] = tatbikat
    CONFIG.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    _olay_yaz({"zaman": datetime.now(ISTANBUL).isoformat(timespec="seconds"),
               "tur": "tahta_modu", "tatbikat": tatbikat,
               "istemci_ip": request.client.host if request.client else None})
    return JSONResponse({"tahta_alarm_tatbikat": tatbikat})


@router.get("/api/acil/zil-anonslar")
async def acil_zil_anonslar(request: Request):
    _dogrula(request)
    try:
        return JSONResponse(await asyncio.to_thread(_zil_istek, _ayarlar(), "/acil/anonslar", "GET"))
    except Exception as e:
        raise HTTPException(502, f"Zile ulaşılamadı: {str(e)[:120]}")


@router.post("/api/acil/zil")
async def acil_zil(request: Request):
    """Panelden tek tek: siren, herhangi bir onaylı anons, sesi durdur."""
    _dogrula(request)
    govde = await request.json()
    eylem, anons_id = govde.get("eylem"), str(govde.get("id", ""))
    yollar = {"siren": "/acil/siren-cal", "durdur": "/youtube-cal/durdur"}
    if eylem == "anons" and anons_id.isalnum() and len(anons_id) == 8:
        yol = f"/anons/cal/{anons_id}"
    elif eylem in yollar:
        yol = yollar[eylem]
    else:
        raise HTTPException(400, "Geçersiz eylem.")
    if eylem == "durdur":
        _zil_tekrar_durdur()
    try:
        sonuc = await asyncio.to_thread(_zil_istek, _ayarlar(), yol)
    except Exception as e:
        raise HTTPException(502, f"Zile ulaşılamadı: {str(e)[:120]}")
    _olay_yaz({"zaman": datetime.now(ISTANBUL).isoformat(timespec="seconds"), "tur": f"zil_{eylem}",
               "anons_id": anons_id or None, "istemci_ip": request.client.host if request.client else None})
    return JSONResponse(sonuc)


# --- Makine API (zil Telegram botu /acil) — X-Acil-Anahtar ------------------------
def _makine_dogrula(request: Request) -> None:
    beklenen = _ayarlar().get("makine_anahtar", "")
    gelen = request.headers.get("X-Acil-Anahtar", "")
    if not beklenen or not hmac.compare_digest(gelen, beklenen):
        raise HTTPException(401, "Anahtar geçersiz.")


SMS_METNI_AZAMI = 160


def _kaynak_etiketi(govde: dict) -> str:
    return "".join(c for c in str(govde.get("kaynak", "makine"))[:40] if c.isprintable())


@router.post("/api/acil/makine/tetikle")
async def acil_makine_tetikle(request: Request):
    _makine_dogrula(request)
    govde = await tahta_api._govde(request)
    tur = govde.get("tur")
    if tur not in TURLER:
        raise HTTPException(400, "Geçersiz tür.")
    a = _ayarlar()
    # tatbikat verilmezse tahta alarm modu (config) belirler; zil botu açıkça gönderdiği için etkilenmez.
    tatbikat = govde.get("tatbikat")
    tatbikat = bool(a.get("tahta_alarm_tatbikat", True)) if tatbikat is None else bool(tatbikat)
    sms_metni = govde.get("sms_metni")
    if sms_metni is not None:
        sms_metni = "".join(c for c in str(sms_metni) if c.isprintable()).strip()[:SMS_METNI_AZAMI] or None
    kayit = await _baslat(a, tur, tatbikat, kaynak=_kaynak_etiketi(govde), sms_metni=sms_metni)
    return JSONResponse(kayit)


@router.get("/api/acil/makine/durum")
async def acil_makine_durum(request: Request):
    """Okul portalı için: aktif alarm var mı ve alarm modu tatbikat mı."""
    _makine_dogrula(request)
    aktif = aktif_alarm(son_olaylar())
    return JSONResponse({
        "aktif": {k: aktif.get(k) for k in ("zaman", "tur", "tatbikat", "istemci_ip")} if aktif else None,
        "tatbikat": bool(_ayarlar().get("tahta_alarm_tatbikat", True)),
    })


@router.post("/api/acil/makine/yanlis-alarm")
async def acil_makine_yanlis_alarm(request: Request):
    _makine_dogrula(request)
    govde = await tahta_api._govde(request)
    return JSONResponse(await _yanlis_alarm(_ayarlar(), _kaynak_etiketi(govde)))
