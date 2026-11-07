# smssistemi

Okul idaresinin öğrenci/veli/personele toplu ve kişiselleştirilmiş SMS gönderdiği FastAPI servisi (Müdür PC'deki Tkinter `sms sistemi`nin web eşdeğeri; Huawei HiLink modem üzerinden). Farabi sunucusunda `farabi-smssistemi.service`, port 8020, `smssistemi/` dizini.
- Tasarım gerekçesi: `../docs/superpowers/specs/2026-09-19-smssistemi-design.md` (kod yorumları buna işaret eder). Kararlar: kök `DECISIONS.md`.

## Komutlar
- Test (tests/ dizini YOK, düz `test_*.py` proje kökünde): `venv/bin/python -m pytest -q`; tek dosya `... pytest test_db.py -q`; tek test `... pytest test_db.py::test_semayi_kur_ve_gonderim_kaydet -q`.
- İlk kurulum: `python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt`; ortak giriş şifresi `venv/bin/python scripts/sifre_belirle.py` (-> `config/gizli.json`, zorunlu).
- Geliştirmede elle: `venv/bin/uvicorn app:app --reload --port 8020`. DİKKAT: lifespan otomasyon döngüsünü de başlatır.
- Üretim: `sudo systemctl status|restart farabi-smssistemi`; log `journalctl -u farabi-smssistemi.service`. Canlı üretim, kod restart'a kadar yayına girmez.
- Lint: `../.venv-tools/bin/ruff check <dokunduğun dosya>` (taban 40 bulgu, farkı oku; F8xx öncelik, toplu otomatik düzeltme yok).
- ⚠️ `test_otomasyon*.py` gitignore'lu `config/modem.json`'a bağımlı; worktree'de 4 test düşer (ana kopyada koş ya da `config/`'e geçici symlink).
- Bir kerelik veri aktarım betikleri (`scripts/`): `--kuru-calistir` destekleyenlerde önce onu çalıştır (`dogum_ice_aktar.py`).
- Test deseni: DB testleri gerçek SQLite dosyası kullanır, `tmp_path` + `monkeypatch.setattr(db, "DB_YOLU", ...)` ile izole; `db.py`'ye sorgu eklerken koru. `test_<modül>.py` saf mantık, `test_<modül>_app.py` route. Test telefonları sahte (`0555…`); gerçek numara teste yazılmaz (public repo).

## Okuma/gizlilik
- `config/gizli.json`, `config/modem.json`, `config/sso.json`, `config/arac.json`, `veri/` gitignore'lu: ASLA okuma/commit etme.
- `mudur/SINIF/` ve `velitelefon/` kişisel veri: okuma.

## Mimari
```
Farabi :8020 (FastAPI) --HTTP proxy (8080)--> Müdür PC WifiHttpProxy.exe --> Huawei modem 192.168.8.1:80
```
- Farabi modeme gerçek IP'siyle (`config/modem.json::modem_ip`) konuşur, proxy yalnız taşır (`proxy_host/port/user/pass`). Eski `host`/`port` alanları okunmaz.
- ⚠️ `WifiHttpProxy.exe` Müdür PC'de servis DEĞİL, elle çalıştırılan batch+exe; PC yeniden başlarsa kendiliğinden kalkmaz (kalıcılaştırılmadı).
- **Kasıtlı bağımsız:** `tahtayoklama/dashboard` ile kod/DB paylaşımı yok; `auth.py`/`db.py` dashboard'dakilerin satır satır bağımsız kopyasıdır (biri değişince diğeri güncellenmez, bilinçli). Bağ: pano menü linkleri + HMAC SSO (`/sms-git`, `/dogum`, `/otomasyon-git` -> `/sso?t=..&s=..`, token 30 sn, anahtar `config/sso.json`).
- **TEK İSTİSNA:** `yoklama_kaynak.py` panonun `tahtayoklama/dashboard/veri/yoklama_pano.db`'sini `mode=ro` doğrudan okur (kullanıcılar: `yoklama_mantik.py` ve `otomasyon.py`). Panonun şemasını bilen tek modül; HTTP+HMAC'e geçilirse yalnız `gunun_satirlari` gövdesi değişir. ⚠️ Panonun `yoklama_onbellek` şeması değişirse sessizce kırılır; `test_yoklama_mantik.py::_PANO_SEMA` o şemanın kopyası, birlikte güncelle.
- `db.py`: SQLite `veri/smssistemi.db`. `baglanti()` her çağrıda yeni bağlantı (WAL); her route kendi bağlantısını açıp `finally`'de kapatır, paylaşılmaz. Tablolar: `gonderimler` (`gonderim_id` ile gruplu), `oturumlar`, `siniflar` (9-A..12-B), `kisiler`, `ayarlar`, `otomasyon_kurallari`; `veli_taslaklari`, `kisisel_taslaklari` `arac_api.py`'de oluşturulur.
  - `kisiler`: ad_soyad, telefon (boş olabilir), sinif_id, tur ('ogrenci'|'veli'|'personel'), ogrenci_kisi_id (yalnız veliler; nullable FK), dogum_tarihi (ISO), okul_no (INTEGER), veli_rol.
