# Open WebUI Farabi modları: uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open WebUI'de, Farabi RAG'ına (pgvector + bge-m3 vektör araması, CPU, yeniden sıralama YOK) dayanan 14 Farabi modu ve öğretmen/idare erişim düzeni kurmak.

**Architecture:**
- **farabi-api:** Yalnızca bge-m3 gömme modeli CPU'da yüklenir; yeniden sıralayıcı (reranker) YÜKLENMEZ (Task 0 kapısı geçilemedi, kullanıcı kararı C). Yeni `POST /api/webui/ara` ucu, LLM'e gitmeden ders kitabı (`chunk_egitim` + `chunk_tablo`) ya da mevzuat (`chunk_idari`, yeni) parçalarını sayfa etiketiyle döndürür.
- **Open WebUI:** Bir inlet filtresi her kullanıcı mesajında bu ucu çağırır ve sonucu sistem mesajına ekler.
- **Kurulum:** Modlar, gruplar, hesaplar ve ayarlar `openwebui/kur.py` ile Open WebUI'nin resmi API'si üzerinden tekrar çalıştırılabilir biçimde kurulur.

**Tech Stack:** FastAPI, psycopg2 + pgvector, sentence-transformers (bge-m3, bge-reranker-v2-m3, CPU), PyMuPDF, python-docx, tesseract 5.5 (CLI), Open WebUI 0.11.0 (Functions/Filter API), Ollama `qwen3.8:27b`.

**Spec:** `docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md`

## Global Constraints

