# 🎓 Farabi

### Sınıf akıllı tahtaları için Türkçe yapay zekâ öğretmen

**Hazırlayan :** Atakan ÜNVER

> **"Günaydın çocuklar ve kıymetli öğretmenim, ben Farabi."**

Adını, Aristoteles'ten sonra tarihte **"Muallim-i Sânî" (İkinci Öğretmen)** unvanını
alan Türk-İslam bilgini **Fârâbî**'den alır. Felsefe, matematik, astronomi ve müzik
alanlarındaki çalışmalarıyla bilginin simgesi olan Fârâbî, bir öğretmen asistanına
adını verebilecek en yerinde isimdir.

---

## Ne yapar

Sınıftaki akıllı tahtada çalışır, öğrencilerle sesli konuşur, tahtadaki soruyu
görerek anlatır. **Hangi ders** olduğunu okul programından bilir; **konu ve
kazanımı** öğretmenin adını yazar veya söyler. Cevabı doğrudan vermek yerine öğrenciye
ilk adımı sordurur — öğrenci iki kez takılırsa üçüncüde çözümü gösterir.

| Yetenek | Açıklama |
|---|---|
| 🎙️ Sesli ders | Gemini Live ile düşük gecikmeli, kesintisiz konuşma — varsayılan Türkçe, isteğe bağlı tamamen İngilizce/Almanca (bkz. altta) |
| 🗓️ Ders programı | Açılışta sınıf, kaçıncı ders ve ders adını duyurur — sınıfa sormaz |
| ✏️ Konu / kazanım | Öğretmen yazar veya söyler; gelmeden yoklama ve anlatım başlamaz |
| 📚 Kitap sayfaları | Öğretmen konu verdikten sonra ilgili ders kitabı sayfalarını getirir |
| 📝 Çıkmış sorular | Konuyla ilgili YKS (TYT/AYT) sorusunu arşivden bulur; soruyu ve şıkları
okur, **çözmeye kalkışmaz** — öğrenciden cevap ya da öğretmenden talimat gelmeden anlatmaz |
| 📄 Materyal okuma | PDF ders notu, ödev, sunum, tablo, görsel |
| 🌐 Kaynak siteler | TDK sözlüğü, Vikipedi, MEB, EBA, Google — yalnızca izinli adresler |
| 📺 Video desteği | YouTube ve EBA'da konu anlatım videosu bulma/açma, YouTube özeti |
| 📖 EBA soru PDF'i | EBA bağlantısından soru/çalışma kâğıdı PDF'i indirip metnini tahtaya basar (tarayıcı açmaz) |
| ⏰ Zil farkındalığı | Kaçıncı derste olduğunu, teneffüsü, öğle arasını bilir |
| 🎛️ Öğretmen paneli | **DURDUR** · **DEVAM ET** · **⏹ DERSİ BİTİR** (çift dokunuş) · yazılan her şey talimat |
| 📝 Ders kaydı | Konuşulanların VE öğretmenin yazılı talimatlarının dosyaya kaydı (ses kaydı yok); ders sonunda sunucuya yedeklenir |
| ❓ Kitap sorusu | Somut soruyu sunucudaki RAG'a sorar; yalnızca kitaptan, kaynak sayfasıyla cevap (`s. 84`, tablodan geldiyse `s. 84 (tablo)`) |
| 🧠 Ders hafızası | Bu tahtada işlenmiş geçmiş dersleri hatırlar (sunucudaki yedek kayıtlardan) |
| 📐 GeoGebra | Canlı GeoGebra penceresinde çizim/hesap (kilitli `chrome --app`) |
| 🖥️ Ekranı oku | Tahtanın KENDİ ekranındaki soruyu görüntü olarak modele verir (kamera yok) |
| 🎨 Görsel üret | Gemini Image ile ders görseli üretir |

## Ders dili

Varsayılan Türkçe. Öğretmen **DERSİ BAŞLAT**'a basmadan önce panelden
**🇬🇧 İngilizce** ya da **🇩🇪 Almanca** seçebilir — dersin tamamı (açılış selamı
dahil) o dilde işlenir. Seçim yalnızca ders başlamadan önce yapılabilir;
canlı bağlantı kurulduktan sonra dil değiştirilemez (Gemini Live'ın bir
teknik sınırı), bu yüzden düğmeler DERSİ BAŞLAT'a basılınca kilitlenir.

## İki ders kipi

Okulda her ders aynı değil:

- **Öğretmenli** (varsayılan) — sınıfta bir öğretmen ve ~20 öğrenci var. Düzen
  öğretmenin; Farabi içeriğe odaklanır, öğretmene "kıymetli öğretmenim" der.
