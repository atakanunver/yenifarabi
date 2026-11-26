# Soru Havuzu (`soruhavuzu/`)

Sınıf oyunları (Sınıf Arenası, Düello, HexaFetih) ve Dijital Okul portalı (Soru Maratonu, Bilgi Arenası) için merkezi soru ve görsel arşivi. Ayrı bir PostgreSQL veritabanı (`soru_havuzu`) üzerinde çalışır.

- Veritabanı: PostgreSQL `soru_havuzu` (şema `sema.sql`, görsel arşivi `soru_arsivi.sql`, bağlantı `~/.pgpass`)
- Servis/Zamanlayıcı: `soru-katki.timer` (systemd, her 2 dakikada bir öğretmen katkı kuyruğunu işler)
- Çalıştırma Alanı: Repo kökünden `server/venv` ortamı ile çalıştırılır (`psycopg2`, `pymupdf`, `httpx`).

## Komutlar
```bash
# Repo kökünden çalıştırılır:
server/venv/bin/python -m soruhavuzu.calistir durum        # havuz durum özeti
server/venv/bin/python -m soruhavuzu.calistir kur          # şemayı kurma
server/venv/bin/python -m soruhavuzu.calistir sik-karistir --kuru  # şık sırası karıştırma
server/venv/bin/python -m soruhavuzu.katki                 # öğretmen katkı kuyruğunu elle işleme
server/venv/bin/python -m pytest soruhavuzu/tests -q       # soru havuzu testleri
```

## Önemli Dosyalar ve Sorumlulukları
| Dosya | Sorumluluk |
|---|---|
| `calistir.py` | Soru havuzu yönetim CLI komutları (`durum`, `kur`, `denetle`, `sik-karistir`, `ogretmen-pdf` vb.) |
| `vt.py` | PostgreSQL bağlantısı, soru ekleme (`soru_ekle`), sorgulama ve transaction yönetimi |
| `katki.py` | Öğretmenlerin Dijital Okul üzerinden yüklediği cevap anahtarlı PDF'leri ayrıştırıp havuza onaylı soru olarak ekleme |
| `sik.py` | Şıkların kanonik sıraya dizilmesi (`sik.kanonik_sira`), metin hash'i ile deterministik şık karıştırma |
| `okul_bildirim.py` | Dijital Okul portalından gelen "soru hatalı" bildirimlerini işleme |
| `acik_uclu_aktar.py` | Açık uçlu soruları yerel LLM (`farabi`) ile çoktan seçmeli formata dönüştürme ve askıya alma |
| `sema.sql` & `soru_arsivi.sql` | Veritabanı tabloları: `soru`, `soru_gorsel`, `soru_kullanim`, `kazanimlar` |

## Önemli Kararlar ve Kurallar
1. 🛑 **Otomatik Soru Üretimi İPTAL (2026-11-07):** Havuz yalnızca doğrulanmış hazır sorulardan ve öğretmen katkılarından oluşur. `soru-havuzu-uret.timer` kapatılmıştır (disabled); açılmamalıdır.
2. 🛑 **RAG ve Gömme Kapalı:** `farabi-embed` servisi kapalıdır. Vektör arama ve gömme gerektiren eski akışlar çalıştırılmaz.
3. **Öğretmen Katkısı Ayrıştırma:** Soru numaraları (1..N) ve şıklar (A..E) sıralı olmalı; şıklar görseldeki harflerle eşleşmesi için orijinal haliyle korunur.
4. **Şekilli Sorular:** Görsel içeren sorular `soru_gorsel` tablosunda saklanır. Tahtada gösterilemeyecek karmaşık şekilli sorular tahta arenası filtresine takılır.
