# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Kapsam:** `benchmark/` — RAG ölçüm harness'ları + kitap/tablo/kazanım
yükleyicileri. Servis değil, pytest'e bağlı değil; her script bağımsız CLI
(`--help`). RAG kuralları ve 40 soruluk ölçüm zorunluluğu kök
`CLAUDE.md`'de, ayrıntılı mimari `docs/mimari.md` §5–§8.

## ⚠️ İsmine rağmen hepsi salt-okunur DEĞİL

| Tür | Script | Yazdığı yer |
|---|---|---|
| **Üretim DB'sine YAZAR** | `embed_kitap.py`, `embed_tablo.py`, `kazanim_test_yukle.py`, `ogretim_program_yukle.py` | canlı PostgreSQL/pgvector (`chunk_egitim`, `chunk_tablo`, `kazanim_test_soru`, `kazanim`) — `farabi-api`'nin okuduğu DB |
| Ölçüm (DB'ye yazmaz) | `rag_test.py`, `recall_test.py`, `katman_test.py`, `model_karsilastir.py` | `reports/*.json` |
| Taslak | `soru_taslak.py` | `sorular_taslak.json` — ground truth DEĞİL, öğretmen onayından önce `recall_test.py`'ye verilmez |
| Saf mantık | `*_parse.py`, `ortak.py` | — |

Yükleyicileri çalıştırmadan önce kullanıcıya sor. Yeni kitap yüklendiyse
ölçüm (`rag_test.py`, 40 soruluk set, şu an 38/40) tekrarlanmalı.

## Komutlar

`benchmark/venv` kurulu; `requirements.txt` YOK, yalnızca
`requirements.lock.txt` (yeniden kurulum: `venv/bin/pip install -r
requirements.lock.txt`).

```bash
venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1              # gerçek server/rag.py'ye karşı
venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1 --llm-atla   # yalnızca retrieval/rerank/eşik
venv/bin/python rag_test.py --karsilastir onceki.json sonraki.json
venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1           # Recall@4 / MRR, rapor reports/<zaman>.json
venv/bin/python katman_test.py --rapor reports/<recall>.json --esik-rerank 0.5
venv/bin/python model_karsilastir.py --limit 5                               # qwen2.5:14b vs başka Ollama modeli
```

## Bilinmesi gerekenler

- **`rag_test.py` esas.** Üretimin `server/rag.py::RagMotoru`'sunu import
  eder; `recall_test.py`/`katman_test.py` pipeline'ı kendileri yeniden
  uygular. Sonuçlar ayrışırsa `rag_test.py`'ye güven. `rag_test.py` DB
  bağlantısını sarar: SELECT'leri geçirir, INSERT'leri yutar (`metrik`/
  `soru_log` kirlenmez).
- **Modeller CPU'da** (`torch 2.13.0+cpu`, sürüm server'la aynı, derleme
  farklı). GPU'ya dokunmaz, ders sırasında bile koşabilir. Doğruluk
  metrikleri geçerli; **gecikme rakamları üretimi temsil etmez** (üretim
  gecikmesi için `metrik` tablosu).
- `sentence-transformers`/`transformers`/`pgvector`/`psycopg2` sürümleri
  server'la birebir aynı tutulmalı — ölçümün üretimi temsil etmesi buna
  bağlı (lock dosyasının başlığı).
- `sorular.json` insan onaylı soru seti; `sorular.json.bak` ve
  `sorular_taslak.json` değil.
