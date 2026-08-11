#youtube_video.py
import json
import re
import sys
import time
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

from config import get_os, is_windows, is_mac, is_linux


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"


def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] ⚠️ open_url başarısız: {e}")

def _scrape_first_video_url(query: str) -> str | None:

    if not _REQUESTS_OK:
        return None

    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )

    try:
        r    = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text

        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)

        seen = set()
        for vid in video_ids:
            if vid in seen:
                continue
            seen.add(vid)

            if f'/shorts/{vid}' in html:
                continue
            return f"https://www.youtube.com/watch?v={vid}"

    except Exception as e:
        print(f"[YouTube] ⚠️ scrape_first_video_url başarısız: {e}")

    return None

def _extract_video_id(url: str) -> str | None:
    match = re.search(
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url
    )
    return match.group(1) if match else None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _ask_for_url(prompt_text: str = "YouTube video URL'si:") -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring("Farabi", prompt_text, parent=root)
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL diyaloğu başarısız: {e}")
        return None


def _get_transcript(video_id: str) -> str | None:
    """
    youtube-transcript-api 1.x API'si — 02.08.2026'da "tüm özellikleri test
    et" isteği sırasında ölçülen gerçek bir kırılma burada düzeltildi:
    `requirements.txt` bu paketin sürümünü sabitlemiyor, `pip install` 1.2.4
    getirdi ve o sürümde eski `YouTubeTranscriptApi.list_transcripts(id)`
    (classmethod) kaldırılmış — yerine `YouTubeTranscriptApi().list(id)`
    (ÖRNEK metodu) geldi. `TranscriptList`'in kendisi
    (find_manually_created_transcript / find_generated_transcript) aynı
    kaldı. Ayrıca `transcript.fetch()`'in döndürdüğü öğeler artık dict değil
    — `FetchedTranscriptSnippet` dataclass'ı, `entry["text"]` değil
    `entry.text` gerekiyor.
    """
    if not _TRANSCRIPT_OK:
        return None
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript      = None

        lang_priority = ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]

        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return None

        fetched = transcript.fetch()
        return " ".join(entry.text for entry in fetched)

    except Exception as e:
        print(f"[YouTube] ⚠️ Transkript alınamadı: {e}")
        return None


def _ozet_uret(transcript: str, video_url: str) -> str:
    """
    İsim tarihseldir (Gemini artık yalnızca canlı ses oturumlarında
    kullanılıyor) — core/saglayicilar.py'nin 'video_ozet' zinciri özetliyor.
    """
    from core import saglayicilar
    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    return saglayicilar.metin_uret(
        "video_ozet",
        f"Please summarize this YouTube video transcript:\n\n{truncated}",
        sistem=(
            "Sen Farabi'sin, sınıftaki yapay zekâ öğretmen. "
            "Ders videosu metinlerini öğrencilere sade biçimde özetle. "
            "Yapı: tek cümlelik genel bakış, ardından 3-5 ana madde. "
            "Lise seviyesinde, TÜRKÇE ve kısa yaz."
        ),
    )


def _save_summary(content: str, video_url: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    header = (
        f"FARABİ — YouTube Özeti\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Tarih  : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] ⚠️ Metin düzenleyici açılamadı: {e}")

    return str(filepath)


def _scrape_video_info(video_id: str) -> dict:
    if not _REQUESTS_OK:
        return {}
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        info = {}

        for key, pattern in [
            ("title",    r'"title":\{"runs":\[\{"text":"([^"]+)"'),
            ("channel",  r'"ownerChannelName":"([^"]+)"'),
            ("views",    r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes",    r'"label":"([0-9,]+ likes)"'),
        ]:
            match = re.search(pattern, html)
            if match:
                raw = match.group(1)
                if key == "views":
                    info[key] = f"{int(raw):,}"
                elif key == "duration":
                    secs = int(raw)
                    info[key] = f"{secs // 60}:{secs % 60:02d}"
                else:
                    info[key] = raw

        return info
    except Exception as e:
        print(f"[YouTube] ⚠️ Bilgi çekme başarısız: {e}")
        return {}


def _scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict]:
    if not _REQUESTS_OK:
        return []
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        titles   = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            results.append({"rank": len(results) + 1, "title": title, "channel": channel})
            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"[YouTube] ⚠️ Trend videolar çekilemedi: {e}")
        return []

