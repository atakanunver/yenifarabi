# Deneme Karnesi + Rol Görünümleri + AI Yorum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `okul/veri/denemeler/*.pdf` içindeki deneme sonuçlarını okul uygulamasına yüklemek; öğrenci kendi karnesini, sınıf öğretmeni kendi şubesini, yönetici tüm okulu görsün; her seviyede Gemini kimliksiz yorum yazsın.

**Architecture:** Mevcut `deneme`/`deneme_ogrenci` modülü (denemeler.py, rotalar/deneme.py, scripts/deneme_yukle.py) korunur. Tek seferlik betikler PDF → JSON ve JSON → Gemini yorumu üretir, sonuç DB'ye yazılır; sayfalar çalışma anında yalnızca DB okur.

**Tech Stack:** FastAPI + Jinja2 + SQLite (okul), `pdfplumber` (yalnızca `server/venv`, okul venv'ine EKLENMEZ), Gemini REST (`urllib`, yeni kütüphane YOK).

**Spec:** 2026-10-29 sohbet kararları (bu dosyanın altındaki "Kararlar").

## Global Constraints
- Sıralama/öğrenciler arası karşılaştırma YOK; PDF'teki Sıra, Okul/İlçe/İl/Genel sıra sütunları alınmaz.
- Gemini'ye ad, okul no, sınıf/şube adı GİTMEZ; yalnız ders netleri, kazanım adı/başarısı ve sayılar.
- Anahtar `server/config/api_keys.json::gemini_api_keys` (kodla okunur, asla basılmaz/loglanmaz/commit edilmez); `server/.env` yok.
- <5 katılımcılı şube ortalaması gizli ("yetersiz veri").
- Şema değişikliği = `db.GOCLER`'e yeni eleman (eskiler değişmez) + `scripts/geri_al.py` GERI girdisi.
- Eşleşmeyen/uyuşmayan öğrenci uygulanmaz, listelenir; "Mezun" ve `-XX` şubeli satırlar atlanır.
- Yorumlar karşılaştırmasız, destekleyici dilde (DECISIONS 2026-10-14); yalnız PDF'te olan veriye dayanır.
- Yükleme `yayinda=0` başlar; Atakan onaylayınca yayınlanır. Commit yalnızca istenirse.

## Review Focus
- Ad bozuk/Ö.No=0 satırı → eşleşmez, listelenir, yanlış öğrenciye yazılmaz.
- Şubede 1-4 katılımcı → ortalama/ortak eksik gizli, öğretmen yine kendi öğrencilerini adıyla görür.
- Öğretmen başka şubenin deneme sayfasını açar → 404.
- Gemini hata/zaman aşımı/boş yanıt → satırın `analiz`'i boş kalır, betik devam eder, yeniden çalıştırmada yalnız boşlar üretilir (idempotent).
- Gemini istemi (prompt) içinde ad/no/şube sızmaması (testle pinlenir).

## Task 1: PDF → JSON okuyucu
**Files:** Create `okul/scripts/deneme_pdf_oku.py`; Test `okul/tests/test_deneme_pdf.py`
**Interfaces:** Produces `satir_ayristir(satir: str) -> dict | None` (`okul_no:int, ad_soyad:str, sinif:str, dersler:{ders:{d,y,net}}, toplam_net:float`), `kurum_kazanimlari(sayfa_tablolari) -> list[{ders,kazanim,soru,d,y,b}]`, CLI `server/venv/bin/python -I okul/scripts/deneme_pdf_oku.py <pdf> <cikti.json> --ad "<deneme adı>"`; çıktı `deneme_yukle.py` biçimi + `kazanimlar` alanı.
- [ ] Test (sentetik satırlarla, gerçek ad yok): `"1 0 AYŞE TEKE 11-A 31 4 30,00 3 2 2,50 ... 330,631 2423"` → sıra ve sıralama sütunları atılmış, ders netleri doğru; `"Mezun3-7XX"` ve `12-XX` → `None`; bitişik `"MENEKŞE RANA CENGİZ11-A"` ad/sınıf ayrışır.
- [ ] Çalıştır → FAIL; sonra `satir_ayristir`, `kurum_kazanimlari` yaz (sütun sırası PDF başlığındaki ders sırası: Türkçe, Tarih-1, Coğrafya-1, Felsefe, Din Kül., Matematik-1, Geometri, Fizik, Kimya, Biyoloji; D Y N üçlüleri). Sayıda virgül ondalık.
- [ ] Öğrenci sayfalarındaki (14-35) kazanım tabloları pdfplumber `extract_tables` ile güvenilir okunuyorsa `ogrenci_kazanimlari(sayfa)` ekle (öğrenci başına kazanım adı + doğru/yanlış/boş); bozuksa yalnız kurum düzeyi kazanım kullanılır ve bu kısıt kullanıcıya raporlanır.
- [ ] Doğrulama: iki gerçek PDF'te çalıştır, çıkan öğrenci sayısı 22 (11. sınıf) / 20 (12. sınıf) − atlananlar; çıktı JSON `.gitignore`'lu `okul/veri/` altına.

## Task 2: Sınıf ve okul özet mantığı
**Files:** Modify `okul/denemeler.py`; Test `okul/tests/test_denemeler_ozet.py`
**Interfaces:** Produces `sinif_ozeti(conn, deneme_id, sinif) -> dict | None` (`katilim:int, ortalama_net:float|None, ders_ortalamalari:{ders:float}|None, ortak_eksikler:list, ogrenciler:[{okul_no,ad,net,deneme_ogrenci_id}]`; `ortalama_net`/`ders_ortalamalari`/`ortak_eksikler` katılım<5 ise `None`/`[]`), `okul_ozeti(conn, deneme_id) -> dict` (`katilim, ortalama_net, subeler:[{sinif,katilim,ortalama_net|None}], ortak_eksikler`), `ogretmen_deneme_siniflari(conn, ogretmen_id) -> list[str]` (`yetki.ogretmen_siniflari` kullanır).
- [ ] Testler: 5 öğrencili şube ortalaması doğru; 4 öğrencili şubede `None`; yayında=0 deneme → `None`; hiçbir fonksiyon sıra/rank alanı döndürmez.
- [ ] FAIL → uygula (`veri` JSON'unu `_coz` gibi güvenli oku; girdi=1 filtre) → PASS.

## Task 3: Rotalar ve şablonlar
**Files:** Modify `okul/rotalar/deneme.py`, `okul/templates/ogrenci/deneme.html` (yalnız kazanım/yorum alanı gerekirse); Create `okul/templates/ogretmen/deneme.html`, `okul/templates/yonetici/deneme.html`; Test `okul/tests/test_deneme_roller.py`
**Interfaces:** Consumes Task 2. Produces `GET /ogretmen/deneme`, `GET /ogretmen/deneme/{deneme_id}/{sinif}` (rol `ogretmen`, şube kendi görevleri değilse 404), `GET /yonetici/deneme`, `GET /yonetici/deneme/{deneme_id}` (rol `yonetici`). Öğretmen/yönetici adlı öğrenci görüntülemesi `erisim_log`'a yazılır (`ogretmen_liderlik` örüntüsü).
- [ ] Testler: öğretmen başka şube → 404; öğrenci `/ogretmen/deneme` → 404; yönetici tüm şubeleri görür; sayfada "sıra" metni yok; adlı görüntüleme `erisim_log`'da.
- [ ] FAIL → rota+şablon (mevcut "kareli defter" şablonlarını örnek al; yeni CSS gerekirse `okul.css?v=N` ve `sw.js` SURUM+STATIK artır) → PASS.
- [ ] Ana sayfa girişleri: öğretmen/yönetici ana sayfasına tek link kartı (`is defined` korumalı Jinja global kullanma; veriyi route'tan geçir).

## Task 4: Gemini yorum betiği
**Files:** Create `okul/scripts/deneme_yorum.py`; Modify `okul/db.py` (`GOCLER` + `deneme_sinif_yorum(deneme_id, sinif, yorum)` V36), `okul/scripts/geri_al.py` (V36 GERI); Test `okul/tests/test_deneme_yorum.py`
**Interfaces:** Produces `ogrenci_istemi(veri: dict, zayif: list) -> str`, `sinif_istemi(ozet: dict) -> str`, `okul_istemi(ozet: dict) -> str` (hepsi kimliksiz), `gemini(istem: str) -> str | None` (REST `generativelanguage.googleapis.com`, model `gemini-2.5-flash`, sıcaklık ≤0,35, zaman aşımı 60 sn, hata → `None`), CLI `venv/bin/python scripts/deneme_yorum.py <deneme_adı> [--kuru]` (yalnız `analiz`/`tavsiye` boş olanları üretir).
- [ ] Testler: `ogrenci_istemi` çıktısında ad, okul_no, şube ("11-A") geçmez; `gemini` monkeypatch'li `None` → satır boş kalır, betik hata vermez; ikinci çalıştırma dolu satırları yeniden üretmez; `--kuru` Gemini'yi çağırmaz, yalnız kaç satır üretileceğini yazar.
- [ ] FAIL → uygula. İstem sabit çerçeve: kazanım odaklı somut öneri, 120-150 kelime, karşılaştırma/sıralama/risk etiketi yok, yalnız verilen veriden. Anahtar `server/config/api_keys.json` içinden kodla okunur, hata iletisinde basılmaz.
- [ ] Doğrulama: `--kuru` sayıları; ardından tek deneme için gerçek çalıştırma, 2-3 yorum Atakan'a okutulur.

## Task 5: Yükleme ve canlıya alma
- [ ] PDF → JSON (iki PDF) → `deneme_yukle.py <json> --kuru` (eşleşen/eşleşmeyen/uyuşmayan sayıları rapor) → Atakan onayı → gerçek yükleme (`yayinda=0`) → `deneme_yorum.py` → Atakan örnek karneleri kontrol eder → `--yayinla`.
- [ ] `cd okul && venv/bin/python -m pytest -q` tamamı geçmeli; `.venv-tools/bin/ruff check` dokunulan dosyalarda yeni hata yok.
- [ ] `sudo systemctl restart farabi-okul` (ders saati dışında) → `systemctl is-active farabi-okul`, `/giris` 200.
- [ ] DECISIONS.md'ye tek satır: Gemini kimliksiz yorum kararı (yerel-gemma kuralından bilinçli istisna) ve sıralamasız tasarım.
