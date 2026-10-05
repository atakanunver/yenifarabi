# Yoklama Panosu (port 8010) inceleme raporu — 2026-10-03

Kapsam: `tahtayoklama/dashboard/` (`farabi-yoklama-dashboard.service`).
Ölçümler Farabi üzerinde, geçici bir oturumla yerelden `curl` ile alındı (oturum ölçüm sonrası silindi).
Ölçüm günü cumartesiydi, bu yüzden `/api/durum` boş döndü. Okul günü değil, poller penceresi kapalı.

## Ölçümler

| Sayfa / uç | Boyut (gzip) | Süre | Not |
|---|---|---|---|
| `/` (ana sayfa, yoklama) | 6,0 KB | 3 ms | Hafif |
| `/api/durum` | 36 B | 1 ms | Cumartesi olduğu için boş |
| `/api/sistem-durumu` | 1,5 KB | 1,5 ms | Önbellekten okuyor |
| `/sistem-durumu` | 9,8 KB | 2 ms | |
| `/admin/tahtalar` | 4,1 KB | 4 ms | |
| `/admin/rapor` | 5,6 KB | 8 ms | |
| **`/admin/uzaktan`** | 4,5 KB | **5,6 s** | Sayfa çizilmeden önce tüm tahtalara SSH atılıyor |
| `/static/pano.css` | 6,4 KB | 4 ms | |

Süreç: RSS **1,3 GB**, ~24 saatte ~3.770 sn CPU (ortalama bir çekirdeğin ~%4'ü).

## Bulgular

1. **Ana sayfa zaten yalnızca yoklamayı yüklüyor.** Panel çok sayfalı (MPA) bir uygulama, diğer bölümler kendi sayfalarında ve yalnızca tıklanınca yükleniyor. Ana sayfayla birlikte yüklenen tek "başka servis" kenar çubuğundaki mini sistem durumu rozetiydi: her sayfa açılışında `/api/sistem-durumu` çağrısı yapıyor, ardından 30 sn'de bir tekrarlıyordu.
2. **Asıl sürekli yük arka plan toplayıcısı.** `sistem_durumu.toplayici_dongusu` panel hiç açılmasa bile 15 sn'de bir çalışıyor. Her turda nvidia-smi, sensors, systemctl, psql ve journalctl çağırıyor; 60 sn'de bir de uzak makinelere HTTP/TCP yoklaması yapıyor. Bu, 2026-09-25'te bilinçli alınmış bir karar (30 dk trend grafiği bu döngüye bağlı). Bu yüzden değiştirilmedi.
3. **`/admin/uzaktan` 5,6 sn bekletiyor.** `tum_durumlar()` tüm tahtalara SSH atıyor, bitene kadar sayfa boş kalıyor; kapalı tahtalarda 6 sn'lik zaman aşımına takılıyor. Sayfa yalnızca tıklanınca açıldığı için ilk açılışı etkilemiyor.
4. **1,3 GB RSS**, küçük bir FastAPI uygulaması için yüksek. Kaynağı araştırılmadı; zamanla büyüyen bir sızıntı olabilir.
5. **Güvenlik:** Kenar çubuğundaki Zil Sistemi bağlantısı Basic Auth kullanıcı adı ve parolasını URL içinde düz metin olarak taşıyor. Bu bilgi panele giren her tarayıcıya HTML içinde gidiyor.

## Yapılan değişiklikler

Yedek: `tahtayoklama/dashboard/yedek/2026-10-03_lazy_yukleme_ai_butonu/`

- **Mini durum rozeti artık tıklanınca yükleniyor.** İlk açılışta `/api/sistem-durumu` çağrısı yapılmıyor, rozet "Durumu göster" yazıyor. Tıklanınca yükleniyor ve 30 sn'de bir yenileniyor, ikinci tıklamada Sistem Durumu sayfasına gidiyor. Sistem Durumu sayfasında eskisi gibi kendiliğinden başlıyor. (`static/kenar.js`, `templates/taban.html`)
- **"Atos Yapay Zeka" butonu** kenar çubuğunun en üstüne, "Yapay Zeka" grubuna eklendi. Open WebUI'yi (port 80) yeni sekmede açıyor. Adres isteğin host'undan üretiliyor; panel `farabi.local:8010` ile açılırsa `http://farabi.local/`, IP ile açılırsa o IP'ye gidiyor. Yeni ikon: `ik-yildiz`. (`templates/taban.html`, `templates/_ikon_sprite.html`, `static/pano.css`)
- Testler: `venv/bin/python -m unittest discover -p 'test_*.py'` sonucu 33/33 OK. Servis yeniden başlatıldı, HTML'de buton ve tembel rozet doğrulandı, `http://farabi.local/` 200 döndü.

## Öneriler (onay bekliyor)

- **Toplayıcıyı talebe bağlamak:** Son N dakikada `/api/sistem-durumu` isteği yoksa döngü uyusun. Panel kapalıyken sunucu ve uzak makinelerdeki sürekli yük kalkar. Bedeli: 30 dk trend grafiği yalnızca biri izlerken dolar.
- **`/admin/uzaktan`:** Sayfa iskeleti hemen gelsin, tahta durumları bir JSON ucundan arka planda dolsun. Böylece 5,6 sn'lik boş bekleme kalkar.
- **RSS 1,3 GB:** Birkaç gün boyunca bellek izlenip sızıntı olup olmadığı netleştirilmeli.
- **Zil parolası:** URL'den çıkarılmalı. Bir sunucu yönlendirmesi ya da tarayıcının kendi kimlik doğrulama penceresi kullanılabilir.
