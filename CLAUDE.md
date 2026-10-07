# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Farabi

Sınıf akıllı tahtalarında çalışan sesli ders asistanı + aynı sunucuda koşan
okul operasyon servisleri (yoklama panosu, SMS).

- **Bu dosya = güncel durum + kurallar.** Tarihli olay anlatımları, kök neden
  hikâyeleri ve "neden böyle" gerekçeleri `DECISIONS.md`'de (2026-09-25'te
  buradan taşınanlar dosyanın sonundaki "Arşiv" bölümünde). Bir notun
  ayrıntısı için `grep "## <tarih>" DECISIONS.md`.
- Detaylı mimari: `@docs/mimari.md` §0–§14 (§15 yok). ⚠️ İçeriği
  **2026-09-13'te donmuş**, sonraki değişiklikleri yansıtmaz; çelişkide BU
  dosya esas. Dosya kaybolursa yeniden üretme: `git show
  3f26d71^:docs/mimari.md` ile geri al.
- **Her alt projenin kendi `CLAUDE.md`'si var** (komutlar + o projenin
  ayrıntısı orada; o dizinde çalışırken otomatik yüklenir): `client/`,
  `server/`, `tahtayoklama/`, `smssistemi/`, `tahtaayar/`, `benchmark/`,
  `mudur/`, `dogum/`, `soruhavuzu/`. Bu dosya ortak kurallar + servisler arası resim.

## Güncel durum (2026-10-06)

- **Tahta istemcisi (2026-10-06):** 8 tahtada `~/tahtayoklama/tahta_istemci.py`
  (`systemd --user` birimi `tahta-istemci`) yoklama kayıtlarını panoya HTTP ile
  iter (`/api/v1/tahta/*`, tahta başına token), 60 sn'de bir nabız atar,
  roster/zil/ders programı/kazanımları çeker. SSH artık yedek yol (nabzı
  taze tahta taranmaz; saatte bir tam tarama). Ayrıntı `tahtayoklama/CLAUDE.md` §3.1.
- **Yoklama ekranı (2026-10-06):** başlıkta ders adı (ders dışında `BOŞ`),
  altında haftanın kazanımı — yıllık planlardan
  (`/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027/`)
  `tahtayoklama/dashboard/scripts/kazanim_yukle.py` üretir; öğretmen deftere
  yazar, plan değişince script + bağımsız denetim yeniden çalıştırılmalı.
