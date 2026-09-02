"""
server/tests/ ortak sahteleme altyapısı.

Neden ayrı bir dosya: `rag.py`'yi GPU'suz/DB'siz test edebilmek için üç
sahte parça gerekiyor (embedding modeli, reranker, psycopg2 bağlantısı) ve
bunlar birden fazla test dosyasında işe yarayacak. `client/tests/
conftest.py` ile aynı gerekçe — orada gerçek log dosyalarını korumak,
burada gerçek GPU/DB'ye hiç dokunmamak.

`RagMotoru`'nun yapıcısı ZATEN enjeksiyonlu (`RagMotoru(embed_model,
reranker, ...)`) — bu dosya o tasarımın karşılığını veriyor, üretim kodunda
test için hiçbir değişiklik gerekmiyor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class SahteEmbed:
    """`embed_model.encode(soru, normalize_embeddings=True)` — gerçek
    bge-m3 yerine sabit bir vektör. Vektörün İÇERİĞİ önemsiz: sorgu
    sonuçlarını `SahteBaglanti` belirliyor, benzerlik hesabı DB'de."""

    def __init__(self, patlat: Exception | None = None):
        self.patlat = patlat
        self.cagrildi = 0

    def encode(self, soru, normalize_embeddings=False):
        self.cagrildi += 1
        if self.patlat:
            raise self.patlat
        return [0.0] * 1024


class SahteReranker:
    """`reranker.predict(ciftler)` — skorları test belirler.

    `skorlar` bir liste ise sırayla eşleştirilir; bir sayı ise TÜM adaylara
    aynı skor verilir. `gorulen_ciftler` ile rerank'e HANGİ metnin gittiği
    denetlenebilir (R-4'ün kırpma testi tam olarak buna bakacak)."""

    def __init__(self, skorlar=0.9, patlat: Exception | None = None):
        self.skorlar = skorlar
        self.patlat = patlat
        self.gorulen_ciftler = None

    def predict(self, ciftler):
        self.gorulen_ciftler = list(ciftler)
        if self.patlat:
            raise self.patlat
        if isinstance(self.skorlar, (int, float)):
            return [float(self.skorlar)] * len(ciftler)
        return [float(s) for s in self.skorlar[:len(ciftler)]]


class _SahteImlec:
    def __init__(self, baglanti):
        self._b = baglanti

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._b.sorgular.append((sql, params))
        if "FROM chunk_egitim" in sql:
            self._sonuc = list(self._b.metin_satirlari)
        elif "FROM chunk_tablo" in sql:
            if self._b.tablo_patlat:
                raise self._b.tablo_patlat
            self._sonuc = list(self._b.tablo_satirlari)
        else:                                    # INSERT (metrik / soru_log)
            self._sonuc = []

    def fetchall(self):
        return self._sonuc


class SahteBaglanti:
    """psycopg2 bağlantısının `rag.py`'nin kullandığı kadarı.

    SQL metnine bakarak hangi tabloya sorulduğunu ayırt eder — gerçek bir
    DB'ye ihtiyaç duymadan `_ilk_k_getir`/`_tablo_getir`/`_logla` yollarının
    üçünü de ayrı ayrı denetlenebilir kılar.

    Satır biçimleri üretim şemasıyla BİREBİR aynı olmalı:
      chunk_egitim → (id, sayfa_no, metin, mesafe)
      chunk_tablo  → (id, sayfa_no, baslik, metin_ozet, mesafe)
    """

    def __init__(self, metin_satirlari=(), tablo_satirlari=(),
                 tablo_patlat: Exception | None = None):
        self.metin_satirlari = list(metin_satirlari)
        self.tablo_satirlari = list(tablo_satirlari)
        self.tablo_patlat = tablo_patlat
        self.sorgular = []        # [(sql, params), ...]
        self.commit_sayisi = 0
        self.rollback_sayisi = 0

    def cursor(self):
        return _SahteImlec(self)

    def commit(self):
        self.commit_sayisi += 1

    def rollback(self):
        self.rollback_sayisi += 1

    # ── denetim yardımcıları ────────────────────────────────────────────
    def _insertlar(self, tablo: str):
        return [(s, p) for s, p in self.sorgular
                if s.strip().upper().startswith("INSERT") and tablo in s]

    def metrik_kayitlari(self):
        return self._insertlar("metrik")

    def soru_log_kayitlari(self):
        return self._insertlar("soru_log")


@pytest.fixture(autouse=True)
def _ag_kapisi(monkeypatch):
    """AĞ KAPISI — bu dizindeki hiçbir test gerçek Ollama'ya gitmemeli.

    Neden autouse: `RagMotoru._llm_cevap` urllib ile 127.0.0.1:11434'e
    çıkıyor ve bu makinede Ollama GERÇEKTEN çalışıyor. Bir test onu
    monkeypatch etmeyi unutursa sessizce ağa çıkar — testin hızı ve
    yeniden üretilebilirliği bozulur, üstelik bunu kimse fark etmez.

    Bu bir kuramsal endişe değil: mutasyon testinde (eşik kapısı devre
    dışı bırakılıp testlerin gerçekten yakaladığı doğrulanırken) tam
    olarak bu oldu — süre 0,05 sn'den 1,20 sn'ye çıktı, çünkü eşik
    kapısını atlayan akış gerçek Ollama'ya ulaştı.

    Artık varsayılan: LLM'e ulaşmak GÜRÜLTÜLÜ BİR HATA. LLM'i gerçekten
    isteyen testler `monkeypatch.setattr(motor, "_llm_cevap", ...)` ile
    ÖRNEK seviyesinde geçersiz kılar (sınıf seviyesindeki bu kapı
    yerinde kalır)."""
    import rag

    def _yasak(self, sistem, soru, timeout=30.0):
        raise AssertionError(
            "Test gerçek LLM'e (Ollama) ulaşmaya çalıştı. Bu testte "
            "LLM'e gidilmesi bekleniyorsa `monkeypatch.setattr(motor, "
            "'_llm_cevap', ...)` ile sahtele; gidilmemesi gerekiyorsa "
            "bu hata gerçek bir regresyondur."
        )

    monkeypatch.setattr(rag.RagMotoru, "_llm_cevap", _yasak)


@pytest.fixture
def motor():
    """Varsayılan sahte parçalarla bir RagMotoru. Testler
    `motor.embed_model`/`motor.reranker`'ı gerektiğinde değiştirir."""
    import rag
    return rag.RagMotoru(SahteEmbed(), SahteReranker())
