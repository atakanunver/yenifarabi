# Dijital Okul (okul/)

Mobil öncelikli okul portalı (öğrenci/veli/öğretmen/yönetici): FastAPI + Jinja2 + vanilla CSS ("kareli defter" teması, imza öğe `.kareler`), kendi SQLite'ı. `farabi-okul.service`, port 9090, dışarıdan https://smual.app (Cloudflare Tunnel). Spec: `../docs/superpowers/specs/2026-10-10-dijital-okul-design.md`.

## Komutlar
- Test (`okul/` içinde): `venv/bin/python -m pytest -q`; tek test: `venv/bin/python -m pytest tests/test_odevler.py::test_adi -q`.
- Lint (repo kökünden, yalnız dokunduğun dosya): `.venv-tools/bin/ruff check okul/<dosya>` (okul/ ruff kapsam listesinde değil).
- Yerel çalıştırma: `venv/bin/uvicorn app:app --host 127.0.0.1 --port 9090` (açılışta yerel veriye erişir).
- Üretime alma: `sudo systemctl restart farabi-okul` (birim kurulum yorumu `systemd/farabi-okul.service`).
- İlk yönetici: `venv/bin/python scripts/yonetici_olustur.py "Ad Soyad" kullanici_adi`.
- Yıllık planlar: `venv/bin/python scripts/yillik_planlari_aktar.py` (argümansız; `/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027` .docx'leri `PLAN_HARITASI` (öğretmen id, sınıf, ders) ile `belgeler`/db'ye aktarır; yeni plan = haritaya satır).
- Bazı dosyalar CRLF (`git ls-files --eol`): Python `open()` ile yeniden yazma, `newline=''` ya da Edit aracı.

## Değişiklik kuralları
- ⚠️ Şablonlar canlıya ANINDA yansır; Python (`deps.py` Jinja global vb.) restart ister. Yeni Jinja global kullanan şablonu `is defined` ile koru ve değişiklikten hemen sonra restart et (korumasız global /giris'i 503 yaptı).
- Şema: `db.GOCLER` sonuna yeni eleman ekle, eskileri DEĞİŞTİRME. Güncel sürüm = `len(GOCLER)` (şu an 41); yeni göç = `V<len+1>`. Şema `PRAGMA user_version` ile sürümlü, her göç tek `BEGIN…COMMIT`. Her göç için `scripts/geri_al.py`'ye GERI girdisi ekle (`--hedef N`).
- CSS/JS değişince: `okul.css?v=N` (base.html) ve `*.js?v=N` (onu yükleyen şablon) sürümünü, `static/sw.js` içindeki SURUM + STATIK listesini artır; yeni statik JS STATIK'e de eklenir.
- Zaman için daima `zaman.simdi()` (test edilebilirlik).
- Yeni rota modülü `rotalar/` altına + `app.py`'de `include_router`. Rota işi `rotalar/`, iş mantığı kök modülde.
- Üst çubuk `.ust` tek satır flex: yeni öğe ≤360px'te Çıkış düğmesini itmemeli (`flex: none`).
- Yeni sabit renk yazma, CSS değişkeni kullan (`--alan --kenar --sari-bg --hata-yazi ...`); dış yazı tipi YOK.
- Test: `tests/test_*.py`; yetki değişikliği test edilir; dış servisler mock'lanır. Yeni yol/ayar eklersen `conftest.py`'deki autouse `gecici_ortam` fixture'ına ekle (yoksa test gerçek `veri/`'ye yazar). `ayarlar.AYAR` tek global ayar nesnesi; testte `analitik.sifirla()` conftest'te çağrılır.

