# SİSTEM MİMARİSİ (ARCHITECTURE)

> ⚠️ **DOĞRULANMAMIŞ — LLM üretimi (2026-10-29 toplu belge seti).** 2026-11-11 kod kontrolünde bu setteki belgelerin
> var olmayan dosyalara (`smssistemi/netgsm.py`, `server/services/stt_service.py`, `okul/rotalar/notlar.py`,
> `tahtayoklama/ziller/zil.py`) ve projede olmayan teknolojilere (Netgsm, go2rtc, Whisper, Nginx, Flask, `/home/pi`)
> atıf yaptığı görüldü. Kaynak değildir; bir bulguya göre iş yapmadan önce kodda doğrula. Esas: kök `AGENTS.md`,
> `docs/mimari.md`, `docs/runbook.md`, `DECISIONS.md`.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Kapsam:** Depodaki tüm bileşenlerin gerçek mimari yapısı ve çalışma prensipleri

---

## 1. Sistem Bağlam Diyagramı (System Context)

Aşağıdaki diyagram; kullanıcıların, donanım uç noktalarının, arka plan servislerinin ve harici sağlayıcıların Farabi ekosistemiyle nasıl etkileşime girdiğini göstermektedir.

```mermaid
flowchart TD
    subgraph KULLANICILAR["Kullanıcılar & Uç Cihazlar"]
        Ogrenci["Öğrenci & Veli (Web/Mobil)"]
        Ogretmen["Öğretmen (Web/Mobil/Pano)"]
        Yonetici["Okul Yönetimi / Müdür"]
        AkilliTahta["Sınıf Akıllı Tahtaları (PyQt6 Client)"]
        Kameralar["RTSP Sınıf Kameraları"]
    end

    subgraph AĞ_KATMANI["Giriş & Ağ Katmanı"]
        Cloudflare["Cloudflare Tunnel / Nginx Reverse Proxy"]
        KurumLAN["Okul Yerel Ağı (LAN / VLAN)"]
    end

    subgraph FARABI_SUNUCU["Farabi Merkezi Sunucu (Host & GPU)"]
        OkulApp["okul (Port 9090)<br/>FastAPI Öğrenci/Veli/Yönetim"]
        YoklamaApp["tahtayoklama (Port 80)<br/>Flask/FastAPI Dashboard & Ziller"]
        ServerAPI["server (Port 8000)<br/>FastAPI AI Asistan, STT/TTS, RAG"]
        SmsApp["smssistemi (Port 8020)<br/>FastAPI SMS Gateway"]
        KelebekApp["kelebek (Port 8050)<br/>FastAPI Sınav Dağıtım"]
        KameraSvc["kameralar<br/>go2rtc / RTSP Proxy"]
        OllamaLocal["Yerel LLM (Ollama)<br/>farabi = qwen3.8:27b, 49152 bağlam; RAG kapalı"]
    end

    subgraph HARICI_SERVISLER["Harici Entegrasyonlar"]
        GeminiAPI["Google Gemini API (2.0/2.5 Flash)"]
        NetgsmAPI["Netgsm SMS Gateway"]
        EdgeTTS["Microsoft Edge TTS / Piper"]
    end

    subgraph VERI_KATMANI["Veri Saklama Katmanı"]
        PG["PostgreSQL (okul_ana, pgvector)"]
        SQLiteDBs["SQLite DBs (okul.db, yoklama.db, sms.db...)"]
        ConfigJSON["JSON Yapılandırmalar (zil.json, ders_programi.json)"]
    end

    %% Bağlantılar
    Ogrenci -->|HTTPS| Cloudflare --> OkulApp
    Ogretmen -->|HTTPS| Cloudflare --> OkulApp
    Yonetici -->|HTTPS| Cloudflare --> OkulApp
    Yonetici -->|LAN / SSH| YoklamaApp
    AkilliTahta -->|LAN / WebSocket / HTTP| ServerAPI
    AkilliTahta -->|LAN / HTTP POST| YoklamaApp
    Kameralar -->|RTSP| KameraSvc --> YoklamaApp

    ServerAPI --> OllamaLocal
    ServerAPI --> GeminiAPI
    ServerAPI --> EdgeTTS
    SmsApp --> NetgsmAPI

    OkulApp --> PG
    OkulApp --> SQLiteDBs
    YoklamaApp --> SQLiteDBs
    YoklamaApp --> ConfigJSON
    SmsApp --> SQLiteDBs
    ServerAPI --> PG
```

