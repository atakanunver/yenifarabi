"""server/ses_cephe.py — Faz 1a: Brain'e OpenAI-uyumlu ses cephesi.

Plan: docs/superpowers/plans/2026-09-25-ses-cephe.md. Gemini Live → yerel
ses (Pipecat) geçişinin Brain tarafı — ses düğümü (Faz 1b) ve tahta (Faz 1c)
bu dosyanın KAPSAMI DIŞINDA. Bu router, ses düğümünün `/v1/chat/completions`
(OpenAI biçimi) ile konuştuğu, Ollama'yı (`qwen2.5:14b`) ajan döngüsüyle
süren, RAG'a (`rag.py`, DEĞİŞTİRİLMEDİ) ve `icerik.py`'ye (DEĞİŞTİRİLMEDİ)
ince bir köprü.

TASARIM — tek çekirdek, iki adaptör (`_ajan_calistir`): SSE (`stream: true`)
ve tek JSON (`stream: false`) yanıtları AYNI iç olay üretecini (`("icerik",
metin)` / `("arac_cagrisi", ad, args, id)` / `("arac_secildi", ad)` /
`("bitti", sebep)`) tüketir — yeniden deneme/düşüş mantığı iki yerde
kopyalanmasın diye.

DÖNGÜSEL IMPORT: `main.py` bu modülü import ediyor (`include_router`); bu
modül DE `main.durum`'a (RAG modelleri/DB hazır mı) ihtiyaç duyuyor ama
`main`'i modül SEVİYESİNDE import EDEMEZ (döngü). `_durum()` bu yüzden
`main`'i yalnızca ÇAĞRILDIĞINDA, fonksiyon içinde import eder.

Ollama'nın gerçek stream davranışı bu turda curl ile doğrulandı
(2026-09-25, `qwen2.5:14b`, ollama 0.32.6): normal içerik token-token akıyor
(`{"message":{"content":"parça"},"done":false}` art arda), ama bir
`tool_calls` kararı TEK bir chunk'ta, BÜTÜN olarak geliyor
(`done:false`, `content:""`, `tool_calls:[{"id":...,"function":{"index":0,
"name":...,"arguments":{...}}}]`) — `arguments` JSON STRING değil, DOĞRUDAN
bir obje. En sonda `content:""`, `done:true` kapanış chunk'ı geliyor.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import auth
import db
import httpx
import icerik
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

log = logging.getLogger("ses_cephe")

BASE_DIR = Path(__file__).resolve().parent
PERSONA_PATH = BASE_DIR / "ses_persona.txt"

MODEL_ID = "farabi-brain"

# Taşınabilirlik için env ile ezilebilir modül sabitleri (plan madde 3) —
# yalnızca modül yüklenirken bir kez okunur, FARABI_SES_TOKEN/IZINLI'nin
# aksine (onlar HER istekte okunur, bkz. `_erisim`, testlerde monkeypatch
# edilebilsin diye).
OLLAMA_HOST = os.environ.get("FARABI_SES_OLLAMA", "127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("FARABI_SES_MODEL", "qwen2.5:14b")

# Ollama'ya ASLA num_ctx ya da temperature DIŞINDA bir `options` alanı
# gönderilmez — farklı bir num_ctx paylaşılan üretim modelini (qwen2.5:14b,
# tahtaların RAG'ı da aynı modeli kullanıyor) yeniden yükletir (CLAUDE.md
# "Kesin sınırlar"). `keep_alive` de BİLEREK gönderilmiyor — `ollama ps`
# modelin süresiz (Forever) yüklü kalması için ayarlı, bir keep_alive değeri
# göndermek bunu değiştirebilir.
KARAR_ZAMAN_ASIMI_SN = 10.0     # ilk içerik/tool_calls'a kadar (plan madde 3)
GENEL_ZAMAN_ASIMI_SN = 30.0     # bir Ollama turunun tamamı için tavan

MAX_SORU_KARAKTER = 500         # rag.py::SoruIstek ile AYNI sınır — reranker
                                 # CUDA OOM koruması (main.py'deki gerekçeyle
                                 # aynı); burada doğrudan motor.sorgula()
                                 # çağrıldığı için o kapı devreye girmiyor,
                                 # bu yüzden aynı sınır burada da uygulanır.
MAX_GECMIS_TOKEN = 2000
KARAKTER_PER_TOKEN = 2.7        # Faz 0 ölçümü: 36.061 karakter → 13.403 token

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

KIPLER = ("ogretmenli", "ogretmensiz", "talimat")
VARSAYILAN_KIP = "ogretmenli"

_DERSLIK_DUZEY_RE = re.compile(r"^(\d{1,2})")


# ── Araç şemaları — parametre ADLARI client/actions/kayit.py ile BİREBİR ───
# aynı (plan "Persona ve araçlar" tablosu). Ollama native /api/chat JSON
# Schema bekliyor (küçük harf "object"/"string"/...), kayit.py'nin Gemini
# biçimindeki (büyük harf "OBJECT"/"STRING") şemaları buraya DOĞRUDAN
# kopyalanamaz — yalnızca alan adları ortak.
ARAC_TANIMLARI: dict[str, dict] = {
    "kitap_sorusu": {
        "kipler": ("ogretmenli", "ogretmensiz", "talimat"),
        "sema": {
            "type": "function",
            "function": {
                "name": "kitap_sorusu",
                "description": (
                    "Öğrencinin ya da öğretmenin somut bir sorusunu, sunucudaki "
                    "RAG motoruna (retrieval + rerank + eşik + LLM) sorar; "
                    "kaynağı doğrulanmış kısa bir cevap döner. Bir tanım, "
                    "'nedir', 'neden', 'nasıl' sorusu ya da kitaba dayalı her "
                    "bilgi sorusu için MUTLAKA bunu çağır, kendi bilginle "
                    "ASLA cevaplama."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "soru":  {"type": "string", "description": "Sorulan soru."},
                        "ders":  {"type": "string", "description": "Ders adı, örn. 'biyoloji'."},
                        "sinif": {"type": "string", "description": "Sınıf düzeyi, örn. '9'."},
                    },
                    "required": ["soru"],
                },
            },
        },
    },
    "ders_icerigi": {
        "kipler": ("ogretmenli", "ogretmensiz"),
        "sema": {
            "type": "function",
            "function": {
                "name": "ders_icerigi",
                "description": (
                    "Öğretmenin verdiği konu için ders kitabı sayfalarını "
                    "getirir — konu anlatımının iskeleti. Bir KONUNUN BAŞTAN "
                    "ANLATILMASI istendiğinde çağır — 'X konusunu anlatır "
                    "mısın', 'X konusunu işleyelim', 'şimdi X'i anlatalım' "
                    "gibi. Tek bir soruya cevap için DEĞİL (o kitap_sorusu'nun "
                    "işi) — bütün bir konunun anlatılması için."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "konu":        {"type": "string",  "description": "Öğretmenin verdiği konu."},
                        "ders":        {"type": "string",  "description": "Ders adı, örn. 'matematik'."},
                        "sinif":       {"type": "string",  "description": "Sınıf düzeyi, örn. '9'."},
                        "tema":        {"type": "string",  "description": "Bilinen ünite/tema adı."},
                        "sayfa_adedi": {"type": "integer", "description": "Kaç sayfa getirilecek (varsayılan 6, azami 12)."},
                    },
                    "required": [],
                },
            },
        },
    },
    "pdf_sayfa": {
        "kipler": ("ogretmenli", "ogretmensiz", "talimat"),
        "sema": {
            "type": "function",
            "function": {
                "name": "pdf_sayfa",
                "description": (
                    "Kitaptan belirli bir sayfa numarasını GÖRSEL olarak "
                    "ekranda gösterir — orijinal PDF düzeni korunur. 'şu "
                    "sayfayı göster/aç/yansıt' dendiğinde çağır."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sayfa": {"type": "integer", "description": "Gösterilecek sayfa numarası."},
                        "ders":  {"type": "string",  "description": "Ders adı, örn. 'biyoloji'."},
                        "sinif": {"type": "string",  "description": "Sınıf düzeyi, örn. '9'."},
                    },
                    "required": ["sayfa"],
                },
            },
        },
    },
    "yks_sorulari": {
        "kipler": ("ogretmenli", "ogretmensiz", "talimat"),
        "sema": {
            "type": "function",
            "function": {
                "name": "yks_sorulari",
                "description": (
                    "Belirtilen konuyla ilgili çıkmış YKS (TYT/AYT) sorusunu "
                    "sayfa görüntüsü olarak gösterir, soru metnini döner — "
                    "çözüm/cevap anahtarı İÇERMEZ. 'çıkmış soru', 'YKS/TYT/AYT "
                    "sorusu' istendiğinde çağır. Sıradaki soru için yalnızca "
                    "öğretmen açıkça isterse 'sonraki: true' ile (konu VERMEDEN) "
                    "yeniden çağır."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "konu":     {"type": "string",  "description": "Aranacak konu; yeni bir dizi başlatır."},
                        "ders":     {"type": "string",  "description": "Ders adı, eşleşmeyi iyileştirir."},
                        "adet":     {"type": "integer", "description": "Kaç soru eşleştirilecek (varsayılan 3, azami 6)."},
                        "sonraki":  {"type": "boolean", "description": "true = mevcut dizide bir sonraki soruya geç."},
                    },
                    "required": [],
                },
            },
        },
    },
    "pencere_kapat": {
        "kipler": ("talimat",),
        "sema": {
            "type": "function",
            "function": {
                "name": "pencere_kapat",
                "description": (
                    "ÖĞRETMEN TALİMAT MODU. Başlığı eşleşen açık bir pencereyi/"
                    "uygulamayı kapatır — 'youtube'u kapat', 'tarayıcıyı kapat'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hedef": {"type": "string", "description": "Pencere başlığında geçmesi beklenen kelimeler."},
                    },
                    "required": ["hedef"],
                },
            },
        },
    },
}

# Yalnızca sunucuda TAMAMEN çözülen araçlar — bunlar için client'a hiçbir
# tool_calls delta'sı GİTMEZ, sonuç doğrudan içerik olarak akıtılır. Geri
# kalan (pdf_sayfa, yks_sorulari, pencere_kapat) TAHTA araçları: OpenAI
# tool_calls biçiminde ses düğümüne iletilir (plan madde 4, alt madde
# "Tahta araçları").
_SUNUCU_ARACLARI = {"kitap_sorusu", "ders_icerigi"}


def _kip_icin_araclar(kip: str) -> list[dict]:
    return [t["sema"] for ad, t in ARAC_TANIMLARI.items() if kip in t["kipler"]]


# ── Erişim — üç katman (plan "Erişim" bölümü), TEK fonksiyonda ─────────────
# Ayrı ayrı Depends() olarak tanımlamak FastAPI'nin bağımlılık çözme sırasını
# (hangi 4xx/5xx önce fırlar) belirsizleştirirdi — burada sıra ADRES → BEARER
# TOKEN → TAHTA ANAHTARI elle, deterministik olarak garanti edilir. Tahta
# katmanı MEVCUT `auth.dogrula_tahta`yı DOĞRUDAN çağırır (yeniden yazılmaz).

def _izinli_adresler() -> set[str]:
    ham = os.environ.get("FARABI_SES_IZINLI", "127.0.0.1,::1")
    return {h.strip() for h in ham.split(",") if h.strip()}


def _erisim(
    request: Request,
    x_farabi_board_key: str | None = Header(default=None, alias=auth.HEADER_ADI),
    authorization: str | None = Header(default=None),
) -> auth.TahtaKimligi | None:
    """Üç katman: adres (403) → bearer token (503 tanımsızsa / 401 yanlışsa)
    → tahta anahtarı (`auth.dogrula_tahta`, 401 ya da rollback modunda None).
    Token DEĞERİ hiçbir log satırına yazılmaz."""
    host = request.client.host if request.client else None
    if host not in _izinli_adresler():
        log.warning("ses cephesi erişim reddi — adres izinli listede değil")
        raise HTTPException(status_code=403, detail="Bu adresten erişim izinli değil")

    beklenen = os.environ.get("FARABI_SES_TOKEN", "").strip()
    if not beklenen:
        raise HTTPException(status_code=503, detail="ses cephesi yapılandırılmamış")

    verilen = ""
    if authorization and authorization.startswith("Bearer "):
        verilen = authorization[len("Bearer "):]
    if not verilen or not hmac.compare_digest(
        verilen.encode("utf-8", "replace"), beklenen.encode("utf-8")
    ):
        log.warning("ses cephesi erişim reddi — geçersiz/eksik bearer token")
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik yetkilendirme")

    return auth.dogrula_tahta(x_farabi_board_key=x_farabi_board_key)


router = APIRouter()


# ── Persona + bağlam ────────────────────────────────────────────────────────

def _persona_metni() -> str:
    try:
        return PERSONA_PATH.read_text(encoding="utf-8")
    except Exception as e:
        log.error("ses_persona.txt okunamadı (%s: %s) — boş persona ile devam", type(e).__name__, e)
        return ""


def _sinif_duzeyi(derslik: str) -> str | None:
    if not derslik:
        return None
    m = _DERSLIK_DUZEY_RE.match(derslik.strip())
    return m.group(1) if m else None


def _baglam_satirlari(kip: str, derslik: str, sinif_duzeyi: str | None, ders: str | None) -> str:
    simdi = datetime.now(ISTANBUL_TZ).strftime("%d.%m.%Y %H:%M")
    satirlar = [f"\n\nŞu anki kip: {kip}.", f"Derslik: {derslik or 'bilinmiyor'}."]
    if sinif_duzeyi:
        satirlar.append(f"Sınıf düzeyi: {sinif_duzeyi}.")
    if ders:
        satirlar.append(f"Şu anki ders: {ders}.")
    satirlar.append(f"Tarih-saat: {simdi}.")
    return " ".join(satirlar)


def _sistem_mesaji(kip: str, derslik: str, sinif_duzeyi: str | None, ders: str | None) -> str:
    return _persona_metni() + _baglam_satirlari(kip, derslik, sinif_duzeyi, ders)


# ── OpenAI istek gövdesi ─────────────────────────────────────────────────────

class SohbetMesaji(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: Any = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class SohbetMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kip: str | None = None
    ders: str | None = None
    derslik: str | None = None


class SohbetIstek(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str | None = None
    messages: list[SohbetMesaji] = []
    stream: bool = False
    metadata: SohbetMetadata | None = None


def _icerik_metni(content: Any) -> str:
    """OpenAI `content` null, düz metin ya da parça listesi (Pipecat)
    olabilir — hepsini tek bir dizeye indirger."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parcalar = []
        for p in content:
            if isinstance(p, dict):
                parcalar.append(str(p.get("text", "")))
            elif isinstance(p, str):
                parcalar.append(p)
        return "".join(parcalar)
    return str(content)


