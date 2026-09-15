# Tahta Uzaktan Yönetim — Web Paneli (Faz 1 + Duvar Kağıdı)

2026-09-15. Windows'taki `tahta_panel.py` (tkinter+paramiko masaüstü paneli)
işlevlerinin bir alt kümesini `http://farabi.local:8010/` panosuna ("Yoklama
Panosu") yeni bir "Uzaktan Yönetim" bölümü olarak taşır.

## Amaç

Öğretmen/yönetici tahtalara (yoklama aç/kapat, web sayfası aç, ekranı
karart, duvar kağıdı değiştir) Windows makinesinde özel bir program
çalıştırmadan, tarayıcıdan, panonun geri kalanıyla aynı girişten erişebilsin.

## Kapsam

**Var (bu spec):** durum tablosu (bağlantı/oturum/yoklama/chrome/ekran
karartma), yoklama aç/kapat, web sayfası aç / chrome kapat, ekranı karart /
karartmayı kaldır, duvar kağıdı değiştir. Hepsi toplu (çoklu tahta seçimi).

**Yok (ertelendi, ayrı bir karar turu gerekir):** dosya gönder (masaüstüne
keyfi dosya), oturum aç / otomatik giriş kur-kaldır (lightdm config'ine
dokunuyor), "kapat butonunu karartmaya çevir" (.desktop dosyası
değiştiriyor). Bunlar `etapadmin`+sudo gerektiren, sistem dosyalarını
değiştiren işlemler — Faz 1'in "ogretmen'e doğrudan SSH, sudo yok"
modeliyle uyuşmuyor, kasıtlı olarak dışarıda bırakıldı.

## Kullanıcı kararları (2026-09-15)

- **Tahta kaydı:** `server/tahtalar.json` tek doğru kaynak. Panonun kendi
  SQLite `tahtalar` tablosuna KOPYALANMAZ/yazılmaz (admin.py'nin aynı
  ilkesini takip eder).
- **Erişim kontrolü:** Ayrı bir yönetici şifresi YOK — panonun mevcut ortak
  öğretmen şifresi/oturum çerezi yeterli kabul edildi.
- **Kapsam:** Önce düşük riskli işlemler + duvar kağıdı (bu spec). Dosya
  gönderme/autologin/kapat-butonu hack'i sonraki bir karara bırakıldı.

## Mimari

Yeni bir FastAPI router (`uzaktan_yonetim.py`), `admin.py`'nin yanına,
aynı `/admin` prefix'i altında (`/admin/uzaktan`) mount edilir. Aynı
Jinja2/form-POST tarzı (SPA/fetch yok — dashboard'un "hafif tut" kuralı).
`pano.html` ve tüm `/admin/*` şablonlarının nav'ına "Uzaktan Yönetim"
linki eklenir.

**Önemli basitleşme:** Yerel Windows aracı `etapadmin` ile bağlanıp
`sudo -u ogretmen` ile masaüstü oturumuna geçiyordu (paramiko + düz metin
şifre). Farabi'nin SSH anahtarı (`~/.ssh/id_ed25519_tahta`) zaten
`ogretmen` hesabına DOĞRUDAN yetkili (`uzaktan_baslat.py` bunu zaten
kanıtlamış). Bu yüzden Faz 1'deki hiçbir işlem sudo/root gerektirmez —
`tahta_ssh.py`'deki `kok()` katmanına hiç ihtiyaç yok. Duvar kağıdı da
aynı basitleşmeden faydalanıyor: yerel araç SFTP+`install`+`chown` üçlüsü
gerektiriyordu (etapadmin→ogretmen sahiplik devri için); burada zaten
ogretmen olarak bağlanıldığından dosya doğrudan doğru sahiplikle yazılır.

**Refactor:** `uzaktan_baslat.py`'deki `_x_ortamini_kesfet` (DISPLAY/
XAUTHORITY keşfi) `ssh_istemci.py`'ye `x_ortamini_kesfet()` olarak taşınır
ve `uid`'i de döner (duvar kağıdı için DBUS adresi gerekiyor). Tek kopya —
`tahtaayar/CLAUDE.md`'de belgelenen "iki kopya senkron kalmadı" hatasından
kaçınmak için.

## Bileşenler

| Dosya | Değişiklik |
|---|---|
| `dashboard/ssh_istemci.py` | + `x_ortamini_kesfet(ip, kullanici) -> (display, xauthority, uid) \| None` |
| `dashboard/uzaktan_baslat.py` | Kendi kopyasını siler, `ssh_istemci.x_ortamini_kesfet` kullanır |
| `dashboard/tahta_kaydi.py` | YENİ — `server/tahtalar.json`'ı okur, `[{ad, ip, kullanici, admin}]` döner |
| `dashboard/uzaktan_yonetim.py` | YENİ — router: durum + 6 eylem endpoint'i |
| `dashboard/templates/uzaktan_yonetim.html` | YENİ |
| `dashboard/static/pano.css` | + küçük, izole bir "Faz 6" bölümü (mevcut kuralları değiştirmez) |
| `dashboard/app.py` | `uzaktan_yonetim.router` include edilir |
| `dashboard/templates/pano.html`, `admin_tahtalar.html`, `admin_siniflar.html`, `admin_sinif_ogrenciler.html`, `admin_rapor.html` | nav'a "Uzaktan Yönetim" linki |

## Veri akışı

**Durum tablosu** (`GET /admin/uzaktan`): `tahta_kaydi.tahtalari_yukle()`
ile tahta listesi okunur; her tahta için TEK ssh round-trip'te (bash
one-liner: `loginctl`+`pgrep`×3) oturum/yoklama/chrome/karartma durumu
alınır, `asyncio.gather` ile tüm tahtalar paralel sorgulanır (6sn zaman
aşımı/tahta — SSH başarısızsa "ulaşılamaz" gösterilir, sayfa yüklemesi en
yavaş tek tahtanın süresiyle sınırlı kalır).