- **Öğretmensiz** — etüt, telafi, boş ders. Sınıfta başka yetişkin yok; dersin
  akışı ve düzeni de Farabi'nin sorumluluğunda. Kip önce ders programından,
  yoksa `config/api_keys.json` içinden okunur.

## Ders çerçevesi

```
ders_programi.json  →  ders adı + saat     →  açılışta duyurulur
öğretmen (yazı/ses) →  konu + kazanım      →  çerçeve tamamlanır
ders_icerigi        →  kitap sayfaları     →  iskelet (çerçeve kaynağı değil)
```

Farabi yıllık plan Excel'inden otomatik kazanım çıkarmaz ve sınıfa
"hangi dersteyiz / nerede kalmıştık" diye sormaz. Öğrenci hafızası (`save_memory`)
yoktur — tahta sınıfça paylaşılır.

## Öğretim ilkesi

Farabi bir cevap makinesi değildir. Çekirdek protokolü (`core/prompt.txt`) şunu
söyler: *cevabı doğrudan verme, öğrenciyi düşündür, neden'i anlat, yanlışı
küçümsemeden düzelt, emin değilsen araştır, bilmiyorsan bilmediğini söyle.*

Oyun konusunda ölçüt "eğlenceli mi ciddi mi" değil, **kazanıma hizmet ediyor mu**:
soru yarışması, tahmin oyunu ve bulmaca serbest; dersten kaçırmaya hizmet eden
oyalama reddedilir.

Bu yaklaşım **Türkiye Yüzyılı Maarif Modeli**'nin öğretmen rolüyle örtüşür: ezber
yerine araştırma ve keşif, bütüncül gelişim, süreç odaklı değerlendirme.

## Mikrofonsuz mod

Tahta mikrofonları donanımsal olarak yetersiz olduğu için (aşağıya bkz.)
**şu an 8 tahtanın hepsinde mikrofonsuz mod açık** (`config/api_keys.json::
mikrofon: false`). Bu modda DERSİ BAŞLAT ders/konu/kazanımı yazılı sorar,
Farabi her turdan sonra kendiliğinden devam eder, ders 40 dakikada ya da
zilden 2 dk önce biter. Paneldeki **🎤 MİKROFONLU / 🚫 MİKROFONSUZ** düğmesi
yalnızca açılış varsayılanını bellekte değiştirir (dosyaya yazmaz).

## Öğretmen talimat modu

Ders dışı kullanım: **👨‍🏫 ÖĞRETMEN MODU**'nda öğretmen sesle tek cümlelik
komutlar verir (web sayfası aç, uygulama aç, dosya aç, pencere kapat, kitap
sayfası göster…). Ders kipleri bu araçları görmez. Mikrofonsuz modda bu mod
kilitlidir (sesle çalışır).

## Güvenlik sınırı

Ders kiplerinde (öğretmenli/öğretmensiz) Farabi terminal komutu
çalıştıramaz, işletim sistemi ayarlarını değiştiremez, tarayıcı süremez,
mesaj gönderemez, dosya yönetemez. Bu eksik bir özellik değil, bilinçli bir
sınırdır: çocukların konuştuğu bir cihazda kabuk komutu çalıştırabilen bir
araç bulunmamalıdır. Kamera yoktur; ekran görüntüsü yalnızca tahtanın kendi
ekranıdır ve yoklama/e-Okul/MEBBİS penceresi öndeyse alınmaz.

Site gösterme aracı **tarayıcı açmaz** — sayfayı çekip tahtaya metin/tablo
olarak basar.

**Bilinçli ya da açık istisnalar:**
- **Talimat modu araçları** (`web_ac`, `uygulama_ac`, `dosya_ac`,
  `pencere_kapat`) — kullanıcı kararı, yalnızca talimat modunda.
- **`geogebra`** — localhost'taki kilitli bir `chrome --app` penceresi açar
  (onaylı istisna).
- **`yoklama_al`** — yoklama ekranını başlatır; yalnızca 9-A'nın tam klon
  yapısında yolu bulur, diğer tahtalarda "bulunamadı" der.
- **Açık delikler:** `youtube_video`'nun oynatma eylemi ve `eba`'nın video
  eylemi `xdg-open` ile sistem tarayıcısını açar; YouTube özetinin
  "kaydet" seçeneği `~/Desktop`'a yazar. Ayrıntı: `CLAUDE.md`, "Capability
  boundary".

## Mimari: ince istemci, sunucu beyin

