# Farabi Client

Sınıf akıllı tahtalarında (Pardus/Vestel) koşan ince PyQt6 istemci; ses = tahtada tutulan Gemini Live oturumu (tek ses yolu). Ağır iş (kitap/YKS, render, bulut metin/görsel, dosya işleme) HTTP ile server'a (`server/`, `farabi.local`) gider; tahtada içerik deposu yok, yalnız `icerik/onbellek/`.
- Kapsam yalnız `client/`; çelişkide kök esas. Yerel STT/TTS/Pipecat KALICI İPTAL: ekleme. Mikrofonsuz mod kaldırıldı; hep mikrofonlu.

## Canlı durum: SADE MOD (varsayılan)
- Tahtalarda yalnız `talimat` kipi koşar; kip/dil düğmeleri gizli (`core/tahta.sade_mod()`; `config/api_keys.json` `"sade_mod": false` + restart ders kiplerini döndürür). Ders kodu (motor, program, `ders_icerigi`, `ders_hafizasi`) uykuda, SİLİNMEDİ.
- 15 araç: `web_ac`, `uygulama_ac`, `dosya_ac`, `pencere_kapat`, `pdf_sayfa`, `kitap_sorusu`, `yks_sorulari`, `geogebra`, `ekran_goruntusu_al`, `ekrandaki_soruyu_oku`, `icerigi_kapat`, `youtube_video`, `web_search`, `eba`, `yoklama_al`. `talimat_modundan_cik`, `shutdown_farabi` hariç (`main.SADE_HARIC_ARACLAR`). Video araçları mikrofonu susturur → DEVAM ET / F4.
- Ders görsel arşivi (pilot 10-A): `ders_gorsel_servis.py` + `core/ders_gorsel.py`, `systemd --user` `farabi-ders-gorsel`, bayrak `ders_gorsel.enabled` → server `POST /api/ders-gorsel`.
- Kipler: `ogretmenli` (varsayılan), `ogretmensiz`, `talimat`; `_ders_kipi` önce `config/ders_programi.json`, sonra `api_keys.json`; kurallar `core/prompt.txt`. Konu/kazanım YALNIZ öğretmenden; yıllık plandan konu türetme, "nerede kalmıştık" deme.

## Yerleşim
- `main.py` FarabiLive (oturum, araç dağıtımı, ses döngüleri); `ui.py` PyQt6 HUD; `actions/` modül başına bir fonksiyon, kayıt `kayit.py`; `core/`: `prompt.txt` (persona, KULLANICI-SAHİPLİ), `vision_prompt.txt` + `prompteski.txt` (kod okumaz, silme), `ders_motoru`, `olaylar`, `program`, `zil`, `tahta` (derslik, `tahta_anahtari`), `anahtar`, `saglayicilar` (server havuzuna ince proxy), `modeller.py` (`CANLI_MODEL`), `transcript`, `kullanim`, `version`.
- `tools/` SERVER'da koşan içerik hazırlama; tahtada yalnız `dogrula.py`, `mikrofon_test.py`. `config/` gerçek JSON gitignore, `*.example.json` commit'li. `memory/` KULLANILMAYAN, yeniden bağlama. `planlar/` arşiv. `logs/` gitignore.
- Tahtada `~/farabi` = `client/` sparse-checkout; cron `farabiguncelle.sh` (20:00, `git fetch` + `git reset --hard origin/master`). İSTİSNA 9-A: tam klon `~/farabi/repo` (client `~/farabi/repo/client`).

## Komutlar
```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python main.py
venv/bin/python -m pytest tests/ -q                      # pytest yalnız dev
venv/bin/python -m pytest tests/test_mufredat.py::TestDersEslesir -q   # tek test; -k "ad" ile isimle
venv/bin/python -c "import main"                         # temiz import kümesi
python tools/dogrula.py                                  # içerik kapısı (exit 1 = KIRMIZI)
python tools/mikrofon_test.py --karsilastir              # oran <3x = derse hazır değil
```
- Lint repo kökünden: `.venv-tools/bin/ruff check client`. Tahtada test: `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"`; son kabul fiziksel tahtada Atakan.
- `requirements.txt` gerçek import kümesinden türer: temiz venv + `import main` ile doğrula. Lock tahtaların Python'unda (3.11) üretilir.
- `tests/conftest.py` `FARABI_LOG_DIR` / `FARABI_DERS_LOG_DIR`'i temp'e yönlendirir; yeni loglama bunların arkasında kalsın.