- `auth.py`: tek ortak şifre, scrypt hash `config/gizli.json`'da; oturum cookie'si `oturumlar` tablosundaki token (JWT değil).
- `gonderim.py`: saf fonksiyonlar (ağ/DB yok): telefon normalizasyon/doğrulama/CSV. Yalnız `05XXXXXXXXX` ve `+905XXXXXXXXX` geçerli. Türkçe karakter -> UCS2, ASCII -> 7-bit (`gonderim.is_ascii`).
- `sms_gonderici.py`: `huawei_lte_api` senkron; `toplu_gonder` `durdur_bayragi` (Event) ile iptal edilebilir döngü; `app.py::_gonderim_calistir` daemon `threading.Thread`'de koşar; `/durum/{id}` sayfası `/api/durum/{id}`'yi poll eder. `_baglan` her denemede taze bağlantı + gerçek API çağrısıyla doğrular (8 deneme). `_proxy_session` -> `_TekSeferlikSession`: WifiHttpProxy TCP bağlantısı başına tek istek işleyip kapattığı için her istekten sonra adapter havuzu kapatılır (yoksa `ConnectionReset`/`ReadTimeout`).
- `app.py` route grupları: giriş/SSO (`/giris`, `/sso`, `/cikis`); gönderim (`/`, `/gonder`, `/durum/{id}`, `/api/durum/{id}`, `/durdur/{id}`, `/tekrar-gonder/{id}`, `/kayitlar`, `/api/mesaj-duzelt`); rehber (`/rehber`, `/rehber/kisi|sinif/...` CRUD, `/rehber/yukle`, `/api/rehber/kisiler`); `/yoklama-sms*`; `/otomasyon*` + `/api/otomasyon/durum`; `/dogum-gunleri*`. İş mantığı saf modüllerde: `yoklama_mantik.py`, `otomasyon.py`, `dogum_mantik.py`, `dogum_sms.py`, `gonderim.py`. Ayrıca `arac_api.py`, `panel_api.py`, `rehber_api.py`, `veli_mesaj.py`.
- Loglama: `app.py::log_ayarla()` yalnız `smssistemi.*` logger ağacını INFO'da stderr'e (-> journal) bağlar, kök logger'a dokunmaz (test `test_log_ayari.py`). Otomasyonun kendiliğinden çalıştığının kanıtı: journal "tetikleniyor" satırı + `otomasyon_ilk_ders_son_sonuc.tetikleyen == "otomatik_zamanlayici"`.
- Gönderim: `gonder.html` iki panelli (sağda sınıf+tür filtreli kişi listesi, solda alıcılar + serbest textarea/CSV; panel seçimi önceliklidir). Kişiselleştirme: `{isim}` (alıcı), `{ogrenci_adi}` (veli için bağlı öğrenci, öğrenci için kendisi). `POST /api/mesaj-duzelt` Ollama `127.0.0.1:11434` `farabi` takma adıyla taslağı resmi okul SMS'ine çevirir, yer tutucuları korur.

## Yoklama SMS (`/yoklama-sms`, `yoklama_mantik.py`)
- Bugün devamsız öğrencileri + veli telefonları + şablonu listeler; kullanıcı gözden geçirip gönderir. **Otomatik/zamanlanmış gönderim YOK** (kullanıcı kararı). Gönderim yeni yol açmaz: seçili veli id'leri mevcut `POST /gonder`'e gider.
- Devamsız = bugün en az N derste yok, varsayılan N=4, sayfadan değişir (1. derse bakmak geç gelen öğrencinin velisine yanlış SMS gönderirdi).
- ⚠️ Yoklaması alınmamış/tahtası ulaşılamaz sınıf listeye GİRMEZ, sebebiyle ayrı uyarı kutusunda gösterilir. Panonun `yoklayici.py` satırı `alindi` olmayan her satıra boş isim dizisi yazar; "kimse yok" ile "yoklama alınmadı" ayrılmazsa heartbeat kopmasında tüm sınıfın velisine "okula gelmedi" SMS'i giderdi (12-A, 2026-09-22).
- İzinli ders "yok" sayılmaz; gün içinde izinli öğrenci varsayılan seçili gelmez. Velisi/telefonu yok -> "Veli telefonu yoktur" etiketiyle listede KALIR, gönderimde pas geçilir (sessizce düşürülmez).
- İsim eşleştirme sınıf kapsamlı; isim başka sınıfta bulunursa SMS gönderilmez, sebep satırda yazılır (canlıda: panoda 11-A, rehberde 11-B).
- Şablon `ayarlar.yoklama_sms_sablonu`, yer tutucular `{isim}`/`{ogrenci_adi}`. Varsayılan metin "...bugün derslere katılmamıştır. Bilginize." ⚠️ "okula gelmemiştir" DEĞİL (bilinçli: eşik kısmi devamsızlığı da kapsar, "okula gelmedi" yanlış bilgi olur).
- **Geçmiş tarihte gönderim KAPALI** (yalnız inceleme): mesaj "bugün" der, eski listeyle veliye yanlış gün bildirilirdi.
- Veli ilişkisi: öğrencinin BİRDEN ÇOK velisi olabilir, hepsine ayrı SMS gider. Bir veli SATIRI tek `ogrenci_kisi_id` taşır; kardeşler için aynı kişi ayrı satır girilir, her çocuk için ayrı SMS. "Aynı veli" birleşik kavramı yok.

