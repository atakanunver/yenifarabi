# VERİ AKIŞLARI (DATA FLOW)

> ⚠️ **DOĞRULANMAMIŞ — LLM üretimi (2026-10-29 toplu belge seti).** 2026-11-11 kod kontrolünde bu setteki belgelerin
> var olmayan dosyalara (`smssistemi/netgsm.py`, `server/services/stt_service.py`, `okul/rotalar/notlar.py`,
> `tahtayoklama/ziller/zil.py`) ve projede olmayan teknolojilere (Netgsm, go2rtc, Whisper, Nginx, Flask, `/home/pi`)
> atıf yaptığı görüldü. Kaynak değildir; bir bulguya göre iş yapmadan önce kodda doğrula. Esas: kök `AGENTS.md`,
> `docs/mimari.md`, `docs/runbook.md`, `DECISIONS.md`.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Kapsam:** Sistemin tüm kritik iş akışlarındaki veri üretim, iletim, işleme ve saklama adımları

---

## 1. Kritik İş Akışları Genel Bakış

Farabi platformunda veri, gerçek zamanlı telemetriden kalıcı veritabanı kayıtlarına kadar çok çeşitli hatlar üzerinden akar. 5 temel iş akışı şunlardır:

1. **Akıllı Tahta Asistanı Ses/Sohbet Akışı (Voice/AI Loop)**
2. **Sınıf Yoklama ve Devamsızlık Kayıt Akışı**
3. **SMS Gönderim ve Onay Yaşam Döngüsü**
4. **Okul Portalı Analitik ve Pano Senkronizasyonu**
5. **Kazanım Bazlı Soru Havuzu ve Sınav Kitapçığı Üretimi**

---

## 2. Akıllı Tahta Asistanı Akışı (Voice & AI Pipeline)

```mermaid
sequenceDiagram
    autonumber
    actor Hoca as Öğretmen / Öğrenci
    participant Tahta as Akıllı Tahta (client)
    participant API as Farabi API (:8000)
    participant STT as Whisper Engine
    participant LLM as Ollama / Gemini API
    participant TTS as Edge-TTS / Piper
    participant Chroma as ChromaDB / pgvector

    Hoca->>Tahta: "Hey Farabi" (Porcupine / Snowboy Wake-word)
    Tahta->>API: WebRTC / WebSocket Ses Akışı (PCM 16kHz)
    API->>STT: Ses Segmenti Gönderimi
    STT-->>API: Deşifre Edilmiş Metin ("Kurtuluş Savaşı ne zaman başladı?")
    
    API->>Chroma: Vektör Arama (Ders Kitapları / Tarih Müfredatı)
    Chroma-->>API: İlgili Ders Notu / Bağlam (Context)
    
    API->>LLM: Prompt (Sistem Talimatı + Bağlam + Soru)
    LLM-->>API: Model Yanıtı ("Kurtuluş Savaşı, 19 Mayıs 1919'da...")
    
    API->>TTS: Metin Sentezleme İsteği
    TTS-->>API: Üretilen Ses Dosyası / Byte Akışı
    API-->>Tahta: WebRTC Ses Kanalından Hoparlöre İletim
    Tahta->>Hoca: Sesli Yanıt Dinletilir + Ekranda Metin Gösterilir
```

### Teknik Detaylar:
- **Gecikme (Latency):** Ses girişinden ilk token/ses çıktısına kadar geçen hedef süre yerel GPU üzerinde 800-1200ms arasındadır.
- **Güvenlik/Gizlilik:** Ses verisi diskte saklanmaz; hafızada (RAM buffer) işlenip yok edilir.

---

## 3. Sınıf Yoklama Akışı (Attendance Lifecycle)