# Pipecat'in OpenAILLMService'i (async function call akışında) bağlama bir
# "developer" rollü mesaj koyabiliyor (OpenAI'nin system'in yeni adı) — bu
# ve gelen `system` mesajları YOK SAYILIR (persona sistem mesajı ayrıca
# başa eklenir, API Prensibi: Brain karar verir). Tanınan yalnızca
# user/assistant/tool — başka HERHANGİ bir rol (bilinmeyen/gelecekteki bir
# SDK rolü) sessizce atlanır, asla çökme sebebi olmaz.
_BILINEN_ROLLER = {"user", "assistant", "tool"}


def _ollama_mesajlarina_cevir(mesajlar: list[SohbetMesaji]) -> list[dict]:
    """OpenAI mesaj listesini Ollama native `/api/chat` biçimine çevirir."""
    sonuc: list[dict] = []
    for m in mesajlar:
        if m.role not in _BILINEN_ROLLER:
            continue
        d: dict = {"role": m.role, "content": _icerik_metni(m.content)}
        if m.role == "assistant" and m.tool_calls:
            donusturulmus = []
            for tc in m.tool_calls:
                fn = tc.get("function") or {} if isinstance(tc, dict) else {}
                ham = fn.get("arguments")
                if isinstance(ham, str):
                    try:
                        args = json.loads(ham) if ham.strip() else {}
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                elif isinstance(ham, dict):
                    args = ham
                else:
                    args = {}
                donusturulmus.append({"function": {"name": fn.get("name", ""), "arguments": args}})
            d["tool_calls"] = donusturulmus
        sonuc.append(d)
    return sonuc


