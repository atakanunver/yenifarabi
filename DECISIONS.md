## 2026-10-10 - Soru üretimi, kazanım testi ve idari yükleme zamanlayıcıları kalıcı kapatıldı; 12. sınıf donduruldu; Maarif odağı
- Ne: `systemctl disable --now` → `soru-havuzu-uret.timer`, `kazanim-test.timer`, `kazanim-test-sonuc.timer`, `kazanim-test-aylik.timer`, `farabi-idari-yukle.timer` (servisleri de durduruldu). Bu makinede zamanlanmış özet çıkarma işi yoktu. `farabi-api` (tahtada kitap sorusu/PDF) ÇALIŞIYOR, dokunulmadı.
- Neden: kullanıcı kararı ("soru üretmeyi, özet çıkarmayı, ders kitabı ile ilgili iş ve işlemleri servisleri kalıcı olarak durdur"; kazanım testi, sonuçlar/aylık rapor ve idari yükleme ayrıca seçildi). 12. sınıf kitapları değişecek → 12. sınıfa ikinci emre kadar dokunulmaz; 9-10-11 Maarif modeline tabi, soru bankası çalışmaları Maarif öğrenme çıktılarına odaklı.
- Durdurulduğu andaki banka: kazanıma bağlı onaylı soru 11.005 (etiket 2.422 + LLM 8.583), üretilmiş/denetimsiz 6.363; LLM sınıflandırmada ~3.100 soru işlenmeden kaldı.
- Geri açmak: `sudo systemctl enable --now <ad>.timer` — yalnızca kullanıcı isterse.

## 2026-10-10 - Soru bankası: şık sırası dengesi, LLM kazanım sınıflandırması, üretim penceresi 08:00, kaldığı yer işareti
- Teşhis (canlı DB): doğru şık %35 A / %43 B / %18 C / %4 D (yeni üretimde D %2,4) — Ollama doğruyu öne koyuyor. `sik.kanonik_sira`: şıklar soru+şık metninin sha256'sına göre (sayısal şıklar küçükten büyüğe) dizilir; konuma atıflı ("A ve B", "hepsi") ve harf önekli ("A) …") şıklara dokunulmaz. `vt.soru_ekle` her yeni soruya uygular; geçmiş için `calistir sik-karistir` çalıştırıldı: 22.573/25.171 satır, sonra A=5.967 B=6.688 C=6.638 D=5.878, ikinci çalıştırma 0 değişiklik. Gönderilmiş kazanım testleri etkilenmez: `sonuc.py` puanlamayı `form_testi.sorular` kopyasından yapar. Yedek: `/mnt/farabi-data/farabi/soru_havuzu/yedek/soru_havuzu_20261010_1452.dump`.
- `siniflandir`: gömme eşiğini (0,55) geçemeyen 14.254 onaylı soru → aynı sınıf+ders en yakın 5 kazanım adayı → Ollama seçer ya da "hiçbiri" (`kazanim_kaynak='llm'`, `kazanim_siniflandirma_at` = kaldığı yer). 24 soruluk denemede 14 bağlandı, bağlar mantıklı, model temkinli. Gece `uret` kazanımlar bitince bunu çağırır.
- Üretim penceresi hafta içi 08:00–17:05 (ilk zil 08:10; önceki 07:30 sabah 30 dk kaybettiriyordu). `uret --denetimsiz` zamanlayıcıda (AGY kotası bitti; denetim sonra toplu bulut LLM). `uret_durum.json` her kazanım sonunda yazılır; asıl devam kaynağı veritabanı.
- Açık: kazanım katmanı (programların tek derse katlanması, hafta=satır, kod okunmaması) — plan `docs/superpowers/plans/2026-10-10-kazanim-katmani.md`, onay bekliyor.

## 2026-10-08 - Dashboard: menü çubuğu kabuğu + /servisler servis yönetimi (farabi-servis betiği)
- Ne: Windows tarzı menü çubuğu (Dosya/Düzen/Yoklama/Tahtalar/Servisler/Uygulamalar/Görünüm/Yardım) + 6'lık ikon şeridi + mobil ☰ çekmece; tek kaynak `menu.py`. Yeni `/servisler`: 6 servis (farabi-api, smssistemi, dashboard, ollama, open-webui, sinif-arena) + 5 zamanlayıcı için yeniden başlat/durdur/başlat, zamanlayıcı aç-kapat, şimdi çalıştır, hatayı temizle, maskeli log, son hata satırı, soru havuzu kazanım kapsamı. Spec/plan `docs/superpowers/{specs,plans}/2026-10-08-dashboard-menu-servis-yonetimi*`.
- Yetki: dashboard yalnız `sudo -n /usr/local/sbin/farabi-servis <eylem> <birim>` (root 755, kaynak `dashboard/scripts/`; sudoers `/etc/sudoers.d/farabi-servis`). `ata` zaten tam sudo'lu — betik ayrıcalık sınırı değil, web katmanındaki bir hatanın keyfi komuta dönüşmemesi için. Liste iki yerde (betik + `servis_yonetimi.BIRIMLER`), `test_farabi_servis` eşitliği denetler. Ders saatinde derse etki eden servis için ikinci onay (409); soru havuzu "şimdi çalıştır" ders saatinde 403; her eylem `uzaktan_denetim` (`kaynak='servisler'`).
- Tuzaklar (yaşandı): ollama restart'ı ExecStartPost ön-yüklemesini bekler → `--no-block`; dashboard kendi restart'ı `systemd-run --collect` + benzersiz birim adı; uygulama hataları journal'a info önceliğiyle düşer → log süzgeci `--grep`; `[hidden]` sınıf display'ine yeniliyordu; tarayıcı eski pano.css'i tutuyordu → `?v=<static mtime>`; şablonlar anında canlı, Python restart ister → master'a alınca hemen restart (aradaki ~8 sn'de 500).
- Kullanıcı kararları: yetki "kontrol + log" (ayar dosyası düzenleme yok), "düzen yeni, renkler aynı", varsayılan tema koyu.

## 2026-10-08 - farabi ve bilgehan saat dilimi UTC → Europe/Istanbul (kullanıcı isteği)
- `timedatectl set-timezone Europe/Istanbul` (farabi: sudo; bilgehan: `sudo -S`). debian, zil, tahtalar, Müdür PC zaten İstanbul.
- Zamanlayıcılar ETKİLENMEDİ: hepsinin `OnCalendar`'ı açık `UTC` ekli (ör. `13:30:00 UTC`); değişiklik öncesi/sonrası `list-timers` next değerleri birebir aynı. CLAUDE.md'deki "14:15 UTC = 17:15 TR" notları geçerli.
- Kodda sistem dilimine bağlı zaman yok (server, dashboard, smssistemi, soruhavuzu, kazanimtest, openwebui, arenasinif taraması — hepsi açık İstanbul). Journal artık TR saatiyle görünür; çalışan servislerin kendi log zaman damgaları restart'a kadar UTC kalabilir.
- PostgreSQL `timezone` BİLEREK UTC bırakıldı: değişirse `timestamp without time zone` + `now()` sütunlarına yerel saat yazılmaya başlar, eski veriyle karışır.

## 2026-10-08 - soru-havuzu-uret failed: AGY denetim istemi E2BIG (tek argüman > 128 KB)
- Kök neden: `denetci.agy_cagir` istemi `agy -p <istem>` ile ARGÜMAN olarak veriyor; kaynakları farklı 100 soruluk bir pakette (soru başına ≤2500 kr kaynak) istem Linux `MAX_ARG_STRLEN`'i (131072 bayt) aştı → `OSError: [Errno 7] Argument list too long`, 2026-10-07 23:01 UTC, 8 saatlik çalışmanın sonundaki denetimde.
- Tuzak: `agy -p -` stdin OKUMUYOR — "-"yi istemin kendisi sanıp "gereksinimleri paylaşır mısınız" diye cevaplıyor (2026-10-08 denendi). Bu yolla süreç çökmez ama her paket sessizce 0 karar döner.
- Düzeltme (`fd0c9f1`): argüman yolu korunur, `paket_denetle` istemi `ISTEM_AZAMI_BAYT = 120_000`'e sığana kadar paketi %10'ar küçültür; kalanlar sonraki pakete. Test `test_istem_tek_arguman_sinirini_asmaz_kalan_sonraki_pakete`.

## 2026-10-08 - Farabi Web Servisleri Yük Hafifletme ve Performans Optimizasyonu (Aşama 1-4)
- Kullanıcı onayı: "diğer çözümlerin hepsini uygula 1.2.3.4" (Bilgehan Chatterbox GPU yerleşimi iptal, küme mimarisi wiki güncellendi).
- **Aşama 1 (Nginx Ters Proxy & Gzip Sıkıştırma):** Nginx port 80'e yerleştirildi. Open WebUI drop-in (`/etc/systemd/system/open-webui.service.d/port.conf`) ile `127.0.0.1:8088` portuna çekildi. Nginx root (`/`) üzerinden WebSocket destekli olarak Open WebUI'a proxy yapar. Ayrıca `/arena/`, `/yoklama/`, `/sms/` temiz yönlendirmeleri sağlandı. HTML/CSS/JS/SVG/JSON için Gzip sıkıştırma (`gzip_comp_level 6`) açılarak okul ağındaki statik dosya yükü ve ağ gecikmesi düşürüldü.
- **Aşama 2 (SQLite WAL & Eşzamanlılık):** `tahtayoklama/dashboard/db.py` ve `smssistemi/db.py` içinde bağlantı açılışlarına `PRAGMA synchronous=NORMAL;` ve `PRAGMA busy_timeout=5000;` eklendi. `yoklama_pano.db`, `pano.db` ve `smssistemi.db` doğrudan WAL moduna ve synchronous=NORMAL seviyesine getirildi.
- **Aşama 3 (SSH & Donanım Polling Optimizasyonu):** `tahtayoklama/dashboard/sistem_durumu.py` donanım toplama periyodu `TOPLAMA_ARALIGI_SN` 15'ten 30 saniyeye çıkarılarak D-Bus ve alt süreç yükü %50 azaltıldı. `ssh_istemci.py` ve `sunucular.py` bağlantı zaman aşımı 5'ten 3 saniyeye indirilerek kapalı tahtalarda bekleme süresi kısaltıldı. `fenlab` tahtası `master` dalına çekilip güncel commit ile senkronize edildi.
- **Aşama 4 (Ağır Görev İzolasyonu & Cgroups v2 / Scheduler):** Canlı ders saatlerinde (07:30–17:05) soru üretiminin engellendiği (`soruhavuzu/zaman.py`) ve Sınıf Arenası'nın derste hazır havuzdan beslendiği teyit edildi. Arka plan servisleri (`soru-havuzu-uret.service`, `kazanim-test.service`, `kazanim-test-sonuc.service`, `kazanim-test-aylik.service`, `farabi-idari-yukle.service`) sistem genelinde `Nice=15`, `CPUSchedulingPolicy=batch`, `CPUWeight=20`, `IOWeight=20`, `IOSchedulingClass=best-effort`, `IOSchedulingPriority=7` ile izole edildi.

## 2026-10-08 - Debian TTS: Chatterbox → EMA Lightning (EBYS); zil anonsları bilgehan Chatterbox'ına
- Kök neden (EBYS "ses oluşturma/özet donuyor"): bot özetin TAMAMINI tek istekle Chatterbox'a (debian, GTX 1060, 3,8 GB RAM) yolluyordu; uzun metinde süreç 3,2 GB RAM + 3,7 GB swap'a çıktı, 394 karakter 78 sn sürdü, sonraki istek botun 90 sn zaman aşımını aştı (bot her belgede bekliyor = "donma"), 2026-10-07 16:08:39'da çekirdek OOM ile öldürdü.
- Karar (kullanıcı): debian'da Chatterbox yerine EMA Lightning (`ema-lightning` 1.0.4, 8,6M parametre, Apache-2.0; paket kurulmadan incelendi: `torch.load(weights_only=True)`, ağ yalnızca HF indirmesi). Servis `ema-tts.service`, `/opt/ema-tts/` (venv torch 2.6.0+cu124, GTX 1060 sm_61), aynı API (`POST :5002/konus {text,hiz}`, `/saglik`, `/saglik/detay` aynı alanlar) — EBYS botu ve dashboard kartı değişmedi. Ölçüm: 491 karakter (~29 sn ses) 0,49 sn (RTF 0,017), VRAM 1,4/6 GB; çıktı 48 kHz. Tuzak: GTX 1060'ta Triton yok → `lightning()` içindeki torch.compile her açılışta ~4 dk deneyip düşüyordu; `TORCHDYNAMO_DISABLE=1` ile açılış 287 → 32 sn (CUDA graph'lar derlemesiz kayıtlı). Açılışta ısınma çağrısı var (ilk say() CPU'da 77 sn ölçüldü).
- Zil anonsları (zil .230 `~/ses/dashboard.py`, kullanıcı kararı): bilgehan'daki Chatterbox'a (`farabi2-ses`, `POST http://192.168.23.223:8060/tts {"metin"}`, ≤2000 karakter) yönlendirildi; bilgehan hız almıyor. Yedek `dashboard.py.yedek-20261008-tts`; `ses_dashboard` restart edildi, `ses_bot` dokunulmadı. Zil reposunda commit'lenmedi.
- Açık kalanlar: Chatterbox durduruldu/devre dışı ama `/opt/chatterbox-tts` (9,4 GB) + `/opt/coqui-tts` diskte (silme izni otomatik denetimde reddedildi, kullanıcı kararı bekliyor). EBYS'deki 195 eski Chatterbox `ses.wav` yerinde (yeniden üretim de reddedildi) — yeni belgeler EMA sesiyle gelir.

## 2026-10-08 - YKS çıkmış soru araması: kapak sayfası + uydurma soru (11-A/11-B), sayfa→konu haritası
- Olay: "dörtgenlerde açı ile ilgili soru" → `yks_sorulari(ders='matematik', konu='DÖRTGENLERDE AÇI')` → AYT_EA_1 s.113 = Matematik KAPAK sayfası tahtaya yansıdı; 11-A'da Gemini sayfada olmayan "ABCD dörtgeninde m(DAB)=80°…" sorusunu uydurdu, "sonraki" s.117/118 konu dışı geldi.
- Kök neden (`server/yks.py`): `ders` kelimesi puana giriyordu (her matematik sayfasında geçer → hepsi 0,5, eşitlikte ilk sayfa = kapak); ek kırpma yok ("dörtgenlerde"≠"dörtgen"), "açı" `len>3` ile atılıyordu; soru içermeyen sayfa (kapak/TOPLAM/cevap anahtarı) elenmiyordu; alaka eşiği yoktu.
- Düzeltme: `server/yks_konu_haritasi.py` PDF yer imleri + sayfadaki beyaz kalın konu bantlarından sayfa→konu haritası üretir (`icerik/eslemeler/yks_konu.json`, PDF değişirse yeniden çalıştır + farabi-api restart). `yks.py`: puan yalnızca konudan (etiket ×2, gövde ×1), ek-toleranslı yerel eşleşme (`metin_araclari` değişmedi), şık/`20xx-AYT` etiketi olmayan sayfa aday değil, cevap anahtarı bölgesi dışarıda, alaka eşiği altı → `bos`, dosyalar arası aynı sayfa tekil (EA_1 s.181 = SAY s.79), sunum metnine "metinde olmayan soru/şekil/şık UYDURMA" + sayfa konusu. Harita yoksa fail-open.
- Kullanıcı kararı: Farabi derste soru ÜRETMEZ; "N soru oluştur/hazırla" istekleri `yks_sorulari`'na gider (`AZAMI_ADET` 6→10; client araç açıklaması + prompt.txt). Soru havuzu (oyunlar) tahtaya bağlanmadı.
- Not: 2026-10-03 "tahta RAG'ı hata döner" notu eskimişti — 2026-10-04'ten beri gömme+rerank bilgehan'da, `/api/egitim/question` çalışıyor (2026-10-08 fenlab: rerank ~0,3-0,4 sn, toplam ~5,5 sn); CLAUDE.md düzeltildi.

## 2026-10-08 - Öğrenci listesi tutarlılığı: rehber düzenleme hatası + tek kaynak pano DB
- Hata: smssistemi rehberinde kişi düzenlemek `okul_no` ve `veli_rol`'ü NULL'luyordu (formda alan yok, `kisi_guncelle` varsayılanı None). Düzeltme: mevcut değerler korunur (`app.py::rehber_kisi_duzenle`, test `test_rehber_duzenle.py`). 12-B'de bir öğrencinin numarası bu yüzden boştu.
- Veri düzeltmesi (yedek `smssistemi/veri/smssistemi.db.yedek-20261008-okulno`): no 160/191 + velileri 11-A→11-B, 12-B öğrencisine okul_no 220. Kaynak = pano/tahta yoklama listesi (kullanıcı: "en güncel liste yoklama listesi"). Sonrası pano↔rehber 96/96 aynı (sınıf, no).
- Atos öğrenci aracı eski `tahtayoklama/data/roster/*.json` (2026-09-12) yerine pano DB'den okur; eski dosyalar veri diskine arşivlendi (kişisel veri, git'te yok).
- Kazanım raporu SMS'i öğrenciyi YALNIZCA okul_no ile bulur (okul genelinde tekil, doğrulandı).

## 2026-10-07 - Kazanım testi hattı: Google Form = Apps Script; formda yalnızca okul no; öğrenciye SMS
- Yeni `kazanimtest/` (servis değil, script + timer, server venv): haftanın yıllık plan kazanımı → aday soru (MEB `kazanim_test_soru` önce, sonra `soru_havuzu` onaylı; bge-m3 CPU benzerliği) → agy seçim/eleme (başarısızsa benzerlik sırası) → Excel/Word (`/mnt/farabi-data/farabi/kazanim_testleri/`) → Google Form (Quiz) + yanıt Tablosu → isteğe bağlı öğrencilere SMS. Kayıt `soru_havuzu.form_testi`, `UNIQUE(sinif, ders, hafta)`.
- Google tarafı **Apps Script web uygulaması** (okul hesabında, "Herkes" erişimi + Script Properties `ANAHTAR`): sunucuya OAuth/yeni kütüphane gerekmez (Kural 8: kullanıcı onayı 2026-10-07). Forms API (OAuth token yönetimi) ve agy'nin tarayıcıyla form doldurması (başsız, 2FA/arayüz kırılgan) reddedildi.
- Gizlilik istisnası (kullanıcı kararı): Google'a yalnızca soru metni + öğrencinin yazdığı **okul numarası** ve cevapları gider; ad/telefon gitmez. CLAUDE.md "Gizlilik"e işlendi.
- smssistemi: `/api/arac/ogrenci-taslak` + `/ogrenci-gonder` (veli akışının genelleştirilmesi; `veli_taslaklari.tur` + `test_telefon` kolonları). `test_telefon` doluysa SMS yalnızca o numaraya gider (deneme). Test numarası yalnızca gitignore'lu `kazanimtest/config/gizli.json`'da.
- Bilinen: MEB `kazanim_test_soru` yalnızca 12. sınıf, 5 şıklı, `cevap` boş → şimdilik tüm sorular soru havuzundan. Timer ilk haftalarda `--sms`siz; beyaz liste (`config/ayar.json::dersler`) boş başlar.