**Eylemler** (`POST /admin/uzaktan/<eylem>`): form'da seçili tahta adları
(`tahta` alanı, checkbox'lar) `server/tahtalar.json`'daki adlarla
eşleştirilir (istemciden gelen IP asla güvenilmez — yalnızca kayıtlı ad
kabul edilir). Seçilenler üzerinde `asyncio.gather` ile paralel çalışır,
sonuç listesiyle birlikte sayfa yeniden render edilir (redirect yok —
`admin.py`'nin `tahta_guncelle`/`sinif_senkronize` deseniyle aynı).

- **Yoklama aç:** `uzaktan_baslat.baslat()` (mevcut, değişmedi) çağrılır —
  python yolu adayları (`/home/ogretmen/tahtayoklama/venv/bin/python`,
  `/usr/bin/python3`) `test -x` ile bulunur.
- **Yoklama kapat / chrome kapat / karartmayı kaldır:** `pkill -f
  '[…]…'; true` — kendi süreci, root gerekmez, `; true` ile "süreç zaten
  yoktu" durumu SSH hatası sayılmaz.
- **Web sayfası aç:** X-ortamı keşfi + eski Chrome Singleton kilidi
  temizliği (chrome çalışmıyorsa) + `google-chrome --new-window <url>`.
  URL `shlex.quote()` ile kaçışlanır, şema yoksa `https://` eklenir.
- **Ekranı karart:** eta-screen-cover başlat (çalışmıyorsa) + `wmctrl`
  ile tam ekrana büyüt — yerel araçla birebir aynı komutlar.
- **Duvar kağıdı:** yüklenen dosya (form'dan `dosya` alanı, max 15MB,
  uzantı görsel formatlarıyla sınırlı) `cat > uzak_yol.tmp && mv …`
  deseniyle (admin.py'nin roster gönderme deseniyle aynı — `stdin_bytes`,
  ayrı bir scp süreci yok) doğrudan `~/Resimler/`'e yazılır, ardından
  X-ortamı + DBUS adresi (`unix:path=/run/user/<uid>/bus`) ile
  `gsettings set org.cinnamon.desktop.background picture-uri …` (+ zoom +
  gnome fallback) çalıştırılır.

## Güvenlik notları

- Tahta hedefleri her zaman sunucudaki `server/tahtalar.json`'dan
  çözülür; istemciden yalnızca "ad" kabul edilir, IP/komut asla.
- URL ve dosya adı gibi kullanıcı girdileri `shlex.quote()` ile
  kaçışlanır (ssh_istemci.py'nin kendi uyarısı: argüman listesiyle
  çağrılsa da uzak tarafta hâlâ bir shell komutu çalışıyor).
- Duvar kağıdı yüklemesi boyut (15MB) ve uzantı allow-list'iyle
  sınırlanır.
- Erişim kontrolü mevcut ortak şifre/oturum çerezine dayanıyor (kullanıcı
  kararı) — bu, panoya girebilen herkesin fiziksel tahtaları
  etkileyebileceği anlamına gelir. Gelecekte ayrı bir yönetici rolü
  gerekirse bu spec'e ek bir karar turu gerekir.

## Hata yönetimi

Her eylem fonksiyonu `{"tahta": ad, "basarili": bool, "detay": str}"
döner; SSH bağlantı hatası/zaman aşımı da bu şekilde yakalanıp
kullanıcıya gösterilir (sayfa asla 500 ile patlamaz — `ssh_istemci`
zaten tüm hataları `SSHSonuc(basarili=False, …)` olarak modelliyor).

## Test planı

- `tahta_kaydi.tahtalari_yukle()` ve durum-parse mantığı için birim testi
  (gerçek SSH gerekmez — sahte `SSHSonuc` ile).
- 1-2 canlı tahtada (ör. 9-A) uçtan uca doğrulama: durum tablosu doğru mu,
  yoklama aç/kapat, web sayfası aç, ekran karart/kaldır, duvar kağıdı —
  her biri fiziksel/uzak masaüstünde gözle teyit edilir (bu projenin
  yerleşik kuralı — bkz. `tahtaayar/CLAUDE.md`, "son kabul testi kullanıcı
  tarafından").
- Servis yeniden başlatması yalnızca ders saatleri (08:00–17:00 TR)
  DIŞINDA yapılır (kök `CLAUDE.md` kuralı).

## Kapsam dışı (sonraki karar turu)

Dosya gönderme, oturum aç / otomatik giriş, "kapat butonunu karartmaya
çevir" — etapadmin+sudo gerektiriyor, Faz 1'in sudo'suz modeline
uymuyor. Ayrıca güçlü bir yönetici parolası ihtiyacı bu işlemler
eklenirken yeniden değerlendirilmeli (kullanıcı Faz 1 için "hayır" dedi,
ama kapat-butonu/autologin gibi daha kalıcı sistem değişiklikleri için
aynı karar geçerli olmayabilir).
