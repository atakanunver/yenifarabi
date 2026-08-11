"""
core/saglayicilar.py — Gemini DIŞI metin/görsel sağlayıcı havuzu.

Neden var
---------
Gemini artık yalnızca CANLI SES için kullanılıyor: `main.py`'nin ana oturumu.
Gerçek zamanlı çift yönlü ses için başka seçenek yok (CLAUDE.md,
"Provider notes").

Geri kalan HER ŞEY — web arama sentezi, belge/video özeti, kitap özeti,
şüpheli sembol düzeltme, yüklenen resim dosyalarının görsel analizi — METİN
(ya da metne dönen görsel) görevleri. Bunlar artık TEK bir sağlayıcıya değil,
altı ayrı ücretsiz katmana dağıtılıyor: Groq, Mistral, DeepSeek, OpenRouter,
NVIDIA NIM (Hugging Face bilinçli olarak dışarıda bırakıldı — ücretsiz
kotası belgelenmemiş/öngörülemez, zamana duyarlı hiçbir göreve güvenle
bağlanamaz). Amaç: hiçbir tek sağlayıcının aylık kotasına/hız sınırına bağımlı
kalmamak.

Hepsi OpenAI-uyumlu `/chat/completions` uç noktası sunuyor — yalnızca
base_url + api_key + model değişiyor, tek istemci kütüphanesi (`openai`)
yetiyor.

GÖREV ZİNCİRLERİ: her görev sıralı bir (sağlayıcı, model) listesine sahip.
Zincirdeki biri hata verirse (kota, bağlantı, 5xx) SIRADAKİNE geçilir —
core/anahtar.py'nin Gemini anahtar havuzu rotasyonuyla aynı ruhta, ama
sağlayıcı bazında. core/anahtar.py'nin aksine hata türü ayrımı yapılmaz: o
modülde "kota dışı hata = tüm anahtarlar aynı hatayı verir, rotasyon yanlış
teşhis olur" ilkesi geçerliydi çünkü anahtarlar AYNI hesaba/servise
bağlanıyordu. Burada her sağlayıcı ayrı bir servis/SDK katmanı — birindeki
"model bulunamadı" ya da "geçersiz istek" hatası ötekini bağlamaz, bu yüzden
her hata türünde bir sonrakine geçmek güvenlidir.

Hiçbiri çalışmazsa hata YÜKSELİR; sessizce boş/uydurma yanıt DÖNMEZ —
CLAUDE.md'deki "failure text is binding" ilkesiyle aynı: bir görevin
başarısız olduğunu bilmek, yanlış/uydurma bir sonuçtan iyidir. Çağıran taraf
(actions/*.py, tools/*.py) kendi "sınırlı devam et" mesajını üretir.

SOĞUMA (4 saat): bir sağlayıcı kota/bakiye/kimlik doğrulama şeklinde bir hata
verirse (402, 401, 429, "insufficient balance/quota", "rate limit") o
sağlayıcı hafızada SOĞUMAYA alınır — süre dolana kadar zincirlerde hiç
denenmez, doğrudan atlanır. Ölçülen olay (02.08.2026): DeepSeek hesabının
bakiyesi sıfırdı (402, kalıcı — yeniden denemekle düzelmez), her sayfada
zincirin başında tekrar tekrar deneniyordu, her denemede gerçek bir istek
gidiyordu. Süre `core/anahtar.kota_hatasi_mi()` ile AYNI dar eşleşmeyi
kullanır — rastgele bir ağ hatasını/geçersiz isteği kalıcı sanıp sağlıklı
bir sağlayıcıyı saatlerce devre dışı bırakmak yanlış teşhis olurdu; bkz. o
fonksiyonun gerekçesi. Durum yalnızca BELLEKTE tutulur (süreç ömrü boyunca)
— `main.py`/`ui.py` gibi uzun süre çalışan bir süreç içinde tam 4 saat
etkilidir, ama `tools/kitap_ozet.py`/`tools/sembol_temizle.py` gibi her
çalıştırmada yeni bir süreç açan CLI betiklerinde yalnızca O ÇALIŞTIRMA
boyunca (art arda işlenen kitaplar arasında) etkilidir — betik yeniden
başlatılınca sıfırlanır. Diske yazılmıyor: ayrı süreçler arasında paylaşmak
(main.py çalışırken bir arka plan betiği de aynı anda kota tüketiyorsa)
kilit/senkronizasyon gerektirir ve şu an ölçülen sorunu çözmek için gerekli
değil.

Model adları burada TEK YERDE — sağlayıcılar sık model emekliye ayırıyor
(ör. Groq'un llama-3.3-70b-versatile'ı Haziran 2026'da emekliye ayırması).
Doğrulama: console.groq.com/docs/models, api-docs.deepseek.com,
docs.mistral.ai/getting-started/models, build.nvidia.com, openrouter.ai/models.
Bir model adı geçersiz kalırsa (404/410) o sağlayıcı hata verir ve zincirdeki
bir SONRAKİ SAĞLAYICIYA düşülür — core/modeller.py'deki Gemini'ye özel 404
yedeği (aynı sağlayıcıda ikinci bir model) farklı bir mekanizma, karıştırmayın.

Görsel görevler OpenAI'ın çok parçalı içerik biçimini kullanır:
[{"type":"text",...}, {"type":"image_url","image_url":{"url":"data:..."}}]
"""

