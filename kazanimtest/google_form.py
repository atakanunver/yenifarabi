"""kazanimtest/google_form.py — Apps Script web uygulamasına (apps_script/Code.gs) form yaptırır.
Yalnızca soru metinleri + okul numarası alanı Google'a gider; öğrenci adı/telefonu gitmez."""

import json
from pathlib import Path

import httpx

GIZLI = Path(__file__).with_name("config") / "gizli.json"


class FormHatasi(Exception):
    pass


def gizli_oku(yol: Path = GIZLI) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def govde(anahtar: str, baslik: str, aciklama: str, sorular: list[dict], puan: int = 10) -> dict:
    return {
        "anahtar": anahtar,
        "baslik": baslik,
        "aciklama": aciklama,
        "sorular": [
            {"metin": s["soru"], "secenekler": s["secenekler"], "dogru_index": s["dogru_index"], "puan": puan}
            for s in sorular
        ],
    }


def form_olustur(gizli: dict, baslik: str, aciklama: str, sorular: list[dict], istemci=None) -> dict:
    """{form_url, form_kisa_url, form_id, tablo_url} döner; hata → FormHatasi."""
    k = istemci or httpx
    # Okul ağı SSL-inceleme yapıyor (MEB-CERT, Python katı X509 kipinde reddediliyor);
    # Google'a Müdür PC WifiHttpProxy'si üzerinden gidilir (gizli.json::proxy).
    ek = {"proxy": gizli["proxy"]} if gizli.get("proxy") else {}
    try:
        r = k.post(
            gizli["script_url"],
            json=govde(gizli["anahtar"], baslik, aciklama, sorular),
            follow_redirects=True,
            timeout=120,
            **ek,
        )
        veri = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise FormHatasi(f"Apps Script çağrısı başarısız: {e}") from e
    if not isinstance(veri, dict) or not veri.get("ok"):
        raise FormHatasi(f"Apps Script hata: {veri.get('hata') if isinstance(veri, dict) else veri}")
    return {a: veri.get(a) for a in ("form_url", "form_kisa_url", "form_id", "tablo_url")}
