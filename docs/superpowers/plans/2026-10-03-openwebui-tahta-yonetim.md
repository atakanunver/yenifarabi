# Open WebUI'den tahta yönetimi: "Farabi Yönetim" aracı

## Context
Atakan, Open WebUI'ye (farabi.local:80) yazarak dashboard'un (farabi.local:8010) yaptığı işleri yaptırmak istiyor. Örnekler:
- "tüm tahtaları yeniden başlat"
- "9-A ekranını karart"
- "hangi tahtalar açık"
- "bugün 9-A'da kim yok"

Teknik olarak mümkün. `qwen3.8:27b` modelinde `tools` yeteneği var. Open WebUI 0.11'de native tool çağrısı ve bir onay penceresi (`__event_call__`) bulunuyor.

Kullanıcı kararları (2026-10-03):
- Araçları **yalnızca admin** kullanır.
- **Sırlar sunucuda kalır.** SSH anahtarı, IP ve MAC adresleri Open WebUI memory'sine ya da wiki'ye girmez. LLM yalnızca tahta adlarını bilir. SSH'ı dashboard yapar.
- **Reboot:** 11-A, 12-A ve fenlab'a yalnızca `systemctl reboot` komutuna izin veren dar bir sudoers kuralı eklenir.
- **v1 kapsamı:** durum sorguları, reboot, mevcut uzaktan eylemler ve yoklama sorgusu.

Mimari ilke: Open WebUI ile dashboard kod paylaşmaz, birbirleriyle HTTP ve anahtar üzerinden konuşur (kök CLAUDE.md).

