# Dijital Okul Platformu — Tasarım (Aşama 1)

- **Tarih:** 2026-10-10
- **Durum:** Onaylandı (kullanıcı, bölüm bölüm)
- **Servis:** `farabi-okul.service`, port **9090**, kod `okul/`
- **Dış erişim:** Cloudflare Tunnel `smual.app` → `http://localhost:9090` (bkz. `llm-cluster-wiki/nodes/farabi.md` "Cloudflare Tunnel")

## 1. Amaç ve kapsam

Öğrenci, veli, öğretmen ve okul yönetimini tek bir mobil uyumlu web uygulamasında
(PWA) buluşturan dijital okul platformu. Öğrenci yalnızca notunu değil eksik
kazanımlarını görür; veli çocuğunun gelişimini takip eder; öğretmen ödev/test
üzerinden kazanım bazlı değerlendirme yapar.

### Kullanıcı kararları

| Konu | Karar |
|---|---|
| Ölçek | Tek okul (kendi lisemiz). Çoklu okul ayrı bir proje. |
| Yapay zekâ | Aşama 1'de yok. |
| Veri girişi | Excel + elle. |
| Giriş | Veli: telefon + SMS kodu. Öğrenci/öğretmen/yönetici: kullanıcı adı + şifre. |
| İlk şifre | `ilk ad + 123` (küçük harf, Türkçe karakter sadeleştirilmiş), ilk girişte değiştirme zorunlu. |
| Oturum | Zaman aşımı yok — 1 yıllık, her istekte yenilenen çerez. Güvenlik kullanıcıyı kaçırmamalı. |
| Devamsızlık kaynağı | Tahta yoklaması (`yoklama_pano.db`), salt-okunur. |
| Ödev | Klasik (açıklama + teslim tarihi, "yaptım") ve çoktan seçmeli test (uygulamada çözülür, otomatik puanlanır, kazanım bazlı). |
| Yığın | FastAPI + Jinja2 + vanilla JS + SQLite (WAL); npm/build yok (repo konvansiyonu). |

### Kapsam dışı (sonraki aşamalar)

2. Ölçme-değerlendirme: not/yazılı girişi, veli toplantıları, gelişim grafikleri.
3. Akıllı raporlama: erken uyarı, sınıf karşılaştırma, Excel/PDF raporlar.
4. Yapay zekâ: çalışma asistanı, soru üretimi, Farabi bağlantısı.
5. Otomasyon: akıllı bildirimler, öğretmen-veli mesajlaşma, randevu.

## 2. Mimari

```
 Telefon/PC ──HTTPS──► Cloudflare (smual.app) ──tünel──► farabi-okul :9090
 (LAN: http://farabi.local:9090)                              │
                                                              ├─ okul/veri/okul.db (SQLite WAL) — kendi verisi
                                                              ├─ tahtayoklama/dashboard/veri/yoklama_pano.db — salt-okunur
                                                              ├─ PostgreSQL soru_havuzu (form_testi, form_cevap, soru havuzu) — salt-okunur
                                                              ├─ mudur/ders_programi.json — salt-okunur
                                                              └─ smssistemi :8020 araç API — veli SMS giriş kodu
```

- Ayrı venv (`okul/venv`), ayrı systemd birimi, uvicorn `0.0.0.0:9090`.
- `tahtayoklama/dashboard` ve `smssistemi` ile **kod paylaşımı yok** (repo genelindeki
  bağımsızlık kararı); desenleri (scrypt `auth.py`, `db.py`) bağımsız kopya olarak izlenir.
  Bağlantılar yalnızca yukarıdaki salt-okunur okumalar + SMS HTTP çağrısı.
- Devamsızlık, kazanım test sonuçları ve ders programı **kopyalanmaz**; her istekte
  kaynağından okunur (tek doğru kaynak).

### Modüller

| Dosya | Sorumluluk |
|---|---|
| `app.py` | FastAPI uygulaması, rotalar, şablon render |
| `auth.py` | Oturum çerezi, scrypt şifre, SMS kodu üretme/doğrulama, deneme sınırlama |
| `yetki.py` | Tek merkez: `gorebilir_mi(kullanici, ogrenci)`, `sinif_yetkisi(kullanici, sinif, ders)` |
| `db.py` | `okul.db` şeması, sürüm tabanlı migration, bağlantı (WAL) |
| `kaynaklar/yoklama.py` | `yoklama_pano.db` salt-okunur (`mode=ro` URI); isim → okul no eşlemesi |
| `kaynaklar/kazanim.py` | Postgres `form_testi`/`form_cevap` ve soru havuzu okuma |
| `kaynaklar/program.py` | `ders_programi.json` okuma (mtime ile önbellek) |
| `kaynaklar/sms.py` | `smssistemi` araç API'si üzerinden tek SMS gönderimi (`POST /api/arac/kod-sms`) |
| `ice_aktar.py` | Excel (openpyxl) öğrenci+veli / öğretmen+görev aktarımı, önizleme + onay |
| `templates/`, `static/` | Mobil öncelikli HTML/CSS, `manifest.json`, `sw.js` (PWA) |

