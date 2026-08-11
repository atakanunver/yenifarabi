#web_search.py
"""
Web arama; ham sonuçlar için DDG (API'siz), sentez için core/saglayicilar.py.

Neden Gemini yok: Gemini artık yalnızca canlı ses oturumunda kullanılıyor
(main.py). Gemini'nin gerçek web-grounding aracının
tam eşdeğeri yok, ama buradaki iş zaten iki adıma ayrılabiliyor: ARAMA (DDG,
ücretsiz, yerel) + SENTEZ (ham snippet'leri okunur bir cevaba derlemek —
salt metin görevi, saglayicilar.py'nin 'arama_sentez' zincirine gidiyor).
Eskiden DDG yalnızca Gemini başarısız olunca ham snippet listesi olarak
dönüyordu; şimdi DDG HER ZAMAN birincil kaynak ve sentez de her zaman
uygulanıyor — sentez başarısız olursa ham DDG formatına düşülüyor.
"""
import sys
from pathlib import Path

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()


def _ddg_search(query: str, max_results: int = 6, region: str = "tr-tr") -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results, region=region):
            results.append({
                "title":   r.get("title",  ""),
                "snippet": r.get("body",   ""),
                "url":     r.get("href",   ""),
            })
    return results


def _format_ddg(query: str, results: list[dict]) -> str:
    if not results:
        return f"Sonuç bulunamadı: {query}"

    lines = [f"Arama sonuçları: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):   lines.append(f"{i}. {r['title']}")
        if r.get("snippet"): lines.append(f"   {r['snippet']}")
        if r.get("url"):     lines.append(f"   Kaynak: {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


# ── Briefing helper ────────────────────────────────────────────────────────────

def _google_news_headlines(n: int = 8) -> tuple[list[str], str]:
    """
    Fetches https://news.google.com/ directly and parses the rendered HTML
    for top headlines. Plain HTTP GET + BeautifulSoup — no Gemini call, no
    billed google_search grounding tool, so it costs zero LLM tokens.
    Returns (headline_list, raw_text_for_display).
    """
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }
    news_url = "https://news.google.com/?hl=tr&gl=TR&ceid=TR:tr"
    resp = requests.get(news_url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    headlines: list[str] = []
    links:     list[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        if not a["href"].startswith("./read/"):
            continue
        text = a.get_text(strip=True)
        if len(text) < 20 or text in seen:
            continue
        seen.add(text)
        headlines.append(text)
        links.append(urljoin(news_url, a["href"]))
        if len(headlines) >= n:
            break

    full_news = "\n\n".join(
        f"• {h}\n  {u}" for h, u in zip(headlines, links)
    )
    return headlines, full_news


# ── Modes ──────────────────────────────────────────────────────────────────────

def _sentezli_arama(sorgu: str, max_sonuc: int = 6, talimat: str = "") -> str:
    """
    DDG'den ham sonuç çek, core/saglayicilar.py'nin 'arama_sentez' zinciriyle
    Türkçe bir cevaba derle. DDG boş dönerse ya da sentez başarısız olursa
    ham DDG formatına düşülür — sessizce uydurma yanıt üretilmez.
    """
    sonuclar = _ddg_search(sorgu, max_results=max_sonuc)
    ham = _format_ddg(sorgu, sonuclar)
    if not sonuclar:
        return ham
    try:
        from core import saglayicilar
        onek = f"{talimat}\n\n" if talimat else ""
        istem = (f"{onek}Aşağıdaki arama sonuçlarından '{sorgu}' hakkında "
                 f"Türkçe, öz ve doğru bir cevap derle:\n\n{ham}")
        return saglayicilar.metin_uret("arama_sentez", istem)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Sentez başarısız ({e}) — ham DDG sonuçları kullanılıyor")
        return ham


def _search(query: str) -> str:
    """Varsayılan arama."""
    return _sentezli_arama(query)


def _news(query: str) -> str:
    """Güncel haberler — sorguya güncellik vurgusu ekler."""
    news_query = f"latest news today: {query}" if query else "top world news today"
    return _sentezli_arama(news_query, max_sonuc=8,
                           talimat="Bu güncel bir haber sorgusu; en yeni bilgiyi öne çıkar.")


def _research(query: str) -> str:
    """Deep dive — arka plan, temel gerçekler, güncel durum, nüanslar dahil."""
    return _sentezli_arama(
        query, max_sonuc=10,
        talimat=("Kapsamlı, ayrıntılı bir açıklama derle: arka plan bağlamı, "
                 "temel gerçekler, güncel durum ve önemli nüanslar dahil."))


def _price(query: str) -> str:
    """Ürün fiyat sorgusu — güncel piyasa fiyatlarını arar."""
    return _sentezli_arama(
        f"{query} price buy", max_sonuc=6,
        talimat="Güncel piyasa fiyatı sorgusu; bulduğun rakamları ve kaynağını belirt.")


def _compare(items: list[str], aspect: str) -> str:
    all_results: dict[str, list] = {}
    for item in items:
        try:
            all_results[item] = _ddg_search(f"{item} {aspect}", max_results=4)
        except Exception:
            all_results[item] = []

    if not any(all_results.values()):
        return f"'{', '.join(items)}' için arama sonucu bulunamadı."

    ham = "\n\n".join(
        _format_ddg(f"{item} — {aspect}", all_results.get(item, [])) for item in items
    )
    try:
        from core import saglayicilar
        istem = (f"Aşağıdaki arama sonuçlarını kullanarak {', '.join(items)} arasında "
                 f"'{aspect}' açısından somut, verilere dayalı bir karşılaştırma yap "
                 f"(Türkçe):\n\n{ham}")
        return saglayicilar.metin_uret("arama_sentez", istem)
    except Exception as e:
        print(f"[WebSearch] ⚠️ Karşılaştırma sentezi başarısız ({e}) — ham sonuçlar kullanılıyor")
        lines = [f"Karşılaştırma — {aspect.upper()}", "─" * 40]
        for item in items:
            lines.append(f"\n▸ {item}")
            for r in all_results.get(item, [])[:2]:
                if r.get("snippet"):
                    lines.append(f"  • {r['snippet']}")
                if r.get("url"):
                    lines.append(f"    {r['url']}")
        return "\n".join(lines)


# ── Public entry point ─────────────────────────────────────────────────────────

def web_search(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    query  = params.get("query", "").strip()
    mode   = params.get("mode",  "search").lower().strip()
    items  = params.get("items", [])
    aspect = params.get("aspect", "general").strip() or "general"

    if not query and not items:
        return "Lütfen bir arama sorgusu belirtin."

    if items and mode not in ("compare",):
        mode = "compare"

    if player:
        player.write_log(f"[Search:{mode}] {query or ', '.join(items)}")

    print(f"[WebSearch] 🔍 mode={mode!r}  query={query!r}")

    try:
        if mode == "compare" and items:
            return _compare(items, aspect)
        if mode == "news":
            return _news(query)
        if mode == "research":
            return _research(query)
        if mode == "price":
            return _price(query)
        return _search(query)

    except Exception as e:
        print(f"[WebSearch] ❌ Tüm kaynaklar başarısız oldu: {e}")
        return f"Arama başarısız oldu: {e}"
