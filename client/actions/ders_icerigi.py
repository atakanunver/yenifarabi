"""
actions/ders_icerigi.py — Öğretmenin verdiği derse/konuya ait kitap sayfalarını
sunucudan (server/icerik.py) getirir.

Server-taşıma (2026-08-14): eşleştirme mantığı (_bolum_bul, kelime-örtüşme
sayfa seçimi, sembol şüphesi, kitap özeti, kırpma) artık BURADA değil,
`server/icerik.py::ders_icerigi_endpoint`'te — "Brain karar verir, Client
görüntüler" ilkesi, kitap_sorusu.py'nin RAG çağrısıyla aynı ruhta. Bu dosya
artık yalnızca HTTP çağrısı + sessiz fallback yapıyor.

NOT: `_norm`, `_kelimeler`, `_ders_eslesir`, `gorunen_ad`, `ders_kodu` BURADA
KALDI (silinmedi) — `actions/kitap_sorusu.py` hâlâ `_ders_eslesir`'i import
ediyor (client'ın kendi kitap listesi eşleşmesi için, bkz. o dosya). Bunlar
saf metin fonksiyonları, dosya I/O'su yok, client'ta kalmalarının bir
maliyeti yok — yeniden adlandırmayın/imzasını değiştirmeyin, kitap_sorusu.py
sessizce bozulur.
"""

import re
import unicodedata

import requests
from core.tahta import auth_headers as _auth_headers
from core.tahta import sunucu_url as _sunucu_url

ZAMAN_ASIMI = 20.0  # server-taraflı cache'siz ilk tarama ölçülmedi, pay bırakıldı

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

_SINIRLI_DEVAM = (
    "KISIT: Kitap sayfası getirilemedi. Elindeki plan ve kazanım metni "
    "çerçevendir; onun dışına çıkma ve kitapta olmayan sayfa/alıntı UYDURMA. "
    "Sınıfa teknik sorun anlatma. Anlatıma devam et: konuyu kazanım metnine "
    "sadık kalarak `web_search` ile araştırıp derinleştirebilirsin — kitap "
    "zaten iskelet verir, anlatım senindir. Kitap sayfası gerçekten gerekiyorsa "
    "ders_icerigi'ni farklı bir tema ya da konu adıyla yeniden çağır."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "")).translate(_TR).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _kelimeler(s: str) -> set[str]:
    return {k for k in _norm(s).split() if len(k) > 3}


def _ders_eslesir(sorgu: str | None, hedef: str) -> bool:
    if not sorgu:
        return True
    h = _norm(hedef)
    kelimeler = [k for k in _norm(sorgu).split() if k]
    return all(k in h for k in kelimeler) if kelimeler else True


_GORUNEN_AD = {
    "BIYOLOJI":            "Biyoloji",
    "COGRAFYA":            "Coğrafya",
    "FELSEFE":             "Felsefe",
    "FIZIK":               "Fizik",
    "KIMYA":               "Kimya",
    "MATEMATIK":           "Matematik",
    "MATEMATIK TD":        "Temel Düzey Matematik",
    "TARIH":               "Tarih",
    "TDE":                 "Türk Dili ve Edebiyatı",
    "TDE SBL":             "Türk Dili ve Edebiyatı",
    "T C INKILAP TARIHI":  "T.C. İnkılap Tarihi ve Atatürkçülük",
    "DIN KULTURU":         "Din Kültürü ve Ahlak Bilgisi",
    "HAZIRLIK MATEMATIK":  "Hazırlık Matematik",
    "HAZIRLIK TDE":        "Hazırlık Türk Dili ve Edebiyatı",
    "HAZIRLIK TDE SBL":    "Hazırlık Türk Dili ve Edebiyatı",
}


def gorunen_ad(ders_kodu: str) -> str:
    kod = (ders_kodu or "").strip().upper()
    return _GORUNEN_AD.get(kod, kod.title())


def ders_kodu(ad: str) -> str:
    n = _norm(ad)
    if not n:
        return ""
    for kod, gorunen in _GORUNEN_AD.items():
        if _norm(gorunen) == n or _norm(kod) == n:
            return kod
    return n.upper()


def ders_icerigi(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    ders = (p.get("ders") or "").strip()
    sinif = (p.get("sinif") or "").strip()
    derslik = ""
    if not sinif:
        try:
            from core import tahta
            sinif = tahta.sinif_duzeyi() or ""
            if sinif:
                log(f"[Ders İçeriği] sınıf dersliktan alındı: {sinif}")
        except Exception:
            pass
    try:
        from core import tahta
        derslik = tahta.derslik() or ""
    except Exception:
        pass
    konu = (p.get("konu") or "").strip()
    tema = (p.get("tema") or "").strip()

    if ders or konu:
        try:
            from core import transcript
            transcript.log_frame(ders or "", tema or konu)
        except Exception:
            pass

    istek = {
        "ders": ders, "sinif": sinif or None, "konu": konu, "tema": tema,
        "sayfa_adedi": int(p.get("sayfa_adedi") or 6), "liste": bool(p.get("liste")),
        "derslik": derslik or None,
    }

    try:
        r = requests.post(f"{_sunucu_url()}/api/egitim/ders_icerigi", json=istek,
                           headers=_auth_headers(), timeout=ZAMAN_ASIMI)
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        log(f"[Ders İçeriği] sunucu hatası: {type(e).__name__}: {e}")
        return _SINIRLI_DEVAM

    metin = veri.get("metin") or _SINIRLI_DEVAM
    baslik = veri.get("baslik")
    log(f"[Ders İçeriği] status={veri.get('status')} · {veri.get('latency_ms')}ms")

    if baslik and player is not None and hasattr(player, "show_content"):
        player.show_content(baslik, metin)

    return metin
