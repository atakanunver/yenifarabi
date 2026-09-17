# Eylül 2026 — Farabi Projesi Genel Analiz

**Tarih:** 2026-09-17 (canlı, farabi.local üzerinde SSH ile yapıldı)
**Kapsam:** `/home/ata/farabi` altındaki tüm alt projeler (client, server,
benchmark, mudur, tahtaayar, tahtayoklama) + 11 akıllı tahtaya canlı bağlantı
testi. Özellikle derinlemesine incelenen: **tahtayoklama/dashboard —
"Uzaktan Yönetim" paneli** (kullanıcı talebi üzerine).

Bu doküman **tek seferlik bir denetim raporudur**, `CLAUDE.md`/`DECISIONS.md`
gibi kalıcı proje belgelerinin yerine geçmez — onlarda zaten belgeli olan
konular burada özetlenip kaynak gösterilmiştir, tekrar uzun uzun anlatılmamıştır.

---

## 1. Genel durum özeti

- Repo `git` ile izleniyor, `origin/master`'ın **3 commit ilerisinde**
  (henüz push edilmemiş).
- **Çalışma dizininde commit edilmemiş değişiklikler var** (bkz. §5) —
  2026-09-15'ten beri bekliyor, iki gündür commit edilmemiş.
- 7 aktif sınıf tahtasının 7'sinde de Farabi (sesli ders) + tahtayoklama
  kurulu ve `client/tests/` 151/151 geçiyor (DECISIONS.md, 2026-09-15).
- Canlı bağlantı testinde (bugün ~06:10 TR) 11 tahtanın **7'si ayakta**,
  4'ü ("No route to host") kapalı/ağda değil — bkz. §2.

## 2. Canlı tahta/istemci bağlantı testi

`tahtayoklama/dashboard`'un kendi `uzaktan_yonetim.tum_durumlar()`
fonksiyonu doğrudan çalıştırılarak (gerçek SSH, gerçek tahtalar) elde
edilen sonuç:

| Tahta | IP | Ulaşılabilir | Oturum | Yoklama | Chrome | Ekran |
|---|---|---|---|---|---|---|
| 9-A | .245 | ✗ (No route to host) | — | — | — | — |
| 9-B | .239 | ✓ | açık | kapalı | kapalı | normal |
| 10-A | .242 | ✓ | açık | **açık** | kapalı | normal |
| 11-A | .228 | ✓ | açık | **açık** | kapalı | normal |
| 11-B | .233 | ✓ | açık | kapalı | **açık** | normal |
| 12-A | .231 | ✓ | açık | kapalı | kapalı | normal |
| 12-B | .240 | ✓ | açık | kapalı | kapalı | normal |
| tahta-234 | .234 | ✗ | — | — | — | — |
| tahta-235 | .235 | ✗ | — | — | — | — |
| tahta-236 | .236 | ✗ | — | — | — | — |
| tahta-244 | .244 | ✓ | açık | kapalı | kapalı | **karartılmış** |

**Sonuç:** Uzaktan Yönetim panelinin durum-tarama mekanizması **gerçek
donanıma karşı sorunsuz çalışıyor** — kod incelemesinde bulunan hiçbir
şey bunu değiştirmiyor, üretim davranışı doğru.

**Dikkat çeken noktalar (hata değil, gözlem):**
- `tahta-234/235/236` zaten bilinen biçimde ağda değil (Faz 6 — lab/kütüphane/
  spor odası ya da boşa çıkmış eski kayıt, bkz. `tahtayoklama/CLAUDE.md`).
- `9-A` şu an ("No route to host") ulaşılamıyor — 7 aktif sınıf tahtasından
  biri olduğu için ayrıca not düşülüyor, ama saat sabah 06:10 TR (ders
  saatleri dışı) olduğundan büyük ihtimalle sadece kapalı; bir arıza kanıtı
  değil, yalnızca doğrulanmamış.
