"""
actions/eba.py — EBA (Eğitim Bilişim Ağı) video ve soru PDF erişimi.

EBA (eba.gov.tr) ağır JS/SPA tabanlı — YouTube'un aksine arama sonucu HTML'i
sunucu tarafında oluşmuyor (ölçüldü: 2026-08-09, ham `curl` çıktısı yalnızca
uygulama kabuğu, içerik yok), bu yüzden `youtube_video.py`'deki gibi güvenilir
bir "ilk sonucu bul" scrape'i mümkün değil. Buna göre iki işlem ayrı tasarlandı:

- video: doğrudan bir eba.gov.tr URL'si verilirse xdg-open ile açılır; yalnızca
  konu adı (query) verilirse EBA'nın arama sayfası açılır — kesin video değil,
  sayfadan seçim öğretmene/öğrenciye kalır. Bu, `youtube_video.py`'nin zaten
  taşıdığı ve CLAUDE.md'nin "düzeltilmedi, açık delik" diye işaretlediği aynı
  tarayıcı-açma sınır ihlalidir — EBA'ya bilerek aynı şekilde genişletildi.
- pdf: bir eba.gov.tr PDF URL'si verilirse sunucu tarafında indirilip metni
  çıkarılır, içerik paneline basılır. Tarayıcı AÇILMAZ, dosya diske
  kaydedilmez — `actions/file_processor.py::_process_pdf`'in metin çıkarma
  deseniyle aynı (pdfplumber, yoksa PyPDF2).

İkisi de yalnızca eba.gov.tr (ve alt alan adları) ile sınırlı — `site_goster.py`
ile aynı beyaz liste ilkesi, ama bu modül ayrı bir amaç için var (video/PDF),
site_goster'ın kapsamı metin/tablo ile sınırlı kalıyor.
"""

import subprocess
import tempfile
from urllib.parse import quote_plus, urlparse

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

from config import is_mac, is_linux

_IZINLI_ALAN_SONEKI = "eba.gov.tr"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _izinli(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == _IZINLI_ALAN_SONEKI or host.endswith("." + _IZINLI_ALAN_SONEKI)


def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[EBA] ⚠️ open_url başarısız: {e}")


def _handle_video(parameters: dict, player) -> str:
    url   = (parameters.get("url") or "").strip()
    query = (parameters.get("query") or "").strip()

    if url:
        if not _izinli(url):
            return "Bu bir EBA adresi değil, efendim — yalnızca eba.gov.tr açabilirim."
        if player:
            player.write_log(f"[EBA] Video açılıyor: {url}")
        _open_url(url)
        return "EBA videosu açıldı."

    if not query:
        return "Hangi konunun videosunu açacağımı söyler misiniz, efendim."

    search_url = f"https://www.eba.gov.tr/ara?icerikTuru=video&sorgu={quote_plus(query)}"
    if player:
        player.write_log(f"[EBA] Video araması açılıyor: {query}")
    _open_url(search_url)
    return f"EBA'da '{query}' araması açıldı, efendim — videoyu sayfadan seçmeniz gerekiyor."


def _extract_pdf_text(pdf_path: str, max_chars: int = 6000) -> str:
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except ImportError:
        try:
            import PyPDF2
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
        except ImportError:
            return ""
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...devamı kesildi...]"
    return text


def _handle_pdf(parameters: dict, player, speak) -> str:
    if not _REQUESTS_OK:
        return "requests kütüphanesi kurulu değil, PDF indirilemiyor."

    url = (parameters.get("url") or "").strip()
    if not url:
        return "Açacağım PDF'in EBA bağlantısını söyler misiniz, efendim."
    if not _izinli(url):
        return "Bu bir EBA adresi değil, efendim — yalnızca eba.gov.tr açabilirim."

    if player:
        player.write_log(f"[EBA] PDF indiriliyor: {url}")
    if speak:
        speak("PDF indiriliyor efendim, bir saniye.")

    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "").lower()
        if "pdf" not in ct and not url.lower().endswith(".pdf"):
            return "Bu bağlantı bir PDF gibi görünmüyor, efendim."
    except Exception as e:
        return f"PDF indirilemedi, efendim: {e}"

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(r.content)
        tmp.flush()
        try:
            text = _extract_pdf_text(tmp.name)
        except Exception as e:
            return f"PDF okunamadı, efendim: {e}"

    if not text:
        return "PDF'den metin çıkarılamadı, efendim (taranmış/görsel tabanlı olabilir)."

    if player is not None and hasattr(player, "show_content"):
        player.show_content("EBA — PDF", text)

    return text


_ACTION_MAP = {
    "video": _handle_video,
    "pdf":   _handle_pdf,
}


def eba(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "video").lower().strip()

    if player:
        player.write_log(f"[EBA] İşlem: {action}")
    print(f"[EBA] ▶️ İşlem: {action}  Parametreler: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        return f"Bilinmeyen EBA işlemi: '{action}'. Kullanılabilir: video, pdf."

    try:
        if action == "video":
            return handler(params, player) or "Tamamlandı."
        return handler(params, player, speak) or "Tamamlandı."
    except Exception as e:
        print(f"[EBA] ❌ {action} işleminde hata: {e}")
        return f"EBA {action} işlemi başarısız oldu, efendim: {e}"