- **Farabi plan kazanımı (2026-10-06):** client ders başında `GET /api/egitim/kazanim`
  (`server/kazanim.py`) ile bu haftanın kazanımını çerçeveye alır ("yıllık plan, bu
  hafta"), konuyu öğretmene yine sorar; öğretmenin kazanımı önceliklidir.
- **Ders programı düzeltmesi:** `SOTarih` = Ortak Türk Tarihi (okulda Osmanlı
  Türkçesi YOK). Tahtaların Farabi client kopyası (`client/config/
  ders_programi.json`) `config_dagit.sh` ile ayrıca güncellenmeli.
- **10-A CMOS pili bitik:** açılışta son kapanış saatiyle başlar, NTP 1-2 dk
  sonra düzeltir; o aralıkta yanlış tarihli yoklama kaydı geçmiş günü EZEMEZ
  (pano koruması). Pil değiştirilmeli.
- **Open WebUI adı "Atos" (2026-10-05):** yalnızca iki yönetici (ortak
  Öğretmen/İdare/Tahta hesapları pending); yönetici e-postaları
  `openwebui/.env::YONETICI_EPOSTALAR`. Yalnızca-İdare araçlar: Belge Kalıcı
  Kayıt (`server/belge_arsiv.py`), SMS ve Hatırlatma (`smssistemi/arac_api.py`).
  Aşağıdaki "Farabi" adlı Open WebUI notları bu tarihten önce.
- **Zamanlanmış işler:** `farabi-idari-yukle.timer` (her gece 23:30 UTC =
  02:30 TR, `mudur/` yeni belgeleri RAG'a), `soru-havuzu-uret.timer`
  (hafta içi 14:15 UTC = 17:15 TR, hafta sonu 05:00 UTC; ders saatinde
  kendiliğinden durur) — bkz. `soruhavuzu/CLAUDE.md`.
  `kazanim-test.timer` (hafta içi 13:30 UTC = 16:30 TR; kazanım testi →
  Excel/Word + Google Form, başlangıçta SMS'siz) — bkz. `kazanimtest/CLAUDE.md`
  (2026-10-07; timer henüz `/etc`'ye kopyalanmadı).
- **RAG kısmen açık (2026-10-03, ikinci karar):** `server/main.py::
  RAG_AKTIF = True` ama yalnızca bge-m3 **CPU**'da; reranker YÜKLENMEZ
  (`RERANK_YUKLE = False`, CPU'da ~10 sn/soru ölçüldü). Open WebUI Farabi
  modları (`POST /api/webui/ara`) yalnızca vektör aramasıyla çalışır;
  tahtadaki `kitap_sorusu` (`/api/egitim/question`) eskisi gibi `hata`
  döner. İki GPU Ollama'da. Ölçüm DECISIONS.md 2026-10-03.
- **Open WebUI = "Farabi" (port 80, 2026-10-03):** 14 mod (branş öğretmenleri,
  Derin Düşünme, Müdür Yardımcısı — yalnızca İdare), `farabi_kaynak` inlet
  filtresi, ortak `Öğretmen`/`İdare` hesapları + tahtalar için yönetici
  olmayan `tahta` hesabı. Kaynak: `openwebui/` (`kur.py` tekrar
  çalıştırılabilir; promptlar `openwebui/promptlar/`; şifreler yalnızca
  gitignore'lu `openwebui/.env`). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-10-03-openwebui-farabi-modlar*`.
  Ek: yalnızca-admin `farabi-yonetim` modeli + `farabi_yonetim` aracı
  (tahta durumu/eylem/yeniden başlatma; her değiştiren eylem onay
  penceresinden geçer). `kur.py` her çalışışında kayıt kapalı + varsayılan
  rol `user` ayarını zorlar.
- **Yerel LLM `qwen3.8:27b`** (2026-10-03): Ollama'daki TEK model — özel
  `farabi-qwen3.8:27b` ve `qwen2.5:14b` takma adı kaldırıldı, başka model
  kurulmaz. Bağlam 16384 (`OLLAMA_CONTEXT_LENGTH`, ollama.service) + KV
  cache q8_0 (`ollama.service.d/zz-kvtest.conf`) → %100 GPU, 32-42 tok/s
  (f16 KV'de %6 CPU'ya taşıyordu; 32k f16 %11 CPU). İki RTX 3060,
  süresiz bellekte (`OLLAMA_KEEP_ALIVE=-1`
  + açılışta `/usr/local/bin/farabi-ollama-onyukle.sh`). Farabi sistem promptu
  `server/ollama/farabi_sistem.txt`'te; `server/saglayicilar.py` sistem
  mesajı olmayan Ollama isteklerine ekler. Çağıran kod düşünmeyi kapatmalı
  (`think:false` / `reasoning_effort="none"`).
- **2026-10-02:** her alt projeye kendi `CLAUDE.md`'si eklendi; client
  Gemini Live token kullanımını `farabi.log`'a `TOKEN` satırları olarak
  yazıyor (ayrıntı `client/CLAUDE.md`).
- **Farabi client:** 8 tahtada kurulu — 7 sınıf (9-A, 9-B, 10-A, 11-A, 11-B,
  12-A, 12-B) + `fenlab`. Tablo: aşağıda "Ağ Envanteri".
- **Tahtayoklama:** aynı 8 tahtada kurulu. Tahta tarafı
  `tahtayoklama/yoklama.py`; sunucu tarafı `tahtayoklama/dashboard/`.
- **Gemini anahtarı:** 8 kurulumda tek, çalışan anahtar (faturalandırma
  engeli 2026-09-25'te çözüldü). "Farabi susuyor" belirtisi faturalandırma
  değil `thinking_config` olabilir — DECISIONS.md 2026-09-25 / 2026-09-27.
- 2026-10-06: mikrofonsuz mod kullanıcı kararıyla koddan kaldırıldı; Farabi her zaman mikrofonlu çalışır (tahta mikrofonları bozuksa öğretmen MİKROFON düğmesiyle sessize alır). Ders içi düğmeler: DURDUR, DEVAM ET, ⏹ DERSİ BİTİR (çift dokunuş, 2026-09-27).
- ⛔ **Yerel ses (Pipecat) KALICI OLARAK İPTAL (2026-09-28)** — bkz.
  "Şu An Yapılmayacaklar"; ayrıntı DECISIONS.md 2026-09-28.
- **`client/core/prompt.txt` hâlâ client'ta.** Server'a taşınması
  PLANLANDI, YAPILMADI (mimari.md §0).
- **Tahta gece/sabah bakımı PLANLANDI, UYGULANMADI.** Spec
  `docs/superpowers/specs/2026-09-28-tahta-gece-sabah-bakim-design.md`,
  plan `docs/superpowers/plans/2026-09-29-tahta-gece-sabah-bakim.md`;
  `tahtayoklama/dashboard/tahta_bakim.py` henüz yok (2026-10-01).
- **Ders planı hattı Faz A tamam (2026-09-30):** `POST /api/egitim/
  ders_plani` (`server/ders_plani.py`, bulut zinciri deepseek > groq >
  cohere, Ollama bilerek yok). Client tarafı henüz bağlı değil.
- **Uzaktan yönetim denetim kaydı (2026-10-01):** her `/admin/uzaktan`
  eylemi dashboard'un `uzaktan_denetim` tablosuna yazılır; oturumsuz
  tarayıcı isteği `/giris`'e yönlenir. Ayrıntı `tahtayoklama/CLAUDE.md` §5.
- **IP değil hostname/MAC esas alınır.** DHCP kirası bozulunca IP değişiyor
  (12-A, 2026-09-22). Kanonik kayıt `server/tahtalar.json`. Bir tahtanın IP'si
  değişirse **üç yer** güncellenir: `server/tahtalar.json` (uzaktan yönetim,
  `config_dagit.sh`, `tahta-ssh.sh`, `tahtaayar` buradan okur), dashboard
  SQLite `tahtalar` tablosu (yoklama polling'i, panodaki "başlat" ve roster
  yükleme buradan okur), bu dosyadaki tablo.
- ⚠️ **Ders programı ve zil saatleri birden çok kopya, otomatik senkron
  yok:**
  - Ders programı: `mudur/ders_programi.json` (kaynak) → tahtaların
    `client/config/ders_programi.json`'ı (`mudur/ders_programi_yukle.py`
    ya da `server/config_dagit.sh` dağıtır). `tahtayoklama/data/
    ders_programi.json` dashboard'un bilinçli bağımsız kopyası (pano
    etiketi), `tahtayoklama/dashboard/scripts/ders_programi_yukle.py` ile
    aynı PDF'ten ayrıca üretilir.
  - Zil: `tahtayoklama/data/zil.json` kaynak → tahtaların
    `client/config/zil.json` + `~/tahtayoklama/data/zil.json`'ı
    (`server/config_dagit.sh` ya da `dashboard/scripts/zil_yukle.py`).

## Mimari: servisler + tahta istemcisi

Hepsi bu makinede (`farabi.local`), **her servis ayrı systemd birimi, ayrı
venv**.
Kod paylaşmazlar, birini deploy etmek diğerini etkilemez; üretime almak =
ilgili servisi restart etmek. Servisler birleştirilmez; servisler arası bağ =
HTTP + HMAC/paylaşılan anahtar.

| Servis | Dizin | Port | Ne yapar |
|---|---|---|---|
| `farabi-api` ("Brain") | `server/` | 8000 | RAG (CPU, reranker yok), Open WebUI kaynak araması, kitap içeriği/PDF render, YKS, bulut LLM proxy, dosya işleme, tahta auth |
| `farabi-yoklama-dashboard` | `tahtayoklama/dashboard/` | 8010 | yoklama, roster, zil/ders programı, uzaktan yönetim (`/admin/uzaktan`); `/api/ajan` makine API'si (yalnızca 127.0.0.1 + `X-Farabi-Ajan-Key`; anahtar gitignore'lu `tahtayoklama/dashboard/config/ajan.json`; Open WebUI "Atos Yönetim" aracı kullanır); `/api/v1/tahta/*` tahta istemcisi API'si (LAN, tahta başına token) |
| `farabi-smssistemi` | `smssistemi/` | 8020 | toplu/kişisel SMS, rehber, Doğum Günleri, Yoklama SMS; `/api/arac/*` (Atos SMS aracı, `X-Sms-Arac-Key`) |
| `ollama` | — | 11434 | `qwen3.8:27b` (iki GPU, tek model), LAN'a açık, paylaşılan yerel LLM |
| `open-webui` | `/opt/open-webui` (kurulum `openwebui/kur.py`) | 80 | "Atos" sohbet arayüzü (2026-10-05'e kadar "Farabi") — yalnızca iki yönetici, kaynaklı cevap |

- **Tek bilinçli DB paylaşımı istisnası:** smssistemi'nin `/yoklama-sms`'i
  dashboard'un `yoklama_pano.db`'sini **salt-okunur, doğrudan** okur (bkz.
  DECISIONS.md 2026-09-23). Dashboard ↔ smssistemi başka bağı yok: HMAC SSO
  köprüsü (`/sms-git`, `/dogum`, `/otomasyon-git` → smssistemi `/sso`).
- **Uzaktan yönetim** (`/admin/uzaktan`): ekran karart/kaldır, yoklama
  aç/kapat, duvar kağıdı, anlık ekran görüntüsü (`GET /admin/uzaktan/
  ekran-goruntusu/{tahta_adi}?ham=1`), çoklu tahta seçimi. Tahtaya doğrudan
  `ogretmen` olarak SSH (`~/.ssh/id_ed25519_tahta`), sudo gerektirmez. İstisna: yeniden
  başlatma `etapadmin` + dar sudoers ile (`/etc/sudoers.d/farabi-reboot`, tahtaayar
  `reboot_sudoers`), okul saatinde reddedilir.

**Client ↔ Server ayrımı (KESİN, mimari.md §0):** client = yalnızca tahtadaki
arayüz/etkileşim yüzeyi (Gemini Live ses oturumu dahil); server = beyin (RAG,
sistem promptu, iş mantığı, sağlayıcı routing). Ses kalıcı olarak Gemini
Live'da, client'ta (2026-08-11 kararı; 2026-09-25'te açılan yerel ses
denemesi 2026-09-28'de kalıcı iptal edildi); client'taki tek bulut anahtarı
Gemini.

**Tahtaya dağıtım:** GitHub tek doğru kaynak (`github.com/atakanunver/
yenifarabi`, PUBLIC). Tahtalar GitHub'dan **doğrudan** çeker, server arada
değil: `server/farabi-kurulum.sh` `client/`'ı sparse-checkout ile klonlar,
tahtadaki `farabiguncelle.sh` = `git fetch` + `git reset --hard
origin/master` (günlük cron), `farabi-heartbeat.sh` 15 dk'da bir `POST
/api/client/heartbeat`. İstisna: **9-A** tam klon yapısını korur
(`~/farabi/repo`, client `~/farabi/repo/client`'ta) — mekanizma aynı.
Gitignore'lu ayarlar (`zil.json`, `ders_programi.json`, `api_keys.json`'ın
ortak alanları: Gemini anahtarı, `mikrofon`, `sunucu_url`) git ile gitmez,
`server/config_dagit.sh [--kuru] [tahta...]` ile SSH'tan dağıtılır; ortak
değerlerin kaynağı `server/config/api_keys_tahta_ortak.json` (gitignore'lu).
`farabi.local` kendi `server/` kodunu ayrıca GitHub'dan çeker.

**Tahta auth:** her `/api/egitim/*` router'ı `auth.dogrula_tahta`'ya bağlı,
üretimde ZORUNLU. Client tüm isteklerde `core.tahta.auth_headers()` ile
`X-Farabi-Board-Key` gönderir. Anahtarlar `server/config/api_keys.json::
board_keys` ve her tahtanın `client/config/api_keys.json`'ında;
`auth._board_keys()` dosyayı her istekte okur (restart gerekmez). Acil geri
dönüş: servis override'ına `Environment="FARABI_AUTH_REQUIRED=0"`.

### `client/` — PyQt6 tahta istemcisi

Detay (modül haritası, araçlar, `config/` alanları) `client/CLAUDE.md`'de.
Servisler arası resim için: `main.py` Gemini Live oturumunu ve araç
dağıtımını yönetir; modelin çağırdığı araçların tek kaynağı
`actions/kayit.py`; `core/saglayicilar.py` sağlayıcı havuzu DEĞİL, server'a
ince HTTP proxy. Server'a bağlı araçlar sunucu ulaşılamazsa sessizce
kısıtlayıcı metne düşer (Kural 2). Client'ın kendi kitap/YKS deposu yok.

### `server/` — FastAPI Brain

Detay (uç nokta tablosu, tahta script'leri, değişirken bozulmaması
gerekenler) `server/CLAUDE.md`'de. Servisler arası resim için bilinmesi
gerekenler:

- Uçlar `/api/egitim/*` (tahta auth'lu) + `/api/client/{heartbeat,durum}`
  + `/health`, `/ready`. RAG: `/api/egitim/question` (reranker yok → `hata`) ve Open WebUI için `POST /api/webui/ara` (`webui.py`, ayrı anahtar); içerik/PDF
  (`icerik.py`), YKS (`yks.py`), bulut LLM proxy (`saglayicilar.py` +
  `proxy.py`), ders planı (`ders_plani.py`), geçmiş ders hatırlama
  (`ders_hafizasi.py`), dosya işleme (`dosya.py`) ayrı router'lar.
- Tek süreç tüm tahtalara hizmet eder: oturum durumu `derslik` anahtarlı
  tutulur (`icerik.py::_SON_KITAP`, `yks.py::_OTURUMLAR`).
- Bulut anahtarları YALNIZCA `server/config/api_keys.json`'dan okunur
  (kökteki `apikeys.env`'den değil; yeni anahtar ikisine de yazılır).
  `.gitignore` desen tabanlı (`*.env`, `**/api_keys*`,
  `!**/api_keys.example.json`) — yeni anahtar dosyasını `git check-ignore`
  ile doğrula.

### Sunucu ortamı — tuzaklar

- **GPU:** 2× RTX 3060 12GB, **ikisi de Ollama'nın** (2026-10-03):
  `ollama.service.d/override.conf` → `CUDA_VISIBLE_DEVICES=0,1` (ana
  birimdeki `=1`'i ezer), context 16384. `farabi-api` GPU kullanmıyor
  (bge-m3 CPU'da); embedding/reranker GPU'ya alınırsa GPU 0'a biner ve 27B
  model tamamen sığmaz (DECISIONS.md 2026-10-03).
  `CUDA_DEVICE_ORDER=PCI_BUS_ID` şart — yoksa CUDA numaralandırması
  `nvidia-smi`'ninkiyle ters çıkabiliyor. 2026-10-03 ölçümü: model 66/66
  katman GPU'da, kart başına ~3 GB boş. Yeni GPU işi planlanırken o an
  `nvidia-smi` ile yeniden ölç.
- **Ollama model indirme proxy'den `ollama pull` ile ÇALIŞMIYOR** (paralel
  parça bağlantıları EOF ile kesiliyor); blob'lar tek akışla curl ile
  indirilip elle yerleştirilir — DECISIONS.md 2026-10-03.
- **Okul ağı SSL-inceleme yapıyor (MEB-CERT-TTVPN).** Sertifika sistem güven
  deposuna VE her venv'in `certifi`'sine eklendi — yeni venv kurulursa
  certifi'ye tekrar eklenmeli, yoksa bulut çağrıları ve HF Hub kırılır.
  `HF_HUB_OFFLINE=1` bu yüzden açık. CDN'e bağlı her şey burada sessizce
  bozulabilir.
- `farabi-api` `--host 0.0.0.0` ile LAN'a açık (tahtalar başka türlü
  ulaşamaz); VLAN/güvenlik duvarı yok, dış sınırı okul güvenlik duvarı
  koruyor.
- Bu çalışma dizini (`/home/ata/farabi`) canlı üretim — servisler buradan
  koşuyor.

## Komutlar

Her projenin tam komut seti (tek test çalıştırma dahil) kendi
`CLAUDE.md`'sinde. Burada yalnızca alt dizine girmeden önce ısıran
tuzaklar:

| Proje | Test | Üretime alma |
|---|---|---|
| `server/` | `venv/bin/python -m pytest tests/ -q` | `sudo systemctl restart farabi-api.service` |
| `tahtayoklama/dashboard/` | ⚠️ **pytest DEĞİL:** `venv/bin/python -m unittest discover -p 'test_*.py'` (venv'de pytest yok) | `sudo systemctl restart farabi-yoklama-dashboard.service` |
| `smssistemi/` | `venv/bin/python -m pytest -q` | `sudo systemctl restart farabi-smssistemi.service` |
| `client/` | ⚠️ `farabi.local`'da `client/venv` **yok** — testi tahtada koş: `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"` (9-A'da `~/farabi/repo/client`) | GitHub'a push; tahtalar `farabiguncelle.sh` ile her gün 20:00'de çeker |
| `benchmark/` | ölçüm script'leri, pytest yok; `requirements.txt` yok, yalnızca `requirements.lock.txt` | — |

**Client güncellemesi SSH ile kopyalanmaz** — kod yalnızca GitHub
üzerinden gider (bkz. "Tahtaya dağıtım"). SSH yalnızca gitignore'lu ayar
dağıtımı, teşhis ve log okuma için:

```bash
server/tahta-ssh.sh <derslik> "<komut>"          # ogretmen olarak
server/tahta-ssh.sh --admin <derslik> "<komut>"  # etapadmin (sudo)
server/config_dagit.sh --kuru                    # gitignore'lu ayar dağıtımı, önce kuru çalıştır
```

Server logu yalnızca `journalctl -u farabi-api.service` (dosya log yok).

### Lint: Ruff

Lint ve formatter aracı Ruff; runtime'dan ayrı geliştirme ortamında:
`.venv-tools/bin/ruff`. `--fix` / `format` çalıştırılabilir
(`.venv-tools/bin/ruff check . --fix`, `.venv-tools/bin/ruff format .`) ama
Farabi çalışan bir eğitim/yoklama sistemi, otomatik değişiklikler davranışı
bozabilir.

```bash
.venv-tools/bin/ruff check client server benchmark tahtayoklama tahtaayar smssistemi
.venv-tools/bin/ruff check smssistemi/app.py      # yalnızca dokunduğun dosya
```

⚠️ **Sıfır bulgu beklenmiyor** (birikmiş yüzlerce stil bulgusu var; tarihli
sayımlar DECISIONS.md'de). Kural: **gerçek hata sınıfı (F821/F811/F632)
sıfır kalmalı** ve değişiklik toplam sayıyı artırmamalı. Değişiklikten önce
ve sonra çalıştırıp **farkı** oku ya da yalnızca dokunduğun dosyayı ver. Birikmiş
yığını topluca temizlemek Kural 6 kapsamında ayrı iş. `mudur/` ve `dogum/`
bilinçli olarak kapsam dışı.

Prosedür — kod değişikliğinden sonra önce yalnızca kontrol, bulgular
sınıflandırılır:
- F8xx / gerçek Python hataları: öncelikli incelenir.
- F401 / F841: güvenli olduğu kontrol edilerek temizlenebilir.
- I001 / formatlama: davranışı değiştirmediği doğrulandıktan sonra.
- DTZ / timezone: İstanbul/Türkiye saat mantığı kontrol edilmeden değiştirilmez.
- PLR / SIM / PERF / RUF: önce davranış etkisi değerlendirilir.

Bulgu gerçek bir bug ise önce çalışma mantığı incelenir, sonra minimum
değişiklik. Büyük ölçekli otomatik düzeltme yapılmaz. Ruff temizliğinde
bozulmaması gerekenler: yoklama sistemi, ders/zil zamanlaması,
İstanbul/Türkiye saat dilimi, öğrenci ve sınıf verileri, dashboard, SSH
bağlantıları, tahta ↔ server iletişimi, RAG, LLM bağlantıları, ders akışı,
mevcut API endpoint'leri, mevcut dosya ve veritabanı formatları. Sonrasında
Ruff tekrar + ilgili testler/çalışma kontrolleri.

**Öncelik sırası:** Çalışan sistem > davranışın korunması > gerçek bugların
düzeltilmesi > lint temizliği > stil/formatlama.

## Temel Kurallar

1. Client ince kalmalı. Ağır iş (RAG, LLM, kitap/plan işleme) sunucuda.
2. **Farabi asla dersi bozmaz.** Herhangi bir servis çökerse tahta normal çalışmaya
   devam eder; tam ekran hata basılmaz. (`mimari.md` §2 — tasarım kısıtı)
3. Tek seferde tek modül değiştir.
4. Değiştirmeden önce ilgili dosyayı oku. Varsayma, koddan kanıt bul.
5. Mevcut davranışı bozma; geriye dönük uyumluluğu koru.
6. Büyük refactor için önce plan sun, onay bekle.
7. Testleri atlama, başarısız testi gizleme.
8. **Mimari dokümanda geçmeyen yeni teknoloji/servis/kütüphane eklemeden önce onay
   iste.** Özellikle: Docker, Redis, Qdrant, Elasticsearch, Celery, Kafka,
   Kubernetes, Prometheus/Grafana, bulut API'si, yeni LLM.
9. `.env` asla commit edilmez. API anahtarı koda yazılmaz.
10. Ölçmeden optimizasyon yapma.
11. **Bug fix / özellik işlerinde plan Opus, uygulama Sonnet ile yapılır.**
    Önce Opus modeliyle (ör. `Agent` tool, `model: opus`, `subagent_type:
    Plan`) sorunun kök nedenini ve değişecek dosya/mantığı netleştiren yazılı
    bir plan çıkarılır, kullanıcıya sunulur; onaydan sonra kodu Sonnet yazar.
    Küçük/aşikâr tek satırlık düzeltmeler için (typo, config değeri gibi) bu
    adım zorunlu değil — orantısız olur.
12. **Çapraz değişiklik:** client+server bağlı değiştiğinde (biri diğerini
    gerektiriyorsa) ikisi BİRLİKTE ele alınır — her iki taraf incelenir,
    ilgili test paketleri (`server/tests/`, `client/tests/`) çalıştırılır,
    sonra `farabi.local` deploy edilir. **Son kabul testi her zaman Atakan
    tarafından fiziksel tahtada yapılır** — otomatikleştirilmez/atlanmaz.

**Kurulum biçimi:** systemd servisleri. Docker kullanılmaz — okulda sistemi
devralacak kişi `systemctl status` ile durumu görebilmeli.

## Şu An Yapılmayacaklar

- ⛔ **Yerel STT/TTS / ses düğümü (faster-whisper, Piper, Pipecat) — KALICI
  OLARAK İPTAL.** İlk karar 2026-08-11; 2026-09-25'te yeniden açıldı,
  2026-09-28'de donanım yetersizliği nedeniyle tekrar ve kalıcı olarak
  kapatıldı. Ses Gemini Live'da kalır. Geri alınan kodu (bd9719c,
  e04e279) geri getirme, `farabi-ses`/`farabi-piper`'ı yeniden
  etkinleştirme.

## Ağ Envanteri

Kimlik bilgileri (şifreler) ve tüm MAC adresleri **yalnızca
`network.txt`'te** (gitignore'lu). Bu dosya public GitHub'a gidiyor —
buraya şifre yazılmaz.

Üç ayrı makine sınıfı var:

1. **Vestel akıllı tahtalar** (Pardus ETAP GNU/Linux, hostname
   `vestel<düzey><şube>` deseninde — ör. `vestel9a`, ağ `192.168.23.0/24`,
   VLAN/güvenlik duvarı yok). **Sayım:** ağda 11 fiziksel tahta; **8'inde**
   Farabi client kurulu (aşağıdaki tablo = `config_dagit.sh`'in varsayılan
   hedef listesi), 8'in **7'si** sınıf, 8.'si `fenlab`. Kalan 3 tahta
   (`.234`, `.235`, `.236`) `server/tahtalar.json`'da `tahta-NNN` geçici
   adıyla kayıtlı, sınıfı atanmamış, client kurulu değil. Kurulum tarihleri
   ve ayrıntıları DECISIONS.md'de.

   | Sınıf/Ad | IP             | Hostname  | Yoklama | Farabi client |
   |----------|----------------|-----------|---------|---------------|
   | 9-A      | 192.168.23.245 | vestel9a  | evet (Farabi client venv'ini paylaşır) | evet (pilot; tam klon yapısı `~/farabi/repo`) |
   | 9-B      | 192.168.23.239 | vestel9b  | evet | evet |
   | 10-A     | 192.168.23.242 | vestel10a | evet | evet |
   | 11-A     | 192.168.23.228 | vestel11a | evet | evet |
   | 11-B     | 192.168.23.233 | vestel11b | evet | evet |
   | 12-A     | 192.168.23.226 | vestel12a | evet | evet |
   | 12-B     | 192.168.23.240 | vestel12b | evet | evet |
   | fenlab   | 192.168.23.244 | fenlab    | evet (7 sınıfın rosterı birden; dashboard'da sınıf atanmamış) | evet |

   ⚠️ **fenlab'ın `derslik` değeri `"fenlab"`** — Farabi sınıf düzeyini
   `derslik`ten çıkarıyor (`10-A` → 10. sınıf); `"fenlab"` bir düzeye
   çözülemez, bu yüzden kitap ararken öğretmene sınıfı soracak. Tek bir
   düzeye sabitlenecekse `derslik` değiştirilmeli.

   Donanım: Pardus ETAP 23, Intel i3-2330M (eski mobil işlemci).
   Bağlanma: `server/tahta-ssh.sh <derslik>` (`ogretmen`) ya da
   `--admin <derslik>` (`etapadmin`, sudo). NOPASSWD sudo tahtadan tahtaya
   değişiyor — önce `sudo -n true` ile dene. MAC adresleri ve kimlik
   bilgileri `network.txt`'te (ikincil referans; çelişkide
   `server/tahtalar.json` esas).

2. **Kapıdaki yüz tanıma sistemi** (giriş yoklaması kiosk PC'si,
   `192.168.23.254`, Debian 12) — bu repodaki hiçbir projeye BAĞLI DEĞİL,
   yalnızca envanter notu.

3. **Farabi sunucu** (bu makine, `ata@farabi.local` / `192.168.23.252`,
   Ubuntu 26.04, Ryzen 9 3900X, 2× RTX 3060, 64 GB RAM, sudo NOPASSWD) —
   tüm servisler burada, tahtalara buradan SSH ile bağlanılıyor.

## RAG Kuralları (kritik)

> ⚠️ 2026-10-03'ten beri RAG yalnızca bge-m3 CPU'da, reranker yok (`RERANK_YUKLE = False`); rerank/eşik (`ESIK_RERANK`) maddeleri reranker geri açılınca geçerli, Open WebUI yolu kosinüs eşiği (`ESIK_BENZERLIK` 0,55) kullanır.

- Cevap **sadece** retrieval sonucundan üretilir. Serbest üretim yok.
- Ana savunma: skor eşiğin altındaysa LLM'e hiç gitme → "Bu konu ders kitabında
  bulunmuyor."
- Arama **yalnızca kitap filtresiyle** (`kitap_id` WHERE koşulu), **iki
  kaynaktan**: `chunk_egitim` top-20 (`rag.py::_ilk_k_getir`) +
  `chunk_tablo` top-10 (`rag.py::_tablo_getir`), ayrı sorgular. Rerank
  birleşim üzerinde, top-4 seçilir; `ESIK_RERANK` = 0,5. Geri dönüş tek
  satır: `rag.py::TABLO_KAYNAGI = False`. **`chunk_tablo` şu an yalnızca
  `biyoloji-9` için dolu** — yeni kitap eklendiğinde ölçüm (40 soruluk set,
  şu an 38/40) tekrarlanmalı. Ayrıntı `docs/mimari.md` §5.
- **Kazanım filtresi YOK:** `chunk_egitim.kazanim_kod` kolonu DB'de var ama
  hiçbir sorguda okunmuyor. Kazanım bazlı filtre yalnızca gelecek-fazı
  önerisi (mimari.md §12).
- Her cevapta kaynak: `9. Sınıf Biyoloji, s. 84`
- Chunk sayfa sınırını aşmaz.
- LLM sıcaklığı ≤ 0.2, cevap ≤ 3 cümle.
- Ek kontrol: cevapta kaynakta geçmeyen **sayı** varsa gösterme.
  Kelime örtüşme oranı kullanma (doğru parafrazı engeller).

## API Prensibi

**Brain karar verir, Client görüntüler.** Server ham LLM metni döndürmez;
`{status, answer, sources[], latency_ms, request_id}` yapısı döner
(`audio_url` yok — ses Brain'de üretilmiyor). Client metni ayrıştırmaz,
`status`'a göre davranır.

Client↔Server event listesi bağlayıcıdır — değişirse `mimari.md`'yi güncelle.

## Veri Yerleşimi ve İzolasyon

- Dosyalar ikinci diskte: `/mnt/farabi-data/farabi/` (1.8TB) — `kitaplar/`,
  `yks/`, `icerik/{metin,ozet,yks_metin,eslemeler,onbellek,kitaplar.json}`.
  Kod bu yoldan yalnızca `DATA_DIR` sabitiyle haberdar (NAS gelirse tek sabit
  değişir).
- **PostgreSQL** → metadata, hash, sınıf, ders, kazanım, sayfa.
  **pgvector** → chunk + embedding. Dosya içeriği DB'ye gömülmez.
- Chunk tabloları: `chunk_egitim` (ders kitapları) + `chunk_idari` (mevzuat,
  yönetmelik, yönerge — Open WebUI Müdür Yardımcısı modu için). 2026-08-31'deki
  "`/api/idari/*` ve `chunk_idari` kalıcı iptal" kararı **2026-10-03'te
  kullanıcı kararıyla kaldırıldı** (DECISIONS.md 2026-10-03). `chunk_idari`
  dolu (20 belge, 1485 parça; `server/idari_yukle.py`) — tasarım:
  `docs/superpowers/specs/`.
- Tahta token'ı yalnızca `/api/egitim/*` çağırabilir.

## Gizlilik

- **Öğrenci sesi kalıcı olarak Gemini Live'a (Google bulutu) gidiyor** —
  bilinçli karar (2026-08-11, mimari.md §14; 2026-09-28'de yeniden
  teyit edildi).
- Fiziksel kamera/webcam yok. Ekran görüntüsü zorunlu bir yetenek ama
  yalnızca `QApplication.primaryScreen().grabWindow(0)` — tahtanın o an
  gösterdiği şey, asla kamera/sınıf/öğrenci. Ayrıntı `client/CLAUDE.md`.
- Ham ses diske yazılmaz — Gemini Live'ın transkripsiyonu client'ta kalır,
  Brain'e yalnızca metin gider.
- Öğrenci kimliği tutulmaz. Anonim "öğrenci sordu".
- **Kitap metni buluta gidebilir (2026-09-29 kararı):** MEB kitapları halka
  açık; ders planı, sayfa görseli ayrıştırma (formül/tablo), özet gibi
  kitap içeriğiyle çalışan görevler bulut sağlayıcılara (`server/
  saglayicilar.py`, server üzerinden; anahtarlar client diskinde durmaz)
  gönderilebilir. **Hâlâ yerel:** RAG soru-cevabının LLM adımı
  (`rag.py` → Ollama; buluta taşımak ayrı karar + 40 soruluk ölçüm ister),
  embedding/reranker/pgvector. **Asla buluta gitmez:** öğrenci/veli
  verisi (yoklama, roster, SMS rehberi). Ses zaten Gemini Live'da.
- **Dar istisna — kazanım testi (2026-10-07 kararı):** `kazanimtest/` Google
  Form'una (okulun Google hesabı, Apps Script) yalnızca soru metinleri gider;
  öğrenci formda **yalnızca okul numarasını** yazar, cevapları Google
  Tablo'da durur. Ad, telefon, roster Google'a GÖNDERİLMEZ; okul no ↔ ad
  eşleşmesi yalnızca sunucuda yapılır.

## Loglama — iki tablo, karıştırma

- `metrik` → yalnızca süre + durum + skor. İçerik yok. Sınırsız saklanır.
- `soru_log` → soru/cevap metni **yalnızca** şu durumlarda: düşük skorlu `ok`,
  `yetersiz_kaynak`, `sayi_kontrolu_reddi`, `iptal`, `hata`.
  Başarılı+yüksek skorlu cevaplarda metin saklanmaz.
- **Derste konuşulanlar ayrıca metin olarak tutulur** — bu `soru_log`
  değil, ders transkripti: tahtada `client/logs/ders/*.txt`, ders sonunda
  `server/yedekler/ders_kaydi/<derslik>/` altına yedeklenir (yalnızca
  metin, ses yok, öğrenci kimliği yok). Loglamanın bilinçli parçası.
- `soru_log` **süre sınırı olmadan** tutulur (bilinçli karar, 2026-08-18);
  otomatik silme mekanizması yok ve olmamalı, aksi istenmedikçe.

### Log dosyalarını okuma ilkesi

**Log dosyaları hata/bug avında birincil kanıt — varsayımla debug etme.**

- Ders transkriptleri (`client/logs/ders/*.txt` — tahtanın kendi diskinde,
  SSH gerekir: `server/tahta-ssh.sh <derslik> "cat
  ~/farabi/client/logs/ders/<dosya>.txt"`) derste ne konuşulduğunu, hangi
  tool'un ne zaman çağrıldığını, modelin nerede yanlış yaptığını gösterir.
  Server'a yedeklenen kopyalar `server/yedekler/ders_kaydi/<derslik>/*.txt`
  (doğrudan okunabilir).
- `client/logs/farabi.log` (tahtanın diskinde, rotating) ikincil kanıt —
  bağlantı/reconnect/hata izleri.
- **Server'da dosya bazlı log YOK** — yalnızca `journalctl -u
  farabi-api.service`.
- **Bir log dosyası büyükse (kabaca >1000 satır ya da >200KB), önce
  boyutunu bildir; dosyanın TAMAMINI okumadan önce mutlaka sor.** Hedefli
  arama (`grep`, `tail`, belirli tarih/derslik aralığı) sormadan yapılabilir.

## Okuma

Şunları okuma: `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`,
`client/config/api_keys.json*`, `server/config/api_keys.json*`, `*.env`,
`network.txt`, servislerin `config/gizli.json`'ları.

### PDF'ler — okunabilir, özetlenebilir (2026-10-02 kuralı)

- **Ders kitabı, YKS ve diğer halka açık PDF'ler** (`/mnt/farabi-data/
  farabi/kitaplar/`, `yks/`, `mudur/siniflar.pdf`, `Farabi.pdf` gibi)
  okunabilir ve özetlenebilir. Gerekçe "Gizlilik"teki 2026-09-29 kararı:
  MEB kitapları halka açık, kitap metni buluta gidebilir.
- Hedefli oku: ilgili sayfa aralığını ver (Read aracı istek başına en çok
  20 sayfa); bütün kitabı bağlama dökme. Türetilmiş metin zaten
  `icerik/{metin,ozet,yks_metin}/` altında — önce oraya bak.
- Üretilen özetler veri diskine yazılır (`/mnt/farabi-data/farabi/icerik/
  ozet/`), public repoya değil.
- **İstisna — kişisel veri içeren PDF/Excel okunmaz:** `mudur/SINIF/`
  (öğrenci listeleri, telefonlar, doğum tarihleri), e-Okul roster
  çıktıları, yoklama/SMS dışa aktarımları. Okumak içeriği buluta gönderir;
  "Asla buluta gitmez" kuralı geçerli.
- **Ürün yönü:** PDF içerikleri sayfa sayfa ayrıştırılıp tahtada
  gösterilebilir (`pdf_sayfa` + `pdf_sayfa_metni` bunu zaten yapıyor);
  ders anında Gemini Live bu sayfaları okuyabilir. Tablo/şekil yorumu için
  sayfa görselini Gemini'ye vision girdisi olarak vermek açık bir
  geliştirme yönü (`ekrandaki_soruyu_oku`'nun `send_client_content`
  deseni örnek).

## Diğer dizinler

- `mudur/` — müdür yardımcısının kaynak dosyaları (ders programı, SINIF/
  Excel+PDF). Servis değil; `smssistemi/scripts/sinif_bilgi_ice_aktar.py`
  buradan okur.
- `dogum/` — eski tek dosyalık **Telegram** doğum günü botu. UYKUDA
  (crontab/systemd'de kayıtlı değil, son çalışma 2026-09-20); smssistemi'nin
  Doğum Günleri modülü yerini aldı, kasıtlı mı bilinmiyor.
- `tahtaayar/` — tahtaların OS/oturum ayarlarını (güç düğmesi, uyku, ekran
  karartma) referans duruma getiren ajansız script'ler.
- `docs/superpowers/{specs,plans}/` — superpowers becerilerinin ürettiği
  belgeler buraya yazılır (`<TARİH>-<konu>-design.md`, `<TARİH>-<konu>.md`).
- Kökteki `plan.md` (2026-09-02 PDF/vision analizi + uygulama günlüğü),
  `sorunlar.md` (2026-09-13 RAG/veri kontrolü), `eylulanaliz.md`,
  `webmimari.md`, `raganaliz.txt` — **tarihli anlık görüntüler**, güncel
  durum değil; çelişkide bu dosya + DECISIONS.md esas.
- **Gemini CLI bu projede kullanılmaz** (2026-09-29 kararı): kökteki
  `package.json`/`package-lock.json`/`node_modules` (yalnızca
  `@google/gemini-cli` içindi) silindi, `~/.gemini/` yapılandırması Claude
  Code'a import edilmez. Bu, ses için kullanılan Gemini Live'ı etkilemez.

## Araçlar / Eklentiler

- **superpowers** — beceriler kendiliğinden tetiklenir. ⚠️ TDD/worktree
  akışı Kural 11'i (plan Opus → uygulama Sonnet) ve Kural 6'yı GEÇERSİZ
  KILMAZ; çakışırsa bu dosya kazanır.
- **context7** (MCP, `.mcp.json`, anahtarsız düşük kota) — FastAPI/PyQt6
  gibi dış kütüphane API'si için. Farabi'nin KENDİ kodu için değil, onun için
  kodu oku (Kural 4).
- **frontend-design** — kurallar `tahtayoklama/CLAUDE.md`'de.

## Frontend / Dashboard Tasarım Standartları

`tahtayoklama/dashboard/` web arayüzüne (templates + `static/`) dokunmadan
önce `tahtayoklama/CLAUDE.md` → "Frontend / Dashboard Tasarım
Standartları" bölümünü oku. Özet: tasarım sistemi (`pano.css` token'ları,
üç tema, satır içi ikon sprite) dondurulmuş; CDN/yeni kütüphane yok
(Kural 8).
