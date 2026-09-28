# Dashboard yük azaltma — rapor sayfalama, gzip, gizli sekmede polling durdurma

Tarih: 2026-09-28 · Kapsam: yalnızca `tahtayoklama/dashboard/` · Plan: Opus, uygulama: Sonnet (Kural 11)

## Sorun ve ölçüm

- `/admin/rapor` detay tablosu seçilen aralığın TÜM satırlarını tek HTML'e basıyor
  (`admin.py::rapor` → `admin_rapor.html` `{% for d in detay %}`).
- Büyüme: ~56 satır/okul günü → yılda ~10 bin satır.
- Sentetik ölçüm (şablon render): 720 satır 174 KB, 1.700 satır 388 KB,
  10.080 satır **2,2 MB / 87 ms**. SQL (indeksli) ve `_devamsizlik_sayaci`
  (10k satırda 5 ms) darboğaz DEĞİL → sorun tarayıcıya giden HTML boyutu.
- Ayrıca `kenar.js` (her sayfa, 30 sn), `sistem_durumu.html` (15 sn),
  `pano.html` (60 sn) sekme arka plandayken de istek atıyor.

## Değişiklik 1 — Detay tablosunu sayfalama (`admin.py`, `admin_rapor.html`)

Kasıtlı olarak **Python tarafında dilimleme**, SQL `LIMIT/OFFSET` değil:
özet (`_devamsizlik_sayaci`) ve CSV zaten tüm veriye ihtiyaç duyuyor, sunucu
maliyeti ölçüldü ve ihmal edilebilir (Kural 10). `_rapor_verisi` ve
`/admin/rapor/csv` DOKUNULMAZ → CSV davranışı birebir aynı kalır.

1. `admin.py` sabitlere: `_RAPOR_SAYFA_BOYUTU = 100`.
2. Yeni saf fonksiyon (test edilebilir):
   ```python
   def _sayfala(satirlar: list, sayfa: str | None, boyut: int) -> tuple[list, int, int]:
       """(dilim, geçerli_sayfa, toplam_sayfa). Geçersiz/eksik/aralık dışı
       sayfa değeri en yakın geçerli sayfaya kıstırılır; boş listede (…, 1, 1)."""
   ```
   `int()` hatası → 1; `< 1` → 1; `> toplam` → toplam. `toplam_sayfa = max(1, ceil(len/boyut))`.
3. `rapor()` imzasına `sayfa: str | None = None` eklenir (str — `sinif_id` ile
   aynı desen, 422 vermesin). `devamsizlik` TAM `detay`'dan hesaplanmaya devam
   eder; şablona `detay` yerine dilim gider, ayrıca `sayfa`, `toplam_sayfa`,
   `toplam_kayit` (= `len(detay)`) eklenir.
4. `admin_rapor.html`:
   - Detay `<h2>`'ye `id="detay"` (sayfa bağlantıları `#detay` ile tabloya iner).
   - Açıklama satırına: "Toplam N kayıt · sayfa x / y" (Türkçe, cümle düzeni).
   - Tablonun altına yalnızca `toplam_sayfa > 1` iken sayfa gezinmesi:
     "← Önceki" / "Sonraki →" bağlantıları + "x / y". Bağlantılar mevcut
     `csv_kuyruk` değişkenini yeniden kullanır: `/admin/rapor{{ csv_kuyruk }}&sayfa=N#detay`.
     İlk/son sayfada ilgili bağlantı yerine pasif metin (`aria-disabled`).
   - Filtre formuna `sayfa` gizli alanı EKLENMEZ → yeni filtre sayfa 1'den başlar.
   - Stil: `pano.css`'e tek küçük blok (`.sayfa-gezinme`), yalnızca var olan
     token'lar (`--renk-*`, `--yaricap`), 0.15 s geçiş; ham hex yok, yeni
     değişken yok (tahtayoklama/CLAUDE.md tasarım kuralları).

## Değişiklik 4 — Gzip (`app.py`)