def _gecmis_kirp(mesajlar: list[dict]) -> list[dict]:
    """Geçmişi (system hariç) en yeniden geriye ≤ MAX_GECMIS_TOKEN olacak
    şekilde kırpar. Son kullanıcı mesajı ve ona bağlı (assistant/tool)
    mesajlar HER ZAMAN kalır; öncesi KULLANICI SINIRLARINDA ("tur") kesilir
    — kırpılmış geçmiş asla bir `tool` ya da yalın `assistant.tool_calls`
    mesajıyla başlamaz."""
    if not mesajlar:
        return mesajlar

    son_kullanici = None
    for i, m in enumerate(mesajlar):
        if m["role"] == "user":
            son_kullanici = i
    if son_kullanici is None:
        son_kullanici = len(mesajlar) - 1

    kalici = mesajlar[son_kullanici:]
    aday = mesajlar[:son_kullanici]

    turlar: list[list[dict]] = []
    for m in aday:
        if m["role"] == "user" or not turlar:
            turlar.append([m])
        else:
            turlar[-1].append(m)

    def _uzunluk(mesaj: dict) -> int:
        return len(str(mesaj.get("content") or ""))

    secilen: list[dict] = []
    toplam_karakter = sum(_uzunluk(m) for m in kalici)
    for tur in reversed(turlar):
        tur_karakter = sum(_uzunluk(m) for m in tur)
        if secilen and (toplam_karakter + tur_karakter) / KARAKTER_PER_TOKEN > MAX_GECMIS_TOKEN:
            break
        secilen = tur + secilen
        toplam_karakter += tur_karakter

    return secilen + kalici


