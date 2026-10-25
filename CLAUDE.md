# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Çalışma ilkeleri
1. **Önce düşün:** Sessiz varsayım yapma. Belirsizlik ya da birden fazla yorum varsa söyle, gerekirse sor.
2. **Önce sadelik:** İsteneni yapan en az kodu yaz; spekülatif özellik ve gereksiz soyutlama ekleme.
3. **Cerrahi değişiklik:** Yalnızca istenen satırlara dokun; komşu kodu "iyileştirme", stili/biçimi değiştirme. SSH ile birden çok makineye dağıtılan kodda özellikle önemli.
4. **Hedef odaklı:** Görevi doğrulanabilir bir başarı kriterine çevir (test, `curl`, `systemctl is-active`, log satırı); kriter sağlanmadan "bitti" deme.

# Farabi
Sınıf akıllı tahtalarında sesli ders asistanı + aynı sunucuda okul operasyon
servisleri (yoklama panosu, SMS). Monorepo; her alt projenin kendi `CLAUDE.md`'si
var (client, server, tahtayoklama, smssistemi, tahtaayar, benchmark, mudur,
soruhavuzu, kazanimtest, okul; `openwebui/`, `webui-tema/` için CLAUDE.md yok). Bu dosya: ortak kurallar + servisler arası resim.

- Kararlar/neden: `DECISIONS.md` (`grep "## <tarih>"`). Mimari (2026-09-13'te
  donmuş, çelişkide bu dosya esas): `docs/mimari.md`. Ağ envanteri, dağıtım,
  SSH, zamanlayıcılar: `docs/runbook.md`. Sürüm notları: `CHANGELOG.md`;
  `README.md` yalnızca Atakan isterse güncellenir. Eski analiz/planlar: `_arsiv/` (okuma).
- ⚠️ `/home/ata/farabi` CANLI ÜRETİM — servisler buradan koşuyor. Master'a commit
  = deploy kaynağı; üretime almak = ilgili servisi restart.