```mermaid
flowchart TD
    A["Öğretmen Sınıfta Tahtayı Açar"] --> B["client/ Uygulaması Dersi ve Sınıf Listesini Yükler"]
    B --> C["Öğretmen Gelmeyen Öğrencileri İşaretler"]
    C --> D["HTTP POST /api/yoklama/kaydet -> tahtayoklama (:80)"]
    D --> E["yoklama.db (SQLite) Tablosuna Yazılır (saat, sinif, ogrenci_no)"]
    E --> F["Müdür/Yönetim Dashboard Ekranında Canlı Güncellenir"]
    E --> G{"Devamsızlık Bildirimi Gerekiyor mu?"}
    G -->|Evet| H["smssistemi Taslak Havuzuna Otomatik Düşer"]
    H --> I["İdareci Onayı ile Netgsm Üzerinden Veliye SMS Gider"]
    G -->|Hayır| J["Arşivlenir / Gün Sonu Raporuna Eklenir"]
```

---

## 4. SMS Gönderim ve Yaşam Döngüsü (SMS Pipeline)

```mermaid
stateDiagram-v2
    [*] --> TASLAK: Şablon veya Devamsızlık Tetiklemesi
    TASLAK --> BEKLEMEDE: İdareci Gönderim Emri Verdi
    BEKLEMEDE --> GONDERILIYOR: smssistemi Netgsm API İsteği Attı
    GONDERILIYOR --> BASARILI: Netgsm 200 OK + Görev ID Döndü
    GONDERILIYOR --> HATALI: Bakiye Yetersiz / Geçersiz Numara / Ağ Hatası
    HATALI --> TASLAK: Tekrar Deneme (Retry)
    BASARILI --> ILETILDI: Operatör DLR Raporu Geldi
    ILETILDI --> [*]
```

### Kritik Nokta:
- SMS gönderimlerinde TOCTOU (Time-of-Check to Time-of-Use) zafiyetini önlemek amacıyla taslak durumunun asenkron iş parçacığı başlatılmadan önce `ISLENIYOR` olarak kilitlenmesi gerekmektedir (Bkz: `docs/SECURITY_AUDIT.md` ve `docs/CODE_QUALITY_AUDIT.md`).

---

## 5. Okul Portalı Analitik ve Pano Senkronizasyonu

```mermaid
flowchart LR
    subgraph KULLANICI_ETKILESIMI["Portal Etkileşimi"]
        Kullanici["Öğrenci / Öğretmen"] -->|Sayfa Ziyareti / Not Girişi| OkulApp["okul (FastAPI)"]
    end

    subgraph BUFFER_KATMANI["Analitik Arabellek (RAM)"]
        OkulApp -->|Middleware: analitik_kaydet| EventBuffer["Queue / RAM Buffer (25 Olay)"]
    end

    subgraph VERI_TABANI["Kalıcı Depolama"]
        EventBuffer -->|Flush (Her 5s / 25 Olayda Bir)| SQLiteAnalitik[("okul.db: analitik_olaylar")]
        OkulApp -->|Doğrudan Sorgu / Cache| SQLiteOkul[("okul.db: notlar, devamsizlik")]
    end

    subgraph DIJITAL_PANO["Koridor Dijital Panoları"]
        Pano["TV / Pano İstemcisi"] -->|GET /api/pano| OkulApp
        OkulApp -->|Nöbetçi Öğretmen, Günün Menüsü, Kutlamalar| Pano
    end
```

---

## 6. Soru Havuzu ve Sınav Kitapçığı Üretimi (Exam Generation)

1. **Girdi:** Öğretmen veya yönetici web arayüzünden ders, ünite, kazanım kodu (`KAZ_10_MAT_01`) ve zorluk derecesi seçer.
2. **Sorgu:** `soruhavuzu`, PostgreSQL `okul_ana` üzerindeki pgvector vektör alanından semantik benzerlik ve kazanım filtresi ile en uygun $N$ adet soruyu çeker.
3. **Derleme:** `kazanimtest` servisi ReportLab motorunu çalıştırarak A4 formatında, çift sütunlu, okul logolu ve karekodlu öğrenciye özel PDF sınav kitapçığı üretir.
4. **Çıktı:** PDF dosyası `/static/sinavlar/` dizininde oluşturulur ve kullanıcıya indirme bağlantısı döndürülür.
