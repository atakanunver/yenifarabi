# Panel yeniden tasarımı: uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tahtayoklama/dashboard` arayüzünü üst alan menüsü + sol sayfa menüsü kabuğuna, sade koyu varsayılan temaya (9 tema, temaya özel font), isimli yoklama ızgarasına ve liste + sağ ayrıntı paneli desenine tek seferde geçirmek.

**Architecture:** Geliştirme canlıdan ayrı worktree'de (`panel-yeniden-tasarim` dalı) yapılır, canlı veriye yazmayan bir önizleme örneğinde (port 8098) Atakan'a gösterilir. Menü ağacı `menu.py`'de alan → sayfa yapısına döner; `taban.html` yeni kabuğu bu ağaçtan üretir. Renk/font token'ları `static/tema.css`'te (9 tema), yeni bileşenler `static/bilesen.css`'te; eski `pano.css` sayfalar taşınana kadar yüklü kalır, sonda silinir.

**Tech Stack:** FastAPI + Jinja2, düz CSS, düz JS, SQLite, `unittest` (pytest YOK).

**Spec:** `docs/superpowers/specs/2026-10-30-panel-yeniden-tasarim-design.md`

## Global Constraints
- Build adımı, npm, React, Tailwind, Bootstrap, CDN YOK; yeni kütüphane yok. Fontlar yerel woff2 (latin + latin-ext), açık lisans.
- Renkler yalnız `--renk-*` değişkeni; ham hex yalnız tema tanım bloklarında. Her tema bloğu `:root`'taki tüm değişkenleri tanımlar.
- Arayüz Türkçe, cümle düzeni; `text-transform: uppercase` yok.
- 1366×768'de hiçbir sayfada belge ya da kaydırma kutusu yatay taşmaz (≤720 px telefon hariç).
- Klavye ile tam gezinme, görünür odak, `aria-current`, `aria-expanded`, `prefers-reduced-motion`.
- URL'ler, form POST uçları, yetki kontrolleri, veri akışları DEĞİŞMEZ.
- CSS/JS bağlantıları `?v={{ agac.surum }}` taşır; her `Jinja2Templates` örneğinde `templates.env.globals["menu_agaci"]` kalır.
- Canlı dizin `/home/ata/farabi` dondurulmuş: oraya yalnız Task 11'de merge yapılır. Restart yalnız 08:00-17:00 TR dışında.
- Testler: `cd <worktree>/tahtayoklama/dashboard && /home/ata/farabi/tahtayoklama/dashboard/venv/bin/python -m unittest discover -p 'test_*.py'` (worktree'de venv yok, canlının venv'i kullanılır; pip install YOK).

## Review Focus
1. Bir hücrede çok uzun devamsız listesi (18 isim): satır aşağı uzar, 1366'da yatay kaydırma çıkmaz → Task 6 testi `test_uzun_isim_listesi_hucrede_metin`.
2. Menüde olmayan sayfa (`/admin/siniflar/5/ogrenciler`, `/kazanim`, `/b/atos`): kabuk çökmeden açılır, önek eşleşen alan aktif ya da hiçbiri → Task 2 testi `test_menude_olmayan_yol`.
3. Kayıtlı tema geçersiz (`klasik`, silinmiş ad, bozuk değer) → `klasik/yumusak` argon'a, diğerleri sade koyuya düşer → Task 3 testi `test_tema_listesi_ve_varsayilan`.
4. JS çalışmazsa: alan sekmeleri ve sol menü düz bağlantı, ayrıntı paneli `?duzenle=` ile sunucuda açılır → Task 4 ve Task 7 render testleri bağlantıları ve paneli JS'siz HTML'de arar.
5. Okul verisi panelinde doğrulama hatası (geçersiz TC): panel hata mesajıyla açık kalır, kayıt seçili kalır → Task 7 testi `test_hata_sonrasi_panel_acik`.

---

### Task 1: Worktree ve canlıya yazmayan önizleme modu

**Files:**
- Modify: `tahtayoklama/dashboard/db.py:11` (`DB_YOLU`)
- Modify: `tahtayoklama/dashboard/app.py:105-118` (`lifespan`, middleware)
- Create: `tahtayoklama/dashboard/scripts/onizleme.sh`
- Test: `tahtayoklama/dashboard/test_onizleme.py`

**Interfaces:**
- Produces: ortam değişkenleri `FARABI_PANEL_DB` (SQLite yolu) ve `FARABI_ONIZLEME=1` (arka plan görevleri yok, değiştiren istek yok); `app.ONIZLEME: bool`.