## Yapılandırma
- `config/api_keys.json` elle düzenlenir; UI bu dosyaya ASLA yazmaz, ilk-açılış sihirbazı yok (eski `SetupOverlay` elle alanları silmişti). `_check_config()` yalnız okur. Ortak alanlar (Gemini anahtarı, `mikrofon`, `sunucu_url`) `server/config_dagit.sh` ile dağıtılır.
- `gemini_api_keys`/`gemini_api_key` yoksa Live başlamaz; `sunucu_url` yoksa `http://127.0.0.1:8000` (dev); `tahta_anahtari` yoksa her server çağrısı 401; `derslik` yoksa `DERSLİK TANIMSIZ`, tahtalar arası KOPYALANAMAZ; `ders_kipi` varsayılan `ogretmenli`. `camera_index` ölü.
- Anahtar havuzu (`core/anahtar.py`) kota hatasında hemen sonrakine geçer. Değişmezler: istemci reconnect döngüsünün İÇİNDE kurulur; rotasyon `fail_streak`'i sıfırlar; `kota_hatasi_mi()` dar eşleşir (harcama sınırı, `RESOURCE_EXHAUSTED`, 429, quota, rate limit); `main.py` anahtarı yalnız `anahtar.simdiki()` ile okur (`gorsel_uret` aynı havuz). Rotasyon yalnız AYRI Cloud projelerinde işe yarar. Farabi susarsa faturadan önce `thinking_config`/config alanlarından şüphelen.

## Ses: yeniden tartışma
- Tahta mikrofonları DONANIM sınırı (konuşma RMS ~200–450, sağlıklı 1500–8000); her tahtaya harici mikrofon. Seviyeyi ölçülen tabana göre yargıla (`mikrofon_test.py --karsilastir` / HUD `MİKROFONU KALİBRE ET`).
- Dev makinede kayıt cihazı `acp`. PulseAudio `default` ZORUNLU (donanım 16 kHz reddeder), `hw:*` sabitleme.
- VAD / `realtime_input_config` / `AutomaticActivityDetection` GERİ EKLEME (Farabi sağır oldu). Ses config'i tam olarak `output_audio_transcription={}`, `input_audio_transcription={}`. `language_codes`/`language_hints` Live'da reddedilir (oturum açılmaz). Gürültü prompt'taki "KALABALIK VE GÜRÜLTÜ" kuralıyla.

