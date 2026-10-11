# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Dijital Okul (okul/)

Mobil öncelikli okul portalı: öğrenci/veli/öğretmen/yönetici. FastAPI + Jinja2 + vanilla CSS ("kareli defter" teması, imza öğe `.kareler`), SQLite (kendi verisi). Port 9090, dışarıdan https://smual.app (Cloudflare Tunnel).
Spec: `docs/superpowers/specs/2026-10-10-dijital-okul-design.md`.

## Çalıştırma / test
- Test: `cd okul && venv/bin/python -m pytest -q` (110 test). Tek test: `venv/bin/python -m pytest tests/test_odevler.py::test_adi -q`. Lint: repo kökünden `.venv-tools/bin/ruff check okul/<dosya>` (okul/ kapsam listesinde değil; yalnızca dokunduğun dosyayı ver)
- Servis: `farabi-okul.service` (kurulum yorumu `okul/systemd/farabi-okul.service` içinde). Kod değişince: `sudo systemctl restart farabi-okul`.
- İlk yönetici: `venv/bin/python scripts/yonetici_olustur.py "Ad Soyad" kullanici_adi`
- CSS değişirse `templates/base.html` içindeki `okul.css?v=N` ve `static/sw.js` içindeki SURUM/STATIK'i artır.

## Modül haritası
- ayarlar, zaman, metin: yapılandırma, saat, metin yardımcıları
- db (şema + `GOCLER`), auth, deps, yetki
- duyurular, odevler, ice_aktar
- sinavlar (yazılı + düzey bazlı deneme takvimi), belgeler (vesikalık foto + yıllık plan: kim neyi görür/değiştirir), dosyalar (yükleme doğrulama + saklama; tür dosya imzasından belirlenir, uzantıdan değil)
- kaynaklar/{program, yoklama, kazanim, sms}: dış veri okuyucular
  (ders programı mudur/ders_programi.json, devamsızlık yoklama_pano.db, kazanım Postgres soru_havuzu, SMS smssistemi /api/arac/kod-sms)
- rotalar/{giris, ogrenci, veli, ogretmen, yonetici, ortak, belge_sinav}; hepsi `app.py`'de `include_router` ile bağlanır (yeni rota modülü oraya da eklenmeli)

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