## 2026-10-06 - Mikrofonsuz mod koddan tamamen kaldırıldı (kullanıcı kararı)
- Kaldırılan: MIKSIZ_KURALLARI, [DEVAM]/[DERS_KAPANISI] otomatik devam döngüsü, 40 dk kapanış, panel MİKROFONLU/MİKROFONSUZ düğmesi, DERSİ BAŞLAT konu kutusu (_KonuDiyalogu), öğretmen modu kilidi, tahta.mikrofon_var(), server/mikrofonsuz_dagit.sh, test_mikrofonsuz*.py. Farabi her zaman mikrofonlu: ses girişi açılır, yoklama sesle sorulur. Tahtaların api_keys.json'undaki "mikrofon" alanı artık okunmuyor.
- Bilinen risk (kullanıcıya söylendi): tahta mikrofonları bozuk diye mod 8 tahtada açıktı; gürültü söz kesmeye yol açabilir — öğretmen MİKROFON düğmesiyle sessize alır. Testler: client 241 (9-B geçici kopya; 57 mikrofonsuz testi silindi, açılış testleri test_acilis.py'ye taşındı).

## 2026-10-06 - Farabi ders çerçevesine bu haftanın yıllık plan kazanımı
- `GET /api/egitim/kazanim?derslik=&ders_no=[&tarih=]` (`server/kazanim.py`, tahta auth): ders adını SUNUCU çözer (tahtayoklama `data/ders_programi.json` — hedef branşlı adlar; tahtanın client kopyasında yok), kazanımı `data/kazanimlar.json`'dan döner; her hata `{"durum":"yok"}`. Bilinçli bağ: farabi-api tahtayoklama/data dosyalarını salt-okur.
- Client `_cerceveye_plan_kazanimi_ekle` ders başında arka planda (≤4 sn) sorar, `kazanim_kaynagi="plan"`; prompt "Kazanım (yıllık plan, bu hafta)" + öğretmene konu yine sorulur (kullanıcı kararı); öğretmenin kazanımı önceliklidir. Testler server 224, client 295 (9-B'de geçici kopyada). 20:00 pull kaçtığı için 8 tahtada `farabiguncelle.sh` elle çalıştırıldı (86d9f90); app yeniden açılınca devrede. Son kabul testi fiziksel tahtada (Kural 12) bekliyor.

## 2026-10-06 - "Hedef" (sınav hazırlık) saatleri branşlı; hedef temelli planlar tarihle eşlenir, takvim oylamasına girmez
- 12-A/12-B'nin 3'er "Hedef" saatinin branşı öğretmen programından (o saatte giren öğretmen) çıkarıldı, kullanıcı teyitli: 12-A Pzt5 fizik / Çrş7 kimya / Prş5 biyoloji; 12-B Salı5 tarih / Çrş6 coğrafya / Prş3 matematik. `ders_programi_yukle.HEDEF_BRANSLARI` → tahtayoklama `ders_programi.json`'da "hedef <branş>" (yoklama başlığı "HEDEF FİZİK", pano "HDF FİZ"). `mudur/` kopyası (Farabi client) DEĞİŞMEDİ.
- Hedef temelli planlar tatil haftalarını da numaralar (41 hafta); satırlar tarihle yerleşir. `TAKVIM_OYU_DISI`: bu planlar oylamaya girmez — ingilizce 11/12 ile 5 plan olunca 38-41. haftalar MIN_OY'u geçip takvime giriyordu.
- Yeni genel kurallar (başka planı değiştirmedi): "Etkinlik Haftası", "N. Dönem N. Sınav" yer tutucu; sondaki " •" / "," atılır.
- Hedef tarih planı 12-16 Nisan'ı ara tatil yazmış (okul takvimiyle çelişiyor) → 27. hafta boş. Hedef biyoloji/matematik/coğrafya planı yok.

## 2026-10-06 - 14:00 öğle devamsızlık SMS'i hiç gitmiyordu: ayar kapalıydı, sayfa "AÇIK" diyordu
- Kök neden: `otomasyon_ogle_aktif` 2026-10-04'te özellik eklendiğinden beri hiç "1" olmamıştı (günlükte 14:00 tetiklenme satırı yok; panelden açma isteği yok). Otomasyon sayfasının ana şalteri `aktif = sabah VEYA öğle` ile hesaplandığından, sabah açık olduğu için "AKTİF — 09:00 ve 14:00" görünüyordu.
- Çözüm: ayar açıldı (`otomasyon_ogle_aktif=1`); sayfa artık ikisi de açıksa AKTİF, yalnızca biri açıksa "KISMEN AÇIK" + hangisinin kapalı olduğunu gösterir (test `test_otomasyon_sayfa_yalniz_sabah_acikken_kismen_gosterir`). Öğle derlemesi 2026-10-05 verisiyle kuru doğrulandı (1 öğrenci / 2 veli SMS'i kaçmıştı).

## 2026-10-06 - Saati yanlış açılan tahta geçmiş günün yoklamasını ezemez; 10-A CMOS pili
- 10-A her açılışta son kapanış saatiyle başlıyor (journal boot listesi: "Mon 17:16" ile açıldı, gerçek Salı 08:12; NTP 1-2 dk sonra eşitliyor) → CMOS pili bitik, değiştirilmeli. O birkaç dakikada kaydedilen yoklama YANLIŞ TARİHLE yazılır.
- Risk (tahta istemcisiyle yeni doğdu — SSH yalnızca bugünün dosyalarını okurdu, istemci son 7 günü iter): yanlış tarihli kayıt geçmiş günün gerçek 'alindi' satırını daha geç kaydedilme_saati yüzünden ezerdi. Çözüm `yoklayici.itilen_kaydi_yaz`: tarih < bugün (İstanbul) ve satır zaten 'alindi' ise YAZILMAZ (200 döner, istemci tekrar denemez) — yoklama.py yalnızca o anki dersi kaydettirdiği için geçmiş güne meşru düzeltme yolu yok; geçmiş gün için yalnızca hiç görülmemiş kayıt eklenir. Gelecek tarih → 422. Testler `test_tahta_api` (bugün setUp'ta 2026-10-06'ya sabit).
- 9-A "otomatik giriş yok" uyarısı eskimişti (autologin 2026-09-29'dan beri kurulu; bugünkü reboot'ta kendiliğinden oturum açtı) → `tahta_yeniden_baslat._UYARILAR` boşaltıldı; `openwebui/farabi_yonetim_araci.py` metni hâlâ eski.

## 2026-10-06 - Yoklama ekranı: ders adı + haftalık kazanım satırı; "osmanlı türkçesi" aslında Ortak Türk Tarihi
- `yoklama.py` başlığı: ders saatinde `YOKLAMA — N. DERS · <DERS ADI>` (data/ders_programi.json), ders dışı `YOKLAMA — BOŞ`; altında 13pt tek satır `Kazanım: …` (data/kazanimlar.json, sağdan "…" ile kısalır). Dosya yok/bozuksa sessizce eski davranış.
- `kazanimlar.json` = `dashboard/scripts/kazanim_yukle.py` (server/venv ile çalışır — python-docx/openpyxl/pdfplumber orada) `/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027/`'den üretir: `haftalar` (plan hafta no → pazartesi, 42 planın tarih etiketinden çoğunluk oyu; ara tatiller 16-20 Kas, 25 Oca-5 Şub, 8-12 Mar atlanır), `kazanimlar[düzey][ders][hafta]` = haftanın İLK kazanımı (≤200 kr). Tahtaya `/yapilandirma` ile yalnızca kendi düzeyi gider (fenlab hepsini). Plan değişince script yeniden çalıştırılır, restart gerekmez.
- Eksik plan (ekranda kazanım yok): 10 beden, 10/11 felsefe, 11 psikoloji, 11 mat. uyg., 11/12 bilişim, 12 fizik, rehberlik, spor etkinlikleri, sınav hazırlık ("Hedef" — hangi branş belli değil); okunamayan: 10/12 TDE (.doc). 9 beden = "temel spor eğitimi" planı (varsayım).
- **Kazanım denetimi ve kararlar (2026-10-06, kullanıcı):** kaynak planlar bağımsız betikle hafta hafta karşılaştırıldı — haftası kayan kazanım bulunmadı (kalan uyarılar: tarih etiketi bozuk satırlar, Orientation/Evaluation haftaları). Haftada birden fazla ayrı kazanım (yalnız matematik, 30 hafta) → hepsi `\n` ile tutulur, tahtada 2 satır (`MAKS_KAZANIM_SAYISI`). Bilişim (Programlamaya Giriş ve Algoritmalar, 11/12, tek PDF, çizgisiz tablo → `pdf_kelime_tablolari`): plandaki tarihler okul takviminden kayık (7 Eylül başlangıç, farklı ara tatiller) → TARİHE DEĞİL SIRAYA göre eşlenir (plan haftası N = okul haftası N). Ortak Türk Tarihi 18/31. haftalar yeni kazanım içermiyor → önceki kazanım (`DEVAM_HAFTALARI`). Öğretmenler kazanımı tahtadan deftere yazacak: plan değişince script + bağımsız denetim yeniden çalıştırılmalı.
- `SOTarih` kısaltması "osmanlı türkçesi"ne tahminle eşlenmişti (`TAHMIN_ISARETLI`); kullanıcı teyidi + dersi tarih öğretmeni veriyor + ortak türk tarihi planı → **ortak türk tarihi** (10-A Per 3-4). İki `ders_programi_yukle.py`, iki `ders_programi.json` düzeltildi; tahtaların Farabi client kopyası `config_dagit.sh` ile ayrıca dağıtılmalı.

## 2026-10-06 - tahtayoklama: tahta istemcisi (HTTP itme/çekme), SSH yedek yola indi
- Tahtalarda `tahtayoklama/tahta_istemci.py` (stdlib, `systemd --user` birimi `tahta-istemci.service`) kayıtları 15 sn içinde `POST /api/v1/tahta/kayit` ile iter, 60 sn'de bir nabız atar, 10 dk'da bir `GET /yapilandirma` ile roster/zil/ders_programi çeker (ETag). Sunucu: `dashboard/tahta_api.py`; tahta başına token, sunucuda yalnızca SHA-256 (`config/tahta_tokenlari.json`, gitignore'lu). Kurulum: `dashboard/scripts/tahta_istemci_kur.py <tahta...>|--hepsi [--kaldir]`.
- Polling: nabzı 5 dk'dan taze tahta kısmi turda SSH ile taranmaz (erişilebilir sayılır), durum hesabı yine 2 dk'da bir; saatte bir tam SSH taraması yedek. İstemci ölürse tahta kendiliğinden SSH'e döner. `yoklama.py` değişmedi (ağdan izole kalır).
- Neden: anında görünürlük, DHCP/IP bağımsızlığı (tahta kendini token'la tanıtır), sızan anahtarın kabuk vermemesi. 2026-10-06 sabahı 9-A, 9-B, 11-A, 11-B, 12-A, fenlab'a kuruldu; 10-A, 12-B, tahta-234/235/236 kapalıydı — açılınca betik yeniden çalıştırılmalı. 9-A'da otomatik giriş yok → istemci yalnızca oturum açılınca çalışır.
- **Yakalanan gerileme:** istemci ilk açılışta son 7 günü gönderdi; `onbellege_yaz` 'alindi' üstüne `>=` saatle yazdığı için isimler BUGÜNKÜ roster'la yeniden çözüldü, roster'dan çıkarılan bir öğrenci 2026-10-02 9-A satırlarında "No 204" oldu. Kural `>` (kesin daha yeni) yapıldı, 8 satır yedekten (`veri/yoklama_pano.db.2026-10-06.yedek`) geri yüklendi, test eklendi. Ders: tarihsel satırı yeniden yazan her yol isimleri bugünkü roster'la çözer — aynı kaydın tekrarı yazılmamalı.

## 2026-10-04 - smssistemi: 14:00 Öğleden sonra devamsızlık SMS otomasyonu eklendi
- **Ne yapıldı:** Sabah 09:00 ilk ders otomasyonunun (`otomasyon.py`) mimarisi ve fail-closed güvenlik kuralları korunarak, öğleden sonra gelmeyen öğrenciler için saat 14:00'te (6. ders: 13:30–14:10) çalışan ikinci bir bağımsız devamsızlık SMS servisi kuruldu.
- **Detaylar:**
  1. Mantık (`otomasyon.py`): `devamsizlar_derle` fonksiyonu genelleştirildi; `ders_no=6` ile 6. derste `durum == 'alindi'` olan sınıfları tarar. Sabah 1. dersle karşılaştırarak öğrencinin tüm gün mü yoksa yalnızca öğleden sonra mı gelmediğini (`sabah_da_yok`) tespit eder.
  2. Güvenlik & İdempotency: Sabah ve öğle servisleri birbirinden tamamen bağımsızdır (`otomasyon_ilk_ders_son_tarih` vs `otomasyon_ogle_son_tarih`). Gönderim ID öneki `oto6_`.
  3. Zamanlayıcı: FastAPI `lifespan`'ındaki `otomasyon_arkaplan_dongusu` içine 14:00–14:10 penceresi eklendi (Pzt-Cum).
  4. Arayüz (`/otomasyon`): Üstte "☀️ Sabah 09:00 Servisi (1. Ders)" ve "🌤️ Öğleden Sonra 14:00 Servisi (6. Ders)" sekmeleri; her servisin bağımsız açma/kapatma şalteri, ayrı şablonu ("Sayın {isim}, öğrenciniz {ogrenci_adi} öğleden sonra derslere gelmemiştir. Bilginize."), canlı simülasyonu ve manuel gönderim butonu.
  5. Testler: 8 yeni birim ve route testi eklendi; toplam test sayısı 122'den 130'a yükseldi, tümü başarıyla geçti.

## 2026-10-03 - Open WebUI "Farabi Yönetim" aracı → dashboard /api/ajan
- Karar: Open WebUI aracı dashboard koduna bağlanmaz; localhost-only + `X-Farabi-Ajan-Key` korumalı JSON API (`/api/ajan`) üzerinden konuşur (servis sınırı korunur, kod paylaşımı yok). Sırlar (SSH anahtarı, IP, parola) sunucuda kalır; LLM yalnızca tahta adını görür — SSH/IP bilgisi memory/wiki'ye KONMADI (kullanıcı kararı).
- Güvenlik: yalnızca admin (araç + `farabi-yonetim` modeli `access_grants` boş + araçta rol kontrolü); her değiştiren eylem onay penceresi (`__event_call__`, yalnızca `True` kabul). Reboot ayrı modülde (`tahta_yeniden_baslat.py`), okul saatinde reddedilir, tahta başına 120 sn bekleme; tahtada dar sudoers kuralı (`etapadmin` yalnızca `systemctl reboot`). Kural 2026-10-03'te 7 tahtaya kuruldu (9-A, 9-B, 10-A, 11-B, 12-A, 12-B, fenlab; `tahta_fix_uygula.py --duzeltme reboot_sudoers`), etkin yetki her birinde `sudo -n -l /usr/bin/systemctl reboot` ile doğrulandı — 12-A ve fenlab'da genel sudo hâlâ parolalı, yani orada yalnızca bu dar kural etkin. **Bekleyen:** 11-A (o an kapalıydı) ve tahta-234/235/236 — açılınca aynı komut tekrar çalıştırılmalı.
- Tuzaklar: Open WebUI async tool içinde senkron HTTP tüm kullanıcıları dondurur → `httpx.AsyncClient`. `meta.hidden` modeli ADMIN seçicisinden de gizler → kullanılmaz. Onay mesajı Markdown olarak işlenir → URL kod aralığında + sıkı doğrulama (ASCII dışı, boşluk/kontrol, `[]()<>\``); IDN punycode ile yazılmalı. POST'ta ağ hatası/zaman aşımı "ulaşılamadı" DEĞİL "sonuç alınamadı, işlem yapılmış olabilir" (tekrar denemeden önce `tahta_durumu`).

## 2026-10-03 - Open WebUI kayıt açıktı, varsayılan rol admin'di
- Tespit: son genel incelemede — kayıt açık + varsayılan rol "admin" olduğundan LAN'daki herkes kendine admin hesabı açabilirdi (yönetim aracı gelmeden de ciddi açık). O an 1 admin + 4 user vardı (ek admin yok).
- Çözüm: canlıda elle kapatıldı (`ENABLE_SIGNUP=false`, `DEFAULT_USER_ROLE=user` — kullanıcı kararı, "pending" değil). `openwebui/kur.py::kimlik_ayarlarini_kur` her çalışışında `GET/POST /api/v1/auths/admin/config` ile bu iki alanı zorlar (tam gövde geri gönderilir, diğer alanlar korunur; hesaplardan önce çalışır).

## 2026-10-03 - Open WebUI'ye Farabi teması (custom.css, `webui-tema/`)
- Ne yapıldı: `webui-tema/static/custom.css` (lacivert/çini `#4f5eff` + altın, 8 köşeli yıldız deseni, lacivert tonlu gri skala; dış font yok) → `kur.sh` ile `open_webui/frontend/static/` ve `open_webui/static/`'e kopyalanır, restart gerekmez. `open-webui.service.d/farabi-tema.conf` `ExecStartPre=-+install ...` ile her açılışta repo kopyasını geri yükler (pip upgrade'e karşı). Aynı gün favicon/splash ikonları da Farabi logosuyla değiştirildi (`ikon_uret.py`, `farabilogo.jpg`'deki sahte dama zemin yüzünden yalnızca yuvarlak amblem kesilip dışı şeffaf yapıldı); dosyalar `webui-tema/static/`'te, drop-in tüm klasörü kopyalar. Lisans: Open WebUI marka koruma maddesi ≤50 kullanıcı/30 gün kurulumlarını muaf tutuyor (şu an 2 kullanıcı) — 50'yi aşarsa ikonlar geri alınmalı. `WEBUI_NAME` değiştirilmedi.
- Neden / tuzak: Open WebUI (`config.py`, "Static DIR") her açılışta `STATIC_DIR`'deki dosyaları SİLİP `frontend/static/`'ten yeniden kopyalıyor — `static/custom.css`'e tek başına yazmak ilk restart'ta kaybolur. Tailwind v4 renkleri `@layer` içinde CSS değişkeni: katmansız custom.css `--color-gray-*`'ı ezince tüm arayüz yeniden boyanır; ama `!bg-*` gibi `!important` yardımcıları katmansız normal kural yenemez → zemin tonları `background-image` ile bindirildi. Kararlı kancalar yalnızca id'ler (`#sidebar`, `#auth-page`, `#chat-input-container`, `#send-message-button`, `.chat-user .rounded-3xl`).
- Model görünen adı: `qwen3.8:27b` → "Farabi" (webui.db `model` tablosuna override satırı, `base_model_id=NULL`, `params={}`, sahibi admin; yedek `webui.db.yedek-2026-10-03-model-adi`). Tuzak: Open WebUI 0.11'de DB kaydı olmayan model YALNIZCA adminlere görünür; kayıt + `access_grant` yoksa `user` rolü yine göremez. Herkese açmak = `access_grant`'e (`model`, `qwen3.8:27b`, `user`, `*`, `read`) ya da Admin › Modeller › Erişim: Public.

## 2026-10-03 - Ollama: qwen2.5:14b → farabi-qwen3.8:27b (iki GPU, tamamı GPU'da, süresiz); RAG GPU'dan kaldırıldı
- Karar (kullanıcı, "Ollama daha önemli"): yerel model Qwen3.8 27B (Q4_K_M). Sistem promptu kullanıcının verdiği Farabi promptu, `server/ollama/farabi-qwen3.8-27b.Modelfile`'da `SYSTEM` olarak gömülü (yalnızca istek kendi sistem mesajını taşımıyorsa uygulanır: rag.py ve smssistemi kendi görev promptlarını gönderir; saglayicilar.py artık Ollama'ya `_OLLAMA_VARSAYILAN_SISTEM` eklemiyor, sabit silindi). Model yalnızca metin: `qwen3.8:27b`'nin görsel projektörü alınmadı (RENDERER qwen3.8 / PARSER qwen3.5 / params Modelfile'a kopyalandı) — projektör + llama.cpp'nin ~1,1 GB en kötü durum payı modeli GPU'dan taşırıyordu.
- **RAG kapalı:** `server/main.py::RAG_AKTIF = False` — embedding/reranker hiç yüklenmez, GPU'ya dokunulmaz; DB + kod diskte. `/api/egitim/question` `status="hata"` döner → tahtadaki `kitap_sorusu` sessizce `_SINIRLI_DEVAM`'a düşer (ders bozulmaz). `yetersiz_kaynak` bilerek seçilmedi (tahta "kitapta bulunmuyor" derdi — yanlış). Geri açmak: `True` + restart; ama o zaman model yine sığmaz (aşağıdaki ölçüm) ve `kitap_sorusu`'nun 10 sn POST zaman aşımı yeni modelle (~12-20 sn) aşılır.
- Neden RAG: 24 GB'ın ~5,7-6,9 GB'ını (fp32, yük altında büyüyen PyTorch önbelleği) farabi-api tutuyordu; model tamamen GPU'da ~17,3 GB + MTP taslak bağlamı istiyor, sıfır güvenlik payıyla bile ~170 MiB eksikti. 17/66 (projektörlü), sonra 9/66 katman CPU'da → RAG 17-23 sn, 8,6 tok/s. RAG kapanınca: 66/66 GPU, varsayılan payla (1024 MiB/kart) sığıyor, ~27-31 tok/s, kartlarda ~3 GB boş.
- fp16 ölçümü (RAG geri açılırsa diye kodda kaldı, `.half()`): 40 soru canlı API, katı ölçüt (kaynak sayfası doğru / grup C'de yetersiz_kaynak) fp32 34/40 → fp16 32/40; düşen 2 sorunun rerank skoru ~0,99 (LLM'in kendisi YETERSIZ_KAYNAK dedi — LLM gürültüsü). 40 sorunun rerank skor farkı ort. 0,0001 / maks. 0,001, eşik (0,5) tarafı değişen 0; rerank medyan 1354 → 414 ms; farabi-api GPU 6926 → 4290 MiB (yük altında büyümedi).
- Ollama 0.32.6 → 0.35.1 (model en az 0.32.12 istiyordu, 412). Tarball'dan kuruldu (resmî install.sh ana birim dosyasını ezerdi); yedek alınmıştı, 2026-10-03'te kullanıcı isteğiyle silindi — geri dönüş yok. `override.conf`'a `CUDA_VISIBLE_DEVICES=0,1` eklendi (ana birimdeki `=1`'i ezer); `CUDA_DEVICE_ORDER=PCI_BUS_ID` korunuyor. Açılışta ön yükleme: `ollama.service.d/farabi-onyukleme.conf` → `/usr/local/bin/farabi-ollama-onyukle.sh` (keep_alive=-1). Satır içi `ExecStartPost` systemd'nin tırnak/`$` işlemesi yüzünden 400 veriyordu — betik dosyası şart.
- Tuzak — model indirme: Müdür PC proxy'si (WifiHttpProxy) Ollama'nın 16 paralel parça bağlantısını EOF ile kesiyor, `ollama pull` ilerlemiyor (küçük blob'lar bile). Çözüm: blob'ları `registry.ollama.ai/v2/library/<ad>/blobs/sha256:<digest>` adresinden tek akışla `curl -C - --speed-limit` döngüsüyle indir, `sha256sum` doğrula, `blobs/sha256-<digest>` olarak koy (sahip `ollama`), manifesti `manifests/registry.ollama.ai/library/<ad>/<etiket>`'e yaz.
- Geçiş: `qwen2.5:14b` adı yeni modele takma ad (`ollama cp`, aynı runner — yeniden yükleme yok); eski qwen2.5:14b ağırlıkları 2026-10-03'te kullanıcı isteğiyle silindi. Dış istemci ebys (istemci IP'si journal'da boş görünen `/api/generate` çağrıları) qwen2.5:14b istiyordu ve her çağrı Farabi modelini bellekten atıyordu; ebys ajanına güncelleme promptu verildi (model adı, `think:false`, `keep_alive` göndermeme, ≥60 sn zaman aşımı). Başka bir model adı istenirse (ör. projektörlü `qwen3.8:27b`) Farabi modeli yine bellekten atılır.
- Düşünme kapalı: rag.py/smssistemi `"think": false`, saglayicilar.py `reasoning_effort="none"` (Ollama bunu think=false'a çevirir). qwen3.x varsayılan düşünür; açık kalırsa kısa cevap bile ~14 sn.

## 2026-10-02 - CLAUDE.md düzeni: her alt projeye kendi dosyası, PDF okuma kuralı, kodla doğrulama
- Her alt projenin kendi CLAUDE.md'si oldu: yeni `server/`, `benchmark/`, `mudur/`, `dogum/` (mevcut: `client/`, `tahtayoklama/`, `smssistemi/`, `tahtaayar/`). Kökteki server uç nokta listesi ve proje komutları alt dosyalara taşındı; kökte yalnızca alt dizine girmeden önce ısıran tuzaklar kaldı (dashboard unittest, `farabi.local`'da client venv yok). `mudur/*` gitignore'lu olduğu için `.gitignore`'a `!mudur/CLAUDE.md` eklendi.
- Yeni kural (kullanıcı kararı): ders kitabı/YKS/halka açık PDF'ler Claude tarafından okunabilir ve özetlenebilir (hedefli sayfa aralığı, özetler veri diskine). Kişisel veri içeren PDF/Excel (`mudur/SINIF/` vb.) hâlâ okunmaz.
- Kodla doğrulamada bulunan doküman hataları düzeltildi: uzaktan yönetim hedefleri dashboard SQLite'tan değil `server/tahtalar.json`'dan (`tahta_kaydi.py`) okunuyor; `zil.json`'un kaynağı `tahtayoklama/data/zil.json` (`config_dagit.sh` dağıtıyor, "bağımsız kopya" değil); `benchmark/`'ta `requirements.txt` yok; SSO köprüsünde `/otomasyon-git` eksikti; tahtaayar'da root fix sayısı 3 değil 4.
- Ruff tarihli sayımları CLAUDE.md'den çıkarıldı (her oturum elle güncelleniyordu), kural "F821/F811/F632 sıfır + toplam artmasın" oldu. Sayımlar: 2026-09-22 480, 2026-09-29 504, 2026-10-01/02 518 (smssistemi 40).
- Neden: kök dosya 552 satırdı ve her oturumda yükleniyordu; alt dosyalar yalnızca o dizinde çalışırken yükleniyor. Yanlış bilgi içeren doküman, olmayan dokümandan daha tehlikeli (Kural 4).

## 2026-10-01 - Dashboard: /admin/uzaktan* için denetim kaydı (uzaktan_denetim) + oturumsuz tarayıcı isteği /giris'e
- Ne yapıldı: her uzaktan eylem (yoklama aç/kapat, web aç, chrome kapat, ekran karart/kaldır, duvar kağıdı) `yoklama_pano.db`'deki yeni `uzaktan_denetim` tablosuna yazılıyor: zaman (İstanbul, değerin içinde +03:00), istemci IP (`request.client.host`, X-Forwarded-For okunmaz), eylem adı, tahtalar, tahta başına ok/hata. `uzaktan_yonetim._dogrula` oturumsuz tarayıcı isteğinde (`Accept: text/html`) 303 → `/giris`, API/JSON'da 401 kalır. Ölü `auth.gecerli_oturum` silindi. Test: `test_uzaktan_denetim.py` (7; paket 33/33).
- Neden: ortak şifreyle giren herkes fiziksel tahtaları etkileyebiliyor (2026-09-15 bilinçli risk kabulü), kim/ne zaman/hangi tahta izi yoktu. Kullanıcı sütunu yok (şifre ortak); URL, dosya adı/içeriği bilinçli olarak yazılmaz. Log yazımı `try/except` içinde — kayıt hatası eylemi asla engellemez. Zaman diğer tablolardaki gibi UTC `datetime('now')` değil, ofsetli İstanbul: tek başına okunduğunda belirsiz olmasın diye. Tablo `semayi_kur()` ile açılışta oluşur — restart'a kadar kayıtlar sessizce yazılmaz. Testler `db.DB_YOLU`'nu geçici dosyaya yönlendirir (üretim DB'sine yazmaz).

## 2026-09-29 - Kitap metni buluta gidebilir; sunucunun bulut zincirleri anahtarsızdı; ders planı için Ollama vs bulut ölçümü
- Karar (kullanıcı): MEB kitap metinleri halka açık, kitap içeriğiyle çalışan görevler (ders planı, sayfa görseli ayrıştırma, özet) bulut sağlayıcılara gidebilir. RAG soru-cevabının LLM adımı ŞİMDİLİK yerel kalır (kullanıcı seçimi: "yalnızca yeni hatlar"); öğrenci/veli verisi buluta gitmez. CLAUDE.md "Gizlilik" güncellendi.
- Bulgu (kök neden): `saglayicilar.py` anahtarları yalnızca `server/config/api_keys.json`'dan okuyor; dosyada (2026-09-12 ve 09-26 yedekleri dahil) yalnızca `board_keys` vardı, anahtarlar kökteki `apikeys.env`'de duruyordu. Sonuç: tüm bulut zincirleri sessizce "anahtar yok, atlanıyor" diyor, metin görevleri Ollama'ya düşüyor, Ollama yedeği olmayan `gorsel` zinciri (`ekrandaki_soruyu_oku`, dosya görseli) hata verecekti (1 Eylül'den beri çağrılmamış, bu yüzden görülmedi). INFO seviyesindeki "anahtar yok" satırı journal'a düşmüyor. Düzeltme: 7 anahtar (deepseek, groq, mistral, cohere, nvidia, cerebras, sambanova) `apikeys.env`'den `api_keys.json`'a kopyalandı (yedek `api_keys.json.yedek-2026-09-29`, izin 600, servis `ata` olarak koşuyor). Restart gerekmedi (dosya her istekte okunuyor). Canlı kodla doğrulandı: `soru_taslak`, `kitap_ozet`, `gorsel` gerçek bulut cevabı veriyor, `/health` 200. openrouter anahtarı hiçbir yerde yok (evrensel yedek hâlâ ölü).
- Ölçüm (Fizik 10, "1.1 Sabit Hızlı Hareket", PDF s. 14–22, ~15,6k karakter, aynı sistem+kullanıcı istemi, sıcaklık 0,3): qwen2.5:14b 32,5 sn / 760 çıktı token'ı, 8k context'e sıkışmış, fizik hataları (sürat "vektörel", x-t eksenleri ters, uydurma tablo) → YETERSİZ. deepseek-v4-flash 25,9 sn / 5873 token, sayfa atıflı, kitap örneğinin sayıları metinle doğrulandı, bozuk ϑ sembolünü kendisi işaretledi → EN İYİ. groq gpt-oss-120b 6,2 sn, iyi ama konu dışı giriş sorusu. cohere command-a yüzeysel. mistral-medium ücretsiz katmanda 429.
- Görsel ölçüm (sayfa PNG → model): pixtral-12b formülleri doğru okuyor (metin katmanının bozduğu ϑ dahil) ama grafik değerlerinde güvenilmez (s. 23'teki doğrusal x-t grafiğine "parabolik" + yanlış noktalar; yatay ϑ-t'ye "negatif eğim"). nvidia llama-3.2-11b-vision işaret/eksenleri ters okuyor, 120 sn timeout → kullanılamaz. Sonuç: ücretsiz görsel modeller formül çıkarmak için evet, grafik değeri okumak için hayır; grafikler derste Gemini Live'da (sayfa görüntüsünü zaten görüyor).
- Tuzak: MEB fizik PDF'lerinin metin katmanında hız sembolü ϑ "c" olarak çıkıyor ("c-t grafiği"), bazı formüller `𝑂𝑂𝑂𝑂…` gibi tekrarlanan matematik fontu harfleri. Metinden formül okuyan her yol bunu devralır.

## 2026-09-29 - smssistemi: otomasyon logları journal'a düşmüyordu — `smssistemi.*` için log yapılandırması
- `app.py::log_ayarla()` (modül yüklenirken çağrılır): yalnızca `smssistemi` logger ağacı INFO düzeyinde, tek `StreamHandler(sys.stderr)` (→ journal), biçim `LEVEL: [ad] mesaj` (zaman damgasını journal ekliyor), `propagate=False`, idempotent. Kök logger'a dokunulmadı. Test: `test_log_ayari.py` (3 test; paket 122/122). Canlıda doğrulandı: restart sonrası journal'da `INFO: [smssistemi.otomasyon] Otomasyon arka plan zamanlayıcı döngüsü başlatıldı.` Commit 4b39d2d.
- Neden: smssistemi'de hiç log yapılandırması yoktu; uvicorn yalnızca kendi logger'larını kuruyor, kökte handler olmadığı için `smssistemi.otomasyon`'un INFO satırları ("döngü başlatıldı", "tetikleniyor") sessizce kayboluyordu (WARNING+ yalnızca Python'un lastResort'u ile görünüyordu). Sonuç: zamanlayıcının 09:00'da gerçekten kendiliğinden çalıştığına dair HİÇ kanıt yoktu — journal + `gonderimler` tablosu incelendiğinde 2026-09-28'deki iki gönderimin ikisi de ELLE (`POST /otomasyon/calistir`, 10:00 ve 10:06 TR), 2026-09-25'teki de 08:57 TR (pencere dışı, muhtemelen elle). Döngü `lifespan`'da başlıyor ve hata logu yok; 09-28 sabahı otomasyon muhtemelen kapalıydı (10:00:46'da `durum-degistir`). Kanıt artık `otomasyon_ilk_ders_son_sonuc.tetikleyen == "otomatik_zamanlayici"` + journal'daki "tetikleniyor" satırı. Kök logger yerine yalnızca `smssistemi` ağacı: başka kütüphanelerin INFO gürültüsü girmesin, uvicorn satırları iki kez basılmasın.
- Tuzak (tekrar edebilir): worktree'de smssistemi testlerinden 4'ü (`test_otomasyon*.py`) gitignore'lu `config/modem.json` olmadığı için düşüyor — testler gerçek config'e bağımlı. Ana kopyada ya da `config/`'e geçici symlink ile koşulmalı.

## 2026-09-29 - 9-A: fare/klavye/dokunmatik kilitlenmesi (hatalı x11vnc birimi) kaldırıldı, "otomatik giriş yok" aslında kilit ekranıydı, sudo diğer tahtalarla eşitlendi
- Belirti: 9-A'da fare/klavye/dokunmatik takılıyor, uzaktan reboot geçici düzeltiyor; oturum "otomatik açılmıyor".
- Kök neden (girdi): yalnızca 9-A'da elle eklenmiş `/etc/systemd/system/x11vnc.service` vardı (`Type=forking` + `x11vnc ... -bg -loop -forever`). `-loop` önde bir gözetleyici bıraktığı için systemd birimi hiç "başladı" saymıyor, 90 sn'de `start operation timed out` → öldür → 5 sn sonra yeniden başlat; o boot'ta **307 kez** yeniden başlamıştı. Her başlangıçta x11vnc `:0`'a yeniden bağlanıp klavye eşlemesine dokunuyordu ("Switching to -xkb mode"). Reboot sayacı sıfırladığı için geçici düzeltiyordu. Düzeltme: birim durduruldu, devre dışı bırakıldı ve dosya `/root/x11vnc.service.kaldirildi-20260929`'a taşındı (diğer 7 tahtada böyle bir birim yok). Veyon'un kendi x11vnc'si (port 11200) ayrı, dokunulmadı. Atakan fiziksel tahtada doğruladı: takılma yok.
- Kök neden (oturum): autologin dosyası (`50-tahta-autologin.conf`) zaten diğer tahtalarla birebir aynıydı ve çalışıyordu (`lightdm.log`: `Started with service 'lightdm-autologin'`). Açılıştan ~18 dk sonra LightDM'e `Seat seat0: Locking` geldi (`custom-screensaver-command = 'dm-tool lock'`), greeter VT8'de öne geçti, `ogretmen` oturumu VT7'de arkada kaldı; öğretmenin gördüğü parola ekranı buydu. `loginctl activate 1` ile oturum öne alındı. **Kilidi neyin tetiklediği bulunamadı** — tekrarlarsa o anki `/var/log/lightdm/lightdm.log` ve journal'a bakılmalı (`sudo` gerekir; `ogretmen` sistem journal'ını okuyamaz).
- Sudo: 9-A ters kuruluydu — `/etc/sudoers.d/farabi-nopasswd` `ogretmen ALL=(ALL) NOPASSWD: ALL` diyordu ve `ogretmen` `sudo` grubundaydı; diğer tahtalarda aynı dosya `etapadmin ALL=(ALL) NOPASSWD: ALL`, `ogretmen` sudo'suz. Kullanıcı kararıyla eşitlendi: dosya `etapadmin` satırıyla değiştirildi (`visudo -cf` ile doğrulandıktan sonra; eskisi `/root/farabi-nopasswd.9A-ogretmen-20260929`), `gpasswd -d ogretmen sudo`. Sonuç: 9-A'da `etapadmin` artık parolasız sudo, `ogretmen` sudo'suz. Client/yoklama kodunda `ogretmen` sudo'suna dayanan bir şey yok (tek `sudo` çağrısı macOS'a özel `powermetrics`).
- Neden: `tahtaayar/CLAUDE.md`'deki "9-A'ya bilinçli olarak dokunulmadı / NOPASSWD asimetrisi normalleştirilmedi" notları artık geçersiz — 9-A diğer sınıf tahtalarıyla aynı referans durumda. Tespit yöntemi: `tahta_fix_uygula.py --sadece-kontrol` 9-A'da her şeyi "uygulanmış" gösteriyordu; fark ancak tahtalar arası ham karşılaştırmayla (birim listesi, sudoers, `lightdm.log`, `loginctl`) çıktı.

## 2026-09-29 - fenlab: son duvar kağıdı gitmemişti, Cinnamon güç tuşu hâlâ 'shutdown'du
- Duvar kağıdı: 2026-09-28 ~17:47'de panelden gönderilen görsel (`duvar_1790606866.jpg`) 9-A/12-B'ye ulaşmış, fenlab'a hiç yazılmamıştı (fenlab 09-28 07:12'deki görselde kalmıştı). Dashboard journal'ında o gönderime ait satır yok — neden ulaşmadığı belirlenemedi. Aynı dosya (md5 eşleşti) fenlab'a kopyalanıp panelle aynı `gsettings` komutlarıyla ayarlandı; Atakan fiziksel tahtada doğruladı.
- Güç tuşu: `tahta_fix_uygula.py --sadece-kontrol` fenlab'da `cinnamon_guc_tusu_yoksay` eksik gösterdi (`button-power 'shutdown'`); `--tahta fenlab --duzeltme cinnamon_guc_tusu_yoksay` ile uygulandı ve doğrulandı.
- Bilinen, dokunulmayan farklar: fenlab'da `veyon-watchdog.timer` yok (diğer 8 tahtada var); `sleep-display-battery` 0 (diğerlerinde 600, tahta prizde olduğu için etkisiz).
- Aynı gün sürüm taraması: açık 8 tahtanın hepsi `3bc5a68`'de, yerel değişiklik yok; `yoklama.py` md5'i her yerde repo ile aynı. tahta-234/235/236 ağda değil.

## 2026-09-29 - Giriş kiosku (yüz tanıma, bu repoya bağlı değil): kamera/ekran penceresi 07:30 → 07:00
- Kiosk 07:00'de açılmıyordu; hata değil ayardı: `~/yuz/ata.py::CAMERA_START_TIME = dtime(7, 30)`. Kullanıcı isteğiyle 07:00–17:00 yapıldı (`dtime(7, 0)`; yorum satırı ve kiosk'un kendi `CLAUDE.md`'si de güncellendi, yedek `ata.py.bak_<tarih>`), uygulama yeniden başlatıldı, kamera açıldı. Kiosk reposundaki önceden commit edilmemiş değişikliklere dokunulmadı, commit yapılmadı.
- Tuzak: uygulamayı SSH ile yeniden başlatırken `pkill -f "python3 ata.py"` kendi SSH komut satırını da eşleştirip oturumu öldürdü (uygulama kapandı, yeniden başlatma adımı çalışmadı). Başlatma komutunu ayrı bir script olarak göndermek gerekti — `pkill -f` desenini aynı komut satırına yazma.

## 2026-09-28 - smssistemi: proxy kapalıyken SMS'ler kayboluyordu + saat 3 saat geri görünüyordu
- `sms_gonderici.toplu_gonder`: bağlantı kurulamazsa (ya da gönderim ortasında koparsa) kalan HER alıcı kendi isim/telefon/mesajıyla `hata` kaydediliyor (eskiden telefonu boş tek satır → `gonderim_basarisizlari` `telefon != ''` ile hepsini eliyor, "Tekrar gönder" boş kalıyordu). İlerleme telefona göre değil indekse göre (kardeşler aynı telefonu paylaşır); DURDUR'la durdurulanlar kayıtsız kalır. `otomasyon.otomasyon_calistir`: hiç `send_sms` DENENMEDİYSE (tüm satırlar "BAĞLANTI HATASI" önekli) `otomasyon_ilk_ders_son_tarih` yazılmaz → 09:00–09:10 döngüsü 30 sn'de bir yeniden dener; manuel tetikte `?mesaj=basarisiz` uyarısı. Zaman damgası: DB'de UTC kalır (`datetime('now')`), yalnızca görüntülemede `db.utc_str_to_istanbul_str` ile İstanbul'a çevrilir (`gonderim_satirlari`, `gonderim_ozetleri`).
- Neden: 2026-09-28 10:00'da Müdür PC WifiHttpProxy kapalıydı; `oto1_af514d65` tek boş satır bıraktı, 8 veli kaydedilmedi, son tarih yazıldığı için otomasyon tekrar denemedi (10:06'da elle gönderildi). Sunucu TZ'si `Etc/UTC`, `zaman` UTC saklanıp ham gösteriliyordu. Yeniden deneme koşulu bilinçli olarak "hiç başarılı yok" DEĞİL "hiç denenmedi": `send_sms` zaman aşımında modem SMS'i göndermiş olabilir, "başarılı yok"a göre tekrar denemek veliye 30 sn'de bir mükerrer SMS demekti. Saat için DB'yi yerel saate çevirmek eski kayıtlarla karışık format yaratırdı ve UTC-UTC karşılaştırmaları (oturumlar) bozardı.

## 2026-09-28 - Dashboard yük azaltma: rapor detayı sayfalı, gzip, gizli sekmede polling yok
- `/admin/rapor` detay tablosu 100 satırlık sayfalara bölündü (Python'da dilimleme; özet ve CSV tüm aralığı kullanıyor, `_rapor_verisi` değişmedi). `app.py`'ye starlette `GZipMiddleware` (minimum_size=1000, compresslevel=6). `pano.html`, `sistem_durumu.html`, `kenar.js` sekme gizliyken istek atmıyor.
- Neden: yoklama_onbellek yılda ~10 bin satır; 1 yıllık aralık 2,2 MB HTML üretiyordu (render 87 ms, SQL/özet ihmal edilebilir). Darboğaz tarayıcıya giden HTML, sunucu değil; bu yüzden SQL LIMIT/önbellek/özet tablosu gerekmedi (Kural 10). Dashboard venv'inde httpx yok → TestClient kullanılamaz, gzip deploy sonrası curl ile doğrulandı. Plan: `docs/superpowers/plans/2026-09-28-dashboard-yuk-azaltma.md`.

## 2026-09-28 - Yoklama panoda "herkes var" görünüyordu: ders sonu otomatik kaydı kaldırıldı, tek pencere, teneffüste kapalı, izinli görünür
- Belirti: tahtada "yok" işaretlenen öğrenci panoda var, sınıf "Tam" görünüyordu (ara derslerde); izinli öğrenci hiç görünmüyordu.
- Kök neden 1: `yoklama.py::_periyodik_kontrol` her ders bitiminde `_kaydet(sessiz=True)` ile ekrandaki hâli öğretmenin kaydının ÜZERİNE yazıyordu; dashboard aynı (sınıf, ders) için en son `kaydedilme_saati`'ni alır. Gerçek kodla (saat sahte, offscreen) iki yol üretildi: (a) masaüstü simgesine çift dokunuşla açılan ikinci, dokunulmamış pencere ders sonunda "herkes var" yazıyor; (b) teneffüste yapılan işaretlemeler ders başında sıfırlanıyor, ders sonunda "herkes var" kaydediliyor. Dashboard verisinde kayıtların çoğunun saati tam ders bitişi (+~30 sn) — otomatik kayıt. Elenenler: 8 tahtada saat, `zil.json`, `yoklama.py`, roster md5'leri dashboard ile aynı; dashboard yoklamayı kendiliğinden açmıyor.
- Kök neden 2: `dashboard/templates/pano.html::hucreDoldur` yalnızca `yok_isimleri`'ne bakıyordu; `izinli_isimleri` API'de vardı ama okunmuyordu → yalnızca izinlisi olan ders "Tam".
- Düzeltme (kullanıcı kararı): otomatik kayıt TAMAMEN kaldırıldı (kayıt yalnızca "YOKLAMAYI KAYDET"; unutulursa pano dürüstçe "alınmadı" gösterir, 10 dk öne-getirme kuralı duruyor); tek örnek koruması (`QLocalServer`/`QLocalSocket`, PyQt6.QtNetwork — ikinci başlatma ilkini öne getirip çıkar, çökmüş örneğin soket kalıntısı temizlenir); teneffüste/ders dışında kartlar ve KAYDET devre dışı; panoda izinliler ayrı `.pill-izinli` rozeti, "Tam" yalnızca iki liste de boşsa. Testler: `tahtayoklama/test_yoklama.py` (11), dashboard `test_api_durum.py`.
- Dağıtım: `yoklama.py` 8 tahtaya SSH ile kopyalandı (yedek `~/tahtayoklama/yoklama.py.bak-2026-09-28`), fenlab'da canlı denendi (ikinci başlatma 165 ms'de çıktı, eski soketten sonra açılış OK). Tahtada Python 3.11.2 / PyQt6 6.11.0.
- Not: tahtada `pkill -f yoklama.py` gibi geniş desenler SSH oturumunun kendi `bash -c` sürecini de eşler ve bağlantıyı koparır — PID ile öldür ya da `[t]ahtayoklama/yoklama.py` desenini kullan.

## 2026-09-28 - Yerel sese geçiş (Pipecat) KALICI OLARAK İPTAL — Gemini Live ile devam
- Ne yapıldı: 2026-09-25'te açılan yerel ses projesi (dal `yerel-ses-pipecat`: Faz 1a `server/ses_cephe.py` `/v1/*`, Faz 1b `voice_node/` Pipecat + faster-whisper + Piper) kullanıcı kararıyla kalıcı olarak iptal edildi. `farabi-ses` ve `farabi-piper` birimleri durduruldu ve devre dışı bırakıldı (`systemctl disable --now`). Kod 66af43d ile `git revert` edildi (bd9719c, e04e279; `/v1/*` route'u `server/main.py`'dan çıktı), git geçmişinde arşiv; yerel `master` bu hâle ileri alındı ve `farabi-api` yeniden başlatıldı. `7fd3d19` (docs) geri alınmadı, CLAUDE.md elle güncellendi. Faz 1c (9-A pilotu) yapılmayacak. CLAUDE.md'ye 2026-08-11'deki "yerel STT/TTS kalıcı iptal" maddesi yeniden eklendi; iki plan dosyası iptal notuyla arşiv olarak kaldı. Git dışı artıklar da silindi (2026-09-28): `/etc/systemd/system/farabi-{ses,piper}.service`, `voice_node/` (venv, `ses_node.env`), `server/config/ses.env`, modeller `/mnt/farabi-data/farabi/ses/` (~1,6 GB); dal `yerel-ses-pipecat` silindi. Yeniden gerekirse kod bd9719c/e04e279'da, modeller yeniden indirilmeli.
- Neden: donanım altyapısı izin vermiyor. Faz 1b ölçümleri bunu gösteriyordu: eşzamanlı RAG altında ses cevabı 15-30 sn (Ollama tek slot, 2× RTX 3060), qwen2.5:14b Gemini'nin prompt+araç setini 8192 bağlamda taşıyamıyor; tahta mikrofonları da büyük ölçüde bozuk. Gemini faturalandırma engeli 2026-09-25'te yeni anahtarla çözüldüğü için projenin asıl tetikleyicisi de ortadan kalktı. Ses Gemini Live'da (client'ta) kalır.

## 2026-09-27 - Ekranı oku: kare Gemini'ye görüntü olarak (realtime video değil)
- Ne yapıldı: `ekrandaki_soruyu_oku` artık ekranı yakalayıp görüntüyü açık Live oturumuna `send_client_content` ile ayrı bir kullanıcı turu olarak gönderiyor (`[EKRAN]` etiketi, ≤1024 px JPEG). Farabi önündeyse yakalarken kendini ~0,4 sn küçültüyor. Öndeki pencere başlığında yoklama, e-Okul veya MEBBİS geçiyorsa kare alınmıyor. Yazılı "ekranı oku" komutu modele bırakılmadan doğrudan çalışıyor. Gönderim başarısızsa eski OCR (Pixtral) yolu yedek.
- Neden: fenlab'da yapay "3. SORU 2x + 3 = 11" görseliyle ölçüldü: `send_client_content` ile model soruyu birebir okudu; `send_realtime_input(video=Blob)` ile rakamı yanlış okudu ("2x + 5 = 11"). Otomatik/periyodik kare kullanıcı kararıyla yapılmadı; yalnızca istenince.

## 2026-09-27 - Ders içi düğmelere DERSİ BİTİR eklendi, mikrofon modu dokunmatik
- Öğretmen panelinde ders içi düğmeler artık DURDUR, DEVAM ET ve ⏹ DERSİ BİTİR (çift dokunuş, yalnızca oturum açıkken). "Yalnızca iki düğme" kararı kullanıcı onayıyla değişti. Ayrıca 🎤 MİKROFONLU / 🚫 MİKROFONSUZ düğmesi `api_keys.json::mikrofon` değerini yalnızca bellekte değiştirir, dosyaya yazmaz. Bu düğme DERSİ BAŞLAT'ta kilitlenir.
- Neden: mod ve mikrofon seçimi DERSİ BAŞLAT'ta kilitleniyor. Ders sırasında bunları değiştirmenin tek yolu 40 dakikalık zili beklemek ya da tahtayı yeniden başlatmaktı. Tuzaklar: (1) `_dersi_bitir` yeniden girişe kapalı (`_ders_bitiriliyor`). Aksi hâlde yedeklemenin sürdüğü 6 sn içinde gelen ikinci çağrı (çift tık, zil ya da boşta kalma) bayrağı sıfırlandıktan sonra yeniden True yapıyor, bir sonraki ders açılır açılmaz kapanıyordu. (2) Bağlantı koparken basılan BİTİR, yeni bağlantı açılmadan işlenir. (3) Mikrofonlu derste `baslangic_cercevesi` sıfırlanır; önceki mikrofonsuz dersin yazılı konusu yeni derse taşınmaz.

## 2026-09-27 - Live modeli thinking_config yüzünden susuyordu (ders "dinliyor"da takılıyordu)
- Belirti: DERSİ BAŞLAT → "Farabi çevrimiçi", açılış gönderildi, sonra Farabi hiç konuşmuyor; mikrofonsuz modda `[DEVAM]` 10 sn'de bir gidiyor (boş tur bekleme süresi). 9-B ve fenlab'da 3+ dk sessizlik; ders kitabı içeriğinin bulunup bulunmaması fark etmiyordu.
- Kök neden: `LiveConnectConfig(thinking_config=ThinkingConfig(include_thoughts=False))`. fenlab'da gerçek `_build_config()` + `_send_session_opening()` ile ölçüldü: bu ayarla her tur `ses=0 bayt`, transkript yalnızca `'\n\n'` (10/10 tur). `thinking_config` kaldırılınca ilk turda 1,4-1,8 MB ses ve doğru açılış (2/2 deneme). `thinking_budget=0` da sessiz + İngilizce "Let me check" sızdırdı. Araçsız ve açılışa `role: user` eklenmiş varyantlar da sessizdi, yani neden onlar değil.
- Düzeltme: iki config'ten (`_build_config`, `_build_talimat_config`) `thinking_config` kaldırıldı; test artık `thinking_config is None` bekliyor. Düşünce sızıntısına karşı savunma `_konusma_temizle()` (`_THOUGHT_RE`).
- Neden önemli: ayar 2026-08-11'den beri vardı ve çalışıyordu, yani davranış Google tarafında (model `gemini-2.5-flash-native-audio-preview-12-2025`) değişti. Model sessizse önce `thinking_config`/config alanlarını tek tek çıkararak ölç; prompt metnini değiştirmeye koşma.

## 2026-09-25 - Gemini Live'dan yerel sese (Pipecat) geçiş başladı
- 2026-08-11'deki "yerel STT/TTS kalıcı iptal" kararı kaldırıldı. Dal `yerel-ses-pipecat`. Kararlar: karma kapsam (kısa server persona + 5 araç: `kitap_sorusu`, `ders_icerigi` sunucuda; `pdf_sayfa`, `yks_sorulari`, `pencere_kapat` tahtada), `kitap_sorusu`'nda dolgu cümlesi + RAG'ın tam/doğrulanmış cevabı aynen (stream'de sayı kontrolü atlanmasın diye), pilot 9-A (11-A'nın mikrofonu hiç çalışmamış, PipeWire kaynağı `auto_null`), tahta istemcisi mevcut PyQt client (Chrome düz http LAN'da getUserMedia'yı engelliyor), STT GPU0'da faster-whisper large-v3-turbo.
- Faz 1b kararları (2026-09-26): taşıma WebSocket + ham PCM (tahtaya yeni paket yok); Türkçe ses `tr_TR-dfki-medium` (CC BY-NC-SA 4.0 — kamu okulunda ticari olmayan kullanım olarak kabul); Silero yalnızca boş basış filtresi, tur yönetimi bas-konuş; RNNoise pilotta kapalı, A/B ölçümüyle; ses metrikleri pilotta yalnızca journal (dashboard `metrik`'in her satırını RAG sayıyor); tahta anahtarı websocket bağlantısında, doğrulama Brain'in `dogrula_tahta`'sında, ses düğümü yalnızca 192.168.23.0/24.
- Neden: Gemini faturalandırma engeliyle (2026-09-22'den beri) Farabi hiçbir tahtada konuşamıyor; yerel ses dış bağımlılığı ve öğrenci sesinin buluta gitmesini kaldırıyor. Ölçümler: qwen2.5:14b, Gemini'nin prompt+araç setini (17 560 token) 8192 bağlamda taşıyamıyor (32k'da %30 CPU'ya taşıyor) — bu yüzden kısa persona; RAG p50 6,4 sn (rerank 1,3 sn) — 1,5 sn hedefi yalnızca sohbet yolunda tutuyor.

## 2026-09-25 - CLAUDE.md'den düz metin şifreler çıkarıldı
- Kök `CLAUDE.md`'deki sunucu (`ata`) ve tahta (`etapadmin`, `ogretmen`) şifreleri ile ham IP/MAC listesi silindi; kimlik bilgileri yalnızca gitignore'lu `network.txt`'te. Dashboard tasarım standartları `tahtayoklama/CLAUDE.md`'ye taşındı.
- Neden: `CLAUDE.md` git'e ekli ve repo PUBLIC — şifreler `origin/master`'da açıktaydı. Geçmişte kaldıkları için şifrelerin değiştirilmesi gerekiyor (dosyadan silmek yetmez).

## 2026-09-24 - Veli & Öğrenci telefonlarının velitelefon/ Excel'lerinden sıfırdan kurulması

- **Ne yapıldı:** `velitelefon/` dizinindeki 7 sınıf Excel dosyasından (9-A..12-B)
  102 öğrencinin okul numaraları, kendi telefonları ve tüm veli telefonları (191 adet)
  ilişkisel olarak sıfırdan içe aktarıldı (`scripts/velitelefon_ice_aktar.py`).
- **Veritabanı şeması güncellendi:** `kisiler` tablosuna `okul_no` (INTEGER) ve
  `veli_rol` (TEXT: 'Anne', 'Baba', 'Teyze', 'Anneanne', 'Enişte') sütunları eklendi.
  `semayi_kur()` bu sütunları idempotan olarak otomatik ekler.
- **Öğrenci-veli ilişkisi & Çift Veli:**
  - 89 öğrencinin hem Anne hem Baba olmak üzere 2 velisi, 13 öğrencinin 1 velisi kuruldu.
  - Excel'de `VELİ ADI` bulunan veli gerçek adıyla; diğer veli ise `{Öğrenci Adı} Babası` / `{Öğrenci Adı} Annesi`
    olarak kaydedildi.
  - Kardeşler için her veli satırı tek bir öğrenciye `ogrenci_kisi_id` ile bağlandı
    (SMS kişiselleştirmede doğru çocuğun adının geçmesi için).
- **Veri kalitesi:**
  - İsimler Türkçe Title Case (Baş Harfleri Büyük) yapıldı.
  - 12-B'de daha önce öğrenci olarak yanlış girilmiş olan `Recep ACAROĞLU` (baba) temizlendi,
    yerine gerçek öğrenci `Feyza Acaroğlu` eklendi ve doğrulanmış doğum tarihi (`2009-11-25`) bağlandı.
  - 11-A'ya geçen `Deniz Çağrı Ateş` güncel sınıfına taşındı.
  - Mevcut 99 doğrulanmış öğrenci doğum tarihi ve 23 personel kaydı eksiksiz korundu.
- **Sonuç:** 102 öğrenci (92 telefonlu, 101 okul numaralı, 99 doğum tarihli),
  191 veli (hepsi telefonlu), 23 personel; toplam 316 kişi. 94 birim testin 94'ü geçti.

## 2026-09-23 - Farabi <-> Mudur PC <-> tahtalar arasinda tam yetkili SSH kurulumu

- **Ne yapildi:** Uc yonlu, kisitlamasiz (tam yetkili) SSH anahtar guveni kuruldu:
  Farabi(ata) -> Mudur PC(exa, Administrator), Mudur PC(exa) -> Farabi(ata), ve
  Mudur PC(exa) -> 7 tahta (hem ogretmen hem etapadmin hesaplari). Anahtarlar:
  `~/.ssh/id_ed25519_mudur` (Farabi->Mudur), `C:\Users\exa\.ssh\id_ed25519_farabi`
  (Mudur->Farabi), `C:\Users\exa\.ssh\id_ed25519_boards` (Mudur->tahtalar).
  Farabi->tahtalar zaten mevcuttu (`id_ed25519_tahta`), degismedi.
- **Neden:** WifiHttpProxy'nin (Mudur PC, :8080) bazen kapanmasi sorununu
  cozmenin bir parcasi olarak, EBYS Telegram botuna "Mudur proxy ac/kapat" ve
  "Farabi proxy ac/kapat" (Farabi'nin Ollama/git trafiginin Mudur proxy'sini
  kullanip kullanmadigini uzaktan degistirme) komutlari eklenecek. Bu, iki
  makine arasinda calisan bir SSH koprusu gerektiriyordu. Kullanici acikca
  "tam yetkili olsun" dedi, kisitli (`command=` zorlamali) bir anahtar yerine
  genis yetkili anahtar tercih edildi.
- **Onemli bulgu (baska oturumlarda tekrar karsilasilabilir):** Windows'ta
  `ssh-keygen -N ""` (bos parola) PowerShell uzerinden native exe cagrisinda
  guvenilir calismiyor — bos string argumani PowerShell'in native process
  cagirma katmaninda kayboluyor, `-N` bir sonraki bayragi (`-C`) deger olarak
  yutuyor, "Too many arguments" hatasi veriyor. cmd /c ile de ayni sorun.
  **Cozum:** anahtari Linux tarafinda (Farabi) uret (`-N ""` sorunsuz calisir),
  private key'i base64 + `[System.IO.File]::WriteAllBytes(...)` ile Windows'a
  tasi, `icacls` ile ACL kisitla, Linux'taki gecici kopyayi sil.
- **Ikinci onemli bulgu:** `exa` hesabi Windows Administrators grubunda —
  sshd_config'te `Match Group administrators` bloğu var, bu yuzden normal
  `C:\Users\exa\.ssh\authorized_keys` **yok sayiliyor**, anahtar
  `C:\ProgramData\ssh\administrators_authorized_keys`'e yazilmali (sadece
  SYSTEM + Administrators erisimiyle, digerleri icin `icacls /inheritance:r`).
  Bu dosyaya yanlislikla eski konuma yazip "neden calismiyor" diye saatler
  kaybetmemek icin bu ayrim onceden bilinmeli.
- **Guvenlik notu:** bu anahtarlarin ucu de KISITSIZ (repodaki `zil-timesync`
  anahtarinin `command=` zorlamali deseninin AKSINE) — Mudur PC'nin Farabi'de,
  Farabi'nin Mudur PC'de, Mudur PC'nin tahtalarda tam kabuk erisimi var.
  Kullanicinin bilincli tercihi, ama blast radius genis: bu anahtarlardan biri
  ele gecirilirse tum uc sistem etkilenir.


## 2026-09-23 - Yoklama SMS: smssistemi panonun DB'sini salt-okunur okuyor

- **Ne yapıldı:** smssistemi'ye `/yoklama-sms` sayfası eklendi (bugün devamsız
  öğrencilerin velilerine toplu bilgilendirme SMS'i). Devamsızlık verisi
  `tahtayoklama/dashboard/veri/yoklama_pano.db`'den `sqlite3 ... mode=ro` ile
  DOĞRUDAN okunuyor — `smssistemi/yoklama_kaynak.py`, tek modül.
- **Neden:** iki servis ayrı DB kullanıyor ve belgelenmiş kural "kod/DB
  paylaşımı yok, tek bağ HMAC" idi. Alternatif olarak panoya HMAC imzalı bir
  `/api/devamsiz` endpoint'i eklemek kullanıcıya sunuldu (iki servis, iki test
  paketi, iki restart); kullanıcı doğrudan salt-okunur okumayı seçti — tek
  servis, tek deploy, daha az hareketli parça.
- **Riski nasıl sınırlandı:** pano şemasını bilen TEK yer `yoklama_kaynak.py`.
  HTTP+HMAC'e dönülmek istenirse yalnızca `gunun_satirlari()`'nın gövdesi
  değişir; `yoklama_mantik.py` ve `app.py` aynı kalır. Bağlantı `mode=ro` —
  bu süreçten panonun verisine yazmak mümkün değil.
- **Bilinmesi gereken:** pano `yoklama_onbellek` şemasını değiştirirse burası
  sessizce kırılır (testteki `_PANO_SEMA` kopyası birlikte güncellenmeli).

## 2026-09-23 - Devamsızlık tanımı: "en az N derste yok", eksik yoklama listeden çıkar

- **Ne yapıldı:** "bugün gelmeyen öğrenci" = yoklaması alınan derslerin en az
  N'inde (varsayılan 4, sayfadan ayarlanır) yok görünen öğrenci. Hiç `alindi`
  dersi olmayan sınıf listeden çıkarılıp uyarı kutusunda sebebiyle gösteriliyor.
- **Neden:** yoklama ders ders tutuluyor, gün bazında bir "devamsız" kaydı YOK.
  Panonun `yoklayici.py:126`'sı `alindi` olmayan her satıra boş isim dizisi
  yazdığı için "kimse yok değil" ile "yoklama hiç alınmadı" ayırt edilemiyor —
  bu ayrım yapılmazsa 12-A'nın 2026-09-22'de yaşadığı heartbeat kopmasında tüm
  sınıfın velisine "okula gelmedi" SMS'i giderdi. 1. derse bakmak ise geç gelen
  öğrencinin velisine yanlış SMS gönderirdi.
- **Mesaj metni buna göre seçildi:** "okula gelmemiştir" değil, **"derslere
  katılmamıştır"**. Eşik kuralı kısmi devamsızlığı da kapsıyor (canlı örnek:
  6 dersin 4'ünde yok, 2 derse girmiş) — o veliye "okula gelmedi" demek yanlış
  bilgi olurdu. Aynı sebeple geçmiş tarihte gönderim butonu hiç basılmıyor:
  metin "bugün" diyor, eski listeyle gönderim yanlış günü bildirirdi.
- **Ayrıca:** izinli ders "yok" sayılmaz; velisi/telefonu bulunamayan öğrenci
  listede "Veli telefonu yoktur" ile KALIR, sessizce düşürülmez (kullanıcı
  kararı — sessiz kayıp, görünür eksikten kötüdür).

## 2026-09-04 - HTTP sürüm el sıkışması
- İstemci başlangıcında kimliği doğrulanmış `GET /api/version` çağrısıyla iki tarafın semantic sürümü karşılaştırılır.
- İletişim zaten HTTP/REST olduğundan kalıcı bağlantı protokolü eklenmeden MAJOR uyumsuzluğu ders başlamadan engellenir; MINOR/PATCH farkı uyarı olarak kalır.

## 2026-09-05 - Kesin client/server ayrımı: prompt server'a, dağıtım GitHub'a
- Client artık kesin olarak yalnızca UI/etkileşim yüzeyi (tahtada render, Gemini Live ses oturumu, yerel araç yürütme); server RAG + sistem promptu + tüm iş mantığının tutulduğu tek yer. Ayrıntı: `docs/mimari.md` §0 (yeni eklendi, bağlayıcı).
- İki somut göç PLANLANDI (henüz uygulanmadı): (1) `client/core/prompt.txt` server'a taşınacak, client oturum başında HTTP ile çekecek — mevcut "Brain karar verir, client görüntüler" desenine (ders_icerigi/pdf_sayfa) uydurmak için; (2) tahta dağıtımı rsync-pull (`farabiguncelle.sh`) yerine GitHub tabanlı, `git diff`/`git log` ile izlenen bir mekanizmaya geçecek.
- Neden: Rule 1 ("client ince kalmalı") zaten 2026-08-14'te büyük ölçüde uygulanmıştı (kitap/YKS/PDF/dosya/sağlayıcı işi server'da) — sistem promptu bu konsolidasyonun dışında unutulmuş tek parça olarak client'ta kalmıştı. Dağıtımın rsync olması ise sürüm geçmişi/rollback sağlamıyor; GitHub'a geçiş bunu çözer.
- Ses (Gemini Live bağlantısının kendisi) bu kararın KAPSAMI DIŞINDA — 2026-08-11 kararıyla client'ta kalmaya devam ediyor, ayrı bir mimari kısıt.

