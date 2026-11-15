# Giriş IP Hareket Eşiği

- **Amaç:** `giris_ip` kamerasındaki kıl payı hareket tetiklerini azaltmak; gece hareket SMS'lerinin yanlış tetiklenmesini önlemek.
- **Seçilen yaklaşım:** Yalnız `kameralar/hareket/ayar.json` içindeki `giris_ip.esik` değerini `0.018`'den `0.025`'e çıkarmak. Diğer kamera eşikleri ve algılama kodu değişmeyecek.
- **Alternatifler:** `0.020` daha küçük hareketleri daha iyi korur ama çok dar bir fark yaratır; tüm kameraların eşiğini değiştirmek gereksiz kapsam ve kaçırılan hareket riskini büyütür.
- **Kısıt / risk:** İncelenen yanlış uyarının oranı `0.0199` olarak loglanmıştı; `0.025` bunu eler. Daha küçük veya uzak kişilerin algılanma olasılığı düşebilir. `hareket.py` ayarları başlangıçta belleğe aldığı için değişikliğin etkinleşmesi servis restart'ı gerektirir; kullanıcı restart'ı ayrıca onayladı. Eski değer yedeklenir, JSON/test doğrulaması ve servis durumu kontrol edilir.
- **Kapsam dışı:** Pre-roll, alarm mantığı, SMS metni ve diğer kamera ayarları.