import base64
import json
import time
from pathlib import Path

from core.logger import get_logger

log = get_logger("saglayicilar")

BASE_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# ── Soğuma: kota/bakiye/kimlik hatası veren sağlayıcı bir süre atlanır ─────
SOGUMA_SURESI_SN: float = 4 * 60 * 60   # 4 saat
_son_basarisizlik: dict[str, float] = {}   # sağlayıcı -> time.monotonic()


def _soguma_hakeder_mi(exc: Exception) -> bool:
    """
    core/anahtar.kota_hatasi_mi() ile AYNI dar eşleşme, aynı gerekçe: geniş
    tutulursa (her exception) bir kerelik ağ hatası bile sağlıklı bir
    sağlayıcıyı 4 saatliğine devre dışı bırakır.
    """
    m = f"{type(exc).__name__}: {exc}".lower()
    return any(k in m for k in (
        "402", "401", "429",
        "insufficient_quota", "insufficient balance",
        "rate limit", "rate_limited", "quota",
        "resource_exhausted", "unauthorized", "invalid_api_key", "invalid api key",
    ))


def _sogumada_mi(saglayici: str) -> bool:
    t = _son_basarisizlik.get(saglayici)
    return t is not None and (time.monotonic() - t) < SOGUMA_SURESI_SN