---

## 2. Servisler Arası İletişim Mimarisi (Service Communication)

Farabi, monolitik bir yapıdan ziyade **gevşek bağlı çoklu mikro/modüler servisler (Multi-service Architecture)** modeliyle çalışmaktadır. Servisler arası etkileşim yöntemleri:

1. **HTTP REST API:**
   - `okul` ve `smssistemi` arasındaki veri doğrulama istekleri.
   - `tahtayoklama` paneli ile `kameralar` (RTSP snapshot) arasındaki REST çağrıları.
2. **WebSocket & WebRTC:**
   - `client` ile `server` arasında düşük gecikmeli iki yönlü ses iletimi (`/webrtc/offer`, `/ws/audio`).
   - Telemetri ve canlı durum bildirimleri (`/ws/telemetry`).
3. **Paylaşımlı Dosya Sistemi & SQLite:**
   - `tahtayoklama/dashboard/okul_ana_panel.py`, ziller ve ders programı güncellendiğinde `data/zil.json` ve `data/ders_programi.json` dosyalarını yazar; `tahtayoklama/ziller/zil.py` ve `client` bu dosyaları okur.
4. **PostgreSQL Entegrasyonu (`okul_ana`):**
   - e-Okul'dan aktarılan ana öğrenci, öğretmen, sınıf ve ders havuzu PostgreSQL üzerinde tutulur. `okul` ve `soruhavuzu` doğrudan PostgreSQL'e bağlanır.
5. **SSH / Paramiko:**
   - `tahtayoklama` paneli (`uzaktan_yonetim.py`, `uzaktan_baslat.py`), sınıflardaki akıllı tahtalara SSH üzerinden bağlanarak uzaktan komut yürütme, ekran görüntüsü alma ve yeniden başlatma işlemleri yapar.

```mermaid
sequenceDiagram
    autonumber
    actor Hoca as Öğretmen / Tahta
    participant Client as client (PyQt6 Tahta)
    participant Server as server:8000 (Farabi API)
    participant Yoklama as yoklama:80 (Dashboard)
    participant AI as Yerel Ollama / Gemini

    Hoca->>Client: "Hey Farabi, fotosentez nedir?" (Wake-word)
    Client->>Server: WebRTC Audio Stream (Opus/PCM)
    Server->>Server: Whisper STT (Ses -> Metin)
    Server->>AI: Prompt + Context (RAG / Hafıza)
    AI-->>Server: Üretilen Yanıt Metni
    Server->>Server: TTS Engine (Metin -> Ses Sentezi)
    Server-->>Client: WebRTC Audio Stream + Metin Metadata
    Client->>Hoca: Hoparlörden Sesli Yanıt

    Note over Client,Yoklama: Ders başlangıcında yoklama akışı
    Hoca->>Client: Yoklama Girişi (Öğrenci Seçimi)
    Client->>Yoklama: HTTP POST /api/yoklama/kaydet
    Yoklama->>Yoklama: SQLite yoklama.db Yazma
    Yoklama-->>Client: 200 OK (Kayıt Başarılı)
```

---

## 3. Katmanlı Mimari ve Sorumluluk Ayrımı