### smssistemi'ye gereken ek

Mevcut araç API'sinde tek bir telefona serbest metin gönderen uç yok
(`kisisel-gonder` okul no'nun tüm velilerine taslak→onay akışıyla gider; giriş kodu için uygun değil).
`smssistemi/arac_api.py`'ye yeni uç eklenir:
`POST /api/arac/kod-sms {telefon, metin}`, `X-Sms-Arac-Key` ile korunur, mevcut `gonder()`'i
kullanır. Kendi içinde telefon başına dakikada 1 / saatte 5 sınırı vardır, bu yüzden
anahtar sızsa bile toplu SMS aracı olarak kullanılamaz. Testleri `smssistemi/test_arac_api.py`'ye eklenir.

### Hata davranışı

Bir dış kaynak (Postgres, pano DB, SMS servisi) erişilemezse ilgili kart
"şu an alınamıyor" gösterir; sayfanın geri kalanı çalışır. SMS servisi kapalıyken
veli girişi açık bir mesajla reddedilir (sessiz başarısızlık yok).

## 3. Veri modeli (`okul.db`)

| Tablo | Ana alanlar | Not |
|---|---|---|
| `kullanici` | id, rol (`ogrenci`/`veli`/`ogretmen`/`yonetici`), ad_soyad, kullanici_adi (UNIQUE, NULL olabilir), telefon (UNIQUE, NULL olabilir), sifre_hash, sifre_degismeli, aktif, olusturma | Veli: telefon ile, şifresiz |
| `ogrenci` | id, **okul_no** (UNIQUE), ad_soyad, sinif, kullanici_id | Okul no tüm kaynakları bağlayan anahtar |
| `veli_ogrenci` | veli_id, ogrenci_id, yakinlik, UNIQUE(veli_id, ogrenci_id) | Excel'deki veli telefonundan kurulur |
| `ogretmen_gorev` | ogretmen_id, sinif, ders, UNIQUE(üçü) | Öğretmen yetkisinin kaynağı |
| `duyuru` | id, yazar_id, baslik, metin, hedef_tur (`okul`/`sinif`/`rol`), hedef, yayin, bitis | |
| `odev` | id, ogretmen_id, sinif, ders, tur (`klasik`/`test`), baslik, aciklama, teslim, olusturma | |
| `odev_soru` | id, odev_id, sira, metin, siklar (JSON), dogru, kazanim, kaynak (`elle`/`havuz:<id>`) | Havuzdan anlık kopya; havuz değişse ödev değişmez |
| `odev_teslim` | odev_id, ogrenci_id, durum, puan, cevaplar (JSON), zaman, UNIQUE(odev_id, ogrenci_id) | Test tek seferlik çözülür |
| `oturum` | token_hash, kullanici_id, olusturma, son_gorulme, cihaz | |
| `sms_kod` | telefon, kod_hash, son_gecerlilik, deneme | 6 hane, 5 dk, 5 deneme |
| `giris_deneme` | anahtar (kullanıcı/IP), sayac, pencere_baslangic | Deneme sınırlama |
| `erisim_log` | kullanici_id, eylem, ogrenci_id, zaman, ip | KVKK |

### Devamsızlık eşlemesi

`yoklama_onbellek` gelmeyenleri **isimle** tutar (`yok_isimleri`, `izinli_isimleri`).
Eşleme: (sınıf, ad_soyad) → pano DB `ogrenciler.no` → `okul.db ogrenci.okul_no`.
İsim karşılaştırması Türkçe-duyarlı normalize edilir (küçük harf, boşluk sadeleştirme).
Aynı sınıfta aynı isimli iki öğrenci ya da eşleşmeyen isim olursa kayıt
**atlanmaz**: velinin ekranına yazılmaz, yönetici paneli "eşleşmeyen yoklama
isimleri" listesinde gösterilir.

## 4. Roller ve yetki

| Rol | Görebildiği öğrenciler | Yazabildikleri |
|---|---|---|
| Öğrenci | Yalnızca kendisi | Ödev "yaptım", test cevapları |
| Veli | `veli_ogrenci`'deki çocukları | — (salt okuma) |
| Öğretmen | `ogretmen_gorev`'deki sınıflar | Kendi sınıf/derslerine ödev ve test; kendi sınıflarına duyuru |
| Yönetici | Tüm okul | Okul duyurusu, kullanıcılar, Excel aktarımı, görev atamaları |

- Her sayfa veri çekmeden önce `yetki.py`'den geçer.
- Yetkisiz erişim **404** döner (403 kaydın varlığını sızdırır).
- Öğrenci verisi görüntülemeleri `erisim_log`'a yazılır.

## 5. Giriş ve oturum

- **Kullanıcı adı:** öğrenci = okul no; öğretmen/yönetici = Excel'deki kullanıcı adı;
  veli = telefon + SMS kodu.
- **İlk şifre:** ilk ad, küçük harf, Türkçe karakterler sadeleştirilmiş + `123`
  ("Ayşe Nur Yılmaz" → `ayse123`). `sifre_degismeli=1`; değişene kadar hesap
  yalnızca şifre değiştirme ekranını açabilir.
- **Oturum:** 1 yıllık çerez, her istekte süresi yenilenir (pratikte tekrar giriş yok).
  Şifre değişince o kullanıcının diğer oturumları kapanır.
- **Görünmez güvenlik önlemleri:**
  - Kullanıcı/IP başına art arda hatalı denemede kısa bekleme.
  - Yönetici panelinde "şifresini değiştirmemiş" listesi (tahmin edilebilir ilk şifre riski).
- **Çerez/form:** `HttpOnly`, `Secure` (HTTPS isteğinde), `SameSite=Lax`; POST formlarında CSRF token.
- **Diğer:** `noindex` başlığı. Gizli bilgiler (`smssistemi` araç anahtarı, Postgres
  şifresi) `okul/config/gizli.json` içinde, `.gitignore`'da — **repo public**.

## 6. Ekranlar (mobil öncelikli)

Rol bazlı ana ekran, alt sekme çubuğu, kart düzeni; masaüstünde aynı tasarım genişler.
`manifest.json` + `sw.js` ile "ana ekrana ekle" (PWA). Service worker yalnızca
statik dosyaları önbelleğe alır; kişisel veri önbelleklenmez.

- **Öğrenci:**
  - Ana sayfa: bugünkü dersler, yaklaşan ödevler, son duyurular, kazanım özeti.
  - Ödevlerim: klasik + test çözme, anında puan ve yanlış yapılan kazanımlar.
  - Kazanımlarım: ders bazında başarılı/eksik; kaynak: kazanım testleri + ödev testleri.
  - Ders programı, Duyurular.
- **Veli:**
  - Birden çok çocuk varsa üstte çocuk seçici.
  - Devamsızlık: gün/ders listesi ve toplam, "resmî kayıt e-Okul'dur" notuyla.
  - Kazanım test sonuçları, ödev durumu, ders programı, duyurular.
- **Öğretmen:**
  - Sınıflarım: öğrenci listesi.
  - Ödev/test oluştur: sorular elle yazılır ya da soru havuzundan kazanıma göre seçilir.
  - Ödev sonuçları: öğrenci ve kazanım bazlı sınıf tablosu.
  - Duyuru yaz.
- **Yönetici:**
  - Excel aktarımı: önizleme + onay.
  - Kullanıcılar: şifre sıfırla (yine `ad123` + değiştirme zorunlu), pasifleştir, "şifre değiştirmemiş" listesi.
  - Okul duyurusu, görev atamaları.
  - Basit özet: sınıf bazlı devamsızlık ve ödev tamamlama.
  - Eşleşmeyen yoklama isimleri.

## 7. Excel aktarımı

- **Öğrenci şablonu:** `okul_no, ad_soyad, sinif, veli_ad, veli_telefon, veli2_ad, veli2_telefon`.
- **Öğretmen şablonu:** `ad_soyad, kullanici_adi, telefon, sinif, ders` (her satır bir görev).
- Uygulamadan boş şablon indirilebilir.
- **Davranış:**
  - Tekrar çalıştırılabilir: okul no / kullanıcı adı / telefon üzerinden ekler ya da günceller.
  - **Silmez**; Excel'de olmayanları raporlar.
  - Telefonlar `05XXXXXXXXX` biçimine normalize edilir.
  - Hatalı satırlar önizlemede satır numarasıyla gösterilir; onay verilmeden yazılmaz.

## 8. Test

- pytest + FastAPI TestClient; dış kaynaklar (Postgres, pano DB, SMS) mock/geçici dosya.
- **Öncelik: yetki matrisi.** Her rol için yasak verilere erişimin 404 döndüğünü doğrulayan testler (veli başka çocuk, öğretmen başka sınıf, öğrenci başka öğrenci).
- Excel aktarımı (yeni/güncelleme/hatalı satır, telefon normalizasyonu).
- İlk şifre üretimi (Türkçe karakterler, çok isimli kişiler).
- Devamsızlık isim eşlemesi (aynı isim, yazım farkı, eşleşmeyen).
- Test çözme, puanlama, tek seferlik teslim.
- SMS kodu: süre, deneme sınırı.
- **Canlı doğrulama:**
  - `smual.app` üzerinden dört rolle telefondan giriş.
  - PWA "ana ekrana ekle".
  - Cloudflare dashboard'da `smual.app` → `localhost:9090` yanıt veriyor.
