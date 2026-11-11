# KOD KALİTESİ VE HATA DENETİMİ (CODE QUALITY AUDIT)

> ⚠️ **DOĞRULANMAMIŞ — LLM üretimi (2026-10-29 toplu belge seti).** 2026-11-11 kod kontrolünde bu setteki belgelerin
> var olmayan dosyalara (`smssistemi/netgsm.py`, `server/services/stt_service.py`, `okul/rotalar/notlar.py`,
> `tahtayoklama/ziller/zil.py`) ve projede olmayan teknolojilere (Netgsm, go2rtc, Whisper, Nginx, Flask, `/home/pi`)
> atıf yaptığı görüldü. Kaynak değildir; bir bulguya göre iş yapmadan önce kodda doğrula. Esas: kök `AGENTS.md`,
> `docs/mimari.md`, `docs/runbook.md`, `DECISIONS.md`.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Denetçi:** Kıdemli Python Yazılım Mimarı ve Kod Denetçisi  
> **Analiz Araçları:** Ruff v0.9+, Pytest, Unittest, AST Analizcisi, Manuel Kod Denetimi

---

## 1. Statik Analiz ve Genel Kalite Özeti

Farabi kod tabanı genelinde çalıştırılan linter ve statik denetimlerde **1.316 adet** kural ihlali ve kod kokusu (code smell) tespit edilmiştir. En kritik kategoriler:
- **`ASYNC221` / `ASYNC230`:** Asenkron FastAPI rotaları içinde senkron subprocess/dosya/veritabanı I/O işlemleri.
- **`B023`:** Döngü değişkenlerinin lambda ve closure fonksiyonlarında geç bağlanması (late-binding bug).
- **`SIM115`:** Dosyaların `with open(...)` kullanılmadan açılması ve açık dosya tanıtıcısı (file descriptor) sızıntısı.
- **`F811`:** Aynı kapsamda yinelenen fonksiyon ve rota tanımları.

---

## 2. 15 Hata Sınıfı Kapsamında Ayrıntılı Bulgular

---

### Kategori 1: Syntax Hataları ve Import Problemleri
- **Bulgu CQA-01:** `smssistemi/app.py` içinde 8 farklı rotada HTTP 410 dönüşünden sonra ölü kod ve import kalıntıları bulunmaktadır.
- **Bulgu CQA-02:** Bazı modüllerde döngüsel bağımlılığı (circular import) aşmak için fonksiyon içi `import` yapılmıştır (örn. `okul/rotalar/analitik.py`).

---

### Kategori 2: Çalışma Zamanı İstisnaları (Runtime Exceptions)
- **Bulgu CQA-03:** `smssistemi` test suite'inde 2 adet birim testi patlamaktadır:
  - `smssistemi/test_dogum_app.py::test_dogum_kisi_tarih_kaydet`
  - `smssistemi/test_rehber_duzenle.py::test_duzenleme_okul_no_ve_veli_rolunu_korur`
  - **Sebep:** 2026-10-23 tarihinde `okul_ana` geçişi sırasında ilgili rotalar HTTP 410 Gone yapılmış fakat testler güncellenmemiştir.

---

### Kategori 3: Hatalı Exception Handling ve Kaybolan Hata Mesajları
- **Bulgu CQA-04:** `tahtayoklama/dashboard/uzaktan_baslat.py:112` ve `kameralar.py:84`:
  ```python
  except Exception:
      pass
  ```
  Kritik SSH bağlantı hataları ve kamera soket kopmaları `except Exception: pass` blokları ile tamamen yutulmakta, sistem günlüğüne (log) hiçbir hata izi bırakılmamaktadır.

---

