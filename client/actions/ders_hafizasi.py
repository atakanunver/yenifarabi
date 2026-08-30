"""
actions/ders_hafizasi.py — "Geçen ders ne işlemiştik" tarzı sorular için
Farabi'nin KENDİ geçmiş ders kayıtlarını sunucudan (server/ders_hafizasi.py)
getirir.

Server-taşıma (2026-08-18): eşleştirme mantığı artık BURADA değil,
`server/ders_hafizasi.py`'de — bu tahtanın `POST /api/egitim/
ders_kaydi_yedek` ile zaten yolladığı `yedekler/ders_kaydi/<derslik>/`
dosyalarına bakıyor. Bu dosya yalnızca HTTP çağrısı yapıyor; "süren oturumu
hariç tut" kuralı da server'a taşındı — bu tahta yalnızca kendi güncel
dosya adını bildiriyor, hariç tutma işini server yapıyor.

`ders_icerigi` ile farkı: `ders_icerigi` KİTAPTAN konu anlatımı getirir; bu
araç kitaba hiç bakmaz. `kitap_sorusu` ile farkı: o da sunucuya gider ama
RAG'a (kitap içeriğine); bu, bu tahtanın kendi geçmiş ders kayıtlarına gider.

Bu araç SORU SUNUM PROTOKOLÜ'ne tabi DEĞİLDİR (bir soru sunmuyor, bir bilgi
sorgusuna cevap veriyor) — `kitap_sorusu` gibi hemen cevap verir, sessizlik
beklemez.
"""

import requests
from core import transcript
from core.tahta import auth_headers as _auth_headers
from core.tahta import derslik as _derslik
from core.tahta import sunucu_url as _sunucu_url

ZAMAN_ASIMI = 10.0


def ders_hafizasi(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    istek = {
        "derslik": _derslik() or "",
        "ders": (p.get("ders") or "").strip(),
        "konu": (p.get("konu") or "").strip(),
        "guncel_dosya": transcript.session_file().name,
    }
    try:
        r = requests.post(f"{_sunucu_url()}/api/egitim/ders_hafizasi",
                           json=istek, headers=_auth_headers(), timeout=ZAMAN_ASIMI)
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        log(f"[Ders Hafızası] sunucu hatası: {type(e).__name__}: {e}")
        return "Şu an geçmiş ders kayıtlarına ulaşamıyorum, efendim."

    metin = veri.get("metin") or "Geçmiş ders kaydı okunamadı, efendim."
    log(f"[Ders Hafızası] yanıt alındı ({len(metin)} karakter)")
    return metin