- [ ] **Step 1:** `superpowers:using-git-worktrees` ile `/home/ata/farabi` deposundan `atos-anythingllm-gemma`'dan (HEAD, `f3c1915` sonrası) `panel-yeniden-tasarim` dalında worktree aç: `/home/ata/farabi-tasarim`. Doğrula: `git -C /home/ata/farabi-tasarim branch --show-current` → `panel-yeniden-tasarim`; `git -C /home/ata/farabi status` değişmemiş.
- [ ] **Step 2: Failing test** `test_onizleme.py`:
  - `test_db_yolu_ortamdan`: `FARABI_PANEL_DB=/tmp/x.db` ile `importlib.reload(db)` → `db.DB_YOLU == Path("/tmp/x.db")`; ortam yokken eski varsayılan.
  - `test_onizlemede_post_reddedilir`: `ONIZLEME=True` iken middleware'e `POST /admin/okul-verisi/personel` → 403, gövdede "Önizlemede değişiklik kapalı"; `POST /giris` ve `POST /cikis` geçer; `GET /` geçer.
  - Uçlar `Request` elle kurularak test edilir (venv'de httpx yok; örnek `test_tahta_api.py`).
- [ ] **Step 3:** Çalıştır, FAIL gör.
- [ ] **Step 4:** `db.DB_YOLU = Path(os.environ.get("FARABI_PANEL_DB") or <eski yol>)`. `app.py`: `ONIZLEME = os.environ.get("FARABI_ONIZLEME") == "1"`; `lifespan` ONIZLEME'de `_polling_dongusu` ve `sistem_durumu.toplayici_dongusu` başlatmaz; `@app.middleware("http")` ONIZLEME'de GET/HEAD dışı ve `/giris`,`/cikis` dışı istekleri 403 düz metinle reddeder. Canlıda (değişken yok) davranış birebir aynı.
- [ ] **Step 5:** `scripts/onizleme.sh`: canlı `veri/yoklama_pano.db`'yi `sqlite3 ... ".backup"` ile `/tmp/farabi-onizleme/yoklama_pano.db`'ye kopyalar; worktree'de `config` yoksa canlı `config`'e sembolik bağ kurar (gitignore'lu, commit'lenmez); `FARABI_ONIZLEME=1 FARABI_PANEL_DB=... /home/ata/farabi/tahtayoklama/dashboard/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8098` (cwd worktree dashboard).
- [ ] **Step 6:** Testler PASS; `scripts/onizleme.sh` arka planda → `curl -s -o /dev/null -w '%{http_code}' http://localhost:8098/giris` → `200`; `journalctl -u farabi-yoklama-dashboard` canlıda değişiklik yok.
- [ ] **Step 7: Commit** `git add db.py app.py scripts/onizleme.sh test_onizleme.py && git commit -m "dashboard: canlıya yazmayan önizleme modu (FARABI_ONIZLEME, FARABI_PANEL_DB)"`

### Task 2: Menü ağacı alan → sayfa yapısına

**Files:**
- Modify: `tahtayoklama/dashboard/menu.py` (`MENU` → `ALANLAR`, `menu_agaci`)
- Test: `tahtayoklama/dashboard/test_menu.py`, `tahtayoklama/dashboard/test_panel_git.py`

**Interfaces:**
- Produces:
  - `ALANLAR: list[dict]` — her alan `{"ad", "anahtar", "kisayol", "ikon", "sayfalar": [{"ad", "href", "ikon", "yeni_sekme"?, "sayac"?}]}`.
  - `ACIL: dict` (`/acil`, kisayol `a`), `ATOS: dict` (href `"atos"`, kisayol `t`), `AYARLAR: list[dict]` (Atos iş ve ayarlar `/b/atos`, Yazdır, Klavye kısayolları, Çıkış — `eylem` ya da `href`).
  - `TEMALAR: list[tuple[str, str]]` (Task 3 doldurur; burada tanımlanır).
  - `menu_agaci(yol: str, sorgu: str = "") -> dict` anahtarları: `alanlar` (kopya, `aktif` işaretli), `aktif_alan` (dict|None), `sayfalar` (aktif alanın sayfaları, eşleşen `aktif`), `konum` (`[alan.ad, sayfa.ad]` ya da `[]`), `acil`, `atos`, `ayarlar`, `temalar`, `ders`, `surum`.
- Alanlar ve sayfalar (sıra bu, href'ler bugünkü `MENU`'den):
  - Yoklama `y`: Ders ızgarası `/`, Bugünkü liste `/bugun`, Rapor `/admin/rapor`, Aylık özet `/aylik-ozet`, Kulüp yoklaması `/kulup-yoklama`.
  - Öğrenci ve personel `p`: Öğrenciler ve veliler `/admin/okul-verisi?sekme=ogrenci`, Personel `?sekme=personel`, Sınıflar ve tahtalar `/admin/siniflar`, Ders programı `?sekme=program`, Zil saatleri `?sekme=zil`, Kulüpler `/admin/kulupler`, Değişiklik günlüğü `?sekme=denetim`.
  - İletişim `i`: Veli mesajları `/veli-mesajlari` (`sayac: "veli"`), SMS gönder `/sms-git`, Yoklama SMS `/yoklama-sms-git`, SMS otomasyonu `/otomasyon-git`, Doğum günleri `/dogum` (bu dördü `yeni_sekme`), Tahta duyuru `/admin/uzaktan#duyuru`.
  - Eğitim `e`: Kelebek `/kelebek-git`, smual.app `SMUAL_URL`, smual.app yönetim `SMUAL_YONETIM_URL` (hepsi `yeni_sekme`).
  - Güvenlik `k`: DVR kameralar `/kameralar`, IP kameralar (yedek) `/kameralar-ip`, Kamera kayıtları `/kameralar-kayit`, Güvenlik ekranı `/guvenlik`, Kiosk yüz tanıma `KIOSK_YUZ_PANELI` (`yeni_sekme`).
  - Sistem `s`: Tahtalar `/admin/uzaktan`, Sistem durumu `/sistem-durumu`, Servis yönetimi `/servisler`, Zamanlanmış görevler `/zamanlanmis-gorevler`, Sunucular `/sunucular`, Zil paneli `/panel-git/zil`, Pano paneli `/panel-git/pano`, Kiosk paneli `/panel-git/kiosk`, Bilgehan paneli `/panel-git/bilgehan` (son dördü `yeni_sekme`).

- [ ] **Step 1: Failing tests** `test_menu.py`'yi yeni yapıya çevir (eski `MENU` sırası testleri yerine):
  - `test_alan_sirasi`: `[a["ad"] for a in menu.ALANLAR] == ["Yoklama", "Öğrenci ve personel", "İletişim", "Eğitim", "Güvenlik", "Sistem"]`.
  - `test_kisayollar_benzersiz`: alan kisayolları + `ACIL` + `ATOS` benzersiz.
  - `test_aktif_isaretleme`: `menu_agaci("/servisler")` → `aktif_alan["ad"] == "Sistem"`, `konum == ["Sistem", "Servis yönetimi"]`, aktif sayfa tek.
  - `test_ana_sayfa`: `menu_agaci("/")` → `konum == ["Yoklama", "Ders ızgarası"]`; `menu_agaci("/admin/rapor")`'da "Ders ızgarası" aktif değil.
  - `test_okul_verisi_sekme_duyarli_aktif`: `("", "Öğrenciler ve veliler")`, `("sekme=personel", "Personel")`, `("sekme=denetim", "Değişiklik günlüğü")`.
  - `test_menude_olmayan_yol` (Review Focus 2): `/admin/siniflar/5/ogrenciler` → aktif alan "Öğrenci ve personel"; `/kazanim` ve `/b/atos` → `aktif_alan is None`, `konum == []`, istisna yok.
  - Korunanlar: tüm dahili href'lerin route'u var, dış bağlantılarda `@` yok, `DAHILI` kümesi menüde, kaynak `ALANLAR` bozulmaz (deepcopy), `menu_agaci` her şablon ortamında global.
  - `test_panel_git.py::test_menu_dogrudan_adrese_degil_rotaya_gider`: hrefleri `ALANLAR[*]["sayfalar"]`'dan topla.
- [ ] **Step 2:** FAIL gör.
- [ ] **Step 3:** `menu.py`'yi uygula. `_eslesir` aynen kalır. Eşleşme: tüm alanların tüm sayfaları taranır, ilk eşleşen sayfa ve alanı aktif. `grep -rn "menu.MENU" --include=*.py` ile başka kullanım varsa `ALANLAR`'a çevir.
- [ ] **Step 4:** Tüm testler PASS (`taban.html` henüz eski `agac.menu`'yü kullanıyor; geçici uyum için `menu_agaci` çıktısına Task 4'te silinecek `"menu": []` koyma — onun yerine Task 2 ve Task 4 aynı commit dizisinde ardışık uygulanır; `test_taban_*` render testleri bu task'ta `@unittest.skip("Task 4")` ile işaretlenir ve Task 4'te açılır).
- [ ] **Step 5: Commit** `"dashboard: menü ağacı 6 alan → sayfa yapısına"`

### Task 3: 9 tema, temaya özel font

**Files:**
- Create: `tahtayoklama/dashboard/static/tema.css` (font-face'ler + `:root` + 8 `:root[data-tema=…]` bloğu)
- Create: `tahtayoklama/dashboard/static/fontlar/*.woff2`
- Modify: `tahtayoklama/dashboard/static/pano.css` (baştaki font-face ve tema blokları buradan `tema.css`'e taşınır)
- Modify: `tahtayoklama/dashboard/static/tema.js`, `tahtayoklama/dashboard/menu.py` (`TEMALAR`)
- Test: `tahtayoklama/dashboard/test_tema.py`

**Interfaces:**
- Produces: `menu.TEMALAR = [("sade-koyu","Sade koyu"), ("kurumsal","Sakin kurumsal"), ("lacivert","Lacivert"), ("argon","Argon açık"), ("argon-koyu","Argon koyu"), ("material","Material açık"), ("material-koyu","Material koyu"), ("black","Black"), ("koyu","Taş Tahta")]`; varsayılan `sade-koyu` (`:root` bloğu sade koyudur; `argon` artık `data-tema="argon"` bloğu). Yeni token'lar (tüm temalarda): `--yazi-tipi`, `--yazi-tipi-baslik`, `--yazi-tipi-sayi`, `--bosluk-1..5` (0.25/0.5/0.75/1/1.5rem), `--punto-kucuk/-govde/-baslik` (0.75/0.85/1.35rem), `--renk-ust-zemin/-ust-metin/-ust-aktif` (üst çubuk; lacivert'te koyu lacivert).
- Renkler: sade koyu = örnek ekran C (zemin `#0d1117`, yüzey `#111720`, kenar `#222a35`, metin `#e6edf3`, soluk `#8b98a8`, birincil `#7cb3ff`, yeşil `#5fd38a`, amber `#f3b35b`, kırmızı `#ff8a80`); kurumsal = örnek A (`#ffffff`, `#e3e7ec`, `#0f172a`, birincil `#1d4ed8`); lacivert = örnek B (içerik `#f4f6f9`, üst çubuk `#0f1b2d`). Diğer 6 temanın bugünkü değerleri korunur.

- [ ] **Step 1: Atakan'dan indirme onayı al** (sohbette, dosya adı/kaynak/boyutla): Inter (sade koyu), Source Sans 3 (kurumsal), IBM Plex Sans (lacivert), Roboto (material, material-koyu), Nunito (Taş Tahta); Geist zaten var (argon, argon-koyu, black). Kaynak: `@fontsource/<ad>` paketinin `files/*-latin-{400,600}-normal.woff2` ve `latin-ext` karşılıkları (jsdelivr'den tek seferlik indirme, çalışma anında CDN yok). Onay yoksa yalnız Geist + sistem fontlarıyla devam et ve bunu raporla.
- [ ] **Step 2: Failing tests** `test_tema.py`:
  - `test_her_tema_tum_tokenlari_tanimlar`: `tema.css`'i regex ile böl; `:root` bloğundaki `--*` adları kümesi, her `data-tema` bloğunda da var (eksik ad listesi boş).
  - `test_tema_listesi_ve_varsayilan` (Review Focus 3): `menu.TEMALAR` anahtarları = `tema.css`'teki `data-tema` adları ∪ {"sade-koyu"}; `tema.js`'te varsayılan `sade-koyu`, eski `klasik`/`yumusak` → `argon`, bilinmeyen → `sade-koyu`, `prefers-color-scheme` kullanılmaz.
  - `test_font_dosyalari_var`: `tema.css`'teki her `url(/static/fontlar/...)` dosyası diskte.
  - `test_buyuk_harf_yok`: `tema.css` ve `bilesen.css`'te `text-transform: uppercase` yok.
- [ ] **Step 3:** FAIL gör.
- [ ] **Step 4:** `tema.css` yaz; `tema.js` tema listesini `document.documentElement.dataset.temalar` (taban.html'in yazacağı JSON) ya da kendi sabitinden alır — tek kaynak `menu.TEMALAR`: `taban.html` inline FOUC betiği ve `tema.js` listeyi `{{ agac.temalar|map(attribute=0)|list|tojson }}` ile alır (Task 4 bağlar; bu task `tema.js`'i `window.FARABI_TEMALAR || [...]` okuyacak şekilde yazar). Tema döngü düğmesi 9 temayı sırayla gezer.
- [ ] **Step 5:** Testler PASS.
- [ ] **Step 6: Commit** `"dashboard: 9 tema ve temaya özel yazı tipi (tema.css)"`

### Task 4: Yeni kabuk (üst alan çubuğu + sol sayfa menüsü)

**Files:**
- Modify: `tahtayoklama/dashboard/templates/taban.html` (tamamı)
- Create: `tahtayoklama/dashboard/static/bilesen.css` (kabuk + ortak bileşenler; Task 5 genişletir)
- Modify: `tahtayoklama/dashboard/static/menu.js`; Delete: `tahtayoklama/dashboard/static/kenar.js` (davranışı `menu.js`'e katılır)
- Test: `tahtayoklama/dashboard/test_menu.py` (`test_taban_*` açılır, yenileri eklenir)

**Interfaces:**
- Consumes: Task 2 `menu_agaci` anahtarları; Task 3 `tema.css`, `TEMALAR`.
- Produces: `taban.html` blokları AYNI adlarla: `baslik_etiketi`, `baslik`, `ust_sag`, `icerik`, `script` (sayfalar değişmeden render olur). Kabuk sınıfları: `.ust-cubuk`, `.alan-sekme` (`aria-current="true"` aktifte), `.sol-menu`, `.sol-oge` (`aria-current="page"`), `.icerik`, `.sayfa-basligi`. Yükleme sırası: `tema.css`, `pano.css` (geçici), `bilesen.css`.

- [ ] **Step 1: Failing tests** (`taban.html`'i DB'siz render eden mevcut `test_taban_kenar_menu_render` desenini kullan):
  - `test_ust_cubukta_alti_alan`: 6 `.alan-sekme` bağlantısı, her biri alanın ilk sayfasının href'i; `/admin/rapor`'da Yoklama sekmesi `aria-current="true"`.
  - `test_sol_menude_yalniz_aktif_alan`: `/servisler` render'ında sol menüde "Servis yönetimi" var, "Personel" yok; aktif öğede `aria-current="page"`.
  - `test_acil_ve_atos_her_sayfada`: `href="/acil"` ve Atos bağlantısı var; konum izi "Sistem › Servis yönetimi".
  - `test_js_siz_gezinme` (Review Focus 4): alan sekmeleri ve sol menü `<a href>`; menü `button` gerektirmez.
  - `test_tema_listesi_sayfada`: inline betikte 9 tema anahtarı JSON olarak var.
  - `test_menude_olmayan_yolda_render`: `/kazanim` için render istisnasız, sol menü boş.
- [ ] **Step 2:** FAIL gör.
- [ ] **Step 3:** `taban.html`'i yeniden yaz: üst çubukta marka, alan sekmeleri, sağda Acil durum (kırmızı), Atos, gün/saat/ders (`gun_adi_buyuk()` yerine cümle düzeni gün adı — `zil`'de yoksa küçük yardımcı ekle), tema düğmesi, ayar açılır menüsü (`agac.ayarlar` + Temalar alt listesi `role="radiogroup"`). Sol menü `agac.sayfalar`; menüde olmayan yolda sol menü gizli. Mevcut `dialog`'lar, `cikis-form`, `toast` korunur. `menu.js`: ←/→ alan sekmeleri arası, ↑/↓ sol menü, F10 ilk alana odak, `?` kısayol penceresi, harf kısayolları (`data-kisayol`, metin alanında devre dışı), ≤720 px'te tek çekmece (`#menu-ac`), mini sunucu durumu (bugünkü `kenar.js` işlevi) ayar menüsünde.
- [ ] **Step 4:** Testler PASS; önizlemede `/`, `/servisler`, `/admin/okul-verisi?sekme=personel` açılır.
- [ ] **Step 5: Commit** `"dashboard: yeni kabuk — üst alan çubuğu, sol sayfa menüsü"`

### Task 5: Ortak bileşenler

**Files:**
- Modify: `tahtayoklama/dashboard/static/bilesen.css`
- Modify: `tahtayoklama/dashboard/templates/_ikon_sprite.html` (eksik ikonlar)
- Test: `tahtayoklama/dashboard/test_bilesen.py`

**Interfaces:**
- Produces (sonraki task'ların kullanacağı sınıflar, hepsi token'larla):
  - Düğme: `.dugme` + `.dugme-birincil | -ikincil | -tehlike | -kucuk`, `.dugme-ikon`.
  - Rozet: `.rozet` + `.rozet-yesil | -amber | -kirmizi | -gri | -mavi`.
  - Filtre çipi: `a.cip` (+ `.secili`, içinde `<b>` sayı); çip satırı `.cip-satir` + `.ara-kutu` (anlık arama input'u).
  - Tablo: `.tablo-kutu > table.tablo` (tam genişlik, `table-layout` serbest, hücre `var(--bosluk-2) var(--bosluk-3)`, td `white-space: normal`, satır hover, `tr.pasif` soluk, `th` cümle düzeni).
  - Uyarı şeridi: `.serit` + `.serit-uyari | -kritik | -bilgi`.
  - Sayfa başlığı: `.sayfa-basligi` (h1 + `.baslik-eylem` sağda + `.durum-yazi` küçük gösterge).
  - Liste + panel: `.ayrinti-duzen` (grid: liste `minmax(0,1fr)` + panel `20rem`), `.ayrinti-panel` (başlık, `.form-alan` dikey alanlar, `.eksik` turuncu alan, alt eylem satırı), panel kapalıyken liste tam genişlik.
  - Boş durum `.bos-durum`, form alanı `.form-alan > label + input/select`, hata `.form-hata`.
- [ ] **Step 1: Failing test** `test_bilesen.py::test_bilesen_siniflari_tanimli`: yukarıdaki her seçici `bilesen.css`'te tanımlı; `test_ham_renk_yok`: `bilesen.css`'te `#[0-9a-f]{3,6}` ve `rgb(` yok (yalnız `var(--…)`).
- [ ] **Step 2:** FAIL gör. **Step 3:** CSS'i yaz. **Step 4:** PASS. **Step 5: Commit** `"dashboard: ortak bileşenler (bilesen.css)"`

### Task 6: Ana ekran — yoklama ızgarası

**Files:**
- Modify: `tahtayoklama/dashboard/templates/pano.html` (şablon + sayfa içi JS'deki hücre üretimi `hucreDoldur`)
- Modify: `tahtayoklama/dashboard/static/bilesen.css` (`#pano-tablo` kuralları; `pano.css`'teki pano kuralları buraya taşınır)
- Test: `tahtayoklama/dashboard/test_pano_sablon.py`

**Interfaces:**
- Consumes: Task 5 `.serit`, `.rozet`, `.sayfa-basligi`.
- Değişmeyenler: `/api/durum` sözleşmesi, hücre id'leri (`hucre-<sınıf>-<no>`), `data-*` alanları, "Tahtada aç" akışı, tarih seçici, `#simdi-yenile`, acil şeridi.
- [ ] **Step 1: Failing tests** (şablonu DB'siz render et, `siniflar`/`ders_saatleri` sahte):
  - `test_uyari_seridi_izgaranin_ustunde`: `id="uyari-seridi"` konumu `id="pano-tablo"`'dan önce.
  - `test_uzun_isim_listesi_hucrede_metin` (Review Focus 1): sayfa içi JS'de devamsız isimleri `span.isim` (çerçevesiz metin) olarak üretilir, `pill-yok` kalmaz; `bilesen.css`'te `#pano-tablo td` için `white-space: normal` ve `overflow-wrap: anywhere`, `#pano-tablo` için `min-width` yok.
  - `test_kpi_ilk_ekrani_doldurmaz`: büyük `.pano-ozet` kart ızgarası yok; aktif sınıf/eksiksiz/devamsız/bekleyen sayıları `.sayfa-basligi` ya da şerit içinde.
- [ ] **Step 2:** FAIL. **Step 3:** Uygula: başlık "Bugün · <gün tarih> · <ders>", sağda tarih/son güncelleme/Şimdi yenile; altında `.serit-uyari` (sorun listesi + "Tahtada aç" + sağda yüzde ve devamsız toplamı; sorun yoksa `.serit-bilgi` tek satır); ızgara: şu anki ders sütunu vurgulu ve başlıkta "· şimdi", "Tam"/"Alınmadı"/"Tahta ulaşılamaz" `.rozet`, isimler `span.isim`, izinliler `span.isim-izinli`, ders etiketi altta küçük. **Step 4:** PASS + önizlemede 1366'da ızgara ilk ekranda görünür (ekran görüntüsü). **Step 5: Commit** `"dashboard: ana ekran ızgarası yeni tasarımda"`

### Task 7: Okul verisi — liste + ayrıntı paneli

**Files:**
- Modify: `tahtayoklama/dashboard/okul_ana_panel.py` (`sayfa`, `_don`, `_islem`)
- Modify: `tahtayoklama/dashboard/templates/admin_okul_verisi.html`
- Test: `tahtayoklama/dashboard/test_okul_ana_panel_sayfa.py`

**Interfaces:**
- Consumes: Task 5 `.ayrinti-duzen`, `.cip`, `.sayfa-basligi`; mevcut `okul_ana_veri` fonksiyonları (değişmez).
- Produces: query parametreleri — `duzenle=<okul_no>` / `pduzenle=<id>` panelde o kaydı açar; `yeni=1` boş panel açar; hata yönlendirmesi (`_don(sekme, hata=…, **geri)`) seçili kaydı ve `yeni`'yi korur. Sekme sekmeleri kaldırılır (sol menü sayfaları); "Yayınla (yeniden dene)" yalnız `not son_yayin.ok` iken; yayın durumu `.durum-yazi` ("● Yayınlandı 14:07", ayrıntı `title`'da).
- [ ] **Step 1: Failing tests** (`okul_ana_panel.sayfa`'yı `oturum_sarti` yamalı, `veri` sahte nesneyle çağır; canlı PG'ye bağlanma):
  - `test_personel_paneli_secili_kayitla`: `pduzenle=5` → HTML'de `.ayrinti-panel` ve o kişinin TC/e-posta input'ları; listede e-posta/TC sütunu yok.
  - `test_yeni_bos_panel`: `yeni=1` → boş form, başlık "Yeni personel".
  - `test_hata_sonrasi_panel_acik` (Review Focus 5): `personel_kaydet` `ValueError("TC kimlik no 11 haneli olmalı.")` atınca yönlendirme URL'sinde `pduzenle=<id>` ve `hata=` var; o URL'nin render'ında panel açık ve hata `.form-hata`'da.
  - `test_yayinla_yalniz_hata_varken`: `son_yayin.ok=True` → "Yayınla" düğmesi yok; `False` → var.
  - `test_cipler_sayaclarla`: personelde 5 çip (Aktif, Telefonsuz, TC eksik, E-posta eksik, Pasif), öğrencide 3; `durum=` seçili çip `.secili`.
- [ ] **Step 2:** FAIL. **Step 3:** Uygula; öğrenci panelinde veli listesi ve veli ekle formu panelin içinde. Program/Zil/Değişiklik günlüğü sayfaları liste+panel değil, yeni bileşenlerle sade tablo. **Step 4:** PASS + önizlemede 1366'da panel açıkken yatay taşma yok. **Step 5: Commit** `"dashboard: okul verisi liste + ayrıntı paneli"`

### Task 8: Sınıflar ve tahtalar, Kulüpler — aynı desen

**Files:**
- Modify: `tahtayoklama/dashboard/admin.py` (`_siniflar_sayfasi`; seçili sınıf/tahta parametresi), `tahtayoklama/dashboard/templates/admin_siniflar.html`, `tahtayoklama/dashboard/templates/admin_kulupler.html`, ilgili route modülü (`kulupler` sayfasını üreten fonksiyon)
- Modify (yalnız görünüm): `admin_sinif_ogrenciler.html`, `admin_kulup_uyeler.html`
- Test: `tahtayoklama/dashboard/test_siniflar_kulupler_sayfa.py`

**Interfaces:**
- Consumes: Task 7'deki panel deseni ve parametre kuralı (`duzenle=`/`yeni=1`, hata yönlendirmesi seçimi korur).
- [ ] **Step 1: Failing tests**: sınıflar sayfasında satır seçilince (`duzenle=<sinif_id>`) panelde atanmış tahta ve "Yükle" eylemi; kulüplerde panelde kulüp alanları; mevcut POST uçlarının action'ları değişmemiş (`/admin/tahtalar/{id}`, kulüp güncelleme uçları — mevcut şablondan kopyala ve testte aynılığını doğrula).
- [ ] **Step 2:** FAIL. **Step 3:** Uygula. **Step 4:** PASS + mevcut `test_kulup_duzenle.py` vb. PASS. **Step 5: Commit** `"dashboard: sınıflar ve kulüpler liste + ayrıntı paneli"`

### Task 9: Kalan sayfaların taşınması ve eski CSS'in kaldırılması

**Files:**
- Modify (yeni bileşenlere, cümle düzenine, `.sayfa-basligi`'na): `bugun.html`, `admin_rapor.html`, `aylik_ozet.html`, `kulup_yoklama.html`, `veli_mesajlari.html` (+ `static/veli_mesajlari.js` sınıf adları), `uzaktan_yonetim.html`, `sistem_durumu.html`, `servisler.html`, `zamanlanmis_gorevler.html`, `sunucular.html`, `yakinda.html`, `acil.html`, `kazanim_rapor.html`
- Modify (yalnız `tema.css` + renk/font token'ları, düzen aynı): `giris.html`, `acil_ekran.html`, `guvenlik.html`, `guvenlik_giris.html`, `kameralar.html`, `kameralar_ip.html`, `kameralar_kayit.html`
- Delete: `static/pano.css` (son adım); `taban.html`'den bağlantısı kaldırılır
- Test: `tahtayoklama/dashboard/test_eski_css_yok.py`
- [ ] **Step 1: Failing test** `test_eski_siniflar_kullanilmiyor`: `templates/*.html` ve `static/*.js`'te eski sınıflar (`btn-ikincil`, `yeni-form`, `admin-tablo`, `pill`, `pano-ozet-kart`, `kenar-oge`, `kenar-alt-oge`, `etiket-uyari`, `rapor-aciklama`, `tablo-sarici`) yok; `static/pano.css` yok; her şablon `tema.css` yükler.
- [ ] **Step 2:** FAIL. **Step 3:** Sayfaları tek tek taşı (sayfa başına: önizlemede aç, 1366'da taşma yok, işlev aynı). JS'in DOM'da aradığı id/sınıfları değiştirirken ilgili betiği de güncelle (`grep` ile kontrol). **Step 4:** Test + tüm suite PASS. **Step 5: Commit** (sayfa grupları halinde birkaç commit) `"dashboard: <sayfa grubu> yeni tasarıma taşındı"`, son commit `"dashboard: eski pano.css kaldırıldı"`

### Task 10: Uçtan uca doğrulama ve Atakan önizlemesi

**Files:**
- Create: `tahtayoklama/dashboard/scripts/sigma_kontrol.js` (tarayıcı konsolunda/MCP javascript aracıyla çalışan ölçüm betiği: menüdeki her dahili sayfayı iframe'de açar, `documentElement.scrollWidth > clientWidth` ve `overflow-x:auto|scroll` taşan kutuları listeler, her tema için tekrarlar)
- [ ] **Step 1:** Tüm suite PASS: `... -m unittest discover -p 'test_*.py'` → `OK`.
- [ ] **Step 2:** Önizleme (`http://farabi.local:8098`) 1366×768 tarayıcıda giriş yap; `sigma_kontrol.js` 9 tema × tüm sayfalar → taşma listesi boş. Taşma varsa ilgili task'a dönüp düzelt.
- [ ] **Step 3:** Her temada ana ekran ve Personel ekran görüntüsü (kontrast, okunurluk); klavye ile alan → sayfa → panel formu gezinmesi.
- [ ] **Step 4:** `.ruff check` dokunulan .py'ler: F821/F811/F632 sıfır, toplam artmamış.
- [ ] **Step 5:** Atakan'a önizleme adresi + ekran görüntüleri; onay bekle. Geri bildirim düzeltmeleri ilgili task'ın deseninde, ayrı commit'lerle.

### Task 11: Tek seferde geçiş

- [ ] **Step 1:** Atakan'ın açık onayı ("geçir") olmadan başlama. Saat 08:00-17:00 TR dışı mı kontrol et (`TZ=Europe/Istanbul date +%H:%M`).
- [ ] **Step 2:** Geri dönüş noktasını kaydet: `git -C /home/ata/farabi rev-parse HEAD` (DECISIONS.md satırına ve sohbete yaz).
- [ ] **Step 3:** `/home/ata/farabi`'de çalışma ağacı temiz mi (dondurma) kontrol et; `git merge --no-ff panel-yeniden-tasarim` (`atos-anythingllm-gemma` üstünde). Çakışma çıkarsa dur, Atakan'a bildir.
- [ ] **Step 4:** Canlıda testler PASS; `sudo systemctl restart farabi-yoklama-dashboard`; `systemctl is-active` → `active`; `journalctl -u farabi-yoklama-dashboard -n 20` hata yok; tarayıcıda `/` ve 3 sayfa açılıyor.
- [ ] **Step 5:** Önizleme sürecini durdur, `/tmp/farabi-onizleme` sil, worktree'yi kaldır (`superpowers:finishing-a-development-branch`). `DECISIONS.md`'ye tek satır: `2026-10-30 | panel yeniden tasarımı (üst alan menüsü, 9 tema, ayrıntı paneli) | menü karmaşası, sığmayan tablolar, bilgi kalabalığı`. `tahtayoklama/CLAUDE.md` "Menü" ve "Kabuk" paragraflarını yeni yapıya göre güncelle.
- [ ] **Step 6:** Sorun olursa: `git -C /home/ata/farabi reset --hard <Step 2 commit>` YERİNE `git revert -m 1 <merge commit>` + restart (geçmiş korunur).
