# Farabi

Sınıf akıllı tahtalarında sesli ders asistanı + aynı sunucuda okul operasyon servisleri (yoklama panosu, SMS, okul portalı).
Monorepo. Bu dosya ortak kurallar + servisler arası resim; alt projelerin kendi `AGENTS.md`'si var (`CLAUDE.md` → `AGENTS.md` sembolik bağı; düzenlemeyi AGENTS.md'de yap).

- ⚠️ `/home/ata/farabi` CANLI ÜRETİM: servisler buradan koşar. Master'a commit = deploy kaynağı; üretime almak = servisi restart.
  Çalışma dizini tek: hangi dal checkout'taysa servisler onu koşar; dal değiştirmek canlı kodu değiştirir. Üretim venv'lerine pip kurma.
- ⚠️ `git sparse-checkout set/reapply` ÇALIŞTIRMA: git'te izlenmeyen canlı dizinleri (`kelebek/`, `kameralar/`,
  `tahtaatlasfarabi/` + `var/atlas.db`, `tahtamasaustuduzeni/`) silebilir. `kiosk/` sparse-checkout dışında.
- Ayrı depolar: `okul3d/` (özel), `tahtaatlasfarabi/` (PUBLIC `atakanunver/farabi-atlas`). Ana depo da PUBLIC: izlenmeyen
  dosyalardan veya `/home/ata/llm-cluster-wiki`'den (şifre içerir) ayrıntı taşıma.
- Kaynaklar: kararlar `DECISIONS.md` (tek satır `tarih | karar | neden`), mimari `docs/mimari.md` (2026-09-13'te donmuş; çelişkide
  bu dosya esas), ağ/dağıtım/SSH/zamanlayıcılar `docs/runbook.md`, sürüm notları `CHANGELOG.md`. `README.md` yalnız Atakan isterse
  güncellenir. `_arsiv/` yalnız okuma.