## Mimari
- Oturum (`main.py`): `_build_config()` (zaman, çerçeve, kip, `[DERSLİK]`, `prompt.txt`, dil) → `CANLI_MODEL`'e bağlan → ses döngüleri + 15 sn mikrofon tanısı → `_send_session_opening()`. Oturum yalnız **DERSİ BAŞLAT** çift tıklamasıyla başlar (boşta oturum para yer), boşta kapanma `BOSTA_KAPATMA_DK` (15). Yeniden bağlanmada `_oturum_devam_notu()` gider. Açılış "sadece bu açılış turunda araç çağırma" der; açılış kuralları tur kapsamlı kalsın.
- `thinking_config` YOK (Live modeli sustu); `tests/test_oturum_yapilandirmasi.py` `_build_config` ve `_build_talimat_config`te `thinking_config is None` bekler. `system_instruction` ve `tools` İKİSİ de `LiveConnectConfig`'e ulaşmalı (biri sessizce eksik kalmıştı); araç kullanımı sessizleşirse prompt'tan önce bunu kontrol et.
- Ders sonu (`shutdown_farabi` → `_dersi_bitir`) süreci kapatmaz; `_DersBitti` sonraki DERSİ BAŞLAT'a kadar bekletir; transcript `/api/egitim/ders_kaydi_yedek`'e POST (hata sessiz).
- Talimat işaretleri (`[DERS_ACILISI]`, `[DERS DURUMU]`, `[ÖĞRETMEN KOMUTU]`, `[OTURUM DEVAM]`) transcript'ten `_ETIKET_RE` ile ayıklanır; saat `%H:%M` (12 saatlik ASLA).
- Ders dili (sade modda gizli): DERSİ BAŞLAT'tan önce seçilir, sonra kilitli; `prompt.txt` Türkçe tek kaynak, sona `[DİL KURALI]`; açılıştaki sabit Türkçe `ders_dili`ye göre dallanmalı (`_acilis_selam_gun`).
- Araç dağıtımı: bildirimler yalnız `actions/kayit.py`'den. Yeni araç = `actions/<ad>.py` + `Arac(...)` kaydı + `_execute_tool`'da `elif`; `tests/test_arac_kaydi.py` sapmada kırılır. `aciklama` modele aynen gider: kısaltmak aracın çağrılmamasına yol açar. `calisma`: `isci` (thread, `zaman_asimi` ile beklenir) · `satirici` (inline) · `arkaplan` (BEKLENMEZ, `gorsel_uret`; kendi timeout'u). `izin`/`maliyet` yalnız metadata. Çağrı: `fn(parameters=args, player=ui, speak=self.speak)`.
- Server destekli araçlar SESSİZ başarısız olur: `ok` olmayan yol kısıtlayıcı "uydurma" metni döner (`_SINIRLI_DEVAM`, `actions/ders_icerigi.py`), istisna atmaz; metin bağlayıcıdır.

### Yetenek sınırı: AŞMA
- Ders kiplerinde (`ogretmenli`/`ogretmensiz`): uygulama başlatma, terminal, OS ayarı, tarayıcı otomasyonu, mesajlaşma, süreç yönetimi YOK. `file_processor` yalnız belge/görsel (kod desteği kaldırıldı). `reminder`, `save_memory` kaldırıldı, kaldırılı KALIR.
- İstisnalar: talimat kipi araçları (kullanıcı kararı; ders kiplerine SORMADAN genişletme); `geogebra` (kilitli `chrome --app`, localhost); `yoklama_al` (`subprocess.Popen`).
- ⚠️ `yoklama_al` `<client>/../tahtayoklama/yoklama.py` arar; yalnız 9-A tam klonunda var, sparse-checkout tahtalarda tahtayoklama `~/tahtayoklama`'da → "bulunamadı".
- Açık delikler (yerleşik davranış DEĞİL): `youtube_video` `play` ve `eba` `video` → `xdg-open` (denetimsiz tarayıcı); `summarize` `save: true` `~/Desktop`'a yazıp açar.

### Talimat kipi (`KIP_TALIMAT`)
- Ders yok, yalnız öğretmen sesli komutu; `_build_talimat_config()` yalnız `_TALIMAT_PERSONASI` kullanır, `_ders_motoru_dongusu()` no-op.
- `web_ac` (gerçek tarayıcı; yalnız `file:`/`javascript:`/`data:` engelli), `uygulama_ac` (elle ad→komut tablosu: `pardus-pen`, `drawing`, `nemo`, `gnome-calculator`, `evince`, `gnome-screenshot`; terminal bilerek yok), `dosya_ac` (yalnız `$HOME`), `pencere_kapat` (`wmctrl -c` BAŞLIK alt dizgisiyle, PID ile değil).
- Mikrofonda konuşmacı doğrulaması yok; kullanıcı "odaya güven"i bilerek seçti: beyaz listeye GERİ DARALTMA.
- `_ders_kipi` HER `_build_config()`te `_ders_kipi_taban`dan hesaplanır; çıplak `FarabiLive.__new__` fixture'ları `_ders_kipi_taban`ı da set etmeli.
- Çıkış: `talimat_modundan_cik` `ui.talimat_modu = False`'u doğrudan yazar, görseller için `_talimat_cikis_sig` ayrıca yayar; BİRLEŞTİRME. `_TalimatCikisi` `tg.create_task()` izleyicisinden atılır (`_execute_tool` içinden değil: try/except yutar); `run()` `_talimat_cikis_istendi`'yi backoff'tan ÖNCE kontrol eder.

### Araçlar
- `ders_icerigi`: `{ders, konu, sinif, tema, derslik}` → `/api/egitim/ders_icerigi`; öğretmenin ders+konusuyla çağır. `transcript.log_frame()` buradan çağrılır.
- `kitap_sorusu`: RAG İPTAL, server "hata" döner, kalıntı; geri açma. `ders` ZORUNLU; `_ders_eslesir`'i `ders_icerigi.py`'den alır (yeniden adlandırma).
- `pdf_sayfa`: tek sayfa no, `ders` zorunlu; PNG (30 dosya LRU, `icerik/onbellek/pdf_sayfa/`) + `/api/egitim/pdf_sayfa_metni` ile gerçek metin (yoksa model uydurur); `derslik` gönderir.
- `yks_sorulari`: bir soru görseli; ilerlemek `sonraki=true` ister.
- `site_goster`: tarayıcısız; alan adı beyaz listesi (sonek eşleşmesi), yönlendirmeden SONRA tekrar kontrol (`tr.wikipedia.org.evil.com`, `file:///etc/passwd` reddi testli); HTTP başlıkları latin-1.
- `eba`: `pdf` yalnız eba.gov.tr, metin YEREL çıkarılır.
- `geogebra`: 127.0.0.1 stdlib HTTP köprüsü + `chrome --app`; çevrimdışı paket (~120 MB) git'te yok: `icerik/geogebra/GeoGebra` (`server/geogebra_dagit.sh`), yedek server `/geogebra/`. CAS yalnız klasik uygulamada.
- `ekran_goruntusu_al` / `ekrandaki_soruyu_oku`: yalnız tahtanın KENDİ ekranı (`_screenshot_sig`, GUI thread), LRU 20. Soru görseli DOĞRUDAN Gemini'ye `send_client_content` ile gider (`FarabiLive.ekrani_modele_gonder`, ≤1024px JPEG q70, `[EKRAN]`); `send_realtime_input(video=…)` rakamları yanlış okudu, KULLANMA. Yakalamadan önce Farabi kendini küçültür (`ui.py::_ekran_goruntusu_yakala`/`_ekran_goruntusu_cek`); aktif pencere başlığı (`xprop`) kişisel veri filtresine uyarsa (yoklama/e-Okul/MEBBİS/tahtayoklama) yakalamaz. Yazılı "ekranı oku" (`_ekran_okuma_komutu_mu`) modele gitmeden tetikler.
- `file_processor`, `web_search`, `youtube_video` → `core/saglayicilar.py` → server proxy. `youtube-transcript-api` sabitsiz ve bir kez bozdu: dokunurken gerçek video ID ile dene.

### Persona (`core/prompt.txt`)
- İstenmeden yeniden yazma; ders kitabı içeriği KOYMA. `SINIRLARIN` bloğu yük taşır: tek mikrofon, KONUŞMACI KİMLİĞİ YOK; kalan süre YALNIZ `[DERS DURUMU]`'ndan; ÖZEL KANAL yok. Diarization/işleyen saat gelirse bloğu yeniden yaz, silme.

### Ders motoru, panel, olaylar, zil
- `core/ders_motoru.py` (`enjekte=True`): akış kodda (`BEKLIYOR → YOKLAMA → … → OZET → ODEV → BITTI`). Enjeksiyon: `turn_complete=True`; ilk `ENJEKSIYON_GECIKMESI_SN` (75 sn) yok, `_is_speaking` iken asla; `[DERS DURUMU]` yalnız değişimde (20/10/5/2 dk bandı), periyodik ASLA. ÖĞRETMEN KAZANIR: `gec()`, kilitli `duraklat()` (yalnız `devam` açar), süreli `mudahale()` (`MUDAHALE_SURESI_DK` = 5).
- Müdahale düğmeleri tam olarak **DURDUR**, **DEVAM ET**, **⏹ DERSİ BİTİR** (çift dokunuş; `on_ders_bitir` → `_on_ders_bitir` → `_dersi_bitir()`, `_ders_bitiriliyor` ile korumalı). Giriş kutusundaki HER ŞEY `[ÖĞRETMEN KOMUTU] …` olarak gider (`_on_teacher_command`: `konu:`/`kazanım:`/`ders:` ayrıştırır). İşaret yük taşır (prompt'taki `ÖĞRETMEN KOMUTLARI` bloğu), sesli sözler işaret ALMAZ. Tahtada auth YOK.
- UI: `F4` mute, `F11` tam ekran; `core.zil`/`core.tahta` `try/except` ile içe alınır; pencere boyutu HESAPLANIR (`availableGeometry()` %94); kalem/silgi (`_CizilebilirGorsel`) yalnız düğme, model aracı DEĞİL.
- `core/program.py` + `config/ders_programi.json` (sınıf → gün → ders saati → ders, +`kip`); boş slot → öğretmene sor. `core/zil.py` + `config/zil.json`: 08:20, 40 dk ders, 10 dk teneffüs, öğle 12:20–13:00. Zaman ifadeleri EKSİZ (model ekleri doğru getirir). İki dosya gitignore; kaynak `okul_ana` → `tahtayoklama/data/` → `server/config_dagit.sh` (kök AGENTS.md).

### Loglama
- `logs/ders/<zaman>_<derslik>.txt`: oturum başına tek dosya, YALNIZ metin, ASLA ses; etiketler ÖĞRENCİ / FARABİ / ÖĞRETMEN / SİSTEM; öğrenci kimliği yok. `logs/farabi.log` dönen 5 × 1 MB.
- Token (`core/kullanim.py`): `TOKEN …` satırları. Mesajlar tekilleştirilmeden toplanır, tur başına usage sayısı DOĞRULANMADI → eğilim için `en_buyuk_baglam`a bak.
- Düşünce zinciri/araç çağrısı kayda sızabilir; TEK savunma `_konusma_temizle()` (`_THOUGHT_RE` + araç deseni, yalnız BİLİNEN araç adları).

### Sağlayıcılar ve kota
- Gerçek zamanlı tek seçenek Gemini Live. Diğer metin/görsel iş `core/saglayicilar.py` → `server/saglayicilar.py`; `metin_uret`/`gorsel_uret` imzaları sabit, toplam başarısızlıkta `RuntimeError`. Sağlayıcılar modeli habersiz emekli eder: ID'leri kontrol et. Maliyet kaldıracı boşta oturum; kota için AYRI Cloud projesi anahtarları; havuzu `farabi.log` ölçümüyle boyutlandır.