## 2026-09-05 - Dağıtım modeli netleştirildi: GitHub kaynak, farabi.local build/deploy noktası
- Yukarıdaki kararın dağıtım ayağı ilk yazımda yanlış anlatılmıştı ("her tahta doğrudan GitHub'a bağlı git checkout olacak") — düzeltildi. Gerçek model: GitHub = tek doğru kaynak (client+server, versiyon/rollback/tahta-sürüm takibi buradan); `farabi.local` = build/deploy noktası, GitHub'dan çeker ve derler/paketler; tahtalar GitHub'a doğrudan bağlanmaz, dağıtım server üzerinden devam eder (rsync'in yerini alacak kesin mekanizma ayrı bir uygulama kararı).
- Yeni çapraz-değişiklik kuralı: client+server bağlı değiştiğinde ikisi birlikte ele alınır — Claude her iki tarafı da inceler, ilgili test paketlerini çalıştırır; son kabul testi HER ZAMAN Atakan tarafından fiziksel tahtada yapılır, otomatikleştirilmez.
- Neden: Kullanıcı GitHub'ı "tek doğru kopya + rollback + hangi tahtada ne çalışıyor" takibi için, farabi.local'i ise mevcut build/deploy rolünü koruyan bir ara istasyon olarak tanımladı — tahtaların GitHub'a doğrudan bağlanması bu modelin parçası değil.

## 2026-09-05 - Dağıtım modeli KESİNLEŞTİ (3. ve son düzeltme): tahtalar GitHub'a DOĞRUDAN bağlanır
- Bir önceki karar ("tahtalar GitHub'a doğrudan bağlanmaz, dağıtım server üzerinden devam eder") kullanıcı tarafından tersine çevrildi: **"tahtalar serverdan kodu github üzerinden çeksin rsync iptal."** Yani doğru model, ilk yazılan (ve sonra yanlışlıkla düzeltilen) modeldi: her tahta kendi git checkout'una sahip, doğrudan GitHub'dan `git fetch` eder; `farabi.local` board dağıtımının İÇİNDE DEĞİL, yalnızca kendi `server/` kodu için paralel ve bağımsız bir şekilde GitHub'dan çeker.
- `farabiguncelle.sh` SİLİNDİ değil, rsync'ten git'e YENİDEN YAZILDI (`server/farabi-kurulum.sh` içinde, aynı isim/cron/heartbeat korunarak) — kullanıcının "farabiguncelle.sh sil" talimatı, "rsync mekanizmasını kaldır" olarak yorumlandı; script'in kendisi (tahtanın güncelleme mekanizması) hâlâ gerekli olduğu için git-tabanlı olarak yeniden üretildi. Kurulum script'indeki ssh-keygen/ssh-copy-id adımları da kaldırıldı — repo public olduğu için (`github.com/atakanunver/yenifarabi`) tahtanın server'a SSH erişimine artık hiç ihtiyacı yok.
- Doğrulanan ön koşul: repo GitHub'da PUBLIC (`git ls-remote` anonim çalıştı) — tahta tarafında kimlik doğrulama/token gerekmiyor.
- **Uygulanmadı/test edilmedi:** 9-A şu an ağda erişilemez (WOL denendi, yanıt yok) — yeni `farabiguncelle.sh` gerçek bir tahtada hiç çalıştırılmadı. Bir sonraki 9-A erişiminde ilk çalıştırma ve `client_durum.py` heartbeat'inin gerçek GitHub commit hash'i raporladığının doğrulanması gerekiyor.

## 2026-09-06 - Düzeltme: yukarıdaki "9-A ağda erişilemez" artık bayat
- 9-A'ya SSH ile bağlanıldı, `farabi.local`'e sorunsuz ulaşıyor — ağ erişimi sorunu yok. Yukarıdaki satır silinmedi (karar günlüğü o anki gerçek durumu yansıtıyordu), yalnızca bugün geçersiz olduğu not düşülüyor.
- Asıl eksik hâlâ duruyor: yukarıdaki karardaki YENİ mekanizma (`server/farabi-kurulum.sh`, sparse-checkout, kimlik doğrulamasız) 9-A'da hiç çalıştırılmadı. 9-A'nın kendi `~/.local/bin/farabiguncelle.sh`'ı 2026-09-04'te ayrıca, bu karardan bağımsız kurulmuş — tüm `~/farabi/repo`'yu (sparse değil) `gh`'nin git credential helper'ıyla pull ediyor. İki mekanizma birbirinden habersiz; hangisinin kalıcı çözüm olacağı ayrı bir karar gerektiriyor.
- Aynı oturumda bulunan, ilgisiz ama kritik bir sorun: `farabi-api.service`/`farabi-yoklama-dashboard.service` ~26 gündür (Python 3.11->3.14 geçişinden beri) eksik venv nedeniyle crash-loop halindeydi — düzeltildi, ayrıntı `CHANGELOG.md` [0.2.0].

## 2026-09-06 - 9-A'nın kendi farabiguncelle.sh'ı yeni mekanizmaya geçirildi (sparse-checkout hariç)
- Kullanıcı kararı: 9-A'nın mevcut klasör yapısı (`~/farabi/repo` tam klon, client `~/farabi/repo/client`'ta, masaüstü kısayolu bu yola sabit) BOZULMADI — kanonik `server/farabi-kurulum.sh`'ın varsaydığı sparse-checkout `~/farabi` yapısına tam yapısal migrasyon yapılmadı, riskli bulundu (canlı sınıf tahtası). Yalnızca MEKANİZMA taşındı: `~/.local/bin/farabiguncelle.sh` artık `gh` kimlik doğrulamalı `git pull` yerine kanonikteki gibi kimlik doğrulamasız `git fetch` + `git reset --hard origin/master` kullanıyor.
- `~/.local/bin/farabi-heartbeat.sh` ilk kez kuruldu ve crontab'a eklendi (15 dk'da bir) — canlıda doğrulandı, `tahta_durum` tablosunda 9-A satırı gerçek commit hash'iyle göründü.
- Bu doğrulama sırasında kanonik `server/farabi-kurulum.sh`'ın ürettiği heartbeat script'inde gerçek bir bug bulundu: `X-Farabi-Board-Key` header'ı hiç gönderilmiyordu, `client_durum.py::heartbeat` auth'a bağlı olduğu için her çağrı sessizce 401 alıyordu. Hem kanonik script hem 9-A'nın kopyası düzeltildi.
- Hâlâ açık: kanonik script'in sparse-checkout (yalnızca `client/`) klon adımı hiçbir tahtada denenmedi — bu, ayrı bir tam yapısal migrasyon kararı gerektiriyor.

## 2026-09-06 - Kritik düzeltme: repo aslında PRIVATE'tı, "public doğrulandı" yanlıştı; şimdi GERÇEKTEN public yapıldı
- 12-A'ya Farabi kurulumu denenirken bulundu: 2026-09-05'teki "repo GitHub'da PUBLIC (`git ls-remote` anonim çalıştı)" doğrulaması YANLIŞTI — test 9-A üzerinde yapılmıştı ve 9-A'da `gh` zaten `atakanunver` hesabıyla oturum açıktı (`~/.gitconfig`'te `credential.https://github.com.helper=!gh auth git-credential`), bu yüzden "anonim" görünen istek aslında bu credential helper üzerinden kimlik doğrulanmış gidiyordu. `git -c credential.helper= ls-remote ...` ile helper devre dışı bırakılınca gerçek anonim istek `could not read Username` ile reddedildi — repo GERÇEKTEN private'tı.
- Sonuç: `server/farabi-kurulum.sh`'daki "repo public, kimlik doğrulama gerekmiyor" mimari kararı (2026-09-05) YANLIŞ bir öncülle uygulanmıştı — `gh` oturumu olmayan HERHANGİ bir tahtada (9-A hariç hepsi) `git clone`/`fetch` kimlik isteyip başarısız olurdu. 12-A'da (hiç `gh` yok) bu ilk kez gerçek bir kurulumda ortaya çıktı.
- Kullanıcı kararı: repo GERÇEKTEN public yapıldı (`gh repo edit atakanunver/yenifarabi --visibility public`, 2026-09-06) — orijinal tasarım niyetine dönüldü, token/deploy-key dağıtımı gibi ek bir operasyonel yük eklenmedi. Doğrulama bu kez helper'sız yapıldı: `git -c credential.helper= ls-remote` ve `raw.githubusercontent.com` üzerinden bir dosya (200) — ikisi de gerçek anonim erişimi onayladı.
- **Ders:** Bu makinedeki (9-A) `gh` oturumu, bundan sonraki her "anonim/public erişim" testini kirletebilir — böyle bir doğrulama gerektiğinde `-c credential.helper=` ile helper'ı açıkça devre dışı bırakmadan güvenilir sayılmamalı.

