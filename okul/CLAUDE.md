# Dijital Okul (okul/)

Mobil öncelikli okul portalı: öğrenci/veli/öğretmen/yönetici. FastAPI + Jinja2 + vanilla CSS ("kareli defter" teması, imza öğe `.kareler`), SQLite (kendi verisi). Port 9090, dışarıdan https://smual.app (Cloudflare Tunnel).
Spec: `docs/superpowers/specs/2026-10-10-dijital-okul-design.md`.

## Çalıştırma / test
- Test: `cd okul && venv/bin/python -m pytest -q` (81 test)
- Servis: `farabi-okul.service` (kurulum yorumu `okul/systemd/farabi-okul.service` içinde). Kod değişince: `sudo systemctl restart farabi-okul`.
- İlk yönetici: `venv/bin/python scripts/yonetici_olustur.py "Ad Soyad" kullanici_adi`
- CSS değişirse `templates/base.html` içindeki `okul.css?v=N` ve `static/sw.js` içindeki SURUM/STATIK'i artır.

## Modül haritası
- ayarlar, zaman, metin: yapılandırma, saat, metin yardımcıları
- db (şema + `GOCLER`), auth, deps, yetki
- duyurular, odevler, ice_aktar
- kaynaklar/{program, yoklama, kazanim, sms}: dış veri okuyucular
  (ders programı mudur/ders_programi.json, devamsızlık yoklama_pano.db, kazanım Postgres soru_havuzu, SMS smssistemi /api/arac/kod-sms)
- rotalar/{giris, ogrenci, veli, ogretmen, yonetici, ortak}

## Kurallar
- Dış kaynaklar SALT-OKUNUR, her istekte okunur, kopyalanmaz.
- Yetkisiz erişim = 404 (varlığı sızdırma).
- `gizli.json` gitignore'lu; repo PUBLIC — şifre/anahtar/token yazma.
- Zaman için daima `zaman.simdi()` kullan (test edilebilirlik).
- Şema değişikliği: `db.GOCLER` listesine yeni eleman ekle (eskileri değiştirme).
- Tahta yoklaması isimle tutuluyor: aynı sınıfta aynı isim/eşleşmeyen isim veliye gösterilmez (yanlış çocuğa devamsızlık yazmamak için); yönetici `/yonetici/eslesmeyen`'de görür.
- Oturum 1 yıl kayan çerez (bilinçli karar); ilk şifre ad+123, zorunlu değişim; veli girişi SMS kodu.