Tahtadaki bu uygulama yalnızca **arayüz + Gemini Live ses oturumu**dur.
Ağır işlerin hepsi okul sunucusunda (`farabi.local`, depodaki `server/`):
kitap/YKS içeriği, sayfa görüntüsü, RAG soru-cevap, bulut metin/görsel
sağlayıcıları, dosya işleme, geçmiş ders hafızası. Tahtanın kendi kitap/YKS
deposu **yoktur**; yalnızca `icerik/onbellek/` altında küçük, silinebilir
önbellekler durur. Sunucuya ulaşılamazsa araçlar sessizce kısıtlayıcı bir
metne düşer — **Farabi asla dersi bozmaz**.

Her sunucu isteği tahta anahtarıyla (`X-Farabi-Board-Key`) gider; anahtar
yoksa sunucu 401 döner.

## Dosya yapısı

```
main.py                 Live oturumu, araç dağıtımı, ses döngüleri, ders açılışı
ui.py                   PyQt6 arayüz (üç kolonlu HUD, öğretmen paneli, kalem/silgi)
setup.py                pip kurulumu
farabi_start.sh         venv içinden main.py'yi başlatır
update_farabi.sh        client checkout'u için git fetch + güncelleme yardımcısı
Farabi.gif              HUD animasyonu (yer tutucu, serbestçe değiştirilebilir)
dersgiriscikis.png      okulun zil çizelgesi fotoğrafı

actions/                modelin çağırdığı araçlar; tek kayıt kaynağı kayit.py
  kayit.py                ARAÇ KAYDI — bildirim, zaman aşımı, kip, çalışma biçimi
  ders_icerigi.py         konu anlatımı için kitap sayfa metni (sunucu)
  kitap_sorusu.py         RAG ile kaynaklı soru-cevap (sunucu)
  pdf_sayfa.py            kitap sayfasının görüntüsü + metni (sunucu)
  yks_sorulari.py         çıkmış YKS sorusu, sayfa görüntüsü olarak (sunucu)
  ders_hafizasi.py        bu tahtadaki geçmiş dersler (sunucu)
  file_processor.py       belge/görsel işleme (sunucu sağlayıcıları, Gemini DIŞI)
  web_search.py           web araması + sentez (sunucu sağlayıcıları)
  youtube_video.py        ders videosu bulma/açma/özeti
  eba.py                  EBA videosu + soru PDF'i metni
  site_goster.py          izinli siteler, tarayıcısız
  geogebra.py             canlı GeoGebra köprüsü
  gorsel_uret.py          Gemini Image ile görsel (arka planda)
  ekran_goruntusu_al.py / ekrandaki_soruyu_oku.py   tahtanın kendi ekranı
  web_ac.py / uygulama_ac.py / dosya_ac.py / pencere_kapat.py   talimat modu
  yoklama_al.py           yoklama ekranını açar

core/
  prompt.txt              öğretmen personası (v2.0) — kullanıcıya ait
  vision_prompt.txt, prompteski.txt   kodda okunmuyor, kullanıcıya ait — silinmez
  ders_motoru.py          ders motoru — deterministik durum makinesi
  olaylar.py              tahta içi olay veri yolu
  program.py              ders programı: sınıf × gün × saat → ders (+ kip)
  zil.py                  zil çizelgesi ve ders saati durumu
  tahta.py                tahta kimliği: derslik, sınıf düzeyi, sunucu adresi,
                          mikrofon, tahta anahtarı başlıkları
  anahtar.py              Gemini API anahtar havuzu (yalnızca canlı ses)
  saglayicilar.py         sunucunun sağlayıcı havuzuna ince HTTP vekili
  modeller.py             canlı ses model adı
  transcript.py           ders kaydı (yalnızca metin)
  logger.py               tanı logu (5 × 1 MB dönen)
  version.py              istemci sürümü (sunucunun /api/version'ı ile karşılaştırılır)

tools/                    ÇEVRİMDIŞI içerik hazırlama — SUNUCUDA koşar
                          (/mnt/farabi-data/farabi/), tahtada değil. Tahtada
                          yalnızca dogrula.py ve mikrofon_test.py işe yarar.
tests/                    pytest — ağ yok, model yok
config/                   gerçek JSON'lar gitignore'lu, *.example.json şablonlar
memory/                   KULLANILMIYOR (eski paket) — yeniden bağlanmaz
planlar/                  MEB yıllık plan .xlsx — yalnızca arşiv
icerik/onbellek/          geçici önbellekler (pdf_sayfa, yks_sayfa, ekran, görsel)
logs/                     ders/*.txt kayıtları + farabi.log (gitignore)
```

## Kurulum

