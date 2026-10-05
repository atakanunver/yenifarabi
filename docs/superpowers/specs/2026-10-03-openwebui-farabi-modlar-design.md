# Open WebUI'de Farabi modları — tasarım

Tarih: 2026-10-03 · Durum: kullanıcı incelemesi bekliyor (bölüm 1–3 ve hesap modeli sohbette onaylandı)

## 1. Amaç ve kapsam

Open WebUI'deki (port 80) yerel yapay zekânın adı **Farabi** olacak. Kullanıcılar öğretmenler ve idare; öğrenciler bu aşamanın dışında.
Farabi branşa ve role göre farklı **modlara** (personalara) bürünür. Cevaplarını ders kitaplarına ve mevzuata dayandırır ve kaynak gösterir: "Kimya 10, s. 84".

Kullanıcı kararları:
- **Kullanıcılar:** Yalnızca öğretmenler ve idare (seçenek C). 120 öğrencinin aynı anda kullanımını mevcut donanım kaldırmıyor; ölçüm 2026-10-03.
- **Kaldırılan mod:** Psikolojik danışman modu iptal.
- **Arama altyapısı:** Yaklaşım 2. Open WebUI'nin kendi bilgi tabanı değil, **Farabi RAG** (pgvector + bge-m3 + reranker) kullanılır.
- **Mevzuat:** pgvector'a `chunk_idari` olarak girer. 2026-08-31'deki iptal kararı kaldırıldı (DECISIONS.md 2026-10-03).
- **Model cihazı:** bge-m3 **CPU'da** çalışır. Ollama iki GPU'yu tamamen kullanmaya devam eder.
- **Yeniden sıralama YOK (2026-10-03, ölçüm sonrası kullanıcı kararı C):** CPU'da tam rerank medyan 9,9 sn sürdü. Arama yalnızca vektör benzerliğiyle yapılır (recall@4 28/35, rerank'li 32/35). Zayıf eşiği kosinüs 0,55. Reranker yüklenmez; tahtanın `question` ucu eskisi gibi `hata` döner. §3.1–3.2'deki reranker/`ESIK_RERANK` ifadelerinin yerine bu madde geçerlidir.
- **Erişim:** Arama ucu `0.0.0.0`'da, yerel ağa açık (okul güvenlik duvarı arkasında). Yine de anahtar ister.
- **Gruplar:** İki grup var, Öğretmenler ve İdare. Müdür Yardımcısı modunu yalnızca İdare görür (seçenek A).
- **Arama tetikleme:** Arama bir **filtre** (Open WebUI inlet) ile her mesajda otomatik yapılır. Tool çağrısı kullanılmaz.
- **OCR:** tesseract kuruldu (5.5.0, `tur` + `eng`). Taranmış mevzuat ve jpeg dosyaları için kullanılacak.

Kapsam dışı: öğrenci hesapları, psikolojik danışmanlık, "OKUL GÜVENLİĞİ AYLIK RAPORLAR" klasörü (kişisel veri içerebilir, okunmadı), 12. sınıf kitapları (sunucuda yok).

## 2. Mimari

```
Öğretmen ─► Open WebUI :80 ── mod: "Kimya Öğretmeni" (qwen3.8:27b, think:false)
              │ inlet filtresi: farabi_kaynak
              │   POST http://127.0.0.1:8000/api/webui/ara
              │   {kapsam:"kimya", soru:"<son kullanıcı mesajı>"}  + X-Farabi-WebUI-Key
              │        └─ farabi-api: bge-m3 (CPU) → pgvector → reranker (CPU) → ilk 4
              │ ◄── {parcalar:[{metin, kaynak:"Kimya 10, s. 84", skor}], sure_ms}
              │ parçalar + "kaynak göster" talimatı sistem mesajına eklenir
              └─► Ollama qwen3.8:27b ─► cevap
```