## Devamsızlık SMS otomasyonu (`otomasyon.py`, `/otomasyon`)
- Hafta içi, kural saatinde ilgili derse gelmeyen öğrencilerin anne/babasına otomatik SMS. Kurallar `otomasyon_kurallari` tablosunda (saat, ders_no UNIQUE, şablon, aktif, son_sonuc); panelden eklenir/düzenlenir/silinir, yeni kural KAPALI başlar. Kural 1 = 09:00/1. ders, kural 2 = 14:00/6. ders (`db._otomasyon_kurallari_tasi`, bayrak `otomasyon_kurallari_tasindi`; eski `otomasyon_ilk_ders_*`/`otomasyon_ogle_*` ayarları okunmaz). Panel API `ilk_ders`/`ogle` anahtarları kural 1/2'yi (silinirse null), `kurallar` hepsini gösterir.
- Fail-closed: yalnız o derste `durum == 'alindi'` olan sınıflar taranır; tahtası kapalı/yoklaması alınmamış hariç; izinli öğrenci devamsız sayılmaz.
- Tetik: kural saati + `PENCERE_DK`=10 (İstanbul saati). Arka plan: FastAPI `lifespan` içinde 30 sn'de bir `otomasyon.otomasyon_arkaplan_dongusu`; pencerede servis kapalıysa o gün çalışmaz. Döngü uvicorn sürecinin içinde: birden çok worker her biri kendi döngüsünü açar, mükerreri yalnız `…_son_tarih` ayarları engeller.
- İdempotency: günde bir kez DERS başına (`otomasyon_ders{N}_son_tarih`), kural başına değil (silinip yeniden eklenen kural aynı gün ikinci SMS atmaz). İstisna: hiç `send_sms` denenmediyse (satırlar "BAĞLANTI HATASI" önekli) son tarih yazılmaz, pencerede yeniden denenir. Koşulu "hiç başarılı yok"a genişletme: mükerrer SMS riski (DECISIONS 2026-09-28).
- Ayarlar: ilk ders/öğle şalteri `otomasyon_ilk_ders_aktif`/`otomasyon_ogle_aktif` (varsayılan '0' KAPALI). Arayüzde ayrı şablonlar, AI mesaj düzeltme (`/api/mesaj-duzelt`), canlı simülasyon/önizleme, manuel gönderim.
- ⚠️ Otomasyon `POST /gonder`'i KULLANMAZ: `otomasyon_calistir` doğrudan `sms_gonderici`'yi kendi thread'inde çağırıp satırları `gonderimler`'e yazar (kimlik `oto{ders_no}_...`). Gönderim mantığını (normalizasyon, UCS2/7-bit, kayıt formatı) değiştirirsen iki yolu da kontrol et.
- Panel API: `GET /api/panel/otomasyon-durum` (`X-Sms-Panel-Key`; `panel_api.py`) bugünkü devamsızlık SMS özeti (yalnız sayılar, `haric_sebepleri`); dashboard Bugün sayfası kartı buradan çizilir.