## Mevcut durum (kalıcı)
- `farabi-idari-yukle.timer` KALICI KAPALI (2026-10-10), açıkça istenmeden açma.
  `kazanim-test*` üç zamanlayıcı SİLİNDİ (2026-10-14); kazanım testi KALICI İPTAL (2026-10-24),
  açıkça istenmeden yeniden açma/önerme (birim dosyaları `_arsiv/kazanimtest-systemd/` altında). İSTİSNA: `soru-havuzu-uret.timer` Atakan tarafından bilerek yeniden AÇILDI
  (2026-10-14 itibarıyla açık; her gün 00:00 TR başlar, 06:00'da durur). Kapatma, açıkça istenmeden yapılmaz.
- 9-11 çalışmaları Maarif modeline göre (2026-10-10).
- Ollama'da TEK model `qwen3.8:27b` (iki RTX 3060); başka model kurulmaz. Çağıran
  kod düşünmeyi kapatır (`think:false`). `CUDA_DEVICE_ORDER=PCI_BUS_ID` şart.
- Gömme + reranker Farabi'de `farabi-embed`'de (2026-10-25'ten beri, 2. RTX 3060, `127.0.0.1:8040`, `FARABI_EMBED_URL`); bilgehan yalnız ses düğümü.
- Ses Gemini Live'da, client'ta. Yerel STT/TTS/Pipecat KALICI İPTAL (2026-09-28).
- Open WebUI adı "Atos"; yalnızca iki yönetici.
- Okul ağı SSL-inceleme yapıyor: yeni venv'de certifi'ye MEB sertifikası eklenmeli;
  `HF_HUB_OFFLINE=1` açık.
- Asıl kimlik avahi hostname (`vestel9b` → `vestel9b.local`; sınıfı o belirler); IP ve MAC değişebilir
  (12-A kablosuz olunca MAC de değişti). Önce `getent hosts <hostname>.local`. IP/MAC değişirse:
  `server/tahtalar.json`, dashboard SQLite `tahtalar`, `docs/runbook.md` tablosu.
- Ders programı/zil TEK kaynak: `okul_ana` (PostgreSQL, panel `/admin/okul-verisi`); yayın
  `tahtayoklama/data/{ders_programi,zil}.json` üretir. Okul portalı ve `server/config_dagit.sh`
  (tahtalara dağıtım, `--kuru` önce) bu dosyaları okur. `mudur/ders_programi.json` ESKİ (2026-10-24'ten beri
  kullanılmıyor).
- 10-A CMOS pili bitik (2026-10 itibarıyla): açılışta yanlış tarih (pano geçmişi ezmez).

## Servisler (ayrı systemd birimi + ayrı venv; BİRLEŞTİRME)
| Servis | Dizin | Port | Not |
|---|---|---|---|
| farabi-api | server/ | 8000 | RAG, kitap/PDF, YKS, LLM proxy, tahta auth |
| farabi-yoklama-dashboard | tahtayoklama/dashboard/ | 8010 | yoklama, uzaktan yönetim, servisler |
| farabi-smssistemi | smssistemi/ | 8020 | SMS, rehber, doğum günleri |
| farabi-okul | okul/ | 9090 | dijital okul portalı, smual.app (Cloudflare Tunnel) |
| ollama | — | 11434 | qwen3.8:27b |
| open-webui | /opt/open-webui | 80 | Atos |
Servisler arası bağ = HTTP + HMAC/paylaşılan anahtar. Tek DB istisnası: smssistemi
`yoklama_pano.db`'yi salt-okunur okur. Docker yok.
- Client = ince arayüz (Gemini Live dahil); server = beyin. Server ham LLM metni
  döndürmez: `{status, answer, sources[], latency_ms, request_id}`.
- Tahta dağıtımı: GitHub (`atakanunver/yenifarabi`, PUBLIC) tek kaynak; tahtalar
  doğrudan çeker. Client kodu SSH ile kopyalanmaz.
- Tahta auth: `/api/egitim/*` `X-Farabi-Board-Key` ile, üretimde ZORUNLU.

## Komutlar
| Proje | Test | Üretime alma |
|---|---|---|
| server | `venv/bin/python -m pytest tests/ -q` | `sudo systemctl restart farabi-api` |
| tahtayoklama/dashboard | `venv/bin/python -m unittest discover -p 'test_*.py'` (pytest YOK) | `... restart farabi-yoklama-dashboard` |
| smssistemi | `venv/bin/python -m pytest -q` | `... restart farabi-smssistemi` |
| okul | `cd okul && venv/bin/python -m pytest -q` | `... restart farabi-okul` |
| client | tahtada: `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"` | GitHub push |
- Tek test: pytest projelerinde `venv/bin/python -m pytest tests/test_x.py::test_adi -q` (smssistemi'de `tests/` yok: `pytest test_x.py::test_adi -q`); dashboard'da (dizin `tahtayoklama/dashboard`, modül adı .py'siz) `venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta`.
- CRLF: `okul/` altındaki bazı dosyalar CRLF (`git ls-files --eol`); Python `open()` ile yeniden yazma, `newline=''` kullan ya da Edit aracı.
- Tahta SSH: `server/tahta-ssh.sh [--admin] <derslik> "<komut>"`. Server logu
  yalnızca `journalctl -u farabi-api.service`.
- Lint: `.venv-tools/bin/ruff check <dokunduğun dosya>`; F821/F811/F632 sıfır kalmalı,
  toplam sayı artmamalı. Büyük `--fix`/`format` yapma. `mudur/` kapsam dışı; `dogum/` `_arsiv/dogum/`'a taşındı (2026-10-24).

## Temel Kurallar
1. Client ince; ağır iş sunucuda. 2. Farabi asla dersi bozmaz (servis çökerse tahta çalışır).
3. Tek seferde tek modül. 4. Önce oku, varsayma. 5. Geriye dönük uyumu koru.
6. Büyük refactor: önce plan, onay. 7. Testi atlama/gizleme. 8. Yeni teknoloji/servis/
kütüphane (Docker, Redis, Qdrant, Celery, yeni LLM, bulut API…) için önce onay.
9. `.env`/API anahtarı commit'lenmez, koda yazılmaz. 10. Ölçmeden optimizasyon yok.
11. Bug/özellik: plan Opus, uygulama Sonnet (tek satırlık işte zorunlu değil).
12. Client+server bağlı değişiklikte ikisi birlikte; son kabul fiziksel tahtada Atakan.

## RAG
- Cevap yalnızca retrieval'dan. Skor eşik altı → "Bu konu ders kitabında bulunmuyor."
  `ESIK_RERANK` 0,5; `kitap_id` filtresi; `chunk_egitim` top-20 + `chunk_tablo` top-10,
  rerank birleşimde top-4. Kazanım filtresi YOK. Geri dönüş: `rag.py::TABLO_KAYNAGI`.
- Her cevapta kaynak (`9. Sınıf Biyoloji, s. 84`); chunk sayfa aşmaz; sıcaklık ≤0,2;
  ≤3 cümle; kaynakta olmayan sayı varsa gösterme.

## Gizlilik ve veri
- Öğrenci/veli verisi (yoklama, roster, SMS rehberi) ASLA buluta gitmez. Ses Gemini
  Live'a gider (bilinçli). Kitap metni buluta gidebilir (RAG LLM adımı hâlâ yerel).
- Kazanım testi istisnası: Google Form'a yalnızca soru metni; öğrenci okul no yazar.
- Öğrenci kimliği tutulmaz; ham ses diske yazılmaz. `soru_log` süresiz, silme yok;
  `metrik`'te içerik yok.
- Veri: `/mnt/farabi-data/farabi/` (`DATA_DIR`), PostgreSQL+pgvector.

## Okuma yasakları
`data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`, `**/api_keys.json*`, `*.env`,
`network.txt`, `apikeys.env`, `gizli.json`; `mudur/SINIF/` ve e-Okul/yoklama/SMS dışa aktarımları
(kişisel veri). Halka açık kitap/YKS PDF'leri sayfa aralığıyla okunabilir.
Log >1000 satır/>200 KB ise boyutu bildir, tamamını okumadan sor (grep/tail serbest).
Log, hata avında birincil kanıttır; varsayımla debug etme.

## Çalışma kuralları (kalıcı)
- Analiz/rapor/özet için yeni .md/.pdf oluşturma; cevabı sohbette ver.
- Kalıcı bilgi: `DECISIONS.md`'ye tek satır ("tarih | karar | neden").
- README.md'yi yalnızca Atakan isterse güncelle.
- Kod değişikliğinde tüm dosyayı değil, değişen fonksiyon/bloğu göster.
- Dil: Türkçe; kod ve teknik terimler orijinal.
- Frontend (`tahtayoklama/dashboard/`): önce `tahtayoklama/CLAUDE.md` tasarım bölümü;
  CDN/yeni kütüphane yok.
- Dış ajan çıktısına güvenme, doğrula.
