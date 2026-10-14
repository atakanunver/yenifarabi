# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Dijital Okul (okul/)

Mobil öncelikli okul portalı: öğrenci/veli/öğretmen/yönetici. FastAPI + Jinja2 + vanilla CSS ("kareli defter" teması, imza öğe `.kareler`), SQLite (kendi verisi). Port 9090, dışarıdan https://smual.app (Cloudflare Tunnel).
Spec: `docs/superpowers/specs/2026-10-10-dijital-okul-design.md`.

## Çalıştırma / test
- Test: `cd okul && venv/bin/python -m pytest -q`. Tek test: `venv/bin/python -m pytest tests/test_odevler.py::test_adi -q`. Lint: repo kökünden `.venv-tools/bin/ruff check okul/<dosya>` (okul/ kapsam listesinde değil; yalnızca dokunduğun dosyayı ver)
- Servis: `farabi-okul.service` (kurulum yorumu `okul/systemd/farabi-okul.service` içinde). Kod değişince: `sudo systemctl restart farabi-okul`.
- İlk yönetici: `venv/bin/python scripts/yonetici_olustur.py "Ad Soyad" kullanici_adi`
- CSS/JS değişirse sürüm sorgusunu (`okul.css?v=N` base.html'de, `*.js?v=N` onu yükleyen şablonda) ve `static/sw.js` içindeki SURUM + STATIK listesini artır; yeni statik JS STATIK'e de eklenir.

## Modül haritası
- ayarlar, zaman, metin: yapılandırma, saat, metin yardımcıları
- db (şema + `GOCLER`), auth, deps, yetki
- duyurular, odevler, ice_aktar
- analitik (kullanım/etkileşim sayaçları: tamponlu+tekilleştirilmiş `olay` yazımı ve yönetici sorguları; `/yonetici/analitik`)
- maraton (Soru Maratonu: puanlama, haftalık liderlik; okul.db. Ders saati kilidi 2026-10-14'te kaldırıldı: `maraton.DERS_KILIDI = False`, True yapılırsa Maraton+Günlük Görev ders saatinde 423)
- arena (Bilgi Arenası: Günlük Görev 5 soru + ortak XP/seviye/rozet defteri `bilgi_xp`; Hızlı Mod = Maraton, tur bitince `maraton_xp`; 9-11 sınıf; XP/seviye saklanmaz, defterden türetilir), kisisel (haftalık hedef; ilerleme `bilgi_tur`/`maraton`/`odev_teslim`'den hesaplanır), bugun (öğrenci ana ekranı görev listesi)
- oduller (haftalık ödül: kiosk duyurusu cuma geçici/pazartesi kesin + rozet + 1 Nescafe; kategoriler en çok etkinlik/en istikrarlı/en katılımcı sınıf, 12. sınıf dahil; sonuç `odul`/`odul_hafta`'ya bir kez yazılır, değişmez; Arena liderliği `oduller.liderlik` xp/doğru/çözülen), avatar (özgün SVG karakter+eşya, seviyeyle açılır, seçim `avatar` tablosunda, açık mı sunucuda doğrulanır)
- Öğretmen liderliği (`rotalar/ogretmen_liderlik.py`, `oduller.sinif_liderlik/yukselenler/sinif_ozetleri`): kendi sınıfının tüm öğrencileri adlı; sınıflar arası kıyasta yalnızca sınıf toplamı; adlı görüntüleme `erisim_log`'a yazılır. Etkinlik sonucunda soru bazlı istatistik (`odevler.soru_istatistik`, kimliksiz), gelişim raporunda kazanım ısı haritası.
- İKİ ARENA AYRI: smual.app Bilgi Arenası = bireysel (okul.db: bilgi_*, odul, avatar); tahta Sınıf Arenası = /home/ata/arenasinif (kendi sonuclar.db, sınıf düzeyi liderlik, Postgres `soru_kullanim`'a yazar). Okul kodu tahta arenasına bağlanmaz, havuza yalnızca SELECT yapar (tests/test_arena_ayrim.py). Ortak olan tek şey soru havuzu.
- anket (yönetici anketi öğrenci/veli/öğretmene AYRI gönderir; yanıtlar ANONİM: `anket_katilim` ile `anket_yanit` arasında bağ yok; <5 yanıtlı grup sonucu gizli), gelisim (akademik gelişim: yalnızca ödev testi + Form kazanım verisi; küçük grup/yetersiz veri gizli, risk etiketi yok; `kaynaklar/form_toplu.py` toplu okuma), etkinlik (öğretmen Hızlı Etkinlik: havuzdan 3/5/10 soruluk test ödevi)
- sinavlar (yazılı + düzey bazlı deneme takvimi), belgeler (vesikalık foto + yıllık plan: kim neyi görür/değiştirir), dosyalar (yükleme doğrulama + saklama; tür dosya imzasından belirlenir, uzantıdan değil)
- kaynaklar/{program, yoklama, kazanim, soru, sms, zil}: dış veri okuyucular
  (ders programı mudur/ders_programi.json, devamsızlık yoklama_pano.db, kazanım + maraton soruları Postgres soru_havuzu, SMS smssistemi /api/arac/kod-sms, zil tahtayoklama/data/zil.json + okulun kendi tatil takvimi `config/takvim.json`)
- Saat widget'ı (`_saat.html`, rol ana sayfaları) ve zil tablosu (`_zil_tablo.html`, program sayfaları) route'tan değil `deps.py`'deki Jinja global'lerinden (`saat_verisi`, `zil_cizelgesi`) beslenir; canlı durum `static/saat.js`'te, kural `kaynaklar/zil.py::durum` ile aynı tutulmalı. Yeni öğretim yılı/tatil = yalnızca `config/takvim.json`.
- rotalar/{giris, ogrenci, veli, ogretmen, yonetici, ortak, belge_sinav, oyun, arena, anket, gelisim, etkinlik, kisisel}; hepsi `app.py`'de `include_router` ile bağlanır (yeni rota modülü oraya da eklenmeli)

## Kurallar
- Dış kaynaklar SALT-OKUNUR, her istekte okunur, kopyalanmaz.
- Yetkisiz erişim = 404 (varlığı sızdırma).
- `gizli.json` gitignore'lu; repo PUBLIC — şifre/anahtar/token yazma.
- Zaman için daima `zaman.simdi()` kullan (test edilebilirlik).
- Şema değişikliği: `db.GOCLER` listesine yeni eleman ekle (eskileri değiştirme).
- Tahta yoklaması isimle tutuluyor: aynı sınıfta aynı isim/eşleşmeyen isim veliye gösterilmez (yanlış çocuğa devamsızlık yazmamak için); yönetici `/yonetici/eslesmeyen`'de görür.
- Oturum 1 yıl kayan çerez (bilinçli karar); ilk şifre ad+123, zorunlu değişim; veli girişi SMS kodu.

## Mimari notları (birden çok dosyayı okuyunca anlaşılır)
- `ayarlar.AYAR` tek global ayar nesnesi; testler `conftest.py`'deki autouse `gecici_ortam` ile db/dosya/pano/program yollarını `tmp_path`'e monkeypatch'ler. Yeni yol/ayar eklersen aynı fixture'a da ekle, yoksa test gerçek `veri/`'ye yazar.
- Yüklenen dosyalar (`veri/dosyalar`, gitignore'lu) `static/` altında DEĞİL; rastgele adla saklanır, yalnızca yetki kontrolü yapan rotalardan sunulur. Yazma geçici ad + `replace` ile atomik.
- `app.py` orta katmanı: her yanıta güvenlik başlıkları + `Cache-Control: no-store` (static hariç) ve kayan oturum çerezi; 404/şifre-değiştir/giriş yönlendirmeleri exception handler'larla.
- Şema `PRAGMA user_version` ile sürümlenir; her göç tek `BEGIN…COMMIT` içinde çalışır.
- Soru Maratonu: doğru şık istemciye cevaptan önce gitmez, süre sunucuda ölçülür (gösterim zamanı kaydedilir). Postgres `soru_havuzu`'na yazılmaz (`soru_kullanim`/`kullanim_sayisi` arena'nın); tekrar engeli öğrenci bazlı okul.db'de. Rotalar `Accept: application/json` ile JS (`static/maraton.js`) ve JS'siz form akışını birlikte sunar.
- Analitik: `olay` tablosu yalnızca sayaçtır (içerik/IP/cihaz yok); UNIQUE(kullanıcı,tür,nesne,gün,oturum_k) + `INSERT OR IGNORE` ile yenileme/tekrar gönderim tek sayılır. Yazım `analitik.kaydet` ile bellek tamponuna gider (25 kayıt/5 sn), `bosalt()` ile tek işlemde yazılır; olaylar orta katmanda yalnızca 200 GET'ten, rotalarda başarılı işlemden sonra üretilir. Çevrim içi = `oturum.son_nabiz` ≤ 90 sn (`/nabiz`, `static/nabiz.js`). Geçmiş veri yok: grafiklerde veri öncesi günler "veri yok". Yeni olay türü = `analitik.OZELLIKLER`'e ekle. Geri alma: `scripts/geri_al.py --hedef N` (her göç için GERI girdisi; yeni göç eklenince oraya da ekle). Testlerde `analitik.sifirla()` conftest'te çağrılır.
