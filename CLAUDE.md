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
soruhavuzu, kazanimtest, okul, kameralar, kiosk; `kelebek/` (sınav salon dağıtım paneli, :8050,
systemd `farabi-kelebek`; `kameralar/` ile birlikte git'te izlenmez, `.gitignore`'da) ve `osym/` (ÖSYM/YKS rapor yükleyici, `osym` DB), `arenasinif/` (tahta yarışma oyunları, :8030, systemd `sinif-arena`; kendi `DECISIONS.md`'si var) ile `anythingllm/` için CLAUDE.md yok; Open WebUI kodu `_arsiv/openwebui/`, `_arsiv/webui-tema/`'dedir). Bu dosya: ortak kurallar + servisler arası resim.

- Kararlar/neden: `DECISIONS.md` (`grep "## <tarih>"`). Mimari (2026-09-13'te
  donmuş, çelişkide bu dosya esas): `docs/mimari.md`. Ağ envanteri, dağıtım,
  SSH, zamanlayıcılar: `docs/runbook.md`. Sürüm notları: `CHANGELOG.md`;
  `README.md` yalnızca Atakan isterse güncellenir. Eski analiz/planlar: `_arsiv/` (okuma).
- ⚠️ `/home/ata/farabi` CANLI ÜRETİM — servisler buradan koşuyor. Master'a commit
  = deploy kaynağı; üretime almak = ilgili servisi restart.
  Çalışma dizini tek: hangi dal checkout'taysa servisler onu koşar; dal değiştirmek de canlı kodu değiştirir.
  Özellik dalında çalışırken (örn. `atos-anythingllm-gemma`) master'a merge edilmeden restart canlıya o dalı alır.

