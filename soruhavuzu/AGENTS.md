# soruhavuzu

Oyunlar (Sınıf Arenası vb.) ve smual.app için hazır soru havuzu: ayrı PostgreSQL veritabanı `soru_havuzu` (şema `sema.sql`, arşiv/görsel eki `soru_arsivi.sql`). Kodu kökten, server venv'i ile koşar (psycopg2/pymupdf/httpx orada).

## Kararlar (uyulacak)
- ⚠️ Otomatik soru üretimi İPTAL (2026-11-07): havuz hazır sorular + orijinal görsellerden oluşan arşivdir. `soru-havuzu-uret.timer` DISABLED; açma. `uret`/`siniflandir`/`tekrar` (gömme ile mükerrer eleme) kodda duruyor ama kullanılmaz.
- ⚠️ RAG/gömme servisi (`farabi-embed`, :8040) ASLA açılmaz; gömme gerektiren akış çalıştırılmaz.
- DB şifresi `~/.pgpass`'tan. Plan: `docs/superpowers/plans/2026-10-05-soru-havuzu.md`; kararlar kök `DECISIONS.md`.

## Komutlar
- Çalıştırma (kökten): `server/venv/bin/python -m soruhavuzu.calistir <komut>`; komutlar `calistir.py` içinde (`durum`, `kur`, `denetle`, `sik-karistir [--kuru]`, `ogretmen-pdf`, `geri-bildirim`, `sekil-tara`, `tekrar-temizle` ...).
- Test: `server/venv/bin/python -m pytest soruhavuzu/tests -q`.
- Birim dosyası değişirse `/etc/systemd/system/`'e de kopyalanmalı (`systemd/` yalnız kaynak kopya).

## Hazır soru arşivi
- MEBİ TYT 2. deneme 125 soru, cevap ve görselleriyle arşivde. Görsel `soru_gorsel` tablosunda (PostgreSQL içinde, `pg_dump` ile yedeklenir). `tyt_pdf_hazirla.py` + `tyt_arsive_aktar.py` bu PDF biçimine özel, doğrulamalı araçlardır; başka PDF'e uyarlamadan koşma.
- Şekil atıflı 284 eski kayıt görselleri doğrulanana kadar askıda kalır.
- Şık sırası: `sik.kanonik_sira` şıkları metin hash'ine (sayısal şıklar değere) göre kanonik diziler, `vt.soru_ekle` her yeni soruya uygular; konuma atıflı şıklar ("A ve B", "hepsi") dokunulmaz. Geçmiş için `calistir sik-karistir [--kuru]` (ikinci çalıştırmada 0 değişiklik). YKS için `dogru_index < 8` (E dahil).
- Okul portalı bildirimi: `okul_bildirim.py` smual.app "soru hatalı" kayıtlarını havuza işler; okul portalı havuza yazmaz, kararları soruhavuzu uygular.

## Öğretmen katkısı (LLM'siz)
- `katki.py` (`python -m soruhavuzu.katki`) + `systemd/soru-katki.{service,timer}` (2 dk, oneshot, `/etc/systemd/system`'e kopyalı, timer enabled): okul `/api/soru-katki` kuyruğundaki cevap anahtarlı PDF'leri ayrıştırır.
  - Ayrıştırma: numara 1..N sıralı, şık zinciri A)…D)/E); yan yana şıklar aynı hizada gruplanır; iri punto filigran ve kenar üst/alt bilgi atılır.
  - Yazma: soru başına kırpılmış PNG `soru_gorsel`'e, soru tek transaction'da `onayli` (anahtar `katki:<sha>:<no>`). Şık sırası KORUNUR (görseldeki harflerle aynı kalsın diye `kanonik_sira` UYGULANMAZ).
  - Soru sayısı ≠ cevap anahtarı ya da şık bulunamazsa HİÇ yazmaz; neden öğretmene döner.
  - Şekle atıflı / kesirli / şıkları resim olan soru `Soruyu görselden inceleyiniz.` yer tutucusuyla yazılır; tahta arenası (`arenasinif/havuz.py::TAHTADA`) bunları göstermez.
  - Aynı tur, öğretmen onay kararlarını (okul.db'deki `soru_katki_karar`) havuza uygular.
  - Bilinen sınır: ortak paragraflı sorularda ("39-40. soruları …") paragraf ilk soruda kalır.
- `acik_uclu_aktar.py` (`ayristir` -> `donustur_bir` -> `aktar [--uygula]`): öğretmenin açık uçlu çözümlü PDF'i yerel `farabi` modeliyle 4 şıklı soruya çevrilir; `askida` + anahtar `ogretmen-acik:<sha>:<no>` yazılır (AGY denetimi `uretildi` seçtiği için dokunmaz); öğretmen `/ogretmen/soru-katki`'da onaylayınca `onayli`. Ayrıştırıcı Kubilay Kurnaz biyoloji PDF'ine özel (`Soru N` / `Soru N Çözümü`, `GURULTU` filigran regex'i); başka PDF'te önce `ayristir` çıktısını incele.

## Denetim ve gece penceresi (eski akış; yalnız bilgi)
- GPU işi (`uret`, denetim) yalnız 00:00-06:00 TR (`zaman.uretim_serbest`); gündüz GPU Ollama'nın diğer kullanıcılarına kalır. Elle `denetle` pencere kontrolsüz ve sınırsızdır, gündüz koşma.
- Sınırlı denetim sabitleri: `calistir.DENETIM_AZAMI_PAKET`, `DENETIM_AZAMI_DK`.
