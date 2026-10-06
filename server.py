"""server.py - Sınıf Arenası Ana Backend Servisi (Port 8030).

Akıllı tahta IP'sini tanır, okul zil/ders saatini ve ders adını çözer,
yoklama panosundan devamsız öğrencileri filtreler, dengeli tematik takımlar
kurar, MEB RAG + Ollama entegrasyonuyla soruları sunar ve kalıcı loglama/sağlık
tanısı sağlar.
"""

import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import logger
import soru_uretici
import takim_kurucu
import fetih_motoru
import havuz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("arena_server")

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

# Dosya yolları (Farabi ekosistemi)
BASE_DIR = Path(__file__).resolve().parent
TAHTALAR_JSON = Path("/home/ata/farabi/server/tahtalar.json")
ZIL_JSON = Path("/home/ata/farabi/tahtayoklama/data/zil.json")
DERS_PROGRAMI_JSON = Path("/home/ata/farabi/tahtayoklama/data/ders_programi.json")
ROSTER_DIR = Path("/home/ata/farabi/tahtayoklama/data/roster")
YOKLAMA_DB = Path("/home/ata/farabi/tahtayoklama/dashboard/veri/yoklama_pano.db")

HTML_DOSYASI = BASE_DIR / "sinif_arena.html"
HTML_FETIH_DOSYASI = BASE_DIR / "hexafetih.html"
HTML_DUELLO_DOSYASI = BASE_DIR / "duello.html"

_GUN_ADLARI = {
    1: "pazartesi",
    2: "sali",
    3: "carsamba",
    4: "persembe",
    5: "cuma",
}

def sinif_duzeyi_coz(sinif: str) -> int:
    """'11-A' → 11; 'fenlab' → 12 (2026-10-05 kullanıcı kararı); bilinmeyen → 9."""
    m = re.match(r"^(\d+)", sinif or "")
    if m:
        return int(m.group(1))
    return 12 if (sinif or "").strip().lower() == "fenlab" else 9


TUM_SINIFLAR = ["9-A", "9-B", "10-A", "11-A", "11-B", "12-A", "12-B", "fenlab"]
TUM_DERSLER = [
    "Biyoloji",
    "Matematik",
    "Fizik",
    "Kimya",
    "Tarih",
    "Türk Dili ve Edebiyatı",
    "Coğrafya",
    "Felsefe",
    "Din Kültürü ve Ahlak Bilgisi",
    "İngilizce",
    "Bilişim Teknolojileri ve Yazılım",
    "Sağlık Bilgisi ve Trafik Kültürü",
    "Görsel Sanatlar ve Müzik",
    "Genel Kültür",
]

