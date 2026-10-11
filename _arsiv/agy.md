# Farabi Sistemi — Yapılan İşler Raporu (AGY)

**Tarih:** 5 Ekim 2026  
**Durum:** Tamamlandı & Canlıda Doğrulandı  
**Toplam Test Kapsamı:** 582 / 582 Başarılı Test (%100 Geçti)

---

## 1. Open WebUI & RAG Sistemi Düzeltmeleri (Mevzuat & Öğretmen/İdare Asistanlığı)

### Tespit Edilen Problem ve Kök Nedenler
* **Yüksek Benzerlik ve Reranker Eşikleri:** `server/rag.py` içindeki vektör aday eşiği (`esik=0.55`) ve `server/webui.py` içindeki yeniden sıralayıcı eşiği (`ESIK_RERANK_WEBUI = 0.50`), mevzuat metinleri için aşırı kısıtlayıcıydı. 657 DMK, KHK ve yönetmelik sorgularında ilgili metin parçalarının kosinüs benzerliği 0.45–0.53 aralığında kaldığından sistem tarafından eleniyor ve modele `zayif` (boş RAG) gidiyordu.
* **Persona & Sistem Rolü Yanılgısı:** Open WebUI filtre (`farabi_filtre.py`) ve sistem promptlarında model, kaynak bulamadığında "kitaplarda/mevzuatta yeni bir kaynak parçası bulunamadı" kalıbını ve "okul idaresine / müdürlüğe başvurun" önerisini ezbere üretiyordu. Oysa sistemi bizzat kullanan kişi okul müdürü, müdür yardımcısı veya öğretmendi.

### Yapılan Düzeltmeler ve İyileştirmeler
1. **Hibrit ve Genişletilmiş RAG Aday Taraması (`server/rag.py` & `server/webui.py`):**
   * Vektör aramasında aday havuzu `k = 15` seviyesine çıkarıldı.
   * Kanun, KHK, yönetmelik ve madde numaraları (ör. "657", "Madde 125", "disiplin cezası") için pgvector sorgusuna `ILIKE` anahtar kelime eşleştirmesi (hibrit vektör + kelime araması) entegre edildi.
   * Vektör aday eşiği `esik = 0.38` seviyesine çekildi.
   * `server/webui.py` üzerinde Bilgehan yeniden sıralayıcı (reranker) eşiği `ESIK_RERANK_WEBUI = 0.25` olarak ayarlandı.
   * **Canlı Test:** 657 disiplin cezaları, izin hakları, Ortaöğretim Kurumları Yönetmeliği vb. sorgularda Bilgehan reranker üzerinden en alakalı 2-4 kanun maddesi başarıyla modele iletildi.
2. **Asistan Rolü ve Persona Güncellemesi (`openwebui/farabi_filtre.py` & `openwebui/promptlar/`):**
   * Farabi'ye, sohbet ettiği kullanıcının **öğretmen, müdür veya müdür yardımcısı** olduğu açıkça tanımlandı.
   * "Okul idaresine sor", "müdürlüğe git", "RAG sisteminde bulunamadı" gibi kaçamak kalıplar kesin olarak yasaklandı.
   * Farabi'nin okul personeline tam yetkili bir dijital meslektaş olarak somut mevzuat bilgisi, resmi yazı taslakları ve idari çözüm önerileri üretmesi sağlandı.
   * `openwebui/kur.py` çalıştırılarak tüm filtreler, modeller ve sistem promptları Open WebUI veritabanına senkronize edildi.

---

## 2. Dashboard 8010 Geç Yüklenme Sorununun Çözümü (`http://farabi.local:8010/`)

### Tespit Edilen Problem
* `/admin/uzaktan` sayfası açılırken 11 akıllı tahtaya senkron olarak SSH üzerinden anlık durum taraması yapılıyor, bu da HTTP yanıtını **3.3 ila 5.6 saniye** bloke ediyordu.

### Yapılan Çözüm ve Hızlandırma
1. **45 Saniyelik Asenkron Durum Önbelleği (`tahtayoklama/dashboard/uzaktan_yonetim.py`):**
   * Tahta durumlarını hafızada tutan thread-safe bir kilit mekanizması ve önbellek yapısı kuruldu.
2. **Asenkron Durum API Uç Noktası:**
   * `/admin/uzaktan/api/durumlar` uç noktası eklendi.
3. **Anında Sayfa Açılışı:**
   * HTML sayfası artık SSH bağlantılarını beklemeden **14 milisaniyede** (önceden 3.3 saniye — **~240 kat hızlanma**) açılıyor; tahta durumları ön yüzde asenkron olarak dolduruluyor.

### Sayfa Yanıt Süreleri Karşılaştırması

| Uç Nokta | Eski Yanıt Süresi | Yeni Yanıt Süresi | Durum |
| :--- | :--- | :--- | :--- |
| **`/` (Yoklama Panosu)** | ~40-100 ms | **4 ms** | HTTP 200 OK |
| **`/admin/uzaktan`** | **3.29 - 5.60 sn** | **14 ms** | HTTP 200 OK |
| **`/admin/tahtalar`** | ~30 ms | **10 ms** | HTTP 200 OK |
| **`/admin/siniflar`** | ~20 ms | **3 ms** | HTTP 200 OK |
| **`/admin/rapor`** | ~40 ms | **13 ms** | HTTP 200 OK |
| **`/sistem-durumu`** | ~50 ms | **4 ms** | HTTP 200 OK |
| **`/sunucular`** | ~30 ms | **8 ms** | HTTP 200 OK |

