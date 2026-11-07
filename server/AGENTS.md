# Server (farabi-api)
Farabi "Brain": FastAPI, `farabi-api.service`, port 8000, `server/` dizini. Kök kurallar (gizlilik, canlı üretim) kök AGENTS.md'de; çelişkide kök kazanır.

## Komutlar
```bash
venv/bin/uvicorn main:app --reload --port 8000             # geliştirmede elle
venv/bin/python -m pytest tests/ -q                        # GPU/DB'ye dokunmaz
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest "tests/test_icerik.py::TestKitapBul" -q   # tek sınıf
sudo systemctl restart farabi-api.service   # üretime alma (bu dizin canlı üretim)
journalctl -u farabi-api.service            # tek log kaynağı — dosya log YOK
```
- Venv: `pip install -r requirements.txt`; birebir üretim ortamı `requirements.lock.txt` (pytest içinde). Yeni venv'de okul ağının MEB-CERT-TTVPN sertifikası `certifi`'ye eklenmeli.
- `tests/conftest.py` sahte embedding/reranker/psycopg2 verir; yeni test gerçek GPU/DB'ye gitmemeli, bu sahteleri kullan.

## Kurallar
- 🛑 RAG KALICI İPTAL (2026-10-31): `main.py::RAG_AKTIF = False`; `farabi-embed` (127.0.0.1:8040) bilerek kapalı. RAG'ı/servisi yeniden açma, önerme. `/api/egitim/question` RAG kapalı çalışır.
- Aşağıdaki router'lar RAG gerektirmez; kendi dosya/DB/anahtar kontrollerini yapar.

## Uç noktalar
- `main.py`, `rag.py`, `db.py`: `/health`, `/ready`, `GET /api/version`, `POST /api/egitim/question`, `GET /api/egitim/kitaplar`, `POST /api/egitim/ders_kaydi_yedek`.
- `ders_gorsel.py`: `POST /api/ders-gorsel` — tahta ders görseli arşivleyici (pilot 10-A), arşiv `/mnt/farabi-data/farabi/ders_gorselleri/`; tahta auth, AI yok.
