# Test soruları — Faz 1b WAV seti

Bu şablon `voice_node/araclar_cli/wav_istemci.py` ile ses düğümüne gönderilecek
10 Türkçe istemi listeler: dosya adı -> beklenen transkript metni (WER
hesaplamak için) + kategori + hangi aracın beklendiği.

⚠️ Gerçek mikrofon kaydı YOK — `voice_node/piper_servis` ile SENTETİK olarak
üretildi (bkz. bitiş raporu "sentetik ses — gerçek mikrofon kaydı değil").
Kullanıcının gerçek kayıtları bu dosyaları GİT'siz olarak buraya
eklediğinde aynı adları (`s01.wav` ... `s10.wav`) kullanmalı; bu durumda
sentetik WAV'lar üzerine yazılır ya da `gercek/` alt dizinine konur.

| # | Dosya | Kategori | Beklenen araç | Metin (beklenen transkript) |
|---|-------|----------|----------------|------------------------------|
| 1 | s01.wav | bilgi (biyoloji-9) | kitap_sorusu | Hücre nedir, kısaca anlatır mısın? |
| 2 | s02.wav | bilgi (biyoloji-9) | kitap_sorusu | Mitoz bölünme neden gerçekleşir? |
| 3 | s03.wav | bilgi (biyoloji-9) | kitap_sorusu | Canlıların ortak özellikleri nelerdir? |
| 4 | s04.wav | bilgi (biyoloji-9) | kitap_sorusu | DNA'nın görevi nedir? |
| 5 | s05.wav | bilgi (biyoloji-9) | kitap_sorusu | Fotosentez hangi organelde gerçekleşir? |
| 6 | s06.wav | bilgi (biyoloji-9) | kitap_sorusu | Homeostazi kavramı ne demektir? |
| 7 | s07.wav | konu anlatımı | ders_icerigi | Hücre zarının yapısını anlatır mısın? |
| 8 | s08.wav | sayfa açma | pdf_sayfa | Kitabın on ikinci sayfasını açar mısın? |
| 9 | s09.wav | çıkmış soru | yks_sorulari | Hücre bölünmesiyle ilgili çıkmış bir TYT sorusu gösterir misin? |
| 10 | s10.wav | sohbet | (araçsız) | Günaydın Farabi, bugün nasılsın? |

Öneri parametreler (`wav_istemci.py`):
- `--kip ogretmenli --ders Biyoloji` (1-6, 7-9), `--kip ogretmenli` (10, ders boş)
- `--girdi tests/audio/s0N.wav --cikti /tmp/cevapN.wav`

WER (kelime hata oranı) hesabı: Türkçe İ/ı normalizasyonu uygulanmalı
(`str.lower()` İ/ı'yı yanlış çeviriyor — bkz. bitiş raporu "Türkçe WER"
notu), noktalama atılır, sayı/rakam-yazı farkları (örn. "12." vs "on iki")
ayrıca not edilir, WER'e dahil edilmeyebilir.