### 3.1. `okul/` Portalı Katman Yapısı
- **Yönlendiriciler (Routers - `okul/rotalar/`):** 33 adet rota modülü (`auth.py`, `notlar.py`, `ogrenci.py`, `ogretmen.py`, `veli.py`, `yonetim.py`, `analitik.py`, `pano.py`, `sudoku.py` vb.). Sadece HTTP istek doğrulama, yetki kontrolü ve HTTP yanıtı oluşturma sorumluluğundadır.
- **Servis Katmanı (`okul/servisler/`):** İş mantığını barındıran servisler (`rapor.py`, `not_servisi.py`, `devamsizlik_servisi.py`).
- **Veri Erişim Katmanı (`okul/db.py`):** SQLite bağlantı havuzu, migration çalıştırıcı ve PostgreSQL (`okul_ana`) bağlantı köprüsü.
- **Yardımcı Modüller (`okul/deps.py`, `okul/auth.py`):** Dependency injection, rol bazlı erişim denetimi (`Rol.OGRENCI`, `Rol.OGRETMEN`, `Rol.MUDUR`), parola hashleme.

### 3.2. `server/` Asistan Katmanı
- **API Uç Noktaları (`server/routers/`):** `chat.py`, `voice.py`, `telemetry.py`, `rag.py`.
- **Servisler (`server/services/`):**
  - `llm_service.py`: Yerel Ollama ile Gemini API arasında dinamik yük dengeleme ve fallback.
  - `stt_service.py`: Whisper tabanlı konuşmadan metne dönüştürme.
  - `tts_service.py`: Edge-TTS ve Piper yerel ses motoru.
  - `rag_service.py`: Müfredat dokümanları ve okul kuralları üzerinde vektör arama.

### 3.3. `tahtayoklama/` Operasyon Katmanı
- **Dashboard:** Flask/FastAPI tabanlı arayüz, anlık tahta durumları, ping izleme.
- **Ziller Modülü (`tahtayoklama/ziller/`):** Hafta içi/hafta sonu ders saatleri, teneffüs zilleri, anons sistemi ve MP3 çalma otomasyonu.
- **Uzaktan Yönetim:** Paramiko tabanlı asenkron/senkron SSH agent yönetimi.

---

## 4. Mimari Kararlar ve Kök Neden Analizi (ADR Özeti)

1. **Çift LLM Stratejisi (Yerel GPU + Bulut Fallback):**
   - *Karar:* Yerel Ollama iki RTX 3060 üzerinde `qwen3.8:27b` çalıştırır; istemciler modeli `farabi` takma adıyla ister (49152 bağlam, süresiz yüklü). `gemma4:12b` diskte kullanılmadan durur; RAG ve embedding servisi kalıcı kapalıdır. Tahtaların ses yolu Gemini Live, metin sağlayıcı yedekleri ise `server/saglayicilar.py` zincirleridir.
   - *Gerekçe:* İnternet bağımlılığını en aza indirmek, kurum içi öğrenci verilerini korumak (KVKK) ve sıfır API maliyeti sağlamak.
2. **PostgreSQL + SQLite Hibrit Depolama:**
   - *Karar:* Temel okul kimlikleri ve vektör verisi PostgreSQL'de (`okul_ana`); hızlı işlem gerektiren operasyonel veriler (günlük yoklama, SMS kuyrukları, sudoku skorları) alt projelerin kendi SQLite veritabanlarında saklanır.
   - *Gerekçe:* Alt projelerin birbirinden bağımsız geliştirilebilmesi ve sunucu göçlerinin kolay olması. Ancak bu durum ACID sınırları ve veri senkronizasyonu açısından teknik borç yaratmaktadır (Bkz: `docs/TECHNICAL_DEBT.md`).
3. **WebRTC Ses İletişimi:**
   - *Karar:* Akıllı tahta mikrofon ve hoparlör iletişimi HTTP yerine WebRTC (veya düşük gecikmeli WebSocket PCM) üzerinden yapılır.
   - *Gerekçe:* Sınıf ortamında öğretmen ile asistan arasındaki diyalog gecikmesini (latency) 500ms altına indirmek.