## Güvenlik ve gizlilik
- Repo PUBLIC: şifre/anahtar/token/özel davet bağlantısı/öğrenci verisi commit'leme. Sırlar gitignore'lu `config/gizli.json`'da.
- Dış kaynaklar SALT-OKUNUR, her istekte okunur, kopyalanmaz. Yetkisiz erişim = 404 (varlığı sızdırma); mevcut rol kontrollerini koru.
- Yüklenen dosyalar (`veri/dosyalar`, gitignore'lu) `static/` altında DEĞİL; rastgele adla saklanır, yalnız yetki kontrollü rotalardan sunulur; yazma atomik (geçici ad + `replace`); tür dosya imzasından belirlenir, uzantıdan değil.
- `app.py` orta katmanı: güvenlik başlıkları + `Cache-Control: no-store` (static hariç) + kayan oturum çerezi; 404/şifre-değiştir/giriş yönlendirmeleri exception handler'larla.
- Oturum 1 yıl kayan çerez (bilinçli); ilk şifre zorunlu değişim; veli girişi SMS kodu.
- Tahta yoklaması isimle tutulur: aynı sınıfta aynı/eşleşmeyen isim veliye gösterilmez (yanlış çocuğa devamsızlık yazmamak için); yönetici `/yonetici/eslesmeyen`'de görür.
- Okul kanalları şeridi: `config/kanallar.json` (`web`/`instagram`/`youtube`, yalnız https; her istekte okunur) → `templates/_kanallar.html`; dosya yoksa şerit gizli. WhatsApp grup davet bağlantıları (`whatsapp_veli`, `whatsapp_ogrenci`) ANAHTAR gibidir: yalnız `config/gizli.json`'a yaz (`kanallar.json`'a YAZMA); girişte görünmez; veli grubu yalnız veliye, öğrenci grubu yalnız öğrenciye (yöneticiye ikisi). Testler `conftest.py`'de bunları boşaltır.
- LAN-only uçlar (`rotalar/pano.py`, `duyuru_api.py`, `devamsizlik_api.py`): Cloudflare Tunnel başlığı (`cf-*`/`x-forwarded-*`) varsa 404.
- Push: VAPID yoksa özellik KAPALI (404); payload SABİT şablon (`push.SABLONLAR`), ad/ders/not ASLA (Google/Apple sunucularından geçer); gönderim asıl işlemi bozmaz.