Tahtaya kurulum depodaki `server/farabi-kurulum.sh` betiğiyle yapılır;
betik **tahtada, `ogretmen` olarak** çalıştırılır (GitHub'dan `client/`'ı
sparse-checkout ile klonlar, venv'i `requirements.lock.txt`'ten kurar,
masaüstü kısayolunu, günlük güncelleme ve 15 dakikalık heartbeat cron'larını
ekler):

```bash
bash farabi-kurulum.sh <derslik> <sunucu_url> <tahta_anahtari>
# tahta_anahtari = sunucudaki board_keys[derslik] ile birebir aynı
```

Tahtada güncelleme: `~/.local/bin/farabiguncelle.sh` (`git fetch` + `git
reset --hard origin/master`, her gün cron'la). İstisna: 9-A tam klon
yapısını korur (`~/farabi/repo/client`).

Elle geliştirme kurulumu:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
pip install pytest && python -m pytest tests/ -q     # yalnızca geliştirme
```

`config/api_keys.json` elle oluşturulur (`api_keys.example.json`'dan) —
**hiçbir arayüz bu dosyayı yazmaz**. Alanlar: `gemini_api_keys`, `derslik`
(örn. `"9-A"`, tahtadan tahtaya kopyalanmaz), `sunucu_url`, `tahta_anahtari`,
`ders_kipi`, `mikrofon`, `os_system`. Ortak alanlar (Gemini anahtarı,
`mikrofon`, `sunucu_url`) sunucudan `server/config_dagit.sh` ile dağıtılır.
`zil.json` ve `ders_programi.json` da gitignore'lu, aynı yolla gelir.

**Gemini yalnızca canlı ses (ve görsel üretme) için gerekli.** Diğer bütün
metin/görsel işler (web arama sentezi, belge/video özeti, resim analizi)
sunucunun sağlayıcı havuzundan geçer; bulut anahtarları tahtada durmaz.

Oturumu öğretmen **DERSİ BAŞLAT** ile açar (çift dokunuş); boşta kalan
oturum 15 dakikada kapanır.

## Kitap ve YKS içeriği

Kitap PDF'leri, sayfa metinleri, YKS arşivi ve RAG indeksi **sunucuda**
hazırlanır ve tutulur (`/mnt/farabi-data/farabi/`, PostgreSQL + pgvector).
Tahtaya bir şey kopyalanmaz; yeni bir kitap sunucuya eklendiğinde bütün
tahtalar onu hemen görür. Hazırlama betikleri `tools/` altında ama sunucuda
çalıştırılır; ayrıntı kök `CLAUDE.md`.

Şu an 25 kitap kayıtlı (9. ve 10. sınıf çoğu ders; 11. sınıfta Coğrafya,
Fizik, Kimya, Tarih, Temel Matematik, TDE; 12. sınıfta İnkılap Tarihi).

## Bilinen sorunlar

- **Dahili mikrofon sınıf için yetersiz — harici mikrofon gerekiyor.**
  Konuşma rms 200-450; sağlıklı aralık 1500-8000. Kazanç yükseltmek
  çözmüyor, gürültü tabanını da aynı oranda yükseltiyor. Bu yüzden
  mikrofonsuz mod açık. Doğrulama: `python tools/mikrofon_test.py
  --karsilastir` (oran 3x altındaysa o tahta derse hazır değil).
- **11. sınıf Biyoloji ve İngilizce kitabı yok**, 12. sınıfta yalnızca
  İnkılap Tarihi var. Kod sorunu değil, veri eksiği (sunucuya eklenir).
- **`fenlab` tahtası sınıf düzeyini bilmez** (`derslik: "fenlab"`) — kitap
  ararken öğretmene sınıfı sorar.
- **9-A'da Farabi konuşurken zaman zaman tekleme** — kök nedeni bulunamadı.
- **Ders programı elle yazılır** (`config/ders_programi.json`). Yazılmazsa
  Farabi ders adını öğretmene sorar.
- **Öğretmen panelinde kimlik doğrulama yok.** Tahtanın başındaki herkes
  yazı kutusuna talimat yazabilir; planlanmıyor.
- **Gemini kotası proje başınadır.** Anahtar havuzu ancak ayrı Google Cloud
  projelerine yayılırsa günlük tavanı genişletir. En büyük maliyet kaldıracı
  boşta kalan oturumlar (`BOSTA_KAPATMA_DK` = 15).

## Proje durumu

8 tahtada kurulu ve çalışıyor (9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B,
fenlab). Ses kalıcı olarak Gemini Live'da (yerel ses denemesi 2026-09-28'de
kalıcı iptal). Sunucu tarafı, dağıtım ve kurallar için kök `CLAUDE.md` ve
`DECISIONS.md` esas.
