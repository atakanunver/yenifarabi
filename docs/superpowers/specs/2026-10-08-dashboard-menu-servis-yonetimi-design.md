# Dashboard: menü çubuğu kabuğu + servis yönetimi — tasarım (2026-10-08)

Kapsam: `tahtayoklama/dashboard/` (`farabi-yoklama-dashboard`, :8010). Kullanıcı:
Atakan ve idareci (öğretmen değil). Kullanıcı kararları 2026-10-08 sohbetinde:
yetki = "kontrol + log", tasarım = "düzen yeni, renkler aynı", gezinme =
"menü çubuğu + ince kenar".

## 1. Hedef ve başarı ölçütü

- Tüm sayfalarda Windows tarzı **üst menü çubuğu** (açılır menüler) + solda
  **ikonlu ince şerit**; telefonda tek ☰ çekmece.
- Yeni **/servisler** sayfası: farabi.local'deki servis ve zamanlayıcıların durumu
  + yeniden başlat / durdur / başlat / zamanlayıcı aç-kapat / şimdi çalıştır /
  son loglar — tek ekrandan, onaylı ve denetim kayıtlı.
- Başarı: (a) her mevcut sayfaya menüden ≤2 tıkla ulaşılır; (b) bir servis
  yeniden başlatma isteği → onay → sonuç rozeti, sayfadan çıkmadan; (c) üç temada
  ve 375 px genişlikte yatay kaydırma yok; (d) yalnızca klavyeyle tüm menüler
  gezilebilir.

## 2. Kapsam dışı (bilinçli)

- Servis **ayar dosyası düzenleme** (ör. `kazanimtest/config/ayar.json`) — ayrı iş.
- Uzak makinelerde eylem (debian EMA TTS, bilgehan, zil): yalnızca durum.
- Nginx ters proxy, SQLite WAL (zaten `wal`, ölçüldü), yoklama polling aralıkları
  — ölçüm olmadan değiştirilmez (Kural 8/10).
- Renk/tema/yazı tipi değişikliği: `pano.css` token'ları ve üç tema korunur.

## 3. Kabuk (tüm sayfalar)

### 3.1 Menü ağacı — tek kaynak `menu.py`

Saf veri (liste/dict) + `menu_agaci(request)` (aktif öğe işaretli). `taban.html`
menü çubuğunu, ikon şeridini ve mobil çekmeceyi BU ağaçtan üretir; menü
öğesi ikinci bir yerde elle yazılmaz.

| Menü | Öğeler |
|---|---|
| ◆ Farabi | Ana pano · Hakkında |
| Dosya | Ana pano · Yazdır (`window.print`) · ─ · Çıkış |
| Düzen | Sayfayı yenile (F5) · Bağlantıyı kopyala |
| Yoklama | Pano · Tahtalar · Sınıflar · Rapor · Kazanım raporu |
| Tahtalar | Uzaktan yönetim |
| Servisler | Servis yönetimi *(yeni)* · Zamanlayıcılar (`/servisler#zamanlayicilar`) · ─ · Sistem durumu · Sunucular |
| Uygulamalar | Atos (yeni sekme) · SMS · SMS otomasyonu · Doğum günleri · Zil paneli |
| Görünüm | Tema ▸ klasik / yumuşak / koyu (radyo) · Kenar şeridini gizle/göster |
| Yardım | Klavye kısayolları · Hakkında |

İkon şeridi (6): Ana pano, Uzaktan yönetim, Yoklama raporu, Servis yönetimi,
Sistem durumu, Atos. Her öğede `title` + görünür odak halkası.

**Zil paneli bağlantısı şifresiz** olur (`http://192.168.23.230:8090/`); bugünkü
`taban.html` bağlantısında kullanıcı adı:şifre gömülü ve repo PUBLIC — kaldırılır,
tarayıcı Basic Auth'u kendisi sorar. (Şifrenin değiştirilmesi kullanıcıda.)

### 3.2 Davranış ve erişilebilirlik

- WAI-ARIA menubar deseni: `role="menubar"` / `menu` / `menuitem` /
  `menuitemradio`; ←/→ üst menüler arası, ↓/↑ öğeler, Enter/Space çalıştır,
  Esc kapat ve odağı üst menüye döndür, Home/End. Bir menü açıkken fareyle
  komşu üst menüye gelmek onu açar (Windows davranışı). Dışarı tıklama kapatır.
- Kısayollar (tarayıcının Alt menüsüyle çakışmamak için yalnızca bu ikisi): `F10`
  menü çubuğuna odak; `?` Yardım › Klavye kısayolları penceresi.
- Görünüm › Tema mevcut `tema.js` mekanizmasını (`data-tema`, localStorage)
  kullanır; kenar şeridi tercihi localStorage'da (`try/catch`, yoksa varsayılan).
- 375 px altında menü çubuğu yerine ☰ → aynı ağaç akordeon çekmece
  (mevcut `kenar.js` çekmece mantığı yeniden kullanılır).