## Modül haritası
Uzun maddelerin tam hali (gayret, sudoku, mikro-görevler, denemeler, push, sohbet, kokpit, veli ekranı, soru_bildirim, kütüphane): `docs/moduller.md`. O modüle dokunmadan önce oku.
- Profil iletişim (`rotalar/belge_sinav.py` `POST /profil/iletisim`; V37 `kullanici.eposta`, telefon `kullanici.telefon`): yalnız kendisi + yönetici görür; `ice_aktar.ogretmen_uygula` CSV'de boş telefonla mevcudu ezmez.
Saat widget'ı (`_saat.html`) ve zil tablosu (`_zil_tablo.html`) `deps.py` Jinja global'lerinden (`saat_verisi`, `zil_cizelgesi`) beslenir; canlı durum `static/saat.js`, kural `kaynaklar/zil.py::durum` ile aynı kalmalı. Yeni öğretim yılı/tatil = yalnız `config/takvim.json`.
- analitik: `olay` tablosu yalnız sayaç (içerik/IP/cihaz yok), UNIQUE(kullanıcı,tür,nesne,gün,oturum_k) + `INSERT OR IGNORE`; `analitik.kaydet` bellek tamponu (25 kayıt/5 sn) → `bosalt()`; olaylar orta katmanda yalnız 200 GET'ten, rotalarda başarılı işlemden sonra; çevrim içi = `oturum.son_nabiz` ≤ 90 sn; yeni olay türü = `analitik.OZELLIKLER`'e ekle. `/yonetici/analitik`.
- maraton (Soru Maratonu, okul.db): doğru şık cevaptan önce istemciye gitmez, süre sunucuda; `maraton.DERS_KILIDI = False` (True olursa Maraton+Günlük Görev ders saatinde 423). Postgres `soru_havuzu`'na YAZILMAZ (`soru_kullanim`/`kullanim_sayisi` arena'nın); tekrar engeli öğrenci bazlı okul.db'de. Rotalar JS ve JS'siz form akışını birlikte sunar (`Accept: application/json`). Cevap kodları `PAS=-3`, `HATALI=-4` istatistiğe girmez.
- arena (Bilgi Arenası: Günlük Görev 5 soru + XP/seviye/rozet defteri `bilgi_xp`; 9-11; XP/seviye saklanmaz, defterden türetilir), kisisel (haftalık hedef; `bilgi_tur`/`maraton`/`odev_teslim`'den), bugun.
- İKİ ARENA AYRI: smual.app Bilgi Arenası = bireysel (okul.db: bilgi_*, odul, avatar); tahta Sınıf Arenası = `/home/ata/farabi/arenasinif` (kendi sonuclar.db, sınıf liderliği, Postgres `soru_kullanim`'a yazar). Okul tahta arenasına bağlanmaz, havuza yalnız SELECT yapar (`tests/test_arena_ayrim.py`).
- oduller (haftalık ödül: kiosk duyurusu; sonuç `odul`/`odul_hafta`'ya bir kez yazılır, değişmez; 12. sınıf dahil), avatar (açık mı sunucuda doğrulanır).
- Öğretmen liderliği: kendi sınıfı adlı; sınıflar arası kıyasta yalnız toplam; adlı görüntüleme `erisim_log`'a yazılır. Soru bazlı istatistik kimliksiz (`odevler.soru_istatistik`).
- gayret (V33): süreç XP'si (<5 sn 0, günde ≤60, yalnız 9-11); kancalar `maraton.cevapla`, `arena.cevapla`, `calisma.cevapla`.
- sudoku: çözüm ve bot süresi istemciye GİTMEZ, süre sunucuda; `bilgi_xp`/rozet/ödüle bağlı değil.
- Mikro-görevler (V35): bilmece doğru şık o gün istemciye gitmez; teşekkür (sabit şablon, yalnız kendi sınıfı) XP'si haftalık ödüle SAYILMAZ; `gunun_bilgisi.py`.
- anket: yanıtlar ANONİM (`anket_katilim` ile `anket_yanit` arasında bağ yok); <5 yanıtlı grup gizli. gelisim: yalnız ödev testi + Form kazanım verisi; küçük grup/yetersiz veri gizli, risk etiketi yok.
- etkinlik (havuzdan 3/5/10 soruluk test ödevi): isteğe bağlı kazanım (`soru.kazanim_id`; `arena_soru.kazanimlar`, ≥3 soruluk; eşleşme TAHMİNİ; serbest metin `konu` filtre için kullanılmaz; seçilince `odev_soru.kazanim` = kod; 12. sınıfta liste kapalı).
- denemeler (`denemeler.py`, `rotalar/deneme.py`, `scripts/deneme_*.py`): oku → eşleştir → yükle → yorum EN SON. Öğrenciler arası karşılaştırma YOK (yalnız kendi sırası); <5 katılımcılı grupta özet gizli; varsayılan yayında=0.
- rotalar/pano.py: kiosk `/api/pano` (salt-okunur, LAN); `yaklasan_denemeler` alanını dashboard `deneme_hatirlatma.py` okuyup teneffüste tahtaya yazar.
- sinavlar: V38 `sinav.bitis` (deneme haftasının son günü, isteğe bağlı) → takvim sorguları `COALESCE(bitis, tarih)`; `yaklasan_denemeler` (başlangıca ≤3 gün kalmış ya da süren) pano + tahta tek kaynağı. MEBİ YKS takvimi: `scripts/mebi_takvim_ekle.py [--kuru]` (idempotent; `okul` hedefi BİLEREK değil ). Yeni yıl = betikteki `TAKVIM`.
- kaynaklar/{program, yoklama, kazanim, soru, sms, zil}: dış veri okuyucular. Ders programı `tahtayoklama/data/ders_programi.json` (okul_ana yayını); zil `tahtayoklama/data/zil.json` + `config/takvim.json`; devamsızlık `yoklama_pano.db` (`yoklama.sinif_devamsizlik/ozet`; görüntüleme `erisim_log` `devamsizlik:<sınıf>`); kazanım + maraton soruları Postgres `soru_havuzu`; SMS smssistemi `/api/arac/kod-sms`.
- sohbet (V12): öğretmen+yönetici tek oda, yalnız metin, 30 gün, polling (WebSocket yok), metin yalnız `textContent`.
- acil (`acil.py`, `rotalar/acil.py`, `kaynaklar/acil.py`): 2 adımlı onay (60 sn jeton + şifre), personel konum paylaşımı (adlı, 24 saat sonra silinir, push'a konum/ad konmaz). Alarmın kendisi (zil, SMS, tahta, Telegram) okulda DEĞİL tahtayoklama dashboard'unda çalışır; okul `kaynaklar/acil.py` ile çağırır; tatbikat/gerçek ayrımı dashboard `tahta_alarm_tatbikat` ayarında. `TURLER` anahtarları ve `UST_KAT` dashboard `acil.py` ile aynı kalmalı.
- kutu: yöneticiye ADLI yazılır, yönetici yalnız durum işaretler, kullanıcı başına saatte 5 kayıt.
- tema (`tema.py`, `static/temalar.css`, V27): `<html data-tema>` ile :root değişkenleri yeniden tanımlanır; yeni tema = `tema.py TEMALAR` + `temalar.css` bloğu (animasyon `prefers-reduced-motion` altında). Veli profil sayfası olmadığından orman haritası (`harita`) temasında SABİT (`base.html`); `.arena` kendi koyu kapsamında.
- Öğretmen kokpiti (`/ogretmen`, V28): kişisel not kimse okuyamaz (yönetici dahil); yoklama/nöbet/randevu bilerek YOK. Veli ana ekranı: "okulda" iddiası YOK.
- onay (V29 `onay_talep`/`onay_yanit`; `/ogretmen/onay`, `/veli/onaylar`): yönetici/öğretmen velilerden Evet/Hayır ister; veli çocuk başına yanıtlar, son tarihe kadar değiştirir, yalnız kendi çocuğunu görür; yazar yanıtları adlarıyla görür. `?hata=` yalnız bilinen kodlardan metne çevrilir (URL'den metin yansıtılmaz).
- sinifpdf (V21, `rotalar/pdfgonder.py`): öğretmen sınıfa PDF gönderir, PDF'ten foto teslimli ödev, PDF'ten soru havuzuna katkı (yalnız 9-11). Katkı soruhavuzu `ogretmen-pdf` komutuyla işlenir: `rotalar/bildirim.py` `/api/soru-istek*` uçları `AYAR.soru_anahtar` (`hmac.compare_digest`) ile korunur.
- soru_katki (`/ogretmen/soru-katki`, V41 `soru_katki`/`soru_katki_karar`): öğretmen cevap anahtarlı çoktan seçmeli PDF yükler (kuyruk); soruhavuzu `soru-katki.timer` (2 dk) `/api/soru-katki*` (bildirim.py `_servis_anahtari`) ile çekip havuza 'onayli' yazar ve sonucu döner. Aynı sayfada LLM şıklı 'askida' sorular (`ogretmen-acik:` kaynaklı) o dersin öğretmenine Onayla/Reddet; karar okul.db'ye, havuza soruhavuzu uygular (okul havuza yazmaz). Ders/düzey seçenekleri `inceleme.ciftler`.
- soru_bildirim (`soru_bildirim.py`, `rotalar/bildirim.py`): "soru hatalı"; ağırlıklı eşik `ESIK`=2 (öğrenci/tahta 1, öğretmen 2) → soru okulda gizli. Postgres'e kişi gitmez.
- inceleme (`/ogretmen/inceleme`, V23 `soru_inceleme`): öğretmene günde 5 soru, kendi dersinden (`ogretmen_gorev` → `HAVUZ_KODU`, yalnız 9-11; eşleşmeyen = kart yok), gün başına sabit set; ✅ doğru (yalnız dahili sinyal) / 🚩 hatalı (+sebep → `soru_bildirim` rol=ogretmen, tek bildirimle gizler) / ⏭ pas. Ana sayfa kartı `inceleme_kart` (is defined korumalı).
- soru_gorsel (Postgres `soru_gorsel`): öğrenciye yalnız kendisine gösterilmiş sorunun (`maraton_soru.gosterim`, arena sırası, `calisma_soru`), öğretmene yalnız `soru_inceleme`'deki sorunun görselini açar (yönetici hepsini); değilse 404.
- duyuru_api (`POST /api/duyuru-ekle`): EBYS botu (Müdür PC) rol duyurusu ekler. Yalnız LAN + `X-Duyuru-Anahtar` = `AYAR.duyuru_anahtar` (`hmac.compare_digest`; tanımsızsa 404). Hedef ogrenci|veli|ogretmen (yonetici yok); duyuru `YAZAR` yöneticisi adına, push tetiklenir.
- devamsizlik_api (`POST /api/devamsizlik-bildir`): dashboard öğretmen 'yok' yazınca veliye anlık push; yalnız LAN, `X-Devamsizlik-Anahtar` = `AYAR.devamsizlik_anahtar` (tanımsızsa 404); sabit şablon.
- calisma (`calisma.py`): XP/rozet/haftalık hedefe BAĞLI DEĞİL (sömürülemesin), yalnız GAYRET XP'si yazar. Sunulan soru `calisma_soru`'ya kopyalanır; tekrar havuzu = son `TEKRAR_GUN` günde yanlış, sonradan doğru yapılmamış, gizlenmemiş sorular.
- push (`push.py`): tetikleyiciler `BackgroundTasks` + kendi DB bağlantısı; test: `push._webpush_gonder` monkeypatch. `scripts/odev_uyari.py` + `systemd/farabi-okul-odev-uyari.{service,timer}`: saatlik, yaklaşan ödev push'u (ödev başına 1 kez, 08-20 arası).
- SMS paneli (`/yonetici/sms*`, `rotalar/yonetici.py` + `kaynaklar/sms.py`): taslak/önizle/gönder; gönderim smssistemi `/api/arac` üzerinden (okul SMS atmaz).
- atlas (`rotalar/atlas.py`, `AYAR.atlas_url`): Farabi Atlas (`tahtaatlasfarabi/`, :8099) için öğretmen/yönetici girişli ters vekil. `/ogretmen/atlas` iframe; `/kure/*` + `/api/atlas/*` aynen iletilir (çerez ve `cf-*`/`x-forwarded-*` iletilmez; Atlas kendi CSRF'ini doğrular). Orta katman yalnız `/kure` için `X-Frame-Options: SAMEORIGIN`, geri kalan `DENY`. Ulaşılamazsa 502. Atlas kodunda burada değişiklik yapma.
- kutuphane (V40, plan `LIBRARY_DISCOVERY.md`): yazmalar `BEGIN IMMEDIATE`; kamera yalnız HTTPS; `ayirtma_temizle` öğrenci ana sayfasını asla bozmamalı.
