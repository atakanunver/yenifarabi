"""server/uzak_model.py — bilgehan'daki farabi-embed servisinin istemcisi.

2026-10-04: iki RTX 3060 Ollama'da (qwen3.8:27b); kullanıcı kararıyla tüm RAG
model işi bilgehan'da (gömme GTX 1660 Ti fp32, rerank RTX 3060 fp16 — servis
kaynağı `server/embed_servisi/`), Farabi CPU'su RAG için kullanılmaz. Bu
sınıflar RagMotoru'nun beklediği arayüzü birebir taklit eder — `rag.py`
değişmez:

- `UzakEmbed.encode(metin_veya_liste, normalize_embeddings=True)` →
  SentenceTransformer gibi np.ndarray (tek metin → 1-B, liste → 2-B).
- `UzakReranker.predict(ciftler)` → CrossEncoder gibi np.ndarray skor.

Hata durumu: uzak çağrı başarısızsa istisna yükselir; rag.py bunu `hata`
durumuna çevirir (tahta `_SINIRLI_DEVAM`'a düşer, ders bozulmaz).
`UzakEmbed(yerel=...)` ile yerel bir geri dönüş modeli verilebilir ama
farabi-api bunu bilerek kullanmaz (CPU boşta kalsın kararı).

Ağ hatası sonrası her istekte tekrar denenmesin diye kısa bir bekleme
(`BEKLEME_SN`) uygulanır; bu sürede çağrılar hemen hata verir.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

log = logging.getLogger("uzak_model")

BEKLEME_SN = 30.0
# Toplu indeksleme: 32 parça × ~600 token, 1660 Ti fp32'de birkaç saniye —
# sorgu yolunun 8 sn'si burada dar kalır.
TOPLU_ZAMAN_ASIMI_SN = 120.0
# farabi-api URL/anahtarı systemd drop-in'inden (ortam) alır; elle çalıştırılan
# indeksleme betikleri için aynı bilgi gitignore'lu bu dosyada.
AYAR_DOSYASI = Path(__file__).resolve().parent / "config" / "embed.json"


class _UzakIstemci:
    def __init__(self, taban_url: str, anahtar: str, zaman_asimi: float):
        self.taban_url = taban_url.rstrip("/")
        self.anahtar = anahtar
        self.zaman_asimi = zaman_asimi
        # LAN adresi — Müdür PC proxy'si açık olsa bile ASLA proxy'den geçme.
        self._acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._kilit = threading.Lock()
        self._kapali_bitis = 0.0

    def ulasilabilir(self) -> bool:
        return time.monotonic() >= self._kapali_bitis

    def _isaretle_kapali(self) -> None:
        with self._kilit:
            self._kapali_bitis = time.monotonic() + BEKLEME_SN

    def post(self, yol: str, govde: dict) -> dict:
        istek = urllib.request.Request(
            self.taban_url + yol,
            data=json.dumps(govde, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Farabi-Embed-Key": self.anahtar,
            },
            method="POST",
        )
        try:
            with self._acici.open(istek, timeout=self.zaman_asimi) as yanit:
                return json.loads(yanit.read())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            self._isaretle_kapali()
            raise


class UzakEmbed:
    def __init__(self, istemci: _UzakIstemci, yerel=None):
        self.istemci = istemci
        self.yerel = yerel

    def encode(self, metinler, normalize_embeddings: bool = True, **kwargs):
        tek = isinstance(metinler, str)
        liste = [metinler] if tek else list(metinler)
        if self.istemci.ulasilabilir():
            try:
                # SentenceTransformer gibi batch_size'a uy: indeksleme betikleri
                # yüzlerce parçayı tek çağrıda verir (servis sınırı 256 metin).
                adim = max(1, int(kwargs.get("batch_size") or 32))
                parcalar = []
                for i in range(0, len(liste), adim):
                    yanit = self.istemci.post(
                        "/embed",
                        {"metinler": liste[i : i + adim], "normalize": normalize_embeddings},
                    )
                    parcalar.append(np.asarray(yanit["vektorler"], dtype=np.float32))
                v = np.concatenate(parcalar) if parcalar else np.zeros((0, 0), np.float32)
                return v[0] if tek else v
            except Exception as e:
                if self.yerel is None:
                    raise
                log.warning(
                    "Uzak gömme başarısız (%s: %s) — yerel CPU modeline düşülüyor",
                    type(e).__name__,
                    e,
                )
        if self.yerel is None:
            raise ConnectionError("farabi-embed ulaşılamıyor ve yerel model yok")
        return self.yerel.encode(
            metinler, normalize_embeddings=normalize_embeddings, **kwargs
        )


class UzakReranker:
    def __init__(self, istemci: _UzakIstemci):
        self.istemci = istemci

    def predict(self, ciftler, **kwargs):
        if not self.istemci.ulasilabilir():
            raise ConnectionError(
                "farabi-embed kısa süre önce ulaşılamadı (bekleme süresinde)"
            )
        yanit = self.istemci.post("/rerank", {"ciftler": [list(c) for c in ciftler]})
        return np.asarray(yanit["skorlar"], dtype=np.float32)


def olustur(taban_url: str, anahtar: str, yerel_embed=None, zaman_asimi: float = 8.0):
    """(UzakEmbed, UzakReranker) — ikisi aynı istemciyi (ve beklemeyi) paylaşır."""
    istemci = _UzakIstemci(taban_url, anahtar, zaman_asimi)
    return UzakEmbed(istemci, yerel_embed), UzakReranker(istemci)


def ayar_oku() -> tuple[str, str]:
    """(url, anahtar): önce FARABI_EMBED_URL/ANAHTAR ortamı, yoksa config/embed.json."""
    url = os.environ.get("FARABI_EMBED_URL", "").strip()
    if url:
        return url, os.environ.get("FARABI_EMBED_ANAHTAR", "")
    try:
        veri = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))
        return (veri.get("url") or "").strip(), veri.get("anahtar") or ""
    except (OSError, ValueError):
        return "", ""


def toplu_gomme_modeli(model_adi: str):
    """İndeksleme betikleri için: uzak ayar varsa UzakEmbed (bilgehan GPU),
    yoksa eskisi gibi yerel CPU SentenceTransformer. 2026-10-04 kararı:
    Farabi CPU'su RAG için kullanılmaz — ayar dosyası Farabi'de kurulu."""
    url, anahtar = ayar_oku()
    if url:
        log.info("Toplu gömme uzakta: %s", url)
        return UzakEmbed(_UzakIstemci(url, anahtar, TOPLU_ZAMAN_ASIMI_SN))
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_adi, device="cpu")