### Kategori 4: Asenkron Yapı ve Event Loop Bloklanması (Kritik Performans)
- **Bulgu CQA-05:** [`tahtayoklama/dashboard/kameralar.py:168`](file:///home/ata/farabi/tahtayoklama/dashboard/kameralar.py#L168)
  - `async def api_kamera_video` içerisinde `subprocess.run(komut, timeout=25, check=False)` çalıştırılmaktadır.
  - **Etki:** Bir kamera yanıt vermediğinde 25 saniye boyunca ana olay döngüsü (event loop) tamamen donmakta, bu sürede paneldeki hiçbir kullanıcıya veya akıllı tahtaya yanıt verilememektedir.
  - **Çözüm:** `await asyncio.to_thread(...)` veya `asyncio.create_subprocess_exec` kullanılmalıdır.
- **Bulgu CQA-06:** [`okul/rotalar/sudoku.py:67, 154`](file:///home/ata/farabi/okul/rotalar/sudoku.py#L67)
  - `async def` rotasında 20.000 döngülük backtracking algoritması CPU-bound olarak doğrudan çalıştırılmaktadır.
- **Bulgu CQA-07:** [`kelebek/app.py:234`](file:///home/ata/farabi/kelebek/app.py#L234)
  - `async def dagit_yap` içinde 4.000 takaslık simüle edilmiş tavlama algoritması ana thread'i bloklamaktadır.

---

### Kategori 5: Deadlock, Race Condition ve Eşzamanlılık
- **Bulgu CQA-08:** `smssistemi/arac_api.py:442-485`:
  - SMS gönderimi için arka plan iş parçacığı (`threading.Thread`) başlatılmakta, ancak taslağın durumu veritabanında hemen güncellenmemektedir. İki idareci aynı anda "Gönder" butonuna bastığında çift SMS atılmaktadır.

---

### Kategori 6: Bellek Sızıntıları ve Model Kaynak Yönetimi
- **Bulgu CQA-09:** `server/services/stt_service.py`:
  - Yerel Whisper modeli her istekte veya birden fazla worker başlatıldığında VRAM'e mükerrer yüklenebilmektedir. Tekil (singleton) model yükleyicisi bulunmakla birlikte Uvicorn `--workers > 1` çalıştırıldığında 24GB VRAM hızla tükenmektedir.

---

### Kategori 7: Timeout ve Harici Servis Bağlantı Havuzu
- **Bulgu CQA-10:** `smssistemi/netgsm.py`:
  - Netgsm API isteklerinde `requests.post()` kullanılırken global bağlantı havuzu (`requests.Session`) kullanılmamakta, her SMS'te yeni TCP + TLS el sıkışması yapılmaktadır. Ayrıca bazı çağrılarda `timeout` parametresi eksiktir.

---

### Kategori 8: Veritabanı Transaction ve N+1 Sorgu Sorunları
- **Bulgu CQA-11:** `okul/rotalar/notlar.py:115-140`:
  - Bir sınıftaki 35 öğrencinin karne notları hesaplanırken döngü içinde her öğrenci için ayrı ayrı 4 adet `SELECT` sorgusu çalıştırılmaktadır (35 x 4 = 140 sorgu). Tek bir `JOIN` veya `IN (...)` sorgusuyla çözülmelidir.
- **Bulgu CQA-12:** `okul/deps.py:167`:
  - Her HTTP isteğinde `rol` bağımlılığı `UPDATE oturum SET son_gorulme = ?` çalıştırmakta ve SQLite üzerinde aşırı disk yazma kilidine (`sqlite3.OperationalError: database is locked`) neden olmaktadır.

---

### Kategori 9: Dosya ve Kaynak Yönetimi
- **Bulgu CQA-13:** `SIM115` ihlalleri:
  - `tahtayoklama/dashboard/app.py` ve `kazanimtest/uretici.py`: PDF ve JSON dosyaları `f = open(...)` ile açılıp bazı hata durumlarında `f.close()` çağrılmadan fonksiyondan çıkılmaktadır.

---

### Kategori 10: Yanlış Tipler ve Sınır Durumları (Edge Cases)
- **Bulgu CQA-14:** `okul/rotalar/devamsizlik.py`:
  - Yarım gün devamsızlık hesaplamasında `float` ve `Decimal` dönüşümleri sırasında yuvarlama farkları oluşmaktadır (örn. `0.5 + 0.5 = 1.0` iken string karşılaştırmalarında `1` != `1.0` uyumsuzluğu).

---

### Kategori 11: Tekrarlanan Kod ve Aşırı Büyük Modüller
- **Bulgu CQA-15:** SQLite bağlantı fonksiyonu:
  - `okul/db.py`, `tahtayoklama/db.py`, `smssistemi/db.py` içinde neredeyse birebir aynı `baglanti()` ve `PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;` fonksiyonları kopyalanmıştır.

---

### Kategori 12: Kullanılmayan Kod ve Ölü Dallar (Dead Code)
- **Bulgu CQA-16:** `smssistemi/app.py`:
  - 8 endpoint içinde `raise HTTPException(status_code=410, detail="...")` ifadesinden sonra gelen 30-50 satırlık iş mantığı kodları tamamen erişilemez durumdadır.

---

### Kategori 13: Önbellek Bayatlaması (Stale Cache Bug - Önemli!)
- **Bulgu CQA-17:** [`tahtayoklama/dashboard/okul_ana_panel.py`](file:///home/ata/farabi/tahtayoklama/dashboard/okul_ana_panel.py)
  - Yönetim panelinden ders programı ve ziller güncellendiğinde `data/zil.json` ve `data/ders_programi.json` dosyalarına yeni veriler yazılmaktadır.
  - Ancak `tahtayoklama/ziller/zil.py` içindeki `@lru_cache(maxsize=1)` fonksiyonuna `zil.yenile()` çağrısı yapılmamaktadır!
  - **Sonuç:** Servis yeniden başlatılana kadar ziller eski saatlere göre çalmaya devam etmektedir.

---

### Kategori 14: Loglama ve Gözlemlenebilirlik Eksiklikleri
- **Bulgu CQA-18:** Birçok modülde `logging` yerine doğrudan `print()` fonksiyonu kullanılmıştır. Bu durum log seviyelerinin (INFO, WARNING, ERROR) filtrelenmesini ve log rotasyonunu imkansız kılmaktadır.

---

### Kategori 15: Eksik Testler ve Test Edilemeyen Alanlar
- **Bulgu CQA-19:** `client/` akıllı tahta arayüzü ve WebRTC donanım katmanı için otomatikleştirilmiş mock testleri bulunmamaktadır. Testler yalnızca fiziksel tahta üzerinde elle doğrulanabilmektedir.