- `prefers-reduced-motion` bloğu `pano.css`'e eklenir (tahtayoklama/CLAUDE.md'nin
  açık maddesi): menü açılış geçişi ve skeleton animasyonu kapanır.
- Geçişler yalnızca mevcut 0.15 s / 0.12 s; renkler yalnızca var olan
  `--renk-*` token'ları; yeni token gerekirse üç temada birden tanımlanır.

### 3.3 Sayfaların uyarlanması

Mevcut sayfaların içeriği değişmez; her sayfada başlık > birincil eylem > KPI >
tablo sırası ve tutarlı sayfa başlığı bileşeni (`.sayfa-ust`) uygulanır.
Eski geniş kenar menüsünün CSS'i kaldırılır, `kenar.js` yalnızca çekmece +
şerit için kalır. Uzun sayfalar (`sistem_durumu.html` 494 satır) bölünmez.

## 4. Servis yönetimi — `/servisler`

### 4.1 Yönetilen birimler (beyaz liste, tek yerde: `servis_yonetimi.py` + betik)

| Birim | Ad | Eylemler | Ders saati uyarısı |
|---|---|---|---|
| `farabi-api` | Farabi Brain | yeniden başlat, durdur, başlat, log | evet |
| `farabi-smssistemi` | SMS Sistemi | yeniden başlat, durdur, başlat, log | hayır (09:00/14:00 otomasyon penceresinde uyarı) |
| `farabi-yoklama-dashboard` | Yoklama Panosu (bu sayfa) | yeniden başlat (gecikmeli), log | hayır |
| `ollama` | Ollama (qwen3.8:27b) | yeniden başlat, log | evet |
| `open-webui` | Atos | yeniden başlat, durdur, başlat, log | evet |
| `sinif-arena` | Sınıf Arenası | yeniden başlat, durdur, başlat, log | evet |
| `kazanim-test.timer` / `-sonuc.timer` / `-aylik.timer` | Kazanım testi | etkin/devre dışı, şimdi çalıştır, log (servisi) | — |
| `soru-havuzu-uret.timer` | Soru havuzu üretimi | etkin/devre dışı, şimdi çalıştır, log | şimdi çalıştır ders saatinde reddedilir (uretim zaten kendisi durur) |
| `farabi-idari-yukle.timer` | İdari belge yükleme | etkin/devre dışı, şimdi çalıştır, log | — |

Yalnızca görüntülenir: `postgresql@18-main`, `chrony`, uzak servisler (debian EMA
TTS :5002, bilgehan `farabi2-ses` :8060 ve `farabi-embed` :8040, zil :8090).
Dashboard kendi kendini durduramaz (yalnız gecikmeli yeniden başlatma).

### 4.2 Ekran

- Üst: başlık "Servis yönetimi", birincil eylem "Yenile", KPI'lar (çalışan /
  sorunlu servis, sıradaki zamanlayıcı).
- **Servisler** kart ızgarası: ad, birim adı (soluk), durum rozeti (yeşil
  çalışıyor / amber başlıyor-duruyor / kırmızı failed / gri durdu), çalışma süresi,
  bellek, son yeniden başlama; eylem butonları + "Log".
- **Zamanlayıcılar** tablosu (`#zamanlayicilar`): ad, sonraki çalışma, son
  çalışma + sonuç (ör. `soru-havuzu-uret` failed → kırmızı), anahtar (etkin),
  "Şimdi çalıştır", "Log".
- **Log paneli**: sağdan açılan panel, son 200 satır (`journalctl -u <birim> -n 200
  -o short-iso --no-pager`, `ata` `adm` grubunda — sudo gerekmez), "yalnız
  uyarı+hata" süzgeci, kopyala düğmesi. Satırlarda `://kullanıcı:şifre@`,
  `key=`/`anahtar=`/`token=`/`password=` değerleri `***` ile maskelenir.
- Yüklenirken skeleton, veri yokken açıklayıcı boş durum.
- Durum verisi mevcut `sistem_durumu.py` önbelleğinden (`systemctl show` tek
  çağrı) okunur; zamanlayıcılar için aynı çağrıya `NextElapseUSecRealtime`,
  `LastTriggerUSec`, `Result` alanları eklenir.

### 4.3 Akış