def _son_kullanici_mesaji(mesajlar: list[dict]) -> str:
    for m in reversed(mesajlar):
        if m.get("role") == "user":
            return str(m.get("content") or "").strip()
    return ""


# ── Ollama ile tek tur ───────────────────────────────────────────────────────

def _yeni_istemci() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"http://{OLLAMA_HOST}",
        timeout=httpx.Timeout(GENEL_ZAMAN_ASIMI_SN, connect=5.0),
    )


# Testlerde enjekte edilebilir fabrika (plan: "enjekte edilebilir istemci").
_istemci_fabrikasi = _yeni_istemci


async def _ollama_akisi(client: httpx.AsyncClient, sistem: str, gecmis: list[dict], araclar: list[dict]):
    """Ollama'nın ham NDJSON stream'ini satır satır ayrıştırıp dict olarak
    yield eder. `options` YALNIZCA temperature — num_ctx ya da başka bir
    alan paylaşılan üretim modelini yeniden yükletir (CLAUDE.md)."""
    mesajlar = [{"role": "system", "content": sistem}] + gecmis
    govde: dict = {
        "model": OLLAMA_MODEL,
        "messages": mesajlar,
        "stream": True,
        "options": {"temperature": 0.2},
    }
    if araclar:
        govde["tools"] = araclar
    async with client.stream("POST", "/api/chat", json=govde) as yanit:
        if yanit.status_code != 200:
            govde_metni = await yanit.aread()
            raise RuntimeError(f"Ollama HTTP {yanit.status_code}: {govde_metni[:300]!r}")
        async for satir in yanit.aiter_lines():
            satir = satir.strip()
            if not satir:
                continue
            try:
                veri = json.loads(satir)
            except json.JSONDecodeError:
                continue
            if veri.get("error"):
                raise RuntimeError(f"Ollama hata bildirdi: {veri['error']}")
            yield veri


