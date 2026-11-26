# Server (farabi-api)

Farabi'nin merkezi backend ve "Brain" API servisi. Akıllı tahtaların eğitsel sorgularını (kitap içeriği, YKS soruları, MEB kazanımları, PDF görsel/metin render), Atos (AnythingLLM) veri/wiki entegrasyonlarını, tahta istemci durumlarını ve ders görseli arşivini yönetir.

- Servis: `farabi-api.service` (systemd, port 8000, `server/` dizini)
- Framework: FastAPI + Uvicorn
- Teknoloji: Python 3.14 / 3.11, PostgreSQL (`farabi`, `~/.pgpass`), PyMuPDF (fitz), Pillow, httpx, pydantic

## Komutlar
```bash
venv/bin/uvicorn main:app --reload --port 8000             # geliştirmede yerel
venv/bin/python -m pytest tests/ -q                        # tüm testler (GPU/DB mock'lu, 299 test)
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest tests/test_icerik.py::TestKitapBul -q   # tek sınıf/test
sudo systemctl restart farabi-api.service                  # üretime alma (canlı kod restart ile yayına girer)
journalctl -u farabi-api.service -f                        # servis logları (tek log kaynağı, dosya logu yok)
```
- Venv: `pip install -r requirements.txt`; kilitli üretim ortamı `requirements.lock.txt`.
- MEB Sertifikası: Okul ağında MEB-CERT-TTVPN sertifikası `certifi` deposuna eklenmeli, `HF_HUB_OFFLINE=1`.
- `tests/conftest.py`: Sahte embedding, reranker ve psycopg2 mock'ları sağlar; gerçek GPU/DB'ye gitmez.

## Önemli Dosyalar ve Sorumlulukları
| Dosya | Sorumluluk |
|---|---|
| `main.py` | FastAPI uygulama girişi, yaşam döngüsü, temel sağlık/sürüm uçları ve router montajı |
| `auth.py` | Tahta (`X-Farabi-Board-Key`) ve WebUI (`X-Farabi-WebUI-Key`) kimlik doğrulama mekanizmaları |
| `icerik.py` | Ders kitabı/içerik arama, PDF sayfa render (PNG) ve sayfa metni çıkarma |
| `yks.py` | TYT/AYT çıkmış sorular ve deneme soruları arama motoru |
| `kazanim.py` | MEB müfredat ve Maarif modeli ders/hafta kazanım sorgulama |
| `proxy.py` | Ollama LLM proxy (`farabi` takma adı ile model yönlendirme) |
| `ders_plani.py` | Öğretmen ve tahta için ders planı oluşturma uçları |
| `dosya.py` | Dosya işleme (OCR / metin çıkarma) ve geçici indirme yönetimi |
| `client_durum.py` | Tahta istemci nabız (heartbeat) toplama ve tahta durum listesi |
| `ders_hafizasi.py` | Tahta ders bağlamı ve hafıza kaydı |
| `ders_gorsel.py` | Tahtalardan gelen ders ekran görüntüsü arşivleme (`/mnt/farabi-data/farabi/ders_gorselleri/`) |
| `belge_arsiv.py` | Atos kalıcı belge arşivleme (`/api/webui/belge-kaydet`, `/api/webui/belge-oku`) |
| `ogrenci_durum.router` | Atos Öğrenci Bilgi Formu özel durum tablosu sorguları |
| `hafiza.py` | Atos okul hafızası uçları (`/api/webui/hafiza/*`) |
| `atos_wiki.py` | Atos wiki kayıtlı tablo ve metin saklama uçları (`/api/webui/wiki/*`) |
| `db.py` | PostgreSQL bağlantı havuzu ve veritabanı yardımcıları |
| `version.py` | API sürüm tanımları (`VERSION`, `major_version`) |

## Uç Noktalar (API)
- **Temel & Sistem:**
  - `GET /health` → Sistem sağlığı (`status`, `version`, `rag_aktif`)
  - `GET /ready` → Hazır olma durumu
  - `GET /api/version` → Sürüm bilgisi
- **Eğitim & Tahta (`X-Farabi-Board-Key` ile korunur):**
  - `POST /api/egitim/question` → Soru cevaplama (RAG kapalı, doğrudan yanıt)
  - `GET /api/egitim/kitaplar` → Yüklü ders kitapları listesi
  - `POST /api/egitim/ders_kaydi_yedek` → Tahta ders transcript yedeği
  - `POST /api/egitim/ders_icerigi` → Konu/içerik arama
  - `GET /api/egitim/pdf_sayfa` → Belirtilen kitabın sayfa görseli (PNG)
  - `GET /api/egitim/pdf_sayfa_metni` → PDF sayfa metni
  - `POST /api/egitim/yks_sorulari` → YKS soru sorgusu
  - `GET /api/egitim/kazanim` → Sınıf, ders ve haftaya göre kazanım
  - `POST /api/egitim/ders_plani` → Ders planı isteği
  - `POST /api/egitim/dosya_isle` & `GET /api/egitim/dosya_indir/{request_id}/{dosya_adi}` → Dosya işleme
  - `POST /api/egitim/ders_hafizasi` → Ders hafızası sorgu/kayıt
- **İstemci Durumu & Görsel:**
  - `POST /api/client/heartbeat` & `GET /api/client/durum` → Tahta nabızları
  - `POST /api/ders-gorsel` → Tahta ekran görüntüsü arşivi (pilot 10-A, AI yok)
- **Atos / WebUI (`webui_anahtari_dogrula` ile korunur):**
  - `POST /api/webui/belge-kaydet`, `/api/webui/belge-oku`
  - `POST /api/webui/hafiza/{kaydet,ara,unut,getir}`
  - `POST /api/webui/wiki/{kaydet,liste,ara,getir,yaz,sabit,pdf-tablo,metin}`

## Güvenlik ve Kod Değiştirirken Dikkat Edilecekler
1. 🛑 **RAG KALICI İPTAL (2026-10-31):** `main.py::RAG_AKTIF = False`; `farabi-embed` servisi kapalıdır. RAG'ı yeniden açma veya önerme.
2. **Tahta Auth:** `/api/egitim/*` rotalarında `X-Farabi-Board-Key` zorunludur (`auth.py::tahta_anahtari_dogrula`).
3. **Kişisel Veri:** Öğrenci kimlik bilgileri buluta veya harici LLM'lere gönderilmez. Loglarda içerik veya isim tutulmaz.
4. **LLM Çağrıları:** Yerel Ollama (`farabi` modeli) kullanılır. Çağrılarda `think: false` gönderilir.
5. **Geriye Dönük Uyum:** Tahtalardaki `client` kodu bu API sözleşmesine bağlıdır; yanıt şemalarını (`status`, `answer`, `sources`, `request_id`) bozma.
