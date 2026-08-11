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
| 🎛️ Öğretmen paneli | **DURDUR** · **DEVAM ET** · yazılan her şey talimat |
| 📝 Ders kaydı | Konuşulanların VE öğretmenin yazılı talimatlarının dosyaya kaydı (ses kaydı yok) |

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

## Güvenlik sınırı

Farabi uygulama açamaz, terminal komutu çalıştıramaz, işletim sistemi ayarlarını
değiştiremez, tarayıcı süremez, mesaj gönderemez, dosya yönetemez. Bu eksik bir
özellik değil, bilinçli bir sınırdır: çocukların gözetimsiz konuştuğu bir cihazda
kabuk komutu çalıştırabilen bir araç bulunmamalıdır. Kamera da yoktur — 2026-08-09'da
kaldırıldı, hiçbir aşamada kullanılmıyor.

Site gösterme aracı **tarayıcı açmaz** — sayfayı sunucu tarafında çekip
tahtaya metin/tablo olarak basar; kaçılacak bir tarayıcı yoktur.

**Üç istisna, üçü de video/dosya açma eylemlerinde:** `youtube_video`'nun
oynatma eylemi videoyu sistem tarayıcısında açar (`xdg-open`), özet çıkarma
eylemi de (kaydet seçeneğiyle) özeti `~/Desktop`'a yazıp bir metin
düzenleyiciyle açar; `eba`'nın video eylemi de aynı şekilde `xdg-open` ile
sistem tarayıcısını açar (EBA'da gömme/oynatma imkânı yok). Üçü de yukarıdaki
sınırın dışında kalır ve tahtada kontrolsüz bir pencere açılabilir; henüz
düzeltilmedi — bkz. `CLAUDE.md`, "Capability boundary" bölümü. `eba`'nın PDF
eylemi bu istisnaya girmez: dosya sunucu tarafında indirilip metni çıkarılır,
tarayıcı açılmaz, disk yazılmaz.

## Dosya yapısı

```
main.py                 Live oturumu, araç dağıtımı, ses döngüleri, ders açılışı
ui.py                   PyQt6 arayüz (üç kolonlu HUD)
setup.py                pip install; kurulumun geri kalanı config/*.example
                        dosyalarını kopyalamaktan ibaret (aşağıya bakın)
farabi_start.sh         venv + başlatma sarmalayıcısı
Farabi.gif              HUD animasyonu (yer tutucu, serbestçe değiştirilebilir)
dersgiriscikis.png      okulun zil çizelgesi fotoğrafı

actions/                araçlar; bildirimler kayit.py'de. Kamera/ekran yakalama
                        yok (screen_processor.py 2026-08-09'da kaldırıldı)
  kayit.py                ARAÇ KAYDI — bildirim, zaman aşımı, izin, maliyet
  ders_icerigi.py         öğretmen konusuna göre kitap sayfaları
  yks_sorulari.py         konuyla ilgili YKS (TYT/AYT) çıkmış sorusu — yalnız
                          soru metni, çözüm var; çözümü model öğrenciye sorar sonra kendisi anlatır
  file_processor.py       belge ve görsel işleme (AI kısmı Gemini DIŞI — bkz. altta)
  youtube_video.py        ders videosu bulma/açma/özeti (AI kısmı Gemini DIŞI)
  eba.py                  EBA videosu açma + soru PDF'i indirip metnini gösterme
                          (2026-08-09 eklendi)
  web_search.py           web araması — DDG (ücretsiz) + AI sentezi (Gemini DIŞI)
  site_goster.py          izinli kaynak siteler — tarayıcısız, sunucu tarafında
                          çekilip metin/tablo olarak basılır

core/
  prompt.txt              öğretmen personası (v2.0)
  program.py              ders programı: gün × saat × sınıf → hangi ders
  vision_prompt.txt       artık kullanılmıyor (yalnız screen_processor.py
                          okuyordu, o kaldırıldı) — kullanıcı içeriği olduğu
                          için silinmedi, sorulmadan silinmez/değiştirilmez
  ders_motoru.py          DERS MOTORU — deterministik durum makinesi
  olaylar.py              tahta içi olay veri yolu
  zil.py                  zil çizelgesi ve ders saati durumu
  tahta.py                bu tahta hangi derslikte
  modeller.py             canlı ses model adı (yalnızca Gemini Live)
  anahtar.py              Gemini API anahtar havuzu (yalnızca canlı ses için)
  saglayicilar.py         Gemini DIŞI 6 sağlayıcılı havuz (Groq, Mistral,
                          DeepSeek, OpenRouter, NVIDIA NIM) — ders anlatımı
                          dışındaki tüm metin/görsel işler buradan geçer
  logger.py               tanı logu
  transcript.py           ders kaydı

tools/                    ÇEVRİMDIŞI hazırlık betikleri (ders sırasında değil),
                          çoğu ui.py'deki bir düğmeden de tetiklenebilir
  kitap_index.py            ders kitabı PDF    → icerik/kitaplar.json
  kitap_metin.py            PDF → icerik/metin/<kitap>.json (zorunlu yol)
  dogrula.py                İÇERİK DOĞRULAMA KAPISI — kitap indeksi + elle
                            eşlemeler; ücretsiz, anında, API çağrısı yok
  sembol_temizle.py         İSTEĞE BAĞLI, ÜCRETLİ: şüpheli '#'/'$' sembollerini
                            yapay zeka ile temizler (yalnız emin olduğunda)
  kitap_ozet.py             İSTEĞE BAĞLI, ÜCRETLİ: kitap özeti + internetten
                            zenginleştirme sorusu fikirleri üretir
  onbellek_isit.py          verilen bir ders+konu için sayfa seçimini ısıtır
  mikrofon_test.py          tahta başına mikrofon ölçümü
  yks_metin.py              YKS PDF → icerik/yks_metin/<dosya>.txt (zorunlu
                            yol için yks_sorulari; kelime puanlaması kullanır)
tests/                    pytest — ağ yok, model yok

config/
  api_keys.json           API anahtarı, derslik, ders kipi   (gitignore)
  api_keys.example.json   aynı biçim, şablon olarak — kurulum sihirbazı yok,
                          elle kopyalanır
  zil.json                zil çizelgesi                      (gitignore)
  zil.example.json        aynı değerler, şablon olarak
  ders_programi.json      okulun ders programı               (gitignore)
  ders_programi.example.json   aynı biçim, şablon olarak

planlar/                  MEB yıllık plan .xlsx — yalnızca ARŞİV, hiçbir kod
                          yolu tarafından okunmuyor (bkz. planlar/BURAYA_NE_KONUR.md)
kitaplar/                 ders kitabı PDF'leri — BURAYA ATILIR
YKS/                      YKS (TYT/AYT) çıkmış sınav soruları — BURAYA ATILIR,
                          kitaplar/ ile aynı mantık; tools/yks_metin.py düz
                          metne çevirir, yks_sorulari bunu okur
icerik/                   üretilen indeks + önbellek    (gitignore)
  eslemeler/*.json          ELLE yazılan tema→sayfa eşlemeleri (depoda durur)
  metin/<kitap>.json        kitap sayfa metni (gitignore) — tools/kitap_metin.py
                            üretir, ders_icerigi bunu okur
  ozet/<kitap>.json          İSTEĞE BAĞLI kitap özeti (gitignore) — tools/kitap_ozet.py
                            üretir, ders_icerigi varsa başa ekler
  yks_metin/<dosya>.txt      YKS PDF'lerinin düz metni (gitignore) — tools/yks_metin.py
                            üretir, yks_sorulari okur
logs/                     ders kayıtları + tanı logu    (gitignore)
```

Kitap verisi tek yönde akar: `kitaplar/` → `tools/` → `icerik/` → çalışma anında
`ders_icerigi`. PDF'ler ders sırasında açılmamalı (`kitap_metin.py` önce
çalıştırılır). Yıllık plan artık hiçbir kod yolunda yok — ders yalnızca
kitaplar üzerinden işlenir: konu/kazanım öğretmenden gelir, doğrudan kitaba
bakılır.

