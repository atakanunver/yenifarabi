# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Kapsam:** yalnızca `server/` — Farabi "Brain" (`farabi-api.service`,
FastAPI, port 8000). Mimari, kurallar, gizlilik ve RAG kuralları kök
`/home/ata/farabi/CLAUDE.md`'de; çelişkide kök kazanır. Tarihli gerekçeler
`DECISIONS.md`'de.

## Komutlar

```bash
venv/bin/uvicorn main:app --reload --port 8000             # geliştirmede elle
venv/bin/python -m pytest tests/ -q                        # testler, GPU/DB'ye dokunmaz
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest "tests/test_icerik.py::TestKitapBul" -q   # tek sınıf

sudo systemctl restart farabi-api.service   # üretime alma (bu dizin canlı üretim)
journalctl -u farabi-api.service            # tek log kaynağı — dosya log YOK
```

- Venv kurulumu: `pip install -r requirements.txt`; birebir üretim ortamı
  `requirements.lock.txt` (pytest bunun içinde). Yeni venv kurulursa okul
  ağının MEB-CERT-TTVPN sertifikası venv'in `certifi`'sine yeniden
  eklenmeli (kök CLAUDE.md, "Sunucu ortamı — tuzaklar").
- `tests/conftest.py` sahte embedding/reranker/psycopg2 bağlantısı verir
  (`RagMotoru` yapıcısı zaten enjeksiyonlu) — yeni test gerçek GPU/DB'ye
  gitmemeli, bu sahteleri kullan.
- `lifespan`, yalnız `RAG_AKTIF=True` ise açılışta ısınma embed'i çalıştırır.
  RAG kalıcı olarak kapalı olduğundan mevcut durumda bu ısınma yapılmaz.

## Yapı ve uç noktalar

> 🛑 **RAG KALICI İPTAL (2026-10-31, Atakan kararı):** `server/main.py::RAG_AKTIF = False` olarak ayarlanmıştır. Gömme ve rerank servisi `farabi-embed` (127.0.0.1:8040) bilerek durdurulmuş ve devre dışı bırakılmıştır. RAG modelini veya servisini yeniden açma/önerme. Aşağıdaki router'lar RAG modeli gerektirmez, kendi dosya/DB/anahtar kontrollerini kendileri yapar.

| Dosya | Uçlar / görev |
|---|---|
| `main.py`, `rag.py`, `db.py` | `/health`, `/ready`, `GET /api/version`, `POST /api/egitim/question` (RAG kapalı), `GET /api/egitim/kitaplar`, `POST /api/egitim/ders_kaydi_yedek` |
| `ders_gorsel.py` | `POST /api/ders-gorsel` — (31 Ekim 2026, pilot 10-A) tahta ders görseli arşivleyici (`/mnt/farabi-data/farabi/ders_gorselleri/`) |