async def _ollama_turu(client: httpx.AsyncClient, sistem: str, gecmis: list[dict], araclar: list[dict]):
    """Bir Ollama turunu, karar (10 sn) + genel (30 sn) zaman aşımlarıyla
    sarar. Yield edilenler: ("icerik", metin) | ("arac", ad, args, id) |
    ("bitti", sebep) | ("hata", mesaj). `tool_calls` curl ile doğrulandığı
    üzere TEK chunk'ta bütün geliyor — ilk görülen anda karar verilmiş
    sayılır ve döngü biter."""
    kaynak = _ollama_akisi(client, sistem, gecmis, araclar)
    baslangic = time.monotonic()
    karar_verildi = False
    try:
        while True:
            simdi = time.monotonic()
            kalan_genel = GENEL_ZAMAN_ASIMI_SN - (simdi - baslangic)
            if kalan_genel <= 0:
                raise TimeoutError("genel zaman aşımı (30 sn) aşıldı")
            if karar_verildi:
                kalan = kalan_genel
            else:
                kalan_karar = KARAR_ZAMAN_ASIMI_SN - (simdi - baslangic)
                if kalan_karar <= 0:
                    raise TimeoutError("karar zaman aşımı (10 sn) aşıldı")
                kalan = min(kalan_genel, kalan_karar)
            try:
                veri = await asyncio.wait_for(kaynak.__anext__(), timeout=kalan)
            except StopAsyncIteration:
                return

            mesaj = veri.get("message") or {}
            arac_cagrilari = mesaj.get("tool_calls")
            parca = mesaj.get("content") or ""

            if arac_cagrilari:
                karar_verildi = True
                if len(arac_cagrilari) > 1:
                    log.warning("ses cephesi: Ollama birden fazla tool_call döndürdü, yalnızca ilki kullanılıyor")
                ilki = arac_cagrilari[0]
                fonksiyon = ilki.get("function") or {}
                yield ("arac", fonksiyon.get("name", ""), fonksiyon.get("arguments") or {},
                       ilki.get("id") or f"call_{uuid.uuid4().hex[:8]}")
                return

            if parca:
                karar_verildi = True
                yield ("icerik", parca)

            if veri.get("done"):
                yield ("bitti", veri.get("done_reason") or "stop")
                return
    except TimeoutError as e:
        # `asyncio.wait_for`'ın kendi TimeoutError'ı BOŞ mesajlıdır
        # (`str(asyncio.TimeoutError()) == ""`) — boş bir "hata" mesajı
        # `_ajan_calistir`'de yanlışlıkla "hata yok" ile karışmasın diye
        # burada asla boş bırakılmaz.
        yield ("hata", str(e) or "zaman aşımı")
    except Exception as e:
        yield ("hata", f"{type(e).__name__}: {e}")


# ── main.durum'a döngüsel importsuz erişim ──────────────────────────────────

def _durum() -> dict:
    import main  # gecikmeli import — main bu modülü import ettiği için döngü kırılır
    return main.durum


# ── kitap_sorusu — RAG'a doğrudan (LLM İKİNCİ turu YOK, cevap aynen aktarılır) ─

def _kitap_id_bul(ders: str, sinif: str | None) -> tuple[int, int, str] | None:
    """main.py::kitaplar_listesi ile AYNI sorgu + icerik._ders_eslesir ile
    eşleştirme (client kitap_sorusu._kitap_id_bul mantığıyla aynı ruhta).
    Dönüş (kitap_id, sinif, ders) — sınıf/ders DB'den; kaynak satırı ve
    loglama modelin argümanını değil kitabın kendi kaydını kullanır
    (main.py::soru_sor ile aynı: "9. Sınıf Biyoloji")."""
    with db.baglanti() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, sinif, ders FROM kitap ORDER BY id")
        satirlar = cur.fetchall()
    for kid, ksinif, kders in satirlar:
        if sinif and str(ksinif) != str(sinif).strip():
            continue
        if not icerik._ders_eslesir(ders, kders):
            continue
        return kid, ksinif, kders
    return None