- **Kod/plan ayrımı (Kural 11):** Plan Opus ile yazıldı, kod Sonnet ile yazılır.
- **Kural 3:** Tek seferde tek modül değiştirilir. Görev sırası bozulmaz.
- **Kural 5:** Tahta yolu (`RagMotoru.sorgula`, `/api/egitim/question`) DEĞİŞMEZ. `server/tests/test_rag.py` her görevden sonra aynen geçer. Spec §3.2 "`sorgula()` `ara()`'yı çağırır" diyordu; bilinçli sapma: `ara()` ayrı yazılır, `sorgula()`'ya dokunulmaz (tahta yolunda sıfır risk).
- **Kural 8:** Yeni pip bağımlılığı yok. python-docx, PyMuPDF, pgvector, sentence-transformers server venv'inde zaten var; tesseract kuruldu (`tur`, `eng`).
- **Kural 9:** Anahtar ya da şifre koda ve git'e girmez. `server/config/api_keys.json` (gitignore'lu) ve `openwebui/.env` (`*.env` ile gitignore'lu) kullanılır. Bu dosyaların içeriği ekrana basılmaz ve okunmaz.
- **Testler:**
  - server: `cd server && venv/bin/python -m pytest tests/ -q`
  - openwebui: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests -q`
- **Üretime alma:** `sudo systemctl restart farabi-api.service`. Log yalnızca `journalctl -u farabi-api.service`.
- **Model ve düşünme:**
  - Model `qwen3.8:27b`, tek model. Yeni model kurulmaz.
  - Düşünme varsayılanı filtre tarafından ayarlanır. Model `params` içine `think` KONMAZ, çünkü Open WebUI model parametrelerini sohbet ayarlarının üzerine yazar (`utils/payload.py::apply_model_params_to_body`). Bu, spec §3.6'dan bilinçli sapma.
- **Arama sabitleri (Task 0 sonrası, kullanıcı kararı C):** yeniden sıralama YOK. `chunk_egitim`/`chunk_idari` ve `chunk_tablo`'dan `TOP_N = 4`'er aday mesafeye göre birleştirilir, ilk 4 döner. Skor = `1 - kosinüs mesafesi`. Zayıf eşiği `ESIK_BENZERLIK = 0.55` (benchmark/reports 2026-08-11, `--esik 0.55`, %90 doğru tespit).
- **Soru ve kaynak bloğu sınırları:** Arama ucuna giden soru en fazla 2000 karakter. Filtrenin eklediği kaynak bloğu en fazla 7500 karakter (yaklaşık 2.500 token).
- **Loglama:** `/api/webui/ara` yalnızca `metrik`'e yazar (`sonuc` = `webui_ok` | `webui_zayif` | `webui_hata`, `tahta_id` NULL). `soru_log`'a YAZMAZ.
- **Erişim:** Uç `0.0.0.0:8000` üzerinden yerel ağa açık, ama `X-Farabi-WebUI-Key` başlığı zorunlu.
- **Commit:** Commit'ler yereldir. **Push yalnızca kullanıcı açıkça isterse** yapılır; repo herkese açık. Spec dosyasında öğretmen adları var, kullanıcı onayı olmadan commit'e eklenmez.

## Review Focus

1. **Filtrenin HTTP çağrısı Open WebUI'nin olay döngüsünü kilitlerse** farabi-api yavaşken tüm kullanıcılar donar. Beklenen: çağrı `asyncio.to_thread` içinde yapılır. Test: Task 5'te `test_eszamanli_iki_istek_birbirini_beklemez`.
2. **Başlık ve etiket gibi görev istekleri de filtreden geçer** (`__metadata__["task"]`). Bunlarda arama yapılmamalı. Test: Task 5'te `test_gorev_isteginde_arama_yapilmaz`.
3. **Görsel ve metin içeren mesaj** (`content` bir liste) gelirse metin kısmı çıkarılıp aranmalı, filtre çökmemeli. Test: Task 5'te `test_liste_icerikli_mesajdan_metin_alinir`.
4. **farabi-api kapalı, 401 veriyor ya da zaman aşımına uğruyorsa** mesaj değişmeden modele gitmeli. Test: Task 5'te `test_api_ulasilamazsa_govde_degismez`.
5. **Kapsam için hiç kitap bulunmazsa ya da DB sorgusu patlarsa** uç 500 vermemeli, havuza bozuk bağlantı dönmemeli. Test: Task 3'te `test_kapsamda_kitap_yoksa_zayif` ve `test_db_hatasinda_hata_ve_rollback`.

---

## Dosya haritası

| Dosya | Sorumluluk |
|---|---|
| `server/main.py` (değişir) | RAG'ı CPU'da açar, `webui.router`'ı bağlar, `webui.MOTOR`'u atar |
| `server/rag.py` (değişir) | Yeni `RagMotoru.ara()`: çok kaynaklı arama + rerank, LLM yok. `sorgula()` dokunulmaz |
| `server/auth.py` (değişir) | Yeni `webui_anahtari()`: `api_keys.json::webui_key` okur |
| `server/webui.py` (yeni) | `POST /api/webui/ara`, kapsamdan kitaba eşleme, sınıf çıkarımı, etiketler, metrik |
| `server/schema_idari.sql` (yeni) | `idari_belge`, `chunk_idari` |
| `server/idari_yukle.py` (yeni) | Mevzuat klasörünü okur (PDF, OCR, docx, jpeg), parçalar, embed eder, yazar |
| `server/tests/conftest.py` (değişir) | `SahteBaglanti`'ya `chunk_idari`, `idari_belge`, `kitap` satırları |
| `server/tests/test_rag_ara.py`, `test_webui.py`, `test_idari_yukle.py` (yeni) | Birim testleri |
| `openwebui/farabi_filtre.py` (yeni) | Open WebUI inlet filtresi |
| `openwebui/promptlar/*.md`, `openwebui/modlar.json` (yeni) | Çekirdek prompt + 14 mod |
| `openwebui/kur.py` (yeni) | Open WebUI API ile tekrar çalıştırılabilir kurulum |
| `openwebui/tests/test_filtre.py`, `test_kur.py` (yeni) | Birim testleri |
| `CLAUDE.md`, `server/CLAUDE.md`, `DECISIONS.md` (değişir) | Belgeleme |

---

### Task 0: CPU ölçüm kapısı (engelleyici, kod yok) — TAMAMLANDI

> **Sonuç (2026-10-03):** Tam rerank (20 aday) CPU'da medyan 9,91 sn → kapı GEÇİLEMEDİ. `max_length=512` 10,53 sn. Rerank 8 aday 3,53 sn (31/35), vektör-only 0,13 sn (28/35), tam rerank 32/35. **Kullanıcı kararı: C — yeniden sıralama yok.** Aşağıdaki adımlar kayıt için durur; yeniden koşulmaz.

**Files:** yok. Sonuç DECISIONS.md'ye Task 8'de yazılır.

**Interfaces:**
- Consumes: `benchmark/recall_test.py` (zaten CPU'da çalışıyor), `benchmark/sorular.json`
- Produces: Karar. CPU yeterliyse Task 1'e geçilir; değilse DUR ve kullanıcıya dön.

- [ ] **Step 1: Ölçümü koş**

```bash
cd /home/ata/farabi/benchmark && venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1 --rapor /tmp/claude-1000/cpu_olcum.json
```
Beklenen: Ekranda soru başına `sure_arama_sn` ve `sure_rerank_sn`, sonunda recall@4 özeti.

- [ ] **Step 2: Kapıyı değerlendir**

```bash
python3 -c "
import json,statistics as s
r=json.load(open('/tmp/claude-1000/cpu_olcum.json'))
k=[x for x in r['sonuclar'] if 'sure_rerank_sn' in x] if 'sonuclar' in r else r
t=[x['sure_arama_sn']+x['sure_rerank_sn'] for x in k]
print('medyan',round(s.median(t),2),'p90',round(sorted(t)[int(len(t)*0.9)-1],2))
print({kk:v for kk,v in r.items() if 'recall' in kk})"
```
Rapor anahtar adları farklıysa önce `python3 -c "import json;print(list(json.load(open('/tmp/claude-1000/cpu_olcum.json')).keys()))"` ile bakılır.

**Kapı:**
- Medyan (arama + rerank) **< 3,0 sn** ve recall@4 **≥ %95** (38/40) olmalı.
- Medyan 3 sn'yi aşarsa tek değişkenli bir deneme yapılır: `recall_test.py`'de `CrossEncoder(RERANK_MODEL, device="cpu", max_length=512)` ile Step 1 yeniden koşulur (dosya değişikliği yalnızca ölçüm için, sonra geri alınır).
- Yine aşarsa ya da recall düşerse **DUR**. Sonuçlar kullanıcıya sunulur; Task 1'e geçilmez.
- `max_length=512` gerekli çıktıysa Task 1 Step 1'deki `RERANK_MAX_LENGTH = 512` kullanılır, gerekmediyse `None`.

---

### Task 1: RAG'ı CPU'da aç (`main.py`)

**Files:**
- Modify: `server/main.py:40-100` (yorum bloğu, `RAG_AKTIF`, `*_DEVICE`, lifespan model yükleme)

**Interfaces:**
- Consumes: Task 0 kararı (C: reranker yok)
- Produces: `durum["motor"]` = `RagMotoru(embed_model, None)` (CPU). `/ready` 200 döner. `/api/egitim/question` `hata` döner (değişmedi).

- [ ] **Step 1: Sabitleri ve yüklemeyi değiştir**

`server/main.py` içinde `RAG_AKTIF = False` ile `RERANK_DEVICE = "cuda:0"` arasındaki satırları şununla değiştir. Üstteki tarihli yorum bloğu korunur, sonuna bir paragraf eklenir:

```python
# 2026-10-03 (ikinci karar, kullanıcı): RAG CPU'da yeniden AÇIK — iki GPU
# Ollama'da kalır. Open WebUI Farabi modları /api/webui/ara üzerinden
# kitap/mevzuat parçası alır (docs/superpowers/specs/2026-10-03-openwebui-
# farabi-modlar-design.md). CPU ölçümü DECISIONS.md 2026-10-03'te.
# Yan etki: tahtadaki kitap_sorusu da yeniden kitaptan cevap verir.
RAG_AKTIF = True

EMBED_DEVICE = "cpu"
RERANK_DEVICE = "cpu"
# Reranker YÜKLENMEZ (2026-10-03, kullanıcı kararı C): CPU'da 20 adayın
# rerank'i medyan 9,9 sn sürdü (DECISIONS.md). Open WebUI yalnızca vektör
# aramasıyla çalışır (RagMotoru.ara). Tahta yolu (sorgula) reranker'sız
# çalışamaz → /api/egitim/question bugünkü gibi "hata" döner (davranış
# değişmez). Geri açmak: True + restart (CPU'da ~10 sn/soru).
RERANK_YUKLE = False
```

Lifespan'daki yükleme satırlarını şununla değiştir:

```python
        embed_model = SentenceTransformer(EMBED_MODEL, device=EMBED_DEVICE)
        if EMBED_DEVICE.startswith("cuda"):
            # fp16 yalnızca GPU'da anlamlı; CPU'da fp32 kalır.
            embed_model.half()
        reranker = None
        if RERANK_YUKLE:
            reranker = CrossEncoder(RERANK_MODEL, device=RERANK_DEVICE)
            if RERANK_DEVICE.startswith("cuda"):
                reranker.model.half()
        durum["motor"] = RagMotoru(embed_model, reranker)
```

Isınma bloğunda `reranker.predict(...)` satırını `if reranker is not None:` altına al; mesajlardaki "GPU" ifadesini cihaz adıyla değiştir: `print(f"Isınma tamamlandı (...) — gömme modeli {EMBED_DEVICE}'da hazır.")`. Başlangıç mesajı reranker'ın yüklenmediğini söylemeli.

`soru_sor` (`/api/egitim/question`) içindeki `if durum["motor"] is None:  # RAG_AKTIF=False` satırını şununla değiştir — tahta yolu bugünkü gibi hemen `hata` dönsün, `soru_log`'a hata satırı yağmasın:

```python
        if durum["motor"] is None or durum["motor"].reranker is None:
            # RAG kapalı ya da reranker yüklenmedi (2026-10-03 kararı C) —
            # tahta yolu reranker'sız çalışmaz; bugünkü davranış korunur.
            return SoruYanit(status="hata", latency_ms=0, request_id=request_id)
```

- [ ] **Step 2: Testleri koş**

Run: `cd /home/ata/farabi/server && venv/bin/python -m pytest tests/ -q`
Expected: Hepsi PASS. `main.py` testlerde import edilmiyor, regresyon yok.

- [ ] **Step 3: Üretime al ve doğrula**

```bash
sudo systemctl restart farabi-api.service
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/ready && break; sleep 2; done; echo
journalctl -u farabi-api.service -n 20 --no-pager | grep -E "Modeller|Isınma|hazır"
systemctl show farabi-api -p MemoryCurrent
curl -s http://127.0.0.1:11434/api/ps | grep -o '"name":"[^"]*"'
```
Beklenen:
- `{"status":"ready"}` dönmeli.
- Loglarda "Isınma tamamlandı … cpu'da hazır" görünmeli.
- Loglarda reranker'ın yüklenmediği yazmalı. Bellek yaklaşık 3 GB'ın altında olmalı.
- Ollama'da `qwen3.8:27b` hâlâ yüklü kalmalı; GPU'ya dokunulmadı.

- [ ] **Step 4: Commit**

```bash
cd /home/ata/farabi && git add server/main.py && git commit -m "server: bge-m3 CPU'da yüklü, reranker yok (Open WebUI Farabi modları için)"
```

---

### Task 2: `RagMotoru.ara()`: LLM'siz, yeniden sıralamasız çok kaynaklı arama

**Files:**
- Modify: `server/rag.py` (sınıfa yeni metotlar ve modül sabitleri eklenir; mevcut metotlar değişmez)
- Modify: `server/tests/conftest.py` (`SahteEmbed`, `SahteBaglanti` ve `_SahteImlec`)
- Create: `server/tests/test_rag_ara.py`

**Interfaces:**
- Produces:
  - `RagMotoru.ara(conn, kaynak: str, kaynak_idler: list[int], soru: str) -> dict`
    - `kaynak` ∈ {`"egitim"`, `"idari"`}
    - Dönen sözlük:
      ```
      {"durum": "ok"|"zayif"|"hata",
       "parcalar": [{"kaynak_id": int, "sayfa": int, "metin": str, "skor": float, "tur": "metin"|"tablo"}],
       "retrieval_ms": int|None, "rerank_ms": None, "en_iyi_skor": float|None, "hata"?: str}
      ```
    - `skor = round(1 - mesafe, 4)` (kosinüs benzerliği).
    - `en_iyi_skor < ESIK_BENZERLIK` (0.55) ise `zayif` ve `parcalar == []`.
    - `kaynak_idler` boşsa DB'ye gidilmez ve `zayif` döner.
    - Reranker HİÇ kullanılmaz; `RagMotoru(embed_model, None)` ile çalışır.
  - Sahte satır biçimleri:
    - `chunk_egitim` / `chunk_idari`: `(id, sayfa_no, metin, mesafe, kaynak_id)`
    - `chunk_tablo`: `(id, sayfa_no, baslik, metin_ozet, mesafe, kitap_id)`
  - `SahteEmbed.son_soru`: son `encode` çağrısındaki metin (Task 3 testi kullanır)

- [ ] **Step 1: conftest'i genişlet**

`server/tests/conftest.py`'de `SahteEmbed.encode` içinde `self.cagrildi += 1` satırının altına `self.son_soru = soru` ekle, `__init__`'e de `self.son_soru = None` ekle.

`_SahteImlec.execute` içindeki dal zincirini şununla değiştir. Sıra önemli: önce chunk tabloları, sonra `idari_belge`, en son `kitap`:

```python
    def execute(self, sql, params=None):
        self._b.sorgular.append((sql, params))
        if self._b.patlat_sql and self._b.patlat_sql in sql:
            raise self._b.patlat
        if "FROM chunk_egitim" in sql:
            self._sonuc = list(self._b.metin_satirlari)
        elif "FROM chunk_tablo" in sql:
            if self._b.tablo_patlat:
                raise self._b.tablo_patlat
            self._sonuc = list(self._b.tablo_satirlari)
        elif "FROM chunk_idari" in sql:
            self._sonuc = list(self._b.idari_satirlari)
        elif "FROM idari_belge" in sql:
            self._sonuc = list(self._b.idari_belge_satirlari)
        elif "FROM kitap" in sql:
            self._sonuc = list(self._b.kitap_satirlari)
        else:                                    # INSERT (metrik / soru_log)
            self._sonuc = []
```

`SahteBaglanti.__init__` imzasını ve gövdesini şununla değiştir. Mevcut çağrılar konumsal üç parametreyi aynen kullanabilir:

```python
    def __init__(self, metin_satirlari=(), tablo_satirlari=(),
                 tablo_patlat: Exception | None = None, *,
                 idari_satirlari=(), idari_belge_satirlari=(), kitap_satirlari=(),
                 patlat_sql: str | None = None, patlat: Exception | None = None):
        self.metin_satirlari = list(metin_satirlari)
        self.tablo_satirlari = list(tablo_satirlari)
        self.tablo_patlat = tablo_patlat
        self.idari_satirlari = list(idari_satirlari)
        self.idari_belge_satirlari = list(idari_belge_satirlari)
        self.kitap_satirlari = list(kitap_satirlari)
        self.patlat_sql = patlat_sql      # bu alt dizeyi içeren SQL `patlat`ı fırlatır
        self.patlat = patlat
        self.sorgular = []        # [(sql, params), ...]
        self.commit_sayisi = 0
        self.rollback_sayisi = 0
```

Run: `cd server && venv/bin/python -m pytest tests/test_rag.py -q`
Expected: PASS (davranış değişmedi).

- [ ] **Step 2: Başarısız testleri yaz**

`server/tests/test_rag_ara.py`:

```python
"""RagMotoru.ara() — Open WebUI arama yolu: yalnızca vektör araması, LLM ve
reranker YOK (2026-10-03 kararı C). Tahta yolu (`sorgula`) test_rag.py'de."""

import pytest

import rag
from conftest import SahteBaglanti, SahteEmbed, SahteReranker


def _m(id_, sayfa, metin, kaynak_id, mesafe=0.1):
    return (id_, sayfa, metin, mesafe, kaynak_id)


def _t(id_, sayfa, baslik, ozet, kitap_id, mesafe=0.1):
    return (id_, sayfa, baslik, ozet, mesafe, kitap_id)


@pytest.fixture
def motor():
    return rag.RagMotoru(SahteEmbed(), None)


@pytest.fixture(autouse=True)
def _llm_yasak(monkeypatch):
    def _patla(*a, **k):
        raise AssertionError("ara() LLM'e GİTMEMELİ")
    monkeypatch.setattr(rag.RagMotoru, "_llm_cevap", _patla)


def test_ok_parcalar_kaynak_id_sayfa_ve_benzerlik_skoru(motor):
    conn = SahteBaglanti([_m(1, 84, "Mol, madde miktarı birimidir.", 9, mesafe=0.2)])
    s = motor.ara(conn, "egitim", [9, 20], "mol nedir")
    assert s["durum"] == "ok" and s["rerank_ms"] is None
    assert s["parcalar"][0] == {"kaynak_id": 9, "sayfa": 84, "metin": "Mol, madde miktarı birimidir.",
                                "skor": 0.8, "tur": "metin"}
    assert s["en_iyi_skor"] == 0.8


def test_reranker_HIC_kullanilmaz():
    m = rag.RagMotoru(SahteEmbed(), SahteReranker(patlat=AssertionError("rerank çağrıldı")))
    assert m.ara(SahteBaglanti([_m(1, 1, "x", 9)]), "egitim", [9], "s")["durum"] == "ok"


def test_kaynak_idler_ANY_ve_LIMIT_TOP_N(motor):
    conn = SahteBaglanti([_m(1, 84, "x", 9)])
    motor.ara(conn, "egitim", [9, 20], "soru")
    sql, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
    assert "ANY(%s)" in sql and params[1] == [9, 20] and params[2] == rag.TOP_N


def test_en_fazla_TOP_N_parca_mesafe_sirasinda(motor):
    satirlar = [_m(i, i, f"m{i}", 9, mesafe=0.1 + i / 100) for i in range(10)]
    s = motor.ara(SahteBaglanti(list(reversed(satirlar))), "egitim", [9], "s")
    assert [p["sayfa"] for p in s["parcalar"]] == [0, 1, 2, 3]


def test_tablo_daha_yakinsa_once_gelir(motor):
    conn = SahteBaglanti([_m(1, 5, "metin", 9, mesafe=0.3)], [_t(7, 6, "Tablo A", "a — 1", 9, mesafe=0.1)])
    s = motor.ara(conn, "egitim", [9], "s")
    assert s["parcalar"][0]["tur"] == "tablo" and s["parcalar"][0]["metin"].startswith("Tablo: Tablo A.")
    assert s["parcalar"][1]["tur"] == "metin"


def test_tablo_sorgusu_patlarsa_metin_yolu_etkilenmez(motor):
    conn = SahteBaglanti([_m(1, 5, "metin", 9)], tablo_patlat=RuntimeError("tablo yok"))
    s = motor.ara(conn, "egitim", [9], "s")
    assert s["durum"] == "ok" and conn.rollback_sayisi == 1


def test_esik_altinda_zayif_ve_bos(motor):
    s = motor.ara(SahteBaglanti([_m(1, 1, "x", 9, mesafe=0.5)]), "egitim", [9], "s")
    assert s["durum"] == "zayif" and s["parcalar"] == [] and s["en_iyi_skor"] == 0.5


def test_esigin_tam_ustunde_ok(motor):
    s = motor.ara(SahteBaglanti([_m(1, 1, "x", 9, mesafe=1 - rag.ESIK_BENZERLIK)]), "egitim", [9], "s")
    assert s["durum"] == "ok"


def test_aday_yoksa_zayif(motor):
    assert motor.ara(SahteBaglanti([]), "egitim", [9], "s")["durum"] == "zayif"


def test_bos_kaynak_listesinde_DB_ye_gidilmez(motor):
    conn = SahteBaglanti([_m(1, 1, "x", 9)])
    s = motor.ara(conn, "egitim", [], "s")
    assert s["durum"] == "zayif" and conn.sorgular == []


def test_idari_kaynakta_chunk_idari_sorulur_tabloya_sorulmaz(motor):
    conn = SahteBaglanti(idari_satirlari=[_m(3, 12, "Madde 5 ...", 2)])
    s = motor.ara(conn, "idari", [2], "devamsızlık")
    assert s["durum"] == "ok" and s["parcalar"][0]["kaynak_id"] == 2
    assert not any("chunk_tablo" in q[0] or "chunk_egitim" in q[0] for q in conn.sorgular)


def test_embedding_patlarsa_hata():
    m = rag.RagMotoru(SahteEmbed(patlat=RuntimeError("x")), None)
    s = m.ara(SahteBaglanti([_m(1, 1, "x", 9)]), "egitim", [9], "s")
    assert s["durum"] == "hata" and s["parcalar"] == [] and "RuntimeError" in s["hata"]


def test_ana_sorgu_patlarsa_hata():
    conn = SahteBaglanti(patlat_sql="FROM chunk_egitim", patlat=RuntimeError("db"))
    assert rag.RagMotoru(SahteEmbed(), None).ara(conn, "egitim", [9], "s")["durum"] == "hata"


def test_ara_HICBIR_sey_yazmaz(motor):
    conn = SahteBaglanti([_m(1, 1, "x", 9)])
    motor.ara(conn, "egitim", [9], "s")
    assert conn.metrik_kayitlari() == [] and conn.soru_log_kayitlari() == []


def test_bilinmeyen_kaynak_ValueError(motor):
    with pytest.raises(ValueError):
        motor.ara(SahteBaglanti(), "kitapsiz", [1], "s")
```

- [ ] **Step 3: Başarısız olduğunu gör**

Run: `cd server && venv/bin/python -m pytest tests/test_rag_ara.py -q`
Expected: FAIL, `AttributeError: 'RagMotoru' object has no attribute 'ara'`.

- [ ] **Step 4: Uygula**

`server/rag.py`'de `TABLO_KAYNAGI = True` satırının altına ekle:

```python
# ── Open WebUI arama yolu (2026-10-03) ────────────────────────────────────
# Yeniden sıralama YOK (kullanıcı kararı C): CPU'da 20 adayın rerank'i
# medyan 9,9 sn sürdü; vektör-only recall@4 28/35 (rerank'li 32/35),
# biyoloji-9 40 soru — DECISIONS.md 2026-10-03.
# kaynak → (chunk tablosu, kaynak kolonu). SQL'e yalnızca bu beyaz
# listeden isim girer (enjeksiyon yok).
_ARAMA_TABLOLARI = {
    "egitim": ("chunk_egitim", "kitap_id"),
    "idari": ("chunk_idari", "belge_id"),
}
# Kosinüs benzerliği (1 - mesafe) eşiği — altındaysa "zayif": filtre modele
# "kaynakta bulunamadı" notu düşer (cevap yine verilir). Değer
# benchmark/recall_test.py --esik 0.55 ölçümünden (2026-08-11, %90 doğru
# tespit, biyoloji-9). Yeni kitaplarda yeniden gözden geçirilmeli.
ESIK_BENZERLIK = 0.55
```

`RagMotoru` sınıfına, `_llm_cevap`'tan hemen önce ekle:

```python
    def _aday_getir(self, conn, kaynak: str, kaynak_idler: list[int], vektor, k: int):
        tablo, kolon = _ARAMA_TABLOLARI[kaynak]
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe, {kolon}
                FROM {tablo}
                WHERE {kolon} = ANY(%s)
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, list(kaynak_idler), k),
            )
            return cur.fetchall()  # [(id, sayfa_no, metin, mesafe, kaynak_id), ...]

    def _tablo_aday_getir(self, conn, kitap_idler: list[int], vektor, k: int):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sayfa_no, baslik, metin_ozet, embedding <=> %s AS mesafe, kitap_id
                FROM chunk_tablo
                WHERE kitap_id = ANY(%s)
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, list(kitap_idler), k),
            )
            satirlar = cur.fetchall()
        sonuc = []
        for _id, sayfa, baslik, ozet, mesafe, kitap_id in satirlar:
            bas = (baslik or "").strip()
            sonuc.append((_id, sayfa, f"Tablo: {bas}. {ozet}" if bas else f"Tablo. {ozet}",
                          mesafe, kitap_id))
        return sonuc

    def ara(self, conn, kaynak: str, kaynak_idler: list[int], soru: str) -> dict:
        """Yalnızca vektör araması — LLM ve reranker YOK (Open WebUI filtresi,
        webui.py). Hiçbir tabloya YAZMAZ; loglamayı çağıran yapar. Tahta yolu
        (`sorgula`) bunu KULLANMAZ (Kural 5)."""
        if kaynak not in _ARAMA_TABLOLARI:
            raise ValueError(f"bilinmeyen kaynak: {kaynak!r}")
        bos = {"parcalar": [], "retrieval_ms": None, "rerank_ms": None, "en_iyi_skor": None}
        if not kaynak_idler:
            return {"durum": "zayif", **bos}

        t0 = time.perf_counter()
        try:
            vektor = self.embed_model.encode(soru, normalize_embeddings=True)
            # (id, sayfa, metin, mesafe, tur, kaynak_id)
            adaylar = [(c[0], c[1], c[2], c[3], "metin", c[4])
                       for c in self._aday_getir(conn, kaynak, kaynak_idler, vektor, TOP_N)]
            if kaynak == "egitim" and TABLO_KAYNAGI:
                try:
                    adaylar += [(c[0], c[1], c[2], c[3], "tablo", c[4])
                                for c in self._tablo_aday_getir(conn, kaynak_idler, vektor, TOP_N)]
                except Exception:
                    conn.rollback()
        except Exception as e:
            return {"durum": "hata", **bos, "hata": f"{type(e).__name__}: {e}"}
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        if not adaylar:
            return {"durum": "zayif", **bos, "retrieval_ms": retrieval_ms}

        secilen = sorted(adaylar, key=lambda c: c[3])[:TOP_N]
        en_iyi = round(1 - float(secilen[0][3]), 4)
        ortak = {"retrieval_ms": retrieval_ms, "rerank_ms": None, "en_iyi_skor": en_iyi}
        if en_iyi < ESIK_BENZERLIK:
            return {"durum": "zayif", "parcalar": [], **ortak}
        parcalar = [{"kaynak_id": int(c[5]), "sayfa": int(c[1]), "metin": c[2],
                     "skor": round(1 - float(c[3]), 4), "tur": c[4]} for c in secilen]
        return {"durum": "ok", "parcalar": parcalar, **ortak}
```

- [ ] **Step 5: Testleri koş**

Run: `cd server && venv/bin/python -m pytest tests/ -q`
Expected: Hepsi PASS. `test_rag.py` değişmeden geçmeli.

- [ ] **Step 6: Commit**

```bash
cd /home/ata/farabi && git add server/rag.py server/tests/conftest.py server/tests/test_rag_ara.py && git commit -m "rag: LLM'siz, rerank'siz çok kaynaklı ara() (Open WebUI için)"
```

---

### Task 3: `POST /api/webui/ara` ucu

**Files:**
- Modify: `server/auth.py` (yeni fonksiyon `webui_anahtari`)
- Create: `server/webui.py`
- Modify: `server/main.py` (router bağlama + `webui.MOTOR` ataması)
- Create: `server/tests/test_webui.py`
- Modify (gitignore'lu, içerik basılmaz): `server/config/api_keys.json` (`webui_key`)

**Interfaces:**
- Consumes: `RagMotoru.ara(conn, kaynak, kaynak_idler, soru) -> dict` (Task 2; skor = kosinüs benzerliği, reranker yok), `SahteEmbed.son_soru` (Task 2 conftest), `db.baglanti()`
- Produces:
  - HTTP: `POST /api/webui/ara`
    - Başlık: `X-Farabi-WebUI-Key`
    - Gövde: `{"kapsam": str, "soru": str, "sinif": int|null}`
    - Yanıt: `{"durum": "ok"|"zayif"|"hata", "parcalar": [{"kaynak": str, "sayfa": int, "metin": str, "skor": float}], "sure_ms": int}`
  - `kaynak` biçimi: `"Kimya 10, s. 84"`, `"Matematik 9 (2. cilt), s. 5"`, `"Ortaöğretim Kurumları Yönetmeliği, s. 12"`
  - Geçerli kapsamlar: `genel, kimya, fizik, biyoloji, matematik, edebiyat, ingilizce, felsefe, din, tarih, cografya, idari`. Bilinmeyen kapsam 400 döner.
  - `webui.sinif_cikar(soru: str) -> int | None`
  - `webui.MOTOR`: modül değişkeni, `main.py` lifespan'ında atanır

- [ ] **Step 1: Başarısız testleri yaz**

`server/tests/test_webui.py`:

```python
"""/api/webui/ara — Open WebUI arama ucu. main.app KURULMAZ (lifespan
model yükler); yalnızca webui.router bağlı küçük bir app (test_proxy.py deseni)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
import db
import rag
import webui
from conftest import SahteBaglanti, SahteEmbed

ANAHTAR = "webui-gizli"
KITAPLAR = [  # (id, sinif, ders, dosya_yolu)
    (20, 9, "Kimya", "/k/kimya_9.pdf"),
    (9, 10, "Kimya", "/k/kimya-10.pdf"),
    (27, 11, "Kimya", "/k/kimya-11.pdf"),
]


def _m(id_, sayfa, metin, kaynak_id, mesafe=0.1):
    return (id_, sayfa, metin, mesafe, kaynak_id)


@pytest.fixture
def kur(monkeypatch):
    """(istemci, baglanti) döndüren fabrika."""
    def _kur(conn: SahteBaglanti, motor=True):
        monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "tahta-anahtari"})

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(db, "baglanti", _Ctx)
        monkeypatch.setattr(webui, "MOTOR", rag.RagMotoru(SahteEmbed(), None) if motor else None)
        app = FastAPI()
        app.include_router(webui.router)
        return TestClient(app), conn
    return _kur


def _post(ist, govde, anahtar=ANAHTAR):
    h = {"X-Farabi-WebUI-Key": anahtar} if anahtar else {}
    return ist.post("/api/webui/ara", json=govde, headers=h)


class TestAuth:
    def test_basliksiz_401(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}, anahtar=None).status_code == 401

    def test_tahta_anahtari_REDDEDILIR(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}, anahtar="tahta-anahtari").status_code == 401

    def test_anahtar_tanimsizsa_herkes_401(self, kur, monkeypatch):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        monkeypatch.setattr(auth, "webui_anahtari", lambda: None)
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}).status_code == 401


class TestArama:
    def test_ok_etiketli_parca(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 84, "Mol ...", 9)], kitap_satirlari=KITAPLAR))
        y = _post(ist, {"kapsam": "kimya", "soru": "mol nedir"}).json()
        assert y["durum"] == "ok"
        assert y["parcalar"][0]["kaynak"] == "Kimya 10, s. 84"
        assert y["parcalar"][0]["metin"] == "Mol ..."

    def test_bilinmeyen_kapsam_400(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "astroloji", "soru": "x"}).status_code == 400

    def test_sinif_ifadesi_kitabi_daraltir(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "10. sınıf mol konusu için etkinlik"})
        _, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert [9] in params

    def test_kitabi_olmayan_sinif_daraltmaz(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "12. sınıf mol"})
        _, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert sorted(params[1]) == [9, 20, 27]

    def test_zayif_bos_parca(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 3, "x", 9, mesafe=0.7)], kitap_satirlari=KITAPLAR))
        y = _post(ist, {"kapsam": "kimya", "soru": "x"}).json()
        assert y["durum"] == "zayif" and y["parcalar"] == []

    def test_kapsamda_kitap_yoksa_zayif(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=[]))
        y = _post(ist, {"kapsam": "kimya", "soru": "x"}).json()
        assert y["durum"] == "zayif"
        assert not any("FROM chunk_egitim" in q[0] for q in conn.sorgular)

    def test_rag_kapaliysa_hata(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR), motor=False)
        assert _post(ist, {"kapsam": "kimya", "soru": "x"}).json()["durum"] == "hata"

    def test_db_hatasinda_hata_ve_rollback(self, kur):
        conn = SahteBaglanti(kitap_satirlari=KITAPLAR, patlat_sql="FROM kitap",
                             patlat=RuntimeError("db"))
        ist, _ = kur(conn)
        r = _post(ist, {"kapsam": "kimya", "soru": "x"})
        assert r.status_code == 200 and r.json()["durum"] == "hata"
        assert conn.rollback_sayisi >= 1

    def test_uzun_soru_2000_e_kirpilir(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "a" * 9000})
        assert len(webui.MOTOR.embed_model.son_soru) == 2000

    def test_cilt_etiketi(self, kur):
        kit = [(11, 9, "Matematik", "/k/matematik_9.pdf"), (12, 9, "Matematik", "/k/matematik_9_2.pdf")]
        ist, _ = kur(SahteBaglanti([_m(1, 5, "x", 12)], kitap_satirlari=kit))
        y = _post(ist, {"kapsam": "matematik", "soru": "x"}).json()
        assert y["parcalar"][0]["kaynak"] == "Matematik 9 (2. cilt), s. 5"

    def test_idari_belge_etiketi(self, kur):
        conn = SahteBaglanti(idari_satirlari=[_m(1, 12, "Madde", 2)],
                             idari_belge_satirlari=[(2, "Ortaöğretim Kurumları Yönetmeliği")])
        ist, _ = kur(conn)
        y = _post(ist, {"kapsam": "idari", "soru": "devamsızlık"}).json()
        assert y["parcalar"][0]["kaynak"] == "Ortaöğretim Kurumları Yönetmeliği, s. 12"


class TestLoglama:
    def test_metrik_webui_ok_yazilir_soru_log_yazilmaz(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 84, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "mol"})
        (sql, params), = conn.metrik_kayitlari()
        assert "webui_ok" in params and params[0] is None
        assert conn.soru_log_kayitlari() == []


@pytest.mark.parametrize("soru,beklenen", [
    ("10. sınıf mol", 10), ("10.sınıf", 10), ("9 sınıf", 9), ("11-A için plan", 11),
    ("12. SINIF", 12), ("mol nedir", None), ("2010 yılında", None), ("110. sayfa", None),
])
def test_sinif_cikar(soru, beklenen):
    assert webui.sinif_cikar(soru) == beklenen
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `cd server && venv/bin/python -m pytest tests/test_webui.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'webui'`.

- [ ] **Step 3: `auth.py`'ye anahtar okuyucuyu ekle**

`server/auth.py` sonuna:

```python
WEBUI_HEADER_ADI = "X-Farabi-WebUI-Key"


def webui_anahtari() -> str | None:
    """Open WebUI filtresinin anahtarı — `api_keys.json::webui_key`
    (2026-10-03). Tahta anahtarlarından AYRI: biri diğerinin ucunu açamaz.
    Yoksa None → /api/webui/ara herkese 401 (fail-closed)."""
    try:
        veri = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    deger = str(veri.get("webui_key") or "").strip()
    return deger or None
```

- [ ] **Step 4: `webui.py`'yi yaz**

`server/webui.py`:

```python
"""server/webui.py — Open WebUI Farabi modlarının kaynak arama ucu (2026-10-03).

Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.2.
Open WebUI'deki `farabi_kaynak` filtresi her kullanıcı mesajında burayı çağırır;
dönen parçalar sistem mesajına eklenir. LLM'e GİTMEZ (RagMotoru.ara).

- Erişim: 0.0.0.0 (yerel ağ, kullanıcı kararı) + `X-Farabi-WebUI-Key`
  (api_keys.json::webui_key). Tahta anahtarı burada geçmez.
- Loglama: yalnızca `metrik` (sonuc=webui_*, tahta_id NULL); `soru_log`
  tahta sorularına ayrılmış, öğretmen soruları oraya YAZILMAZ.
- Hata: her durumda 200 + durum="hata" — filtre aramasız devam eder,
  Open WebUI asla düşmez.
"""

from __future__ import annotations

import hmac
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import auth
import db

log = logging.getLogger("webui")

router = APIRouter()

MOTOR = None  # main.py lifespan'da RagMotoru atanır; None = RAG kapalı
SORU_AZAMI = 2000

# kapsam → kitap.ders değerleri (canlı DB'deki yazımla birebir, 2026-10-03)
KAPSAM_DERSLER: dict[str, list[str]] = {
    "kimya": ["Kimya"],
    "fizik": ["Fizik"],
    "biyoloji": ["Biyoloji"],
    "matematik": ["Matematik", "Temel Matematik"],
    "edebiyat": ["Türk Dili ve Edebiyatı"],
    "ingilizce": ["İngilizce"],
    "felsefe": ["Felsefe"],
    "din": ["Din Kültürü ve Ahlak Bilgisi"],
    "tarih": ["Tarih", "İnkılap Tarihi ve Atatürkçülük"],
    "cografya": ["Coğrafya"],
}
KAPSAM_DERSLER["genel"] = sorted({d for liste in KAPSAM_DERSLER.values() for d in liste})
KAPSAMLAR = set(KAPSAM_DERSLER) | {"idari"}

# "10. sınıf", "10.sınıf", "10 sınıf", "10-a" — soru .lower() edilerek aranır
# ("SINIF".lower() == "sinif"). Önünde/arkasında rakam olan sayılar (2010,
# 110) eşleşmez.
_SINIF_RE = re.compile(
    r"(?<!\d)(9|10|11|12)(?:\s*\.\s*|\s+)(?:sınıf|sinif)"
    r"|(?<!\d)(9|10|11|12)-[a-zçğıöşü](?![a-zçğıöşü])"
)


def sinif_cikar(soru: str) -> int | None:
    m = _SINIF_RE.search(soru.lower())
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def webui_anahtari_dogrula(
    x_farabi_webui_key: str | None = Header(default=None, alias=auth.WEBUI_HEADER_ADI),
) -> None:
    beklenen = auth.webui_anahtari()
    if not beklenen or not x_farabi_webui_key or not hmac.compare_digest(beklenen, x_farabi_webui_key):
        log.warning("webui authentication failure")
        raise HTTPException(status_code=401, detail="Geçersiz ya da eksik WebUI anahtarı")


class AraIstek(BaseModel):
    kapsam: str
    soru: str = Field(..., min_length=1)
    sinif: int | None = None


def _kitaplar(conn, dersler: list[str], sinif: int | None) -> dict[int, str]:
    """kitap_id → etiket öneki ("Kimya 10", "Matematik 9 (2. cilt)")."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sinif, ders, dosya_yolu FROM kitap WHERE ders = ANY(%s) ORDER BY id",
            (dersler,),
        )
        satirlar = cur.fetchall()
    if sinif is not None and any(r[1] == sinif for r in satirlar):
        satirlar = [r for r in satirlar if r[1] == sinif]
    # Aynı (sınıf, ders) birden fazla ciltse id sırasıyla "N. cilt" eklenir.
    gruplar: dict[tuple, list[int]] = {}
    for kid, snf, ders, _yol in satirlar:
        gruplar.setdefault((snf, ders), []).append(kid)
    etiketler = {}
    for (snf, ders), idler in gruplar.items():
        for sira, kid in enumerate(sorted(idler), start=1):
            ek = f" ({sira}. cilt)" if len(idler) > 1 else ""
            etiketler[kid] = f"{ders} {snf}{ek}"
    return etiketler


def _idari_belgeler(conn) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ad FROM idari_belge ORDER BY id")
        return {int(r[0]): r[1] for r in cur.fetchall()}


def _metrik_yaz(conn, sonuc: dict, toplam_ms: int) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metrik
                    (tahta_id, retrieval_ms, rerank_ms, llm_toplam_ms,
                     toplam_ms, sonuc, en_yuksek_skor)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (None, sonuc.get("retrieval_ms"), sonuc.get("rerank_ms"), None,
                 toplam_ms, f"webui_{sonuc['durum']}", sonuc.get("en_iyi_skor")),
            )
        conn.commit()
    except Exception:
        conn.rollback()


@router.post("/api/webui/ara", dependencies=[Depends(webui_anahtari_dogrula)])
def ara(istek: AraIstek):
    if istek.kapsam not in KAPSAMLAR:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen kapsam: {istek.kapsam}")
    t0 = time.perf_counter()
    if MOTOR is None:
        return {"durum": "hata", "parcalar": [], "sure_ms": 0}

    soru = istek.soru[:SORU_AZAMI]
    etiketler: dict[int, str] = {}
    with db.baglanti() as conn:
        try:
            if istek.kapsam == "idari":
                etiketler = _idari_belgeler(conn)
                kaynak = "idari"
            else:
                sinif = istek.sinif if istek.sinif is not None else sinif_cikar(soru)
                etiketler = _kitaplar(conn, KAPSAM_DERSLER[istek.kapsam], sinif)
                kaynak = "egitim"
            sonuc = MOTOR.ara(conn, kaynak, list(etiketler), soru)
        except Exception as e:
            conn.rollback()
            log.warning("webui arama hatası: %s: %s", type(e).__name__, e)
            sonuc = {"durum": "hata", "parcalar": []}
        toplam_ms = int((time.perf_counter() - t0) * 1000)
        _metrik_yaz(conn, sonuc, toplam_ms)

    parcalar = [
        {"kaynak": f"{etiketler.get(p['kaynak_id'], '?')}, s. {p['sayfa']}",
         "sayfa": p["sayfa"], "metin": p["metin"], "skor": p["skor"]}
        for p in sonuc.get("parcalar", [])
    ]
    return {"durum": sonuc["durum"], "parcalar": parcalar, "sure_ms": toplam_ms}
```

- [ ] **Step 5: Testleri koş**

Run: `cd server && venv/bin/python -m pytest tests/ -q`
Expected: Hepsi PASS.

- [ ] **Step 6: `main.py`'ye bağla**

`import ders_plani` satırının altına `import webui` ekle. `app.include_router(ders_hafizasi.router)` satırının altına şunu ekle:

```python
# Open WebUI Farabi modları (2026-10-03) — kendi anahtarıyla korunur
# (webui.webui_anahtari_dogrula), tahta auth'una bağlı DEĞİL.
app.include_router(webui.router)
```

Lifespan'da `durum["motor"] = RagMotoru(embed_model, reranker)` satırının hemen altına `webui.MOTOR = durum["motor"]` ekle.

- [ ] **Step 7: Anahtarı üret (içerik basılmadan)**

```bash
cd /home/ata/farabi/server && venv/bin/python - <<'EOF'
import json, secrets
from pathlib import Path
p = Path("config/api_keys.json")
d = json.loads(p.read_text(encoding="utf-8"))
if not d.get("webui_key"):
    d["webui_key"] = secrets.token_urlsafe(32)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("webui_key eklendi")
else:
    print("webui_key zaten var")
EOF
git -C /home/ata/farabi check-ignore -q server/config/api_keys.json && echo "gitignore OK"
```
Expected: "webui_key eklendi" ya da "zaten var", ardından "gitignore OK".

- [ ] **Step 8: Üretime al ve canlı duman testi**

```bash
sudo systemctl restart farabi-api.service
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/ready >/dev/null && break; sleep 2; done
cd /home/ata/farabi/server && venv/bin/python - <<'EOF'
import json, time, urllib.request
k = json.load(open("config/api_keys.json"))["webui_key"]
for kapsam, soru in [("kimya", "10. sınıf mol kavramı"), ("fizik", "Newton'un hareket yasaları"),
                     ("edebiyat", "divan edebiyatında gazel"), ("genel", "fotosentez")]:
    t = time.time()
    r = urllib.request.Request("http://127.0.0.1:8000/api/webui/ara",
        json.dumps({"kapsam": kapsam, "soru": soru}).encode(),
        {"Content-Type": "application/json", "X-Farabi-WebUI-Key": k})
    y = json.load(urllib.request.urlopen(r, timeout=30))
    print(kapsam, y["durum"], round(time.time()-t, 2), "sn", [p["kaynak"] for p in y["parcalar"]])
EOF
```
Beklenen:
- Dört kapsamın hepsinde `ok` dönmeli.
- Etiketler doğru branştan olmalı. Kimya'da 10. sınıf kitabı gelmeli, örneğin "Kimya 10, s. N".
- Her sorgu 1 sn'nin altında kalmalı (vektör-only; Task 0'da ~0,13 sn).
- Anahtar ekrana basılmaz; betik yalnızca okuyup kullanır.

- [ ] **Step 9: Commit**

```bash
cd /home/ata/farabi && git add server/auth.py server/webui.py server/main.py server/tests/test_webui.py && git commit -m "server: /api/webui/ara — Open WebUI kaynak arama ucu"
```

---

### Task 4: `chunk_idari` + mevzuat yükleme

**Files:**
- Create: `server/schema_idari.sql`
- Create: `server/idari_yukle.py`
- Create: `server/tests/test_idari_yukle.py`

**Interfaces:**
- Consumes: tesseract CLI (`tesseract stdin stdout -l tur+eng`), PyMuPDF (`fitz`), python-docx (`docx`), bge-m3
- Produces:
  - Tablolar: `idari_belge(id, ad, dosya_yolu UNIQUE, hash, tur, indekslendi_at)`, `chunk_idari(id, belge_id, sayfa_no, metin, embedding vector(1024))`. Task 3'teki `_idari_belgeler` ve `RagMotoru.ara(..., "idari", ...)` bunları okur.
  - Fonksiyonlar:
    - `belge_adi(yol: Path) -> str`
    - `belgeleri_listele(klasor: Path) -> list[Path]`
    - `sayfa_metinleri(yol: Path, ocr=ocr_png) -> list[tuple[int, str, bool]]` (sayfa_no, metin, ocr_mu)

- [ ] **Step 1: Şemayı yaz ve uygula**

`server/schema_idari.sql`:

```sql
-- Mevzuat/yönetmelik parçaları (2026-10-03) — Open WebUI Müdür Yardımcısı modu.
-- 2026-08-31 iptali kaldırıldı (DECISIONS.md 2026-10-03). Vektörler
-- chunk_egitim ile aynı: bge-m3, 1024 boyut, normalize.
CREATE TABLE IF NOT EXISTS idari_belge (
    id             bigserial PRIMARY KEY,
    ad             text NOT NULL,
    dosya_yolu     text NOT NULL UNIQUE,
    hash           text NOT NULL,
    tur            text NOT NULL,              -- pdf | docx | gorsel
    indekslendi_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunk_idari (
    id        bigserial PRIMARY KEY,
    belge_id  bigint NOT NULL REFERENCES idari_belge(id) ON DELETE CASCADE,
    sayfa_no  integer NOT NULL,
    metin     text NOT NULL,
    embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunk_idari_belge_id ON chunk_idari (belge_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON idari_belge, chunk_idari TO farabi;
GRANT USAGE, SELECT ON SEQUENCE idari_belge_id_seq, chunk_idari_id_seq TO farabi;
```

Run: `sudo -u postgres psql -d farabi -v ON_ERROR_STOP=1 -f /home/ata/farabi/server/schema_idari.sql`
Expected: `CREATE TABLE`, `CREATE TABLE`, `CREATE INDEX`, `GRANT`, `GRANT`. `farabi` kullanıcısının CREATE yetkisi olmadığı için `postgres` ile uygulanır.

- [ ] **Step 2: Başarısız testleri yaz**

`server/tests/test_idari_yukle.py`:

```python
"""idari_yukle.py — saf fonksiyonlar. Gerçek tesseract/bge-m3/DB'ye gitmez."""

from pathlib import Path

import docx
import fitz
import pytest

import idari_yukle as iy


def test_bilinen_dosya_adi_esleme():
    assert iy.belge_adi(Path("yazıı ve uygulamalı sınavlar yönergesi.pdf")) == \
        "Yazılı ve Uygulamalı Sınavlar Yönergesi"


def test_bilinmeyen_dosya_adi_dosya_kokunden():
    assert iy.belge_adi(Path("okul_nobet-cizelgesi.pdf")) == "Okul Nobet Cizelgesi"


def test_listeleme_alt_klasor_ve_xlsx_haric(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "b.docx").write_bytes(b"x")
    (tmp_path / "c.jpeg").write_bytes(b"x")
    (tmp_path / "d.xlsx").write_bytes(b"x")
    (tmp_path / "GUVENLIK").mkdir()
    (tmp_path / "GUVENLIK" / "e.pdf").write_bytes(b"x")
    assert [p.name for p in iy.belgeleri_listele(tmp_path)] == ["a.pdf", "b.docx", "c.jpeg"]


def test_haric_dosya_listelenmez(tmp_path):
    (tmp_path / "657DEVLET.pdf").write_bytes(b"x")
    (tmp_path / "657_devlet_memurlari_kanunu.pdf").write_bytes(b"x")
    assert [p.name for p in iy.belgeleri_listele(tmp_path)] == ["657DEVLET.pdf"]


def test_metinli_pdf_ocr_suz(tmp_path):
    yol = tmp_path / "m.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Madde 1 - Bu yonetmelik ortaogretim kurumlarini kapsar. " * 3)
    d.save(yol)
    cagri = []
    sonuc = iy.sayfa_metinleri(yol, ocr=lambda png: cagri.append(1) or "OCR")
    assert sonuc[0][0] == 1 and "Madde 1" in sonuc[0][1] and sonuc[0][2] is False
    assert cagri == []


def test_bos_pdf_sayfasi_ocr_a_gider(tmp_path):
    yol = tmp_path / "t.pdf"
    d = fitz.open()
    d.new_page()
    d.save(yol)
    sonuc = iy.sayfa_metinleri(yol, ocr=lambda png: "taranmış metin")
    assert sonuc == [(1, "taranmış metin", True)]


def test_docx_paragraf_ve_tablo(tmp_path):
    yol = tmp_path / "y.docx"
    belge = docx.Document()
    belge.add_paragraph("Sınıf rehber öğretmeni görevleri")
    t = belge.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Görev"
    t.cell(0, 1).text = "Veli toplantısı"
    belge.save(yol)
    (sayfa, metin, ocr_mu), = iy.sayfa_metinleri(yol)
    assert sayfa == 1 and "rehber" in metin and "Veli toplantısı" in metin and ocr_mu is False


def test_gorsel_dosya_ocr(tmp_path):
    yol = tmp_path / "g.jpeg"
    yol.write_bytes(b"\xff\xd8sahte")
    assert iy.sayfa_metinleri(yol, ocr=lambda b: "norm saat") == [(1, "norm saat", True)]
```

- [ ] **Step 3: Başarısız olduğunu gör**

Run: `cd server && venv/bin/python -m pytest tests/test_idari_yukle.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'idari_yukle'`.

- [ ] **Step 4: Uygula**

`server/idari_yukle.py`:

```python
#!/usr/bin/env python3
"""server/idari_yukle.py — mevzuat klasörünü chunk_idari'ye yükler (2026-10-03).

Kaynak: /mnt/farabi-data/farabi/mudur/ (ALT KLASÖRLER HARİÇ — "OKUL GÜVENLİĞİ
AYLIK RAPORLAR" kişisel veri içerebilir, bilinçli olarak dışarıda).
- PDF: PyMuPDF sayfa metni; < 50 karakterlik sayfa tesseract'a (tur+eng, 300 dpi)
- jpeg/jpg/png: tesseract, tek sayfa
- docx: python-docx paragraf + tablo hücreleri, tek "sayfa"
Parçalama benchmark/embed_kitap.py::sayfayi_boluml ile AYNI (400 token,
%15 örtüşme, sayfa sınırı aşılmaz). Hash aynıysa belge atlanır.

Kullanım (server/ dizininden):
    venv/bin/python idari_yukle.py --kuru     # yalnızca listele, DB'ye yazma
    venv/bin/python idari_yukle.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

KLASOR = Path("/mnt/farabi-data/farabi/mudur")
UZANTILAR = {".pdf", ".docx", ".jpeg", ".jpg", ".png"}
OCR_ESIK_KARAKTER = 50
CHUNK_TOKEN = 400
ORTUSME_ORANI = 0.15
MODEL_ADI = "BAAI/bge-m3"

BILINEN_ADLAR = {
    "Ortaöğretim Kurumları Yönetmeliği (22.02.2025).pdf": "Ortaöğretim Kurumları Yönetmeliği (22.02.2025)",
    "resmi yazışma kuralları.pdf": "Resmî Yazışma Kuralları",
    "türkiye yüzyılı maarif modeli.pdf": "Türkiye Yüzyılı Maarif Modeli",
    "yazıı ve uygulamalı sınavlar yönergesi.pdf": "Yazılı ve Uygulamalı Sınavlar Yönergesi",
    "zümre yönerge 23-24.pdf": "Zümre Öğretmenler Kurulu Yönergesi (2023-24)",
    "iokbs 2024.pdf": "İOKBS 2024 Kılavuzu",
    "dyk.pdf": "Destekleme ve Yetiştirme Kursları (DYK) Yönergesi",
    "ekders saatlerine ilişkin karar.pdf": "Ek Ders Saatlerine İlişkin Karar",
    "e okul kullanım rehberi.pdf": "e-Okul Kullanım Rehberi",
    "kılık-kıyafet yönetmeliği.pdf": "Kılık-Kıyafet Yönetmeliği",
    "OKUL KIYAFETLERİ YÖNETMELİĞİ.docx": "Okul Kıyafetleri Yönetmeliği",
    "sınıf reh. görevleri yönetmelik.docx": "Sınıf Rehber Öğretmeni Görevleri",
    "egzersiz yönetmeliği.pdf": "Egzersiz Yönetmeliği",
    "su verimliliği yönetmeliği.pdf": "Su Verimliliği Yönetmeliği",
    "Ders Giriş Çıkış Saatleri Çizelgesi.pdf": "Ders Giriş-Çıkış Saatleri Çizelgesi",
    "NORM BRANS SAAT.jpeg": "Norm Branş Saatleri",
    "açık lise geçiş 2023.jpeg": "Açık Liseye Geçiş (2023)",
    "08142336_25145204_sosyal_etkinlikler_yonetmeligi.pdf": "Sosyal Etkinlikler Yönetmeliği",
    "11220411_millegitimbakanligiokulailebirligiyonetmeligi.pdf": "Okul-Aile Birliği Yönetmeliği",
    "657DEVLET.pdf": "657 Sayılı Devlet Memurları Kanunu",
}
# Yüklenmeyecek dosyalar (silinmez) — 2026-10-03 kullanıcı kararı: 657'nin
# 2015 baskısı eski; güncel olan 657DEVLET.pdf (Mevzuat Bilgi Sistemi).
HARIC_DOSYALAR = {"657_devlet_memurlari_kanunu.pdf"}


def belge_adi(yol: Path) -> str:
    if yol.name in BILINEN_ADLAR:
        return BILINEN_ADLAR[yol.name]
    kelimeler = re.split(r"[\s_\-]+", yol.stem)
    return " ".join(k[:1].upper() + k[1:] for k in kelimeler if k)


def belgeleri_listele(klasor: Path) -> list[Path]:
    return sorted(p for p in klasor.iterdir()
                  if p.is_file() and p.suffix.lower() in UZANTILAR
                  and p.name not in HARIC_DOSYALAR)


def ocr_png(goruntu: bytes) -> str:
    """tesseract CLI — stdin'den görüntü, stdout'a metin. Yerel; buluta gitmez."""
    r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "tur+eng", "--dpi", "300"],
                       input=goruntu, capture_output=True, timeout=120, check=False)
    return r.stdout.decode("utf-8", errors="replace").strip()


def sayfa_metinleri(yol: Path, ocr=ocr_png) -> list[tuple[int, str, bool]]:
    uz = yol.suffix.lower()
    if uz == ".pdf":
        import fitz
        sonuc = []
        with fitz.open(yol) as d:
            for i, sayfa in enumerate(d, start=1):
                metin = sayfa.get_text().strip()
                if len(metin) >= OCR_ESIK_KARAKTER:
                    sonuc.append((i, metin, False))
                else:
                    png = sayfa.get_pixmap(dpi=300).tobytes("png")
                    sonuc.append((i, ocr(png), True))
        return sonuc
    if uz == ".docx":
        import docx
        belge = docx.Document(str(yol))
        parcalar = [p.text for p in belge.paragraphs if p.text.strip()]
        for tablo in belge.tables:
            for satir in tablo.rows:
                hucreler = [h.text.strip() for h in satir.cells if h.text.strip()]
                if hucreler:
                    parcalar.append(" | ".join(hucreler))
        return [(1, "\n".join(parcalar), False)]
    return [(1, ocr(yol.read_bytes()), True)]


def sayfayi_boluml(metin: str, tokenizer, chunk_token: int, ortusme: int) -> list[str]:
    """benchmark/embed_kitap.py::sayfayi_boluml ile BİREBİR aynı (ayrı venv/dizin
    olduğu için kopya). Değişirse ikisi birlikte değişir."""
    ids = tokenizer.encode(metin, add_special_tokens=False)
    if not ids:
        return []
    if len(ids) <= chunk_token:
        return [metin]
    adim = chunk_token - ortusme
    parcalar = []
    i = 0
    while i < len(ids):
        pencere = ids[i:i + chunk_token]
        parcalar.append(tokenizer.decode(pencere))
        if i + chunk_token >= len(ids):
            break
        i += adim
    return parcalar


def _hash(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _tur(yol: Path) -> str:
    return {".pdf": "pdf", ".docx": "docx"}.get(yol.suffix.lower(), "gorsel")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", type=Path, default=KLASOR)
    ap.add_argument("--kuru", action="store_true", help="DB'ye yazma, yalnızca listele")
    a = ap.parse_args()

    belgeler = belgeleri_listele(a.klasor)
    okunan = []
    for yol in belgeler:
        sayfalar = sayfa_metinleri(yol)
        ocrli = sum(1 for _, _, o in sayfalar if o)
        bos = [s for s, m, _ in sayfalar if not m.strip()]
        print(f"{belge_adi(yol)} | {len(sayfalar)} sayfa | OCR {ocrli} | boş {bos or '-'}")
        okunan.append((yol, sayfalar))
    if a.kuru:
        return 0

    import psycopg2
    from pgvector.psycopg2 import register_vector
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ADI)
    model = SentenceTransformer(MODEL_ADI, device="cpu")
    ortusme = int(CHUNK_TOKEN * ORTUSME_ORANI)
    conn = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    register_vector(conn)
    for yol, sayfalar in okunan:
        h = _hash(yol)
        with conn.cursor() as cur:
            cur.execute("SELECT id, hash FROM idari_belge WHERE dosya_yolu = %s", (str(yol),))
            var = cur.fetchone()
        if var and var[1] == h:
            print(f"atlandı (değişmemiş): {yol.name}")
            continue
        chunklar = [(s, p) for s, m, _ in sayfalar if m.strip()
                    for p in sayfayi_boluml(m, tokenizer, CHUNK_TOKEN, ortusme) if p.strip()]
        vektorler = model.encode([p for _, p in chunklar], normalize_embeddings=True,
                                 batch_size=16, show_progress_bar=False)
        with conn.cursor() as cur:
            if var:
                cur.execute("DELETE FROM idari_belge WHERE id = %s", (var[0],))
            cur.execute(
                "INSERT INTO idari_belge (ad, dosya_yolu, hash, tur) VALUES (%s, %s, %s, %s) RETURNING id",
                (belge_adi(yol), str(yol), h, _tur(yol)),
            )
            belge_id = cur.fetchone()[0]
            cur.executemany(
                "INSERT INTO chunk_idari (belge_id, sayfa_no, metin, embedding) VALUES (%s, %s, %s, %s)",
                [(belge_id, s, p, v) for (s, p), v in zip(chunklar, vektorler)],
            )
        conn.commit()
        print(f"yüklendi: {belge_adi(yol)} — {len(chunklar)} parça")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Testleri koş**

Run: `cd server && venv/bin/python -m pytest tests/ -q`
Expected: Hepsi PASS.

- [ ] **Step 6: Kuru çalıştırma ve gözden geçirme**

Run: `cd /home/ata/farabi/server && venv/bin/python idari_yukle.py --kuru`
Beklenen:
- 20 dosya listelenir (2026-10-03'te eklenen Sosyal Etkinlikler, Okul-Aile Birliği ve 657DEVLET dahil; eski `657_devlet_memurlari_kanunu.pdf` hariç), alt klasör ve xlsx yok.
- Egzersiz Yönetmeliği'nde 4, Su Verimliliği Yönetmeliği'nde 19 OCR'lı sayfa olur. İki jpeg OCR'lıdır.
- "boş" sütununda en fazla birkaç sayfa çıkar. Bir belgenin tümü boşsa DUR ve kullanıcıya bildir.
- **Liste, Global Constraints'teki kişisel veri kuralı gereği belge içeriği değil yalnızca istatistik basar.**

- [ ] **Step 7: Gerçek yükleme ve doğrulama**

```bash
cd /home/ata/farabi/server && time venv/bin/python idari_yukle.py
venv/bin/python -c "
import psycopg2;c=psycopg2.connect(host='127.0.0.1',dbname='farabi',user='farabi').cursor()
c.execute('select b.ad,count(*) from idari_belge b join chunk_idari ch on ch.belge_id=b.id group by 1 order by 1')
[print(r) for r in c.fetchall()]"
venv/bin/python idari_yukle.py | grep -c "atlandı"
```
Beklenen:
- 20 belge, her birinde en az 1 parça.
- İkinci çalıştırmada 20 "atlandı" satırı (tekrar çalıştırılabilirlik).

- [ ] **Step 8: Canlı arama**

```bash
cd /home/ata/farabi/server && venv/bin/python - <<'EOF'
import json, urllib.request
k = json.load(open("config/api_keys.json"))["webui_key"]
for soru in ["öğrencinin özürsüz devamsızlık sınırı kaç gün", "resmi yazıda sayı ve konu satırı nasıl yazılır",
             "ek ders ücreti hangi durumlarda ödenir"]:
    r = urllib.request.Request("http://127.0.0.1:8000/api/webui/ara",
        json.dumps({"kapsam": "idari", "soru": soru}).encode(),
        {"Content-Type": "application/json", "X-Farabi-WebUI-Key": k})
    y = json.load(urllib.request.urlopen(r, timeout=30))
    print(y["durum"], [p["kaynak"] for p in y["parcalar"]])
EOF
```
Beklenen: Üç sorunun hepsinde `ok` dönmeli. İlk soruda Ortaöğretim Kurumları Yönetmeliği, ikincisinde Resmî Yazışma Kuralları, üçüncüsünde Ek Ders Kararı belgesi ilk sırada gelmeli.

- [ ] **Step 9: Commit**

```bash
cd /home/ata/farabi && git add server/schema_idari.sql server/idari_yukle.py server/tests/test_idari_yukle.py && git commit -m "server: chunk_idari + mevzuat yükleme (OCR dahil)"
```

---

### Task 5: Open WebUI filtresi

**Files:**
- Create: `openwebui/farabi_filtre.py`
- Create: `openwebui/tests/test_filtre.py`
- Create: `openwebui/tests/conftest.py`

**Interfaces:**
- Consumes: `POST /api/webui/ara` (Task 3). Yanıt `{"durum", "parcalar": [{"kaynak", "metin", ...}]}`.
- Produces:
  - Open WebUI Function, id `farabi_kaynak`, tür filter.
  - Model meta alanlarını okur:
    - `farabi_kapsam: str | null`
    - `farabi_think: bool`
  - Sınıf `Filter`:
    - `Valves(api_url: str, api_key: str, zaman_asimi_sn: float)`
    - `async inlet(body, __model__=None, __metadata__=None) -> dict`
  - Saf yardımcılar:
    - `son_kullanici_mesaji(messages) -> str`
    - `kaynak_blogu(sonuc: dict) -> str | None`
    - `sistem_mesajina_ekle(body, blok) -> None`

- [ ] **Step 1: Başarısız testleri yaz**

`openwebui/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`openwebui/tests/test_filtre.py`:

```python
import asyncio
import time

import farabi_filtre as ff

KIMYA = {"info": {"meta": {"farabi_kapsam": "kimya", "farabi_think": False}}}
DERIN = {"info": {"meta": {"farabi_kapsam": "genel", "farabi_think": True}}}
ALMANCA = {"info": {"meta": {"farabi_kapsam": None, "farabi_think": False}}}
OK = {"durum": "ok", "parcalar": [{"kaynak": "Kimya 10, s. 84", "metin": "Mol, madde miktarı birimidir."}]}


def _govde(icerik="mol nedir", sistem=None):
    m = [{"role": "user", "content": icerik}]
    if sistem:
        m.insert(0, {"role": "system", "content": sistem})
    return {"model": "farabi-kimya", "messages": m}


def _filtre(sonuc=OK, gecikme=0.0, cagrilar=None):
    f = ff.Filter()

    def _sahte_ara(kapsam, soru):
        if cagrilar is not None:
            cagrilar.append((kapsam, soru))
        time.sleep(gecikme)
        return sonuc
    f._ara = _sahte_ara
    return f


def _calistir(f, govde, model=KIMYA, meta=None):
    return asyncio.run(f.inlet(govde, __model__=model, __metadata__=meta or {}))


def test_ok_sonucu_sistem_mesajina_eklenir():
    g = _calistir(_filtre(), _govde())
    assert g["messages"][0]["role"] == "system"
    assert "[1] Kimya 10, s. 84" in g["messages"][0]["content"]
    assert "Mol, madde miktarı birimidir." in g["messages"][0]["content"]


def test_var_olan_sistem_mesajinin_sonuna_eklenir():
    g = _calistir(_filtre(), _govde(sistem="Sen Farabi'sin."))
    assert g["messages"][0]["content"].startswith("Sen Farabi'sin.")
    assert "Kimya 10, s. 84" in g["messages"][0]["content"]
    assert len([m for m in g["messages"] if m["role"] == "system"]) == 1


def test_zayif_sonucta_genel_bilgi_notu():
    g = _calistir(_filtre({"durum": "zayif", "parcalar": []}), _govde())
    assert "bulunamadı" in g["messages"][0]["content"]


def test_hata_sonucunda_mesajlar_degismez():
    g = _calistir(_filtre({"durum": "hata", "parcalar": []}), _govde())
    assert g["messages"] == _govde()["messages"]


def test_api_ulasilamazsa_govde_degismez():
    f = ff.Filter()
    f.valves.api_url = "http://127.0.0.1:9/api/webui/ara"   # kapalı port
    f.valves.zaman_asimi_sn = 1.0
    g = _calistir(f, _govde())
    assert g["messages"] == _govde()["messages"]


def test_gorev_isteginde_arama_yapilmaz():
    c = []
    g = _calistir(_filtre(cagrilar=c), _govde(), meta={"task": "title_generation"})
    assert c == [] and g["messages"] == _govde()["messages"]


def test_kapsamsiz_modda_arama_yapilmaz_ama_think_ayarlanir():
    c = []
    g = _calistir(_filtre(cagrilar=c), _govde(), model=ALMANCA)
    assert c == [] and g["think"] is False


def test_think_varsayilani_moddan():
    assert _calistir(_filtre(), _govde())["think"] is False
    assert _calistir(_filtre(), _govde(), model=DERIN)["think"] is True


def test_kullanici_think_secimi_EZILMEZ():
    g = _govde()
    g["think"] = True
    assert _calistir(_filtre(), g)["think"] is True
    g2 = _govde()
    g2["params"] = {"think": True}
    assert "think" not in _calistir(_filtre(), g2)  # sohbet ayarı params'ta — dokunulmaz


def test_liste_icerikli_mesajdan_metin_alinir():
    c = []
    icerik = [{"type": "image_url", "image_url": {"url": "data:..."}},
              {"type": "text", "text": "bu tablodaki mol sayısı"}]
    _calistir(_filtre(cagrilar=c), _govde(icerik=icerik))
    assert c == [("kimya", "bu tablodaki mol sayısı")]


def test_son_kullanici_mesaji_aranir():
    c = []
    g = {"messages": [{"role": "user", "content": "ilk"}, {"role": "assistant", "content": "cvp"},
                      {"role": "user", "content": "ikinci soru"}]}
    _calistir(_filtre(cagrilar=c), g)
    assert c == [("kimya", "ikinci soru")]


def test_blok_azami_uzunlugu_asmaz():
    uzun = {"durum": "ok", "parcalar": [{"kaynak": f"K{i}", "metin": "x" * 5000} for i in range(4)]}
    assert len(ff.kaynak_blogu(uzun)) <= ff.BLOK_AZAMI_KARAKTER


def test_eszamanli_iki_istek_birbirini_beklemez():
    f = _filtre(gecikme=0.5)

    async def iki():
        t = time.perf_counter()
        await asyncio.gather(f.inlet(_govde(), __model__=KIMYA, __metadata__={}),
                             f.inlet(_govde(), __model__=KIMYA, __metadata__={}))
        return time.perf_counter() - t
    assert asyncio.run(iki()) < 0.9
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests/test_filtre.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'farabi_filtre'`.

- [ ] **Step 3: Uygula**

`openwebui/farabi_filtre.py`:

```python
"""
title: Farabi Kaynak Arama
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Farabi modlarında her kullanıcı mesajı için ders kitabı/mevzuat parçalarını farabi-api'den (/api/webui/ara) getirip sistem mesajına ekler; düşünme varsayılanını moddan ayarlar.
"""

# Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.4
# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Function olarak yüklenir;
# Open WebUI içinde elle düzenlenmez (kur.py her çalıştığında üzerine yazar).

import asyncio
import json
import urllib.request

from pydantic import BaseModel, Field

BLOK_AZAMI_KARAKTER = 7500  # ~2.500 token — 16k bağlamın payı

GIRIS = ("Aşağıdaki kaynak parçaları kullanıcının son mesajı için okulun arama sisteminden geldi. "
         "Yalnızca soruyla ilgiliyse kullan. Kullandığın bilginin sonunda kaynağı köşeli parantezle "
         "belirt, örneğin [Kimya 10, s. 84]. Parçalarda olmayan sayfa numarası uydurma.")
ZAYIF_NOTU = ("Not: Bu soru için ders kitaplarında ya da mevzuatta yeterince ilgili bir bölüm bulunamadı. "
              "Genel bilginle cevap verebilirsin; ama kitaba/mevzuata dayanmadığını açıkça söyle ve "
              "sayfa numarası verme.")


def son_kullanici_mesaji(messages: list) -> str:
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        icerik = m.get("content")
        if isinstance(icerik, str):
            return icerik.strip()
        if isinstance(icerik, list):
            return " ".join(p.get("text", "") for p in icerik
                            if isinstance(p, dict) and p.get("type") == "text").strip()
        return ""
    return ""


def kaynak_blogu(sonuc: dict) -> str | None:
    durum = (sonuc or {}).get("durum")
    if durum == "zayif":
        return ZAYIF_NOTU
    if durum != "ok" or not sonuc.get("parcalar"):
        return None
    blok = GIRIS
    for i, p in enumerate(sonuc["parcalar"], start=1):
        ek = f"\n\n[{i}] {p['kaynak']}\n{p['metin'].strip()}"
        if len(blok) + len(ek) > BLOK_AZAMI_KARAKTER:
            kalan = BLOK_AZAMI_KARAKTER - len(blok)
            if kalan > 200:
                blok += ek[:kalan]
            break
        blok += ek
    return blok


def sistem_mesajina_ekle(body: dict, blok: str) -> None:
    mesajlar = body.setdefault("messages", [])
    if mesajlar and mesajlar[0].get("role") == "system" and isinstance(mesajlar[0].get("content"), str):
        mesajlar[0]["content"] = mesajlar[0]["content"].rstrip() + "\n\n" + blok
    else:
        mesajlar.insert(0, {"role": "system", "content": blok})


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(default="http://127.0.0.1:8000/api/webui/ara")
        api_key: str = Field(default="")
        zaman_asimi_sn: float = Field(default=8.0)

    def __init__(self):
        self.valves = self.Valves()

    def _ara(self, kapsam: str, soru: str) -> dict | None:
        """Bloklayan HTTP çağrısı — inlet bunu asyncio.to_thread ile çağırır
        (Open WebUI'nin olay döngüsü farabi-api yavaşken donmasın)."""
        try:
            istek = urllib.request.Request(
                self.valves.api_url,
                data=json.dumps({"kapsam": kapsam, "soru": soru}).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "X-Farabi-WebUI-Key": self.valves.api_key},
            )
            with urllib.request.urlopen(istek, timeout=self.valves.zaman_asimi_sn) as r:
                return json.load(r)
        except Exception as e:
            print(f"[farabi_kaynak] arama başarısız: {type(e).__name__}: {e}")
            return None

    async def inlet(self, body: dict, __model__: dict | None = None,
                    __metadata__: dict | None = None) -> dict:
        if (__metadata__ or {}).get("task"):
            return body  # başlık/etiket gibi arka plan görevleri — arama yok

        meta = (((__model__ or {}).get("info") or {}).get("meta")) or {}
        kullanici_secti = (body.get("think") is not None
                           or (body.get("params") or {}).get("think") is not None)
        if not kullanici_secti and "farabi_think" in meta:
            body["think"] = bool(meta["farabi_think"])

        kapsam = meta.get("farabi_kapsam")
        if not kapsam:
            return body
        soru = son_kullanici_mesaji(body.get("messages"))
        if not soru:
            return body

        sonuc = await asyncio.to_thread(self._ara, kapsam, soru)
        blok = kaynak_blogu(sonuc) if sonuc else None
        if blok:
            sistem_mesajina_ekle(body, blok)
        return body
```

- [ ] **Step 4: Testleri koş**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests/test_filtre.py -q`
Expected: Hepsi PASS. `test_api_ulasilamazsa_govde_degismez` en fazla yaklaşık 1 sn sürmeli.

- [ ] **Step 5: Commit**

```bash
cd /home/ata/farabi && git add openwebui/farabi_filtre.py openwebui/tests/ && git commit -m "openwebui: farabi_kaynak inlet filtresi"
```

---

### Task 6: Promptlar ve mod tanımları

**Files:**
- Create: `openwebui/promptlar/cekirdek.md`
- Create: `openwebui/promptlar/{genel,derin,kimya,fizik,biyoloji,matematik,edebiyat,ingilizce,almanca,felsefe,din,tarih,cografya,mudur_yrd}.md`
- Create: `openwebui/modlar.json`
- Create: `openwebui/tests/test_modlar.py`

**Interfaces:**
- Produces: `modlar.json`, Task 7'deki `kur.py` tarafından okunan bir liste. Her öğe şu alanları taşır:
  ```
  {"id": str, "ad": str, "aciklama": str, "kapsam": str|null, "think": bool, "gruplar": ["Öğretmenler", "İdare"] | ["İdare"], "ek": "<dosya>.md"}
  ```
  `ek` dosyası `openwebui/promptlar/` altında bulunur.

- [ ] **Step 1: Doğrulama testini yaz**

`openwebui/tests/test_modlar.py`:

```python
import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAPSAMLAR = {"genel", "kimya", "fizik", "biyoloji", "matematik", "edebiyat", "ingilizce",
             "felsefe", "din", "tarih", "cografya", "idari", None}


def _modlar():
    return json.loads((KOK / "modlar.json").read_text(encoding="utf-8"))


def test_14_mod_benzersiz_id():
    m = _modlar()
    assert len(m) == 14 and len({x["id"] for x in m}) == 14


def test_alanlar_ve_ek_dosyalari_var():
    for x in _modlar():
        assert set(x) == {"id", "ad", "aciklama", "kapsam", "think", "gruplar", "ek"}
        assert x["kapsam"] in KAPSAMLAR
        assert (KOK / "promptlar" / x["ek"]).is_file()


def test_mudur_yrd_yalnizca_idare():
    m = {x["id"]: x for x in _modlar()}
    assert m["farabi-mudur-yrd"]["gruplar"] == ["İdare"]
    assert all(x["gruplar"] == ["Öğretmenler", "İdare"] for i, x in m.items() if i != "farabi-mudur-yrd")


def test_yalnizca_derin_dusunur():
    assert [x["id"] for x in _modlar() if x["think"]] == ["farabi-derin"]


def test_prompt_boyutu_sinirli():
    cekirdek = (KOK / "promptlar" / "cekirdek.md").read_text(encoding="utf-8")
    assert len(cekirdek) < 5000          # ~1.300 token
    for x in _modlar():
        assert len((KOK / "promptlar" / x["ek"]).read_text(encoding="utf-8")) < 1500
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests/test_modlar.py -q`
Expected: FAIL, `FileNotFoundError: .../modlar.json`.

- [ ] **Step 3: Çekirdek promptu yaz**

`openwebui/promptlar/cekirdek.md` (kaynak: `server/ollama/farabi_webui_sistem.txt`; öğrenciye yönelik kurallar çıkarıldı, kullanıcılar öğretmen ve idare):

```markdown
Sen Farabi'sin: Şehit Murat Ustaoğlu Anadolu Lisesi'nin yerel yapay zekâ asistanı. Okulun kendi sunucusunda çalışırsın ve internete bağlı değilsin. Okulun öğretmenlerine ve idaresine yardım edersin.

# Kişiliğin
- Meraklı, sabırlı, güler yüzlü ve yardımseversin; iyi bir meslektaş gibi davranırsın.
- Yeri gelince hafif bir espri yapabilirsin ama abartmazsın; ciddi konularda ciddisin.
- Herkese "sen" diye hitap edersin. Samimi ama saygılısın.
- Kendini "Farabi" olarak tanıtırsın. Hangi modelin üzerinde çalıştığın sorulursa: okulun kendi sunucusunda çalışan açık kaynak bir dil modeli olduğunu söylersin.

# Okulumuz
- 101 öğrencili bir Anadolu Lisesi: 9 derslik, 1 STEM Lab, 1 kütüphane.
- Okulumuz adını Şehit Jandarma Uzman Çavuş Murat Ustaoğlu'ndan alır. 1985'te Çankırı'nın Kurşunlu ilçesinde doğdu. 2009'da Foça'da uzman çavuşluk eğitimini alarak göreve başladı. Şırnak Gülyazı'daki 2. Jandarma Komando Tabur Komutanlığı'nda görev yaparken, 21 Ağustos 2012'de Uludere'de göreve giderken askerî servis aracının devrilmesi sonucu şehit oldu.
- Şehidimizden her zaman saygıyla söz edersin. Hakkında bu bilgilerin dışında ayrıntı uydurmazsın.
- Okulla ilgili bilmediğin konularda (ders programı, sınav tarihleri, kurallar, kişiler, etkinlikler) tahmin yürütmezsin; "Bunu bilmiyorum, okul idaresine sorabilirsin" dersin.

# Kaynaklar
- Sistem mesajında "kaynak parçaları" verildiyse cevabını öncelikle onlara dayandırırsın ve kullandığın bilginin sonunda kaynağı köşeli parantezle belirtirsin, örneğin [Kimya 10, s. 84].
- Kaynakta olmayan bir bilgiyi kaynaktaymış gibi sunmazsın; sayfa numarası uydurmazsın.
- Kaynak bulunamadığı belirtildiyse genel bilginle cevap verirsin ama bunu açıkça söylersin.

# Kurallar
- Kişisel veri: Biri öğrenci ya da başka bir kişi hakkında TC kimlik no, not, adres, telefon, sağlık veya aile bilgisi yazarsa, bu bilgileri paylaşmamasını ya da isimleri çıkararak anonimleştirmesini nazikçe hatırlatırsın.
- Siyasi ve dinî tartışmalarda tarafsız kalırsın; kendi görüşünü söylemez, farklı bakış açılarını nesnel biçimde anlatırsın.
- Kendine zarar verme, istismar, şiddet ya da zorbalık: Böyle bir durumdan söz edilirse sakin ve şefkatli olursun ve hemen okul idaresine başvurulmasını önerirsin. Acil bir tehlike varsa 112'nin aranmasını söylersin. Bu konuları geçiştirmez, şakaya vurmazsın.
- Bilgi sınırın: İnternete bağlı değilsin ve bilgilerin belli bir tarihe kadar. Güncel olaylar, tarihler, mevzuat değişiklikleri ya da sonuçlar sorulursa bundan emin olmadığını açıkça söylersin.
- Uydurmazsın: Bilmediğin bir şeyi biliyormuş gibi anlatmazsın; kaynak, alıntı, istatistik, kitap ya da sayfa numarası uydurmazsın.

# Üslup
- Türkçe konuşursun; kullanıcı başka bir dilde yazarsa o dilde cevap verirsin.
- Kısa ve net olursun; uzun anlatım gerekiyorsa başlık, madde ya da adım kullanırsın.
- Matematik ve fen sorularında çözümü adım adım gösterirsin.
```

- [ ] **Step 4: Mod eklerini yaz**

Ortak branş öğretmeni kalıbı aşağıda; her dosyada `<BRANŞ>` ve `<KİTAPLAR>` yerine aşağıdaki tablo değerleri **yazılarak** dosya oluşturulur. Bu bir kalıp; dosyalarda `<…>` kalmaz.

```markdown
# Bu sohbetteki rolün: <BRANŞ> öğretmenlerinin asistanı
- Okulun <BRANŞ> öğretmenine meslektaş gibi yardım edersin: ders planı (40 dakikalık), kazanım odaklı etkinlik, cevap anahtarlı yazılı ve quiz soruları, değerlendirme ölçütü (rubrik), çalışma kâğıdı ve kitaptan konu özeti hazırlarsın.
- Dayandığın kitaplar: <KİTAPLAR>. Sınıf düzeyi belirtilmemişse ve önemliyse sorarsın.
- Soru hazırlarken zorluk düzeyini ve soru tipini (çoktan seçmeli, açık uçlu, doğru-yanlış) belirtir, her sorunun cevabını ayrıca verirsin.
- Kitaptaki konu sırasına ve MEB müfredatına uyarsın; müfredat dışı konuyu müfredat içiymiş gibi sunmazsın.
```

| Dosya | `<BRANŞ>` | `<KİTAPLAR>` | Ek satır (kalıbın sonuna eklenir) |
|---|---|---|---|
| `kimya.md` | Kimya | Kimya 9, 10, 11 | `- Kimyasal formülleri ve tepkime denklemlerini denkleştirilmiş olarak yazarsın; birimleri her zaman belirtirsin.` |
| `fizik.md` | Fizik | Fizik 9, 10, 11 | `- Formülleri ve birimleri açıkça yazar, sayısal çözümlerde her adımı ve birim dönüşümünü gösterirsin.` |
| `biyoloji.md` | Biyoloji | Biyoloji 9, 10 | `- 11. ve 12. sınıf kitapları sistemde yok; bu düzeyde genel bilginle çalıştığını söylersin.` |
| `matematik.md` | Matematik | Matematik 9 (iki cilt), Matematik 10, Temel Matematik 11 | `- Çözümleri adım adım ve gerekçeli yazarsın; gerekiyorsa denklemleri ayrı satırlarda gösterirsin.` |
| `edebiyat.md` | Türk Dili ve Edebiyatı | Türk Dili ve Edebiyatı 9, 10, 11 | `- Metin incelemelerinde dönem, tür, şekil ve tema bilgisini ayrı başlıklarla verirsin; yazar ve eser bilgisi uydurmazsın.` |
| `ingilizce.md` | İngilizce | Waymark 9 (B1.1) | `- Öğrenci materyalini (metin, soru, diyalog) İngilizce, öğretmene açıklamayı Türkçe yazarsın; CEFR düzeyini belirtirsin.` |
| `felsefe.md` | Felsefe | Felsefe 10 | `- Filozofların görüşlerini nesnel aktarır, kendi felsefi görüşünü dayatmazsın.` |
| `din.md` | Din Kültürü ve Ahlak Bilgisi | Din Kültürü ve Ahlak Bilgisi 9 | `- Konuları MEB programı çerçevesinde bilgilendirici ve nesnel bir dille anlatırsın; vaaz ya da dinî hüküm (fetva) vermez, mezhepler ve inançlar arasında taraf tutmazsın. Tarafsızlık kuralı ders içeriğini anlatmana engel değildir, yalnızca tartışmada taraf tutmanı engeller.` |
| `tarih.md` | Tarih | Tarih 9, 10, 11 ve 12. Sınıf T.C. İnkılap Tarihi ve Atatürkçülük | `- Tarihleri ve kişileri yalnızca kaynaktan ya da emin olduğun bilgiden verirsin; olayları neden-sonuç ilişkisiyle anlatırsın.` |
| `cografya.md` | Coğrafya | Coğrafya 9, 10, 11 | `- Harita ve grafik gerektiren etkinliklerde neyin çizileceğini tarif edersin; istatistik uydurmazsın.` |

Kalıp dışındaki ekler (tam metin):

`openwebui/promptlar/genel.md`:
```markdown
# Bu sohbetteki rolün: genel asistan
- Her branştan öğretmene ve idareye yardım edersin: ders hazırlığı, soru yazma, metin düzeltme, veli bilgilendirme mesajı taslağı, toplantı notu ve benzeri işler.
- Kaynak parçaları birden fazla dersten gelebilir; yalnızca soruyla ilgili olanı kullanırsın.
```

`openwebui/promptlar/derin.md`:
```markdown
# Bu sohbetteki rolün: derin düşünen genel asistan
- Bu mod uzun ve dikkat isteyen işler içindir: kapsamlı ders planı, zor problem çözümü, uzun analiz. Cevap vermeden önce dikkatlice düşünürsün.
- Her branştan öğretmene ve idareye yardım edersin; kaynak parçalarından yalnızca soruyla ilgili olanı kullanırsın.
```

`openwebui/promptlar/almanca.md`:
```markdown
# Bu sohbetteki rolün: Almanca öğretmenlerinin asistanı
- Okulun Almanca öğretmenine meslektaş gibi yardım edersin: ders planı, etkinlik, cevap anahtarlı soru, çalışma kâğıdı, diyalog ve okuma metni hazırlarsın.
- Öğrenci materyalini Almanca, öğretmene açıklamayı Türkçe yazarsın.
- Sistemde Almanca ders kitabı yok; kitap ya da sayfa atfı yapmazsın. Hangi düzeyde (A1, A2, B1) çalışıldığı belirtilmemişse sorarsın.
```

`openwebui/promptlar/mudur_yrd.md`:
```markdown
# Bu sohbetteki rolün: müdür yardımcısının asistanı
- Okul idaresine yardım edersin: resmî yazı (Resmî Yazışma Kuralları'na uygun biçimde), tutanak, duyuru, veli bilgilendirmesi, nöbet çizelgesi, sınav ve kurul takvimi taslakları hazırlarsın.
- Mevzuat sorularında kaynak parçalarına dayanırsın ve belge adı ile sayfayı belirtirsin, örneğin [Ortaöğretim Kurumları Yönetmeliği (22.02.2025), s. 12]. Madde numarası, tarih ya da sayı uydurmazsın.
- Mevzuat değişmiş olabilir; önemli kararlarda güncel metnin MEB'in resmî kaynaklarından kontrol edilmesini önerirsin.
- Öğrenci ya da personel hakkında kişisel veri istemez, taslaklarda isim yerine yer tutucu kullanırsın: [Öğrenci Adı], [Tarih].
```

- [ ] **Step 5: `modlar.json`**

`openwebui/modlar.json`:

```json
[
  {"id": "farabi", "ad": "Farabi", "aciklama": "Genel asistan — tüm ders kitaplarından kaynak gösterir.", "kapsam": "genel", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "genel.md"},
  {"id": "farabi-derin", "ad": "Farabi – Derin Düşünme", "aciklama": "Daha yavaş, daha dikkatli: uzun plan ve zor problemler için.", "kapsam": "genel", "think": true, "gruplar": ["Öğretmenler", "İdare"], "ek": "derin.md"},
  {"id": "farabi-kimya", "ad": "Kimya Öğretmeni", "aciklama": "Kimya 9-10-11 kitaplarına dayanır.", "kapsam": "kimya", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "kimya.md"},
  {"id": "farabi-fizik", "ad": "Fizik Öğretmeni", "aciklama": "Fizik 9-10-11 kitaplarına dayanır.", "kapsam": "fizik", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "fizik.md"},
  {"id": "farabi-biyoloji", "ad": "Biyoloji Öğretmeni", "aciklama": "Biyoloji 9-10 kitaplarına dayanır.", "kapsam": "biyoloji", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "biyoloji.md"},
  {"id": "farabi-matematik", "ad": "Matematik Öğretmeni", "aciklama": "Matematik 9-10 ve Temel Matematik 11 kitaplarına dayanır.", "kapsam": "matematik", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "matematik.md"},
  {"id": "farabi-edebiyat", "ad": "Edebiyat Öğretmeni", "aciklama": "Türk Dili ve Edebiyatı 9-10-11 kitaplarına dayanır.", "kapsam": "edebiyat", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "edebiyat.md"},
  {"id": "farabi-ingilizce", "ad": "İngilizce Öğretmeni", "aciklama": "Waymark 9 kitabına dayanır.", "kapsam": "ingilizce", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "ingilizce.md"},
  {"id": "farabi-almanca", "ad": "Almanca Öğretmeni", "aciklama": "Sistemde Almanca kitabı yok — genel bilgiyle çalışır.", "kapsam": null, "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "almanca.md"},
  {"id": "farabi-felsefe", "ad": "Felsefe Öğretmeni", "aciklama": "Felsefe 10 kitabına dayanır.", "kapsam": "felsefe", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "felsefe.md"},
  {"id": "farabi-din", "ad": "Din Kültürü Öğretmeni", "aciklama": "Din Kültürü ve Ahlak Bilgisi 9 kitabına dayanır.", "kapsam": "din", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "din.md"},
  {"id": "farabi-tarih", "ad": "Tarih Öğretmeni", "aciklama": "Tarih 9-10-11 ve İnkılap Tarihi 12 kitaplarına dayanır.", "kapsam": "tarih", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "tarih.md"},
  {"id": "farabi-cografya", "ad": "Coğrafya Öğretmeni", "aciklama": "Coğrafya 9-10-11 kitaplarına dayanır.", "kapsam": "cografya", "think": false, "gruplar": ["Öğretmenler", "İdare"], "ek": "cografya.md"},
  {"id": "farabi-mudur-yrd", "ad": "Müdür Yardımcısı", "aciklama": "Mevzuat ve resmî yazışma — yalnızca idare.", "kapsam": "idari", "think": false, "gruplar": ["İdare"], "ek": "mudur_yrd.md"}
]
```

- [ ] **Step 6: Testleri koş**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests -q && grep -l "<BRANŞ>\|<KİTAPLAR>" openwebui/promptlar/*.md; echo "kalıp kalıntısı kontrolü bitti"`
Expected: Testler PASS. grep hiçbir dosya listelememeli.

- [ ] **Step 7: Commit**

```bash
cd /home/ata/farabi && git add openwebui/promptlar openwebui/modlar.json openwebui/tests/test_modlar.py && git commit -m "openwebui: Farabi çekirdek prompt + 14 mod"
```

---

### Task 7: `kur.py`: Open WebUI kurulumu + uçtan uca doğrulama

**Önkoşul (kullanıcı):**
- Open WebUI'de Yönetici Paneli → Ayarlar → Genel'den **API anahtarları** açılır, Ayarlar → Hesap'tan bir anahtar oluşturulur.
- İki ortak hesap şifresi belirlenir.
- Bunlar `openwebui/.env` dosyasına yazılır. Bu adım kullanıcı sağlamadan başlamaz.

**Files:**
- Create: `openwebui/kur.py`
- Create: `openwebui/tests/test_kur.py`
- Create (gitignore'lu): `openwebui/.env`

**Interfaces:**
- Consumes: `modlar.json`, `promptlar/*.md`, `farabi_filtre.py`, `server/config/api_keys.json::webui_key`
- Produces:
  - Open WebUI durumu:
    - Gruplar: "Öğretmenler", "İdare"
    - Hesaplar: `ogretmen@farabi.local`, `idare@farabi.local`
    - Filtre: function `farabi_kaynak` (aktif, valves dolu)
    - Modeller: 14 Farabi modu
    - Ham model: `qwen3.8:27b` gizli
    - Varsayılan model: `farabi`
    - Görev ayarları: etiket ve takip sorusu üretimi kapalı, `TASK_MODEL = "farabi"`
  - Saf fonksiyon: `model_govdesi(mod: dict, cekirdek: str, ek: str, grup_idleri: dict[str, str]) -> dict`

- [ ] **Step 1: Başarısız testleri yaz**

`openwebui/tests/test_kur.py`:

```python
import kur

MOD = {"id": "farabi-kimya", "ad": "Kimya Öğretmeni", "aciklama": "Kimya", "kapsam": "kimya",
       "think": False, "gruplar": ["Öğretmenler", "İdare"], "ek": "kimya.md"}
GRUPLAR = {"Öğretmenler": "g-ogr", "İdare": "g-idr"}


def test_model_govdesi_temel_alanlar():
    g = kur.model_govdesi(MOD, "ÇEKİRDEK", "EK", GRUPLAR)
    assert g["id"] == "farabi-kimya" and g["base_model_id"] == "qwen3.8:27b"
    assert g["name"] == "Kimya Öğretmeni" and g["is_active"] is True
    assert g["params"]["system"] == "ÇEKİRDEK\n\nEK"


def test_think_params_e_KONMAZ_meta_ya_konur():
    g = kur.model_govdesi(MOD, "c", "e", GRUPLAR)
    assert "think" not in g["params"]
    assert g["meta"]["farabi_think"] is False and g["meta"]["farabi_kapsam"] == "kimya"


def test_filtre_bagli():
    assert kur.model_govdesi(MOD, "c", "e", GRUPLAR)["meta"]["filterIds"] == ["farabi_kaynak"]


def test_grup_erisimi():
    g = kur.model_govdesi({**MOD, "gruplar": ["İdare"]}, "c", "e", GRUPLAR)
    assert g["access_grants"] == [{"principal_type": "group", "principal_id": "g-idr", "permission": "read"}]


def test_env_okuma(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# yorum\nOPENWEBUI_API_KEY=abc\nOGRETMEN_SIFRE='x y'\n\n", encoding="utf-8")
    assert kur.env_oku(p) == {"OPENWEBUI_API_KEY": "abc", "OGRETMEN_SIFRE": "x y"}
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests/test_kur.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'kur'`.

- [ ] **Step 3: Uygula**

`openwebui/kur.py`:

```python
#!/usr/bin/env python3
"""openwebui/kur.py — Farabi modlarını Open WebUI'ye kurar (tekrar çalıştırılabilir).

Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.6, §6.
Yalnızca Open WebUI'nin resmi HTTP API'si kullanılır (DB'ye doğrudan yazılmaz,
token üretilmez). Kimlik bilgileri openwebui/.env'den (gitignore'lu):
    OPENWEBUI_URL=http://127.0.0.1:80
    OPENWEBUI_API_KEY=...        # yönetici API anahtarı
    OGRETMEN_SIFRE=...           # ortak Öğretmen hesabı
    IDARE_SIFRE=...              # ortak İdare hesabı
farabi-api anahtarı server/config/api_keys.json::webui_key'den okunur.

Kullanım:  server/venv/bin/python openwebui/kur.py [--kuru]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent
TABAN_MODEL = "qwen3.8:27b"
FILTRE_ID = "farabi_kaynak"
GRUPLAR = {"Öğretmenler": "Okulun öğretmenleri (ortak hesap)", "İdare": "Okul idaresi"}
HESAPLAR = [  # (ad, e-posta, .env anahtarı, grup)
    ("Öğretmen", "ogretmen@farabi.local", "OGRETMEN_SIFRE", "Öğretmenler"),
    ("İdare", "idare@farabi.local", "IDARE_SIFRE", "İdare"),
]
MEVCUT_OGRETMENLER = ["Arzu"]  # önceden açılmış kişisel hesaplar → Öğretmenler


def env_oku(yol: Path) -> dict[str, str]:
    sonuc = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        k, v = satir.split("=", 1)
        sonuc[k.strip()] = v.strip().strip("'\"")
    return sonuc


def model_govdesi(mod: dict, cekirdek: str, ek: str, grup_idleri: dict[str, str]) -> dict:
    return {
        "id": mod["id"],
        "base_model_id": TABAN_MODEL,
        "name": mod["ad"],
        "meta": {
            "description": mod["aciklama"],
            "filterIds": [FILTRE_ID],
            "farabi_kapsam": mod["kapsam"],
            "farabi_think": bool(mod["think"]),
        },
        # think BURAYA KONMAZ: Open WebUI model parametrelerini sohbet
        # ayarlarının üzerine yazar; varsayılanı filtre (farabi_think) verir.
        "params": {"system": f"{cekirdek.strip()}\n\n{ek.strip()}"},
        "access_grants": [{"principal_type": "group", "principal_id": grup_idleri[g],
                           "permission": "read"} for g in mod["gruplar"]],
        "is_active": True,
    }


class Api:
    def __init__(self, url: str, anahtar: str, kuru: bool):
        self.url, self.anahtar, self.kuru = url.rstrip("/"), anahtar, kuru

    def __call__(self, yontem: str, yol: str, govde=None, yazma=True):
        if self.kuru and yazma and yontem != "GET":
            print(f"[kuru] {yontem} {yol}")
            return {}
        istek = urllib.request.Request(
            self.url + yol, method=yontem,
            data=None if govde is None else json.dumps(govde, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.anahtar}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=60) as r:
                veri = r.read()
                return json.loads(veri) if veri else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 404) and yontem == "GET":
                return None
            raise SystemExit(f"{yontem} {yol} → {e.code}: {e.read()[:300]!r}")


def gruplari_kur(api: Api) -> dict[str, str]:
    mevcut = {g["name"]: g["id"] for g in (api("GET", "/api/v1/groups/") or [])}
    for ad, aciklama in GRUPLAR.items():
        if ad not in mevcut:
            g = api("POST", "/api/v1/groups/create", {"name": ad, "description": aciklama})
            mevcut[ad] = (g or {}).get("id", f"<kuru:{ad}>")
            print(f"grup oluşturuldu: {ad}")
    return mevcut


def kullanici_bul(api: Api, sorgu: str) -> list[dict]:
    y = api("GET", "/api/v1/users/?" + urllib.parse.urlencode({"query": sorgu})) or {}
    return y.get("users", []) if isinstance(y, dict) else []


def hesaplari_kur(api: Api, env: dict, grup_idleri: dict[str, str]) -> None:
    for ad, eposta, env_anahtar, grup in HESAPLAR:
        bulunan = [u for u in kullanici_bul(api, eposta) if u.get("email") == eposta]
        if bulunan:
            uid = bulunan[0]["id"]
        else:
            u = api("POST", "/api/v1/auths/add",
                    {"name": ad, "email": eposta, "password": env[env_anahtar], "role": "user"})
            uid = (u or {}).get("id", f"<kuru:{eposta}>")
            print(f"hesap oluşturuldu: {eposta}")
        api("POST", f"/api/v1/groups/id/{grup_idleri[grup]}/users/add", {"user_ids": [uid]})
    for ad in MEVCUT_OGRETMENLER:
        for u in kullanici_bul(api, ad):
            if u.get("name") == ad and u.get("role") != "admin":
                api("POST", f"/api/v1/groups/id/{grup_idleri['Öğretmenler']}/users/add",
                    {"user_ids": [u["id"]]})
                print(f"mevcut hesap Öğretmenler'e eklendi: {ad}")


def filtreyi_kur(api: Api, webui_key: str) -> None:
    icerik = (KOK / "farabi_filtre.py").read_text(encoding="utf-8")
    govde = {"id": FILTRE_ID, "name": "Farabi Kaynak Arama", "content": icerik,
             "meta": {"description": "Farabi modları için kitap/mevzuat parçası ekler."}}
    var = api("GET", f"/api/v1/functions/id/{FILTRE_ID}")
    api("POST", f"/api/v1/functions/id/{FILTRE_ID}/update" if var else "/api/v1/functions/create", govde)
    simdi = api("GET", f"/api/v1/functions/id/{FILTRE_ID}") or {}
    if simdi and not simdi.get("is_active"):
        api("POST", f"/api/v1/functions/id/{FILTRE_ID}/toggle")
    api("POST", f"/api/v1/functions/id/{FILTRE_ID}/valves/update",
        {"api_url": "http://127.0.0.1:8000/api/webui/ara", "api_key": webui_key, "zaman_asimi_sn": 8.0})
    print("filtre kuruldu: farabi_kaynak")


def modelleri_kur(api: Api, grup_idleri: dict[str, str]) -> list[str]:
    cekirdek = (KOK / "promptlar" / "cekirdek.md").read_text(encoding="utf-8")
    modlar = json.loads((KOK / "modlar.json").read_text(encoding="utf-8"))
    for mod in modlar:
        ek = (KOK / "promptlar" / mod["ek"]).read_text(encoding="utf-8")
        govde = model_govdesi(mod, cekirdek, ek, grup_idleri)
        var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": mod["id"]}))
        api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", govde)
        print(f"model {'güncellendi' if var else 'oluşturuldu'}: {mod['ad']}")
    # Ham taban modeli yalnızca yönetici görsün (erişim izni boş).
    ham = {"id": TABAN_MODEL, "base_model_id": None, "name": TABAN_MODEL,
           "meta": {"description": "Ham model — yalnızca yönetici."}, "params": {},
           "access_grants": [], "is_active": True}
    var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": TABAN_MODEL}))
    api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", ham)
    return [m["id"] for m in modlar]


def ayarlari_kur(api: Api, mod_idleri: list[str]) -> None:
    cfg = api("GET", "/api/v1/configs/models") or {}
    cfg.update({"DEFAULT_MODELS": "farabi", "MODEL_ORDER_LIST": mod_idleri})
    api("POST", "/api/v1/configs/models", cfg)
    gorev = api("GET", "/api/v1/tasks/config") or {}
    gorev.update({"TASK_MODEL": "farabi", "ENABLE_TAGS_GENERATION": False,
                  "ENABLE_FOLLOW_UP_GENERATION": False})
    api("POST", "/api/v1/tasks/config/update", gorev)
    print("ayarlar: varsayılan model farabi, etiket/takip üretimi kapalı, görev modeli farabi")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yalnızca okur, yazacaklarını listeler")
    a = ap.parse_args()
    env = env_oku(KOK / ".env")
    webui_key = json.loads((KOK.parent / "server/config/api_keys.json").read_text(encoding="utf-8"))["webui_key"]
    api = Api(env.get("OPENWEBUI_URL", "http://127.0.0.1:80"), env["OPENWEBUI_API_KEY"], a.kuru)
    if api("GET", "/api/v1/auths/", yazma=False) is None:
        raise SystemExit("API anahtarı geçersiz ya da API anahtarları kapalı.")
    grup_idleri = gruplari_kur(api)
    hesaplari_kur(api, env, grup_idleri)
    filtreyi_kur(api, webui_key)
    mod_idleri = modelleri_kur(api, grup_idleri)
    ayarlari_kur(api, mod_idleri)
    print("tamam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Testleri koş**

Run: `cd /home/ata/farabi && server/venv/bin/python -m pytest openwebui/tests -q`
Expected: Hepsi PASS.

- [ ] **Step 5: `.env`'i yaz ve gitignore'u doğrula**

Kullanıcının verdiği değerlerle dosya oluşturulur; değerler ekrana basılmaz.

```bash
cd /home/ata/farabi && git check-ignore -q openwebui/.env && echo "gitignore OK" && test -f openwebui/.env && echo ".env var"
```
Expected: "gitignore OK" ve ".env var".

- [ ] **Step 6: Open WebUI DB yedeği + kuru çalıştırma**

```bash
sudo -n install -d -o ata /home/ata/yedek-openwebui
sudo -n python3 -c "
import sqlite3; s=sqlite3.connect('/opt/open-webui/data/webui.db'); d=sqlite3.connect('/home/ata/yedek-openwebui/webui-2026-10-03.db'); s.backup(d); d.close(); print('yedek tamam')"
cd /home/ata/farabi && server/venv/bin/python openwebui/kur.py --kuru
```
Beklenen:
- "yedek tamam".
- Ardından `[kuru] POST …` satırları: 2 grup, 2 hesap, 1 filtre, 15 model (14 mod + ham), 2 ayar.
- 401 ya da 404 ile çıkış olursa DUR. API anahtarı ya da uç adı yanlıştır; kullanıcıya bildir.

- [ ] **Step 7: Gerçek kurulum, ardından tekrar çalıştırılabilirlik kontrolü**

Run: `cd /home/ata/farabi && server/venv/bin/python openwebui/kur.py && server/venv/bin/python openwebui/kur.py`
Beklenen:
- İlk çalıştırmada "oluşturuldu" satırları görünür.
- İkinci çalıştırmada yalnızca "güncellendi" görünür, yeni grup ya da hesap oluşturulmaz.
- İki çalıştırma da "tamam" ile biter.

- [ ] **Step 8: Uçtan uca doğrulama**

```bash
cd /home/ata/farabi && server/venv/bin/python - <<'EOF'
import json, time, urllib.request
from pathlib import Path
import sys; sys.path.insert(0, "openwebui"); import kur
env = kur.env_oku(Path("openwebui/.env")); U = env.get("OPENWEBUI_URL", "http://127.0.0.1:80")

def istek(yol, govde=None, token=None, stream=False):
    r = urllib.request.Request(U + yol, data=None if govde is None else json.dumps(govde).encode(),
                               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return urllib.request.urlopen(r, timeout=180)

def giris(eposta, sifre):
    return json.load(istek("/api/v1/auths/signin", {"email": eposta, "password": sifre}))["token"]

ogr = giris("ogretmen@farabi.local", env["OGRETMEN_SIFRE"])
idr = giris("idare@farabi.local", env["IDARE_SIFRE"])
gor = lambda t: {m["id"] for m in json.load(istek("/api/models", token=t))["data"]}
o, i = gor(ogr), gor(idr)
print("öğretmen mudur-yrd görmüyor:", "farabi-mudur-yrd" not in o, "| ham model gizli:", "qwen3.8:27b" not in o)
print("idare mudur-yrd görüyor:", "farabi-mudur-yrd" in i)

def sor(model, soru, token, params=None):
    t0 = time.time(); ilk = None; metin = ""; dusunce = False
    g = {"model": model, "messages": [{"role": "user", "content": soru}], "stream": True}
    if params: g["params"] = params
    for satir in istek("/api/chat/completions", g, token):
        s = satir.decode().strip()
        if not s.startswith("data:") or s.endswith("[DONE]"): continue
        d = json.loads(s[5:])["choices"][0]["delta"]
        if d.get("reasoning_content") or d.get("reasoning"): dusunce = True
        if d.get("content"):
            ilk = ilk or time.time() - t0; metin += d["content"]
    return round(ilk or -1, 1), dusunce, metin

for model, soru, tok in [("farabi-kimya", "10. sınıf mol kavramını bir paragrafta özetle", ogr),
                         ("farabi-mudur-yrd", "Özürsüz devamsızlık sınırı nedir?", idr),
                         ("farabi-almanca", "A1 düzeyinde selamlaşma diyaloğu yaz", ogr)]:
    ilk, dus, m = sor(model, soru, tok)
    print(model, "ilk kelime", ilk, "sn | düşündü:", dus, "| kaynak etiketi:", "[" in m and ", s." in m)
ilk, dus, _ = sor("farabi-kimya", "mol nedir", ogr, params={"think": True})
print("sohbetten think açılınca düşündü:", dus, "| ilk kelime", ilk)
EOF
journalctl -u farabi-api.service --since "-5min" --no-pager | grep -c "POST /api/webui/ara"
```
Beklenen:
- `öğretmen mudur-yrd görmüyor: True | ham model gizli: True`, `idare mudur-yrd görüyor: True`
- `farabi-kimya`: ilk kelime < 5 sn, düşündü False, kaynak etiketi True
- `farabi-mudur-yrd`: kaynak etiketi True
- `farabi-almanca`: kaynak etiketi False (kitap yok)
- `sohbetten think açılınca düşündü: True`. **False çıkarsa:** Open WebUI'nin sohbet parametreleri gövdeye başka bir anahtarla ulaşıyordur. Filtreye geçici olarak `print(sorted(body.keys()), body.get("params"))` eklenir, `kur.py` tekrar çalıştırılır, `journalctl -u open-webui -n 50` incelenir ve `kullanici_secti` koşulu buna göre düzeltilir. Düzeltilemezse bu yetenek kullanıcıya "yalnızca Derin Düşünme modu" olarak raporlanır.
- journalctl sayısı 4 olmalı; Almanca aramaz, başlık ve etiket görevleri de aramaz. Daha büyükse görev istekleri filtreden geçiyordur: Review Focus 2.

- [ ] **Step 9: Commit**

```bash
cd /home/ata/farabi && git add openwebui/kur.py openwebui/tests/test_kur.py && git commit -m "openwebui: kur.py — gruplar, ortak hesaplar, filtre, 14 mod, ayarlar"
```

---

### Task 8: Belgeleme ve kabul

**Files:**
- Modify: `CLAUDE.md` (Güncel durum + Mimari tablosu)
- Modify: `server/CLAUDE.md` (uç tablosu, RAG notu)
- Modify: `DECISIONS.md`

- [ ] **Step 1: Kök `CLAUDE.md`**

"Güncel durum" bölümündeki `⛔ **RAG KAPALI (2026-10-03…` maddesini şununla değiştir:

```markdown
- **RAG kısmen açık (2026-10-03, ikinci karar):** `server/main.py::
  RAG_AKTIF = True` ama yalnızca bge-m3 **CPU**'da; reranker YÜKLENMEZ
  (`RERANK_YUKLE = False`, CPU'da ~10 sn/soru ölçüldü). Open WebUI Farabi
  modları (`POST /api/webui/ara`) yalnızca vektör aramasıyla çalışır;
  tahtadaki `kitap_sorusu` (`/api/egitim/question`) eskisi gibi `hata`
  döner. İki GPU Ollama'da. Ölçüm DECISIONS.md 2026-10-03.
- **Open WebUI = "Farabi" (port 80, 2026-10-03):** 14 mod (branş öğretmenleri,
  Derin Düşünme, Müdür Yardımcısı — yalnızca İdare), `farabi_kaynak` inlet
  filtresi, ortak `Öğretmen`/`İdare` hesapları. Kaynak: `openwebui/`
  (`kur.py` tekrar çalıştırılabilir; promptlar `openwebui/promptlar/`).
  Spec/plan: `docs/superpowers/{specs,plans}/2026-10-03-openwebui-farabi-modlar*`.
```

Mimari tablosuna satır ekle:

```markdown
| `open-webui` | `/opt/open-webui` (kurulum `openwebui/kur.py`) | 80 | "Farabi" sohbet arayüzü — öğretmen/idare modları, kaynaklı cevap |
```

- [ ] **Step 2: `server/CLAUDE.md`**

RAG notunu "bge-m3 CPU'da, reranker yok; question ucu hata döner" olarak güncelle ve uç tablosuna şunları ekle:

```markdown
| `webui.py` | `POST /api/webui/ara` — Open WebUI filtresinin kaynak araması (LLM yok), `X-Farabi-WebUI-Key` (`config/api_keys.json::webui_key`), yalnızca `metrik`'e `webui_*` yazar |
| `idari_yukle.py` + `schema_idari.sql` | mevzuat → `idari_belge`/`chunk_idari` (`--kuru` önce; OCR tesseract) |
```

- [ ] **Step 3: `DECISIONS.md`**

Sona ekle; köşeli parantezli alanlar Task 0 ve Task 7 Step 8'de ölçülen gerçek değerlerle doldurulur:

```markdown
## 2026-10-03 - Open WebUI Farabi modları devrede; bge-m3 CPU'da, rerank yok
- CPU ölçümü (biyoloji-9, 40 soru, 24 thread fp32): tam rerank (20 aday) recall@4 32/35 ama medyan 9,91 sn (max_length=512: 10,53 sn); rerank 8 aday 31/35 3,53 sn; vektör-only 28/35 ~0,13 sn. **Kullanıcı kararı C: yeniden sıralama yok.** `RERANK_YUKLE = False`; zayıf eşiği kosinüs 0,55 (`ESIK_BENZERLIK`, 2026-08-11 ölçümü). Tahta `question` ucu reranker'sız çalışmadığı için eskisi gibi `hata` döner.
- `/api/webui/ara` + `farabi_kaynak` filtresi + 14 mod + `chunk_idari` (20 belge, OCR'lı sayfalar dahil). Uçtan uca: farabi-kimya ilk kelime [değer] sn.
- Düşünme varsayılanı model `params`'a değil filtreye konuldu: Open WebUI model parametrelerini sohbet ayarlarının üzerine yazıyor (`utils/payload.py::apply_model_params_to_body`), yoksa sohbetteki `think` düğmesi çalışmazdı.
- Filtre görev isteklerini (`__metadata__.task`) atlar — başlık üretimi kitap araması tetiklemesin. HTTP çağrısı `asyncio.to_thread` içinde — Open WebUI olay döngüsü donmasın.
- Neden: kullanıcı kararları (spec §1). Geri dönüş: `RAG_AKTIF=False` + restart (Open WebUI modları aramasız çalışmaya devam eder).
```

- [ ] **Step 4: Son test turu**

Run: `cd /home/ata/farabi/server && venv/bin/python -m pytest tests/ -q && cd .. && server/venv/bin/python -m pytest openwebui/tests -q && .venv-tools/bin/ruff check server/webui.py server/rag.py server/idari_yukle.py server/auth.py openwebui/`
Expected:
- Testler PASS.
- Ruff'ta F821, F811 ve F632 sıfır. Dokunulan dosyalarda yeni bulgu sayısı artmamış olmalı; Kural gereği önce/sonra farkı okunur.

- [ ] **Step 5: Commit**

```bash
cd /home/ata/farabi && git add CLAUDE.md server/CLAUDE.md DECISIONS.md && git commit -m "docs: Open WebUI Farabi modları + RAG CPU"
```

- [ ] **Step 6: Kullanıcı kabul testi (otomatikleştirilmez, Kural 12)**

Kullanıcıya bildirilecekler:
1. Tahta tarafı değişmedi (`kitap_sorusu` eskisi gibi kısıtlı metne düşer); yine de bir tahtada Farabi'nin normal açıldığı fiziksel olarak denenmeli.
2. Öğretmenlere ortak hesap bilgisi ve "sohbetler ortak hesapta herkese görünür" uyarısı iletilmeli.
3. Eksik kitapların PDF'leri gelince `benchmark/embed_kitap.py` ile indekslenir; `webui.KAPSAM_DERSLER` yazımıyla eşleşmeli.
4. Push yapılmadı. Spec dosyası öğretmen adları içerdiği için commit edilmedi; karar kullanıcıda.
```

- [ ] **Step 7: Planın tamamlandığını işaretle**
```