## Kurulum

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Testler (geliştirme; `pytest` tahta kurulumunda gerekmez):

```bash
pip install pytest && python -m pytest tests/ -q
```

Okula özel iki dosya, örneklerinden kopyalanır:

```bash
cp config/zil.example.json           config/zil.json            # zil saatleri
cp config/ders_programi.example.json config/ders_programi.json  # ders programı
```

`config/api_keys.json` de aynı şekilde elle oluşturulur — örneği kopyalayın:

```bash
cp config/api_keys.example.json config/api_keys.json
```

ve içine gerçek Gemini API anahtarınızı (`gemini_api_keys`), tahtanın bulunduğu
sınıfı (`derslik`, örn. `"9-A"`) ve ders kipini (`ders_kipi`) yazın. **Otomatik
bir ilk-kurulum penceresi yoktur** — eskiden dosya eksikse bir "İLK KURULUM"
penceresi çıkıp tek bir anahtar + işletim sistemiyle dosyayı SIFIRDAN
yazıyordu, bu da elle girilmiş `derslik`/`ders_kipi`/anahtar havuzunu sessizce
siliyordu. O pencere kaldırıldı: dosya eksikse ya da anahtar taşımıyorsa Farabi
DERS KAYDI panelinde bir hata satırı gösterir ve dosyanın elle
tamamlanmasını bekler; hiçbir şeyi kendi yazmaz. Program + derslik olmadan
Farabi hangi sınıfta ve derste olduğunu bilemez; o durumda **öğretmene**
sorar (sınıfa değil).