def _rag_sorgula(kitap_id: int, soru: str, sinif: int | None, ders: str | None) -> dict:
    with db.baglanti() as conn:
        return _durum()["motor"].sorgula(conn, kitap_id, soru, sinif=sinif, ders=ders)


async def _kitap_sorusu_isle(args: dict, mesajlar: list[dict], derslik: str,
                              sinif_duzeyi: str | None, ders_baglam: str | None):
    yield ("icerik", "Kitaba bakıyorum. ")

    ders = (str(args.get("ders") or "").strip() or (ders_baglam or "")).strip() or None
    if not ders:
        yield ("icerik", "Hangi dersin kitabına bakayım?")
        yield ("bitti", "stop")
        return

    sinif = str(args.get("sinif") or "").strip() or sinif_duzeyi

    # Soru metni MODEL ARGÜMANINDAN değil kullanıcının SON mesajından alınır
    # (plan madde 4: "qwen 'ı'→'i' bozabiliyor").
    soru = _son_kullanici_mesaji(mesajlar)[:MAX_SORU_KARAKTER]
    if not soru:
        yield ("icerik", "Şu an kitaba ulaşamıyorum.")
        yield ("bitti", "stop")
        return

    if not _durum().get("hazir"):
        yield ("icerik", "Şu an kitaba ulaşamıyorum.")
        yield ("bitti", "stop")
        return

    try:
        kitap = await run_in_threadpool(_kitap_id_bul, ders, sinif)
    except Exception as e:
        log.warning("ses cephesi: kitap_id arama hatası: %s: %s", type(e).__name__, e)
        kitap = None
    if kitap is None:
        yield ("icerik", "Şu an kitaba ulaşamıyorum.")
        yield ("bitti", "stop")
        return

    try:
        kitap_id, kitap_sinif, kitap_ders = kitap
        sonuc = await run_in_threadpool(_rag_sorgula, kitap_id, soru, kitap_sinif, kitap_ders)
    except Exception as e:
        log.warning("ses cephesi: kitap_sorusu RAG hatası: %s: %s", type(e).__name__, e)
        yield ("icerik", "Şu an kitaba ulaşamıyorum.")
        yield ("bitti", "stop")
        return

    durum_kodu = sonuc.get("status")
    if durum_kodu == "ok":
        sayfalar = dict.fromkeys(str(k["sayfa"]) for k in (sonuc.get("sources") or []))
        kaynak = (f" Kaynak: {kitap_sinif}. Sınıf {kitap_ders}, sayfa {', '.join(sayfalar)}."
                  if sayfalar else "")
        yield ("icerik", (sonuc.get("answer") or "").strip() + kaynak)
    elif durum_kodu in ("yetersiz_kaynak", "sayi_kontrolu_reddi"):
        yield ("icerik", "Bu bilgi ders kitabında bu haliyle bulunmuyor.")
    else:
        yield ("icerik", "Şu an kitaba ulaşamıyorum.")
    yield ("bitti", "stop")


# ── ders_icerigi — sunucuda çalışır, kitap metnini bulup İKİNCİ (araçsız) tur ─

def _sayfa_adedi_sinirla(deger: Any) -> int:
    try:
        n = int(deger)
    except (TypeError, ValueError):
        return icerik.VARSAYILAN_SAYFA
    return max(1, min(n, 12))


async def _ders_icerigi_isle(client: httpx.AsyncClient, args: dict, sistem: str,
                              mesajlar: list[dict], derslik: str, sinif_duzeyi: str | None):
    yield ("icerik", "Konuyu açıyorum. ")

    istek = icerik.KonuIstek(
        ders=str(args.get("ders") or ""),
        sinif=(str(args.get("sinif") or sinif_duzeyi or "") or None),
        konu=str(args.get("konu") or ""),
        tema=str(args.get("tema") or ""),
        sayfa_adedi=_sayfa_adedi_sinirla(args.get("sayfa_adedi")),
        derslik=derslik,
    )
    try:
        yanit = await run_in_threadpool(icerik.ders_icerigi_endpoint, istek)
    except Exception as e:
        log.warning("ses cephesi: ders_icerigi hatası: %s: %s", type(e).__name__, e)
        yield ("icerik", "Bu konuyu kitapta bulamadım.")
        yield ("bitti", "stop")
        return

    if yanit.status != "ok" or not yanit.metin:
        yield ("icerik", "Bu konuyu kitapta bulamadım.")
        yield ("bitti", "stop")
        return

    # İKİNCİ LLM turu — ARAÇSIZ (tools boş) — kitap metnini `tool` mesajı
    # olarak ekleyip modelden anlatmasını istiyoruz.
    yeni_mesajlar = mesajlar + [
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "ders_icerigi", "arguments": dict(args)}}]},
        {"role": "tool", "content": yanit.metin[:icerik.MAX_KARAKTER]},
    ]
    icerik_akti = False
    async for olay in _ollama_turu(client, sistem, yeni_mesajlar, []):
        if olay[0] == "icerik":
            icerik_akti = True
            yield ("icerik", olay[1])
        elif olay[0] == "hata":
            log.warning("ses cephesi: ders_icerigi ikinci tur hatası: %s", olay[1])

    if not icerik_akti:
        yield ("icerik", "Bu konuyu kitapta bulamadım.")
    yield ("bitti", "stop")


