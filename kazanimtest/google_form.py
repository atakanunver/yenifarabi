"""kazanimtest/google_form.py — Apps Script web uygulamasına (apps_script/Code.gs) form yaptırır.
Yalnızca soru metinleri + okul numarası alanı Google'a gider; öğrenci adı/telefonu gitmez."""

import json
import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger("kazanimtest.google")

GIZLI = Path(__file__).with_name("config") / "gizli.json"


class FormHatasi(Exception):
    pass


def _tekrarli_post(k, url: str, deneme: int = 3, bekleme_sn: float = 5.0, **kw) -> dict:
    """YALNIZCA tekrarlanabilir (idempotent) işlemler için: Apps Script yönlendirmesi ara sıra
    JSON yerine HTML (doGet sayfası) döndürüyor (2026-10-08, aralıklı) — kısa beklemeyle tekrar."""
    for i in range(1, deneme + 1):
        try:
            return k.post(url, **kw).json()
        except ValueError:  # JSON değil
            if i == deneme:
                raise
            log.warning("Apps Script JSON dönmedi (deneme %d/%d) — tekrar", i, deneme)
            time.sleep(bekleme_sn)
    raise AssertionError("ulaşılmaz")


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


def sonuclari_al(gizli: dict, form_id: str, istemci=None) -> list[dict]:
    """Formun gönderimleri: [{zaman, okul_no, secimler[şık metni|None]}]; hata → FormHatasi."""
    k = istemci or httpx
    ek = {"proxy": gizli["proxy"]} if gizli.get("proxy") else {}
    try:
        veri = _tekrarli_post(
            k,
            gizli["script_url"],
            json={"anahtar": gizli["anahtar"], "islem": "sonuclar", "form_id": form_id},
            follow_redirects=True,
            timeout=120,
            **ek,
        )
    except (httpx.HTTPError, ValueError) as e:
        raise FormHatasi(f"Apps Script sonuç çağrısı başarısız: {e}") from e
    if not isinstance(veri, dict) or not veri.get("ok"):
        raise FormHatasi(f"Apps Script hata: {veri.get('hata') if isinstance(veri, dict) else veri}")
    return veri.get("cevaplar") or []


def raporlari_yaz(gizli: dict, raporlar: list[dict], istemci=None, parti: int = 20) -> dict[str, str]:
    """Aylık raporları Apps Script'e yazdırır (her token için bir Google Dokümanı); {token: doküman_linki} döner.
    raporlar: [{token, ay, sinif, okul_no, son_gecerlilik, veri}] — isim/telefon İÇERMEZ.
    Küçük partiler: her doküman birkaç sn sürer (Apps Script 6 dk sınırı). Bir token'ın linki eksikse FormHatasi."""
    k = istemci or httpx
    ek = {"proxy": gizli["proxy"]} if gizli.get("proxy") else {}
    linkler: dict[str, str] = {}
    for i in range(0, len(raporlar), parti):
        grup = raporlar[i:i + parti]
        try:
            veri = _tekrarli_post(
                k,
                gizli["script_url"],
                json={"anahtar": gizli["anahtar"], "islem": "rapor_yaz", "raporlar": grup},
                follow_redirects=True,
                timeout=300,
                **ek,
            )
        except (httpx.HTTPError, ValueError) as e:
            raise FormHatasi(f"Apps Script rapor çağrısı başarısız: {e}") from e
        if not isinstance(veri, dict) or not veri.get("ok"):
            raise FormHatasi(f"Apps Script hata: {veri.get('hata') if isinstance(veri, dict) else veri}")
        if veri.get("yazilan") != len(grup):
            raise FormHatasi(f"Apps Script {len(grup)} rapordan {veri.get('yazilan')} tanesini yazdı")
        yanit = veri.get("linkler") if isinstance(veri.get("linkler"), dict) else {}
        for r in grup:
            link = yanit.get(r["token"])
            if not isinstance(link, str) or not link.startswith("https://"):
                raise FormHatasi(f"Apps Script {r['token'][:4]}… raporu için doküman linki döndürmedi")
            linkler[r["token"]] = link
    return linkler
