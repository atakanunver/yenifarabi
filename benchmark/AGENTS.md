# Benchmark
`benchmark/`: eski RAG ölçüm harness'ları + kitap/tablo/kazanım yükleyicileri. Servis değil, pytest'e bağlı değil; her script bağımsız CLI (`--help`). RAG KALICI İPTAL (2026-10-31): yeni RAG işi/geri açma yok; ayrıntı `docs/mimari.md` §5–§8.

## ⚠️ İsmine rağmen hepsi salt-okunur DEĞİL
| Tür | Script | Yazdığı yer |
|---|---|---|
| **Üretim DB'sine YAZAR** | `embed_kitap.py`, `embed_tablo.py`, `kazanim_test_yukle.py`, `ogretim_program_yukle.py` | canlı PostgreSQL/pgvector (`chunk_egitim`, `chunk_tablo`, `kazanim_test_soru`, `kazanim`) — `farabi-api`'nin okuduğu DB |
| Ölçüm (DB'ye yazmaz) | `rag_test.py`, `recall_test.py`, `katman_test.py`, `model_karsilastir.py` | `reports/*.json` |
| Taslak | `soru_taslak.py` | `sorular_taslak.json` — ground truth DEĞİL, öğretmen onayından önce `recall_test.py`'ye verilmez |
| Saf mantık | `*_parse.py`, `ortak.py` | — |
- Yükleyicileri çalıştırmadan önce kullanıcıya sor.

## Komutlar
`benchmark/venv` kurulu; `requirements.txt` YOK, yalnız `requirements.lock.txt` (`venv/bin/pip install -r requirements.lock.txt`).
```bash
venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1              # gerçek server/rag.py'ye karşı
venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1 --llm-atla   # yalnız retrieval/rerank/eşik
venv/bin/python rag_test.py --karsilastir onceki.json sonraki.json
venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1           # Recall@4 / MRR, rapor reports/<zaman>.json
venv/bin/python katman_test.py --rapor reports/<recall>.json --esik-rerank 0.5
venv/bin/python model_karsilastir.py --limit 5                               # qwen2.5:14b vs başka Ollama modeli
```

## Bilinmesi gerekenler
- `rag_test.py` esas: `server/rag.py::RagMotoru`'yu import eder; `recall_test.py`/`katman_test.py` pipeline'ı yeniden uygular. Sonuçlar ayrışırsa `rag_test.py`'ye güven. DB bağlantısını sarar: SELECT geçer, INSERT yutulur (`metrik`/`soru_log` kirlenmez).
- Modeller CPU'da (`torch 2.13.0+cpu`); GPU'ya dokunmaz, ders sırasında koşabilir. Doğruluk geçerli, gecikme rakamları üretimi temsil etmez (üretim gecikmesi: `metrik` tablosu).
- `sentence-transformers`/`transformers`/`pgvector`/`psycopg2` sürümleri server'la birebir aynı kalmalı.
- `sorular.json` insan onaylı set; `sorular.json.bak` ve `sorular_taslak.json` değil.
