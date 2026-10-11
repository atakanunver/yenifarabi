# Farabi — RAG/Veri Kontrolü (2026-09-13, yarın 14.09.2026 canlı ders öncesi)

Kontrol talebi: kitaplar/sorular/yıllık planların Farabi tarafından kullanılıp
kullanılmadığının doğrulanması, yıllık planların tarih güncellemesi, tam RAG
kontrolü (kitap + kazanım erişimi), 9-A/11-B/12-A'ya SSH ile bağlanıp gerçek
RAG server + data erişiminin test edilmesi. Bulgular aşağıda madde madde;
her madde ne / kanıt / yarını engelliyor mu / önerilen adım formatında.

## 1. Yıllık plan + kazanım — RAG'e hiç bağlı değil (bilgi amaçlı, engel değil)

**Ne:** `/mnt/farabi-data/farabi/icerik/plan.json` (yıllık plan) ve DB'deki
`kazanim` (208 satır), `yillik_plan` (0 satır), `ders_programi` (0 satır),
`sinif_kitap` (0 satır) tabloları Farabi'nin canlı ders davranışını
ETKİLEMİYOR. Konu/kazanım yalnızca öğretmenin sesli/yazılı girdisinden gelir
(`client/main.py`, `konu:`/`kazanım:` regex'i) — kod, dosyadan ya da DB'den
otomatik kazanım/konu türetmiyor. Bu, kasıtlı bir mimari karar (bkz.
`client/CLAUDE.md`: "yıllık plan pipeline'ı kaldırıldı, tekrar eklenmeyecek").

**Kanıt:**
- `grep -rn "yillik_plan\|kazanim" server/*.py` → server tarafında SIFIR
  referans (test dosyaları hariç).
- `select count(*) from yillik_plan` → 0. `select count(*) from
  ders_programi` → 0. `select count(*) from sinif_kitap` → 0.
- client'taki `kazanim`/`kazanim_kodu` alanları yalnızca öğretmenin o an
  yazdığı serbest metni taşıyor (`main.py:570` civarı), DB'ye bağlı değil.

**Yarını engelliyor mu:** Hayır. Zaten hiç kullanılmıyordu, yarın da
kullanılmayacak — bu bir eksiklik değil, tasarım.

**Yapılan (başka bir oturum tarafından, ben devraldığımda bitmişti):**
`plan.json` yedeklendi (`plan.json.bak.20260913`) ve içindeki ders
kayıtlarının tarihleri +371 gün kaydırıldı (en erken yeni tarih:
2026-09-14). **Bunun hiçbir işlevsel etkisi yok** (dosya hiç okunmuyor) —
yalnızca dosyanın kendisi güncel görünsün diye yapılmış bir hijyen işlemi.
Zararsız, geri alınabilir (`.bak` dosyası duruyor).

**Öneri:** Bir şey yapmaya gerek yok. İleride konu/kazanımın yıllık plandan
otomatik gelmesi isteniyorsa bu ayrı, kasıtlı bir mimari karar gerektirir
(mevcut tasarımın tam tersi yönde) — bugünkü kontrolün kapsamı dışında.

## 2. Kitap/RAG erişimi — 9-A, 11-B, 12-A'nın KENDİSİNDEN test edildi, ÇALIŞIYOR

**Ne:** Üç tahtaya da `server/tahta-ssh.sh` ile bağlanıp, tahtanın kendi
`config/api_keys.json`'ındaki gerçek `sunucu_url` + `tahta_anahtari` ile
GERÇEK bir `POST /api/egitim/question` isteği gönderildi (yalnızca
`/health` değil — o auth'a bağlı değil, yanıltıcı olurdu).

**Kanıt (gerçek istek/yanıt, tahtanın kendisinden):**
- **9-A** → `kitap_id=1` (biyoloji-9), soru "Hücre zarının görevi nedir?"
  → HTTP 200, `status: ok`, kaynaklı cevap döndü.
- **12-A** → `kitap_id=26` (Fizik-11), soru "Serbest düşme hareketinde ivme
  neye eşittir?" → HTTP 200, `status: ok`, 4 kaynak sayfa (s.20/24/30/48),
  gecikme 7,6 sn.
- **11-B** → `kitap_id=30` (Türk Dili ve Edebiyatı-11), soru "Roman türünün
  özellikleri nelerdir?" → HTTP 200, `status: ok`, kaynaklı cevap döndü.
- Üçü de `GET /api/egitim/kitaplar` ile 22-25 kitaplık gerçek katalogu
  görüyor (auth header doğru gönderiliyor, 401 YOK).
- `tahta_durum` tablosu: üçü de bugün 12:29 UTC civarı heartbeat atmış,
  canlı.

**Yarını engelliyor mu:** Hayır — üç tahtanın da RAG'e erişimi tam
çalışıyor durumda, gerçek istekle doğrulandı (varsayımla değil).

**Not (önceki oturumun "kritik risk" uyarısı, ŞİMDİ KAPANDI):** 11-B/12-A
için "placeholder board_key olabilir, 401 riski var" diye bir uyarı vardı —
canlı testle bu risk GERÇEKLEŞMEDİ, üçünün de gerçek anahtarı doğru
tanınıyor. Endişe yersizmiş, ama test edilmeden bilinemezdi — iyi ki test
edildi.

## 3. YENİ EKLENEN 6 kitap — 11. sınıf, hepsi işlendi ve RAG'e alındı

**Ne:** Kullanıcının `/mnt/farabi-data/farabi/kitaplar/`'a bıraktığı 6 yeni
11. sınıf kitabı (bozuk otomatik dosya adlarıyla gelmişti) mevcut
kısayol dosya adı düzenine göre yeniden adlandırıldı, kapak sayfasından
gerçek başlıkla doğrulandı, `icerik/kitaplar.json`'a eklendi (yedek alındı:
`kitaplar.json.bak.20260913`), metne çevrildi ve pgvector'a embed edildi:

| Dosya | Ders (DB) | kitap_id | chunk sayısı |
|---|---|---|---|
| cografya-11.pdf | Coğrafya | 25 | 477 |
| fizik-11.pdf | Fizik | 26 | 711 |
| kimya-11.pdf | Kimya | 27 | 592 |
| tarih-11.pdf | Tarih | 28 | 679 |
| temel-matematik-11.pdf | Temel Matematik | 29 | 295 |
| turk-dili-ve-edebiyati-11.pdf | Türk Dili ve Edebiyatı | 30 | 488 |

Toplam: DB'de 25 kitap, 11968 chunk. Hepsi `indekslendi_at` dolu (tamamlanmış).

**Kanıt:** Yukarıdaki tablo `select ... from kitap` ile doğrulandı; her
kitap için gerçek bir RAG sorusu (madde 2) başarıyla cevaplandı.

**Yarını engelliyor mu:** Hayır — tam tersi, bu kitaplar olmadan yarın
12-A/11-B'nin fen/matematik/edebiyat derslerinde RAG hiç çalışmayacaktı.

## 4. BULUNDU VE DÜZELTİLDİ: "seçmeli X" ders adları RAG'de eşleşmiyordu

**Ne:** Bu oturumda daha önce üretilen `ders_programi.json`'da 11-A/11-B/
12-A gibi seçmeli-ağırlıklı sınıflar için ders adları "seçmeli fizik",
"seçmeli kimya" gibi yazılmıştı. `kitap_sorusu`'nun kitap eşleştirmesi
(`client/actions/ders_icerigi.py::_ders_eslesir`) sorgudaki HER kelimenin
kitabın `ders` alanında (ör. "Fizik") alt dize olarak geçmesini şart
koşuyor — "seçmeli" kelimesi "Fizik" içinde hiç geçmediği için eşleşme
HER ZAMAN başarısız oluyordu.

**Kanıt (canlı DB'ye karşı ölçüldü, düzeltmeden ÖNCE):**
```
ders='seçmeli fizik'    -> kitap_id=None
ders='seçmeli kimya'    -> kitap_id=None
ders='seçmeli biyoloji' -> kitap_id=None
```
Yarın (Pazartesi) 12-A'nın İLK 3 blok dersi (1-2. ders seçmeli fizik,
3-4. ders seçmeli kimya, 6-7. ders seçmeli biyoloji) ve 11-B'nin 1-2. dersi
(seçmeli türk dili ve edebiyatı) tam olarak bu kalıba giriyordu.

**Yarını engelliyor muydu:** EVET, düzeltilmeden önce — 12-A'nın günün
büyük kısmında `kitap_sorusu`/`ders_icerigi` kitap bulamayıp Farabi'yi
"kısıtlı devam" moduna (ders bozulmaz ama kaynaklı cevap veremez, konuyu
kendi bilgisiyle/`web_search` ile anlatmak zorunda kalır) düşürecekti.

**Yapılan düzeltme:** `mudur/ders_programi_yukle.py`'deki `KISALTMALAR`
sözlüğünden "seçmeli " öneki tamamen kaldırıldı (bu önek benim kendi
tercihimdi, kullanıcıdan gelen bir gereksinim değildi — kitabın içeriği
zaten seçmeli/zorunlu ayrımı yapmıyor, aynı MEB kitabı). `ders_programi.json`
yeniden üretilip 9-A/11-B/12-A'ya tekrar dağıtıldı. Düzeltmeden SONRA aynı
test:
```
ders='fizik' (12-A, 1. ders)  -> kitap_id=26  ✓
ders='kimya' (12-A, 3. ders)  -> kitap_id=27  ✓
```

**Öneri:** Bir şey yapmana gerek yok, düzeltildi ve redeploy edildi. İleride
"öğrenciye/veliye seçmeli/zorunlu ayrımını sözlü duyur" gibi ayrı bir istek
gelirse bu ayrı bir konu (RAG eşleşmesini bozmayan bir yolla — ör. sunum
esnasında ayrı bir kip/etiket, ders adının kendisi değil) olarak ele
alınmalı.

## 5. Yarın (14.09.2026, Pazartesi) hangi dersler RAG kaynaklı, hangileri değil

Kitap eşleştirmesi gerçek algoritmayla, gerçek DB'ye karşı hesaplandı:

### 9-A (9. sınıf)
| Saat | Ders | Kitap var mı |
|---|---|---|
| 1-2 | İngilizce | ✓ |
| 3-4 | Din Kültürü ve Ahlak Bilgisi | ✓ |
| 5-6 | Görsel Sanatlar | ✗ kitap yok |
| 7 | Spor Etkinlikleri | ✗ kitap yok |
| 8 | Sağlık Bilgisi ve Trafik Kültürü | ✗ kitap yok |

### 11-B
| Saat | Ders | Kitap var mı |
|---|---|---|
| 1-2 | Türk Dili ve Edebiyatı | ✓ (yeni eklenen kitap) |
| 3-4 | Görsel Sanatlar | ✗ kitap yok |
| 5-6 | İngilizce | ✗ **11. sınıf İngilizce kitabı hiç yok** (yalnızca 9. sınıf Waymark kitabı var) |
| 7-8 | Psikoloji | ✗ kitap yok (seçmeli ders, MEB kitabı hiç sağlanmamış) |

### 12-A
| Saat | Ders | Kitap var mı |
|---|---|---|
| 1-2 | Fizik | ✓ (yeni eklenen kitap) |
| 3-4 | Kimya | ✓ (yeni eklenen kitap) |
| 5 | Sınav Hazırlık Çalışması | ✗ kitap yok (kitap gerektirmiyor zaten) |
| 6-7 | Biyoloji | ✗ **11. sınıf Biyoloji kitabı hiç yok** (yalnızca 9./10. sınıf var) |
| 8 | Türk Dili ve Edebiyatı | ✓ (yeni eklenen kitap) |

**Önemli — "kitap yok" bir ÇÖKME değil:** `ders_icerigi`/`kitap_sorusu`
kitap bulamadığında Farabi'ye "kaynaklı sayfa yok, kazanım metnine sadık
kalarak `web_search` ile derinleştir" talimatı döner (`_SINIRLI_DEVAM`) —
ders durmaz, yalnızca o saatte kitap alıntısı/sayfa gösterimi olmaz.

**Yarını engelliyor mu:** Görsel Sanatlar/Spor/Sağlık için hayır (bu
sistemde hiçbir sınıf seviyesinde bu derslerin kitabı yok, yeni bir eksiklik
değil). **11. Sınıf Biyoloji ve 11. Sınıf İngilizce için EVET, bir içerik
boşluğu** — 12-A yarın 2 ders saati biyolojiyi, 11-B 2 ders saati
İngilizceyi kitapsız işleyecek.

**Öneri:** Biyoloji-11 ve İngilizce-11 (varsa) ders kitabı PDF'i
`/mnt/farabi-data/farabi/kitaplar/`'a bırakılırsa aynı yöntemle (bu
oturumdaki 6 kitapla uygulanan) hızlıca RAG'e eklenebilir — bugünkü kapsamda
DEĞİL çünkü kaynak dosya hiç yoktu, uydurulmadı.