1. Butona tık → onay penceresi: eylemin etkisi düz Türkçe ("Farabi Brain yeniden
   başlatılacak; tahtalardaki kitap/YKS soruları ~10 sn yanıt vermez").
2. Ders saatinde (`tahta_yeniden_baslat.ders_saatinde_mi`) uyarılı birimlerde
   pencerede kırmızı not + "Yine de yeniden başlat" ikinci onayı.
3. `POST /servisler/eylem` `{birim, eylem}` → `servis_yonetimi.calistir()` →
   `subprocess.run(["sudo","-n","/usr/local/sbin/farabi-servis",eylem,birim],
   timeout=60)` (kabuk yok).
4. Yanıt `{ok, durum, mesaj}`; kart rozeti güncellenir; denetim kaydı yazılır.
5. Dashboard'un kendi restart'ı: betik `systemd-run --on-active=2 systemctl
   restart farabi-yoklama-dashboard` kullanır; sayfa "bağlantı yenileniyor"
   gösterip `/servisler`'i 3 sn arayla yeniden dener.

## 5. Güvenlik

- **`/usr/local/sbin/farabi-servis`** (root:root 755, kaynak repoda
  `tahtayoklama/dashboard/scripts/farabi-servis`, kurulum `install` ile):
  `set -euo pipefail`, eylem ve birim **sabit `case` listeleriyle** doğrulanır,
  liste dışı → çıkış 2 + stderr; yalnızca `systemctl {restart,start,stop}
  <servis>`, `systemctl {enable --now,disable --now} <timer>`, `systemctl start
  <timer'ın servisi>`, dashboard için gecikmeli restart. `okul-sunucu` deseni.
- `/etc/sudoers.d/farabi-servis`: `ata ALL=(root) NOPASSWD: /usr/local/sbin/farabi-servis`
  (`visudo -c` ile doğrulanır). Not: `ata` zaten tam sudo'ya sahip; betiğin
  değeri web katmanındaki bir hatanın keyfi komuta dönüşmemesi.
- Uç: yalnızca POST, mevcut oturum (`_oturum_gerekli`), `Origin`/`Referer`
  dashboard'un kendi host'u değilse 403, gövde Pydantic ile beyaz listeye karşı
  doğrulanır (betikten ÖNCE de).
- Denetim: her eylem `uzaktan_denetim`'e (`eylem="servis_<eylem>"`,
  `tahtalar=<birim>`, sonuç, `kaynak="servisler"`); yazım hatası eylemi
  engellemez (mevcut desen).
- `/api/ajan` (Atos yönetim aracı) bu eylemlere bu aşamada BAĞLANMAZ.

## 6. Bileşenler

| Dosya | Görev |
|---|---|
| `menu.py` (yeni) | menü ağacı verisi + aktif öğe |
| `templates/taban.html` | menü çubuğu, ikon şeridi, çekmece (ağaçtan) |
| `static/menu.js` (yeni) | menubar klavye/fare davranışı, tema/şerit tercihleri |
| `static/pano.css` | kabuk düzeni, menü, şerit, `prefers-reduced-motion`; eski geniş kenar CSS'i silinir |
| `templates/_ikon_sprite.html` | eksik ikonlar (`ik-sunucu`, `ik-zamanlayici`, `ik-log`, `ik-yeniden`…) Lucide çiziminde |
| `servis_yonetimi.py` (yeni) | beyaz liste, durum birleştirme, `calistir()`, log + maskeleme, ders saati kuralı |
| `templates/servisler.html` (yeni) | sayfa |
| `app.py` | `GET /servisler`, `GET /servisler/durum`, `GET /servisler/log/{birim}`, `POST /servisler/eylem` |
| `scripts/farabi-servis` + `scripts/farabi-servis.sudoers` | ayrıcalıklı sarmalayıcı (repo kaynağı) |

## 7. Test

unittest (dashboard pytest değil):
- `test_menu.py`: her mevcut route menüde var; aktif öğe; zil bağlantısında `@` yok.
- `test_servis_yonetimi.py`: beyaz liste dışı birim/eylem → reddedilir, subprocess
  çağrılmaz; ders saatinde uyarılı birim ilk istekte `onay_gerekli`; log maskeleme
  (`http://u:p@h`, `token=abc`); denetim kaydı yazılır; Origin yanlış → 403;
  oturumsuz → 401/303.
- `farabi-servis` betiği: sahte `systemctl` (PATH başı) ile liste içi/dışı
  çağrılar (bash testi `scripts/test_farabi_servis.sh`, unittest'ten subprocess).
- Elle: Chrome'da üç tema, klavyeyle tüm menüler, 375 px, gerçek bir
  `sinif-arena` yeniden başlatması (ders dışı saatte).

## 8. Sıralama ve riskler

1. Başka oturumun commit'lenmemiş `kazanim_rapor.*` + `pano.css` değişiklikleri
   commit'lenmeden `pano.css`'e dokunulmaz (çakışma).
2. `menu.py` + kabuk → tüm sayfalar → `/servisler` (salt okunur) → sarmalayıcı +
   eylemler → zamanlayıcılar → log paneli.
3. Risk: `taban.html` her sayfayı etkiler — her adımdan sonra tüm route'lar 200
   döner mi testi (`test_menu.py`).
4. Risk: dashboard restart'ı canlı panoyu ~3 sn düşürür; ders saatinde yapılan
   restart'ta tahta istemcisinin o ~3 sn'lik itmelerinin yeniden denenip
   denenmediği uygulama planında `tahta_istemci.py`'den doğrulanmalı.