```python
from starlette.middleware.gzip import GZipMiddleware   # FastAPI'nin mevcut bağımlılığı, yeni paket değil
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
```
`app = FastAPI(...)` satırının hemen altına. `compresslevel=6` (varsayılan 9
yerine): oran farkı küçük, CPU belirgin daha az.
Bilinen yan etki: ekran görüntüsü (JPEG) de sıkıştırılmaya çalışılır — kazanç
yok ama maliyet birkaç ms, seyrek çağrı; kabul. CSV `StreamingResponse` gzip ile
uyumlu (tarayıcı indirmede açar). Sağlık uçlarını kullanan dış çağıran yok
(smssistemi yalnızca SQLite'ı okuyor), `Accept-Encoding` göndermeyen istemci
sıkıştırılmamış alır → geriye uyumlu.

## Değişiklik 5 — Gizli sekmede polling durdurma (3 dosya)

Aynı desen üç yerde, `setInterval` süresi DEĞİŞMEZ:
- Zamanlayıcı geri çağırması başında `if (document.hidden) return;`
- `document.addEventListener('visibilitychange', () => { if (!document.hidden) <güncelle>(); });`
  → sekmeye dönünce veri hemen tazelenir.

Dosyalar:
- `static/kenar.js` — `miniDurumGuncelle` (ES5 stili korunur: `function`, `var`).
- `templates/sistem_durumu.html` — `durumGuncelle`.
- `templates/pano.html` — `tabloyuGuncelle`. Not: pano öğretmenin "hangi
  sınıfta yoklama eksik" ekranı; görünür olduğunda davranış aynı, yalnızca
  arka planda istek kesilir. Elle "Şimdi yenile" ve uzaktan başlat
  akışlarına dokunulmaz.

Sunucudaki `yoklayici` SSH polling döngüsü (`app.py::_polling_dongusu`) bu
değişiklikten ETKİLENMEZ — o tarayıcıdan bağımsız.

## Testler (`unittest`, pytest DEĞİL)

Yeni `test_rapor_sayfalama.py` (`unittest.TestCase`):
- `_sayfala`: boş liste → `([], 1, 1)`; 250 satır/100 → 3 sayfa, sayfa 3 = 50 satır;
  `"0"`, `"-5"`, `"abc"`, `None` → sayfa 1; `"99"` → son sayfa; tam bölünen (200) → 2 sayfa.
- Gzip: `import app as app_modulu` → `any(m.cls is GZipMiddleware for m in app_modulu.app.user_middleware)` —
  yapılandırma testi. ⚠️ `TestClient` KULLANILMAZ: dashboard venv'inde `httpx`
  yok ve üretim venv'ine paket kurulmaz. Gerçek sıkıştırma deploy sonrası
  `curl` ile doğrulanır (aşağıdaki "Deploy ve doğrulama" 2. adım).

Çalıştırma:
```bash
cd tahtayoklama/dashboard
venv/bin/python -m unittest discover -p 'test_*.py'
../../.venv-tools/bin/ruff check admin.py app.py test_rapor_sayfalama.py   # önce/sonra fark
```

## Deploy ve doğrulama

1. Testler yeşil → `sudo systemctl restart farabi-yoklama-dashboard.service`.
2. `curl -sI -H 'Accept-Encoding: gzip' http://localhost:8010/static/pano.css | grep -i content-encoding`.
3. Tarayıcıda (Atakan): `/admin/rapor` — özet tam, detay 100 satır, sayfa
   gezinmesi filtreyi koruyor, CSV hâlâ tüm aralığı indiriyor; pano ve
   sistem durumu sekmeye dönünce hemen tazeleniyor.

## Geri alma

Her değişiklik bağımsız; tek commit'i `git revert` yeterli. Gzip acil kapatma:
`app.py`'deki tek `add_middleware` satırı.

## Kapsam dışı

SQL `LIMIT/OFFSET`, özet tablosu/önbellek, veri silme/arşivleme, ders
programı/zil mantığı, `/admin/rapor/csv`.