# ── Ajan döngüsü — SSE ve JSON'un ORTAK çekirdeği ───────────────────────────

async def _ajan_calistir(sistem: str, mesajlar: list[dict], kip: str, derslik: str,
                          sinif_duzeyi: str | None, ders_baglam: str | None):
    """`("icerik", metin)` / `("arac_secildi", ad)` / `("arac_cagrisi", ad,
    args, id)` / `("bitti", sebep)` üretecir. Stream başladıktan sonra
    HİÇBİR istisna dışarı sızmaz (plan madde 6) — özür cümlesi + 'bitti' ile
    kapanır."""
    araclar = _kip_icin_araclar(kip)
    client = _istemci_fabrikasi()
    try:
        icerik_akti = False
        arac_olay: tuple | None = None
        bitis_nedeni = "stop"

        for deneme in range(2):  # ilk deneme + boş cevapta TEK yeniden deneme
            icerik_akti = False
            arac_olay = None
            bitis_nedeni = "stop"
            hata_mesaji: str | None = None
            async for olay in _ollama_turu(client, sistem, mesajlar, araclar):
                tur = olay[0]
                if tur == "icerik":
                    icerik_akti = True
                    yield ("icerik", olay[1])
                elif tur == "arac":
                    if not icerik_akti:
                        arac_olay = olay[1:]
                elif tur == "bitti":
                    bitis_nedeni = olay[1]
                elif tur == "hata":
                    hata_mesaji = olay[1]

            if hata_mesaji is not None and not icerik_akti and arac_olay is None:
                log.warning("ses cephesi: ollama hatası/zaman aşımı (deneme=%d): %s", deneme, hata_mesaji)
                yield ("icerik", "Şu an yanıt veremiyorum.")
                yield ("bitti", "stop")
                return

            if icerik_akti or arac_olay is not None:
                break  # içerik ya da araç geldi — yeniden denemeye gerek yok

        if not icerik_akti and arac_olay is None:
            yield ("icerik", "Anlayamadım, tekrar eder misiniz?")
            yield ("bitti", "stop")
            return

        if icerik_akti:
            yield ("bitti", bitis_nedeni)
            return

        ad, args, call_id = arac_olay
        yield ("arac_secildi", ad)

        if ad not in ARAC_TANIMLARI or kip not in ARAC_TANIMLARI[ad]["kipler"]:
            log.info("ses cephesi: bilinmeyen/kipte kapalı araç (%s, kip=%s)", ad, kip)
            yield ("icerik", "Bunu şu an yapamıyorum.")
            yield ("bitti", "stop")
            return

        if ad == "kitap_sorusu":
            async for parca in _kitap_sorusu_isle(args, mesajlar, derslik, sinif_duzeyi, ders_baglam):
                yield parca
            return

        if ad == "ders_icerigi":
            async for parca in _ders_icerigi_isle(client, args, sistem, mesajlar, derslik, sinif_duzeyi):
                yield parca
            return

        # Tahta araçları (pdf_sayfa, yks_sorulari, pencere_kapat) — OpenAI
        # tool_calls biçiminde OLDUĞU GİBİ ses düğümüne iletilir.
        yield ("arac_cagrisi", ad, args, call_id)
    except Exception as e:
        # Son çare — buraya kadar sızan hiçbir istisna 500'e dönmez.
        log.warning("ses cephesi: beklenmeyen hata: %s: %s", type(e).__name__, e)
        yield ("icerik", "Şu an yanıt veremiyorum.")
        yield ("bitti", "stop")
    finally:
        await client.aclose()


# ── Loglama — journal'a, İÇERİK YOK (plan "Kesin sınırlar") ─────────────────

def _ozet_logla(*, t0: float, t_karar: float | None, kip: str, derslik: str, arac: str | None) -> None:
    karar_ms = int((t_karar - t0) * 1000) if t_karar else None
    toplam_ms = int((time.monotonic() - t0) * 1000)
    log.info("ses cephesi turu — derslik=%s kip=%s arac=%s karar_ms=%s toplam_ms=%d",
              derslik or "?", kip, arac or "-", karar_ms, toplam_ms)


# ── SSE biçimi (OpenAI ile birebir) ──────────────────────────────────────────

def _sse_yaz(veri: dict) -> str:
    return f"data: {json.dumps(veri, ensure_ascii=False)}\n\n"


def _sse_taban(tamamlanma_id: str, olusturma: int) -> dict:
    return {"id": tamamlanma_id, "object": "chat.completion.chunk", "created": olusturma, "model": MODEL_ID}