- AGENTS.md'si olmayanlar: `kelebek/` (sınav salon dağıtımı), `osym/` (ÖSYM/YKS rapor yükleyici, `osym` DB), `arenasinif/`
  (tahta yarışma oyunları; kendi `DECISIONS.md`'si), `anythingllm/` (Atos kurulum + yetenekler), `tahtagoruntuyakala/` (notlar).
- Ders görsel arşivi: `client/ders_gorsel_servis.py` + `client/core/ders_gorsel.py` (tahta, `systemd --user farabi-ders-gorsel`,
  bayrak `ders_gorsel.enabled`, pilot 10-A) → `server/ders_gorsel.py` (`POST /api/ders-gorsel`, `/mnt/farabi-data/farabi/ders_gorselleri/`).

## Canlı durum
- KALICI İPTAL, açıkça istenmeden geri açma/önerme: RAG ve gömme servisi `farabi-embed` (`server/main.py::RAG_AKTIF = False`;
  `kitap_sorusu` aracı kalıntı), otomatik soru üretimi (`soru-havuzu-uret.timer` disabled, 2026-11-07), kazanım testi
  (birimler `_arsiv/kazanimtest-systemd/`), yerel STT/TTS/Pipecat (ses tek yol: client'ta Gemini Live), `farabi-idari-yukle.timer`.
- Soru havuzu hazır soru + görsel arşividir; öğretmen katkısı `soru-katki.timer` (2 dk) LLM ile soru üretmez.
- NAS yedeği `farabi-yedek.timer` pazar 03:30 TR (`~/farabi-yedek/farabi-yedek.py` → `server/yedek/farabi_yedek.py`).
  2026-11-04..07 bağlantı eksikti; uçtan uca doğrulanana dek çalışıyor varsayma.
- 9-11 çalışmaları Maarif modeline göre.
- Planlanan: tahtada "Soruyu çöz" (mevcut `actions/ekrandaki_soruyu_oku.py`'yi tetikler).
- Okul ağı SSL-inceleme yapar: yeni venv'de certifi'ye MEB sertifikası ekle; `HF_HUB_OFFLINE=1`.
- Tahta kimliği avahi hostname (`vestel9b.local` sınıfı belirler); IP/MAC değişir. Önce `getent hosts <hostname>.local`.
  Değişince: `server/tahtalar.json`, dashboard SQLite `tahtalar`, `docs/runbook.md` tablosu. 10-A CMOS pili bitik (yanlış tarih).
- Ders programı/zil TEK kaynak `okul_ana` (PostgreSQL, panel `/admin/okul-verisi`) → `tahtayoklama/data/{ders_programi,zil}.json`;
  okul portalı ve `server/config_dagit.sh` (tahtalara dağıtım, önce `--kuru`) bunu okur. `mudur/ders_programi.json` ESKİ.

## LLM (Ollama, 11434)
- TEK model `qwen3.8:27b`, istemciler **`farabi` takma adıyla** ister (`server/saglayicilar.py`, `smssistemi/app.py`, soruhavuzu,
  Atos `/opt/anythingllm/app/server/.env`, Müdür PC EBYS botu). qwen/codewhale CLI'leri `qwen3.8:27b` adını kullanır (aynı digest).
- Model değişimi = `ollama cp <yeni> farabi`; kod değişmez. Başka adla istek ikinci modeli yükletip `farabi`'yi boşaltır (~50 sn).
  Yeni model kurmak onay ister. Sunucu `OLLAMA_CONTEXT_LENGTH=49152`, `OLLAMA_KEEP_ALIVE=-1`; farklı `num_ctx` yeniden yükletir.
- Çağıran kod `think:false` gönderir (qwen3.x'te düşünme varsayılan açık). `CUDA_DEVICE_ORDER=PCI_BUS_ID` şart. İki RTX 3060'ı da kullanır.
- Açılışta `/usr/local/bin/farabi-ollama-onyukle.sh` yükler; 2026-11-07 sabahı bellekte değildi (nedeni bilinmiyor).
- Ajanlar qwen'i yoğun kullanırken `saglayicilar.py` (30 sn) ve SMS çağrıları kuyrukta bekleyip bulut yedeğine düşebilir.

## Servisler (ayrı systemd birimi + ayrı venv; BİRLEŞTİRME)
| Servis | Dizin | Port | Not |
|---|---|---|---|
| farabi-api | server/ | 8000 | kitap/PDF, YKS, LLM proxy, tahta auth, ders görsel arşivi |
| farabi-yoklama-dashboard | tahtayoklama/dashboard/ | 80 | yoklama, uzaktan yönetim, servisler |
| farabi-smssistemi | smssistemi/ | 8020 | SMS, rehber, doğum günleri |
| farabi-okul | okul/ | 9090 | dijital okul portalı, smual.app (Cloudflare Tunnel) |
| farabi-kelebek | kelebek/ | 8050 | sınav salon dağıtımı |
| farabi-kameralar / farabi-hareket | kameralar/ | 8889 | mediamtx WebRTC (RTSP/API yalnız 127.0.0.1); hareket algılama |
| farabi-okul3d | okul3d/ | 8095, 8096 | 3D dijital ikiz + oda adları API'si |
| sinif-arena | arenasinif/ | 8030 | Sınıf Arenası, Düello, HexaFetih |
| farabi-atlas | tahtaatlasfarabi/ | 8099 | harita/küre oyunları, kendi `var/atlas.db`'si |
| pm2-anythingllm | /opt/anythingllm | 8010 | Atos (AnythingLLM, PM2, Docker'sız; collector 8888) |
- Servisler arası bağ = HTTP + HMAC/paylaşılan anahtar. Tek DB istisnası: smssistemi `yoklama_pano.db`'yi salt-okunur okur. Docker yok.
- Client = ince arayüz; server = beyin, ham LLM metni döndürmez: `{status, answer, sources[], latency_ms, request_id}`.
- Tahta dağıtımı: GitHub (`atakanunver/yenifarabi`, PUBLIC) tek kaynak, tahtalar doğrudan çeker; client kodu SSH ile kopyalanmaz.
- Tahta auth: `/api/egitim/*` `X-Farabi-Board-Key` ile, üretimde ZORUNLU.

## Atos veri erişimi (dashboard `POST /api/okul/sql`)
- Akış: `anythingllm/skills/` (`sql-sorgu`, `tablo-dosyasi`, ortak `_ortak/okul.js`) → `tahtayoklama/dashboard/okul_bilgisi.py::sql`
  → `okul_sql.py`. Dağıtım `anythingllm/kur_yetenekler.sh` (`__SEMA__` ← `sema_aciklamasi.txt`, `__ANAHTAR__` ←
  `config/okul.json::anahtar`, depoya yazılmaz). Şema değişince `sema_aciklamasi.txt`'yi güncelle, betiği yeniden çalıştır.
- Güvenlik sunucuda: yerel IP + `X-Farabi-Okul-Key` + `X-Farabi-Rol: admin`. Her çağrıda kaynaklar bellek içi SQLite'a kopyalanır;
  tek ifade, `set_authorizer` (yalnız SELECT + `IZINLI_TABLOLAR`), 200 satır (`azami_satir` ≤ 2000), 3 sn. Parola/oturum/anahtar
  tabloları kopyalanmaz; hata metni DSN/yol sızdırmaz (`SqlHatasi`); SMS/osym kaynağı yoksa sessizce atlanır.
- Kaynaklar: `okul_ana` (`atos_ro`), `yoklama_pano.db`, `smssistemi.db`, `mudur/SINIF/tcler`, `osym` DB (`osym_ro`), `okul_ana.dosya`/
  `dosya_satir` (yükleyici `tahtayoklama/dashboard/scripts/okul_dosya_yukle.py`), türetilmiş görünümler.
  Yeni tablo = `okul_sql.py` sabiti + `IZINLI_TABLOLAR` + `okul_bilgisi.py::sql` birleşimi + şema açıklaması.
- SMS yeteneği `anythingllm/skills/sms-gonder/`: taslak → AnythingLLM kullanıcı onayı → gönderim; otomatik onay/zamanlama yok, toplu
  gönderim SMS arayüzündeki sayı onayına yönlenir. Onay `User approved the tool execution.` yanıtına bağlı: AnythingLLM güncellenince
  kontrol et. `__SMS_ANAHTAR__` ← `smssistemi/config/arac.json::anahtar`. Test: `node --test anythingllm/tests/sms-gonder.test.js`.

## Komutlar (proje dizininden; client tahtada)
| Proje | Test | Üretime alma |
|---|---|---|
| server | `venv/bin/python -m pytest tests/ -q` | `sudo systemctl restart farabi-api` |
| tahtayoklama/dashboard | `venv/bin/python -m unittest discover -p 'test_*.py'` (pytest YOK) | `... restart farabi-yoklama-dashboard` (08:00-17:00 TR dışında) |
| smssistemi | `venv/bin/python -m pytest -q` | `... restart farabi-smssistemi` |
| okul | `venv/bin/python -m pytest -q` | `... restart farabi-okul` |
| client | `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"` | GitHub push |
- Diğer: kelebek `venv/bin/python -m pytest tests -q`; osym `venv/bin/python -m unittest`; arenasinif `venv/bin/python -m pytest -q`;
  soruhavuzu (kökten) `server/venv/bin/python -m pytest soruhavuzu/tests -q`; tahtaayar `python3 -m unittest test_tahta_fix_uygula -v`;
  benchmark ve kameralar: kendi AGENTS.md'si; kiosk `kiosk/tests/test_okul_panel.py` (sparse-checkout dışı).
- Tek test: `venv/bin/python -m pytest tests/test_x.py::test_adi -q` (smssistemi: `test_x.py::test_adi`); dashboard:
  `venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta`.
- Lint: `.venv-tools/bin/ruff check <dokunduğun dosya>`; F821/F811/F632 sıfır, toplam artmamalı. Büyük `--fix`/`format` yok. `mudur/` kapsam dışı.
- CRLF: `okul/` altında bazı dosyalar CRLF (`git ls-files --eol`); Python ile yeniden yazarken `newline=''` ya da Edit aracı.
- Tahta SSH: `server/tahta-ssh.sh [--admin] <derslik> "<komut>"`. Server logu yalnız `journalctl -u farabi-api.service`.

## Temel kurallar
1. Client ince; ağır iş sunucuda. 2. Farabi asla dersi bozmaz (servis çökerse tahta çalışır). 3. Tek seferde tek modül.
4. Önce oku, varsayma. 5. Geriye dönük uyumu koru. 6. Büyük refactor: önce plan, onay. 7. Testi atlama/gizleme.
8. Yeni teknoloji/servis/kütüphane/LLM/bulut API için önce onay. 9. `.env`/API anahtarı commit'lenmez, koda yazılmaz.
10. Ölçmeden optimizasyon yok. 11. Client+server bağlı değişiklikte ikisi birlikte; son kabul fiziksel tahtada Atakan.
- Dil Türkçe; kod ve teknik terimler orijinal. Kod değişikliğini anlatırken yalnız değişen bloğu göster.
- Frontend (`tahtayoklama/dashboard/`): önce `tahtayoklama/AGENTS.md` tasarım bölümü; CDN/yeni kütüphane yok.

## Gizlilik ve okuma yasakları
- Öğrenci/veli verisi (yoklama, roster, SMS rehberi) ASLA buluta gitmez. Ses Gemini Live'a gider (bilinçli); kitap metni gidebilir.
- Öğrenci kimliği tutulmaz; ham ses diske yazılmaz. `soru_log` süresiz, silme yok; `metrik`'te içerik yok. Veri: `/mnt/farabi-data/farabi/`.
- Okuma: `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`, `**/api_keys.json*`, `*.env`, `network.txt`, `apikeys.env`, `gizli.json`,
  `analizatakanekim2026.txt`, `mudur/SINIF/`, e-Okul/yoklama/SMS dışa aktarımları (kişisel veri). Kitap/YKS PDF'leri sayfa aralığıyla.
- Log >1000 satır/>200 KB ise boyutu bildir, tamamını okumadan sor (grep/tail serbest; ör. `soruhavuzu_uret_12.log`). Hata avında log
  birincil kanıttır; varsayımla debug etme.
