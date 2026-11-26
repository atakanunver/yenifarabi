# CLAUDE.md (Farabi Geliştirici Ajan Kuralları)

Bu belge, Claude Code ve diğer yapay zekâ geliştirici ajanların Farabi monoreposunda çalışırken uyması gereken kesin, uygulanabilir ve bağlayıcı kuralları içerir. Kapsamlı sistem mimarisi ve teknik harita için [AGENTS.md](file:///home/ata/farabi/AGENTS.md) belgesini inceleyin.

---

## 1. Altın Kurallar (Asla Çiğnenemez)
1. ⚠️ **CANLI ÜRETİM ORTAMI:** `/home/ata/farabi` canlı üretim ortamıdır. Servisler doğrudan bu dizindeki dosyalardan koşar. Master dalındaki kod canlıdır; servis restart edildiğinde yayına girer.
2. 🛑 **KOD DEĞİŞTİRMEDEN ÖNCE İLGİLİ MODÜLLERİ OKU:** Tahminle veya eski belgelere güvenerek kod yazma. Önce ilgili modülü, importları ve bağımlılıkları oku.
3. 🛑 **MEVCUT MİMARİYİ VE API SÖZLEŞMELERİNİ KORU:** Servisler arası HTTP/JSON sözleşmelerini bozma. Tahtalarda çalışan `client` ve `tahta_istemci.py` kodlarının geriye dönük uyumunu daima koru.
4. 🛑 **GEREKSİZ BAĞIMLILIK EKLEME:** Yeni harici kütüphane, CDN linki veya ağır framework ekleme. Her zaman mevcut standart kütüphane veya kurulu paketleri kullan.
5. 🛑 **ÇALIŞAN SERVİSLERİ İZİNSİZ DURDURMA:** Ders saatlerinde (08:00 - 17:00 TR) `farabi-yoklama-dashboard` veya `farabi-api` gibi tahta/okul servislerini asla yeniden başlatma veya durdurma.
6. 🛑 **GİZLİ BİLGİLERİ VE KİMLİK BİLGİLERİNİ AÇIĞA ÇIKARMA:** Repo PUBLIC'tir. `.env`, `gizli.json`, API tokenları, şifreler, öğrenci/veli kişisel verileri (TC, telefon, devamsızlık) kesinlikle commit'lenemez, kodlara yazılamaz veya genel belgelere aktarılamaz.
7. 🛑 **DEĞİŞİKLİKLERDEN SONRA İLGİLİ TESTLERİ ÇALIŞTIR:** Yapılan her değişiklikten sonra ilgili modülün testlerini koştur ve geçtiğini gözlerinle gör.
8. 🛑 **YAPILMAYAN TESTLERİ YAPILMIŞ GİBİ RAPORLAMA:** Testi atlama, sonucu gizleme, çalıştırmadığın bir testi "başarılı" diye raporlama. Ölçülebilir ve doğrulanabilir kanıt sun.
9. 🛑 **YENİ ÖZELLİK EKLERKEN MEVCUT MODÜLER YAPIYI KULLAN:** Spagetti kod yazma; ilgili servisin kendi modüler router/iş mantığı desenine uy.
10. 🛑 **İLGİLİ ALT KLASÖR TALİMATLARINI DİKKATE AL:** Her alt servisin kendi `AGENTS.md` / `CLAUDE.md` belgesindeki özel kuralları (örn. dashboard'daki unittest kuralı, okul'daki GOCLER kuralı) bağlayıcıdır.

---

## 2. Kalıcı İptal Edilmiş Özellikler (Yeniden Açma / Önerme)
- **RAG ve Gömme Servisi (`farabi-embed`):** `server/main.py::RAG_AKTIF = False`. 8040 portundaki embed servisi bilerek kapalıdır; RAG'ı yeniden açma.
- **Otomatik Soru Üretimi:** `soru-havuzu-uret.timer` disabled'dır; LLM ile otomatik soru üretimi yapılmaz.
- **Kazanım Testi Zamanlayıcıları:** `kazanimtest` kalıcı olarak iptal edilmiştir.
- **Yerel STT / TTS / Pipecat:** Tahtalarda ses yalnızca tahta istemcisinin Gemini Live WebSocket oturumu üzerinden yürütülür.

---

## 3. Servis Test ve Doğrulama Komutları Tablosu
Değişiklik yaptığın modüle göre ilgili test komutunu mutlaka çalıştır:

| Modül | Test Komutu | Test Framework |
|---|---|---|
| `server/` | `cd server && venv/bin/python -m pytest tests/ -q` | pytest |
| `tahtayoklama/dashboard/` | `cd tahtayoklama/dashboard && venv/bin/python -m unittest discover -p 'test_*.py'` | **unittest** (pytest YOK!) |
| `smssistemi/` | `cd smssistemi && venv/bin/python -m pytest -q` | pytest |
| `okul/` | `cd okul && venv/bin/python -m pytest -q` | pytest |
| `client/` | `cd client && venv/bin/python -m pytest tests/ -q` | pytest |
| `arenasinif/` | `cd arenasinif && venv/bin/python -m pytest -q` | pytest |
| `kelebek/` | `cd kelebek && venv/bin/python -m pytest tests -q` | pytest |
| `progmatik/` | `cd progmatik && venv/bin/python -m pytest tests -q` | pytest + npm test |
| `tahtaatlasfarabi/` | `cd tahtaatlasfarabi && .venv/bin/python -m pytest tests/test_atlas.py -q` | pytest |
| `soruhavuzu/` | `server/venv/bin/python -m pytest soruhavuzu/tests -q` | pytest |
| `kameralar/hareket/` | `cd kameralar/hareket && venv/bin/python -m unittest test_hareket -v` | unittest |
| `tahtaayar/` | `cd tahtaayar && python3 -m unittest test_tahta_fix_uygula -v` | unittest |

---

## 4. Kodlama ve Git Standartları
- **Cerrahi Değişiklik:** Yalnızca gereken satırlara dokun. Bozuk olmayan kodu refactor etme, dosyanın mevcut kodlama ve girinti stiline uy.
- **Lint:** Dokunduğun dosyayı `.venv-tools/bin/ruff check <dosya>` ile denetle. F821/F811/F632 hataları sıfır olmalı, mevcut uyarı sayısı artmamalı.
- **Git Komutları:** `git sparse-checkout set/reapply` komutunu ASLA çalıştırma (izlenmeyen dizinleri silebilir).
- **CRLF Uyarısı:** `okul/` dizini altındaki bazı dosyalar CRLF olabilir; Python ile düzenleme yaparken satır sonu formatını bozma.

---

## 5. Değişiklik Sonrası Doğrulama Adımları
1. **Statik Kontrol:** `ruff` veya `node --check` ile sözdizimi hatalarını tara.
2. **Birim Testleri:** Yukarıdaki tablodan ilgili modülün test komutunu çalıştırıp tamamının geçtiğini doğrula.
3. **Diff İncelemesi:** `git diff` ile yalnızca dokunmak istediğin satırların değiştiğini, araya gereksiz formatlama veya gizli anahtar karışmadığını kontrol et.
4. **Servis Durumu:** Canlı servisi yeniden başlattıysan `systemctl status <servis>` ve `journalctl -u <servis> -n 30` ile hatasız ayağa kalktığını doğrula.