def _handle_play(parameters: dict, player) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Ne izlemek istediğinizi söyler misiniz, efendim."

    if player:
        player.write_log(f"[YouTube] Aranıyor: {query}")

    print(f"[YouTube] 🔍 Shorts olmayan ilk video aranıyor: {query}")

    video_url = _scrape_first_video_url(query)

    if video_url:
        print(f"[YouTube] ▶️ Açılıyor: {video_url}")
        _open_url(video_url)
        return f"Oynatılıyor: {query}"

    print(f"[YouTube] ⚠️ Video bulunamadı, filtrelenmiş arama sayfası açılıyor")
    fallback_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    _open_url(fallback_url)
    return f"YouTube araması açıldı: {query} (manuel seçim gerekli)"


def _handle_summarize(parameters: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api kurulu değil. Kurmak için: pip install youtube-transcript-api"

    url = _ask_for_url("Lütfen YouTube video URL'sini yapıştırın:")
    if not url:
        return "URL verilmedi efendim. Özet iptal edildi."
    if not _is_valid_youtube_url(url):
        return "Bu geçerli bir YouTube URL'si gibi görünmüyor, efendim."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Bu URL'den video ID'si çıkarılamadı, efendim."

    if player:
        player.write_log(f"[YouTube] Özetleniyor: {url}")
    if speak:
        speak("Transkript alınıyor efendim. Bir saniye.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return "Bu video için transkript alamadım, efendim."

    if speak:
        speak("Transkript alındı. Özet oluşturuluyor.")

    try:
        summary = _ozet_uret(transcript, url)
    except Exception as e:
        return f"Özet oluşturma başarısız oldu, efendim: {e}"

    if speak:
        speak(summary)

    if parameters.get("save", False):
        saved_path = _save_summary(summary, url)
        return f"Özet tamamlandı ve Masaüstü'ne kaydedildi: {saved_path}"

    return summary


def _handle_get_info(parameters: dict, player, speak) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Lütfen YouTube video URL'sini yapıştırın:")
    if not url or not _is_valid_youtube_url(url):
        return "Lütfen geçerli bir YouTube URL'si belirtin, efendim."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Video ID'si çıkarılamadı, efendim."

    if player:
        player.write_log(f"[YouTube] Bilgi alınıyor: {url}")

    info = _scrape_video_info(video_id)
    if not info:
        return "Video bilgileri alınamadı, efendim."

    lines = [
        f"{key.capitalize()}: {info[key]}"
        for key in ("title", "channel", "views", "duration", "likes")
        if key in info
    ]
    result = "\n".join(lines)

    if speak:
        speak(f"Video bilgileri şöyle efendim. {result.replace(chr(10), '. ')}")

    return result


def _handle_trending(parameters: dict, player, speak) -> str:
    region = parameters.get("region", "TR").upper()

    if player:
        player.write_log(f"[YouTube] Trend: {region}")

    trending = _scrape_trending(region=region, max_results=8)
    if not trending:
        return f"{region} bölgesi için trend videolar alınamadı, efendim."

    lines  = [f"{region} bölgesinde trend videolar:"]
    lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
    result = "\n".join(lines)

    if speak:
        top3   = trending[:3]
        spoken = "İşte en çok trend olan videolar efendim. " + ". ".join(
            f"{v['rank']} numara: {v['channel']} kanalından {v['title']}" for v in top3
        )
        speak(spoken)

    return result

_ACTION_MAP = {
    "play":      _handle_play,
    "summarize": _handle_summarize,
    "get_info":  _handle_get_info,
    "trending":  _handle_trending,
}


def youtube_video(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[YouTube] İşlem: {action}")
    print(f"[YouTube] ▶️  İşlem: {action}  Parametreler: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        return (
            f"Bilinmeyen YouTube işlemi: '{action}'. "
            "Kullanılabilir: play, summarize, get_info, trending."
        )

    try:
        if action == "play":
            return handler(params, player) or "Tamamlandı."
        return handler(params, player, speak) or "Tamamlandı."
    except Exception as e:
        print(f"[YouTube] ❌ {action} işleminde hata: {e}")
        return f"YouTube {action} işlemi başarısız oldu, efendim: {e}"