## Mevcut durum (kalıcı)
- `farabi-idari-yukle.timer` KALICI KAPALI (2026-10-10), açıkça istenmeden açma.
  `kazanim-test*` üç zamanlayıcı SİLİNDİ (2026-10-14); kazanım testi KALICI İPTAL (2026-10-24),
  açıkça istenmeden yeniden açma/önerme (birim dosyaları `_arsiv/kazanimtest-systemd/` altında). İSTİSNA: `soru-havuzu-uret.timer` Atakan tarafından bilerek yeniden AÇILDI
  (2026-10-14 itibarıyla açık; her gün 00:00 TR başlar, 06:00'da durur). Kapatma, açıkça istenmeden yapılmaz.
- 9-11 çalışmaları Maarif modeline göre (2026-10-10).
- Ollama'da Farabi'nin VARSAYILAN modeli `gemma4:12b` (Gemma 4 12B Q4_K_M; tools/thinking/vision; 2026-10-25) (iki RTX 3060). 2026-10-31'den beri
  her uygulama ihtiyacı olan modeli o an yükler (Atakan kararı): kod ajanları (qwen, codewhale) `qwen3.8:27b` (iki karta yayılır, ~19 GB) kullanır.
  İkisi aynı anda sığmaz; Ollama boştaki modeli boşaltıp isteneni yükler, geçiş ~50 sn (ölçüldü: qwen→gemma 48 sn). `saglayicilar.py` Ollama
  çağrısı 30 sn'de bulut yedeğine düşer, soru havuzu 180 sn bekler. Yeni model kurmak yine onay ister. TÜM istemciler aynı bağlamı
  kullanır: sunucu `OLLAMA_CONTEXT_LENGTH=49152` (drop-in `zz-baglam.conf`; farklı `num_ctx` modeli yeniden yükletir). 49152 tek karta (GPU0 ~9 GB) sığar, 65536 ikinci karta taşıp `farabi-embed` ile çakışır.
  Açılışta `/usr/local/bin/farabi-ollama-onyukle.sh` modeli yükler. Çağıran kod düşünmeyi kapatır (`think:false`; Gemma'da düşünme varsayılan AÇIK). `CUDA_DEVICE_ORDER=PCI_BUS_ID` şart.
- Gömme + reranker servisi `farabi-embed` (2. RTX 3060, `127.0.0.1:8040`, `FARABI_EMBED_URL`) 2026-10-30'dan beri BİLEREK durdurulmuş ve disabled;
  RAG kapalı (`server/main.py::RAG_AKTIF = False`). Açıkça istenmeden başlatma; RAG açılırsa önce bu servis açılır. bilgehan yalnız ses düğümü.
- Ses Gemini Live'da, client'ta. Yerel STT/TTS/Pipecat KALICI İPTAL (2026-09-28).
- Atos = AnythingLLM (Docker'sız, `/opt/anythingllm`, PM2 + `pm2-anythingllm.service`, port 8010, tek kullanıcı modu + erişim parolası; kurulum/yetenekler `anythingllm/`). Open WebUI 2026-10-25'te kaldırıldı, verisi `/mnt/farabi-data/farabi/arsiv/open-webui-atos-20261025.tgz`. Veri erişimi: aşağıdaki "Atos veri erişimi".
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
| farabi-yoklama-dashboard | tahtayoklama/dashboard/ | 80 | yoklama, uzaktan yönetim, servisler |
| farabi-smssistemi | smssistemi/ | 8020 | SMS, rehber, doğum günleri |
| farabi-okul | okul/ | 9090 | dijital okul portalı, smual.app (Cloudflare Tunnel) |
| farabi-kelebek | kelebek/ | 8050 | sınav salon dağıtım paneli |
| farabi-embed | server/embed_servisi/ (server venv) | 127.0.0.1:8040 | gömme + rerank (bge-m3), 2. RTX 3060; 2026-10-30'dan beri bilerek kapalı (RAG kapalı) |
| farabi-kameralar | kameralar/ | 8889 | mediamtx (WebRTC; RTSP/API yalnız 127.0.0.1), ffmpeg on-demand |
| farabi-hareket | kameralar/hareket/ | — | hareket algılama + hareketsiz kayıt temizleme |
| sinif-arena | arenasinif/ | 8030 | tahta yarışma oyunları (Sınıf Arenası, Düello, HexaFetih); unit kopyası `arenasinif/sinif-arena.service` |
| ollama | — | 11434 | gemma4:12b |
| pm2-anythingllm | /opt/anythingllm | 8010 | Atos (AnythingLLM; collector 8888) |
Servisler arası bağ = HTTP + HMAC/paylaşılan anahtar. Tek DB istisnası: smssistemi
`yoklama_pano.db`'yi salt-okunur okur. Docker yok.
- Client = ince arayüz (Gemini Live dahil); server = beyin. Server ham LLM metni
  döndürmez: `{status, answer, sources[], latency_ms, request_id}`.
- Tahta dağıtımı: GitHub (`atakanunver/yenifarabi`, PUBLIC) tek kaynak; tahtalar
  doğrudan çeker. Client kodu SSH ile kopyalanmaz.
- Tahta auth: `/api/egitim/*` `X-Farabi-Board-Key` ile, üretimde ZORUNLU.

## Atos veri erişimi (dashboard `POST /api/okul/sql`)
Akış: Atos agent yetenekleri `sql-sorgu` / `tablo-dosyasi` (`anythingllm/skills/`, ortak istemci `_ortak/okul.js`)
→ `tahtayoklama/dashboard/okul_bilgisi.py::sql` → `okul_sql.py`. Yetenekler `anythingllm/kur_yetenekler.sh` ile
`/opt/anythingllm/storage/plugins/agent-skills` altına dağıtılır (`__SEMA__` ← `sema_aciklamasi.txt`, `__ANAHTAR__` ←
`config/okul.json::anahtar`; anahtar depoya yazılmaz). Şema/tablo listesi değişince `sema_aciklamasi.txt`'yi de güncelle, betiği yeniden çalıştır.
- Güvenlik burada, istemcide değil: yalnız yerel IP + `X-Farabi-Okul-Key` + `X-Farabi-Rol: admin` (uç öğrenci/veli telefonu, TC, rehberlik/disiplin dosyaları döndürür).
  Her çağrıda kaynaklar bellek içi SQLite'a kopyalanır; tek ifade, `set_authorizer` (yalnız SELECT + `IZINLI_TABLOLAR`),
  200 satır (`azami_satir` ile en çok 2000), 3 sn. Parola/oturum/anahtar tabloları kopyaya hiç alınmaz.
- Kaynaklar: `okul_ana` (PG, `atos_ro`), `yoklama_pano.db`, `smssistemi.db`, `mudur/SINIF/tcler` (TC), `osym` DB (`osym_ro`,
  `okul.json::osym_dsn`; tablolar `osym_*` + `mezun`), `okul_ana.dosya`/`dosya_satir` (Excel/Word içeriği; yükleyici
  `tahtayoklama/dashboard/scripts/okul_dosya_yukle.py`), türetilmişler `ogrenci_genis`, `ogretmen`, `ogretmen_programi`, `kazanim`, `simdi`.
  Yeni tablo = `okul_sql.py`'de sabit + `IZINLI_TABLOLAR` + `okul_bilgisi.py::sql` birleşimi + şema açıklaması.
- SMS ve osym kaynakları yoksa sessizce atlanır (diğer tablolar çalışır); hata metinleri DSN/yol sızdırmaz (`SqlHatasi`).
- Test: `cd tahtayoklama/dashboard && venv/bin/python -m unittest test_okul_sql`. Dashboard restart'ı ders saati dışında (08:00-17:00 TR dışı).
- Bu çalışma dizininde `anythingllm/` ve `kiosk/` sparse-checkout dışındadır (diskte yok; `git show HEAD:<dizin>/<dosya>` ya da `git sparse-checkout add <dizin>`).

## Komutlar
| Proje | Test | Üretime alma |
|---|---|---|
| server | `venv/bin/python -m pytest tests/ -q` | `sudo systemctl restart farabi-api` |
| tahtayoklama/dashboard | `venv/bin/python -m unittest discover -p 'test_*.py'` (pytest YOK) | `... restart farabi-yoklama-dashboard` |
| smssistemi | `venv/bin/python -m pytest -q` | `... restart farabi-smssistemi` |
| okul | `cd okul && venv/bin/python -m pytest -q` | `... restart farabi-okul` |
| client | tahtada: `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"` | GitHub push |
- Diğer projeler: kelebek `cd kelebek && venv/bin/python -m pytest tests -q`; osym `cd osym && venv/bin/python -m unittest` (pytest YOK); arenasinif `cd arenasinif && venv/bin/python -m pytest -q`;
  soruhavuzu `server/venv/bin/python -m pytest soruhavuzu/tests -q`; tahtaayar `cd tahtaayar && python3 -m unittest test_tahta_fix_uygula -v`;
  benchmark (pytest'e bağlı değil, DB'ye yazan betikler içerir) ve kameralar (test yok) için kendi `CLAUDE.md`'sine bak; kiosk testi `kiosk/tests/test_okul_panel.py` (sparse-checkout dışı).
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
`network.txt`, `apikeys.env`, `gizli.json`, `analizatakanekim2026.txt`, `soruhavuzu_uret_12.log` (büyük log; grep/tail serbest); `mudur/SINIF/` ve e-Okul/yoklama/SMS dışa aktarımları
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