Servis sınırları değişmez. Open WebUI ile farabi-api HTTP ve anahtar üzerinden konuşur, kod paylaşmazlar (kök CLAUDE.md, "servisler arası bağ = HTTP + HMAC/anahtar").

## 3. Bileşenler

### 3.1 farabi-api: CPU'da RAG

- `main.py`: `RAG_AKTIF = True`, `EMBED_DEVICE = RERANK_DEVICE = "cpu"`. CPU'da fp32 çalışır; `.half()` yalnızca CUDA'da uygulanır.
- **Yan etki:** Tahtaların `/api/egitim/question` ucu (`kitap_sorusu`) yeniden çalışmaya başlar, bu sefer CPU üzerinden.
- **Ölçüm kapısı (uygulamanın ilk adımı):**
  - Sorgu başına arama ve rerank süresi ölçülür. Hedef: 3 saniyenin altı.
  - `benchmark/` altındaki 40 soruluk set CPU'da yeniden koşulur. Beklenen sonuç: 38/40, yani GPU ile aynı.
  - Gerekirse `torch.set_num_threads` ayarlanır.
  - Hedef tutmazsa durulur ve kullanıcıya dönülür.

### 3.2 Yeni uç: `POST /api/webui/ara`

- **Dosya:** Yeni router `server/webui.py`. Mevcut `RagMotoru` yeniden kullanılır.
- **Yeni metot:** `RagMotoru.ara(conn, kitap_idler, soru, kaynak="egitim"|"idari")`. Embedding, arama ve rerank yapar, LLM'e gitmez. `sorgula()`'daki arama mantığı bu metoda ayrılır ve `sorgula()` onu çağırır. Tahta davranışı değişmez; `test_rag.py` bunu doğrular.
- **Girdi:**
  - `kapsam`: `genel | kimya | fizik | biyoloji | matematik | edebiyat | ingilizce | felsefe | din | tarih | cografya | idari`
  - `soru`: en fazla 2000 karakter; fazlası kırpılır. Bu sınırın sebebi, uzun metinde reranker'ın OOM'a düşmesi (2026-08-11).
  - `sinif`: isteğe bağlı.
- **Kapsamdan kitaplara eşleme:** `kitap.ders` alanına göre yapılır. `matematik` kapsamı "Temel Matematik"i de içerir. `tarih` kapsamı Tarih 9, 10, 11 ve 12. Sınıf T.C. İnkılap Tarihi ve Atatürkçülük'ü kapsar. `cografya` kapsamı Coğrafya 9, 10, 11'i kapsar. Almanca modunda `kapsam` boştur: sunucuda Almanca kitabı yok, filtre arama yapmaz ve model genel bilgiyle çalışır; kitap gelince kapsam eklenir. `genel` kapsamı kitabı olan on branşın tüm kitaplarını kapsar. Felsefe'de yalnızca Felsefe 10, Din Kültürü'nde yalnızca Din Kültürü ve Ahlak Bilgisi 9 var.
- **Sınıf filtresi:** Filtre mesajda "10. sınıf", "10.sınıf" ya da "10-A" gibi bir ifade bulursa `sinif` gönderilir. O sınıfın kitabı yoksa filtre uygulanmaz.
- **Arama:**
  - Arama `kitap_id = ANY(%s)` ile yapılır. Kitap başına ilk-K değil, birleşik ilk 20 aday alınır; `chunk_tablo` adayları da eklenir. Rerank sonrası ilk 4 parça döner.
  - **Eşik:** Tahtadaki gibi `ESIK_RERANK = 0,5` kullanılır, ama eşik altı sonuçta "cevap verme" denmez. Yanıt `{parcalar: [], durum: "zayif"}` döner ve filtre modele "kitapta bulunamadı" bilgisini verir.
- **Çıktı:** `{durum: "ok"|"zayif"|"hata", parcalar: [{metin, kaynak, sayfa, skor}], sure_ms}`.
  - `kaynak` örnekleri: "Kimya 10, s. 84" ya da "Ortaöğretim Kurumları Yönetmeliği, s. 12".
