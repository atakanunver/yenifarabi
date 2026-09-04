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

**Gemini artık yalnızca CANLI SES için kullanılıyor** — `main.py`'nin ana
oturumu. Gerçek zamanlı çift yönlü ses için başka seçenek yok; bu yüzden bu
dosya hâlâ var.
Bütün gerçek ZAMANSIZ işler (arama sentezi, belge/video özeti, kitap özeti,
sembol düzeltme, yüklenen resim analizi) `core/saglayicilar.py`'deki
altı-sağlayıcılı havuza taşındı — eski `METIN_MODELI`/`YEDEK_MODEL`/`uret()`
üçlüsü SİLİNDİ, çünkü hiçbir tüketicisi kalmadı. Gemini'nin metin çağrısı
tekrar gerekirse (ör. saglayicilar.py'deki hiçbir sağlayıcı bir görevi
karşılayamıyorsa) buraya değil, saglayicilar.py'ye Gemini'yi bir sağlayıcı
olarak eklemek doğru yoldur — bu dosyayı tekrar genişletmeyin.

Canlı ses modeli ayrı tutulur: Live API'nin kabul ettiği ad kümesi metin
modellerinden farklıdır ve oradaki bir değişiklik oturumun hiç açılmamasına
yol açar.
"""

# Gerçek zamanlı ses oturumu (main.py)
CANLI_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