# ── Sağlayıcı tanımları: ad -> (base_url, config/api_keys.json'daki alan) ──
# "ollama" bilinçli olarak farklı: yerel, anahtar gerektirmez, `anahtar_alani`
# None. Bulut kotasından tamamen bağımsız olduğu için "soğuma" mantığı da
# anlamsız — _istemci() bunu ayrı ele alır. Yalnızca `soru_taslak` zincirinde
# (ve en sonda, son çare olarak) kullanılıyor — CLAUDE.md'nin "Bilinçli
# sapma" notu: Ollama Faz 1 Brain'i önceden kurmak için değil, bu tür
# çevrimdışı içerik araçlarının bulut kotasına bağımlılığını azaltmak için
# kuruldu. Diğer görev zincirlerine eklenmedi — kapsam genişletmek ayrı bir
# karar.
SAGLAYICI_TANIMLARI = {
    "groq":       {"base_url": "https://api.groq.com/openai/v1",      "anahtar_alani": "groq_api_key"},
    "mistral":    {"base_url": "https://api.mistral.ai/v1",           "anahtar_alani": "mistral_api_key"},
    "deepseek":   {"base_url": "https://api.deepseek.com/v1",         "anahtar_alani": "deepseek_api_key"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",        "anahtar_alani": "openrouter_api_key"},
    "nvidia":     {"base_url": "https://integrate.api.nvidia.com/v1", "anahtar_alani": "nvidia_api_key"},
    "ollama":     {"base_url": "http://127.0.0.1:11434/v1",           "anahtar_alani": None},
}

# ── Görev zincirleri: (sağlayıcı_adı, model) sıralı listesi ────────────────
GOREV_ZINCIRLERI: dict[str, list[tuple[str, str]]] = {
    # actions/file_processor.py — yüklenen resim dosyalarının görsel analizi
    # (describe/ocr/analyze). Metin döner, konuşma yok — bu yüzden buraya
    # taşınabiliyor.
    "gorsel": [
        ("groq",   "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("nvidia", "meta/llama-3.2-90b-vision-instruct"),
    ],
    # actions/web_search.py + tools/kitap_ozet.py zenginleştirme — kaynak
    # DDG'den gelir, bu yalnızca ham sonuçları Türkçe bir cevaba derliyor.
    "arama_sentez": [
        ("deepseek", "deepseek-v4-flash"),
    ],
    # actions/file_processor.py metin görevleri (PDF/docx/txt/csv/json/pptx)
    "belge_ozet": [
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
    ],
    # actions/youtube_video.py transkript özeti — kısa, hız öncelikli
    "video_ozet": [
        ("deepseek", "deepseek-v4-flash"),
        ("groq",     "openai/gpt-oss-120b"),
    ],
    # tools/kitap_ozet.py — ders anında değil, kalite hızdan önemli.
    # "ollama" burada da yalnızca SON çare (bkz. "soru_taslak" üstteki not) —
    # bu, _metinden_ozet_uret'in düz metin özetleme görevi; kitap_ozet.py'nin
    # grounded web-arama zenginleştirmesi ayrı bir zincir (arama_sentez),
    # buraya eklenmedi.
    "kitap_ozet": [
        ("nvidia",   "meta/llama-3.3-70b-instruct"),
        ("deepseek", "deepseek-v4-flash"),
        ("ollama",   "qwen2.5:14b"),
    ],
    # tools/sembol_temizle.py — matematiksel belirsizlik çözümü, akıl
    # yürütmesi güçlü modeller tercih edilir
    "sembol_duzelt": [
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
    ],
    # benchmark/soru_taslak.py — Faz 0a soru seti TASLAĞI (insan onayı
    # gerektirir, bkz. o dosyanın modül dokümanı). Ders anında değil.
    # "ollama" zincirin SONUNDA — üç bulut sağlayıcı da başarısız olursa son
    # çare; normal çalışmada hiç devreye girmez. Çıktısı, diğer
    # sağlayıcılarınki gibi "onaylandi": False ile işaretlenir, otomatik
    # onaylanmaz.
    "soru_taslak": [
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
        ("nvidia",   "meta/llama-3.3-70b-instruct"),
        ("ollama",   "qwen2.5:14b"),
    ],
}

# Metin görevlerinin tükenmesi durumunda son çare. OpenRouter'ın kendi
# otomatik yönlendiricisi (openrouter/free) sabit bir model adı yerine
# kullanılabilir bir ücretsiz modeli KENDİSİ seçiyor — bu yüzden
# OpenRouter'ın sık değişen ücretsiz model listesine tek tek bağımlı değil.
# Görsel görevlere eklenmez: ücretsiz görsel modelleri güvenilir değil,
# sessizce düşük kaliteli bir sonuç üretmektense görevin başarısız olduğu
# bilinsin.
_EVRENSEL_METIN_YEDEK = ("openrouter", "openrouter/free")


def _config_oku() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _anahtar(saglayici: str) -> str | None:
    alan = SAGLAYICI_TANIMLARI[saglayici]["anahtar_alani"]
    return (_config_oku().get(alan) or "").strip() or None


def _istemci(saglayici: str):
    from openai import OpenAI
    if saglayici == "ollama":
        anahtar = "ollama"  # yerel sunucu anahtarı kontrol etmiyor, sabit değer yeterli
    else:
        anahtar = _anahtar(saglayici)
        if not anahtar:
            return None
    # max_retries=0: `openai` kütüphanesi varsayılan olarak 429/5xx'te KENDİ
    # İÇİNDE üstel beklemeyle 2 kez daha deniyor — bizim _zinciri_dene'nin
    # sıradaki sağlayıcıya SESSİZCE geçmesinden ÖNCE, tek bir başarısız
    # çağrıyı dakikalarca uzatabiliyor (ölçüldü: DeepSeek 402 + Mistral 429
    # art arda geldiğinde tek bir sayfa 464 sn sürdü, hiçbir çıktı olmadan —
    # "sistem tıkandı" izlenimi buradan geliyordu). Sıradaki sağlayıcıya
    # geçme kararı zaten burada veriliyor, SDK'nın kendi retry'ı gereksiz.
    # timeout: tek bir isteğin süresiz asılı kalmasını da engeller.
    return OpenAI(base_url=SAGLAYICI_TANIMLARI[saglayici]["base_url"],
                 api_key=anahtar, max_retries=0, timeout=30.0)


def _zinciri_dene(gorev: str, mesajlar: list[dict], evrensel_yedek: bool = True) -> str:
    # NOT: tanımsızlık kontrolü evrensel yedek eklenmeden ÖNCE yapılır — aksi
    # halde yazım hatası olan bir görev adı (ör. "beige_ozet") sessizce
    # openrouter/free'ye düşer, hatanın kendisi hiç görünmez.
    if gorev not in GOREV_ZINCIRLERI:
        raise RuntimeError(f"Tanımsız görev: '{gorev}'")
    zincir = list(GOREV_ZINCIRLERI[gorev])
    if evrensel_yedek:
        zincir = zincir + [_EVRENSEL_METIN_YEDEK]

    son_hata: Exception | None = None
    for saglayici, model in zincir:
        if _sogumada_mi(saglayici):
            kalan_dk = (SOGUMA_SURESI_SN - (time.monotonic() - _son_basarisizlik[saglayici])) / 60
            log.info("%s: soğumada (~%.0f dk kaldı), atlanıyor", saglayici, kalan_dk)
            continue

        istemci = _istemci(saglayici)
        if istemci is None:
            log.info("%s: config/api_keys.json içinde anahtar yok, atlanıyor", saglayici)
            continue
        try:
            # ollama'nın varsayılan sıcaklığı bu görevler için çok yüksek —
            # ölçüldü: sıcaklık verilmeden qwen2.5:14b bozuk/anlamsız metin
            # üretti ("Lipitler nedendiragramış?"), temperature=0.2 ile aynı
            # istem tutarlı ve doğru sonuç verdi. Diğer beş sağlayıcı kendi
            # varsayılanıyla test edilip onaylanmıştı, onlara dokunulmadı.
            ekstra = {"temperature": 0.2} if saglayici == "ollama" else {}
            yanit = istemci.chat.completions.create(model=model, messages=mesajlar, **ekstra)
            metin = (yanit.choices[0].message.content or "").strip()
            if metin:
                _son_basarisizlik.pop(saglayici, None)
                return metin
            son_hata = RuntimeError(f"{saglayici}/{model}: boş yanıt")
            log.warning("%s/%s boş yanıt döndü, sıradaki sağlayıcıya geçiliyor", saglayici, model)
        except Exception as e:
            son_hata = e
            if _soguma_hakeder_mi(e):
                _son_basarisizlik[saglayici] = time.monotonic()
                log.warning("%s/%s başarısız (%s): %s — %d saat soğumaya alındı, sıradaki sağlayıcıya geçiliyor",
                           saglayici, model, type(e).__name__, str(e)[:160], SOGUMA_SURESI_SN // 3600)
            else:
                log.warning("%s/%s başarısız (%s): %s — sıradaki sağlayıcıya geçiliyor",
                           saglayici, model, type(e).__name__, str(e)[:160])
            continue

    raise RuntimeError(f"'{gorev}' görevi için hiçbir sağlayıcı yanıt vermedi. Son hata: {son_hata}")


def metin_uret(gorev: str, istem: str, sistem: str | None = None) -> str:
    """Salt metin görevler (özet, sentez, analiz, düzeltme)."""
    mesajlar = []
    if sistem:
        mesajlar.append({"role": "system", "content": sistem})
    mesajlar.append({"role": "user", "content": istem})
    return _zinciri_dene(gorev, mesajlar)


def gorsel_uret(gorev: str, istem: str, resim_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Görsel + metin isteyen görevler ('gorsel' zinciri). Konuşma DÖNMEZ,
    yalnızca metin döner."""
    b64 = base64.b64encode(resim_bytes).decode("ascii")
    icerik = [
        {"type": "text", "text": istem},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]
    return _zinciri_dene(gorev, [{"role": "user", "content": icerik}], evrensel_yedek=False)