**Gemini yalnızca canlı sesli ders için gerekli.** Ders anlatımı dışındaki her
şey — web arama sentezi, belge/video özeti, kitap özeti, şüpheli sembol
düzeltme, yüklenen resim analizi — altı farklı ücretsiz/ucuz sağlayıcıya
dağıtılmış durumda (`core/saglayicilar.py`): `groq_api_key`, `mistral_api_key`,
`deepseek_api_key`, `openrouter_api_key`, `nvidia_api_key`. Hiçbiri zorunlu
değil — boş bırakılan bir sağlayıcı sırasıyla atlanır, o görevin zincirindeki
bir sonrakine geçilir; hepsi boşsa o görev başarısız olur ve ilgili araç
"sınırlı devam et" mesajıyla döner, sessizce uydurma yanıt üretmez. Anahtarları
almak için: [console.groq.com/keys](https://console.groq.com/keys),
[console.mistral.ai](https://console.mistral.ai/),
[platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys),
[openrouter.ai/settings/keys](https://openrouter.ai/settings/keys),
[build.nvidia.com](https://build.nvidia.com) (`nvapi-...` ile başlar).

Dosya hazır olduktan sonra Farabi'yi başlatın (yeniden başlatma gerekir —
dosya çalışırken izlenmez). Oturumu öğretmen **DERSİ BAŞLAT** ile açar (çift
tık).

## Kitap indeksini hazırlama

Kitap içeriği çalışma anında değil, **bir kez önceden** hazırlanır — elle
komut satırından, ya da HUD'daki düğmelerden (sağ panel):

```bash
# Ders kitaplarını toplu indeksle
python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json

# ZORUNLU: sayfa metnini çıkar (ders_icerigi bunu okur)
python tools/kitap_metin.py kitaplar/ --json icerik/metin

# ZORUNLU: üretilen indeksi doğrula (bozuk indeks sınıfta doğaçlama olur)
python tools/dogrula.py
```

Program her açılışta `kitaplar/` klasörünü de kendisi kontrol eder: yeni bir
PDF eklenmişse `icerik/kitaplar.json`'u arka planda, sessizce günceller
(`ui.py`, `_kitaplar_json_guncelle`) — elle `kitap_index.py` çalıştırmayı
unutmak bir kitabı görünmez bırakmaz. Sayfa metnini çıkarma
(`kitap_metin.py`) da aynı açılış kontrolünde eksik kitaplar için otomatik
tetiklenir; HUD'daki **📚 KİTAPLARI METNE DÖNÜŞTÜR** düğmesi aynı işi görünür
bir terminalde, ilerlemeyi göstererek çalıştırır.

**Doğrulama kapısı ne yakalar:** bir kitabın bütün ünitelerinin aynı adı
taşıması, tek bölümün kitabın tamamını kaplaması, bozuk eşleme dosyaları.
RED alan kitap için `icerik/eslemeler/<kitap>.json` dosyasına elle tema→sayfa
eşlemesi yazılır; elle eşleme otomatik indeksin önüne geçer. Ücretsiz ve
anında — API çağrısı yapmaz.

Öğretmen konu verdikten sonra Farabi `ders_icerigi` ile ilgili sayfaları getirir.
Sayfa seçimi kelime-örtüşme yöntemiyle yapılır (semantik/embedding arama
kaldırıldı — `sentence-transformers`/`torch` bağımlılığı yok, kurulum daha
hafif). Matematik gibi sembol yoğun kitaplarda bozuk fontlar `kitap_metin.py`
içinde metin olarak onarılır (API çağrısı yok); yalnızca EMİN OLUNAMAYAN
semboller ('#', '$') değiştirilmeden bırakılır ve sayılır.

**İsteğe bağlı, ÜCRETLİ adımlar (HUD düğmesi ya da elle, `--onayla` gerekir):**

```bash
# Emin olunan şüpheli sembolleri yapay zeka ile düzelt
python tools/sembol_temizle.py --onayla

# Kitap özeti + internetten zenginleştirme soru fikirleri üret
python tools/kitap_ozet.py --onayla
```

İkisi de `core/saglayicilar.py` üzerinden gerçek API çağrısı yapar (Gemini
DEĞİL — DeepSeek/Mistral/NVIDIA NIM, bkz. yukarıdaki "Gemini yalnızca canlı
sesli ders için gerekli"); HUD'daki karşılıkları **🧹 ŞÜPHELİ SEMBOLLERİ
TEMİZLE (AI)** ve **🗒️ KİTAP ÖZETİ ÇIKAR (AI)** düğmeleridir — düğmeye basmak
`--onayla` onayı yerine geçer. Kitap özeti üretildiyse `ders_icerigi` onu
ilgili sayfaların başına otomatik ekler; yeni bir araç değildir, model hâlâ
tek bir çağrıyla içeriği alır.

## Çıkmış YKS sorularını hazırlama

`YKS/` klasörüne atılan geçmiş sınav PDF'leri de çalışma anında değil, önceden
düz metne çevrilir — kitap indeksiyle aynı mantık, farklı yol. Elle:

```bash
python tools/yks_metin.py YKS/ --txt icerik/yks_metin
```

ya da HUD'daki **📝 YKS SORULARINI METNE DÖNÜŞTÜR** düğmesinden (görünür bir
terminalde, kitap dönüştürmeyle aynı akış).

Bu **zorunludur**: `yks_sorulari` aracı `icerik/yks_metin/` boşsa doğaçlama
yapmaz, "arşiv hazır değil" der ve kitaptan anlatmaya devam eder. Dönüştürme
tamamen yerel (`pdfplumber`, API çağrısı yok); ölçülen süre bu geliştirme
makinesinde 8 dosya (~1.300 sayfa) için 4 dakika 9 saniye, bir kerelik bedel.

Öğretmen ya da öğrenci "bu konuda çıkmış soru var mı" dediğinde Farabi bu
arşivden konuya en yakın sayfayı kelime örtüşmesiyle bulur ve **sınıfa okuyup
çözümü kendisi anlatır** — kaynak PDF'lerde yazılı çözüm yok (yalnızca soru),
o yüzden çözmek modelin işidir.

## Bilinen sorunlar

- **Dahili mikrofon sınıf için yetersiz — harici mikrofon gerekiyor.** Ölçüldü:
  sessiz oda rms 8-16, konuşma rms 200-450; sağlıklı aralık 1500-8000. Mikrofon
  bozuk değil, sesi ~10 kat düşük seviyede yakalıyor. Kazanç yükseltmek
  çözmüyor, gürültü tabanını da aynı oranda yükseltiyor. Her tahtaya USB
  konferans ya da tavan mikrofonu gerekir.
  Doğrulama: `python tools/mikrofon_test.py --karsilastir` (oran 3x altındaysa
  o tahta derse hazır değil).
- **11 ve 12. sınıfın ders kitabı yok.** Elde olan PDF'ler `kitaplar/` altına
  konup `kitap_index.py` + `kitap_metin.py` çalıştırılınca bağlanır. Kod sorunu
  değil, veri eksiği.
- **Bazı kitapların otomatik indeksi bozuk çıkıyor** — `fizik-10` ve
  `cografya-10` ölçüldü ve `icerik/eslemeler/` altında elle eşlendi. Yeni bir
  kitap eklendiğinde `tools/dogrula.py` çalıştırılmalı.
- **Yeni bir konu ilk çağrıldığında sayfa taraması sürebilir** (önbelleksiz
  kitapta). Ders öncesinde `tools/onbellek_isit.py --ders ... --sinif ...
  --konu ... --onayla` ile ısıtın (konu elle verilir, hiçbir yerde otomatik
  tespit edilmez).
- **Ders programı elle yazılır** (`config/ders_programi.json`). Yazılmazsa
  Farabi ders adını öğretmene sorar.
- **Öğretmen panelinde kimlik doğrulama yok.** Tahtanın başındaki herkes
  yazı kutusuna talimat yazabilir. Çözülmedi, planlanmıyor da — gerçek bir
  sorun olursa yerel bir çözüm gerekir (PIN, fiziksel anahtar, öğretmene özel
  cihaz), merkezi bir sunucuya ertelenecek bir şey değil.
- **HUD animasyonu yer tutucu.** `Farabi.gif` değiştirilebilir, kod değişikliği
  gerekmez.
- **`sembol_temizle.py` ve `kitap_ozet.py` gerçek API parası harcar.** Kuru
  çalışma varsayılan (`--onayla` gerekir); HUD düğmesine basmak onay yerine
  geçer, yani düğmeye her basış ücretlidir — teneffüste rastgele denemeyin.
- **Gün boyu API kotası tek anahtarla zorlanabilir.** Her tahta kendi
  `config/api_keys.json` dosyasındaki `gemini_api_keys` havuzunu kullanır;
  havuz ayrı Google Cloud projelerine yayılmadıkça rotasyon aynı aylık
  harcama tavanına düşer (bkz. `CLAUDE.md`, "API key pool"). Boşta kalan
  oturumu kapatan `BOSTA_KAPATMA_DK` (15 dk) zaten var; kota sık dolan bir
  tahtada önce bunun çalıştığını, sonra anahtar havuzunun proje sayısını
  kontrol edin. Bu yalnızca CANLI SES (Gemini) için geçerli.
- **Altı sağlayıcılı havuzun (`core/saglayicilar.py`) da kendi ücretsiz kota
  sınırları var** (ör. OpenRouter günde 50-1000 istek, NVIDIA NIM ~40
  istek/dk) — bir sağlayıcı kotası dolarsa o görev zincirindeki sıradaki
  sağlayıcıya otomatik geçilir, tek bir sağlayıcının kotası tüm sistemi
  durdurmaz. Yine de tüm sağlayıcılar aynı anda dolarsa (yoğun kullanım,
  büyük bir belge yığını vb.) ilgili araç "sınırlı devam et" mesajıyla döner.

## Proje durumu

Tahta istemcisi (bu depo) çalışıyor. Linux'ta uçtan uca doğrulandı — temiz
kurulum, canlı oturum, araç çağrıları, ders kaydı. Gerçek akıllı tahta
donanımında (dokunmatik) ve güvenilir mikrofon girişinde saha testi bekliyor.
Kamera kullanılmıyor, test kapsamında değil.

Her tahta bağımsız çalışır: kendi config dosyaları, kendi API anahtarları,
kendi yerel içerik indeksi. Merkezi bir sunucu üzerinden yönetim denendi,
sonra bilinçli olarak vazgeçildi — bu depoda ya da dokümantasyonda "faz 2
sunucu" gibi bir çerçeve yeniden kurulmamalı.