- **Kimlik doğrulama:** `X-Farabi-WebUI-Key` başlığı, `config/api_keys.json::webui_key` ile karşılaştırılır (gitignore'lu; dosya her istekte okunur, `auth.py` deseni). Tahta anahtarı bu uçta geçmez, `webui_key` de `/api/egitim/*` uçlarında geçmez.
- **Loglama:** `metrik` tablosuna yalnızca süre, durum ve skor yazılır. `soru_log`'a yazılmaz; öğretmen soruları tahta loglarıyla karışmasın.
- **Hata:** RAG modelleri yüklenmemişse ya da DB hatası olursa `{durum: "hata"}` döner. Filtre bu durumda aramasız devam eder: Open WebUI asla düşmez.

### 3.3 `chunk_idari` (mevzuat)

- **Şema** (`server/schema_idari.sql`):
  - `idari_belge(id bigserial, ad text, dosya_yolu text, hash text, tur text, indekslendi_at timestamptz)`
  - `chunk_idari(id bigserial, belge_id bigint, sayfa_no int, metin text, embedding vector(1024))`
  - `belge_id` üzerinde indeks.
  - Vektörler `chunk_egitim` ile aynı biçimde (1024 boyutlu bge-m3, normalize).
- **Yükleme betiği:** `server/idari_yukle.py`. Klasör: `/mnt/farabi-data/farabi/mudur/`; alt klasörler hariç, yani güvenlik raporları girmez.
  - PDF: PyMuPDF ile sayfa metni alınır. 50 karakterin altındaki sayfalarda tesseract (`tur`, 300 dpi) çalışır.
  - jpeg: tesseract.
  - docx: `python-docx` ile okunur; yoksa `unzip` ile `word/document.xml` ayrıştırılır. Yeni bağımlılık eklenirse onay alınır (Kural 8).
  - Parçalama: sayfa sınırını aşmaz (RAG kuralı). `embed_kitap.py`'deki parça boyu ve örtüşme aynen kullanılır.
  - Hash aynıysa belge atlanır, değişmişse eski parçalar silinip yeniden yüklenir. `--kuru` seçeneği yalnızca listeler.
- **Belge adları:** Dosya adından üretilir ve tabloda elle düzeltilebilir. Örnek: `yazıı ve uygulamalı sınavlar yönergesi.pdf` → "Yazılı ve Uygulamalı Sınavlar Yönergesi".
- **Dahil edilecek belgeler (16):**
  - Ortaöğretim Kurumları Yönetmeliği
  - Resmî Yazışma Kuralları
  - Türkiye Yüzyılı Maarif Modeli
  - Yazılı ve Uygulamalı Sınavlar Yönergesi
  - Zümre Yönergesi
  - İOKBS 2024
  - DYK
  - Ek Ders Kararı
  - e-Okul Rehberi
  - Kılık-Kıyafet Yönetmeliği (pdf ve docx)
  - Okul Kıyafetleri Yönetmeliği (docx)
  - Sınıf Rehber Öğretmeni Görevleri (docx)
  - Egzersiz Yönetmeliği (OCR)
  - Su Verimliliği Yönetmeliği (OCR)
  - Ders Giriş-Çıkış Saatleri Çizelgesi
  - NORM BRANŞ SAAT (jpeg, OCR)
  - Açık Lise Geçiş 2023 (jpeg, OCR)

### 3.4 Open WebUI filtresi: `openwebui/farabi_filtre.py`

- Open WebUI "Function" (filter) olarak yüklenir. Valves alanlarında `api_url`, `api_key`, `zaman_asimi_sn=8` ve `kapsam` bulunur. `kapsam` her modda ayrı ayarlanır; model meta verisinden okunur.
- **`inlet` adımı:**
  - Son kullanıcı mesajı alınır ve `/api/webui/ara` çağrılır.
  - Sonuç `ok` ise parçalar şu kalıpla sistem mesajının sonuna eklenir: "Kaynaklar (yalnızca ilgiliyse kullan, kullandığında kaynağı belirt): [1] Kimya 10, s. 84: …". Sonuç `zayif` ise "Bu soru için kitapta/mevzuatta ilgili bölüm bulunamadı; genel bilginle cevap verdiğini belirt." notu eklenir.
  - Zaman aşımı ya da hata olursa hiçbir şey eklenmez ve mesaj olduğu gibi geçer.
- Sohbet geçmişi büyüdükçe yalnızca son mesaj aranır. Bağlamı korumak için eklenen kaynak bloğu en fazla yaklaşık 2.500 token tutar.

### 3.5 Modlar ve promptlar: `openwebui/`

```
openwebui/
  modlar.json            # id, ad, kapsam, think, gruplar, açıklama, prompt eki dosyası
  promptlar/cekirdek.md  # ortak: kişilik, okul, şehidimiz, kurallar, üslup
  promptlar/<mod>.md     # branş/rol eki
  farabi_filtre.py
  kur.py                 # Open WebUI API ile idempotent kurulum
```

| id | Ad | Kapsam | think | Gruplar |
|---|---|---|---|---|
| farabi | Farabi | genel | false | Öğretmenler, İdare (varsayılan model) |
| farabi-derin | Farabi – Derin Düşünme | genel | true | Öğretmenler, İdare |
| farabi-kimya | Kimya Öğretmeni | kimya | false | Öğretmenler, İdare |
| farabi-fizik | Fizik Öğretmeni | fizik | false | Öğretmenler, İdare |
| farabi-biyoloji | Biyoloji Öğretmeni | biyoloji | false | Öğretmenler, İdare |
| farabi-matematik | Matematik Öğretmeni | matematik | false | Öğretmenler, İdare |
| farabi-edebiyat | Edebiyat Öğretmeni | edebiyat | false | Öğretmenler, İdare |
| farabi-ingilizce | İngilizce Öğretmeni | ingilizce | false | Öğretmenler, İdare |
| farabi-felsefe | Felsefe Öğretmeni | felsefe | false | Öğretmenler, İdare |
| farabi-din | Din Kültürü Öğretmeni | din | false | Öğretmenler, İdare |
| farabi-tarih | Tarih Öğretmeni | tarih | false | Öğretmenler, İdare |
| farabi-cografya | Coğrafya Öğretmeni | cografya | false | Öğretmenler, İdare |
| farabi-almanca | Almanca Öğretmeni | — (kitap yok, arama yapılmaz) | false | Öğretmenler, İdare |
| farabi-mudur-yrd | Müdür Yardımcısı | idari | false | **Yalnızca İdare** |

- **Çekirdek prompt:** `server/ollama/farabi_webui_sistem.txt` temel alınır. "Sen Farabi'sin", "sen" diye hitap, kişilik, okul bilgisi, şehidimiz, uydurmama, siyasi/dinî tarafsızlık, kişisel veri uyarısı, kriz durumunda idareye ve 112'ye yönlendirme kuralları korunur. Öğrenciye yönelik kurallar (ödev cevabı vermeme vb.) çıkarılır.
- **Branş öğretmeni ekleri:** Ders planı, kazanım odaklı etkinlik, cevap anahtarlı soru, rubrik, çalışma kâğıdı, kitaptan konu özeti. Kaynak kullanıldığında "Kimya 10, s. 84" biçiminde belirtilir. İngilizce modunda üretim İngilizce, açıklama Türkçe yapılır.
- **Almanca eki:** Üretim Almanca, açıklama Türkçe. Kitap kaynağı olmadığı için kitap/sayfa atfı yapılmaz; seviye (A1–B1) öğretmene sorulur.
- **Din Kültürü eki:** Konular MEB Din Kültürü ve Ahlak Bilgisi programı ve kitabı çerçevesinde, bilgilendirici ve nesnel bir dille anlatılır; vaaz ya da dinî hüküm (fetva) verilmez, mezhepler ve inançlar arasında taraf tutulmaz. Çekirdek prompttaki "dinî tartışmalarda tarafsızlık" kuralı bu modda ders içeriğini anlatmayı engellemez, yalnızca tartışmada taraf tutmayı engeller.
- **Müdür Yardımcısı eki:** Resmî yazı (Resmî Yazışma Kuralları'na uygun), tutanak, duyuru, nöbet ve çizelge işleri. Mevzuata atıfta belge adı ve sayfa verilir, madde numarası uydurulmaz; güncellik için resmî kaynağın kontrol edilmesi önerilir.
- **Uzunluk:** Çekirdek prompt yaklaşık 1.000 token, her ek 300 token'ın altında. 16k bağlamın yaklaşık 2,5k'sı kaynak bloğuna ayrılır.

### 3.6 `kur.py`: Open WebUI kurulumu

Resmi API'yi kullanır ve tekrar çalıştırılabilir: var olanı günceller, olmayanı oluşturur.
- **Gruplar:** "Öğretmenler" ve "İdare" grupları yoksa oluşturulur.
- **Filtre:** Function olarak yüklenir ya da güncellenir; valves değerleri girilir.
- **Modeller:** 14 model oluşturulur ya da güncellenir. Her birinde temel model `qwen3.8:27b`, `params.system` (çekirdek + ek), filtre bağlantısı ve meta verisi (`farabi_kapsam`, `farabi_think`) bulunur. **Düşünme `params`'a konmaz** (2026-10-03 kod incelemesi): Open WebUI model parametrelerini sohbet ayarlarının üzerine yazdığı için sohbetteki düğme çalışmazdı. Varsayılanı, kullanıcı sohbette seçim yapmadıysa filtre verir. Erişim izinleri grup bazında verilir.
- **Varsayılan model:** `farabi`.
- **Arka plan görevleri:**
  - Etiket ve takip sorusu üretimi kapatılır.
  - Başlık üretimi açık kalır, ama düşünmeden çalışır: görev modeli `farabi` olarak ayarlanır; bunun düşünmeyi kapattığı doğrulanacak.
- **Hesaplar:** `Öğretmen` ve `İdare` ortak hesapları oluşturulur ya da güncellenir ve gruplarına eklenir (§6).
- **Kullanıcı izni:** Öğretmenler grubuna "sohbet kontrolleri" izni verilir. Kullanıcı bir sohbette düşünmeyi `think (Ollama)` ile açabilir.
- **Ham `qwen3.8:27b`:** Kullanıcılardan gizlenir, yalnızca yönetici görür.

**Kimlik bilgisi:** Open WebUI yönetici API anahtarı. Kullanıcı arayüzden API anahtarlarını açıp bir anahtar oluşturur; anahtar `openwebui/.env` dosyasına yazılır (gitignore'lu, `*.env` deseni). Kimlik doğrulama token'ı **üretilmez**; bunun nedeni 2026-10-03'teki izin reddi.

## 4. Hata durumları

| Durum | Davranış |
|---|---|
| farabi-api kapalı ya da yavaş (>8 sn) | Filtre aramasız geçer, model genel bilgiyle cevaplar |
| Eşik altı arama sonucu | Model "kitapta bulamadım" diyerek genel bilgiyle cevaplar |
| `webui_key` yanlış | 401 döner, filtre aramasız geçer, Open WebUI loguna uyarı düşer |
| OCR boş metin üretirse | O sayfa atlanır, betik raporunda listelenir |
| RAG modelleri CPU'da yüklenemezse | `/api/webui/ara` ve tahta `question` ucu `hata` döner (bugünkü kapalı RAG davranışı); diğer uçlar etkilenmez |

## 5. Test ve doğrulama

1. **CPU ölçümü (kapı):** Süre ve 40 soruluk set (38/40) doğrulanır.
2. **`server/tests/test_webui.py`** (conftest sahteleri kullanılır, gerçek GPU ya da DB'ye gidilmez):
   - Anahtar kontrolü; tahta anahtarının reddedilmesi.
   - Kapsamdan kitap eşlemesi.
   - Sınıf filtresi.
   - Eşik altında `zayif` dönmesi.
   - Uzun sorunun kırpılması.
   - Hata durumunda `hata` dönmesi.
3. **`test_rag.py`:** Eksiksiz geçmeli; `sorgula()` davranışı değişmemeli.
4. **`idari_yukle.py --kuru`:** Belge listesi ve OCR'lı sayfa sayıları gözden geçirilir. Gerçek yüklemeden sonra mevzuattan 10 örnek soruyla elle kontrol yapılır.
5. **Open WebUI uçtan uca:**
   - Her modda bir soru sorulur; kaynak etiketi ve ilk kelime süresi ölçülür. Hedef: düşünme kapalıyken 5 saniyenin altı.
   - İdare dışı bir kullanıcının Müdür Yardımcısı modunu görmediği kontrol edilir.
   - Sohbet içinden `think (Ollama)` ile düşünmenin açılabildiği doğrulanır.
6. **Tahta regresyonu:** `kitap_sorusu`, bir tahtada fiziksel olarak Atakan tarafından test edilir (Kural 12).

## 6. Hesaplar ve açık konular

**Hesap modeli (kullanıcı kararı 2026-10-03, seçenek A):**
- İki **ortak hesap** olacak: `Öğretmen` (Öğretmenler grubu) ve `İdare` (İdare grubu). `kur.py` bu hesapları, `openwebui/.env` içindeki ortak şifrelerle oluşturur.
- Her cihazda bir kez giriş yapılır. Oturum `auth.jwt_expiry` süresince, yani 4 hafta açık kalır; pratikte şifre sorulmaz.
- Öğretmen branşını ya da rolünü sohbetin başında **model listesinden** seçer. İsimler giriş için kullanılmaz.
- **Bilinen bedel:** Öğretmen hesabındaki sohbetleri o hesabı kullanan herkes görür. Öğretmenlere bu söylenmeli.
- **Mevcut kullanıcı:** Arzu'nun mevcut kişisel hesabı silinmez, Öğretmenler grubuna eklenir. Yönetici hesabı (Atakan) değişmez.
- Şifresiz isim listesi (B) ve girişin tamamen kapatılması (C) reddedildi. B yeni bir ara katman gerektiriyordu; C herkesi yönetici yapıyordu.

**Öğretmen listesi (bilgi amaçlı):**
- Emine (Kimya), Gözde (Fizik), Merve (Biyoloji), Melek ve Fatma (Matematik), Elif, Zehra ve Ayşe (Edebiyat), Gonca (Felsefe), Muharrem (Din Kültürü), Sedat (Tarih), Özlem (Coğrafya), Arzu ve Safiye (İngilizce), Feride (Almanca). Toplam 15 öğretmen.
- Her branş modunun en az bir öğretmeni var.

**Açık konu:**
- **Open WebUI yönetici API anahtarı:** Kullanıcı Yönetici Paneli → Ayarlar'dan API anahtarlarını açıp bir anahtar oluşturur. Bu anahtar ve iki ortak hesabın şifresi `openwebui/.env` dosyasına yazılır. Bu adım `kur.py`'den önce yapılmalı.

## 7. Uygulama notları

- Kök CLAUDE.md Kural 11 gereği uygulama planı Opus ile yazılır, kod Sonnet ile yazılır.
- Kural 3 gereği tek seferde tek modül değiştirilir. Sıra:
  1. CPU ölçümü
  2. `rag.py` içinde `ara()` ayrımı
  3. `webui.py`
  4. `chunk_idari` ve yükleme
  5. Filtre ve `kur.py`
- **Yedek:** Open WebUI DB'si (`/opt/open-webui/data/webui.db`) `kur.py`'nin ilk çalıştırılmasından önce yedeklenir.