app = FastAPI(title="Sınıf Arenası Servisi", version="2.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ip_den_sinif_bul(ip: str) -> str:
    """Tahtanın IP adresinden sınıf adını çözer."""
    if not TAHTALAR_JSON.exists():
        return "9-A"
    try:
        data = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
        for sinif_adi, bilgi in data.items():
            if isinstance(bilgi, dict) and bilgi.get("ip") == ip:
                return sinif_adi
    except Exception as e:
        log.warning("tahtalar.json okuma hatası: %s", e)
    return "9-A"


def _saat_ayristir(s: str):
    saat, dakika = s.split(":")
    return int(saat), int(dakika)


def _simdiki_ders_bilgisi(simdi: datetime | None = None) -> tuple[int, bool]:
    """Zil saatlerine göre o anki ders numarasını döner (1-8)."""
    simdi = simdi or datetime.now(ISTANBUL_TZ)
    if not ZIL_JSON.exists():
        return 1, False

    try:
        zil_verisi = json.loads(ZIL_JSON.read_text(encoding="utf-8"))
        dersler = zil_verisi.get("dersler", [])
        simdi_dakika = simdi.hour * 60 + simdi.minute

        for ders in dersler:
            b_saat, b_dakika = _saat_ayristir(ders["baslangic"])
            s_saat, s_dakika = _saat_ayristir(ders["bitis"])
            baslangic_dk = b_saat * 60 + b_dakika
            bitis_dk = s_saat * 60 + s_dakika

            if baslangic_dk <= simdi_dakika < bitis_dk:
                return ders["no"], True
            if simdi_dakika < baslangic_dk:
                return ders["no"], False
    except Exception as e:
        log.warning("Zil dosyası okunamadı: %s", e)

    return 1, False


def _ders_adini_bul(sinif: str, gun_no: int, ders_no: int) -> str:
    """Haftalık ders programından dersin adını bulur."""
    gun_adi = _GUN_ADLARI.get(gun_no, "pazartesi")
    if not DERS_PROGRAMI_JSON.exists():
        return "Biyoloji"

    try:
        program = json.loads(DERS_PROGRAMI_JSON.read_text(encoding="utf-8")).get("siniflar", {})
        ders = program.get(sinif, {}).get(gun_adi, {}).get(str(ders_no))
        if ders:
            kelimeler = ders.split()
            return " ".join(k.capitalize() if k not in ["ve", "ile"] else k for k in kelimeler)
    except Exception as e:
        log.warning("Ders programı okunamadı: %s", e)

    return "Biyoloji"


def _ogrencileri_ve_yoklamayi_getir(sinif: str, ders_no: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Sınıf listesini ve o günkü yoklama durumunu çekerek mevcut/devamsız ayrımı yapar."""
    roster_dosyasi = ROSTER_DIR / f"{sinif}.json"
    tum_ogrenciler = []
    if roster_dosyasi.exists():
        try:
            veri = json.loads(roster_dosyasi.read_text(encoding="utf-8"))
            tum_ogrenciler = veri.get("ogrenciler", [])
        except Exception as e:
            log.warning("Roster okuma hatası: %s", e)

    devamsiz_isimler = set()
    bugun_str = datetime.now(ISTANBUL_TZ).date().isoformat()

    if YOKLAMA_DB.exists():
        try:
            conn = sqlite3.connect(YOKLAMA_DB)
            cur = conn.cursor()
            # 1. Önce bugünün o dersine bak
            cur.execute(
                "SELECT yok_isimleri, izinli_isimleri FROM yoklama_onbellek WHERE tarih = ? AND sinif = ? AND ders_no = ?",
                (bugun_str, sinif, ders_no),
            )
            satir = cur.fetchone()
            # 2. Bugünün herhangi bir dersine bak
            if not satir:
                cur.execute(
                    "SELECT yok_isimleri, izinli_isimleri FROM yoklama_onbellek WHERE tarih = ? AND sinif = ? ORDER BY ders_no DESC LIMIT 1",
                    (bugun_str, sinif),
                )
                satir = cur.fetchone()
            # 3. Bugün hiç yoklama yoksa en son kaydedilmiş güne bak
            if not satir:
                cur.execute(
                    "SELECT yok_isimleri, izinli_isimleri FROM yoklama_onbellek WHERE sinif = ? ORDER BY tarih DESC, ders_no DESC LIMIT 1",
                    (sinif,),
                )
                satir = cur.fetchone()

            if satir:
                yoklar = json.loads(satir[0]) if satir[0] else []
                izinliler = json.loads(satir[1]) if satir[1] else []
                devamsiz_isimler = set(yoklar + izinliler)
            conn.close()
        except Exception as e:
            log.warning("Yoklama DB sorgulama hatası: %s", e)

    mevcutlar = []
    devamsizlar = []

    for o in tum_ogrenciler:
        ad = o.get("ad_soyad", "")
        if ad in devamsiz_isimler:
            devamsizlar.append({**o, "mevcut": False})
        else:
            mevcutlar.append({**o, "mevcut": True})

    return tum_ogrenciler, mevcutlar, devamsizlar


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # 204 No Content döner (404 hatasını önler)
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index():
    if not HTML_DOSYASI.exists():
        raise HTTPException(status_code=404, detail="sinif_arena.html bulunamadı.")
    return HTML_DOSYASI.read_text(encoding="utf-8")


@app.get("/api/arena/oturum")
async def oturum_bilgisi(request: Request, sinif: str | None = None, ders: str | None = None, ip: str | None = None):
    """Tahtanın açılış durumunu: sınıf, ders, yoklama, takımlar ve soruları tek pakette döner."""
    istemci_ip = ip or (request.client.host if request.client else "127.0.0.1")

    # Sınıf belirle
    secilen_sinif = sinif or _ip_den_sinif_bul(istemci_ip)
    if secilen_sinif not in TUM_SINIFLAR:
        secilen_sinif = "9-A"

    sinif_duzeyi = sinif_duzeyi_coz(secilen_sinif)

    # Ders ve zaman belirle
    simdi = datetime.now(ISTANBUL_TZ)
    ders_no, ders_saatinde_mi = _simdiki_ders_bilgisi(simdi)
    gun_no = simdi.isoweekday()
    ders_adi = ders or _ders_adini_bul(secilen_sinif, gun_no, ders_no)

    # Öğrenci listesi ve yoklama
    tum_ogrenciler, mevcut_ogrenciler, devamsiz_ogrenciler = _ogrencileri_ve_yoklamayi_getir(secilen_sinif, ders_no)

    # Takımları oluştur
    takimlar = takim_kurucu.takimlari_olustur(mevcut_ogrenciler, ders_adi, takim_sayisi=4)

    # Hazır soruları al (0 sn bekleme)
    sorular = soru_uretici.hazir_sorulari_getir(ders_adi)

    # Kalıcı log kaydı
    logger.log_oturum(
        ip=istemci_ip,
        sinif=secilen_sinif,
        ders_no=ders_no,
        ders_adi=ders_adi,
        mevcut=len(mevcut_ogrenciler),
        devamsiz=len(devamsiz_ogrenciler),
    )

    return {
        "sinif": secilen_sinif,
        "sinif_duzeyi": sinif_duzeyi,
        "tahta_ip": istemci_ip,
        "ders_no": ders_no,
        "ders_saatinde_mi": ders_saatinde_mi,
        "gun": _GUN_ADLARI.get(gun_no, "hafta sonu"),
        "ders_adi": ders_adi,
        "toplam_ogrenci": len(tum_ogrenciler),
        "mevcut_sayisi": len(mevcut_ogrenciler),
        "devamsiz_sayisi": len(devamsiz_ogrenciler),
        "ogrenciler": tum_ogrenciler,
        "mevcut_ogrenciler": mevcut_ogrenciler,
        "devamsiz_ogrenciler": devamsiz_ogrenciler,
        "takimlar": takimlar,
        "sorular": sorular,
        "tum_siniflar": TUM_SINIFLAR,
        "tum_dersler": TUM_DERSLER,
    }


class SoruUretIstek(BaseModel):
    sinif: str
    ders: str
    konu: str = ""


@app.post("/api/arena/soru-uret")
async def soru_uret(request: Request, istek: SoruUretIstek):
    """MEB RAG ve yerel Ollama (qwen3.8:27b) ile canlı Jeopardy seti üretir."""
    istemci_ip = request.client.host if request.client else "127.0.0.1"
    sinif_duzeyi = sinif_duzeyi_coz(istek.sinif)
    t0 = time.perf_counter()

    # 0. Soru havuzu (yalnızca AGY onaylı) — anında; yoksa canlı RAG+Ollama
    ders_anahtari = soru_uretici.KAPSAM_ESLEME.get(istek.ders.strip().lower(), istek.ders.strip().lower())
    havuz_seti = havuz.jeopardy_seti(ders_anahtari, sinif_duzeyi, istek.konu)
    if havuz_seti:
        gecen_sn = time.perf_counter() - t0
        logger.log_soru_uret(ip=istemci_ip, sinif=istek.sinif, ders=istek.ders, konu=istek.konu,
                             kaynak="soru_havuzu", sure_sn=gecen_sn, durum="ok")
        return {"durum": "ok", "kaynak": "soru_havuzu", "sure_sn": round(gecen_sn, 1), "sorular": havuz_seti}

    # 1. RAG ile kitap içeriği ara
    rag_parcalari = await soru_uretici.rag_icerik_ara(istek.ders, sinif_duzeyi, istek.konu)

    # 2. Ollama ile soruları üret
    yeni_sorular = await soru_uretici.ollama_soru_uret(istek.ders, sinif_duzeyi, istek.konu, rag_parcalari)
    gecen_sn = time.perf_counter() - t0

    if yeni_sorular:
        logger.log_soru_uret(
            ip=istemci_ip,
            sinif=istek.sinif,
            ders=istek.ders,
            konu=istek.konu,
            kaynak="rag_ollama",
            sure_sn=gecen_sn,
            durum="ok",
        )
        return {"durum": "ok", "kaynak": "rag_ollama", "sure_sn": round(gecen_sn, 1), "sorular": yeni_sorular}

    # Ollama yanıt veremezse hazır sorulara güvenli dönüş
    fallback = soru_uretici.hazir_sorulari_getir(istek.ders)
    logger.log_soru_uret(
        ip=istemci_ip,
        sinif=istek.sinif,
        ders=istek.ders,
        konu=istek.konu,
        kaynak="hazir_havuz",
        sure_sn=gecen_sn,
        durum="fallback",
        hata="Ollama zaman aşımı veya yanıt biçim hatası",
    )
    return {
        "durum": "fallback",
        "mesaj": "Yapay zeka soru seti oluştururken hazır müfredat paketine geçildi.",
        "sure_sn": round(gecen_sn, 1),
        "sorular": fallback,
    }


class TakimYenileIstek(BaseModel):
    sinif: str
    ders: str
    takim_sayisi: int = 4


@app.post("/api/arena/takim-yenile")
async def takim_yenile(request: Request, istek: TakimYenileIstek):
    """Mevcut öğrencileri belirtilen sayıda takıma yeniden dengeli dağıtır."""
    istemci_ip = request.client.host if request.client else "127.0.0.1"
    _, mevcut_ogrenciler, _ = _ogrencileri_ve_yoklamayi_getir(istek.sinif, ders_no=1)
    takimlar = takim_kurucu.takimlari_olustur(mevcut_ogrenciler, istek.ders, istek.takim_sayisi)

    logger.log_takim_yenile(
        ip=istemci_ip,
        sinif=istek.sinif,
        ders=istek.ders,
        takim_sayisi=istek.takim_sayisi,
        takimlar=takimlar,
    )
    return {"durum": "ok", "takimlar": takimlar}


class IstemciHataIstek(BaseModel):
    mesaj: str
    kaynak_url: str = ""
    satir: int = 0
    sutun: int = 0
    stack: str = ""
    user_agent: str = ""


@app.post("/api/arena/log-hata")
async def log_hata_endpoint(request: Request, hata: IstemciHataIstek):
    """Akıllı tahtanın tarayıcısında oluşan JS ve çalışma zamanı hatalarını kaydeder."""
    istemci_ip = request.client.host if request.client else "127.0.0.1"
    logger.log_istemci_hata(
        ip=istemci_ip,
        mesaj=hata.mesaj,
        kaynak_url=hata.kaynak_url,
        satir=hata.satir,
        sutun=hata.sutun,
        stack=hata.stack,
        user_agent=hata.user_agent,
    )
    return {"durum": "kaydedildi"}


@app.get("/api/arena/saglik")
async def saglik_kontrolu():
    """Tüm bağlı servislerin (Farabi Brain RAG, Ollama, Yoklama DB) sağlık durumunu kontrol eder."""
    saglik_raporu = {
        "zaman": datetime.now(ISTANBUL_TZ).isoformat(),
        "genel_durum": "ok",
        "servisler": {},
    }

    async with httpx.AsyncClient(timeout=3.0) as client:
        # 1. Farabi Brain API (8000) kontrolü
        t0 = time.perf_counter()
        try:
            r = await client.get("http://127.0.0.1:8000/health")
            ms = int((time.perf_counter() - t0) * 1000)
            saglik_raporu["servisler"]["farabi_brain"] = {
                "durum": "ok" if r.status_code == 200 else "uyari",
                "gecikme_ms": ms,
                "detay": "RAG pgvector servisi aktif",
            }
        except Exception as e:
            saglik_raporu["servisler"]["farabi_brain"] = {
                "durum": "hata",
                "detay": str(e),
            }
            saglik_raporu["genel_durum"] = "uyari"

        # 2. Ollama (11434) kontrolü
        t0 = time.perf_counter()
        try:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            ms = int((time.perf_counter() - t0) * 1000)
            saglik_raporu["servisler"]["ollama"] = {
                "durum": "ok" if r.status_code == 200 else "uyari",
                "gecikme_ms": ms,
                "model": "qwen3.8:27b (2x RTX 3060)",
            }
        except Exception as e:
            saglik_raporu["servisler"]["ollama"] = {
                "durum": "hata",
                "detay": str(e),
            }
            saglik_raporu["genel_durum"] = "uyari"

    # 3. Yoklama SQLite DB kontrolü
    if YOKLAMA_DB.exists():
        try:
            conn = sqlite3.connect(YOKLAMA_DB)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM ogrenciler;")
            ogr_sayisi = cur.fetchone()[0]
            conn.close()
            saglik_raporu["servisler"]["yoklama_db"] = {
                "durum": "ok",
                "kayitli_ogrenci": ogr_sayisi,
            }
        except Exception as e:
            saglik_raporu["servisler"]["yoklama_db"] = {"durum": "hata", "detay": str(e)}
            saglik_raporu["genel_durum"] = "uyari"
    else:
        saglik_raporu["servisler"]["yoklama_db"] = {"durum": "uyari", "detay": "Veritabanı dosyası bulunamadı"}

    return saglik_raporu


@app.get("/api/arena/loglar")
async def loglar_endpoint(limit: int = 50, sadece_hata: bool = False):
    """En son log kayıtlarını döner."""
    satirlar = logger.son_loglari_getir(limit=limit, sadece_hata=sadece_hata)
    return {
        "toplam": len(satirlar),
        "sadece_hata": sadece_hata,
        "loglar": satirlar,
    }


# =====================================================================
# HEXAFETİH (BÖLGE FETHİ VE STRATEJİ ARENASI) UÇ NOKTALARI
# =====================================================================


@app.get("/arena", response_class=HTMLResponse)
async def arena_page():
    """Sınıf Arenası (Jeopardy) doğrudan erişim rotası."""
    if not HTML_DOSYASI.exists():
        raise HTTPException(status_code=404, detail="sinif_arena.html bulunamadı.")
    return HTML_DOSYASI.read_text(encoding="utf-8")


@app.get("/fetih", response_class=HTMLResponse)
async def fetih_page():
    """HexaFetih (Bölge Fetih & Strateji) arayüzünü sunar."""
    if not HTML_FETIH_DOSYASI.exists():
        raise HTTPException(status_code=404, detail="hexafetih.html bulunamadı.")
    return HTML_FETIH_DOSYASI.read_text(encoding="utf-8")


@app.get("/api/fetih/oturum")
async def fetih_oturum(request: Request, sinif: str | None = None, ders: str | None = None, ip: str | None = None):
    """HexaFetih açılış durumunu: sınıf, ders, yoklama, dengeli takımlar ve 19 peteklik haritayı döner."""
    istemci_ip = ip or (request.client.host if request.client else "127.0.0.1")

    # Sınıf belirle
    secilen_sinif = sinif or _ip_den_sinif_bul(istemci_ip)
    if secilen_sinif not in TUM_SINIFLAR:
        secilen_sinif = "9-A"

    # Ders ve zaman belirle
    simdi = datetime.now(ISTANBUL_TZ)
    ders_no, _ = _simdiki_ders_bilgisi(simdi)
    gun_no = simdi.isoweekday()
    ders_adi = ders or _ders_adini_bul(secilen_sinif, gun_no, ders_no)

    # Yoklama ve mevcut öğrenciler
    tum_ogrenciler, mevcut_ogrenciler, devamsiz_ogrenciler = _ogrencileri_ve_yoklamayi_getir(secilen_sinif, ders_no)

    # 4 Takım oluştur (HexaFetih 4 takım: Mavi, Kırmızı, Yeşil, Sarı)
    takimlar = takim_kurucu.takimlari_olustur(mevcut_ogrenciler, ders_adi, takim_sayisi=4)

    # 19 Peteklik dinamik haritayı hazırla
    harita = fetih_motoru.haritayi_hazirla(ders_adi, sinif_duzeyi_coz(secilen_sinif))

    logger.log_olay(
        olay="FETIH_OTURUM",
        detay=f"IP: {istemci_ip} | Sınıf: {secilen_sinif} | Ders: {ders_adi} | Mevcut: {len(mevcut_ogrenciler)} | Petek: {len(harita)}",
    )

    return {
        "durum": "ok",
        "sinif": secilen_sinif,
        "ders": ders_adi,
        "ders_no": ders_no,
        "toplam_ogrenci": len(tum_ogrenciler),
        "mevcut_ogrenci": len(mevcut_ogrenciler),
        "devamsiz_ogrenci": len(devamsiz_ogrenciler),
        "ogrenciler": mevcut_ogrenciler,
        "takimlar": takimlar,
        "harita": harita,
        "tum_siniflar": TUM_SINIFLAR,
        "tum_dersler": TUM_DERSLER,
    }


class FetihHamleIstek(BaseModel):
    dugum_id: int
    takim_index: int
    dogru_mu: bool
    saldiri_mi: bool = False
    harita: list[dict[str, Any]]


@app.post("/api/fetih/hamle")
async def fetih_hamle(request: Request, istek: FetihHamleIstek):
    """HexaFetih hamlesini işler, bölge sahipliğini, puan değişimini ve kombo bonuslarını hesaplar."""
    istemci_ip = request.client.host if request.client else "127.0.0.1"
    harita = istek.harita

    # İlgili düğümü bul
    hedef_dugum = None
    for d in harita:
        if d.get("id") == istek.dugum_id:
            hedef_dugum = d
            break

    if not hedef_dugum:
        raise HTTPException(status_code=404, detail=f"Düğüm {istek.dugum_id} bulunamadı.")

    puan_degisimi = 0
    kombo_bonus = 0
    eski_sahip = hedef_dugum.get("sahip")
    mesaj = ""

    if istek.dogru_mu:
        # Doğru cevap verildi
        if istek.saldiri_mi and eski_sahip is not None and eski_sahip != istek.takim_index:
            # Başarılı Düşman Bölgesi Saldırısı (1.5x puan)
            hedef_dugum["sahip"] = istek.takim_index
            puan_degisimi = int(hedef_dugum.get("puan", 100) * 1.5)
            mesaj = f"Düşman bölgesi fethedildi! +{puan_degisimi} Puan"
        else:
            # Boş bölge fethi
            hedef_dugum["sahip"] = istek.takim_index
            puan_degisimi = hedef_dugum.get("puan", 100)
            mesaj = f"Bölge fethedildi! +{puan_degisimi} Puan"

        # Kombo Bağlantı Kontrolü (3 veya daha fazla bitişik petek)
        kombo_boyutu = fetih_motoru.baglantili_kombo_hesapla(harita, istek.takim_index)
        if kombo_boyutu >= 3:
            kombo_bonus = 150
            mesaj += f" | {kombo_boyutu}'lü Hat Kombo Bonusu! +150 Puan"
    else:
        # Yanlış cevap verildi
        if istek.saldiri_mi:
            # Saldırı başarısız, saldıran takım puan kaybeder
            puan_degisimi = -50
            mesaj = "Saldırı püskürtüldü! -50 Puan ceza"
        else:
            puan_degisimi = 0
            mesaj = "Soru bilinemedi, bölge sahipsiz kaldı."

    logger.log_olay(
        olay="FETIH_HAMLE",
        detay=f"IP: {istemci_ip} | Takım: {istek.takim_index} | Petek: {istek.dugum_id} | Doğru: {istek.dogru_mu} | Puan: {puan_degisimi} | Kombo: {kombo_bonus}",
    )

    return {
        "durum": "ok",
        "dugum_id": istek.dugum_id,
        "takim_index": istek.takim_index,
        "puan_degisimi": puan_degisimi,
        "kombo_bonus": kombo_bonus,
        "eski_sahip": eski_sahip,
        "yeni_sahip": hedef_dugum.get("sahip"),
        "mesaj": mesaj,
        "harita": harita,
    }


# =====================================================================
# TAHTA DÜELLOSU (DÜELLO ÇARKI & 10 SORULUK MARATON) UÇ NOKTALARI
# =====================================================================


@app.get("/duello", response_class=HTMLResponse)
async def duello_page():
    """Tahta Düellosu (Düello Çarkı & Hızlı Cevap Yarışması) arayüzünü sunar."""
    if not HTML_DUELLO_DOSYASI.exists():
        raise HTTPException(status_code=404, detail="duello.html bulunamadı.")
    return HTML_DUELLO_DOSYASI.read_text(encoding="utf-8")


@app.get("/api/duello/oturum")
async def duello_oturum(request: Request, sinif: str | None = None, ders: str | None = None, ip: str | None = None):
    """Tahta Düellosu açılış oturumu: sınıf, yoklama, mevcut öğrenciler ve sorular."""
    istemci_ip = ip or (request.client.host if request.client else "127.0.0.1")

    secilen_sinif = sinif or _ip_den_sinif_bul(istemci_ip)
    if secilen_sinif not in TUM_SINIFLAR:
        secilen_sinif = "9-A"

    sinif_duzeyi = sinif_duzeyi_coz(secilen_sinif)
    simdi = datetime.now(ISTANBUL_TZ)
    ders_no, ders_saatinde_mi = _simdiki_ders_bilgisi(simdi)
    gun_no = simdi.isoweekday()
    ders_adi = ders or _ders_adini_bul(secilen_sinif, gun_no, ders_no)

    tum_ogrenciler, mevcut_ogrenciler, devamsiz_ogrenciler = _ogrencileri_ve_yoklamayi_getir(secilen_sinif, ders_no)

    ders_anahtari = soru_uretici.KAPSAM_ESLEME.get(ders_adi.strip().lower(), ders_adi.strip().lower())
    sorular = havuz.duello_sorulari(ders_anahtari, sinif_duzeyi, adet=10)
    kaynak = "soru_havuzu" if sorular else "hazir"

    if not sorular:
        hazir = soru_uretici.hazir_sorulari_getir(ders_adi)
        duz = []
        for kat in (hazir or []):
            for q in kat.get("questions", []):
                duz.append({
                    "konu": kat.get("name", "Genel"),
                    "q": q.get("q", ""),
                    "secenekler": [q.get("a", ""), "B şıkkı", "C şıkkı", "D şıkkı"],
                    "a": q.get("a", ""),
                    "kaynak": "MEB Hazır Soru",
                })
        import random
        random.shuffle(duz)
        sorular = duz[:10] if duz else []

    return {
        "durum": "ok",
        "sinif": secilen_sinif,
        "sinif_duzeyi": sinif_duzeyi,
        "ders": ders_adi,
        "ders_no": ders_no,
        "ogrenciler": mevcut_ogrenciler if mevcut_ogrenciler else tum_ogrenciler,
        "tum_ogrenciler": tum_ogrenciler,
        "sorular": sorular,
        "kaynak": kaynak,
        "tum_siniflar": TUM_SINIFLAR,
        "tum_dersler": TUM_DERSLER,
    }


@app.get("/api/duello/sorular")
async def duello_sorular_api(ders: str = "Biyoloji", sinif: int = 9, adet: int = 10):
    """Yeni bir düello maratonu için 10 soru döner."""
    ders_anahtari = soru_uretici.KAPSAM_ESLEME.get(ders.strip().lower(), ders.strip().lower())
    sorular = havuz.duello_sorulari(ders_anahtari, sinif, adet=adet)
    kaynak = "soru_havuzu" if sorular else "hazir"

    if not sorular:
        hazir = soru_uretici.hazir_sorulari_getir(ders)
        duz = []
        for kat in (hazir or []):
            for q in kat.get("questions", []):
                duz.append({
                    "konu": kat.get("name", "Genel"),
                    "q": q.get("q", ""),
                    "secenekler": [q.get("a", ""), "B şıkkı", "C şıkkı", "D şıkkı"],
                    "a": q.get("a", ""),
                    "kaynak": "MEB Hazır Soru",
                })
        import random
        random.shuffle(duz)
        sorular = duz[:adet] if duz else []

    return {"durum": "ok", "kaynak": kaynak, "sorular": sorular}