# ── Uç noktalar ───────────────────────────────────────────────────────────

@router.get("/v1/models", dependencies=[Depends(_erisim)])
def modeller_listesi() -> dict:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "farabi"}]}


@router.post("/v1/chat/completions")
async def sohbet_tamamlama(istek: SohbetIstek, kimlik: auth.TahtaKimligi | None = Depends(_erisim)):
    t0 = time.monotonic()
    metadata = istek.metadata or SohbetMetadata()

    # Derslik SUNUCUDAN (tahta kimliği) gelir; metadata.derslik yalnızca
    # FARABI_AUTH_REQUIRED=0 acil rollback modunda (dogrula_tahta None
    # döndüğünde) kullanılır (plan "Erişim" madde 3).
    derslik = kimlik.derslik if kimlik is not None else (metadata.derslik or "").strip()
    sinif_duzeyi = _sinif_duzeyi(derslik)

    kip = (metadata.kip or "").strip() or VARSAYILAN_KIP
    if kip not in KIPLER:
        kip = VARSAYILAN_KIP
    ders_baglam = (metadata.ders or "").strip() or None

    sistem = _sistem_mesaji(kip, derslik, sinif_duzeyi, ders_baglam)
    mesajlar = _gecmis_kirp(_ollama_mesajlarina_cevir(istek.messages))

    tamamlanma_id = f"chatcmpl-{uuid.uuid4().hex}"
    olusturma = int(time.time())

    if istek.stream:
        async def govde():
            ilk_parca = True
            t_karar: float | None = None
            secilen_arac: str | None = None
            bitis_nedeni = "stop"
            async for olay in _ajan_calistir(sistem, mesajlar, kip, derslik, sinif_duzeyi, ders_baglam):
                tur = olay[0]
                if tur == "arac_secildi":
                    secilen_arac = olay[1]
                    continue
                if t_karar is None:
                    t_karar = time.monotonic()
                taban = _sse_taban(tamamlanma_id, olusturma)
                if tur == "icerik":
                    delta: dict = {"content": olay[1]}
                    if ilk_parca:
                        delta["role"] = "assistant"
                        ilk_parca = False
                    yield _sse_yaz({**taban, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
                elif tur == "arac_cagrisi":
                    _ad, args, call_id = olay[1], olay[2], olay[3]
                    delta = {"tool_calls": [{"index": 0, "id": call_id, "type": "function",
                                              "function": {"name": _ad,
                                                           "arguments": json.dumps(args, ensure_ascii=False)}}]}
                    if ilk_parca:
                        delta["role"] = "assistant"
                        ilk_parca = False
                    yield _sse_yaz({**taban, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
                    bitis_nedeni = "tool_calls"
                elif tur == "bitti":
                    bitis_nedeni = olay[1] or bitis_nedeni

            taban = _sse_taban(tamamlanma_id, olusturma)
            yield _sse_yaz({**taban, "choices": [{"index": 0, "delta": {}, "finish_reason": bitis_nedeni}]})
            yield "data: [DONE]\n\n"
            _ozet_logla(t0=t0, t_karar=t_karar, kip=kip, derslik=derslik, arac=secilen_arac)

        return StreamingResponse(govde(), media_type="text/event-stream")

    # stream: false — aynı mantık, tek chat.completion JSON.
    icerikler: list[str] = []
    arac_cagrisi: tuple | None = None
    secilen_arac: str | None = None
    bitis_nedeni = "stop"
    t_karar: float | None = None
    async for olay in _ajan_calistir(sistem, mesajlar, kip, derslik, sinif_duzeyi, ders_baglam):
        tur = olay[0]
        if tur == "arac_secildi":
            secilen_arac = olay[1]
            continue
        if t_karar is None:
            t_karar = time.monotonic()
        if tur == "icerik":
            icerikler.append(olay[1])
        elif tur == "arac_cagrisi":
            arac_cagrisi = olay[1:]
            bitis_nedeni = "tool_calls"
        elif tur == "bitti":
            bitis_nedeni = olay[1]

    _ozet_logla(t0=t0, t_karar=t_karar, kip=kip, derslik=derslik, arac=secilen_arac)

    mesaj: dict = {"role": "assistant"}
    if arac_cagrisi:
        _ad, args, call_id = arac_cagrisi
        mesaj["content"] = None
        mesaj["tool_calls"] = [{"id": call_id, "type": "function",
                                 "function": {"name": _ad, "arguments": json.dumps(args, ensure_ascii=False)}}]
    else:
        mesaj["content"] = "".join(icerikler)

    return JSONResponse({
        "id": tamamlanma_id, "object": "chat.completion", "created": olusturma, "model": MODEL_ID,
        "choices": [{"index": 0, "message": mesaj, "finish_reason": bitis_nedeni}],
    })
