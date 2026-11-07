"""ISBN ile internetten eser bilgisi (Kitap Ekle formunu doldurmak için): önce Open Library, bulamazsa Google Books.

Open Library önce: Google Books'un anahtarsız ortak kotası sık doluyor (429). Dışarı yalnızca ISBN gider. Ulaşılamazsa/bulunamazsa None — form elle doldurulur.
"""

import httpx


def _get(url: str) -> dict:
    try:
        r = httpx.get(url, timeout=6, follow_redirects=True)
        return r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


def _open_library(isbn: str) -> dict | None:
    v = _get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data").get(f"ISBN:{isbn}")
    if not v or not v.get("title"):
        return None
    return {
        "baslik": v["title"],
        "yazar": ", ".join(a.get("name", "") for a in v.get("authors", [])),
        "yayinevi": ", ".join(p.get("name", "") for p in v.get("publishers", [])),
    }


def _google(isbn: str) -> dict | None:
    ogeler = _get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}").get("items") or []
    v = ogeler[0].get("volumeInfo", {}) if ogeler else {}
    if not v.get("title"):
        return None
    return {"baslik": v["title"], "yazar": ", ".join(v.get("authors", [])), "yayinevi": v.get("publisher", "")}


def eser_bilgisi(isbn: str) -> dict | None:
    return _open_library(isbn) or _google(isbn)