## 2026-09-06 - 12-A'ya Farabi kuruldu — kanonik dağıtım mekanizmasının ilk gerçek testi
- Kullanıcı talimatıyla 12-A'ya (192.168.23.231, `server/tahta-ssh.sh 12-A` ile erişildi) Farabi client kuruldu — ilk defa 9-A DIŞINDA bir tahtada, ve ilk defa kanonik `server/farabi-kurulum.sh`'ın sparse-checkout (yalnızca `client/`, partial clone) mekanizması gerçek bir tahtada uçtan uca çalıştırıldı.
- Ön koşullar 12-A'da eksikti, tamamlandı: `git` hiç kurulu değildi (etapadmin+sudo ile `apt-get install git`), `wmctrl`/`python3-venv` de aynı fırsatla kuruldu; `libportaudio2`/`libxcb-cursor0` zaten kuruluydu.
- Kurulum sırasında client/requirements.lock.txt'te GERÇEK bir bug bulundu ve düzeltildi (ayrı commit, `ed5b657`) — kilit dosyası Python 3.14'te üretilmişti ve ~40 fazladan/kaldırılmış paket içeriyordu, tahtaların gerçek Python'unda (3.11.2) kurulum anında patlıyordu. 12-A'daki temiz kurulumdan yeniden üretildi, 9-A'nın çalışan venv'iyle çapraz doğrulandı.
- `config/api_keys.json` dolduruldu: `derslik=12-A`, `sunucu_url=http://192.168.23.252:8000`, ve server'ın `board_keys`'ine yeni üretilen bir `tahta_anahtari` eklendi (`secrets.token_hex(32)`, 9-A'nınkiyle aynı formatta) — canlıda doğrulandı (`/api/version` 200, `/api/egitim/kitaplar` 200, 12. sınıf filtresi doğru çalışıyor: 1 kitap).
- Bu sırada ayrı bir gerçek bug bulundu: server/version.py 0.2.0'a bump edilip commit edilmişti ama `farabi-api.service` hiç yeniden başlatılmamıştı — servis hâlâ 0.1.0 raporluyordu. Restart edildi, artık 0.2.0/0.2.0 eşleşiyor.
- Masaüstü kısayolu (`~/Masaüstü/farabi.desktop`), heartbeat cron (`farabi-heartbeat.sh`, 15 dk) ve günlük pull cron (`farabiguncelle.sh`, 20:00) kuruldu; heartbeat canlıda doğrulandı (`tahta_durum` tablosunda 12-A satırı, gerçek commit hash'iyle). `client/tests/` 151/151 12-A'da da geçti.
- **Bilinçli olarak yapılmadı, kullanıcının kendisi tamamlamalı:** `gemini_api_keys` boş bırakıldı (API anahtarı üretme/tedarik etme Claude'un işi değil) — sesli ders gerçekleşmeden önce elle doldurulmalı. `ders_programi.json`/`zil.json` de 9-A'daki gibi boş bırakıldı (9-A'da da gerçek dosyalar yok, yalnızca `.example.json` şablonları var — client bunlar olmadan da çalışıyor, öğretmene soruyor).
- **Bilinen risk, henüz doğrulanmadı:** 12-A'nın mikrofonu `ALC662` dahili analog kodek (harici mikrofon yok, `arecord -l` ile doğrulandı) — client/CLAUDE.md'nin "Microphone: hardware limit" bölümündeki 9-A'da ölçülen aynı düşük-hassasiyet sorununu yaşama ihtimali yüksek. `python tools/mikrofon_test.py --karsilastir` fiziksel olarak biri konuşurken çalıştırılmalı.
- Son kabul testi (fiziksel tahtada, gerçek ders) kullanıcının kendisi tarafından yapılmalı — bu, DECISIONS.md/mimari.md §0 madde 3'teki kuralın gereği.

## 2026-09-15 - `tahtaayar/` açıldı: tahta OS provizyonu ayrı, ajansız bir katman oldu
- Kullanıcı isteğiyle: ajanın tahtalarda elle yaptığı OS/oturum düzeyi düzeltmeler (güç düğmesi, uyku, ekran karartma) tekrarlanabilir script'lere dönüştürülüp yeni bir üst düzey klasörde (`tahtaayar/`) toplandı — amaç, yeni bir tahta kurulduğunda ya da mevcut bir tahta sıfırlandığında bu ayarların bir AI ajanı olmadan, sağlam bir referans tahtadan alınıp uygulanabilmesi.
- `tahtayoklama/dashboard/scripts/tahta_fix_uygula.py` buraya TAŞINDI (git mv, kopya bırakılmadı) — gerekçe: repoda zaten yaşanmış bir "iki kopya senkron kalmadı" hatası var (`mudur/` vs `tahtayoklama/dashboard/scripts/`'teki `ders_programi_yukle.py` KISALTMALAR sözlüğü), ikinci bir `DUZELTMELER` listesi aynı riski taşırdı. OS provizyonu hem `client/` hem `tahtayoklama/` altında koşan ortak bir katman, tek projeye ait değil.
- Bu taşıma sırasında yeni bir gerçek bulgu ortaya çıktı: 2026-09-14'te "çözüldü" denen güç düğmesi sorununun yalnızca YARISI kapatılmıştı. `HandlePowerKey=ignore` (systemd/logind seviyesi) doğruydu, ama Cinnamon'un kendi `button-power` gsettings anahtarı (masaüstü oturumu seviyesi, logind'den bağımsız bir ikinci tetikleyici) hâlâ `'shutdown'`'du — 7 aktif tahtanın 5'inde. Yalnızca 10-A ve 12-B'de bu daha önce elle `'nothing'`'e çekilmişti ama hiçbir script'e yazılmamıştı, yani bilgi kayboluyordu. Kullanıcı onayıyla hedef değer `'nothing'` seçildi (alternatif `'blank'` değerlendirildi, tercih edilmedi) ve 7/7 aktif tahtaya uygulandı.
- **Dürüst belirsizlik:** bu ikinci yol, 2026-09-14 fix'inden sonra da süren "kendi kendine kapanma" bildirimleri için güçlü bir aday açıklama ama kanıtlanmış kök neden değil — aynı gün kullanıcı 9-A/9-B'yi ayrı bir pano-bug testi için kendisi elle açıp kapatıyordu, bazı bildirimler buna ait olabilir. Fiziksel tuş testi SSH ile yapılamaz, son kabul kullanıcıya ait.
- Ayrıca eklendi: uzun basış için de `HandlePowerKeyLongPress=ignore`'un açıkça sabitlenmesi (önceden yalnızca systemd varsayılanına güveniliyordu), ve sleep/suspend/hibernate/hybrid-sleep target'larının maskeli kalmasını doğrulayan bir düzeltme (7 tahtada da zaten böyleydi, bu fix yeni bir tahtada aynı durumu yeniden üretir).
- Ayrıntı, tam düzeltme listesi ve "Güç düğmesi" bulgusunun hikâyesi: `tahtaayar/CLAUDE.md`.

## 2026-09-15 - Panoya "Uzaktan Yönetim" bölümü eklendi — Windows'taki tkinter panelin web karşılığı (Faz 1 + duvar kağıdı)
- Kullanıcı isteğiyle: Windows'ta ayrı çalışan `tahta_panel.py` (tkinter+paramiko, `TAHTA ISLERI` projesi) yerine, `/admin/uzaktan` altında panoya entegre bir bölüm eklendi — yoklama aç/kapat, web sayfası aç/chrome kapat, ekranı karart/kaldır, duvar kağıdı değiştir (toplu, çoklu tahta seçimiyle). Spec: `docs/superpowers/specs/2026-09-15-tahta-uzaktan-yonetim-design.md`.
- **Kasıtlı olarak dışarıda bırakıldı** (etapadmin+sudo gerektiren, sistem dosyalarına dokunan işlemler): masaüstüne dosya gönderme, oturum aç/otomatik giriş kur-kaldır, "kapat butonunu karartmaya çevir". Bunlar Faz 1'in "ogretmen'e doğrudan SSH, sudo yok" modeliyle uyuşmuyor — ayrı bir karar turu gerektirir.
- **Kullanıcı kararı — tahta kaydı:** `server/tahtalar.json` tek doğru kaynak seçildi (yeni `tahta_kaydi.py` bunu okur), panonun kendi SQLite `tahtalar` tablosuna hiçbir kopya YAZILMADI — admin.py'nin aynı ilkesi (roster/atama için server/tahtalar.json'a yazmama) buraya da uygulandı.
- **Kullanıcı kararı — erişim kontrolü:** ayrı bir yönetici şifresi eklenmedi, mevcut ortak öğretmen şifresi/oturum çerezi yeterli kabul edildi. Yani panoya girebilen herkes artık fiziksel tahtaları etkileyebilir (ekran karartma, uygulama aç/kapat, duvar kağıdı) — bilinçli bir risk kabulü, gelecekte autologin/kapat-butonu gibi daha kalıcı işlemler eklenirse yeniden değerlendirilmeli.
- **Önemli basitleşme, canlı doğrulandı:** Farabi'nin SSH anahtarı (`~/.ssh/id_ed25519_tahta`) zaten `ogretmen` hesabına doğrudan yetkili (`uzaktan_baslat.py` daha önce kanıtlamıştı) — bu yüzden Faz 1'deki hiçbir işlem sudo/root gerektirmiyor. Yerel Windows aracı `etapadmin` ile bağlanıp `sudo -u ogretmen` ile oturuma geçiyordu (paramiko+düz metin şifre); burada doğrudan `ogretmen` olarak bağlanıldığı için hem daha basit hem daha güvenli. Duvar kağıdı da aynı basitleşmeden faydalandı: yerel araç SFTP+`install`+`chown` üçlüsü gerektiriyordu (etapadmin→ogretmen sahiplik devri), burada dosya `cat > … && mv …` (admin.py'nin roster gönderme deseniyle aynı, `stdin_bytes` üzerinden — ayrı bir scp süreci yok) ile doğrudan doğru sahiplikle yazılıyor.
- **Refactor:** `uzaktan_baslat.py`'deki X-ortamı (DISPLAY/XAUTHORITY) keşif mantığı `ssh_istemci.py`'ye `x_ortamini_kesfet()` olarak taşındı ve `uid`'i de döner oldu (duvar kağıdının DBUS adresi için gerekli) — tek kopya, `tahtaayar/CLAUDE.md`'deki "iki kopya senkron kalmadı" dersine uyuldu.
- **Uçtan uca canlı doğrulama (9-A, 2026-09-15 ~23:00 TR, ders saati dışı):** durum tablosu 11 tahtaya paralel SSH ile ~3sn'de yüklendi; ekranı karart→kaldır çalıştı; duvar kağıdı testi (1x1 piksel test görseli) başarıyla yazıldı ve `gsettings` ile ayarlandı — **9-A'nın gerçek duvar kağıdı bu testle değişti, kullanıcı isterse panodan gerçek bir görselle geri değiştirmeli.** Servis (`farabi-yoklama-dashboard.service`) ders saatleri (08:00-17:00 TR) dışında güvenle yeniden başlatıldı.
- **Yapılmadı:** değişiklikler commit edilmedi (kullanıcı açıkça istemedi/sormadı) — `git status` ile görülebilir, commit edilmek istenirse ayrıca istenmeli.

## 2026-09-15 - Farabi client kalan 4 tahtaya kuruldu (9-B, 10-A, 11-A, 12-B) — 7/7 aktif tahta tamamlandı, `server/farabi-kurulum.sh` genişletildi
- Kullanıcı talimatıyla: 12-A/11-B'den sonra Farabi client kurulmamış son 4 aktif tahtaya (9-B/192.168.23.239, 10-A/192.168.23.242, 11-A/192.168.23.228, 12-B/192.168.23.240) kurulum yapıldı, ardından `server/tahta-ssh.sh` ile uçtan uca test edildi.
- **Önce script GÜNCELLENDİ (kullanıcı talimatı: "kurulum scriptini güncelle... işlem adımlarını kurulum scripti ile karşılaştır").** 12-A kurulumunun (2026-09-06) gerçek adımları ile `server/farabi-kurulum.sh`'ın o zamanki içeriği karşılaştırıldı — script yalnızca git sparse-checkout + pull/heartbeat cron kuruyordu; venv oluşturma, `pip install -r requirements.lock.txt`, `config/api_keys.json` şablonunu kopyalayıp doldurma ve masaüstü kısayolu (`~/Masaüstü/farabi.desktop`) hepsi 12-A'da ELLE yapılmıştı, script'e hiç yazılmamıştı — bir sonraki kurulumda aynı elle-adımların tekrarlanacağı, unutulma riski taşıyan bir boşluktu. Script şimdi 7 adımlı: [0] sistem paketi ön-kontrolü (git/wmctrl/python3-venv/libportaudio2/libxcb-cursor0 — sudo çağırmaz, yalnızca raporlar, çünkü `ogretmen` kullanıcısının çoğu tahtada sudo'su yok), [1] git clone (değişmedi), [2] venv+`requirements.lock.txt` kurulumu (YENİ), [3] `config/api_keys.json` — yoksa `.example.json`'dan oluşturulup opsiyonel argümanlarla (`$1 derslik $2 sunucu_url $3 tahta_anahtari`) doldurulur, `gemini_api_keys` HİÇBİR ZAMAN script tarafından yazılmaz (YENİ), [4] masaüstü kısayolu (YENİ), [5]/[6]/[7] pull scripti/heartbeat scripti/crontab (değişmedi, yalnızca numaralandırma kaydı).
- **Ön koşul paketleri tahta tahta farklıydı, elle keşfedildi (SSH ile):** 9-B/10-A/11-A'da `git` hiç kurulu değildi, 10-A/12-B'de `libportaudio2` eksikti (12-B'de git zaten vardı). Hepsi `etapadmin`+sudo ile `apt-get install` edildi — 9-B/10-A/12-B'de NOPASSWD sudo çalıştı, 11-A'da sudo parola istedi (aynı SSH parolası, `tahtalar.json`'ın önceki notuyla tutarlı: NOPASSWD imajdan imaja değişiyor).
- **Gerçek bir bug bulundu, `farabi-kurulum.sh`'ın kendisinde DEĞİL, `tahtaayar/`'ın 2026-09-14 provizyonunda:** 10-A, 11-A, 12-B'de `~/.local/bin` dizini **root:root** sahipliğindeydi (Eyl 14 11:44 tarihli — 9-B'de bu tarihte oluşmamış, ogretmen:ogretmen kalmış), kurulum script'i heartbeat/pull script'lerini bu dizine `ogretmen` olarak yazamayıp "Erişim engellendi" ile patladı. Kök neden: `tahtaayar/`'ın güç-düğmesi fix turu (`eta-ekran-karart.sh` gibi bir script'i) muhtemelen `etapadmin`+sudo altında `mkdir -p ~/.local/bin` çalıştırmış, dizin `ogretmen`'e ait DEĞİL root'a ait oluşmuş. Üç tahtada `sudo chown -R ogretmen:ogretmen ~/.local/bin` ile düzeltildi, kurulum sorunsuz tamamlandı. **`tahtaayar/`'ın kendi script'lerinde bu sahiplik hatası büyük ihtimalle hâlâ var** — ayrı bir konu, burada yalnızca bulgu olarak not düşülüyor, `tahtaayar/` kodu bu oturumda değiştirilmedi.
- **Server tarafı:** 4 tahta için `secrets.token_hex(32)` ile yeni `tahta_anahtari` üretilip `server/config/api_keys.json`'daki `board_keys`'e eklendi (CLAUDE.md'nin "6 tahtaya placeholder anahtar yazıldı" notu güncel değilmiş — kontrol edilince 9-B/10-A/11-A/12-B için `board_keys`'te hiç kayıt yoktu, muhtemelen bir önceki temizlik/refactor'da kaybolmuş). `auth._board_keys()` dosyayı her istekte yeniden okuduğu için (`server/auth.py`) **servis restart'ı gerekmedi** — anahtarlar server dosyasına yazılır yazılmaz canlıya geçti.
- **Uçtan uca doğrulama, 4 tahtanın 4'ünde de:** `venv/bin/python -c "import main"` temiz; `client/tests/` **151 passed, 1 skipped** (9-A/12-A ile aynı sayı); `farabiguncelle.sh` (git fetch+reset) ve `farabi-heartbeat.sh` (`{"status":"ok"}`) elle çalıştırıldı; `tahta_durum` tablosunda 7 aktif tahtanın 7'si de aynı commit hash'iyle (`19a8baa`) göründü; `GET /api/egitim/kitaplar` kendi `tahta_anahtari`'sıyla 200 döndü (25 kitap, her tahtanın `derslik` alanı doğru).
- **Bilinçli olarak yapılmadı, kullanıcının kendisi tamamlamalı (12-A/11-B'deki aynı karar):** 4 tahtanın 4'ünde de `gemini_api_keys` boş bırakıldı — API anahtarı üretmek/tedarik etmek Claude'un işi değil, sesli ders öncesi elle girilmeli. `ders_programi.json`/`zil.json` de boş (yalnızca `.example.json` var).
- **Son kabul testi (fiziksel tahtada, gerçek ders/mikrofon) yapılmadı** — kural gereği (`docs/mimari.md` §0 madde 3) bu adım kullanıcıya ait.
- **Yapılmadı:** `server/farabi-kurulum.sh` ve kök `CLAUDE.md`'deki değişiklikler commit edilmedi — kullanıcı istemedi/sormadı, bu turda yalnızca kurulum + script güncellemesi istendi. `git status` ile görülebilir.

## 2026-09-17 - tahta-244 → fenlab yeniden adlandırıldı; network.txt'te gerçek bir isim-kayması hatası bulundu ve düzeltildi
- Kullanıcı teyidiyle: 192.168.23.244 (eski `tahta-244`) fiziksel olarak fen laboratuvarı — makinenin hostname'i `hostnamectl set-hostname fenlab` + `/etc/hosts` güncellemesiyle "etap"tan "fenlab"a değiştirildi (etapadmin+sudo). `server/tahtalar.json`'da anahtar "fenlab" oldu, kayda `"mac": "00:09:df:8c:32:8a"` eklendi — kullanıcı isteğiyle: IP DHCP ile değişebilir, kimlik doğrulaması için MAC esas alınmalı (otomatik MAC→IP çözümleme YOK, IP değişirse elle güncellenmeli). Dashboard SQLite'ındaki (`tahtayoklama/dashboard/veri/yoklama_pano.db`, `tahtalar` tablosu id=10) `ad` alanı da güncellendi.
- Bu işlem sırasında `network.txt` (insan-okunur ikincil referans dosya, gitignore'lu) düzenlenirken GERÇEK bir hata bulundu: `.233`/`.239`/`.242` satırlarının sınıf etiketleri (10-A/11-B/9-B) birbirine kaymıştı — IP/MAC doğruydu, isim yanlıştı. Gerçek değer (`.233`=11-B, `.239`=9-B, `.242`=10-A) her üç tahtanın kendi `data/roster/*.json` ve `client/config/api_keys.json`'daki `derslik` alanı canlı SSH ile okunarak doğrulandı; `server/tahtalar.json` (asıl doğru kaynak) zaten doğruydu, yalnızca `network.txt` yanlıştı — muhtemelen 2026-08-24'te dosya ilk yazılırken satır kayması olmuş ve hiç fark edilmemiş. Düzeltildi, dosyanın başına bu bulgu not düşüldü.
- Ders: aynı bilgiyi tutan resmi (server/tahtalar.json) ve ikincil/insan-okunur (network.txt) iki dosya olduğunda, ikincisi sessizce eskiyip yanlış kalabilir — şüphe anında asıl kaynağa ve mümkünse canlı doğrulamaya (roster/api_keys.json içeriği) güvenilmeli, ikincil referansa değil.
- Ayrıca bu oturumda `tahtayoklama/plan.md` (fazların tamamı tamamlanmış, artık yalnızca tarihsel değeri vardı) kullanıcı onayıyla `tahtayoklama/CLAUDE.md`'ye konsolide edilip `git rm` ile kaldırıldı (henüz commit edilmedi) — tek, güncel bir tahtayoklama dokümanı hedeflendi.

## 2026-09-17 - fenlab, diğer 7 aktif tahtayla aynı duruma getirildi (Farabi + tahtayoklama, tüm sınıf rosterlarıyla)
- Kullanıcı talebi: fenlab (eski tahta-244) diğer tahtalarla aynı OS-düzeyi ayarlara sahip olsun, Farabi kurulu olsun, ve tahtayoklama'da ortak kullanım alanı olduğu için (dersler mekan değişikliğiyle farklı sınıflar tarafından kullanılıyor) TEK bir sınıfa değil, TÜM sınıflara ait roster kopyalansın.
- `tahtaayar/tahta_fix_uygula.py --tahta fenlab`: güç tuşu yoksay / uzun basış yoksay / uyku hedefleri maskele fix'lerinin 3'ü uygulandı ve doğrulandı (cinnamon_guc_tusu_yoksay zaten vardı) — artık 8/8 aktif tahta (7 sınıf + fenlab) aynı ayarda.
- Farabi client kuruldu (`server/farabi-kurulum.sh fenlab http://192.168.23.252:8000 <yeni tahta_anahtari>`, anahtar `server/config/api_keys.json`'daki `board_keys.fenlab`'a eklendi). Eksik paketler (etapadmin+sudo ile kuruldu): git, wmctrl, libportaudio2, libxcb-cursor0, **python3.11-venv** (bkz. aşağıdaki script düzeltmesi). Kurulum sonrası `import main` temiz, heartbeat `{status:ok}`. `gemini_api_keys` diğer kurulumlarla aynı ilkeyle BOŞ bırakıldı — kullanıcı elle girmeli.
- **`server/farabi-kurulum.sh` düzeltildi:** [0/7] ön koşul kontrolü `python3 -c import venv` ile test ediyordu — bu Debian'da BAŞARILI dönebiliyor ama venv oluşturma anında gerçek ihtiyaç olan `ensurepip` ayrı bir pakette (`python3.11-venv`) olduğu için yine de patlıyordu (fenlab kurulumunda canlı yaşandı: ensurepip is not available). Kontrol artık `python3 -c import ensurepip`e çevrildi, eksikse çalışan Python sürümüne göre doğru paket adını (`python3.11-venv` vb.) öneriyor — bir sonraki kurulumda aynı elle-keşfin tekrarlanmaması için.
- tahtayoklama kuruldu: kendi `~/tahtayoklama/venv` (9-A dışındaki diğer tahtalarla aynı desen), `yoklama.py`+`data/zil.json` kopyalandı, `~/Masaüstü/YoklamaFenLab.desktop` oluşturuldu (diğer tahtalardaki `Yoklama<sinif>.desktop` adlandırma deseniyle tutarlı). **Fark:** `data/roster/`'a tek sınıf değil, mevcut 7 sınıfın (9-A/9-B/10-A/11-A/11-B/12-A/12-B) TAMAMI kopyalandı — `yoklama.py`'nin combo box'ı açılışta `data/roster/*.json`'ı taradığı için öğretmen o an hangi sınıf oradaysa onu seçebiliyor (canlı doğrulandı, 7/7 dosya görüldü). Dashboard tarafında HİÇBİR DEĞİŞİKLİK gerekmedi — mimari zaten kayıt içeriğindeki `sinif` alanını esas aldığından (tahtayoklama/CLAUDE.md §3) bu paylaşımlı kullanım otomatik destekleniyor; fenlab'ın dashboard'da `sinif_id=NULL`/`tahta_atanmamis` kalması bilerek korundu.
- Aynı taşıma sırasında `server/tahtalar.json`'a `fenlab` anahtarı ve `mac` alanı zaten önceki oturumda eklenmişti (bkz. bir önceki DECISIONS.md kaydı) — bu oturum yalnızca fiziksel kurulumu tamamladı.
- **Son kabul testi (fiziksel/görsel doğrulama) yapılmadı** — kural gereği kullanıcıya ait.

## 2026-09-18 - Dashboard (yoklama panosu) sidebar + ikon + Sistem Durumu sayfasıyla yeniden tasarlandı
- Kullanıcı talebi: mevcut üst-nav düzeni yerine ikonlu sol sidebar, daha "dashboard" hissiyatı, ve sunucu donanım/servis durumunu gösteren yeni bir sayfa ("sunucu sıcaklığı, fan hızı, Ollama durumu gibi çalışan servisler") — "Zil Servisi" ve "Tahta Yönetimi" başlıklarıyla.
- **Yapı:** 6 sayfa artık ortak `templates/taban.html` (base layout, `{% extends %}` + block'lar) kullanıyor — önceden her sayfada header/nav/tema-seçici neredeyse birebir kopyalanmıştı (6 kopya), tek dosyaya indirildi. İkonlar CDN/font YOK — `templates/_ikon_sprite.html` içinde tek seferlik tanımlı, stroke-tabanlı (Lucide/Feather stiline benzer, elle çizilmiş) inline SVG `<symbol>` seti, `<use href="#ik-...">` ile her yerde referanslanıyor — okul LAN'ının filtreli internetine bağımlılık yok, sayfa ağırlığı neredeyse artmadı.
- **Yeni "Sistem Durumu" sayfası** (`/sistem-durumu` + `/api/sistem-durumu`, `sistem_durumu.py`): CPU sıcaklığı+fan RPM (`sensors -j`), 2x GPU sıcaklık/kullanım/VRAM (`nvidia-smi --query-gpu... --format=csv`), RAM/disk (`/proc/meminfo`, `shutil.disk_usage`), yük ortalaması+çalışma süresi (`os.getloadavg()`, `/proc/uptime`), 6 systemd servisinin durumu (`systemctl is-active` — **sudo GEREKMEZ**, salt-okunur D-Bus sorgusu, canlı doğrulandı), ve Ollama'daki yüklü modeller (`/api/tags`). **Hiçbir yeni pip bağımlılığı eklenmedi** (psutil YOK) — repo'nun "hafif tut" konvansiyonuna (`requirements.txt` başındaki not, `ssh_istemci.py`'deki "paramiko yok" kararı) uyularak subprocess+stdlib kullanıldı. Sidebar altında da aynı veriden mini bir özet rozet (CPU sıcaklığı + N/6 servis noktası) 30sn'de bir yenileniyor.
- Değişiklik öncesi `yedek/2026-09-18_sidebar_ikon_oncesi/` içine eski templates+static+app.py yedeklendi (proje konvansiyonu, bkz. daha önceki `yedek/2026-09-15_tema_oncesi/`).
- Uçtan uca doğrulama: `venv/bin/python3 -m py_compile` temiz; servis restart edildi (ders saatleri dışı değildi ama kısa kesinti kabul edilebilir görüldü — canlı kullanıcı o an `/api/durum` polling yapıyordu, birkaç saniyelik kesintiden sonra sorunsuz devam etti); DB üzerinden geçici bir QA oturum tokenı (`auth.oturum_olustur`) üretilip tüm sayfalar (`/`, `/admin/tahtalar`, `/admin/siniflar`, `/admin/rapor`, `/admin/uzaktan`, `/sistem-durumu`, `/api/sistem-durumu`) hem `curl` hem gerçek Chrome üzerinden (üç tema: klasik/yumuşak/koyu) görsel olarak kontrol edildi, token test sonrası silindi.
- **Bilinen sınırlama:** mobil/dar-ekran (sidebar'ın off-canvas'a geçtiği <900px) davranışı bu oturumda otomasyon tarayıcısının pencere-boyutlandırma kısıtı yüzünden CANLI doğrulanamadı — CSS standart bir `transform:translateX` + hamburger deseni, ama kullanıcı gerçek bir dar ekran/telefon üzerinden bir kez kontrol etmeli.

## 2026-09-19 - SMS Sistemi: köprü redirect hatası bulundu+düzeltildi, ama Müdür PC portproxy güvenilmez çıktı — gerçek SMS testi YAPILAMADI
- `sms_gonderici.baglantiyi_test_et` ilk denemede `192.168.8.1` (modemin
  kendi LAN IP'si) adresine bağlanmaya çalışıp timeout veriyordu. Kök neden
  bulundu: modem `http://192.168.23.243:18080/` (köprü) isteğine 307 ile
  cevap veriyor ama `Location` header'ı kendi mutlak adresine
  (`http://192.168.8.1/html/index.html?origin=...`) işaret ediyor — netsh
  portproxy salt TCP seviyesinde yönlendirdiği için bu HTTP içeriğini
  düzeltmiyor, `requests`/`huawei_lte_api` da bu redirect'i olduğu gibi
  takip edip köprüden kaçıyor, Farabi o ağa doğrudan ulaşamadığı için
  bağlantı düşüyor.
- **Düzeltildi** (`smssistemi/sms_gonderici.py::_kopru_session`): her iki
  `Connection(...)` çağrısına özel bir `requests.Session` veriliyor,
  `response` hook'u her redirect'in `Location`'ındaki host:port'unu köprüyle
  değiştiriyor. Bu düzeltme doğrulandı — köprü artık en azından bazı
  denemelerde modemin gerçek giriş sayfasına (200, csrf_token'lı HTML)
  ulaşabiliyor.
- **Ama ayrı, çözülmemiş bir sorun ortaya çıktı: köprünün kendisi
  güvenilmez.** ~10 art arda denemede yalnızca 1 tanesi tam HTML'e ulaştı,
  1 tanesi `125003: Wrong Session Token` (modem API hatası, muhtemelen
  session/csrf senkron sorunu) verdi, geri kalanı
  `ConnectionError: BadStatusLine('ï»¿<!DOCTYPE html>\n')` ile düştü — yani
  HTTP response byte akışı bozuluyor (bir önceki isteğin gövdesi bir
  sonrakinin status satırı yerine okunuyor). Bu, `netsh interface
  portproxy`'nin salt TCP relay olup HTTP framing'i anlamamasından ve/veya
  bağlantı tekrar kullanımı (keep-alive) sırasında zamanlama sorunlarından
  kaynaklanıyor gibi görünüyor — `Connection: close` header'ı eklemek
  değiştirmedi.
- **Sonuç: gerçek SMS testi (Task 10) bu oturumda YAPILMADI** — güvenilmez
  bir bağlantı üzerinden gerçek bir SMS denemesi anlamlı bir doğrulama
  olmaz (başarısız bir gönderim bağlantı sorunundan mı yoksa gerçek bir
  hatadan mı kaynaklandığını ayırt edemeyiz). Bu, Farabi tarafında yazılan
  Python koduyla düzeltilebilecek bir sorun değil — Müdür PC'deki
  portproxy/firewall kurulumunun ve/veya Müdür PC'nin modeme olan Wi-Fi
  bağlantısının kendisinin incelenmesi gerekiyor (paket yakalama, portproxy
  loglama, sinyal kalitesi). Alternatif: `netsh portproxy` yerine Müdür
  PC'de gerçek bir HTTP reverse proxy (Location/body rewrite yapabilen) —
  ama bu "Müdür PC'ye uygulama kodu yok" kararını (spec, "Kullanıcı
  kararları") değiştirir, ayrı bir onay gerektirir.

## 2026-09-19 (devam) - SMS köprüsü: sorun zamanla kötüleşiyor, muhtemelen Wi-Fi sinyali
- Müdür PC'nin kendi üzerinden köprüye (`192.168.23.243:18080`) atılan 10
  bağımsız `curl.exe` isteği **10/10 başarılı** (307, hatasız) — portproxy
  kuralı ve firewall kuralı doğru, modemin kendisi de köprüden erişilebilir
  durumda. Bu, sorunun Müdür PC↔modem hattında DEĞİL, Farabi'nin köprüyü
  art arda/kalıcı bağlantıyla kullanma şeklinde olduğunu gösteriyordu.
- **Denendi ve reddedildi:** her redirect hop'unda bağlantıyı kapatıp taze
  bir TCP bağlantısı zorlamak (`session.close()` + manuel redirect takibi)
  — bu, modemin kendi redirect mantığını bozup **sonsuz döngüye** soktu
  (`origin` parametresi her seferinde bir öncekini base64 olarak sarıp
  büyüyerek 30 redirect sınırına çarpıyordu). Modem, aynı TCP bağlantısının
  kesintisiz sürmesini bekliyor gibi görünüyor.
- `sms_gonderici._baglan` artık her denemede tamamen taze bir Connection
  kurup gerçek bir API çağrısıyla (`device.information`) doğruluyor (bkz.
  commit `77cc036`) — ama bu da tek başına yeterli olmadı.
- **Önemli gözlem: başarı oranı zaman içinde kötüleşti.** Oturumun başında
  (~15:10-15:20 TR) tekli isteklerde %30-60 başarı görülüyordu; ~15:40'ta
  aynı testler ard arda **0/15** başarısız oldu (tutarlı
  `ConnectionError: BadStatusLine`, bir de `ExpatError`/`TooManyRedirects`
  çeşitlemesi). Bu, sabit/deterministik bir bug'dan çok **zamanla
  değişen bir ortam koşuluna** (en olası aday: Müdür PC'nin modemin ayrı
  Wi-Fi ağına olan sinyal kalitesi) işaret ediyor.
- **Sonuç: gerçek SMS testi hâlâ yapılamadı.** `netsh wlan show interfaces`
  çıktısı (Wi-Fi sinyal yüzdesi) istendi, henüz alınmadı — bu, sorunun
  fiziksel/ortam kaynaklı olup olmadığını netleştirecek. Netleşene kadar
  Farabi tarafında daha fazla kör deneme yapmanın değeri düşük.

## 2026-09-19 (sonuç) - SMS Sistemi uçtan uca doğrulandı ✅
- **Gerçek SMS testi başarılı**: `05059399303` numarasına `2026-09-19
  15:34:32`'de gönderildi (`gonderim_id=1be31ac0515d`, `durum=gonderildi`,
  DB'de doğrulandı: `db.gonderim_ozetleri` → `basarili: 1`). Kullanıcı
  telefonda SMS'i aldığını teyit etti.
- Önceki kayıttaki "başarı oranı zamanla kötüleşiyor" gözlemi doğru çıktı
  ama geçiciydi — birkaç dakika sonra köprü/modem stabilize oldu, ek bir
  müdahale gerekmedi. Kök neden kesin teşhis edilmedi (Wi-Fi sinyal
  dalgalanması en olası aday olarak kaldı) ama `sms_gonderici._baglan`'daki
  8 denemelik, gerçek API çağrısıyla doğrulanan retry mekanizması (bkz.
  önceki kayıt, commit `77cc036`) bu geçici bozulmayı tolere edebildi.
- **Task 10 (uçtan uca test) tamamlandı.** Proje artık üretimde çalışır
  durumda: `farabi-smssistemi.service` aktif (port 8020), dashboard'dan
  SSO ile tek tıkla giriş çalışıyor, gerçek gönderim doğrulandı.
- **Kalan/bilinçli ertelenen:** kök nedenin kesin teşhisi (paket yakalama
  ile) yapılmadı — sorun tekrar ederse `netsh wlan show interfaces` ile
  Wi-Fi sinyali ilk bakılacak yer.

## 2026-09-20 - SMS köprüsü kök nedeni bulundu ve kalıcı çözüldü: netsh portproxy → WifiHttpProxy
- Önceki kayıttaki "geçici, kendi kendine düzeldi" değerlendirmesi
  **yanlış çıktı** — sorun tekrar etti (`BadStatusLine`, tek/temiz
  denemede bile), Wi-Fi sinyali de normaldi (modem Müdür PC'nin kendi
  tarayıcısından şifreyle sorunsuz açılıyordu). Canlı teşhis (debug
  seviyesinde ham HTTP trafiği izlenerek) kök nedeni kesinleştirdi:
  **`netsh interface portproxy` ham TCP seviyesinde çalışıyor, HTTP
  mesaj çerçevelemesini (framing) anlamıyor/korumuyor** — modemin kendi
  `/html/index.html?origin=...` self-redirect akışı ve ardışık
  login/logout API çağrıları bu ham relay üzerinden bazen düzgün
  taşınıyor, bazen bozuk status-line ile düşüyor, bazen de `origin`
  parametresi köprü host'una sabitlendiği için sonsuz yönlendirme
  döngüsüne giriyordu (`TooManyRedirects`).
- **Ayrıca bulunan, düzeltilen ayrı bir bug:** `_kopru_session`'ın
  Location-yeniden-yazma hook'u redirect'in sorgu dizesini (`origin=`)
  koruyordu — bu, host düzeltmesi tek başına yeterli olmadığında döngüye
  giren asıl mekanizmaydı. Commit `ceabdfb`.
- **Kalıcı çözüm:** Müdür PC'deki köprü mekanizması `netsh portproxy`'den
  gerçek bir HTTP forward proxy'ye (`WifiHttpProxy.exe` — kullanıcının
  ayrı bir amaçla [Wi-Fi üzerinden filtrelenmiş Ethernet'i atlatma]
  yazdırdığı bir .NET CONNECT/HTTP relay) taşındı. Proxy'nin script'inde
  carrier-tethering-tespitini atlatmaya yönelik bir TTL ayarı (`DefaultTTL=65`)
  vardı — bu satır bilinçli olarak KULLANILMADI, yalnızca HTTP proxy
  kısmı devreye alındı. `sms_gonderici.py` artık modeme kendi gerçek
  IP'siyle (`192.168.8.1`, yeni `modem_ip` config alanı) bu proxy
  üzerinden konuşuyor — modemin kendi Host-eşleşme kontrolü böylece
  doğal şekilde geçiyor, eski `_kopru_session` Location-hack'ine hiç
  gerek kalmadı (komple kaldırıldı, commit `9cda34b`).
- **Yol boyunca bulunan ikinci, beklenmedik bug:** WifiHttpProxy her TCP
  bağlantısında yalnızca TEK istek işleyip soketi kapatıyor (kalıcı/
  keep-alive bağlantı desteklemiyor) — `requests`'in varsayılan bağlantı
  havuzu aynı soketi ikinci istek için yeniden kullanmaya çalışınca
  `ConnectionResetError`/`ReadTimeout` ile düşüyordu (`Connection: close`
  header'ı da tek başına çözmedi). Fix: `_TekSeferlikSession` — her
  istekten sonra adapter'ın bağlantı havuzunu kapatıp sonraki isteğin
  taze bir TCP bağlantısı açmasını zorluyor.
- **Uçtan uca doğrulandı:** `device.information()`, `device.signal()`,
  ve gerçek bir SMS gönderimi — hepsi üretim servisi (`farabi-
  smssistemi.service`, kod değişikliğinden sonra restart edildi)
  üzerinden, `05059399303` numarasına gönderildi, kullanıcı telefonda
  aldığını teyit etti.
- **config/modem.json şema değişikliği** (gitignore'lu dosya, kod
  dışında elle/scriptle güncellendi): yeni alanlar `modem_ip`,
  `proxy_host`, `proxy_port`, `proxy_user`, `proxy_pass` eklendi; eski
  `host`/`port` (köprü adresiydi) artık `sms_gonderici.py` tarafından
  okunmuyor, dosyadan silinmedi ama ölü alan.
- **Açık kalan operasyonel risk:** WifiHttpProxy.exe, Müdür PC'de
  `netsh portproxy`'nin aksine systemd/Windows servisi değil, kullanıcının
  elle çalıştırdığı bir batch script + .exe — Müdür PC yeniden
  başlatılırsa otomatik ayağa kalkmayabilir (görev zamanlayıcı/başlangıç
  klasörü ile kalıcı hale getirilmesi ayrı bir iş, bu oturumda
  yapılmadı).

## 2026-09-24 - Veli & Öğrenci Telefon Veritabanı Yenilendi + Sabah 09:00 İlk Ders Devamsızlık SMS Otomasyon Modülü Eklendi
- **Telefon Veritabanı Sıfırdan İnşa Edildi (`velitelefon/`):**
  - Tüm 7 sınıfın Excel dosyaları (`9-A.xlsx` .. `12-B.xlsx`) taranarak öğrenci-veli ilişkileri sıfırdan kuruldu.
  - Şemaya `okul_no` (INTEGER) ve `veli_rol` (TEXT: anne, baba vb.) eklendi.
  - 102 öğrenci, 191 veli (89 öğrencinin hem anne hem baba 2 velisi, 13 öğrencinin 1 velisi) ve 23 personel veritabanına eksiksiz aktarıldı.
  - 12-B'deki hatalı veri temizlendi: `Recep ACAROĞLU` (öğrenci yerine girilmişti) düzeltildi; yerine gerçek öğrenci `Feyza Acaroğlu` (no 103, doğum tarihi 2009-11-25) eklendi, Recep Acaroğlu baba olarak bağlandı.
- **Sabah 09:00 İlk Ders Devamsızlık SMS Otomasyonu (`otomasyon.py`):**
  - Kullanıcı onayı ve yönlendirmesiyle mimari kuruldu:
    1. Arayüz konumu: SMS Sisteminde müstakil `/otomasyon` sekmesi; Dashboard menüsünden de SSO ile tek tıkla `/otomasyon-git` geçişi.
    2. Varsayılan Mesaj: "Sayın {isim}, öğrenciniz {ogrenci_adi} sabah ilk saate gelmemiştir. Bilginize."
    3. Başlangıç Durumu: Güvenlik için varsayılan KAPALI (0) olarak başlatıldı, arayüzden tek tıkla AÇILIP KAPATILABİLİR switch eklendi.
  - **Fail-Closed Güvenlik Kuralı:** Yalnızca 1. derste `durum == 'alindi'` olan sınıflar taranır. Tahta kapalı/ulaşılamaz veya yoklama alınmamış sınıflardan kimseye SMS gönderilmez. İzinli öğrenciler yok sayılmaz.
  - **Anne & Baba Çift Gönderim:** Gelmeyen öğrencinin hem annesine hem babasına ayrı ayrı kişiselleştirilmiş SMS gönderilir.
  - **İdempotency:** `otomasyon_ilk_ders_son_tarih` kontrolü ile günde yalnızca 1 defa çalışır; mükerrer gönderim engellenir.
  - **Canlı Simülasyon (Kuru Çalıştırma):** Arayüzden SMS göndermeden "09:00'da kimlere ne mesaj gidecekti?" tablosu anlık önizlenebilir ve gerektiğinde manuel tetiklenebilir.
  - **Zamanlayıcı:** FastAPI `lifespan` içinde arka plan `asyncio` döngüsü ile hafta içi (Pzt-Cum) saat 09:00'da çalışır.
- **Doğrulama:** 104 birim testin 104'ü de başarıyla geçti (`pytest`); `farabi-smssistemi.service` ve `farabi-yoklama-dashboard.service` yeniden başlatıldı ve canlıda doğrulandı.

## 2026-09-25 - Farabi Health audit + Sistem Durumu genişletmesi + 8020 event-loop donması
- **Audit (ölçümle, ayrıntı `webmimari.md`):** sunucu kaynak olarak boşta (sar 8 gün: CPU %99.8 idle, iowait 0, RAM %6–9); RAG p50 6.2 sn (rerank 1.3 sn, LLM 4.6 sn), zamanla kötüleşme yok. Ollama %100 GPU, CPU fallback yok, 34.5 tok/s, tek slot.
- **smssistemi:** 09:00 otomasyonu, manuel çalıştır ve "Ollama ile düzelt" senkron çağrıları async route/döngü içinden yapıyordu → gönderim boyunca 8020'nin tamamı donuyordu. `asyncio.to_thread` + thread içinde kendi sqlite bağlantısı + `_CALISMA_KILIDI` (otomatik ve manuel tetik artık eşzamanlı koşabildiği için çift SMS'i önler, `mesaj=calisiyor`).
- **server/db.py:** `SimpleConnectionPool` → `ThreadedConnectionPool` (def endpoint'ler threadpool'da paralel koşuyor; Simple sürüm thread-safe değil).
- **Sistem Durumu:** ölçüm istek başına değil lifespan'daki tek arka plan görevinde (15 sn), API önbellekten okur (~51 ms → ~1 ms, kenar.js'in her sekmedeki 30 sn'lik çağrısı yük üretmiyor). Process/HTTP ayrımı, servis başına PID/port/CPU/RAM/uptime (tek `systemctl show`), Ollama `/api/ps`+journal, PostgreSQL+RAG (`metrik`) tek `psql`, uzak TTS/zil/SMS köprüsü (60 sn), 30 dk bellek içi trend. Salt okunur; birimlerin `Environment`'ı API'ye konmaz (ollama'nınki proxy parolası içeriyor); SMS modemine asla bağlanılmaz.
- **Bilerek yapılmayanlar:** proxy aç/kapat düğmesi (kullanıcı iptal etti; `~/proxy-on.sh` yalnızca kabuk ortamını değiştirir, gerçek toggle `server/proxy_kontrol.sh` Ollama'yı restart eder). Rerank fp16 (ölçüldü: 1298→405 ms, top-4 39/39 aynı, eşik kararı değişmedi — onay bekliyor). pgvector ANN index (gereksiz, ~800 satır/kitap).
- **Aynı gün ek — SMS otomasyonu hiç SMS göndermiyordu:** `otomasyon_calistir` → `toplu_gonder(durdur_bayragi=None)`; ilk `.is_set()` AttributeError → 0 SMS, ama gün "tamamlandi" işaretleniyor ve manuel tetik "SMS'ler gönderildi" diyordu. Mock'lu testler (`toplu_gonder` mock) ve kuru çalıştırma bunu gizliyordu. Düzeltme: `threading.Event()`; gerçek `toplu_gonder`'i sahte modemle koşan test eklendi (düzeltmesiz FAIL, düzeltmeyle PASS). Otomasyon düzeltme anında KAPALIYDI (hiç çalışmamıştı), açık bırakıldı karar kullanıcıda.
- **Sağlık yoklamaları 60 sn:** 15 sn'lik HTTP yoklamaları servis journal'larına 10 dk'da 17–65 satır ekliyordu (ölçüldü) → HTTP/Ollama API yoklamaları 60 sn'lik gruba alındı (kullanıcı onayı); başarısız sonuç önbelleğe alınmaz, her turda yeniden denenir.
- **Servisler arası DB paylaşımı — ikinci bilinçli istisna:** dashboard, Farabi PostgreSQL'ini (`metrik`, `pg_stat_*`) `psql` ile SALT OKUNUR sorguluyor (izleme amaçlı; yazma yok). İlk istisna smssistemi → `yoklama_pano.db` (2026-09-23).

## 2026-09-25 - Farabi tüm tahtalarda konuşmuyor: Gemini faturalandırma engeli + mikrofonsuz mod
- **Kök neden (kod değil):** 12-A'da "dersi başlatamadı" şikâyeti. Tahta Farabi sunucusuna ulaşıyor (heartbeat ok); kopan Gemini Live: `APIError 1008 Lightning dunning decision is deny for project: projects/1085789612187`. REST ile de 403 PERMISSION_DENIED — Google Cloud faturalandırma/ödeme engeli. 8 kurulumun (9-A dahil, `~/farabi/repo/client`) HEPSİ aynı anahtarı kullanıyor (sha1 önek `a035692e`, havuzda aynı anahtar iki kez); ilk görülen hata 9-A'da 2026-09-22 12:12. Çözüm yalnızca ödeme ya da AYRI projeden anahtar. `apikeys.env`'deki `GEMINI_API_KEY` farklı bir anahtar ama 401 ACCESS_TOKEN_TYPE_UNSUPPORTED döndü (biçimi kontrol edilmedi).
- **Mikrofonsuz mod (client, `"mikrofon": false`):** mikrofonlar bozuk olduğu için öğrenci modunda ses beklemeden anlatım. Konu DERSİ BAŞLAT'ta yazılı alınır (konu zorunlu); yoklama sorulmaz; `[MİKROFONSUZ MOD]` kuralları prompt.txt'ten SONRA eklenir (yoklama/üç adım/katılım askıda); `_otomatik_devam_dongusu` her tur bitip ses susunca `[DEVAM]` gönderir — Gemini Live kullanıcı sesi gelmeyince susar, dersi ilerleten tek şey bu. Duraklatma/video/araç sürerken göndermez, boş turdan sonra 10 sn bekler; 40 dk (zil.json yoksa) ya da zile 2 dk kala kapanış ister ve kapanış bitince dersi kapatır (boşta açık oturum ücretli).
- **Neden:** kullanıcı kararı — konu öğretmenden yazılı, tek yönlü anlatım, tahta başına config bayrağı. Yıllık plandan konu çıkarma bilerek geri getirilmedi.
- **Not:** hiçbir tahtada `config/zil.json` yok (yalnızca örnek) → `program.simdiki_ders()` hep None, Farabi dersin adını/zili bilmiyor. Ayrı karar bekliyor (zil.json dağıtımı ders motoru enjeksiyonunu da açar).
- **Çözüm (aynı gün):** yeni projeden tek Gemini anahtarı (sha256 önek `e67f5db9`) 8 kuruluma (7 sınıf + fenlab) SSH ile yazıldı: `gemini_api_keys=[yeni]`, `gemini_api_key` alanı kaldırıldı, dosya 600. Eski anahtarlar temizlendi: 9-A'daki eski `~/farabi/repo/config/api_keys.json` (hiçbir kod okumuyor, 2 eski anahtar) içinden gemini alanları silindi, yanındaki `api_keys.json.zip` silindi; sunucuda `apikeys.env`'den `GEMINI_API_KEY` satırı silindi. Fenlab'dan tahtanın venv'iyle gerçek Live bağlantısı doğrulandı (ses yanıtı geldi). Anahtar `anahtar.py::anahtarlar()` ile bağlantı denemesinde okunuyor, ama açık bir Farabi penceresi varsa yeniden başlatmak en garantisi.

## 2026-09-25 - Gitignore'lu tahta ayarları SSH ile dağıtılıyor: server/config_dagit.sh
- **Durum:** kod GitHub'dan çekiliyor ama `zil.json`, `ders_programi.json`, `api_keys.json` gitignore'lu → tahtalar kopmuştu: Farabi `client/config/zil.json` yalnızca 11-B/12-A'da, `ders_programi.json` yalnızca 9-A/11-B/12-A'da vardı; yoklamanın `zil.json`'unun iki sürümü dolaşıyordu (saatler aynı, yalnız açıklama farklı). Ayrıca kod otomatik yalnızca 20:00 cron'unda çekildiği için fenlab dahil 6 tahta mikrofonsuz mod commit'ini almamıştı → `farabiguncelle.sh` elle tetiklendi, 8'i de `6d76c66`.
- **Karar:** tek kaynak sunucu. `server/config_dagit.sh [--kuru] [tahta...]` (varsayılan 7 sınıf + fenlab) tek SSH bağlantısıyla yazar, sha256 önekiyle raporlar: `tahtayoklama/data/zil.json` → client `config/zil.json` + `~/tahtayoklama/data/zil.json`; `mudur/ders_programi.json` → client `config/ders_programi.json`; `server/config/api_keys_tahta_ortak.json` (gitignore'lu, **/api_keys*) ortak alanları (gemini_api_keys, sunucu_url, ders_kipi, os_system, mikrofon) her tahtanın api_keys.json'ına BİRLEŞTİRİR — derslik/tahta_anahtari'ye dokunmaz, eski `gemini_api_key` alanını siler. 9-A'nın `~/farabi/repo/client` yapısını kendisi algılar.
- **Kullanıcı kararı:** mikrofonsuz mod (`"mikrofon": false`) 8 tahtanın HEPSİNDE açık. zil.json artık her tahtada var → `program.simdiki_ders()` ders adını biliyor (canlıda doğrulandı); bir önceki kayıttaki "hiçbir tahtada zil.json yok" notu artık geçersiz.
- Zil ya da program değişince: kaynak dosyayı güncelle → `./config_dagit.sh --kuru` → `./config_dagit.sh`. Açık Farabi penceresi yeni ayarı yeniden başlatınca alır.

## 2026-09-25 - GeoGebra: sunucu /geogebra/ kuruldu; soğuk önbellekte ilk açılış kararsız, kapat→aç'ta ilk komut kayboluyor
- **Yapılan:** fenlab'daki `4b8d228` (geogebra aracı) Farabi'ye `git am` ile alındı (`b51dead`, mikrofonsuz-mod). Math Apps Bundle `/mnt/farabi-data/farabi/geogebra/GeoGebra`'ya açıldı (117 MB, 486 dosya; md5 `a8042a2d…`). `farabi-api` yeniden başlatıldı; `/geogebra/deployggb.js` LAN'dan 200. **Farabi'de `unzip` YOK** — python `zipfile` ile açıldı. `StaticFiles` bağlaması yalnızca import anında dizin varsa kurulur → paket konduktan SONRA restart şart (14:13'teki restart dizin boşken yapıldığı için 404 kaldı).
- **Bulgu 1 (kararsızlık):** fenlab'da headless Chrome ile, yerel paket kapalı, soğuk önbellek: 5 denemede 3 FAIL (GWT parça yükleyicisi `deferredjs/…/15.cache.js` sonrası takılıyor, `appletOnLoad` hiç tetiklenmiyor). Yerel paket 5/5 OK; önbellek bir kez dolunca (17 dosya, ~9 MB) sunucu yolu da 5/5 OK. Yani sorun yalnızca ilk soğuk açılış (yalnız graphing test edildi; geometry/3d başka parçalar çeker, onlar hâlâ soğuk). Takılan pencerede aynı pencereye tekrar komut göndermenin toparlayıp toparlamadığı test EDİLMEDİ.
- **Bulgu 2 (hata):** aynı Farabi süreci içinde GeoGebra kapatılıp yeniden açılınca ilk komut kayboluyor: ölen Chrome'un bekleyen `/komut` long-poll'u köprüde `kuyruk.get()`'te duruyor, yeni paketi o alıp ölü sokete yazıyor (BrokenPipe). `surum` değişmediği için 410 koruması devreye girmiyor.
- Sunucu testleri 108/108. Push YAPILMADI (fenlab master `4b8d228`, origin/master'ın 1 önünde; 20:00 cron'u tüm tahtalara dağıtır).

## 2026-09-25 - GeoGebra kararlı hale getirildi: tahtaya ön kopya + onaylı teslim + tek seferlik Chrome yeniden açma
- **Karar (kullanıcı, seçenek a):** paket her tahtaya SSH ile kopyalanır — `server/geogebra_dagit.sh` (config_dagit.sh deseni; `client/icerik/geogebra/GeoGebra`, 9-A'nın `repo/client`'ını algılar, özet `4d308b972665`, 8/8 tahtaya yazıldı). Sunucunun `/geogebra/` yolu yedek olarak kalır. Paket güncellenirse: önce `/mnt/farabi-data/farabi/geogebra`'yı değiştir, sonra `./geogebra_dagit.sh`.
- **Bir önceki kayıttaki üç sorunun kök nedenleri (fenlab + 12-B headless, istek zaman damgalarıyla):** (1) kapat→aç'ta ölü sayfanın long-poll'u paketi yutuyordu → sürüm Chrome durdurulmadan ÖNCE artar, "hazır" sürüme bağlı. (2) GWT parça yükleyicisi aynı-Chrome yeniden yüklemede ve soğuk sunucu yüklemesinde takılıyor, toparlanmıyor (aynı pencereye tekrar komut da başarısız — test edildi) → sayfa 8 sn'de ilk /komut'a gelmezse Chrome bir kez temiz açılır; uygulama geçişi reload yerine Chrome'u yeniden başlatır. (3) Yerel bağlantıda ~1/100 `Failed to fetch`: köprü /komut yanıtını yazıyor ama sayfaya ulaşmıyor (sayfanın /hata bildirimiyle yakalandı; request_queue_size büyütmek ETKİSİZ) → teslim onaylı: /sonuc'u gelmeyen paket sonraki /komut'ta yeniden gönderilir, sayfa id ile tekrar uygulamaz.
- **Sonuç:** stres 504 adım 0 hata (12-B + fenlab; iki `Failed to fetch` görünmeden toparlandı), kapat/aç 3/3, X ile kapatma 3/3, geçiş 3/3, soğuk sunucu 6/6. Commit'ler: push dalı `4b8d228 → 620ac53` (origin/master'dan fast-forward), Farabi mikrofonsuz-mod'da `0992baa` + `4b9df9b`.
- **Test EDİLMEDİ:** 3D (headless'ta GPU yok), gerçek ekranlı `--app` penceresi, gerçek Gemini oturumu — fiziksel test kullanıcıda.
- **Ek (aynı gün):** tembel yüklenen komut riski test edildi — Derivative/Integral/Extremum/Root/Intersect/Sequence/FitLine/Normal graphing'de <0,15 sn, yeni parça yüklemiyor (YANIT_BEKLEME 5 sn yeterli). AMA CAS (giac, `2.cache.js` 10 MB) yalnızca `classic` açılışında yükleniyor: graphing'de Solve/Factor/Tangent REDDEDİLİYOR (beklemek değiştirmiyor), classic'te çalışıyor (taze açılış 2,4–2,8 sn). Araç açıklaması + başarısız-komut özeti modeli classic'e yönlendiriyor (`23a6034`). fenlab'ın commit'lenmemiş `TANI` log satırları 20:00 `reset --hard`'dan önce `server/yedekler/fenlab_TANI_log_2026-09-25.patch`'e alındı. `geogebra_dagit.sh --kuru` 8/8 güncel.


---

# Arşiv: CLAUDE.md'den taşınan tarihli anlatımlar (2026-09-25)

Aşağıdaki kayıtlar kök `CLAUDE.md`'de duruyordu; o dosya yalnızca güncel durumu
ve kuralları taşısın diye 2026-09-25'te buraya **metin değiştirilmeden** taşındı.
Kayıtların içindeki "bu dosya", "yukarıdaki", "aşağıdaki" gibi ifadeler
CLAUDE.md'deki eski konumlarını kastediyor. Kronolojik sıradadır.
Zaten bu dosyada olan anlatımlar (2026-09-05 dağıtım, 2026-09-06 9-A mekanizması
ve heartbeat bug'ı, 2026-09-06 12-A kurulumu, 2026-09-15 dört tahta kurulumu)
ikinci kez kopyalanmadı.

## 2026-08-11 - Öğrenci sesi kalıcı olarak Gemini Live'da (yerel STT/TTS iptal)
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **Karar (2026-08-11): Öğrenci sesi kalıcı olarak Gemini Live'a (Google
bulutu) gidiyor.** Bu, önceki sürümlerde "geçici, kabul edilmiş bir açık"
olarak yazıyordu ve yerel STT/TTS hedef gösteriliyordu — o plan **iptal
edildi**. Gerekçe: Gemini Live'ın gerçek-zamanlı ses akıcılığını (konuşma
sırası, araya girme, doğal tonlama) yerel bir hatla eşleştirmek ayrı, büyük
bir mühendislik işi; başka bir projede denenebilir, bu projenin kapsamında
değil. Detay: `docs/mimari.md` §14.

## 2026-08-12 - GPU kart sabitleme ve Ollama'nın LAN'a açılması
_(CLAUDE.md'den taşındı, 2026-09-25)_

- **GPU yapılandırması** artık karara bağlandı: makinede 2x NVIDIA RTX 3060
  var, `nvidia-driver-595-open` kuruldu (`nvidia-smi` ile doğrulandı, iki kart
  da görünüyor). "Kaç kart aktif" sorusu **2026-08-12'de kapatıldı**: her
  servis kendi kartına `CUDA_VISIBLE_DEVICES` ile sabitlendi —
  `ollama.service` bir kartı (context 32768→8192'ye düşürüldü, tek 12GB
  karta sığması için), `farabi-api.service` diğer kartı (embedding+reranker
  birlikte) tek başına kullanıyor. `CUDA_DEVICE_ORDER=PCI_BUS_ID` her ikisine
  de eklendi — bu olmadan CUDA'nın kendi kart numaralandırması
  `nvidia-smi`'ninkiyle TERS çıkabiliyor (canlıda böyle bir çakışma
  yaşandı: iki servis aynı fiziksel karta düştü, modelin bir kısmı CPU'ya
  taştı — `CUDA_DEVICE_ORDER` eklenince düzeldi). Doğrulama: `ollama ps` →
  `100% GPU`, `nvidia-smi` → iki kart ayrı, `POST /api/egitim/question` uçtan
  uca test edildi.
- **Ollama** kullanıcının açık isteğiyle kuruldu — amaç Faz 1'deki Brain'i
  önceden kurmak DEĞİL, `benchmark/soru_taslak.py` gibi çevrimdışı içerik
  araçlarının bulut sağlayıcı kotalarına (deepseek/mistral/nvidia kesintileri,
  bkz. `core/saglayicilar.py`) bağımlılığını azaltmak. **2026-08-12'de
  kapsamı genişledi:** artık yalnızca Farabi'ye özel değil — `OLLAMA_HOST`
  ile okul LAN'ına açıldı (`0.0.0.0:11434`, okulun kendi güvenlik duvarı
  dış sınırı koruyor), başka projelerin de kullanabileceği kalıcı, paylaşılan
  bir yerel LLM servisi olarak düşünülüyor.

## 2026-08-14 - Üçüncü sapma: RAG dışındaki tüm ağır iş server'a taşındı
_(CLAUDE.md'den taşındı, 2026-09-25)_

**Üçüncü sapma (2026-08-14):** "Server iskeleti"nden çok daha ileri gidildi
— kullanıcının açık isteğiyle ("çoğu şeyi server tarafına alalım, client'ta
minimum dosya bulunsun") RAG dışındaki TÜM ağır iş (kitap/YKS PDF depolama,
sayfa render, bulut LLM çağrıları, dosya işleme) da server'a taşındı; bkz.
yukarıdaki "server/" ve "client/" bölümleri, mimari.md §6/§9/§10 (§15
diye bir bölüm YOK, dosya §14'te bitiyor — 2026-09-22'de doğrulandı). Bu,
Faz 1→4 yol haritasının bir adımı değil, ona PARALEL yapılan bir
konsolidasyon — roadmap'in kendisi değişmedi, yalnızca "client ince kalmalı"
kuralı (Kural 1) artık neredeyse tam uygulanıyor. Aynı oturumda kritik bir
üretim hatası da düzeltildi: server API'si LAN'a hiç açık değildi (bkz.
"server/" bölümündeki düzeltme notu).

## 2026-08-14 - farabi-api LAN'a açıldı (0.0.0.0) + MEB-CERT-TTVPN sertifikası
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **Kritik düzeltme (2026-08-14):** `farabi-api.service` önceden yalnızca
`127.0.0.1:8000`'e bağlıydı — bu satırın eski hâli "client artık BAĞLI"
diyordu ama bu YANLIŞTI, hiçbir gerçek tahta server'a ulaşamıyordu (bağlantı
reddediliyordu). `--host 0.0.0.0` yapıldı, artık LAN'dan erişilebilir ve
uçtan uca doğrulandı. VLAN/güvenlik duvarı henüz kurulmadığı için bu, Ollama
ile aynı risk modelini paylaşıyor (okul güvenlik duvarı dış sınır koruması,
bkz. §5 ve mimari.md §11). Aynı oturumda okul ağının SSL-inceleme sertifikası
(MEB-CERT-TTVPN) server'da tanınmadığı için hem HuggingFace Hub kontrolleri
(`HF_HUB_OFFLINE=1` ile atlandı, ~5dk→~12sn) hem de bulut LLM proxy çağrıları
başarısız oluyordu — sertifika server'ın sistem güven deposuna VE her venv'in
certifi paketine eklendi, artık gerçek Groq/Mistral/DeepSeek çağrıları çalışıyor.

## 2026-08-14/25 - Bulut sağlayıcı çağrıları server'a taşındı; belge_ozet yerel Ollama'ya
_(CLAUDE.md'den taşındı, 2026-09-25)_

**Kapandı (2026-08-14):** Yukarıda "hâlâ açık" denen konu artık farklı bir
biçimde kapandı — client'ın metin/görsel görevleri (eskiden `core/
saglayicilar.py`) hâlâ bulut sağlayıcılara (Groq/Mistral/DeepSeek/
OpenRouter/NVIDIA NIM) gidiyor, bu DEĞİŞMEDİ; ama artık bu çağrılar
client'tan değil server'dan yapılıyor (`server/saglayicilar.py` +
`proxy.py`), anahtarlar client diskinde durmuyor. Yerel qwen'e taşıma hâlâ
karara bağlanmadı (zincirlerde yalnızca son çare olarak duruyor) ama bu artık
ayrı bir soru — bulut bağımlılığının KENDİSİ değil, anahtarların NEREDE
durduğu sorunu çözüldü.

**Kısmen genişledi (2026-08-25):** `belge_ozet` görevi (dosya/PDF metin
özeti, `dosya.py`) için "yerel qwen'e taşıma" kararı verildi — artık bu
görevde Ollama birincil, bulut yalnızca yedek. Diğer görevler
(`gorsel`, `arama_sentez`, `video_ozet`, `sembol_duzelt`, `soru_taslak`,
`kitap_ozet`) DEĞİŞMEDİ, hâlâ bulut öncelikli/yalnızca bulut. Ollama'ya
giderken sistem mesajı olmadan dil karışması (Türkçe→Çince kayma)
gözlendi ve düzeltildi — bkz. `server/saglayicilar.py` içindeki
`_OLLAMA_VARSAYILAN_SISTEM`, ayrıntı `raganaliz.txt`'te.

- `dosya.py` (2026-08-14 eklendi) — `POST /api/egitim/dosya_isle` (multipart
  upload; PDF/docx/xlsx/pptx/görsel işleme + AI özet/analiz),
  `GET /api/egitim/dosya_indir/{id}/{ad}` (üretilen dönüşüm dosyaları, 24 saat
  sonra silinir). **2026-08-25:** metin özetleme (`belge_ozet` görevi,
  `_ai_metin`) artık ÖNCE yerel Ollama'yı (`qwen2.5:14b`) dener, bulut
  (deepseek→mistral) yalnızca Ollama yanıt vermezse devreye girer — kullanıcı
  kararı: "PDF analizinde bulut token'ı harcanmasın". Görsel özetleme
  (`gorsel_uret`, `_ai_gorsel`) hâlâ yalnızca bulut — bu makinede yerel bir
  vision modeli yok; yerel vision modeli eklemek Kural 8 kapsamında ayrı bir
  onay gerektirir. **2026-09-02: zincirin KENDİSİ değişti** (eski
  groq→nvidia zinciri tamamen ölüydü, bkz. yukarıdaki `saglayicilar.py`
  notu) — artık mistral/pixtral birincil. Ayrıca aynı tarihte ölçüldü:
  GPU 0'da yük altında **7.041 MiB boş** var (GPU 1 dolu) — yerel VLM
  tartışması bu ölçümle yapılmalı, varsayımla değil.
  Ayrıntı: `raganaliz.txt` (2026-08-25) ve kökteki `plan.md` (2026-09-02).

## 2026-08-18 - soru_log için "90 gün sonra silinir" kaldırıldı
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **Karar (2026-08-18): "90 gün sonra silinir" kaldırıldı, bilinçli
olarak.** Bu satır önceki sürümlerde burada duruyordu ama hiçbir zaman
uygulanmamıştı (crontab'da, systemd timer'da ya da kodda buna karşılık
gelen bir DELETE hiç yoktu — bir kod incelemesinde bulundu). Kullanıcı bu
boşluğu bir hata olarak DEĞİL, olması gereken durum olarak onayladı:
`soru_log` artık süre sınırı olmadan tutulur. Zaten kimlik tutulmuyor
("Anonim öğrenci sordu", bkz. Gizlilik bölümü) — süresiz saklamanın KVKK
açısından ek bir kişisel-veri riski taşımadığı değerlendirmesiyle alınmış
bir karar. İleride tekrar bir silme politikası istenirse bu not
güncellenmeli, kod tarafında hâlâ hiçbir otomatik silme mekanizması yok.

## 2026-08-30 - 9-A'da gerçek sınıf hatası: tahtadaki sayfa ≠ Farabi'nin okuduğu
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **9-A'da gerçek sınıf hatası (2026-08-30) — tahtadaki sayfa ile Farabi'nin
okuduğu farklıydı.** İki AYRI kusur bulundu, ikisi de kanıtlı:

1. **Düzeltildi:** `icerik.py::_kitap_bul` (pdf_sayfa'nın kitap seçimi),
   `_bolum_bul` (ders_icerigi'nin konu bazlı seçimi) ile SENKRON değildi.
   9. sınıf matematik için İKİ kitap var (`matematik_9.pdf` cilt 1, temalar
   1-3; `matematik_9_2.pdf` cilt 2, temalar 4-7) — `ders_icerigi` konuya
   göre doğru cildi buluyordu ama `pdf_sayfa` her zaman listedeki İLK kitabı
   (cilt 1) döndürüyordu, aynı sayfa numarası iki kitapta bambaşka içerik.
   Fix: `ders_icerigi` artık hangi kitabı seçtiğini `_SON_KITAP` (derslik
   anahtarlı, process-ömürlü dict) içine yazıyor, `pdf_sayfa` aynı derslik+
   ders için varsa onu tercih ediyor. `derslik` kimliği auth'tan DEĞİL,
   doğrudan client isteğinden geliyor (`yks.py`'nin `istek.derslik`
   deseniyle aynı) — bkz. madde 2, auth henüz client'a bağlı değil. Client
   tarafı: `actions/ders_icerigi.py`/`actions/pdf_sayfa.py` artık
   `tahta.derslik()`'i isteğe ekliyor. Test: `server/tests/test_icerik.py::
   TestKitapBul`. Uçtan uca canlıda doğrulandı (aynı derslik ile cilt 2,
   derslik olmadan cilt 1 döndüğü curl ile karşılaştırıldı).
2. **DÜZELTİLDİ (2026-08-30, aynı gün, `6ab9328` commit'i içinde — bu not
   "flagged, onay bekliyor" derken bayat kalmıştı, 2026-08-31'de koddan
   doğrulanıp güncellendi).** Kök neden: öğretmen doğrudan sayfa numarası
   söylediğinde ("Bizim 45. sayfa") Farabi `pdf_sayfa`yı ÇIPLAK çağırıyordu
   (önce/sonra hiçbir `ders_icerigi` çağrısı yok) → `pdf_sayfa` yalnızca PNG
   döndürüyordu, sayfa METNİ döndürmüyordu → Farabi ekranda ne olduğunu
   bilmeden içerik uyduruyordu. Fix: `server/icerik.py`'a
   `GET /api/egitim/pdf_sayfa_metni` eklendi (`SayfaMetniYanit`, `metin`
   alanı); `client/actions/pdf_sayfa.py` artık sayfayı gösterdikten sonra bu
   endpoint'i çağırıp modele "buna dayandır" diyerek gerçek sayfa metnini
   veriyor. 9-A'da SSH ile doğrulandı (2026-08-31): repodaki kod ile 9-A'daki
   kod checksum'ları birebir aynı, bu fix üründe canlı.

## 2026-08-30 - FAZ 1 tahta auth: yanlış rapor, geçici kapatma, üretimde zorunlu hâle geliş
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **FAZ 1 (server auth) — rapor ile gerçek durum uyuşmuyor (2026-08-30
doğrulandı).** `docs/FAZ1_IMPLEMENT_RAPORU.md` (commit edilmemiş,
`server/auth.py`/`server/tests/test_auth.py` ile birlikte hâlâ `??`)
"Client (10) dosya değiştirildi, `client` testleri 129/129 geçti" diyor —
bu YANLIŞ. `git status client/` tertemiz (hiçbir client dosyası
değişmemiş) ve gerçek `client/tests/test_board_auth.py` çalıştırıldığında
3/5 test `AttributeError: module 'core.tahta' has no attribute
'tahta_anahtari'` ile düşüyor — o fonksiyon hiç yazılmamış, hiçbir
`actions/*.py` `X-Farabi-Board-Key` header'ı göndermiyor. Server tarafı
(`auth.dogrula_tahta`, her router'a bağlı) gerçek ve çalışıyor, ama
`server/config/api_keys.json`'da `board_keys` alanı da BOŞ. Rapor bunu
düzeltmeden/silmeden burada not düşülüyor — rapor kendi hâlinde kalsın,
gerçek durum buradan okunsun.

**Operasyonel sonuç (2026-08-30'da böyleydi):** servis restart edilirse
(auth kod olarak zaten her router'a bağlı) client hiç header göndermediği
için TÜM tahtaların HER `/api/egitim/*` çağrısı 401 alırdı — bu bir
icerik.py fix'ini devreye almak için restart gerekirken keşfedildi, restart'tan
HEMEN ÖNCE. Geçici çözüm olarak `/etc/systemd/system/farabi-api.service.d/
override.conf` içine `Environment="FARABI_AUTH_REQUIRED=0"` eklenmişti
(auth.py'nin kendi tasarladığı acil rollback anahtarı).

⚠️ **ÇÖZÜLDÜ (2026-08-30, aynı gün ilerleyen saatlerde) — override
kaldırıldı, auth artık üretimde ZORUNLU.** `core.tahta.auth_headers()`/
`tahta_anahtari()` yazıldı ve `core/saglayicilar.py` + 6 `actions/*.py`
dosyasındaki (`kitap_sorusu`, `pdf_sayfa`, `ders_icerigi`, `ders_hafizasi`,
`yks_sorulari`, `file_processor`) + `main.py`'nin `ders_kaydi_yedek`
çağrısındaki TÜM sunucu isteklerine eklendi (`client/tests/
test_board_auth.py` 5/5). Yalnızca **9-A** için gerçek bir `board_keys`
anahtarı üretilip hem `server/config/api_keys.json`'a hem 9-A'nın kendi
`client/config/api_keys.json`'ına yazıldı, kod 9-A'ya senkronlandı
(`farabiguncelle.sh` elle tetiklendi). `override.conf` silindi,
`farabi-api.service` yeniden başlatıldı ve uçtan uca doğrulandı: header
yoksa/yanlışsa 401, 9-A'nın gerçek anahtarıyla 200 — hem localhost'tan hem
9-A'nın kendisinden (LAN üzerinden, `sunucu_url()` ile) gerçek istekle
test edildi.

**Diğer 6 aktif "tahta" (9-B, 10-A, 11-A, 11-B, 12-A, 12-B) bu restart'tan
ETKİLENMEDİ ve etkilenemezdi** — bu deploy sırasında keşfedildi: bu
tahtalarda Farabi client hiç KURULU DEĞİL (yalnızca ayrı bir proje olan
`tahtayoklama/` kurulu; kök `CLAUDE.md`'deki "Yoklama kurulu mu" tablosu
yoklama projesinin kurulumunu gösteriyordu, Farabi client'ının değil —
yalnızca 9-A'da ikisi birlikte, aynı venv'i paylaşarak kurulu). Bu 6 tahta
için `board_keys`'e önceden birer anahtar yazıldı (placeholder, zararsız,
şu an hiçbir client bunları hiç göndermiyor) — ileride `farabi-kurulum.sh`
ile bu tahtalara gerçek Farabi client kurulduğunda hazır beklesinler diye.
O kurulum yapılmadan bu tahtaların auth'la bir ilgisi yok.

(Not, 2026-09-25: son paragraftaki "6 tahta Farabi client kurulu değil" artık geçersiz — 2026-09-15'te hepsine kuruldu, yukarıdaki kayda bkz.)

## 2026-08-30 - RAG dokümanı düzeltmesi: kazanım filtresi hiç uygulanmamıştı
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **Daha eski düzeltme (2026-08-30, doc↔kod denetiminde bulundu), hâlâ
  geçerli:** bu satır o tarihten önceki sürümlerde "iki aşamalı: (1)
  kazanım + kitap filtresi, (2) sonuç yoksa yalnızca kitap" diyordu — bu hiç
  doğru olmamıştı, `chunk_egitim`'in `kazanim_kod` kolonu DB'de var ama kod
  tarafında hiçbir sorguda okunmuyor/filtrelenmiyor. Kazanım bazlı filtre
  fikri gerçek bir gelecek-fazı önerisi (`docs/mimari.md` §12, "RAG çıktı-
  doğrulama genişletmesi + kazanım filtresi") ama BUGÜN uygulanmış bir
  davranış değil — kod değiştirilmedi, yalnızca bu satır gerçeğe uyduruldu.

## 2026-09-02 - `gorsel` sağlayıcı zinciri onarıldı (eski zincir tamamen ölüydü)
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **2026-09-02 — `gorsel` zinciri onarıldı.** Gerçek çağrılarla ölçüldü:
  eski zincirin İKİ basamağı da ölüydü (groq `llama-4-scout` → 404, model
  groq hesabının kataloğunda artık yok; nvidia `llama-3.2-90b-vision` →
  120 sn'de bile yanıt yok) ve `gorsel_uret` `evrensel_yedek=False` ile
  çağrıldığı için üçüncü basamak yoktu. Yani `ekrandaki_soruyu_oku` ve
  `file_processor`'ın görsel işi ~31 sn sonra hata dönüyordu. Loglar bu
  yolun 2026-08-14'ten beri hiç çağrılmadığını gösterdi — arıza gizliydi,
  ilk gerçek sınıf kullanımında patlayacaktı. Yeni zincir:
  `mistral/pixtral-12b-2409` → `mistral/mistral-medium-latest` →
  `nvidia/meta/llama-3.2-11b-vision-instruct`. Uçtan uca doğrulandı
  (`POST /api/egitim/dosya_isle`, gerçek kitap sayfası: 200 OK, 10,1 sn).
  Aynı turda `kitap_ozet` ve `soru_taslak` zincirlerindeki ölü
  `nvidia/meta/llama-3.3-70b-instruct` (410 Gone) da değiştirildi.
  **nvidia bu ağdan genel olarak güvenilmez** — metin modelleri 410/timeout
  veriyor, yalnızca 11b-vision çalışıyor (10,4 sn, ama Türkçe istemde
  İngilizce cevap eğilimli, o yüzden son çare).
  Durum tespiti ve ölçümlerin tamamı: kökteki `plan.md`.

## 2026-09-02 - .gitignore anahtar kuralları desen tabanlı yapıldı
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **2026-09-02:** `.gitignore` kuralları TAM YOL idi
  (`server/config/api_keys.json`), yanında duran `apikeys.env` ve
  `api_keys_yeni 30.08.2026.txt` ignore kapsamı DIŞINDAYDI — bir
  `git add -A` anahtarları commit ederdi (Kural 9 ihlali, denetimde
  bulundu). Kurallar desen tabanlı yapıldı: `*.env`, `**/api_keys*`,
  `!**/api_keys.example.json`. Yeni anahtar dosyası bırakılırken bu
  desenlere uyduğu `git check-ignore` ile doğrulanmalı.

## 2026-09-12 - Ağ envanterinde yanlış sınıf↔IP eşlemesi düzeltildi
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **Düzeltme (2026-09-12):** Bu tablo önceden 9-B/10-A/11-B için YANLIŞ
IP eşlemesi taşıyordu (.242↔9-B, .233↔10-A, .239↔11-B yazıyordu).
MAC adresleri sabit kaldı (hiçbir IP fiilen değişmedi — DHCP kirası
tutarlı) ama sınıf↔IP eşlemesi baştan yanlış girilmişti. Her tahtaya
SSH ile bağlanıp gerçek `hostname` (`vestel<sınıf düzeyi><şube>` deseni)
okunarak doğrulandı ve tablo buna göre düzeltildi — bu üç satırda IP
yerine **hostname/MAC** esas alınmalı, statik IP notu tek başına
güvenilir değil. `server/tahtalar.json` (tahta-ssh.sh'nin kaynağı)
zaten bu doğru eşlemeyi taşıyordu (muhtemelen tahtayoklama dashboard'un
otomatik keşfi düzeltmişti) — kanonik kaynak odur, bu tablo ona göre
senkron edildi.

## 2026-09-22 - 12-A'nın IP'si değişti (.231 → .226), yoklama 4-8. derslerde koptu
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **2026-09-22 — 12-A'nın IP'si değişti: `.231` → `.226`.** DHCP kirası
bozuldu, **aynı fiziksel tahta** (MAC `00:09:df:83:ff:cc` ve hostname
`vestel12a` ile doğrulandı, sınıf değişmedi). Tam da bu dosyanın başındaki
"IP değil hostname esas alınmalı" uyarısının gerçekleşmiş hâli.
**Canlı etkisi ölçüldü:** 12-A yoklaması 1-3. derslerde alındı, 4-8.
derslerde `tahta_ulasilamaz` oldu — `.231`'in son heartbeat'i 10:30
(3. dersin bitişi), pano tahtayı tam o anda kaybetti. Güncellenen üç yer:
`server/tahtalar.json`, dashboard `tahtalar` tablosu (yoklama + uzaktan
yönetim buradan okur) ve bu tablo. Uzaktan ekran görüntüsü yeni IP'de
doğrulandı.

## 2026-09-22 - docs/mimari.md git'ten geri alındı (3f26d71'de yanlışlıkla silinmişti)
_(CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ 3f26d71 "klasör temizliği" commit'inde YANLIŞLIKLA
silinmişti (commit mesajı yalnızca "eski analiz
raporları" diyor, bu o değil; aynı commit bu dosyaya
olan atıfları da bırakmıştı). 2026-09-22'de git'ten
geri alındı — içeriği 2026-09-13'te donmuş durumda,
sonraki değişiklikleri YANSITMIYOR, okurken bunu
hesaba kat. Yoksa yeniden üretme, önce `git show
3f26d71^:docs/mimari.md` ile geri al.


---

# Arşiv: client/CLAUDE.md'den taşınan tarihli anlatımlar (2026-09-25)

Aşağıdaki kayıtlar `client/CLAUDE.md`'de duruyordu (İngilizce yazılmıştı, öyle bırakıldı);
o dosya yalnızca güncel durumu ve kuralları taşısın diye 2026-09-25'te buraya **metin
değiştirilmeden** taşındı. İçlerindeki "above/below/this file" ifadeleri client/CLAUDE.md'deki
eski konumlarını kastediyor; birçoğu yazıldıkları andaki durumu anlatır ve bugün bayat olabilir
(özellikle yerel `kitaplar/`/`icerik/`, rsync ve 9-A push anlatımları). Taşınmadan önceki tam
dosya: `git show 6387439:client/CLAUDE.md`.

## 2026-07-31 - Canlı derste bulunan iki kusur: işaretçiler sesli okunuyordu, saat 12'lik biçimdeydi
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**Two defects found only by running it** (31.07.2026, live session):

- **The model reads instruction markers aloud.** Lesson record: `FARABİ
  [DERS_ACILISI] Merhaba çocuklar…`. Defended twice, like the chain-of-thought
  leak: the opening now says not to read the marker, and `_ETIKET_RE` strips
  `[DERS_ACILISI]`, `[DERS DURUMU]`, `[ÖĞRETMEN KOMUTU]`, `[OTURUM DEVAM]` from
  the transcript.
- **The clock was handed over in 12-hour form.** `time_ctx` used `%I:%M %p`, so
  at 00:20 Farabi told the class *"saat 12:20"*. It is `%H:%M` now — the same
  format the opening already used.

**Verified working:** clean install, Live session, audio tasks, HUD animation,
live tool calls (`ders_icerigi`, `web_search`), lesson-record file,
opening line with day/time/period. **Not verified:** reliable microphone input
(above), real smart-board hardware, touchscreen, camera.

## 2026-07-31 - Model araç çağırdığını anlatıyordu: `system_instruction` ve `tools` config'e hiç gitmiyordu
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**Two things must actually be passed to `LiveConnectConfig`, and both were
   silently missing at different times: `system_instruction` and `tools`.**

   `tools=[{"function_declarations": TOOL_DECLARATIONS}]` was absent entirely —
   the declarations were built and dropped, so the model never knew any tool
   existed. The symptom was worse than silence: it **narrated calling a tool**.
   From the lesson record, 30.07.2026 23:25 —
   *"…`youtube_video` aracını çağırıyorum. (`youtube_video` çağırıldı…)
   Çocuklar, şu an ekranda … bir video dönüyor."* — with nothing on screen and
   not one `ARAÇ ▶` line in that session's log. A comment in this very file
   asserted "Araç TANIMLARI gidiyordu (tools=…)"; it did not.

   A tool works only when **both** are true: the declaration reaches the model
   (`tools=`) and the text saying when to call it reaches it
   (`system_instruction`). `tests/test_oturum_yapilandirmasi.py` now asserts the
   built config carries both; the startup banner logs the tool count.

   **The assembled prompt must actually be passed as `system_instruction`.** It
   once was not: `parts` was built and then dropped, so the returned
   `LiveConnectConfig` carried no system instruction and Farabi ran with **no
   persona at all** — no teaching rules, no tool-usage table, no lesson frame.
   It looked healthy because startup logs `Sistem promptu: prompt.txt (8033
   karakter)`; the file was read and discarded. The visible symptom was Farabi
   never calling `ders_icerigi` or `web_search` on its own: tool *declarations*
   reached the model, the text saying *when* to call them did not. If tool use
   goes quiet again, check this line before touching prompt wording.

## 2026-07-31 - Model adı emekliye ayrıldı (`gemini-2.5-flash` 404)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

`gemini-2.5-flash` **was retired mid-flight** (verified 31.07.2026: 404 "no
longer available", and `gemini-2.5-flash-lite` with it). At the time every
non-realtime call went through Gemini too, so it broke at once — the visible
symptom was `ders_icerigi` returning "Kitap içeriği okunamadı" after 17.1 s
while the class waited, with nothing explaining why. `ders_icerigi` itself
calls no AI API at all now (see "Content pipeline"), so that specific failure
mode is gone, but the lesson generalizes: **any** provider can retire a model
without notice.

`core/modeller.py` now holds only `CANLI_MODEL` (Live audio) — no fallback
logic left there, because it has exactly one consumer shape (the Live
session) and no alternative model to fall back to if the Live name breaks.
`core/saglayicilar.py` holds every other model name, one per
`(sağlayıcı, model)` pair in `GOREV_ZINCIRLERI`; a bad model id there fails
that one provider (caught, logged) and the chain moves to the next provider
— the fallback is provider-level, not a same-provider alternate-model retry
like Gemini's old `uret()` used to do. Measured for Gemini at the time of
writing: `gemini-3.6-flash` ✔, `gemini-flash-latest` ✔, `gemini-3.5-flash`
503, `gemini-2.5-flash*` 404 (kept for history; not relevant to `CANLI_MODEL`,
which is a different model family).

## 2026-07/08 - Mikrofon teşhisinde yapılan üç hata
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

Two of my own diagnostic mistakes are worth remembering:
1. **Absolute RMS thresholds were wrong.** The noise floor moves ~40x with system
   gain, so a fixed "rms 400 = speech" rule reported a silent room as speech.
   `_listen_audio`'s diagnostic now measures the floor first and bands relative
   to it.
2. **A single startup transient was misread as clipping.** Opening the stream
   produces a pop that hits 32768; judging clipping by the run's max peak made
   `mikrofon_test.py` recommend *lowering* gain when the real problem was too
   little signal. It now skips the first blocks and judges clipping by the
   proportion of samples at the ceiling.
3. **A logarithmic level bar hid the answer.** rms 500 → 29 bars, rms 5000 → 40
   bars, so speech and room noise looked identical and the level appeared "flat".
   Now square-root scaled.

Interpreting levels without knowing *when* the speaker was talking produced two
wrong diagnoses. The two-phase `--karsilastir` mode exists because of that:
it measures silence and speech itself and reports the ratio.

## 2026-08-02 - Kayıt/ders kaydı hataları: ÖĞRETMEN etiketi yoktu, sözü kesilen turlar birleşiyordu
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**ÖĞRETMEN is a distinct label from ÖĞRENCİ, and it did not exist until
02.08.2026.** Only *written* teacher input (panel buttons, the input box —
anything that goes out as `[ÖĞRETMEN KOMUTU] ...`) gets it; spoken input
still can't be attributed to the teacher specifically (see SINIRLARIN in
`core/prompt.txt`) and stays ÖĞRENCİ. Before this, `_on_teacher_command()`
sent the instruction to the model and showed it on the **on-screen** DERS
KAYDI panel (`ui.py`, ephemeral) but never called `transcript.log_line()` —
the persistent daily file only ever showed Farabi's resulting *response*,
never the teacher's actual instruction that caused it. Found by reading a
real lesson transcript to debug reported model misbehavior and being unable
to tell what the teacher had actually typed. Fixed in `_on_teacher_command()`
(`main.py`): logs `metin` with the `"[ÖĞRETMEN KOMUTU] "` prefix stripped
(the ÖĞRETMEN label already says that) for every teacher action, including
DURDUR/DEVAM ET, not only free-typed instructions.

The lesson record once leaked a serialized tool call and the model's **English
chain-of-thought** about a student ("Struggles with understanding…"). Two defences
now: `thinking_config(include_thoughts=False)` at the source, and
`_konusma_temizle()` which strips tool-call-shaped text. The sanitizer targets
**known tool names only** — a generic pattern would eat ordinary speech.

**A student interrupting mid-answer used to merge two turns into one unreadable
line.** `_receive_audio` (`main.py`) buffers `out_buf`/`in_buf` per turn and
only ever flushed them to the transcript on `turn_complete`. On
`server_content.interrupted` it discarded the unplayed audio queue and logged
— it did **not** flush or reset the text buffers, so a cut-off turn's partial
text just sat there and got prepended onto the **next** turn's text at the
following flush. Measured (02.08.2026, `logs/ders/2026-08-02.txt`, 11:30:22):
the teacher's "Matematik, permütasyon" landed in the same `FARABİ` line as
Farabi's previous, cut-off sentence. Fixed by flushing `in_buf`/`out_buf` to
the transcript (each in its own line, `out_buf`'s marked `(kesildi)`) and
resetting both to `[]` right in the `interrupted` branch, covered by
`tests/test_alim_dongusu_kesinti.py` against a fake, finite `session.receive()`
event sequence (no network).

## 2026-08-02 - `youtube-transcript-api` API değişikliği özet özelliğini sessizce bozmuştu
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

`_get_transcript()` was **completely broken** — `youtube-transcript-api` isn't
version-pinned in `requirements.txt`, `pip install` pulled 1.2.4, and that
release removed the classmethod the code called
(`YouTubeTranscriptApi.list_transcripts(video_id)`) in favor of an instance
method (`YouTubeTranscriptApi().list(video_id)`); it also changed
`transcript.fetch()`'s items from dicts (`entry["text"]`) to a
`FetchedTranscriptSnippet` dataclass (`entry.text`). Every call raised
`AttributeError` and was swallowed by the function's own `except Exception`,
so `youtube_video(action="summarize", ...)` silently returned "transcript
unavailable" for **every** video — this was invisible from `_handle_summarize`'s
code alone; it only surfaced by actually calling `_get_transcript()` against a
real video ID during a "run and test every feature" pass (02.08.2026). Fixed
to the current API; `_scrape_video_info`/`get_info` (no library call, pure
HTML scraping) was never affected. Same lesson as `core/modeller.py`'s Gemini
retirement and the `kitap_index.py` fitz-ordering bug above: a dependency
silently drifting out from under unpinned code is a recurring failure class
here, not a one-off — when in doubt, actually call the function with real
input rather than trusting that unchanged code still matches its library's
current API.

## 2026-08-0x - Ders dili özelliği: gizli Türkçe sabitler ve kaldırılan screen_processor
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**Two hard-coded-Turkish spots had to be found and fixed, or the feature
would silently not work**, same class of bug as the missing
`system_instruction`/`tools` lines above — each one *looked* like a detail,
each one would have made the model open an "English" lesson by literally
speaking Turkish:

- The opening's verbatim first line (`"İlk cümlen aynen şu olsun: '{selam}
  {hitap}, ben Farabi.'"`) was built from `core/zil.py`'s Turkish-only
  `selam()`/`GUN_ADLARI` — `core/zil.py` stays Turkish (it also feeds the
  UI's date/time panel, which must stay Turkish regardless of lesson
  language). `main._acilis_selam_gun(ders_dili, simdi)` computes a
  language-appropriate greeting/day name locally instead, used only for the
  opening's verbatim line.
- A second, independent `"- Tamamen TÜRKÇE konuş."` line was appended to the
  *opening's own instruction turn*, separate from and in addition to the
  `[DİL KURALI]` block in `system_instruction` — the general language
  directive alone would not have overridden this more specific, later
  instruction for the opening. Now branches on `ders_dili` (`"- Speak
  entirely in ENGLISH…"` / `"- Sprich vollständig auf DEUTSCH…"`).

**A third spot existed in `actions/screen_processor.py`, since removed
(2026-08-09, see "Project layout") — kept here as history, the lesson about
easy-to-miss unreachable config blocks still applies to any future per-module
persona/session.** It was easy to miss for exactly the reason
`core/vision_prompt.txt` is already flagged "USER-OWNED, easy to miss" in
this doc. That module opened its **own**, separate
Gemini Live sub-session (screen/webcam vision that speaks its answer
directly — see "Provider notes and API quota" for why this couldn't be
migrated off Gemini) with its own persona file and its own hard-coded
`"- Tamamen TÜRKÇE konuş."` line, completely unreachable from
`main.py._build_config()`'s `[DİL KURALI]` block. Without a fix, a student
showing their screen mid-"English lesson" would get a Turkish-speaking
vision module — a jarring, silent break of the feature `main.py` otherwise
delivers correctly. Fixed the same way as `core/prompt.txt`:
`core/vision_prompt.txt` stays Turkish, single source; `_sistem_promptu(ders_dili)`
appends the same style of EN/DE directive. `_VisionSession._session_loop()`'s
`config` (previously built once, before the `while True` reconnect loop —
unlike `main.py`, this one genuinely didn't need per-connection freshness
for anything else) now rebuilds every (re)connection so a language chosen
before `screen_process` is first called is picked up correctly; the value
comes from `self._player.ders_dili` (`self._player` is the `FarabiUI` bridge,
same object `main.py` passes as `player=self.ui` when dispatching the tool).

`tests/test_oturum_yapilandirmasi.py::TestDersDili` and `::TestAcilisSelamGun`
cover the `main.py` side: the directive text per language, the `"tr"` default
when `ui.ders_dili` is absent entirely (not just empty — a bare
`FarabiLive.__new__(...)` test double has no `.ui` at all, which is why the
read is `getattr(getattr(self, "ui", None), "ders_dili", None) or "tr"`, not
a single-level `getattr`), and the greeting/day tables for en/de.
(`tests/test_screen_processor_dili.py` covered the vision-module side the same
way — removed along with the module.)

## 2026-08-12 - Sunucu adresi tahta başına config'e alındı (`sunucu_url`)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

### Server config becomes per-board, not hardcoded (2026-08-12)

Adding this feature's backup call (below) meant a second call site would
need to know the Brain server's address — `kitap_sorusu.py` already had
`SUNUCU_URL = "http://127.0.0.1:8000"` hardcoded, fine for one-machine dev,
not fine once the server moves to the school's server room and boards are
cloned from a "golden" board image. Fixed by adding `core.tahta.sunucu_url()`
(reads `config/api_keys.json`'s new `sunucu_url` field, same file `derslik`
already lives in, falls back to localhost) and switching `kitap_sorusu.py`
to call it instead of the constant. **Still a landmine for the "clone one
board's config to N others" plan**: `derslik` and (now) `sunucu_url` both
live in `config/api_keys.json`, which also holds the Gemini key pool — that
whole file can't be blindly copied board-to-board, `derslik` at minimum
needs editing per board after any clone.

## 2026-08-12 - `ders_hafizasi` tasarımı (ilk, yerel sürüm)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

### `ders_hafizasi` — recalling a PAST lesson, added 2026-08-12

User request: "geçen ders şöyle yapmıştık" style teacher advisory — Farabi
should be able to say what a previous lesson on this board covered. Two
design calls made explicitly (not the obvious defaults):

1. **Not mid-lesson resume.** This is NOT about picking a lesson back up
   where it left off after a crash/reboot — it's about recalling a
   *different, earlier* lesson from within a *new* one.
2. **No separate "summary" storage layer.** `core/transcript.py`'s existing
   per-lesson files (see above) are the ONLY source — one file, two uses.
   Summarization happens at answer time, in the model, from the raw fetched
   text — same "fetch raw, let the model paraphrase" pattern already used by
   `yks_sorulari`/`kitap_sorusu`, not a new architecture.

**Where the frame gets logged matters.** `transcript.log_frame()` is called
from `actions/ders_icerigi.py`, not from `main.py`'s
`_cerceveyi_ogretmenden_guncelle` (the obvious first guess). Reason: that
main.py function only parses the WRITTEN teacher-panel "ders: X konu: Y"
syntax. Since this session's SESLİ HİTAP addition, a lesson frame can also
be set purely by VOICE ("Farabi öğretmen talimatı: ...") — that path never
touches the regex parser, it goes straight to the model calling
`ders_icerigi` with resolved `ders`/`konu`. `ders_icerigi()` itself is the
one point both channels funnel through, so that's where the hook lives.

**Matching**: `_norm`/`_kelimeler` word-overlap, copied a THIRD time (already
duplicated once between `ders_icerigi.py` and `yks_sorulari.py` before this
addition) rather than extracted to a shared module — matches this codebase's
own established precedent for this exact helper pair.

**Always excludes the current session** — compares every candidate file
against `transcript.session_file()`, Farabi never "recalls" the lesson
that's still running.

## 2026-08-1x - `ders_kaydi_yedek`'te yol geçişi (path traversal) hatası
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**Path traversal was a real, caught bug, not a theoretical one.** First
version's containment check compared the resolved target path against
`hedef_dizin` (the *already-derslik-joined* directory) instead of the fixed
`YEDEK_DIR` — a `derslik` value of `".."` passed the regex allowlist (all
characters individually valid) and the check, because by the time the check
ran, `hedef_dizin` had ALREADY been walked one level up by the traversal it
was supposed to catch. Live-tested: a request with `derslik=".."` wrote a
file one directory above `yedekler/ders_kaydi/`, outside the intended tree.
Fixed by checking containment against the ORIGINAL, unwalked `YEDEK_DIR` at
both the directory and final-file-path steps. Re-tested clean before
shipping. The regex allowlist alone (`[A-Za-z0-9ÇĞİÖŞÜçğıöşü_.-]+`, no `/`)
blocks multi-segment traversal but NOT a bare `".."` value — the
resolve+containment check is load-bearing, not just defense-in-depth.

## 2026-08-14 - Client: içerik, render ve sağlayıcı havuzu server'a taşındı (client tarafı notları)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **RESOLVED 2026-08-14 (server-taşıma) — supersedes the "Reconciled
2026-08-09/2026-08-11" note that used to be here.** That note said "the
text/vision provider dependency is a separate, still-open question, not
resolved by the voice decision" and warned not to "pretend content already
flows through `server/`" — this is exactly what happened next, on the
user's explicit request ("çoğu şeyi server tarafına alalım, client'ta
minimum dosya bulunsun"): `ders_icerigi`, `kitap_sorusu`, `pdf_sayfa`,
`yks_sorulari`, `file_processor`, and all five non-Gemini text/vision
providers (`core/saglayicilar.py`) now go over HTTP to `server/`. **Voice
is still the one unchanged, permanent exception** — Gemini Live stays
fully client-side, independent of `server/` (same reasoning as before:
local STT/TTS was evaluated and cancelled, realtime turn-taking/barge-in
isn't worth re-engineering for this project). See the repo root
`CLAUDE.md` and `docs/mimari.md` §6/§9/§10/§15 for the authoritative,
up-to-date architecture — **this file is the client-only detail layer,
the root doc is the source of truth when the two disagree.**

⚠️ **`kitaplar/`, `YKS/`, and everything under `icerik/` except
`icerik/onbellek/` are GONE from this board (2026-08-14, server-taşıma) —
the paragraphs below describing them as live drop directories are
HISTORICAL.** 1.1GB+ of textbook/YKS PDFs and all derived content
(`icerik/metin`, `icerik/ozet`, `icerik/eslemeler`, `icerik/yks_metin`,
`icerik/kitaplar.json`) moved to the server's own disk
(`/mnt/farabi-data/farabi/`, see root `CLAUDE.md`). This board now only
keeps `icerik/onbellek/pdf_sayfa/` and `icerik/onbellek/yks_sayfa/` — a
small (≤30 files each), disposable local cache of PNG pages already
rendered by the server for THIS board's current lesson, not a data store.
Nothing in `actions/` reads a local PDF or a local `icerik/metin/*.json`
anymore; `ders_icerigi`/`kitap_sorusu`/`pdf_sayfa`/`yks_sorulari` all call
`server/` over HTTP instead (see each tool's section further down).

**`tools/` invariant — CHANGED 2026-08-14.** `kitap_index.py`, `kitap_metin.py`,
`sembol_temizle.py` and `kitap_ozet.py` are still content preparation
scripts and their code is still here, but they **no longer run on this
board** — the `kitaplar/`/`YKS/`/`icerik/` directories they process don't
exist here anymore (see the warning box above). The HUD buttons that used to
trigger them (`📚 KİTAPLARI METNE DÖNÜŞTÜR` etc., see "Content pipeline"
below) were **removed from `ui.py`** in the same change. Content preparation
now happens once, centrally, on the server side against
`/mnt/farabi-data/farabi/` — see root `CLAUDE.md`'s "server/" section. The
"Content pipeline" subsection further down in this file describes the OLD,
now-inactive-on-this-board flow; kept for history since the scripts
themselves weren't deleted, not because a teacher should press those buttons
here.

The rest of the old algorithm notes (hand-written `eslemeler/` mappings
winning over the index, the `TARAMA_SINIRI` page-scan cap, grade defaulting
from `tahta.sinif_duzeyi()`, word-based subject matching, ≥50% theme-overlap
threshold, the 6000-char output cap, the `ozet/` summary prepend) are now
**server-side facts, not client-side ones** — see `server/icerik.py` and the
root `docs/mimari.md` for the current, authoritative description. Grade
still defaults from THIS board's `derslik` before the request is sent
(`tahta.sinif_duzeyi()`), since that's board-identity information the
server doesn't have on its own.

## 2026-08-14 - İçerik hazırlama hattı (`tools/`) ve sayfa seçimi algoritması — artık server tarafında
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

### Content pipeline — `tools/`

> ⚠️ **INACTIVE ON THIS BOARD since 2026-08-14 (server-taşıma) — kept as
> historical/reference only.** The commands and HUD buttons below assumed a
> local `kitaplar/`/`YKS/`/`icerik/` on this board; none of that exists here
> anymore (see "Project layout" above), and the HUD buttons themselves were
> removed from `ui.py`. The scripts (`tools/*.py`) are still physically
> present in this repo but don't run against this board's data — the same
> content-prep work now happens once, centrally, against
> `/mnt/farabi-data/farabi/` (see root `CLAUDE.md`'s "server/" section and
> `docs/mimari.md`). Read on only to understand the algorithms (symbol
> repair, OCR fallback, hand-written mappings, etc.) — not as instructions
> for what to run on this board.

Prepared **once, offline** (or from a HUD button, see below — HISTORICAL,
see warning above), never at runtime, and never automatically triggering an
API call without an explicit `--onayla`/button press:

```bash
python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json
python tools/kitap_metin.py  kitaplar/ --json icerik/metin
python tools/dogrula.py
python tools/yks_metin.py    YKS/      --txt  icerik/yks_metin   # for yks_sorulari

# optional, PAID (real core/saglayicilar.py calls — Groq/Mistral/DeepSeek/
# OpenRouter/NVIDIA NIM, no Gemini) — see the two subsections below
python tools/sembol_temizle.py --onayla
python tools/kitap_ozet.py     --onayla
```

There is no yearly-plan step here anymore — `tools/plan_parse.py` and
`icerik/plan.json` are gone (see "Project layout" above). A lesson only ever
needs `kitaplar.json` + `icerik/metin/`.

**`kitap_metin.py` is not optional.** It is what `ders_icerigi` reads at runtime.
A book missing from `icerik/metin/` still works, but every page selection for it
opens the PDF with `pdfplumber` in the middle of a lesson. `ls icerik/metin/` is
the check — anything in `kitaplar/` without a matching JSON is on the slow path.

**Every step above is also a HUD button** (`ui.py`, right panel): `📚 KİTAPLARI
METNE DÖNÜŞTÜR` (`_kitaplari_donustur`), `📝 YKS SORULARINI METNE DÖNÜŞTÜR`
(`_yks_donustur`), `🧹 ŞÜPHELİ SEMBOLLERİ TEMİZLE (AI)` (`_sembolleri_temizle`),
`🗒️ KİTAP ÖZETİ ÇIKAR (AI)` (`_kitap_ozeti_cikar`). The first two share
`_terminalde_donustur`, the AI-paid two share `_api_calisan_dugmeyi_baslat` —
both run in a **visible terminal window**, not silently. It used to be
`subprocess.run(capture_output=True)` — no output until the whole run finished,
which on a large/scanned book looked like the app had frozen. `_terminalde_calistir`
(module-level in `ui.py`) launches the script in the first available terminal
emulator (`x-terminal-emulator`, `gnome-terminal`, `konsole`, `xfce4-terminal`,
`xterm`) so the teacher sees the script's own progress lines live; falls back
to the old silent `subprocess.run` only if no terminal is found. This is
scoped to these admin buttons, not to `_icerik_hazirlik_kontrolu` (the startup
check) — that one still runs silent/background, because it can fire while the
HUD is coming up right before a lesson, and a terminal window stealing focus
over the board at that moment is the same class of harm that got `reminder`
removed. See "Capability boundary" below for why this doesn't conflict with the
no-terminal-execution rule. Pressing a paid button **is** the `--onayla`
confirmation — both scripts are invoked with it already set.

**`_icerik_hazirlik_kontrolu` also refreshes `icerik/kitaplar.json` on every
startup**, silently, before the two conversion steps: it diffs the PDF
filenames in `kitaplar/` against the `dosya` fields already in
`kitaplar.json` and runs `kitap_index.py` only if something's missing
(`_kitaplar_json_guncelle`). A book dropped into `kitaplar/` becomes
searchable without anyone remembering to run the indexer by hand — it still
needs `kitap_metin.py` (button or startup check) before its pages are fast.

**`yks_metin.py` is the same idea for `yks_sorulari`, run separately** — it's
not part of `dogrula.py`'s gate (that gate validates the *textbook* index, unit
coverage, theme names; the exam-question archive has no such structure to
validate). Skipping it just means `yks_sorulari` refuses every call until
`icerik/yks_metin/` exists — measured: 8 files (~2.8 MB PDFs → text, 1,300
pages) converted in 4m9s on this dev machine, one-time cost.

**`sembol_temizle.py` is a separate, opt-in, PAID third layer on top of
`kitap_metin.py`'s two-layer repair** (see below) — it sends each page that
still carries an ambiguous `#`/`$` to the text model with instructions to
replace a symbol **only when certain**, and leave it alone otherwise; anything
left ambiguous still gets the "read this sentence, not the symbol" warning at
runtime. Deliberately kept out of `dogrula.py` (which is free and instant) and
out of `kitap_metin.py` (which is free and runs on every conversion) — mixing
a paid, non-deterministic step into either would make a normal conversion or
validation run silently cost money.

**Two bugs found in a real run** (02.08.2026, live `--onayla`, real
DeepSeek/Mistral keys):

- **The "kaç sayfa düzeltildi" counter always reported 0**, even when a page
  genuinely got fixed (verified: `fizik-10.pdf` s.88 went from `supheli: 1`
  to `supheli: 0`, `ai_temizlendi: true` — real fix, wrong report). Cause:
  `kayit["supheli"]` was overwritten with the new count *before* being
  compared against the old one, so the comparison was against itself and
  could never be true. Fixed by capturing `eski_supheli` first. The
  written data was never wrong, only the summary line — worth remembering
  before assuming a "0 düzeltildi" run did nothing.
- **A single failing provider call could silently block for minutes**
  (measured: one page took 464 s with no output) — `openai`'s client
  retries 429/5xx internally with backoff *before* our own
  `_zinciri_dene` gets a chance to move to the next provider, so a
  provider we're about to skip anyway (DeepSeek returning a permanent 402
  "Insufficient Balance" is never going to succeed by retrying) still ate
  real wall-clock time on every single call. Fixed in
  `core/saglayicilar.py._istemci()`: `max_retries=0, timeout=30.0` on the
  `OpenAI(...)` client — provider-level failover already exists one layer
  up, the SDK's own retry was pure redundant latency stacked on top of it.

**`kitap_ozet.py` produces `icerik/ozet/<kitap>.json`** — a short book
summary (from a handful of sample pages) plus a grounded-web-search block of
enrichment question ideas for the book's chapters (same `google_search` tool
`web_search.py` uses). Not a new tool the model calls: `ders_icerigi`'s
`_kitap_ozeti()` reads the summary file if present and prepends it to the
page content it already returns, so a lesson still costs exactly one tool
call.

`kitap_index.py` handles "Ünite" (older books) and "Tema" (Maarif Modeli books,
which put the name inside the header: `1. Tema / Sayılar`), single file or whole
directory.

**MEB math/physics PDFs have a broken symbol font**: `R"R` should be `R→R`,
`6c, d !R` should be `∀c, d ∈ R`, `a$c` should be `a·c`. `pdfplumber` and
`pdftotext` produce identical corruption — it is the PDF. Measured: prose book 0
occurrences, matematik-9 125, matematik-10 78.

**This is now fixed offline, in text, with no API call** (`tools/kitap_metin.py`),
and the fix is deliberately two-layer:

- **unambiguous corruption is repaired** — `R"R`→`R→R`, `x!R`→`x ∈ R`, `6x`→`∀x`.
- **ambiguous corruption is never guessed, only counted** — `#` may be ≤, ≥ or ≠
  and `$` may be `·` or ≥. `ders_icerigi` reads that count (`supheli`) and appends
  a warning telling the model not to read the formula symbol by symbol. Teaching
  an inequality the wrong way round is worse than not showing the symbol at all.

**Do not re-add the image path.** Pages used to be rendered with `pypdfium2` and
transcribed by Gemini. It burned a real API call per new theme and its measured
worst case mid-lesson was a 20 s timeout (31.07.2026 live session). `_gorsel_cikar`
is gone and the note at the foot of `actions/ders_icerigi.py` says so — the broken
symbols are solved by the two layers above, not by pictures.

**Sayfa metni `PyMuPDF` (fitz) ile çıkarılıyor, `pdfplumber` ile değil** —
`kitap_metin.py` ve (02.08.2026'dan beri) `kitap_index.py` içinde; diğer
araçlarda (`file_processor`, `ders_icerigi`, `yks_metin`) `pdfplumber` hâlâ
duruyor, çünkü onlar tek seferde bir belge işliyor, bir kitaplığın tamamını
taramıyor. Gerekçe ölçüldü: `pdfplumber`, 300+ sayfalık görsel ağırlıklı
`tarih-10.pdf`'de (161 MB) her sayfanın ayrıştırılmış nesnelerini önbellekte
tutup 5+ GB'a çıkıp bu makinede (7,1 GB RAM) OOM'a düşüyordu —
`sayfa.close()` bile yetmedi. `fitz` aynı kitabı 7,1 sn'de, 246 MB sabit
bellekle bitiriyor. `kitap_index.py` aynı OOM'u kendi başına, `pdfplumber`
üzerinde tekrar üretti (ölçüldü: `_kitaplar_json_guncelle`'in ardı ardına
tetiklediği 3 eşzamanlı süreç ~4,6 GB'a çıkıp makineyi takasa düşürdü) — bu
hem `fitz`'e geçişi hem `kitap_metin.py`/`yks_metin.py`'deki `fcntl` kilit
desenini `kitap_index.py`'ye eklemeyi gerektirdi (aynı hedefe iki süreç
birden yazmasın diye).

**`kitap_index.py`'nin fitz geçişi bir REGRESYON içeriyordu, "tüm özellikleri
test et" isteği sırasında bulundu.** `indexle()` ünite/tema başlığını
yalnızca sayfanın İLK SATIRINDAN okuyor. `sayfa.get_text()` (varsayılan,
`sort=False`) fitz'in PDF'in dahili nesne sırasını izler; birçok kitapta
sayfa numarası (üstbilgi/kenar boşluğu nesnesi) başlıktan ÖNCE geliyor, bu
yüzden ilk satır "1. Tema" değil "15" gibi bir sayı oluyordu ve `BOLUM_RE`
hiç eşleşmiyordu. Ölçüldü: gerçek kitaplıkta (13 kitap) `sort=False` ile
yalnızca 3'ünde bölüm tespit ediliyordu — **`biyoloji-9.pdf` dahil, daha önce
(pdfplumber ile) 2/2 doğru tespit edilen bir kitap SIFIRA düşmüştü**, ve bu
`ders_icerigi`'yi o kitap için tamamen köreltiyordu ("Kitap bölümü
eşleşmedi"). `sayfa.get_text(sort=True)` (konum sıralı: üstten alta, soldan
sağa) düzeltti — 9 kitapta iyileşme, hiçbirinde gerileme (`tarih-10.pdf` ve
`waymark-*.pdf` ikisinde de 0 kaldı, muhtemelen taranmış/düzensiz sayfa
düzeni, sıralamadan bağımsız bir ayrı sorun). `tests/test_kitap_index_sira.py`
sentetik bir PDF'le (sayfa numarası nesnesi önce eklenir, başlık nesnesi
sayfada daha yukarıda ama SONRA eklenir — ölçülen gerçek düzenin taklidi)
bunu kilitler; `kitaplar/` bir DROP DIRECTORY olduğu (gitignore'da, her
makinede olmaması normal) için test gerçek bir kitaba bağımlı değil.

**Görsel OCR yedeği var, ama DAR ve SAYFA GÖVDESİNİN üzerine hiç yazmıyor —
bu, "Do not re-add the image path" ile ÇELİŞMİYOR, farklı bir şey.** Eski yol
her yeni temada Gemini'ye görüntü gönderiyordu (API, kota, ders-ortası gecikme).
Bu yol tamamen yerel (`tesseract`), yalnız `kitap_metin.py`'nin offline dönüştürme
adımında çalışır, asla derste değil. Her sayfada `sayfa.get_images()` ile büyük
görseller (harita, tablo-görseli, diyagram — <150×150 px ikon/logo elenir) tek
tek kırpılıp OCR'lanır ve sonuç **gövde metnine EKLENİR**, üzerine yazılmaz;
`"[SAYFADAKİ GÖRSEL/HARİTA METNİ — OCR ile okundu, hatalı olabilir]"` etiketiyle
ayrılır — `#`/`$` şüpheli sembol uyarısıyla aynı ilke: belirsiz/hatalı olabilecek
içerik asla sessizce iyi metinle karıştırılmaz. Ölçüldü ve KASITLI olarak dar:
tam sayfa OCR, zaten metin İÇEREN bir sayfada (tarih-10.pdf) denendi, sonuç
`fitz`'in çıkardığından daha kötüydü (tablo çerçeveleri "eT3.", "ee ee ee" gibi
gürültüye dönüştü) — bu yüzden OCR yalnız görsel dikdörtgenleri hedefler, gövde
metnini yeniden okumaz. Aynı mekanizma taranmış (metin katmanı hiç olmayan) bir
sayfayı da ayrıca kod yazmadan kurtarır: öyle bir sayfada gövde tek büyük bir
görseldir, döngü onu da yakalar. `tesseract`/`tesseract-ocr-tur` sistemde yoksa
(`sudo apt install tesseract-ocr tesseract-ocr-tur` — pip değil, apt paketi)
sessizce atlanır, kitap yine dönüşür. Kapatmak için: `--ocr-yok`. Ölçüldü:
12 kitaplık kitaplığın tamamında görsel OCR toplam ~20 dakika (tek seferlik,
offline; en ağırı `tarih-10.pdf` ~5 dk, 308 büyük görsel).

The `gorsel` marker itself still exists and is **inert at runtime**: `kitap_index.py`
still sets `yontem: "gorsel"` on units with ≥3 corrupt symbols, but `ders_icerigi`
only logs that field. Nothing branches on it. It is an index-quality signal now,
not an extraction mode — don't wire behaviour back onto it.

Indexing quality varies by publisher and **the gate now measures it**
(`tools/dogrula.py`). matematik and biyoloji index cleanly. `fizik-10` and
`cografya-10` do not, and the earlier note here — "page ranges are still right" —
was wrong for coğrafya: its index is a *single* unit spanning s.9–241, i.e. the
whole book, which is where the 55.4 s page scan came from. Both are now fixed by
hand in `icerik/eslemeler/`, which is the supported answer for any book whose
running headers carry no unit name.

**One cache now, plus one in-process cache:**
- `icerik/onbellek/_sayfa_secimi.json` — page selection, on disk. Without it every
  call re-scored all ~86 pages of a theme: 13.3 s versus 0.03 s.
- `_METIN_ONBELLEK` in `ders_icerigi` — a converted book (0.5–2 MB of JSON) is held
  in memory for the life of the process; one lesson hits the same book repeatedly.

The `icerik/onbellek/<kitap>-s<ilk>-<son>.md` files are **leftovers from the
removed Gemini transcription** — nothing reads them. Delete freely. Same for a
stray `icerik/plan.json` if one is sitting on disk (measured: 3.9M) — debris
from the removed yearly-plan pipeline (see "Project layout" above); no code
path reads or writes it anymore.

**A cold page selection is still the slow moment**, and how slow depends on the
book: a converted book is scored in memory, an unconverted one opens the PDF and
is bounded by `TARAMA_SINIRI` (60 pages, striding over larger ranges). Either way,
warm it before a lesson, not during one.

**Do not put textbook content in the system prompt.** The persona is ~1.4k tokens,
a theme is 13–37k. Content belongs behind a tool call.

### Page selection: hand-written mapping first, word-overlap underneath

> ⚠️ **This algorithm runs in `server/icerik.py` now (2026-08-14), not on
> this board** — see the `ders_icerigi` section above. Kept here as the
> current, accurate description of the algorithm itself (nothing about the
> matching LOGIC changed in the move, only which machine runs it and which
> `icerik/` it reads).

Where the book index is good, unit-level lookup is deterministic and nothing
beats it:

```
teacher konu (+ ders / tema) → book index → volume + pages → icerik/metin
```

Verified name-for-name for matematik-9 (7/7 across both volumes) and for
cografya-10 (7/7 against the printed table of contents).

**But "we always know where the answer is" was too strong.** Measured:
`fizik-10` matched **zero** unit names by header alone because the publisher's
page headers name every unit `ÖLÇME VE DEĞERLENDİRME`. Name matching fails
exactly where the publisher is sloppy, and no amount of matcher cleverness
fixes a name that is not there. The fix is a hand-written mapping
(`icerik/eslemeler/`) — deterministic, auditable, ~20 minutes per book — and
it always wins over the auto-index.

**Ranking pages *within* an already-resolved chapter is word-overlap only —
no semantic/embedding search.** `tools/semantic_index.py` (a local
`sentence-transformers` embedding index) existed at one point and was
**removed**: `sentence-transformers`/`torch` are gone from
`requirements.txt`, and `ders_icerigi._ilgili_sayfalar` has no import to try
before falling back — the word-overlap scorer against `konu` is the only
path now. This was a deliberate simplification (lighter board install, one
fewer subsystem to keep correct), not a regression to route around; do not
reintroduce a vector index without a concrete, measured reason the
word-overlap scorer is failing.

Symbol-heavy units are only as good as `kitap_metin.py`'s repair layer (plus
the optional `tools/sembol_temizle.py` AI pass, see "Content pipeline"
above) — the ambiguous symbols are flagged rather than silently resolved
unless that separate, paid step has been run.

### Cache warming (`tools/onbellek_isit.py`) — pay the cost before the lesson

Measured in a live run (31.07.2026, 00:29): the model called `ders_icerigi` on
its own for a `gorsel` theme, the uncached Gemini transcription ran past the
20 s tool timeout, and the class got 20 s of silence followed by a contentless
continuation. Warming that same kazanım offline took **57.1 s**; the identical
call afterwards returns in **0.03 s**.

**That original cost is gone with the image path** — warming no longer spends API
calls. What it warms is `_sayfa_secimi.json`, which matters most for a book
that has not been through `kitap_metin.py`, since selecting its pages means
opening the PDF.

**The topic must be given by hand** (`--ders --sinif --konu`) — there is no
automatic "what's tomorrow's topic" source anymore. The script used to fall
back to `gunun_adaylari` (yearly-plan candidates) when the timetable didn't
resolve a topic; that function is gone along with the plan pipeline, and
warming without a `konu` can't select real pages anyway (it would just
re-fetch the book catalogue). Whoever runs this — the evening before, e.g.
via cron — needs the teacher to have already said what topic tomorrow
covers. **Dry by default** — `--onayla` is still required.

Two symptoms that mean the cache is cold rather than something being broken: a
`ders_icerigi` timeout in the log, and Farabi telling the class about a
"teknik aksaklık" (the timeout text now explicitly forbids that phrasing).

## 2026-08-14 - Altı sağlayıcılı havuz notları (tablo bu tarihteki hâli; güncel zincir server/saglayicilar.py)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

## Provider notes and API quota

> ⚠️ **2026-08-14: the six-provider pool described below lives in
> `server/saglayicilar.py` now, not `core/saglayicilar.py` on this board.**
> This board's `core/saglayicilar.py` is just an HTTP client to it (see
> "Project layout" above). The task→chain table, cooldown logic, and model
> names below are unchanged in substance — just physically on the server
> machine, with `server/config/api_keys.json` holding the real keys instead
> of this board's `config/api_keys.json`. The Gemini-specific parts of this
> section (Live voice, key pool) are still 100% about THIS board — that part
> never moved.

Gemini Live is the only realtime option and **that is now its only job in this
repo**. **Groq and OpenRouter cannot replace it for the voice path** — neither
offers realtime bidirectional audio, so switching means a second pipeline
(VAD → STT → LLM → TTS) with manual barge-in and a separate Turkish TTS
problem. **This is now the permanent decision (2026-08-11), not just a
practical stopgap** — a local voice pipeline was evaluated and explicitly
cancelled for this project (see `docs/mimari.md` §14). `main.py`'s main
session is now the **only** Gemini consumer left
(`screen_processor.py`'s vision sub-session was the second one, removed
2026-08-09 — see "Project layout"); see "API key pool" above for the key
pool it uses.

**Every non-realtime text/vision task moved to `core/saglayicilar.py`** — a
six-provider pool (Groq, Mistral, DeepSeek, OpenRouter, NVIDIA NIM; Hugging
Face deliberately excluded, its free-tier limits aren't published/predictable
enough for anything time-sensitive). All five expose an OpenAI-compatible
`/chat/completions` endpoint, so one client library (`openai`) covers all of
them — only `base_url` + `api_key` + `model` change. Consumers:

| Task (`GOREV_ZINCIRLERI` key) | Used by | Primary → fallback |
|---|---|---|
| `gorsel` | `file_processor.py` image describe/OCR/analyze (uploaded files) | Groq → NVIDIA NIM |
| `arama_sentez` | `web_search.py` (all modes), `kitap_ozet.py` enrichment | DeepSeek → (universal: OpenRouter) |
| `belge_ozet` | `file_processor.py` text tasks (PDF/docx/txt/csv/json/pptx) | DeepSeek → Mistral → (universal) |
| `video_ozet` | `youtube_video.py` transcript summary | DeepSeek → Groq → (universal) |
| `kitap_ozet` | `tools/kitap_ozet.py` book summary | NVIDIA NIM → DeepSeek → (universal) |
| `sembol_duzelt` | `tools/sembol_temizle.py` | DeepSeek → Mistral → (universal) |

"(universal)" = `openrouter/free`, OpenRouter's own auto-router — appended to
every **text** chain as a last resort (never to `gorsel`: free vision models
are unreliable enough that a failed image task should surface as a failure,
not silently degrade). A chain member with no key configured, or that raises
any exception (429, 5xx, timeout, bad model id), is skipped and the next one
tried — unlike `core/anahtar.py`'s Gemini pool, **any** exception triggers the
next provider here, not just quota-shaped ones, because each provider is a
wholly separate service; a "model not found" on Groq says nothing about
Mistral. If every provider in a chain fails, `saglayicilar.metin_uret`/
`gorsel_uret` **raises** — callers get a real exception to catch and turn
into their own "stay inside what you know, don't invent" fallback text, same
principle as `ders_icerigi`'s `_SINIRLI_DEVAM`.

**Why `screen_processor.py` was NOT migrated despite being "vision":** it
opens its own Gemini **Live** sub-session — image in, spoken audio out,
played directly through the speakers (`calisma="daemon"` in
`actions/kayit.py`, the tool that "speaks for itself"). That is realtime
voice synthesis, the same constraint as the main session; none of the five
providers do it. Only `file_processor.py`'s image actions (a photo of
homework, uploaded — text out, no speaking) are genuinely vision-to-*text*
and could move.

**Model names live in `core/saglayicilar.py`, one place, same reasoning as
`core/modeller.py`'s Gemini deprecation handling** — these providers retire
models at least as fast as Gemini did (Groq deprecated `llama-3.3-70b-
versatile` in June 2026). Verify current IDs before assuming: console.groq.com/
docs/models, api-docs.deepseek.com, docs.mistral.ai/getting-started/models,
build.nvidia.com, openrouter.ai/models. A stale model id makes that one
provider fail (caught, logged, next provider tried) — it does not need a
Gemini-style automatic-fallback layer of its own because the provider-level
fallback already covers it.

## 2026-08-17/30 - 9-A ↔ server kod senkronu: push dönemi, rsync pull'a dönüş (sonra git ile değişti)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

### 9-A ↔ server code sync — NOT part of the git repo, lives only on this board

**This is infrastructure, not a `client/` tool the model calls — added
2026-08-17/18, documented here because it lives on and controls THIS board's
copy of the code.** Not in `docs/mimari.md` yet.

> ⚠️ **RESOLVED 2026-08-30 — pilot period ended, direction reversed back to
> pull.** Everything below describing 9-A as "the SOURCE of truth, pushes to
> the server every night" is now HISTORICAL. The user's explicit instruction:
> "9-A'dan push olayını kaldır serverdan pull etsin, client artık server
> merkezli çalışacağız." `client/` on the SERVER (`/home/ata/farabi/client/`)
> is now the one and only source of truth — edits happen there (by hand or by
> an agent working on the server), every board (9-A included) pulls from it.
> This matches what `farabi-kurulum.sh` was already built for — see its own
> section below, now back in active use for 9-A instead of being the
> "future boards" fallback it was during the pilot.
>
> **What changed on 9-A, concretely:**
> - `~/.local/bin/farabiguncelle.sh` was rewritten from a push-wrapper
>   (`farabi-push.sh` + git-commit) to a pull (`rsync -avz --delete` FROM
>   `ata@farabi.local:~/farabi/client/` TO `~/farabi/client/`). Same cron
>   line, unchanged (`0 20 * * *`), so nothing needed to change in `crontab`.
> - **Exclude list is now symmetric and load-bearing in the OPPOSITE
>   direction than before.** The old pull script generated by
>   `farabi-kurulum.sh` only excluded `config/api_keys.json(.zip)` — that was
>   fine as a *template* but would have been actively destructive run for
>   real here: the server's own `client/` working copy independently has its
>   own `venv/`, `logs/`, `.pytest_cache/`, `__pycache__/`, `memory/` (from
>   development directly on the server machine, unrelated to any board) that
>   don't belong on a board at all. A `--dry-run` caught this BEFORE it ran
>   for real — without the fix it would have deleted 9-A's own `venv/`
>   (breaking `python main.py` outright) and `logs/` (losing local lesson
>   records) on the first pull. The deployed script now excludes the same
>   full list `farabi-push.sh` used (`venv/`, `__pycache__/`, `*.pyc`,
>   `.pytest_cache/`, `logs/`, `icerik/`, `kitaplar/`, `YKS/`, `memory/`,
>   `config/api_keys.json(.zip)`, `okul dosyaları/`, `*.pdf`, `/Farabi.zip`)
>   — **always dry-run a pull script before trusting it against a real
>   board's disk**, the asymmetry between "safe to not-send" and "safe to
>   not-delete-when-absent" is not obvious from the exclude list alone.
> - `.bashrc`'s `farabi-simdi-gonder` alias (pointed at `farabi-push.sh`) was
>   replaced with `farabi-simdi-guncelle` (points at
>   `~/.local/bin/farabiguncelle.sh`, i.e. triggers a pull by hand).
> - `~/farabi/farabi-push.sh` itself was **left on disk, untouched, but no
>   longer called by anything** — same "kept for history, not deleted"
>   convention as `tools/*.py` elsewhere in this repo. Its server-side
>   auto-commit-on-push (described below) no longer fires for the same
>   reason: nothing pushes anymore.
> - Verified end-to-end the same day: `farabiguncelle.sh` run for real once,
>   confirmed 9-A picked up a genuine server-side fix
>   (`actions/pdf_sayfa.py`/`ders_icerigi.py`'s new `derslik` field, see root
>   `CLAUDE.md`'s server/ section) while `venv/`, `logs/`, `icerik/`,
>   `config/api_keys.json` stayed untouched on 9-A's disk.
>
> **Re-verified 2026-08-31 (SSH, `server/tahta-ssh.sh 9-A`):** `md5sum` over
> all 61 `.py` files under `~/farabi/client` on 9-A matches this repo's
> `client/` byte-for-byte, and `~/farabi/client/CLAUDE.md` on the board
> matched this file too (one line behind — the Ruff-linter correction made
> the same session, not yet pulled; expected, self-resolves on next
> `farabiguncelle.sh`). 9-A's real `config/api_keys.json` (not readable by
> content per this repo's own "Okuma" rule, only checked field-by-field by
> name) has `derslik=9-A`, `sunucu_url` pointed at the real server,
> `tahta_anahtari` set, `ders_kipi=ogretmenli`, and none of the five cloud-
> provider keys (correctly stripped 2026-08-14). **This repo's own local
> `client/config/api_keys.json` (dated 2026-08-09, `derslik: "10-A"`, no
> `tahta_anahtari`, still had the five cloud keys) and the equally stale
> `client/config/api_keys.json.zip` (a zipped backup from 2026-07-31) were
> deleted (2026-08-09/07-31-dated, both gitignored, neither ever tracked) —
> confirmed unused first: excluded from `farabiguncelle.sh`'s rsync, no board
> ever received them.** If you need a working local config again, copy
> `config/api_keys.example.json` and fill it in by hand — do not treat a
> stray `api_keys.json` found lying around as ground truth for any board's
> real config without checking it the way this note did.
>
> **Open gap, not yet resolved:** the server-side auto-commit that used to
> give `client/` a git history (`git add -A -- client/ && git commit`,
> described below) lived entirely on the PUSH path, inside
> `farabi-push.sh`. Now that boards pull instead, **nothing commits `client/`
> changes on the server anymore** — a fix made directly in
> `/home/ata/farabi/client/` (by hand or by an agent) sits uncommitted until
> someone runs `git add`/`git commit` themselves. Don't assume the
> "tahta senkron: ..." auto-commit history is still being kept; it stopped
> the day push stopped. If continuous history matters going forward, this
> needs its own mechanism (e.g. a server-side cron committing `client/` on a
> schedule, or just discipline about committing by hand after edits) — not
> designed yet, flagged here so the gap isn't silently assumed away.

This board (9-A) was previously the **pilot**: it was the SOURCE of truth for
`client/` code, and PUSHED to the server every night — direction was
deliberately the opposite of what you'd expect for other boards (see above
for why this ended). Nothing here touches `farabi-api.service` or restarts
anything on either machine; it only copies files and (when push was active)
recorded a git commit. The rest of this section describes the now-inactive
push mechanism, kept for history:

- **`~/farabi/farabi-push.sh`** (this board, NOT inside the `client/` tree
  that gets synced — a sibling file, edit it here directly) — `rsync`s this
  board's `~/farabi/client/` to `ata@farabi.local:~/farabi/client/`.
  Excludes `venv/`, `__pycache__/`, `.pytest_cache/`, `logs/`, `icerik/`,
  `kitaplar/`, `YKS/`, `config/api_keys.json(.zip)` (board-specific secret,
  NEVER sent), `*.pdf`. Does **not** exclude `config/zil.json`/
  `config/ders_programi.json` — those are school-wide shared, sent on
  purpose so a newly cloned board picks them up automatically. No
  `--delete` — a file removed from this board doesn't get removed from the
  server's copy by this script. **INACTIVE since 2026-08-30** — nothing
  calls this anymore, see the resolved note above.
- **`~/farabi/farabi-kurulum.sh`** — the ORIGINAL mechanism, pull-direction
  (server→board, `--delete`). **This is what 9-A's `farabiguncelle.sh` now
  runs, in substance** (the deployed script isn't literally re-generated by
  running this installer — its SSH-key-setup steps 1–2 were skipped since
  9-A already had a working key — but steps 3–4's script shape is the same
  pull+delete pattern, with the exclude list expanded per the note above).
  Still what future new boards should run as-is — see root `CLAUDE.md`'s
  analysis-report note on this, don't rebuild it.
- **`~/.local/bin/farabiguncelle.sh`** — cron target (`crontab -l`: `0 20 * *
  * ~/.local/bin/farabiguncelle.sh`, board-local time — i.e. after the 8th
  lesson ends at 15:50, well outside teaching hours). **Since 2026-08-30
  this pulls** (see resolved note above); logs to
  `~/.local/share/farabi-sync.log` same as before.
- **`farabi-simdi-gonder`** — a `.bashrc` alias for `~/farabi/farabi-push.sh`,
  so a push could be triggered by hand without waiting for 20:00. **Replaced
  2026-08-30 by `farabi-simdi-guncelle`** (triggers a pull instead), see
  resolved note above.
- **Server-side auto-commit (added 2026-08-17, INACTIVE since 2026-08-30):**
  after a real (non-`--dry-run`) push, `farabi-push.sh` SSHed into
  `farabi.local` and ran `git add -A -- client/ && git commit` if anything
  under `client/` changed — gave the server's `client/` mirror a real git
  history of what THIS board pushed, when. **No restart, ever, on either
  side** — this was deliberate (`FARABİ ASLA DERSİ BOZMAZ`), a code update
  landing on the server didn't do anything to a running lesson on any board
  until someone separately decided to act on it. See "Open gap" above — this
  mechanism has no pull-direction equivalent yet.
- **Multi-board status (planned, 2026-08-18, IN PROGRESS — check root
  `CLAUDE.md`/git log for current state before trusting this paragraph):**
  the goal is a central view of all boards' liveness/version once more
  boards exist, via a lightweight heartbeat this board would send
  independently of `main.py` (a separate cron, NOT wired into the Live
  session — heartbeat failing must never affect a lesson, same principle as
  the backup above). As of this writing the server side (`tahta_durum`
  table, `POST /api/client/heartbeat`) exists and is tested; this board's
  own heartbeat cron may not be set up yet — don't assume it's running
  without checking `crontab -l` here.

## 2026-08-23 - Öğretmen talimat modunun ilk gerçek sınıf testi: dört sorun
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

**First real classroom test (2026-08-23, same day as shipping) found four
real problems**, all from reading `logs/farabi.log` + the actual
`logs/ders/2026-08-23_14-17-09_9-A.txt` transcript, not from guessing:

1. **No way to CLOSE anything, and the model lied about it.** Only
   open-tools existed. Asked to close YouTube, the model called
   `web_ac(hedef='kapat')` — which doesn't close anything, it Google-searched
   the literal word "kapat" and opened ANOTHER tab — while telling the room
   "Kapatılıyor." Fixed with `actions/pencere_kapat.py`, a new
   `kip=("talimat",)` tool. Matches windows by **title substring**
   (`wmctrl -c <hedef>`), not by tracking the PID `web_ac`/`uygulama_ac`
   launched — verified this matters: `xdg-open <url>` usually hands the URL
   to an *already-running* browser via IPC and the `Popen`'d process exits
   in under a second, so PID-tracking would silently fail to close browser
   windows specifically. `wmctrl` was not installed on this board; added via
   `sudo apt install wmctrl` (2026-08-23) — a fresh board needs this too, not
   yet added to `farabi-kurulum.sh`.
2. **No way to EXIT talimat modu by voice at all.** "Öğretmen talimat
   modundan çık" got a confident "Anlaşıldı, çıkıyorum" and then *nothing
   changed* — no tool existed, so the model just said what sounded right.
   Real fix needed a way to force the live connection closed and let it
   reconnect with a fresh (non-talimat) config, since (same constraint as
   `ders_dili`) a Live connection's `system_instruction`/`tools` can't change
   mid-connection. New `talimat_modundan_cik` tool (`calisma="satirici"`,
   same shape as `shutdown_farabi`) sets `self._talimat_cikis_istendi=True`
   and, after a 1.5s delay so the confirmation sentence is heard, sets
   `ui.talimat_modu = False` and signals `self._talimat_cikis_event`. A new
   `_talimat_cikis_gozcusu()` task (registered via `tg.create_task()`,
   **not** a bare `asyncio.create_task()` — raising from inside
   `_execute_tool`/`_araclari_calistir` doesn't work, that call chain has its
   own try/except that swallows the exception, see its docstring) raises
   `_TalimatCikisi` when the event fires, which unwinds the `TaskGroup` and
   lands in `run()`'s `except Exception`. That handler now checks
   `self._talimat_cikis_istendi` **first**, before the generic
   fail_streak/backoff/quota logic — a deliberate mode exit must never be
   logged or treated as a connection error, and must reconnect *immediately*,
   not after a 3-60s backoff. **RESOLVED 2026-09-01 — `shutdown_farabi`'s
   pattern now IS the same family.** This paragraph used to say
   `shutdown_farabi`'s `_temiz_kapan`/`os._exit(0)` ended the whole process
   and couldn't be reused; that was true until the "programı açıp kapatmak
   gerekiyor" complaint (teacher had to manually restart the app between
   every lesson period, since mode/language buttons never re-enabled after
   `DERSİ BAŞLAT`) got traced to exactly this `os._exit(0)`. `_temiz_kapan`
   was renamed `_dersi_bitir` and no longer calls `os._exit` — it sets
   `self._ders_bitti_event` instead, mirroring `_TalimatCikisi` via a new
   `_DersBitti`/`_ders_bitti_gozcusu()` pair. The one real difference from
   talimat-exit stays: `_DersBitti` does **not** reconnect immediately, it
   parks the loop (`self._oturum_izni.clear()`) until the next `DERSİ
   BAŞLAT` — reconnecting instantly after "lesson ended" would just hold an
   idle connection open, the exact waste `BOSTA_KAPATMA_DK` exists to avoid.
3. **`self._ders_kipi` was a one-way ratchet — genuinely would have broken
   (2) even after building it.** The original `_build_config()` only ever
   set `self._ders_kipi = KIP_TALIMAT` when `ui.talimat_modu` was true; it
   never had a branch to set it back. Once a connection had been in talimat
   mode, `self._ders_kipi` stayed `"talimat"` forever, so the exit tool's
   forced reconnect would have rebuilt the *same* talimat config again.
   Fixed by adding `self._ders_kipi_taban` (the real, `__init__`-time
   kip from the timetable/config, never mutated) and recomputing
   `self._ders_kipi` **fresh on every `_build_config()` call**:
   `KIP_TALIMAT if ui.talimat_modu else self._ders_kipi_taban`. Covered by
   `TestTalimatModu::test_kip_iki_yonlu_calisir_tek_yonlu_mandal_degil` —
   asserts the SAME `FarabiLive` instance produces the talimat persona, then
   the normal one, then the talimat one again as `ui.talimat_modu` flips.
   Any test fixture that hand-builds a bare `FarabiLive.__new__(...)` and
   calls `_build_config()` must set `_ders_kipi_taban` too now, not just
   `_ders_kipi` (three existing fixtures needed this fix).
4. **The model guessed missing required parameters instead of asking, and
   confused local files with server-hosted textbook PDFs.** Asked to open
   "25. sayfa" with no subject named (after a `ders='fizik'` call correctly
   failed — 9-A is grade 9, only `fizik-10.pdf` exists), the model silently
   substituted `ders='matematik'` out of nowhere. Separately, "kitabın
   PDF'ini aç" was routed to `dosya_ac(hedef='matematik.pdf')`, which of
   course found nothing — textbook PDFs haven't lived on this board's disk
   since the 2026-08-14 server-taşıma (see the warning box under "Project
   layout"), `pdf_sayfa`/`kitap_sorusu` are the only way to reach them from
   here. `_TALIMAT_PERSONASI` was rewritten to say both explicitly: never
   guess a required tool parameter, ask instead; and textbook content is
   never a local file, always `pdf_sayfa`/`kitap_sorusu`, never `dosya_ac`.
   Also tightened: the model must relay what a tool call **actually
   returned**, not narrate an assumed success — the "Kapatılıyor" lie in
   (1) was as much a prompt-honesty gap as a missing-tool gap.

## 2026-08-30 - Ekran görüntüsü araçları bağlandı (kullanıcı kararı)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **RESOLVED 2026-08-30 — `ekran_goruntusu_al`/`ekrandaki_soruyu_oku` wired
in, by explicit user decision.** These two files were found already on disk
(2026-08-30, pulled onto 9-A from the server's `client/` mirror; origin
unknown, not in any commit message) but **not** registered in `kayit.py`
and missing their capture mechanism (`ui.py::_ekran_goruntusu_yakala`, the
GUI-thread slot `_screenshot_sig` fires into, did not exist — the files
would have failed every call). The user was told this reintroduces the
capability class `screen_processor.py` was removed for (root `CLAUDE.md`'s
"Gizlilik" section, "Kamera yok") and explicitly confirmed they want it
applied anyway. **What actually ships is narrower than a camera ever
was, and categorically different**: `_ekran_goruntusu_yakala` calls
`QApplication.primaryScreen().grabWindow(0)` — the board's OWN on-screen
display only (whatever `pdf_sayfa`/`show_content` is already showing),
never a camera frame, never the physical room or students. Both tools are
registered in `kayit.py` (`kip=KIP_HEPSI + (KIP_TALIMAT,)`, matching
`pdf_sayfa`/`kitap_sorusu`'s availability), dispatched in `main.py`. Saved
to `icerik/onbellek/ekran_goruntusu/` (LRU-capped at 20, same pattern as
`pdf_sayfa`'s cache) and logged via `transcript.log_line("SİSTEM", ...)`.
`ekrandaki_soruyu_oku` reuses `file_processor`'s existing `"ocr"` action
(`server/dosya.py:104`, already supported, no server change needed).
Verified end-to-end with an offscreen Qt test (`QT_QPA_PLATFORM=offscreen`)
before deploying to 9-A.

## 2026-08-30 - 9-A'da konuşma sırasında tekleme — incelendi, kök neden BULUNAMADI
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

## Reported stutter/lag during speech (9-A, 2026-08-30) — investigated, NOT root-caused

Teacher-reported "tekleme ve kasma" (stutter/hitching) while Farabi speaks.
Investigated from `logs/farabi.log` only (no live session was running —
Sunday, no school — so nothing below is a confirmed cause, only what the
static log data supports or rules out):

- **133 `Sözü kesildi` (interrupted) events** across the retained log window
  (2026-08-23 to 2026-08-29). Distribution of "çalınmamış N ses paketi
  atıldı" (unplayed packets discarded at interrupt): 72 are `0` (turn had
  already finished playing — benign, not a mid-speech cutoff), but 61 are
  non-zero and the tail is heavy — values up to 390. **Roughly half of all
  interruptions genuinely land mid-speech.** An initial theory (mic
  picking up Farabi's own voice with no echo cancellation, given 9-A's
  audio is the internal `ALC662` analog codec with no external mic detected
  in `arecord -l`/`pactl list sources`) is *plausible* given the packet
  counts, but was **not verified** — no live session to correlate an
  interrupt timestamp against an actual FARABİ-speaking window.
- **Tool-call latency is not the cause** — checked and ruled out. Slowest
  tool calls in the window: `web_search` at ~20s (expected, has its own
  budget), everything else (`pdf_sayfa`, `web_ac`, `uygulama_ac`) under 1s.
  Tool calls run off the receive loop (see "Tool dispatch" above) so
  wouldn't stutter playback even if slow.
- **Untested but mechanically plausible, not yet measured:** 9-A's board is
  an Intel i3-2330M (2011-era dual-core mobile CPU, per the school's own
  hardware sheet) running four asyncio audio loops, a 15s rolling RMS
  diagnostic, and Qt repainting a 12.7 MB `Farabi.gif` HUD animation, all on
  one process. This is the kind of load that produces exactly "az da olsa
  tekleme ve kasma" if the process occasionally can't keep the audio
  callback fed. **Not measured this session** — would need, during an
  actual live lesson: `pidstat -p $(pgrep -f 'python main.py') 2 10` (is the
  process pegging a core when it stutters), `pw-top` (XRUN count on the
  PipeWire output stream during a stutter). Do not write a cause into this
  file from this paragraph alone — it's a hypothesis to test, not a finding.

**Next step, not done:** run the two `pidstat`/`pw-top` checks above on 9-A
during a real lesson, correlated against a stutter the teacher actually
hears, before spending effort on either the mic/AEC theory or a CPU/audio-
underrun fix.

## 2026-08-31 - `yoklama_al.py` silindi (NOT: 2026-09-02'de yeniden kayıtlı olarak eklendi)
_(client/CLAUDE.md'den taşındı, 2026-09-25)_

⚠️ **`yoklama_al.py` REMOVED (2026-08-31).** Found unregistered (not in
`kayit.py`, no `ad="yoklama_al"` entry, unreachable from tool dispatch) and
shelling out to launch `tahtayoklama/yoklama.py` (a separate, sibling
project) via `subprocess.Popen` — dead, half-wired integration code, not a
capability Farabi's own actions should have. Deleted from the repo; will
disappear from 9-A on its next `farabiguncelle.sh` pull. If yoklama
integration is wanted later, it needs a real `Arac(...)` entry and an
explicit capability-boundary decision, not a resurrected copy of this file.

## 2026-10-03 - Ollama'da tek model: qwen3.8:27b
- `qwen2.5:14b` takma adı ve özel `farabi-qwen3.8:27b` (yalnızca metin Modelfile) silindi; tüm kod (saglayicilar, rag, smssistemi, dogum) düz `qwen3.8:27b` kullanıyor. Farabi SYSTEM promptu `server/ollama/farabi_sistem.txt`'e taşındı, `saglayicilar.py` sistem mesajı olmayan Ollama isteklerine ekliyor. Açılış ön yükleme betiği (`/usr/local/bin/farabi-ollama-onyukle.sh`) da qwen3.8:27b'ye çevrildi.
- Neden: kullanıcı kararı — keep-alive tek model, başka model yok. Farklı model adı istemek kalıcı modeli GPU'dan atıyordu (dogum.py testinde görüldü). mmproj'lu düz qwen3.8:27b şu an %100 GPU'ya sığıyor (RAG kaldırıldığı için).

## 2026-10-03 - Ollama bağlam penceresi 8k → 16k
- `OLLAMA_CONTEXT_LENGTH` 16384 yapıldı (`/etc/systemd/system/ollama.service`, yedek `ollama.service.2026-10-03-8k`). 32k denendi: %11 CPU'ya taştı, geri alındı. 16k'da %6 CPU / %94 GPU, ~27 tok/s.
- Neden: Farabi sistem promptu tek başına 2.863 token; `belge_ozet` (Ollama zincirde 1.) 40.000 karaktere (~13k token) kadar girdi gönderiyor, 8k'da Ollama girdiyi sessizce kesiyordu. Not: GPU1'de ~4 GB boş kalırken katmanlar CPU'ya düşüyor — dağılım dengesiz; ileride num_gpu veya OLLAMA_FLASH_ATTENTION=1 + OLLAMA_KV_CACHE_TYPE=q8_0 ile tamamen GPU'ya alınabilir (test edilmedi). 16k, 40k karakterlik belgenin tamamına yine yetmez.

## 2026-10-03 - Ollama KV cache q8_0 (16k bağlam %100 GPU)
- `ollama.service.d/zz-kvtest.conf`: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`. KV 1024→544 MiB, 66/66 katman GPU'da (f16'da 65/66, %6 CPU). Flash attention zaten `auto` ile açıktı — tek değişken KV tipi. Geri almak: dosyayı sil + daemon-reload + restart.
- Neden / kanıt: /mnt/farabi-data/farabi/ebys'teki 10 resmî yazı, sabit Türkçe prompt + Farabi sistem promptu, temperature 0, seed 42. f16 iki koşuda 10/10 birebir aynı (gürültü tabanı 0). q8_0 vs f16: istenen işlem 10/10 eşdeğer, tarih/sayı aktarımı ve eksikleri birebir aynı, cevap-gerekli kararı 9/9 aynı, uydurma talimat yok; üretim ~%10 hızlı. Sınır: yalnız 2 yazı 8k'yı aştı (048: 9,1k, 140: 14,3k token).
- Gizlilik ayrımı (kullanıcı kararı): resmî yazılar (EBYS, gizlilik maddeli) asla buluta gitmez — yalnızca Müdür PC'deki EBYS botundan geçer, botta bulut sağlayıcı yok (Ollama hatasında yalnızca uyarı loglar). Tahtadan yüklenen eğitim belgeleri (`belge_ozet`), ders kitapları (`kitap_ozet`, gece toplu işlenebilir), görseller ve formül/matematik işleri buluta gidebilir — `belge_ozet` bulut yedeği bilerek korunur. Not: yerel çağrılar 17-58 sn sürdüğünden 30 sn istemci zaman aşımıyla uzun belgeler sık sık buluta düşer.
- EBYS botu (Müdür PC, `resmi_yazi_analiz.py:31`) silinen `farabi-qwen3.8:27b`'yi çağırıyor ve `num_ctx: 8192` gönderiyor (`ebys_akilli_evrak_asistani.py:79`) — `qwen3.8:27b` ve 16384'e güncellenmeli, yoksa özet üretmez / modeli her istekte yeniden yükletir.

## 2026-10-03 - Yoklama panosu: ilk açılışta yalnızca yoklama + Atos Yapay Zeka butonu
- Kenar çubuğu mini sistem durumu rozeti artık tıklanınca (veya /sistem-durumu sayfasında) yükleniyor; ana sayfa açılışında yalnızca `/api/durum` çağrılıyor. Kenar çubuğuna Open WebUI (port 80) için "Atos Yapay Zeka" bağlantısı eklendi (host istekten alınıyor). Rapor: `docs/dashboard-inceleme-2026-10-03.md`.
- Neden: kullanıcı isteği — ilk açılışta yalnızca yoklama, diğer servisler tıklandıkça. Arka plan toplayıcısı (15 sn) bilinçli olarak dokunulmadı (2026-09-25 kararı, trend grafiği); talebe bağlama önerisi raporda onay bekliyor.

## 2026-10-03 - chunk_idari iptali kaldırıldı (Open WebUI personaları)
- 2026-08-31'deki "`/api/idari/*` ve `chunk_idari` kalıcı iptal" kararı kaldırıldı; CLAUDE.md'den "Şu An Yapılmayacaklar" maddesi silindi, "Veri Yerleşimi" güncellendi.
- Neden: kullanıcı kararı — Open WebUI'de Farabi personaları (branş öğretmenleri + Müdür Yardımcısı) Farabi RAG'ını (pgvector, bge-m3 + reranker) kullanacak; Müdür Yardımcısı modunun mevzuatı (`/mnt/farabi-data/farabi/mudur/`) de aynı arama altyapısına `chunk_idari` olarak girecek. Alternatif (mevzuatı Open WebUI'nin kendi bilgi tabanına koymak) reddedildi: tek arama altyapısı tercih edildi.

## 2026-10-03 - Open WebUI Farabi modları devrede; bge-m3 CPU'da, rerank yok
- CPU ölçümü (biyoloji-9, 40 soru, 24 thread fp32): tam rerank (20 aday) recall@4 32/35 ama medyan 9,91 sn (max_length=512: 10,53 sn); rerank 8 aday 31/35 3,53 sn; vektör-only 28/35 ~0,13 sn. **Kullanıcı kararı C: yeniden sıralama yok.** `RAG_AKTIF = True`, `RERANK_YUKLE = False` (yukarıdaki "RAG kapalı" kararının yerine geçer); zayıf eşiği kosinüs 0,55 (`ESIK_BENZERLIK`, 2026-08-11 ölçümü). Tahta `question` ucu reranker'sız çalışmadığı için eskisi gibi `hata` döner.
- `/api/webui/ara` + `farabi_kaynak` filtresi + 14 mod + `chunk_idari` (20 belge, 1485 parça, OCR'lı sayfalar dahil; yükleme CPU'da 15 dk 5 sn). Uçtan uca (Open WebUI, 2026-10-03): farabi-kimya ilk kelime 5,3 sn (kaynak etiketli, düşünme kapalı); farabi-mudur-yrd 1,1 sn; farabi-almanca 1,0 sn (kaynaksız). `/api/webui/ara` canlı: kitap kapsamları 0,12-0,23 sn, idari ~0,1 sn. Sohbetten think açılınca model düşünüyor (ilk kelime 11,2 sn).
- Düşünme varsayılanı model `params`'a değil filtreye konuldu: Open WebUI model parametrelerini sohbet ayarlarının üzerine yazıyor (`utils/payload.py::apply_model_params_to_body`), yoksa sohbetteki `think` düğmesi çalışmazdı. Ayrıntı: Open WebUI filtrelerden ÖNCE `params`'ı `options`'a taşır ve Ollama'ya yalnızca `options.think`'i iletir (`utils/payload.py::convert_payload_openai_to_ollama`); filtre bu yüzden `options["think"]` yazar, kullanıcı seçimini (`options.think`/`params.think`/`think`) ezmez.
- Filtre görev isteklerini (`__metadata__.task`) atlar — başlık üretimi kitap araması tetiklemesin. HTTP çağrısı `asyncio.to_thread` içinde — Open WebUI olay döngüsü donmasın.
- Open WebUI 0.11 bir modu kullanabilmek için alttaki taban modele (`qwen3.8:27b`) okuma izni ister; ham model bu yüzden iki gruba okuma izniyle ve `meta.hidden=True` ile (yalnızca seçicide gizli) kurulur — öğretmenler `/api/models`'ta görebilir.
- Hesaplar: ortak `ogretmen@farabi.local`, `idare@farabi.local` ve tahtalar için yönetici olmayan `tahta@farabi.local` (Öğretmenler grubu). Şifreler yalnızca `openwebui/.env`'de (gitignore'lu). Ortak hesap şifreleri kullanıcı kararıyla zayıf; İdare için güçlü şifre önerildi.
- Mevzuat klasörü: 3 yeni belge eklendi (Sosyal Etkinlikler, Okul-Aile Birliği, 657 güncel); eski `657_devlet_memurlari_kanunu.pdf` hariç tutuldu (silinmedi); "OKUL GÜVENLİĞİ AYLIK RAPORLAR" alt klasörü bilinçli dışarıda.
- İşletim: büyük yeniden yüklemeler CPU'yu doyurur (Tctl 97°C görüldü) → `taskset -c 6-11` ya da torch thread sınırı; `idari_yukle.py` `HF_HUB_OFFLINE=1` ile koşulmalı; şema `postgres` ile stdin'den uygulanır (`sudo -u postgres psql -d farabi -v ON_ERROR_STOP=1 < server/schema_idari.sql`, postgres `/home/ata`'yı okuyamaz).
- Open WebUI DB yedeği: `/home/ata/yedek-openwebui/webui-2026-10-03.db` (`kur.py`'nin ilk çalıştırılmasından önce).
- Neden: kullanıcı kararları (spec §1). Geri dönüş: `RAG_AKTIF=False` + restart (Open WebUI modları aramasız çalışmaya devam eder).
- Düzeltme (final inceleme): üstteki Open WebUI teması kaydındaki "Farabi" yeniden adlandırması ve `user:*` herkese açık erişim artık geçerli değil — `kur.py` ham modeli `qwen3.8:27b` adına geri alır, `meta.hidden` ile gizler ve erişim izinlerini iki gruba okuma olarak DEĞİŞTİRİR (Open WebUI `set_access_grants` ekleme değil değiştirme yapar).
- Düzeltme: yukarıdaki `chunk_idari` kaydındaki "bge-m3 + reranker" ifadesi eskidir — rerank sonradan kullanıcı kararı C ile bırakıldı (yalnızca bge-m3 vektör araması).
- Düzeltme: 2026-10-03 tarihli ilk "RAG kapalı" Ollama kaydı bu kayıtla (Open WebUI modları, `RAG_AKTIF = True`, rerank yok) geçersiz kılındı.
- Başlık üretimi düşünmesin: Open WebUI görev yolunda Function inlet'i çalışmaz, bu yüzden `farabi_think` uygulanmaz ve Ollama varsayılanı (medium) başlığı yavaşlatır. `kur.py` gizli `farabi-gorev` modelini (`params.think=False`, `routers/ollama.py` bunu payload köküne taşır) kurar ve `TASK_MODEL` olarak atar.

## 2026-10-04 - 5 yeni kitap RAG'a eklendi (Din 10/11, Biyoloji 11, Edebiyat 12, Matematik 12); Din 9 temizliği
- Antigravity ajanı `benchmark/embed_kitap.py` ile yeni kitapları yükledi; kod değişikliği yapmadı, eski 25 kitap sağlam kaldı. Ancak: (1) `din-kulturu-ve-ahlak-bilgisi-9sinif-ders-kitabi_…pdf` adlı yüklemeyi "Din 9 yeni baskı" sanıp `din-kulturu-ve-ahlak-bilgisi-9_2.pdf` olarak Din 9'a ekledi — künyesi **10. Sınıf** (Devlet Kitapları 2026, Fatih Çelikel vd.). `webui.py::_kitaplar` aynı (sınıf, ders) iki kitabı cilt sandığı için kaynaklar "Din 9 (1. cilt)/(2. cilt)" diye karıştı. Kullanıcı kararı: Şimşek vd. yazarlı eski Din 9 (kitap 18) kalır; yanlış kayıt (kitap 32) silindi, dosya `din-kulturu-ve-ahlak-bilgisi-10.pdf` adıyla Din 10 olarak yüklendi (kitap 37, hariç 1-12,171-184). (2) `taskset` kullanmadı (Tctl 96,8°C) — çalışan süreçler sonradan 6-11 çekirdeğe kısıtlandı. (3) Matematik 12 yüklemesi antigravity oturumu kapanınca 64 parçada yarım kaldı (`indekslendi_at` NULL, yarım veri aramada canlıydı) — yeniden koşuldu, 612 parça (kitap 36); `indekslendi_at IS NULL` kitap kalmadı.
- `icerik/kitaplar.json`'a 5 kitap `kitap_index.py`'nin `indexle`/`kitap_kimligi`'siyle tek tek eklendi (klasör modu ham kopyaları da mükerrer eklerdi; yedek `kitaplar.json.bak.20261004_0514`). Otomatik bölüm tespiti Din 10 (ad = "Sonu Ölçme…"), Matematik 12 (s.1-86 eksik) ve Edebiyat 12'de (çakışan aralıklar) bozuktu; bu üçünün bölümleri İçindekiler'den elle yazıldı (PDF = basılı +1 Mat/Edb, +0 Din 10).
- Din 9 "Kader" → "bölüm eşleşmedi": `ders_icerigi` konuyu yalnızca ünite adıyla eşliyor, kader 2. Ünite (İnanç Esasları) alt başlığı. `icerik/eslemeler/din-kulturu-ve-ahlak-bilgisi-9.json` yazıldı (ünite kapakları 10/44/80/116/150, temalar = İçindekiler + iman esası ara başlıkları; eşleştirici kök bulmadığı için "Kader"/"Kaza ve Kader" ayrıca). Yan etki: sınıfsız istekte (fenlab) "Kader" Din 9'a gider — elle eşlemeler her zaman önce bakılır.
- Neden / ders: yeni kitap yüklemeden önce künyeden sınıfı doğrula, büyük yüklemede `taskset -c 6-11`, yükleme sonrası `indekslendi_at IS NULL` kontrol et. Kalan iş: 40 soruluk `rag_test.py` ölçümü tekrarlanmalı. Ham yükleme kopyaları (5 adet, md5 ile birebir aynı, DB/kitaplar.json referansı yok, ~430 MB) kullanıcı onayıyla silindi; `kitaplar/` = 30 PDF, mükerrer yok.

## 2026-10-04 - Dashboard "Sunucular" sekmesi + okul-sunucu proxy anahtarı
- `/sunucular` (sunucular.py): farabi/bilgehan/debian donanım, GPU, NTP, kritik servis ve proxy durumu + Chatterbox `/saglik/detay` kartı. Proxy aç/kapat düğmesi yalnızca farabi ve bilgehan'da (sayfa içi onay, `uzaktan_denetim`'e yazılır).
- Tek betik `server/okul-sunucu/okul-sunucu` → `/usr/local/sbin/okul-sunucu {durum|proxy-ac|proxy-kapat}` üç makinede kurulu. Proxy = profile.d + apt + (varsa) Ollama `proxy.conf`; GitHub SSH ProxyCommand kapsam dışı (hep açık). Proxy URL'si (parolalı) repoda DEĞİL: hedefte `/etc/okul-sunucu.conf` (root 600) — repo public.
- Ders saatinde (08:00–17:00 TR, hafta içi) Ollama restart'ı 17:05'e tek seferlik systemd timer'ıyla (`okul-proxy-ollama-restart`) ertelenir. `proxy_kontrol.sh` arayüzü (EBYS botu) korundu, artık bu betiğe sarmalayıcı.
- Toplama istek üzerine + 60 sn önbellek (sistem_durumu'ndaki sürekli döngü bilerek yok): sekme kapalıyken hedeflerin auth loguna dakikada bir SSH girişi düşmesin.
- Tuzak: yeni bir router kendi `Jinja2Templates`'ini kuruyorsa `gun_adi_buyuk` global'ini de eklemeli (taban.html kullanıyor) — yoksa sayfa 500 verir; `test_sunucular.test_sayfa_render_edilir` bunu yakalar.
- Bekleyen: Farabi→debian/bilgehan `~/.ssh/sunucu_izleme` anahtarı (command= kısıtlı) henüz kurulmadı — kurulana kadar o iki kart "anahtar kurulmamış" gösterir, bilgehan proxy düğmesi çalışmaz.

## 2026-10-04 - Open WebUI RAG altyapısı düzeltildi + Dashboard 8010 modern tasarımı ve hızlandırması
- **Open WebUI RAG Arama ve Persona İyileştirmesi:**
  - `server/rag.py` ve `server/webui.py`: Aday havuzu `k=15`'e çıkarıldı. Kanun ve yönetmelik maddeleri (657, KHK vb.) için pgvector'e hibrit ILIKE anahtar kelime eşleştirmesi eklendi. Vektör aday eşiği `esik=0.38`'e indirildi.
  - `server/webui.py`: Bilgehan yeniden sıralayıcı (reranker) eşiği `ESIK_RERANK_WEBUI = 0.25` olarak ayarlandı (önceki 0.50 eşiği mevzuat parçalarını eliyordu).
  - `openwebui/farabi_filtre.py` & promptlar (`cekirdek.md`, `genel.md`, `mudur_yrd.md`): Farabi'nin kullanıcıyı (öğretmen / müdür / müdür yardımcısı) tanıması sağlandı. Farabi artık tam yetkili dijital meslektaş olarak yanıt veriyor; "okul idaresine sor", "müdürlüğe git" ya da "RAG sisteminde bulunamadı" gibi kalıplar yasaklandı. `openwebui/kur.py` ile tüm modeller senkronize edildi.
- **Yoklama Dashboard (`http://farabi.local:8010/`) Geç Yüklenme Çözümü:**
  - `/admin/uzaktan` sayfasındaki senkron SSH bloklaması (3.3 - 5.6 sn) kaldırıldı: 45 saniyelik thread-safe durum önbelleği ve asenkron istemci uç noktası (`/admin/uzaktan/api/durumlar`) eklendi. Sayfa açılışı 3.3 saniyeden **14 milisaniyeye (200x hızlanma)** indi. İstemci taraflı iskelet yükleyici ile durumlar arka planda dolduruluyor.
- **Tüm Dashboardlar İçin Modern Web Tasarımı (`tahtayoklama/dashboard/`):**
  - `pano.css`: Klasik (slate/indigo), Koyu (deep navy/slate) ve Yumuşak (warm paper) temalar için modern renk paleti, çok katmanlı kart gölgeleri, pürüzsüz kaydırma çubukları (custom scrollbar) ve duyarlı arayüz tasarlandı.
  - `pano.html`: Sayfa üstüne 4 adet KPI özet kartı eklendi (Aktif Sınıflar, Eksiksiz Dersler, Devamsız/İzinli, Bekleyen Yoklama). Yoklama durumu değiştikçe ve periyodik yenilemelerde bu sayaçlar anlık olarak güncelleniyor.
  - Aktif ders saati vurgusu eklendi (`.aktif-ders-sutun`, `.aktif-ders-rozet`): Zil saatlerine göre o an işlenen ders tablosunda otomatik vurgulanıyor.
  - Durum rozetleri (`.pill`), iskelet yükleme ışıltısı (`@keyframes iskelet-isilti`), tablo satır geçişleri ve uzaktan yönetim butonları modernize edildi.
  - Tüm test paketleri (190 server, 148 openwebui, 114 dashboard, 130 smssistemi — toplam 582 test) eksiksiz geçti.

## 2026-10-05 - WebUI RAG: kitap/mevzuat ayrı rerank eşiği, zayıf notu, takip sorusu bağlamı
- `server/webui.py`: rerank eşiği kaynağa göre — ders kitabı 0.10 (`ESIK_RERANK_WEBUI_EGITIM`), mevzuat 0.25. `farabi_filtre.py`: `ZAYIF_NOTU` artık modele "kaynak bulunamadı" demiyor (model "belgelerde bulamadım" diye açıyordu), uydurma madde/sayfa yasağı korundu; kısa (≤8 kelime) takip mesajlarında RAG sorgusuna önceki kullanıcı mesajı eklenir (`arama_sorgusu`). Arena: `sinif_duzeyi_coz` — fenlab = 12. sınıf (kullanıcı kararı).
- Neden: ders kitabı sorgularında reranker skorları düşük (12. sınıf logaritma 0.149) olduğu için gerçek parçalar eleniyordu; canlı doğrulamada logaritma/fotosentez/mazeret izni ok, kitapta olmayan mitoz doğru biçimde zayıf. Think ayarına dokunulmadı (gecikme 2-3x artardı, derin mod zaten var).

## 2026-10-05 - Oyunlar için soru_havuzu veritabanı (yerel Ollama üretir, AGY tek seferde denetler)
- Ayrı PostgreSQL DB `soru_havuzu` (paket `soruhavuzu/`, plan `docs/superpowers/plans/2026-10-05-soru-havuzu.md`). Kaynaklar: 30 kitap (`chunk_egitim`, ~1800 karakterlik sayfa grupları → 7508 birim), kazanım testleri (201 sayfa), YKS çıkmış (1244 sayfa). Üretim yalnızca yerel qwen3.8:27b (`think:false`, `format:json`); `soru-havuzu-uret.timer` hafta içi 17:15 / hafta sonu 08:00 TR başlatır, hafta içi 07:30–17:05 arası kendiliğinden durur, kaldığı yerden devam eder. Kopyalar bilgehan bge-m3 ile (kosinüs ≥ 0.92) elenir. Tüm birimler bitince AGY (`agy -p --json-schema --mode plan`) tüm `uretildi` soruları TEK çalıştırmada 100'lük paketlerle denetler (kullanıcı kararı). Arena (`havuz.jeopardy_seti`) ve HexaFetih (`havuz.petek_sorulari`; artık sınıf düzeyli, petek başına farklı soru) YALNIZCA `onayli` soruları kullanır (kullanıcı kararı: denetlenmemiş soru oyunlara gitmez); yoksa eski akış.
- Neden: canlı 16 soruluk üretim 45–65 sn sürüyordu, hazır havuz 9. sınıfa kilitliydi, Hexa'da sınıf düzeyi ve soru çeşitliliği yoktu. İstem dersleri: model "tabloya göre" atıflı sorular yazıyordu (öğrenci metni görmüyor) → atıf yasağı + süzgeç; içindekiler sayfasından "hangi bölümde" soruları → konu bilgisi kuralı; istemdeki açık `{"sorular": []}` örneği modeli bilgi içeren sayfaları da atlamaya itti → kaldırıldı.
- Bilinen açık: YKS ve kazanım PDF sayfalarında cevap anahtarı çoğunlukla aynı sayfada değil, model "cevap kesin değilse atla" kuralıyla 0 soru dönebiliyor; adından sınıfı çözülemeyen ~100 kazanım PDF'i kataloğa alınmadı.

## 2026-10-05 - İdari kayıtlar yalnızca İdare'ye; xlsx desteği
- `server/webui.py`: "genel" ve ders kapsamları artık YALNIZCA ders kitaplarında arar; idari belgeler (mevzuat + öğrenci bilgi formu, personel listesi, RPDH planı gibi okul kayıtları) yalnızca "idari" ve yeni "hepsi" (kitap + idari) kapsamlarından aranır. `farabi-mudur-yrd` modu (yalnızca İdare grubu) "hepsi"ye alındı. Öğretmen ve Farabi Tahta hesaplarının kullandığı farabi/farabi-derin/branş modları idari kayıtlara ulaşamaz (canlı doğrulandı: "genel" ile mazeret izni → zayif, öğrenci formu görünmez; "hepsi" ile ikisi de geliyor). `idari_yukle.py` artık .xlsx de okuyor (çalışma sayfası başına bir "sayfa"); 3 yeni belge yüklendi.
- Neden (kullanıcı kararı): mudur/ klasörüne hassas öğrenci/personel verisi konuyor; Farabi Tahta hesabı Öğretmenler grubunda ve sınıf ekranında görünüyor. Ders programı/öğrenci bilgisi aracı (farabi_okul) bundan bağımsız, tahtaya zaten kapalı.
- Not: AGY'nin `agy/rag-iyilestirme` dalı bu değişiklikten ÖNCE ayrıldı; birleştirirken webui.py kapsam satırlarına dikkat.

## 2026-10-05 - Open WebUI → "Atos"; belge kalıcı kayıt aracı; gece idari taraması; SMS/hatırlatma aracı; ortak hesaplar kapatıldı
- Ad/logo: `webui-tema/atos-ad.conf` drop-in (WEBUI_NAME=Atos) + `atos_ad_yama.sh` (env.py'deki " (Open WebUI)" ekini her açılışta kaldırır; lisans ≤50 kullanıcıda izinli). Logo `webui-tema/atos_ikon_uret.py` (tema renkleri, DejaVu; kaynak kopya /mnt/farabi-data/farabi/atoslogo.png). Eski Farabi amblemi `ikon_uret.py`'de duruyor.
- Belge Kalıcı Kayıt (`openwebui/farabi_belge_araci.py`, yalnızca İdare) → farabi-api `POST /api/webui/belge-kaydet` (`server/belge_arsiv.py`): dosyayı mudur/'a yazar (aynı içerik başka adla varsa ikinci kopya yok; aynı ad farklı içerik = güncelleme), yalnızca o dosya için `idari_yukle.py --dosya` çalıştırır. Neden: model "kalıcı hafızaya kaydettim" diyordu ama hiçbir şey kaydedilmiyordu (Open WebUI sohbet dosyaları yalnızca o sohbete bağlı, MiniLM ile gömülü). Çekirdek prompt: "kaydettim/SMS gönderdim/hatırlatma kurdum" yalnızca araç başarılıysa.
- Gece taraması: `farabi-idari-yukle.timer` 02:30 TR → `idari_yukle.py` (hash aynıysa atlar). Not: klasörden silinen belge DB'den kendiliğinden silinmez.
- SMS: `smssistemi/arac_api.py` (`/api/arac/*`, X-Sms-Arac-Key, `config/arac.json` gitignore'lu) + `openwebui/farabi_sms_araci.py` (yalnızca İdare). Hatırlatma ve acil SMS her zaman yönetime (Atakan Ünver, Arzu Oral — arac.json "yonetim"), hatırlatma ONAYSIZ, saat yoksa 10:00, ≤120 karakter, 30 sn'lik döngü, 6 saatten geç kalan "kacirildi". Veli SMS'i taslak (alıcı sayısı) → açık onay → gönder (taslak 30 dk; kardeş velisi tek SMS). Gönderimler mevcut `gonderimler` tablosuna (/kayitlar).
- Doğrulama sınırı: Open WebUI araçları yalnızca arayüz sohbet oturumunda sunucu tarafında yürütür; API ile (stream) model aracı doğru çağırdı (tarih 2026-10-14, saat boş) ama yürütme arayüzden test edilmeli. stream:false API çağrısında model aracı çağırmadan "kurdum ✅" dedi — prompt kuralı bu yüzden önemli.
- Ortak "Öğretmen", "İdare" ve "Farabi Tahta" hesapları kapatıldı (rol pending, silinmedi); kur.py artık hiç ortak hesap oluşturmuyor (`HESAPLAR=[]`, `KAPALI_HESAPLAR`, `hesaplari_kapat`). Atos yalnızca atakanunver1@ ve arzuoralece@ (admin) içindir; ikisi `YONETICI_EPOSTALAR` ile İdare grubuna eklenir (kullanıcı kararı). Görünen adlar: modlar "Atos"/"Atos – Derin Düşünme", "Atos Yönetim"; çekirdek prompt kimliği "Atos"; giriş sayfası alt imzası custom.css'te. Model id'leri (`farabi`, `farabi-*`) değişmedi — tarayıcıdaki sohbetler/varsayılan model kırılmasın diye.
- Ders: dış ajan (agy) testler kırılınca `git checkout openwebui/kur.py` ile commit'lenmemiş çalışmayı sildi; içerik testlerdeki diff'ten yeniden yazıldı. Dış ajan kartlarında `git checkout/restore/reset/stash` açıkça YASAK'a yazılmalı; uzun süren ajan işinden önce ara commit (wt dalında) alınmalı.

## 2026-10-05 - Farabi ısınma: CPU turbo kapalı, GPU güç sınırı 120 W
- `cpu-boost-kapali.service` (boost=0, en yüksek ~3.8 GHz) ve `gpu-guc-siniri.service` (`nvidia-smi -pm 1 -pl 120`, 170 W'tan; ollama'dan önce) — ikisi de `/etc/systemd/system/`, enabled. Geri almak: `systemctl disable --now <servis>` + boost=1 / `nvidia-smi -pl 170`.
- Neden: soru havuzu üretimi altında CPU Tctl 95°C (3900X'in sınırı), GPU1 84°C ve ~48 dk sıcaklık nedeniyle yavaşlamış. Hemen sonra CPU 88.6°C, GPU 72/78°C. Kök neden donanımda: GPU0 (04:00.0) 90+ W'ta fan %0 gösteriyor (fan arızası şüphesi), kasa fanlarından yalnızca 2'si dönüyor — fiziksel kontrol gerekli.

## 2026-10-05 - Soru havuzu denetçisi: AGY yanıt ayrıştırma + ders dışı soru kuralı
- `soruhavuzu/denetci.py::yaniti_coz` önce `structured_output` alanını okur; yoksa `response`'taki ilk JSON nesnesini `raw_decode` ile alır.
- Neden: AGY `response`'a JSON'u iki kez art arda yazıyordu ("```json{..}```{..}") → `json.loads` "Extra data" hatası verdi, 20 kararın 20'si sessizce düştü.
- Denetçi istemine "ders dışı / saçma soru reddedilir" kuralı eklendi: eski istemle matematik kitabındaki problem hikâyesinden çıkan "Millî Ağaçlandırma Günü hangi tarih" sorusu "metinle uyumlu" diye onaylanıyordu.
- Üretici (`uretici.py`): `num_predict: 2048` (16 hatalı birimin 3'ü modelin 8k+ token tekrar döngüsüyle 180 sn zaman aşımı) + Ollama 500'ünde tek tekrar (13 birim; Ollama logunda hata nedeni yok, aynı birim tekrar denenince geçiyor).

## 2026-10-10 - Dijital Okul platformu (okul/, port 9090)
- Bağımsız FastAPI + Jinja2 + SQLite servis; devamsızlık yoklama_pano.db'den, kazanım sonuçları/soru havuzu Postgres soru_havuzu'ndan, ders programı mudur/ders_programi.json'dan SALT-OKUNUR ve her istekte okunur (kopyalanmaz). Veli girişi SMS kodu (smssistemi'ye eklenen /api/arac/kod-sms, telefon başına dk 1 / saat 5); diğerleri şifre, ilk şifre ad+123 ve zorunlu değişim; oturum 1 yıl kayan çerez (kullanıcı kararı: güvenlik kullanıcıyı kaçırmamalı).
- Tahta yoklaması gelmeyenleri isimle tutuyor: isim→(sınıf, no)→okul_no eşleniyor; aynı sınıfta aynı isim ya da eşleşmeyen isim varsa veliye gösterilmiyor, yönetici /yonetici/eslesmeyen'de görüyor (yanlış çocuğa devamsızlık yazmamak için).
- Spec: docs/superpowers/specs/2026-10-10-dijital-okul-design.md. Dış erişim Cloudflare Tunnel smual.app (cloudflared edge trafiği okul filtresi yüzünden Müdür PC proxy'si üzerinden, bkz. llm-cluster-wiki nodes/farabi.md).