---

## 3. Tüm Dashboardlar İçin Kapsamlı Modern Web Tasarımı

### Tasarım Sistemi & Stil Mimarisi (`tahtayoklama/dashboard/static/pano.css`)
* **3 Farklı Tema Desteği:**
  * **Klasik Tema (Varsayılan):** Temiz Slate zemin (`#f8fafc`), saf beyaz kartlar, Indigo birincil vurgu (`#4f46e5`), zümrüt yeşili (`#059669`) ve gül kırmızısı (`#e11d48`).
  * **Koyu Tema:** Zengin lacivert/koyu slate zemin (`#0b0f19`), yükseltilmiş kartlar (`#131926`) ve yüksek kontrastlı renkler.
  * **Yumuşak Tema:** Göz yormayan sıcak kağıt/keten tonları (`#f7f3ec`) ve kiremit rengi vurgular (`#b55d28`).
* **Özel Scrollbar Tasarımı:** İnce, yuvarlatılmış ve arka planla uyumlu pürüzsüz kaydırma çubukları.
* **Katmanlı Kart Gölgeleri:** Hover durumunda `-2px` yükselen modern elevation gölgeleri (`--renk-golge-kart`, `--renk-golge-yukseltilmis`).

### Yoklama Panosu Yenilikleri (`tahtayoklama/dashboard/templates/pano.html`)
1. **KPI Özet İstatistik Kartları:**
   * Tablonun hemen üstüne 4 adet KPI özet kartı eklendi:
     * 👥 **Aktif Sınıflar:** Sistemdeki toplam sınıf adedi
     * ✅ **Eksiksiz Dersler:** Devamsızı veya izinlisi olmayan, tam tamamlanan dersler
     * ⚠️ **Devamsız / İzinli:** Devamsızlık veya izin kaydı bulunan dersler
     * ⏳ **Bekleyen Yoklama:** Henüz yoklama alınmamış dersler
   * Bu sayaçlar sayfa yüklendiğinde ve her otomatik veri yenilemesinde JavaScript ile anlık olarak hesaplanıp güncellenir.
2. **Aktif Ders Saati Vurgusu:**
   * Okul zil saatlerine göre o an işlenmekte olan ders saati sütun başlığında `.aktif-ders-sutun` stili ve yanıp sönen `Şu an` rozetiyle otomatik olarak vurgulanır.
3. **Pürüzsüz İskelet Yükleme (Shimmer Animation):**
   * Hücrelerdeki kesik yanıp sönen animasyon yerine degrade akışına sahip modern `@keyframes iskelet-isilti` getirildi.

### Diğer Sayfalar ve Bileşenler
* **`taban.html`:** Yan menüye marka logosu ve alt başlık (`Farabi Panel — Yoklama & Yönetim`) eklendi; alt durum göstergesine nabız atan renkli durum noktası entegre edildi.
* **`admin_siniflar.html`:** Sınıf tablosuna öğrenci sayısı rozetleri ve modern ikincil aksiyon butonları eklendi.
* **`admin_tahtalar.html`:** Akıllı tahta isimleri belirginleştirildi, yüklü liste durum rozetleri modernize edildi.
* **`uzaktan_yonetim.html`:** Yeni sekmede ekran görüntüsü açma butonları (`.ss-link-btn`), toplu seçim ve eylem çubukları güncellendi.
* **`_ikon_sprite.html`:** Eksik olan `#ik-onay` checkmark ikonu sprite dosyasına eklendi.

---

## 4. Test ve Kalite Güvencesi

Tüm alt projelerdeki test paketleri eksiksiz olarak çalıştırıldı ve %100 başarı sağlandı:

1. **Server RAG & API Testleri:**
   * `server/venv/bin/pytest server/tests/`
   * **190 test geçti** (0 hata)
2. **Open WebUI Filtre & Araç Testleri:**
   * `PYTHONPATH=. /home/ata/farabi/server/venv/bin/pytest openwebui/tests/`
   * **148 test geçti** (0 hata)
3. **Tahta Yoklama Dashboard Testleri:**
   * `tahtayoklama/dashboard/venv/bin/python -m unittest discover -p "test_*.py"`
   * **114 test geçti** (0 hata)
4. **SMS Sistemi Testleri:**
   * `smssistemi/venv/bin/pytest`
   * **130 test geçti** (0 hata)
5. **Genel Toplam:** **582 / 582 Test Başarılı.**

---

## 5. Servis ve Dağıtım Durumu

Aşağıdaki systemd servisleri güncellenmiş ve canlıda sorunsuz çalışmaktadır:
* `farabi-api.service` (Port 8000 — RAG, Hibrit Arama & Bilgehan Reranker)
* `farabi-yoklama-dashboard.service` (Port 8010 — Yoklama Panosu & Yönetim)
* `farabi-smssistemi.service` (Port 8020 — SMS Yönetimi & Otomasyon)
* `open-webui.service` (Port 80 — Atos Yapay Zeka & Farabi Modları)