- `tahta-244` **açık ve ekranı karartılmış durumda** — biri az önce panodan
  ya da elle bu tahtayı karartmış olabilir; kim/ne zaman/neden bilinmiyor,
  kullanıcıya sorulmalı (aşağıda §4.3'te güvenlik açısından da ele alınıyor).

`tahtaayar/tahta_fix_uygula.py --sadece-kontrol` ile OS-düzeyi
provizyon durumu da canlı tarandı: 7 aktif tahtanın 7'sinde de dört
düzeltme de ("güç tuşu yoksay", "uzun basış yoksay", "uyku hedefleri
maskeli", "cinnamon güç tuşu yoksay") **hâlâ uygulanmış** durumda — burada
bir regresyon yok.

## 3. "Uzaktan Yönetim" paneli — derin kod incelemesi

Kod (`uzaktan_yonetim.py`, `ssh_istemci.py`, `tahta_kaydi.py`,
`uzaktan_baslat.py`) satır satır tasarım belgesiyle
(`docs/superpowers/specs/2026-09-15-tahta-uzaktan-yonetim-design.md`)
karşılaştırıldı.

**Tasarım-kod uyumu:** Spesifikasyondaki her madde (tahta hedeflerinin
yalnızca `server/tahtalar.json`'dan çözülmesi, sudo'suz model, X-ortamı
keşfinin tek kopyaya taşınması, nav linklerinin 5 şablona eklenmesi, dosya
boyutu/uzantı sınırı) **birebir uygulanmış**. Yeni bir kod hatası
bulunmadı — mevcut haliyle işlevsel ve önceden (2026-09-15, 9-A'da) uçtan
uca doğrulanmış (DECISIONS.md).

**Bulunan gerçek sorunlar / riskler:**

1. **Ölü kod: `auth.gecerli_oturum()` hiç çağrılmıyor.**
   `tahtayoklama/dashboard/auth.py:81` — FastAPI dependency tarzında
   yazılmış ama repodaki hiçbir route bunu kullanmıyor (hepsi
   `auth.dogrula()` + elle `raise HTTPException(401, ...)` deseniyle
   tekrar ediyor, bu dosyada da dahil `uzaktan_yonetim.py::_dogrula`).
   Kod hatası değil ama iki paralel auth deseninin bir arada durması
   kafa karıştırıcı — ya `gecerli_oturum` silinmeli ya da tüm route'lar
   ona geçirilmeli.

2. **`/admin/uzaktan*` route'ları oturumsuz istekte çıplak 401 döndürüyor,
   `/` (ana pano) gibi `/giris`'e yönlendirmiyor.** Bu, `admin.py`'nin
   zaten yerleşik davranışı (yeni bir hata değil) ama kullanıcı deneyimi
   açısından tutarsız: tarayıcıdan doğrudan `/admin/uzaktan`'a giden,
   oturumu düşmüş bir kullanıcı FastAPI'nin çıplak hata sayfasını görür,
   giriş formuna yönlendirilmez.

3. **Güvenlik notu (spec'te zaten bilinçli kabul edilmiş bir risk,
   burada yalnızca teyit ediliyor):** Panodaki ortak öğretmen şifresine
   sahip HERKES artık fiziksel tahtaları karartabilir/duvar kağıdını
   değiştirebilir/Chrome açabilir — ayrı bir yönetici rolü yok. Şu anda
   `tahta-244`'ün karartılmış bulunması (bkz. §2) bu riskin soyut değil,
   fiilen kullanılabilir olduğunu gösteriyor. Öneri: en azından "kim,
   ne zaman, hangi eylemi, hangi tahtaya yaptı" bir log satırı
   (`print`/dosya, ağır bir audit sistemi değil) eklenmesi düşünülebilir
   — şu an hiçbir eylem loglanmıyor, `sorunlar.md`/`DECISIONS.md`'de de
   bu konuda bir not yok.

4. **Küçük verimsizlik:** `_yoklama_ac_tek()` önce `_python_yolu_bul()`
   ile bir SSH round-trip yapıyor, sonra çağırdığı `uzaktan_baslat.baslat()`
   içeride **ayrıca** `x_ortamini_kesfet()` ile bir round-trip daha
   yapıyor — işlevsel bir hata değil (sonuç doğru), yalnızca "Yoklama Aç"
   eylemini gereğinden 1 SSH turu kadar yavaşlatıyor.

## 4. Diğer projelerde bulunan/teyit edilen sorunlar

Bunların çoğu zaten `DECISIONS.md`/`sorunlar.md`/`tahtaayar/CLAUDE.md`'de
kayıtlı; burada yalnızca bu oturumda **canlı doğrulanan güncel durumları**
veya **yeni fark edilen** noktalar var.

4.1. **`tahta-244`'te OS-düzeyi güvenlik düzeltmeleri hiç uygulanmamış**
(yeni bulgu, bugün): `guc_tusu_yoksay`, `guc_tusu_uzun_basis_yoksay`,
`uyku_hedefleri_maskeli` üçü de "UYGULANMAMIŞ" çıktı verdi (yalnızca
`cinnamon_guc_tusu_yoksay` uygulanmış). Bu, kasıtlı bir kapsam dışı
bırakma olabilir (tahta-234/235/244 sınıf değil, fen-lab/kütüphane/spor —
bkz. Faz 6) ama **tahta-244 şu an açık, aktif kullanımda ve karartılmış**
durumda bulundu (§2) — yani biri orada fiilen ders/etkinlik yapıyor
olabilir ve güç düğmesine basarsa tahta anında kapanır. Kullanıcıya
sorulmalı: bu 3 oda artık kullanılıyor mu, kullanılıyorsa güç düğmesi
fix'i onlara da uygulansın mı?

4.2. **İki farklı tahta güncelleme mekanizması senkron değil**
(DECISIONS.md 2026-09-06'dan beri açık): 9-A'nın kendi
`~/.local/bin/farabiguncelle.sh`'ı ile kanonik
`server/farabi-kurulum.sh`'ın ürettiği script arasındaki fark hâlâ
netleştirilmemiş — ayrı bir karar gerektiriyor, bu oturumda dokunulmadı.

4.3. **`~/.local/bin` sahiplik hatası** (DECISIONS.md 2026-09-15):
10-A/11-A/12-B'de `tahtaayar/`'ın güç-düğmesi provizyonu `~/.local/bin`'i
yanlışlıkla `root:root` yapmıştı; elle düzeltildi ama **kök neden
(`tahtaayar/`'ın script'lerindeki `mkdir -p` çağrısının sudo altında
çalışması) hâlâ kodda düzeltilmedi** — yeni bir tahtaya aynı sırayla
provizyon uygulanırsa hata tekrarlanabilir.

## 5. Commit edilmemiş değişiklikler (dikkat)

`git status` şunu gösteriyor — **2 gündür bekliyor**, kaybolma riski var:

- Değiştirilmiş: `pano.css`, ve 7 `templates/*.html` dosyası (koyu/yumuşak
  tema sistemi eklemesi).
- İzlenmeyen (yeni): `static/tema.js`, `dashboard/yedek/2026-09-15_tema_oncesi/`
  (değişiklik öncesi elle alınmış yedek), `sorunlar.md`.

Bu bir hata değil ama öneri: tema değişikliği görünüşe göre tamamlanmış ve
tutarlı (tüm ilgili şablonlarda `tema.js`/`data-tema` kullanımı var) —
kullanıcı onaylarsa commit edilmesi, kaybolma riskini ortadan kaldırır.

## 6. Kullanılmayan / şüpheli dosyalar — SİLİNMEDİ, onay bekliyor

Aşağıdakilerin hiçbiri bu oturumda silinmedi. Kullanıcı onayı olmadan
hiçbir dosya silinmeyecek.

| Dosya | Neden şüpheli | Kanıt | Öneri |
|---|---|---|---|
| `client/core/prompteski.txt` (v2.0, 483 satır) | Hiçbir `.py` dosyasında referans yok; `prompt.txt` (v2.1, 637 satır) güncel/kullanılan sürüm | `grep -rn prompteski` → sıfır sonuç (docs dahil) | Silinebilir — git geçmişinde zaten duruyor, ayrıca dosya olarak tutmaya gerek yok |
| `benchmark/sorular.json.bak` | Bir yedek dosyası **yanlışlıkla git'e commit edilmiş** (`git ls-files` içinde çıktı) | `git ls-files \| grep bak` | Git'ten çıkarılabilir (`git rm --cached`) — yedek zaten commit geçmişinde korunuyor |
| `server/config/api_keys.json.bak-20260912170429` | Elle alınmış tek seferlik yedek, kod tarafından okunmuyor | dosya adı zaten tarih damgalı "bak" | Sorun değilse (disk alanı önemli değilse) kalabilir; temizlik isteniyorsa silinebilir |
| `node_modules/` (100MB, tek bağımlılık `@google/gemini-cli`) | Hiçbir `.py`/`.md` dosyasında `gemini-cli`'ye referans yok; `package.json`/`package-lock.json` **git'e hiç commit edilmemiş** (yalnızca yerel) | `grep -rn gemini-cli` → sıfır; `git ls-files package*.json` → boş | Amacı belirsiz — **silmeden önce kullanıcıya sorulmalı** (elle `npx`/CLI için mi kuruldu, yoksa terk edilmiş bir deneme mi?) |
| `client/planlar/BURAYA_NE_KONUR.md` içeriği ile gerçek dizin durumu **uyuşmuyor** | Doküman "Bu klasördeki 29 dosya test verisi olarak depoda duruyor" diyor ama dizinde `.md` dışında **hiçbir dosya yok** | `ls client/planlar/` → yalnızca placeholder | Silinecek bir şey yok (zaten gitignore'lu, arşiv) — yalnızca **doküman satırı güncel değil**, düzeltilmesi (ya da "29 dosya sadece bazı geliştirme makinelerinde mevcut" notu eklenmesi) faydalı olur |

## 7. Öncelik sırası (öneri)

1. **Commit et** — §5'teki tema değişikliği + `sorunlar.md` iki gündür
   bekliyor, kaybolma riski taşıyor (kullanıcı onayı gerekir).
2. **tahta-244 sorusu** — hâlâ karartılmış ve güç-düğmesi fix'i eksik;
   kullanıcıya "bu oda aktif kullanılıyor mu" diye sorulmalı (§4.1).
3. **Onaylanırsa** §6'daki dosyaların temizliği (en düşük riskli:
   `prompteski.txt`, `sorular.json.bak`; belirsiz: `node_modules`).
4. Düşük öncelik: `auth.gecerli_oturum` ölü kodunun kaldırılması/birleştirilmesi,
   `/admin/uzaktan` 401→/giris yönlendirmesi, eylem loglaması eklenmesi
   (§3, madde 1-3).

---

*Bu rapor `farabi.local` üzerinde canlı SSH erişimiyle (kod okuma +
`uzaktan_yonetim.tum_durumlar()` çalıştırma + `tahta_fix_uygula.py
--sadece-kontrol`) üretildi. Hiçbir dosya değiştirilmedi/silinmedi, hiçbir
tahtaya yazma işlemi yapılmadı — yalnızca salt-okunur komutlar
çalıştırıldı.*