## Doğum günü
- `/dogum-gunleri` (yaklaşan/bugünkü panosu, personel/öğrenci filtresi, doğum tarihi düzenleme, otomatik SMS şalteri) ve `/dogum-gunleri/ice-aktar` (Excel analizi, 3 kategori). `dogum_mantik.py` yaş kuralı: 13-19 aktif öğrenci (mevcutla eşleşen onaysız bağlanır); >=20 personel adayı (varsayılan seçili, `tur='personel'`); listede olmayan -> ayrılan öğrenci adayı (varsayılan seçili DEĞİL).
- `dogum_sms.py`: hafta içi 09:30-09:40'ta `otomasyon_arkaplan_dongusu` tetikler. Gerçek gönderim için `sms_otomatik`=1 VE `dogum_sms_gercek`=1; varsayılan `dogum_sms_gercek`=0 = KURU (alıcıları sayar, `dogum_sms_son_sonuc`a yazar, SMS GÖNDERMEZ). Alıcı: telefonlu öğrenci + personel (veli ve "Bilinmeyen Sınıf" hariç, numara tekil, geçerli telefon); pazartesi hafta sonu doğanları da kapsar; 29 Şubat artık olmayan yılda 28'inde. `_CALISMA_KILIDI` devamsızlık SMS'iyle ortak (aynı anda koşmaz; meşgulse 30 sn sonra tekrar). Kimlik `dgm_...`, günlükte yalnız sayı. Mükerrer engeli `dogum_sms_son_tarih`; hiç SMS denenmediyse yazılmaz.
- Deneme: `venv/bin/python scripts/dogum_sms_test.py <telefon>` yalnız o numaraya örnek SMS atar (kayıt yazmaz). Gerçek moda geçiş: panel `/dogum-gunleri` -> Gönderim Modu.

## Rehber verisi (canlı durum)
- 316 kişi: 102 öğrenci, 191 veli, 23 personel. Kaynaklar: `velitelefon/*.xlsx` (`scripts/velitelefon_ice_aktar.py`), `mudur/SINIF/` (`scripts/sinif_bilgi_ice_aktar.py`; ikinci çalıştırma 0 ekleme, mükerrer numara 0), `tahtayoklama/data/roster/*.json` (`scripts/roster_ice_aktar.py`, tekrar çalıştırmak güvenli).

## Atos/makine SMS API'si (`arac_api.py`)
Kimlik `X-Sms-Arac-Key` (`config/arac.json::anahtar`; yönetici adları/telefonları da orada, koda yazılmaz). Tüketiciler: AnythingLLM `sms-gonder` yeteneği (yalnız İdare) ve dijital okul (`okul/kaynaklar/sms.py`, `kod-sms`). Open WebUI aracı kaldırıldı.
- `POST /api/arac/hatirlatma` (yönetime zamanlı, ONAYSIZ; saat yoksa 10:00 TR, not <=120 kr); `GET /api/arac/hatirlatmalar`; `POST /api/arac/hatirlatma/{id}/iptal`; `POST /api/arac/acil` (yönetime anında).
- İki adımlı akış (taslak: alıcı sayısı + önizleme, 30 dk geçerli -> açık onay -> gönder): `veli-taslak`/`veli-gonder`; `ogrenci-taslak`/`ogrenci-gonder` (alıcı = sınıfın telefonlu öğrencileri; `test_telefon` verilirse yalnız o numaraya); `personel-taslak`/`personel-gonder` (`{metin}`, alıcı = "Personel" sınıfı, telefonlu, tekil). Veli/öğrenci taslakları aynı `veli_taslaklari` tablosunda `tur` ile ayrılır; çapraz gönderilemez.
- `sinif: "TÜM"` (veli/öğrenci taslak): 9-A…12-B (Personel/Bilinmeyen Sınıf hariç), sınıflar arası numara tekil. `*-gonder` gövdesinde `alici_sayisi` (= taslaktaki sayı) ZORUNLU, yoksa/yanlışsa 400.
- Günlük sınır: taslak yoluyla günde en çok `TOPLU_GUNLUK_AZAMI`=500 alıcı, aşılırsa gönder 429. `test_telefon` gönderimleri sayılmaz; acil/hatırlatma/kod-sms girmez.
- `kisisel-taslak`/`kisisel-gonder`: `{ogeler:[{okul_no, metin_sablon}], test_telefon?}`; öğrenci YALNIZ `kisiler.okul_no` ile bulunur, alıcı = öğrenci (telefonu varsa) + velileri, öğe içinde tekil; `{ad}` sunucuda `str.replace` ile doldurulur, metin <=300. Yanıtta `bulunamayan`/`alicisiz` listeleri. `test_telefon` varsa yalnız İLK bulunan öğe, yalnız o numaraya. Ayrı `kisisel_taslaklari` tablosu (çapraz kullanılamaz); gönderimde alıcılar yeniden çözülür.
- `POST /api/arac/kod-sms`: `{telefon, metin}`, tek telefona serbest metin 1-160 karakter, taslak/onay YOK; telefon başına dakikada 1 / saatte 5 sınır (aşınca 429; bellekte, restart'ta sıfırlanır); geçersiz telefon/metin 422.
- Sonuç `gonderimler` tablosunda (`/kayitlar`).
