"""
core/modeller.py — Canlı ses model adı TEK YERDE.

Neden var
---------
Model adı altı ayrı dosyada sabit yazılıydı ve 30.07.2026'da hepsi birden
kırıldı: `gemini-2.5-flash` **emekliye ayrıldı**. Sağlayıcının cevabı:

    404 NOT_FOUND — "This model models/gemini-2.5-flash is no longer available"

Derste görünen hâli şuydu (logs/farabi.log, 23:58): öğretmen konu istedi, model
`ders_icerigi`'yi çağırdı, araç 17,1 saniye sonra "Kitap içeriği okunamadı"
diye döndü. Sınıf, sebebi hiç anlaşılmayan bir sessizlik yaşadı.

Bu dosya o olayın tekrarını engellemek için vardı: ad tek yerde dursun, bir
emeklilik olduğunda tek satır değişsin.

**Gemini uzun süre yalnızca CANLI SES için kullanıldı** — `main.py`'nin ana
oturumu. Gerçek zamanlı çift yönlü ses için başka seçenek yok; bu yüzden bu
dosya hâlâ var.
Bütün gerçek ZAMANSIZ işler (arama sentezi, belge/video özeti, kitap özeti,
sembol düzeltme, yüklenen resim analizi) `core/saglayicilar.py`'deki
altı-sağlayıcılı havuza taşındı — eski `METIN_MODELI`/`YEDEK_MODEL`/`uret()`
üçlüsü SİLİNDİ, çünkü hiçbir tüketicisi kalmadı. Gemini'nin METİN çağrısı
tekrar gerekirse (ör. saglayicilar.py'deki hiçbir sağlayıcı bir görevi
karşılayamıyorsa) buraya değil, saglayicilar.py'ye Gemini'yi bir sağlayıcı
olarak eklemek doğru yoldur.

**İstisna (2026-09-04): `GORSEL_URET_MODEL`, metinden-görsel üretim
(`actions/gorsel_uret.py`).** `saglayicilar.py`'nin altı-sağlayıcı havuzu
görsel ÜRETMİYOR, yalnızca görsel AÇIKLIYOR (`server/saglayicilar.py::
gorsel_uret`, imzası `resim_bytes` alıyor — bambaşka bir iş, vision değil
generation). Bu havuzda text-to-image yeteneği olan hiçbir sağlayıcı yok, o
yüzden server'a yeni bir görsel-üretim entegrasyonu eklemek yerine zaten
client'ta duran Gemini anahtar havuzu (`core/anahtar.py`, Live oturumunun
kullandığı AYNI havuz) kullanıldı — kullanıcı onayıyla (2026-09-04). Bu bir
metin/senkronizasyon modeli değil (o durum hâlâ yukarıdaki kuralın
kapsamında, saglayicilar.py'ye gider), görsel üretim ayrı bir yetenek
sınıfı olduğu için burada.

Canlı ses modeli ayrı tutulur: Live API'nin kabul ettiği ad kümesi metin
modellerinden farklıdır ve oradaki bir değişiklik oturumun hiç açılmamasına
yol açar.
"""

# Gerçek zamanlı ses oturumu (main.py)
CANLI_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

# Metinden görsel üretim (actions/gorsel_uret.py) — Gemini'nin ayrı bir model
# ailesi (Live'dan bağımsız, "resim üret" istekleri için). Diğer Gemini
# modelleri gibi bu da emekliye ayrılabilir (bkz. yukarıdaki 2026-07-30
# gemini-2.5-flash olayı) — 404 alınırsa önce Gemini'nin güncel image
# generation model listesini doğrula, sonra yalnızca bu satırı değiştir.
#
# 2026-09-04, gerçek anahtarla doğrulandı: `gemini-2.5-flash-image` API'de
# kabul ediliyor ama sunucu tarafında eski/emekli bir kota kovasına
# (`gemini-2.5-flash-preview-image`, ücretsiz kotası 0) yönlendiriliyordu —
# `client.models.list()` çıktısında artık hiç görünmüyor. `gemini-3.1-flash-
# image` o listede canlı ve kendi adıyla kota tutuyor; buna geçildi. İkisi de
# bu anahtarın PROJESİNDE 429 RESOURCE_EXHAUSTED (limit: 0, free tier) verdi
# — bu bir model-adı sorunu değil, projede görsel üretim için faturalandırma
# (billing) etkin olmaması. Görsel üretim modelleri Gemini'de genelde salt
# ücretsiz katmanda çalışmıyor; ilerlemek için o Google Cloud projesinde
# billing açılmalı.
GORSEL_URET_MODEL = "gemini-3.1-flash-image"
