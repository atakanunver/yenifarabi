# Farabi Project - Gemini Guide

Bu dosya `CLAUDE.md` temel alınarak Gemini için oluşturulmuştur.

## Mimari ve Sistem Özeti
- **Proje:** Sınıf akıllı tahtalarında çalışan sesli ders asistanı.
- **Client (İstemci):** `client/` dizininde çalışır. PyQt6 tabanlı, ince (thin) bir istemcidir. Kitap, PDF, YKS soruları gibi ağır işlemler sunucuya HTTP üzerinden gönderilir. Ses işlemleri Gemini Live üzerinden yürütülür.
- **Server (Sunucu):** `server/` dizininde çalışır. FastAPI tabanlıdır. RAG (pgvector+rerank+LLM), kitap içeriği/PDF render, YKS soru arama ve bulut LLM proxy işlemleri burada gerçekleşir. 2 adet NVIDIA RTX 3060 GPU'yu tam kapasite kullanır (biri Ollama, diğeri farabi-api/embedding+reranker için).
- **Veri Depolama:** `icerik`, `kitaplar`, `YKS` klasörleri artık sunucudadır (`/mnt/farabi-data/farabi/` veya belirlenen sunucu diskinde). Client tarafında yalnızca geçici, boyut sınırına sahip önbellekler tutulur. PostgreSQL ve pgvector kullanılmaktadır.

## Temel Kurallar
1. **Client ince kalmalı:** Ağır iş (RAG, LLM, kitap/plan işleme) sunucuda yapılmalıdır.
2. **Ders asla bozulmamalı:** Sunucu veya bir servis çökerse tahta normal çalışmaya devam etmeli, tam ekran hata basılmamalıdır.
3. Değişiklikler tek seferde tek modül üzerinden yapılmalı ve öncesinde ilgili dosyalar mutlaka okunmalıdır.
4. Mevcut davranış bozulmamalı, geriye dönük uyumluluk korunmalıdır.
5. Büyük yapısal (refactor) değişikliklerden veya yeni teknoloji/servis eklemeden önce (Docker, Redis, Qdrant vb.) mutlaka onay alınmalıdır.
6. `.env` dosyaları asla commit edilmez, API anahtarları doğrudan koda yazılmaz. (Sunucu tarafındaki `api_keys.json` vb. gitignore'ludur).
7. Testler atlanmamalı veya başarısız testler gizlenmemelidir.
8. Ölçüm yapmadan optimizasyona girişilmemelidir.

## RAG ve AI Kuralları
- RAG cevapları **sadece** retrieval sonucundan üretilir; modelin kendi bilgisinden serbest metin üretimi yapılmaz.
- Skor eşiğin altındaysa LLM tetiklenmez ve içeriğin bulunmadığı belirtilir.
- Çıktılarda kaynak mutlaka gösterilir (ör. `9. Sınıf Biyoloji, s. 84`).
- Ses veri işleme ve transkripsiyon Gemini Live üzerinden sağlanır ve ham ses diske yazılmaz.
- Öğrenci kimlikleri ("Anonim öğrenci sordu" şeklinde) gizli tutulur.

## Loglama
- `metrik` tablosu süresiz ve içeriksiz metrikleri tutar.
- `soru_log` tablosu sadece başarısız, yetersiz veya reddedilen içerik/cevap durumlarında detay metinlerini kaydeder. Başarılı/yüksek skorlu cevaplarda içerik metni tutulmaz. Zaman aşımıyla silinme politikası iptal edilmiştir, veriler süresiz kalır.

## Yapılmayacaklar (Yasaklı İşlemler)
- **Yerel STT/TTS (faster-whisper, Piper):** Kalıcı olarak iptal edilmiştir. Ses işlemleri Gemini Live'da kalmaya devam edecektir.
- **Faz 4 Endpoints (`/api/idari/*`):** Henüz yazılmamalıdır. İdari tablolar boş kalmalı, izolasyon sağlanmalıdır.

## Okunmaması / Dokunulmaması Gerekenler
Şu dosya ve dizinlere AI tarafından dokunulmamalıdır: `*.pdf`, `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`, `client/logs/`, `client/config/api_keys.json*`, `server/config/api_keys.json*`, `/mnt/farabi-data/farabi/`.