## Mevcut durum (keşif)
- **Dashboard'da makine API'si yok.** Giriş yalnızca ortak şifre ve `oturum` çereziyle yapılıyor (`auth.py:77`). Eylemler form-data alıp HTML döndürüyor (`uzaktan_yonetim.py:286-341`, `_eylem_calistir_ve_render` :272). Canlı durum için JSON yok, ama `tum_durumlar()` (:127) var.
- **Reboot hiç yok.** `ssh_istemci.komut_calistir()` (:45) ve `tahta_kaydi.tahtalari_yukle()` (`admin` alanı dahil) yeniden kullanılacak.
- **Denetim kaydı:** `_denetim_yaz` (:74) `uzaktan_denetim` tablosuna yazıyor. Tabloda `kaynak` sütunu yok.
- **Yanıtlar IP sızdırıyor.** `tum_durumlar()` `{**t}` döndürüyor, `detay` ham stderr içeriyor, `durum_topla()` LAN IP'lerini içeriyor. Bu yüzden ajan yanıtları yalnızca izin verilen alanları döndürmeli.
- **Dashboard venv'inde httpx yok.** Testler route fonksiyonlarını doğrudan çağırır (`test_uzaktan_denetim.py` deseni). Test komutu: `venv/bin/python -m unittest discover -p 'test_*.py'`.
- **Sudo çerçevesi hazır.** `tahtaayar/tahta_fix_uygula.py` zaten etapadmin + `sudo -n`/`-S` akışını ve `Duzeltme` dataclass'ını (:110) içeriyor. Etapadmin parolasını gitignore'lu `gizli.json`'dan kendisi okuyor.
- **Open WebUI tool'ları** OW sürecinde, `openwebui` kullanıcısıyla, sandbox ve zaman aşımı olmadan çalışıyor. Async tool event loop'ta await ediliyor; senkron HTTP çağrısı bütün kullanıcıları dondurur, bu yüzden `httpx.AsyncClient` (OW venv'inde var) şart. Tool API'si: `/api/v1/tools/{create, id/{id}/update, id/{id}/valves/update, id/{id}/access/update}`. `kur.py::filtreyi_kur` (:117-127) bu deseni zaten uyguluyor.

## Sıralama
- **A (dashboard):** master'dan ayrı bir dalda, hemen başlayabilir.
- **C (sudoers):** kodu A ile paralel yazılabilir. Kurulumu tahtalarda kullanıcı çalıştırır.
- **B (OW aracı + kur.py):** yalnızca `openwebui-farabi-modlar` dalı merge edildikten sonra. `kur.py`'yi genişletir, kopyalamaz.
- **Kurallar:** Kural 11 (kodu Sonnet yazar), Kural 3 (tek seferde tek modül). Yeni pip bağımlılığı yok.

## A. Dashboard makine API'si (`tahtayoklama/dashboard/`)
1. **Anahtar dosyası:**
   - `tahtayoklama/dashboard/config/ajan.json` `.gitignore`'a eklenir (şu an ignore edilmiyor ve repo public).
   - `scripts/ajan_anahtari_olustur.py` dosyayı `secrets.token_urlsafe(32)` ile, 0600 izinle yazar.
   - `gizli.json` kullanılmaz.
2. **Yeni router `ajan_api.py` (prefix `/api/ajan`):**
   - **Kimlik:** `_ajan_dogrula` önce istemci IP'sine bakar; `127.0.0.1` ya da `::1` değilse 403 döner. Sonra `X-Farabi-Ajan-Key` başlığını `hmac.compare_digest` ile karşılaştırır, yanlışsa 401 döner. Anahtar her istekte okunur; dosya yoksa 503 döner. Çerez kabul edilmez ve mevcut route'lar değişmez.
   - **Kaynak bilgisi:** `X-Farabi-Kaynak` başlığı (`openwebui:<email>`, en fazla 120 karakter) denetim kaydına yazılır.
   - **Uçlar:**
     - `GET /tahtalar?canli=0|1`: yalnızca `{ad, ulasilabilir, oturum, yoklama, chrome, karartildi}` döner.
     - `GET /sistem`: servis adı, durum ve süre döner; host ve IP dönmez.
     - `GET /yoklama?tarih=&sinif=`: `app.api_durum`'daki SQL `_durum_satirlari(conn, tarih)` yardımcısına taşınır ve iki route da onu kullanır.
     - `POST /eylem {eylem, tahtalar, url?}` ve `POST /yeniden-baslat {tahtalar}`.
   - **Tahta adı:** Bilinmeyen tahta adı gelirse 400 ve `{"bilinmeyen": [...]}` döner, hiçbir şey çalışmaz. Mevcut kod bilinmeyen adları sessizce atlıyor.
   - **Sonuç biçimi:** `{tahta, basarili, sebep}`. `sebep` şunlardan biridir: `tamam | ulasilamadi | zaman_asimi | oturum_yok | izin_yok | hata`. Ham stderr dönmez.
3. **`uzaktan_yonetim.py`:**
   - `EYLEMLER = {"yoklama_ac": _yoklama_ac_tek, ...}` eşlemesi eklenir: altı eylem, duvar kağıdı hariç.
   - `form` yerine düz `dict` geçilir.
   - `_denetim_yaz(..., kaynak=None)`. Ajan eylemlerinin adı `ajan:<eylem>` biçiminde yazılır.
4. **Yeni modül `tahta_yeniden_baslat.py`:**
   - **Okul saati:** `ders_saatinde_mi()` okul günlerinde ilk dersten son dersin bitişine kadar (teneffüsler dahil) reboot'u **reddeder**. LLM'in bunu aşabileceği bir yol yok.
   - **Akış:**
     1. `sudo -n -l /usr/bin/systemctl reboot` ile ön kontrol yapılır; yetki yoksa sonuç `izin_yok` olur.
     2. Sonra `sudo -n /usr/bin/systemctl reboot` çalışır. Komut sudoers kuralıyla birebir aynıdır.
     3. Çıkış kodu 0 ya da 255 (bağlantı koptu) ise "gönderildi" sayılır.
   - **Tekrar koruması:** Tahta başına 120 saniye bekleme süresi var, böylece model aynı isteği tekrarlarsa ikinci reboot olmaz.
   - **Uyarı:** 9-A için "giriş ekranında kalır" uyarısı eklenir (otomatik giriş yok).
5. **`db.semayi_kur()`:** `PRAGMA` ile kontrol edilip yoksa `ALTER TABLE uzaktan_denetim ADD COLUMN kaynak TEXT` çalışır.
6. **`app.py`:** `include_router(ajan_api.router)` ve `_durum_satirlari` taşıması.
7. **`test_ajan_api.py`:** şunları doğrular:
   - 403 ve 401 kuralları; çerez tek başına yetmez.
   - Yanıtlarda IP deseni yok.
   - Bilinmeyen tahta 400 alır ve hiçbir şey çalışmaz.
   - Reboot ders saatinde ve teneffüste reddedilir, 15:50'den sonra kabul edilir.
   - `sudo -l` başarısızsa reboot komutu çağrılmaz.
   - 255 "gönderildi" sayılır.
   - Bekleme süresi çalışır.
   - Denetim kaydına `kaynak` yazılır.
   - `/api/durum` sonucu değişmez.
   - SSH `patch` ile taklit edilir.

## C. Sudoers kuralı (`tahtaayar/tahta_fix_uygula.py`)
- Yeni bir `Duzeltme("reboot_sudoers", root_gerekli=True)` eklenir.
- Kural geçici bir dosyaya yazılır: `etapadmin ALL=(root) NOPASSWD: /usr/bin/systemctl reboot`. `visudo -cf` doğrulaması geçerse `install -m0440` ile `/etc/sudoers.d/farabi-reboot` olarak kurulur.
- Kontrol `sudo -n -l` ile etapadmin bağlamında yapılır. Framework kontrolü root olarak sarmalıyor, bu ayrıntı birim testte doğrulanmalı.
- Önce Pardus'ta `command -v systemctl` ile yol teyit edilir.
- **Tahtalara kurulumu kullanıcı çalıştırır.** Uygulayıcı parola dosyasını okumaz.

## B. Open WebUI aracı (`openwebui/`, modlar dalı merge edildikten sonra)
1. **`farabi_yonetim_araci.py`**
   - `class Tools`, `Valves(api_url="http://127.0.0.1:8010/api/ajan", api_key, zaman_asimi_sn=60)`. Bütün metotlar async, HTTP çağrıları `httpx.AsyncClient` ile yapılır.
   - Her metot önce `__user__["role"] == "admin"` kontrolü yapar.
   - **Okuma metotları:** `tahta_durumu()`, `sunucu_durumu()`, `yoklama_sorgula(tarih, sinif)`.
   - **Değiştiren metotlar:** `tahta_eylemi(eylem: Literal[...], tahtalar, url)` ve `tahtalari_yeniden_baslat(tahtalar)`. Akış:
     1. Adlar normalleştirilir: `9a`, `9/a`, `9 A` hepsi `9-A` olur.
     2. `hepsi`, kayıttaki gerçek listeye açılır.
     3. Bilinmeyen ad varsa geçerli adlar listelenerek reddedilir.
     4. `__event_call__` confirmation penceresinde kesin tahta listesi ve eylem gösterilir. Reboot için ders saati ve 9-A uyarısı da eklenir.
     5. Yalnızca dönüş değeri `is True` ise devam edilir. `False`, `None` ya da `{'error'}` gelirse HTTP isteği yapılmaz.
   - `__event_emitter__` ile durum bildirimi yapılır.
   - Dönüş değeri kısa bir Türkçe özettir ve sır içermez.
2. **`kur.py`**
   - `araci_kur()`, `filtreyi_kur` desenini izler. `access_grants=[]` olur, yani aracı yalnızca admin görür. Valves'a anahtar `tahtayoklama/dashboard/config/ajan.json`'dan okunup yazılır.
   - Yeni model `farabi-yonetim` ("Farabi Yönetim"):
     - `meta.toolIds=["farabi_yonetim"]`
     - builtin araçlar (memory dahil) kapalı
     - `params.function_calling="native"`
     - `access_grants=[]`
     - Sistem promptu `promptlar/yonetim.md`'den gelir: araçlar, tahta adlandırması, "araç çıktısında olmayan tahta adı uydurma", "yeniden başlatmayı yalnızca açık istek üzerine yap".
   - `--kuru` yeni adımları da kapsar.
3. **`tests/test_yonetim_araci.py` ve `test_kur.py` ekleri:**
   - Onay değerlerinden yalnızca `True` HTTP isteğine yol açar.
   - `user` rolü reddedilir.
   - `hepsi` açılımı ve ad normalleştirme doğru çalışır.
   - Bilinmeyen ad onay penceresi açılmadan reddedilir.
   - Yeni model gövdesi doğru oluşur.

## Varsayılan olarak aldığım kararlar (itiraz edersen değişir)
- **Ders saatinde zorla reboot yok.** LLM'e böyle bir argüman açılmaz. Gerekirse ileride varsayılanı kapalı bir admin Valve'ı olarak eklenir.
- **`hepsi`** kayıttaki 11 tahtanın hepsini kapsar, sınıf atanmamış `tahta-234/235/236` dahil. Onay penceresinde görünürler, kapalıysa "ulaşılamadı" dönerler.
- **Duvar kağıdı v1'de yok:** dosya yükleme gerektiriyor.

## Ayrı konu (bu planın dışında, senin kararın)
- `server/tahtalar.json` git'te izleniyor ve repo public, yani tahta IP ve MAC adresleri GitHub'da. Bu planı etkilemiyor ama ayrıca ele alınmalı.

## Doğrulama
1. Dashboard unittest'lerinin hepsi geçer. Panelden normal giriş, `/admin/uzaktan` ve bir eylem elle denenir; davranış değişmemiş olmalı.
2. `curl` kontrolleri:
   - Başka bir LAN makinesinden `/api/ajan/tahtalar` isteği 403 alır.
   - Sunucuda anahtarsız istek 401 alır.
   - Anahtarlı istek JSON döner ve çıktıda IP deseni yoktur.
   - `git status` çıktısında `ajan.json` görünmez.
3. Sudoers kuralı uygulandıktan sonra 8 tahtada `sudo -n -l /usr/bin/systemctl reboot` başarılı olmalı.
4. `kur.py --kuru` ve ardından gerçek kurulum çalıştırılır. Öğretmen ve İdare hesaplarında `farabi-yonetim` modeli ve araç görünmemeli.
5. Admin olarak şunlar denenir:
   - "hangi tahtalar açık" ve "bugün 9-A'da kim yok"
   - "9-A ekranını karart": önce **iptal** edilir, eylem ve denetim kaydı oluşmamalı. Sonra onaylanır, ekran kararmalı ve denetim kaydında `kaynak=openwebui:<email>` görünmeli.
6. Okul saatinden sonra önce bir NOPASSWD tahta, sonra 11-A, 12-A ya da fenlab'dan biri yeniden başlatılır. Okul saatinde reboot isteğinin reddedildiği görülmeli.
7. Son kabul testi fiziksel tahtada Atakan tarafından yapılır (Kural 12).