## 6. Veri bütünlüğü — kimya-11 chunk sayısı geçici bir okuma tutarsızlığıydı, gerçek sorun değil

Embed işi sürerken (satır satır commit ediliyor) ara sırada okunan chunk
sayısı (352) ile bitişteki sayı (592) farklı görününce paralel bir
yarış durumu şüphesi doğdu (aynı anda kapatılan başka bir oturum da bu
klasörde çalışıyordu). **Temizden tekrar çalıştırılıp doğrulandı: iki
tam koşuda da 592 chunk** — yarış değilmiş, yalnızca işlem sürerken
yapılan ara okumaydı. Şu an tek, tutarlı bir kayıt var, ekstra/yinelenen
satır yok.

## Özet — yarın için durum

- RAG server + auth + kitap erişimi: **9-A, 11-B, 12-A'nın üçünde de
  çalışıyor**, gerçek istekle doğrulandı.
- Yeni 6 kitap: **tamamı RAG'e alındı**, sorgulanabilir.
- Kritik bir eşleşme hatası (**seçmeli X ders adları**) bulundu ve
  düzeltildi — düzeltilmeseydi 12-A'nın günün büyük kısmı etkilenecekti.
- Yıllık plan/kazanım: zaten kullanılmıyor, dokunulmasına gerek yoktu,
  dokunulması da zarar vermedi.
- Kalan tek gerçek boşluk: **11. Sınıf Biyoloji ve İngilizce kitabı yok** —
  kaynak PDF sağlanırsa aynı gün eklenebilir.
