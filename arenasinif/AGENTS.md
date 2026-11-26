# Sınıf Arenası (`arenasinif/`)

Sınıf akıllı tahtalarında oynanan etkileşimli eğitim ve yarışma oyunları servisi. Sınıf Arenası, Düello ve HexaFetih oyun modlarını içerir.
Tahta IP'sini tanır, sınıfı ve o anki dersi çözer, yoklama panosundan devamsız öğrencileri filtreler, dengeli takımlar kurar ve MEB soru havuzundan soruları sunar.

- Servis: `sinif-arena.service` (systemd, port 8030, `arenasinif/` dizini)
- Başlatma scripti: `./baslat.sh` (uvicorn `server:app --host 0.0.0.0 --port 8030`)
- Framework: FastAPI + Uvicorn + Jinja2/HTML + Tailwind CSS
- Veritabanı: SQLite WAL (`veri/sonuclar.db`), harici salt-okunur PostgreSQL `soru_havuzu`

## Komutlar
```bash
venv/bin/uvicorn server:app --reload --port 8030           # geliştirmede yerel
venv/bin/python -m pytest -q                              # tüm testler (71 test)
venv/bin/python -m pytest test_arena.py -q                # tek test dosyası
venv/bin/python -m pytest test_yerel.py -q                # yerel mantık testleri
sudo systemctl restart sinif-arena.service                # üretime alma (servis restart)
journalctl -u sinif-arena.service -f                      # canlı loglar
```
- Arayüz derlemesi (Tailwind): Değişiklik sonrası derlenmiş CSS `static/` altına kopyalanır. Ortak cam teması (`cam-tema.css`) kullanılır.

## Önemli Dosyalar ve Sorumlulukları
| Dosya | Sorumluluk |
|---|---|
| `server.py` | FastAPI uygulama girişi, oyun API'leri ve sayfa yönlendirmeleri |
| `havuz.py` | PostgreSQL `soru_havuzu` veritabanından ders ve sınıf düzeyine göre soru çekme |
| `soru_uretici.py` | Havuz ve yerel LLM (Ollama `farabi`) ile dinamik soru hazırlama |
| `takim_kurucu.py` | Sınıf mevcudunu ve devamsızlık durumunu dikkate alarak dengeli tematik takımlar oluşturma |
| `duello_motoru.py` | 1'e 1 öğrenci yarışması (Düello) mekaniği, can puanı ve süre kontrolü |
| `duello_deposu.py` | Düello skorları ve karşılaşma geçmişi saklama |
| `fetih_motoru.py` | Altıgen harita üzerinde takım bazlı stratejik fetih (HexaFetih) kuralları ve hamle denetimi |
| `sonuc_deposu.py` | Oyun sonuçları, liderlik tablosu ve istatistiklerin `veri/sonuclar.db`'ye kaydedilmesi |
| `logger.py` | Oyun olaylarının yapılandırılmış JSON loglanması |
| `turkce.py` | Türkçe metin normalizasyonu ve karakter işleme |
| `sinif_arena.html`, `duello.html`, `hexafetih.html`, `ozet.html` | Oyun ön yüz şablonları |

## Uç Noktalar (API)
- **Sayfalar:**
  - `GET /` → Ana karşılama ve mod seçimi
  - `GET /arena` → Sınıf Arenası oyun ekranı
  - `GET /duello` → Düello ekranı
  - `GET /hexafetih` → HexaFetih strateji haritası
  - `GET /ozet` → Karşılaşma sonu özet ve liderlik tablosu
- **API Rotaları:**
  - `GET /api/sinif-durumu` → İstemci IP'sinden sınıf, ders ve devamsız öğrenci listesini getirme
  - `GET /api/soru` → Dersi ve zorluğu belirlenmiş yeni soru çekme
  - `POST /api/cevapla` → Soru cevabını doğrulama ve puanlama
  - `POST /api/sonuc-kaydet` → Oyun sonucunu kalıcı kaydetme
  - `POST /api/duello/*` → Düello hamle, pas ve sonuç uçları
  - `POST /api/fetih/*` → HexaFetih hücre ele geçirme ve bölge puanlama uçları

## Veri Akışı ve Bağımlılıklar
1. **Tahta Tanıma:** `server.py`, bağlanan istemcinin IP adresini `../server/tahtalar.json` ve dashboard DB'si üzerinden eşleştirerek hangi sınıfta olduğunu tespit eder.
2. **Ders ve Zil:** O anki aktif ders `tahtayoklama/data/zil.json` ve `ders_programi.json` üzerinden okunur.
3. **Yoklama:** `tahtayoklama/dashboard/veri/yoklama_pano.db` salt-okunur taranarak o gün devamsız olan öğrenciler takım kurucuya dahil edilmez.
4. **Soru Havuzu:** Sorular merkezi PostgreSQL `soru_havuzu` veritabanından çekilir; kullanım istatistiği kaydedilir.
5. **Görsel Tema:** Ortak cam teması (`static/cam-tema.css`) kullanılır.
