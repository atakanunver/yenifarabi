# Ders ızgarası — buzlu cam React paneli Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ders ızgarasını (ana ekran) Lifestats'taki buzlu cam estetiğinde, React + TypeScript + Framer Motion + Tailwind ile yeniden yazmak; önce `/yeni` adresinde, Atakan onaylayınca `/` yerine.

**Architecture:** `tahtayoklama/dashboard/arayuz/` altında Vite projesi; `npm run build` tek JS + tek CSS üretir ve bunları `static/pano-cam.js` / `static/pano-cam.css` olarak yazar (derlenmiş dosyalar git'e girer, sunucuda node gerekmez). FastAPI `/yeni` rotası mevcut `/` ile aynı bağlamı `pano_cam.html` şablonuna verir; şablon `_ikon_sprite.html`'i gömer, bağlamı `window.PANO_VERI` olarak JSON basar, React buna bağlanır. Veri uçları DEĞİŞMEZ (`/api/durum`, `/api/yenile`, `/api/tahta/{id}/baslat`, `/api/acil/durum`).

**Tech Stack:** react 18.3.1, react-dom 18.3.1, framer-motion 11.11.17, tailwindcss 3.4.16, vite 5.4.11, @vitejs/plugin-react 4.3.4, typescript 5.6.3, vitest 2.1.8 (sürümler sabit, `^` yok).

**Spec:** Bu konuşmadaki istek (buzlu cam panel, sprite ikonlar, Framer Motion) + `/home/ata/lifestats/index.html` görsel referansı.

## Global Constraints

- Dış ikon kütüphanesi yok: ikonlar `<svg className="h-5 w-5"><use href="#ik-<ad>" /></svg>`, sprite `templates/_ikon_sprite.html` (gezinme `#ik-ev`, grafik `#ik-grafik`, saat `#ik-saat`, bildirim `#ik-zil`, eksikse sprite'a Lucide çizgisinde yeni `<symbol>` eklenir).
- Çalışma anında CDN yok: her şey `static/` altından yerel sunulur (okul ağı SSL-inceleme yapıyor; Lifestats'te CDN boş ekran verdi).
- Arayüz metni Türkçe, cümle düzeni; brief'teki "On Going"/"Complete" → **"Devam ediyor"** (fıstık yeşili `#C8F25C`) / **"Tamamlandı"** (zümrüt `#10B981`).
- Zemin `bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900`; ana kart `backdrop-blur-xl bg-white/10 border border-white/10`; gezinme ikonları `text-white/60 hover:text-white transition-all`.
- Gezinmenin tek kaynağı `menu.py::menu_agaci` (şablon `agac.alanlar`'ı JSON'a basar; React elle menü yazmaz).
- `prefers-reduced-motion`: Framer Motion `useReducedMotion()` true ise tüm giriş animasyonları kapalı.
- Vite `build.target: 'es2019'`; çıktı adları sabit (`pano-cam.js`, `pano-cam.css`), önbellek kırma mevcut `?v={{ agac.surum }}` ile (`menu.statik_surum` yalnız `static/` kökündeki dosyalara bakar; o yüzden alt dizine değil köke yazılır).
- `app.py` değişikliği restart ister: `sudo systemctl restart farabi-yoklama-dashboard` YALNIZ 17:00–08:00 TR.
- `/` bu planın sonunda DEĞİŞMEZ; geçiş ayrı onaydır (Task 6).

## Review Focus

1. Hafta sonu / ders olmayan gün / henüz hiç yoklama yok: oranların paydası 0 → "—" gösterilir, `NaN%` veya boş halka çökmesi olmaz (Task 2 testi).
2. Oturum polling sırasında düşer (`/api/durum` 401): sayfa `/giris`'e gider, sessiz boş ekran kalmaz (Task 5 testi).
3. Sınıfa 0 veya >1 tahta bağlı (`sinif_tahta`'da yok): "Alınmadı" hücresi tıklanamaz, buton olarak işaretlenmez (Task 2 testi).
4. Geçmiş tarih seçili: "şimdi" sütunu yok, ders listesinde "Devam ediyor" yok, "Şimdi yenile" kapalı (Task 2 testi).
5. "Tam" yalnız `yok_isimleri` VE `izinli_isimleri` boşsa (2026-09-28 hatası); biri doluysa isimler yazılır (Task 2 testi).

---

### Task 1: `/yeni` rotası ve kabuk şablonu

**Files:**
- Modify: `tahtayoklama/dashboard/app.py:442-493` (`ana_sayfa` gövdesini `_pano_baglami` olarak ayır; yeni rota)
- Create: `tahtayoklama/dashboard/templates/pano_cam.html`
- Test: `tahtayoklama/dashboard/test_pano_cam.py`

**Interfaces:**
- Produces: `_pano_baglami(conn, tarih: str | None) -> dict` anahtarları `tarih, bugun, siniflar, sinif_tahta, ders_saatleri, ilk_durum` (bugünkü `ana_sayfa` ile birebir). `GET /yeni?tarih=` → `pano_cam.html`.
- Produces (React'e): `window.PANO_VERI = {tarih, bugun, siniflar:[{id,ad}], sinif_tahta:{"<sinif_id>": tahta_id}, ders_saatleri:[{no,baslangic,bitis}], ilk_durum:{tarih,satirlar,tahta_acik}, menu:[{ad, ikon, href, aktif}], acil:{ad, href}}`.

- [ ] **Step 1: Testleri yaz** (`test_pano_sablon.py`'deki `Request` elle kurma kalıbı; httpx yok)
  - `test_yeni_oturumsuz_giris_yonlendirir`: çerezsiz `/yeni` → 303, `location == "/giris"`.
  - `test_sablon_sprite_ve_veri`: render çıktısında `id="ik-ev"`, `window.PANO_VERI =`, `/static/pano-cam.js?v=`, `/static/pano-cam.css?v=` var; `taban.html` kabuğu (`class="ust-cubuk"`) YOK.
  - `test_veri_json_gecerli`: `PANO_VERI` satırı `json.loads` ile ayrışır; `menu` uzunluğu `len(menu.ALANLAR)`; `sinif_tahta` anahtarları string.
  - `test_ana_sayfa_degismedi`: `/` hâlâ `pano.html` render eder (`TemplateResponse` adı).
- [ ] **Step 2:** `venv/bin/python -m unittest test_pano_cam -v` → FAIL.
- [ ] **Step 3:** `_pano_baglami` çıkar, `ana_sayfa` onu kullansın; `@app.get("/yeni")` aynı oturum kontrolü + `pano_cam.html`. Şablon: `<!doctype html>`, `lang="tr"`, `{% include "_ikon_sprite.html" %}`, `<div id="kok"></div>`, `<script>window.PANO_VERI = {{ veri | tojson }};</script>`, bundle bağlantıları. Bundle henüz yoksa sayfa boş kök gösterir (Task 2 doldurur).
- [ ] **Step 4:** `venv/bin/python -m unittest discover -p 'test_*.py'` → hepsi OK; `ruff check app.py` F821/F811/F632 sıfır.
- [ ] **Step 5:** Commit `dashboard: /yeni rotası ve pano_cam kabuğu`.

### Task 2: Vite projesi ve saf veri türetmeleri (TDD)

**Files:**
- Create: `arayuz/package.json`, `arayuz/vite.config.ts`, `arayuz/tsconfig.json`, `arayuz/tailwind.config.ts`, `arayuz/postcss.config.js`, `arayuz/src/index.css`, `arayuz/src/main.tsx`, `arayuz/src/tipler.ts`, `arayuz/src/turet.ts`
- Test: `arayuz/src/turet.test.ts`
- (Tüm yollar `tahtayoklama/dashboard/` altında.)

**Interfaces:**
- Produces `tipler.ts`: `Durum = 'alindi'|'alinmadi'|'henuz_baslamadi'|'tahta_ulasilamaz'|'ders_yok_o_gun'|'tahta_atanmamis'`; `Satir` (`/api/durum` satırı, `yok_isimleri`/`izinli_isimleri` JSON metin); `PanoVeri` (Task 1'deki şekil).
- Produces `turet.ts`:
  - `hucreDurumu(s: Satir): {tur: 'tam'|'devamsiz'|'alinmadi'|'ulasilamaz'|'atanmamis'|'bos', yok: string[], izinli: string[]}`
  - `yoklamaOrani(satirlar: Satir[]): number | null` — `alindi / (alindi + alinmadi)`, payda 0 → `null`.
  - `dagilim(satirlar): {tam, devamsiz, alinmadi, ulasilamaz}` (halka dilimleri).
  - `aktifDers(saatler, simdi: Date, bugunMu: boolean): {no, baslangic, bitis} | null`.
  - `dersListesi(saatler, satirlar, simdi, bugunMu): {no, durum: 'devam'|'tamam', alinan, beklenen}[]` — yalnız başlamış dersler; geçmiş tarihte hepsi `'tamam'`.
  - `tiklanabilir(s: Satir, sinifTahta, sinifId): boolean` — `alinmadi` VE tahta id var.
  - `haftaGunleri(tarih: string): string[]` — o haftanın Pzt–Cum ISO tarihleri.

- [ ] **Step 1: `turet.test.ts`** — Review Focus 1, 3, 4, 5 burada:
  - `yoklamaOrani([])` → `null`; 3 alindi + 1 alinmadi → `0.75`; yalnız `henuz_baslamadi` → `null`.
  - `hucreDurumu({durum:'alindi', yok_isimleri:'[]', izinli_isimleri:'["Ali"]'})` → `tur:'devamsiz'`, `izinli:['Ali']`; ikisi `'[]'` → `'tam'`; bozuk JSON `'x'` → boş liste.
  - `tiklanabilir` sınıf tahtasızken `false`.
  - `aktifDers(..., bugunMu=false)` → `null`; `dersListesi(..., bugunMu=false)` içinde `'devam'` yok.
  - `haftaGunleri('2026-11-14')` (cumartesi) → `['2026-11-09', …, '2026-11-13']`.
- [ ] **Step 2:** `cd arayuz && npm ci && npx vitest run` → FAIL.
- [ ] **Step 3:** `turet.ts`'i yaz; `vite.config.ts` `build.outDir: '../static'`, `emptyOutDir: false`, `rollupOptions.output` sabit adlar `pano-cam.js` / `pano-cam.css`, `target: 'es2019'`; Tailwind `content: ['./src/**/*.tsx']`, `preflight` yalnız bu sayfaya yüklendiği için açık kalır.
- [ ] **Step 4:** `npx vitest run && npx tsc --noEmit && npm run build` → PASS, `static/pano-cam.js` ve `.css` oluşur.
- [ ] **Step 5:** Commit (`package-lock.json` dahil, `node_modules` hariç).

### Task 3: Kabuk, gezinme, katılım sütunları, hızlı metrikler

**Files:** Create `arayuz/src/App.tsx`, `arayuz/src/bilesenler/{Ikon,Gezinme,KatilimGrafigi,Metrikler}.tsx`

**Interfaces:**
- Consumes: Task 2 `turet.ts`, `PanoVeri`.
- Produces: `<Ikon ad="ev" />`; `App` düzeni (xl 12 sütun: katılım 5, metrikler 3, halka 4; alt sıra ders listesi 5, ızgara 7; md 2, mobil 1 sütun; mobilde gezinme alt şerit).

- [ ] **Step 1:** Gezinme: `PANO_VERI.menu`'den sprite ikonlu bağlantılar, aktif olan `aria-current="page"`, en altta kırmızı acil bağlantısı (`#ik-uyari`). Yüzen dikey şerit `lg:sticky`.
- [ ] **Step 2:** KatilimGrafigi: `haftaGunleri` için `/api/durum?tarih=` paralel çağrı (bugünden sonraki günler çağrılmaz, boş sütun); sütun yüksekliği `yoklamaOrani`, `null` → soluk iskelet; `motion.div` `scaleY 0→1`, `originY:1`, sırayla 0.05 sn gecikme. Seçili gün vurgulu, odak/hover ile değer üstte.
- [ ] **Step 3:** Metrikler (3 kart): "Şu an" (`aktifDers` → "3. ders · 09:50–10:30", yoksa "Teneffüs"/"Ders yok", `#ik-saat`); "Açık tahta" (`tahta_acik` true sayısı / toplam, `#ik-tahta`); "Alınan yoklama" (alindi / beklenen, `#ik-onay`).
- [ ] **Step 4:** `npm run build`; `arayuz/onizleme.html` (yalnız geliştirme, örnek `PANO_VERI` + `fetch` taklidi, build'e girmez) ile headless Chrome 1440 ve 390 px ekran görüntüsü al, gözle denetle.
- [ ] **Step 5:** Commit.

### Task 4: Halka grafik ve ders listesi

**Files:** Create `arayuz/src/bilesenler/{KatilimHalkasi,DersListesi}.tsx`

- [ ] **Step 1:** KatilimHalkasi: `dagilim` dilimleri (Tam zümrüt, Devamsız var fıstık, Alınmadı amber `#F59E0B`, Ulaşılamaz `white/30`), `motion.circle` `pathLength 0→değer` + kapsayıcı `rotate -90→0`; ortada `yoklamaOrani` % veya "—"; yanında renkli kare göstergeli lejant. `role="img"` + `aria-label` ("Genel yoklama oranı %75").
- [ ] **Step 2:** DersListesi: `dersListesi` satırları — "2. ders · BİY-AY" değil, ders no + saat aralığı; hap "Devam ediyor"/"Tamamlandı"; ince ilerleme çubuğu `alinan/beklenen`, `role="progressbar"`.
- [ ] **Step 3:** Önizleme ekran görüntüsü 1440/390 px, boş gün verisiyle de ("—").
- [ ] **Step 4:** Commit.

### Task 5: Ders ızgarası tablosu ve eylemler

**Files:** Create `arayuz/src/bilesenler/{DersIzgarasi,UstSerit}.tsx`, `arayuz/src/api.ts`; Test `arayuz/src/api.test.ts`

**Interfaces:**
- Produces `api.ts`: `durumGetir(tarih): Promise<DurumYaniti>`, `yenile(tarih): Promise<{basarili, detay?}>`, `tahtaBaslat(tahtaId): Promise<{basarili, durum?, detay?}>`, `acilDurum(): Promise<{aktif, turler}>`; 401 alan her çağrı `location.assign('/giris')`.

- [ ] **Step 1: `api.test.ts`** — `fetch` taklidi 401 → `location.assign` `'/giris'` ile çağrıldı (Review Focus 2); 502 `tahtaBaslat` → `{basarili:false}` döner, fırlatmaz.
- [ ] **Step 2:** `npx vitest run` → FAIL; `api.ts` yaz → PASS.
- [ ] **Step 3:** DersIzgarasi: mevcut `pano.html` davranışı birebir — sorunlu satırlar (alinmadi/ulaşılamaz) üstte, tahta noktası, "şimdi" sütunu vurgusu, hücrede ders etiketi `DERS-ÖĞR` (title tam ad), devamsız isimler sarar, tıklanabilir hücre `role="button"` + Enter/Space → `tahtaBaslat` + bildirim. 60 sn polling, `visibilitychange`'de yenile, gizliyken çekme yok.
- [ ] **Step 4:** UstSerit: başlık ("Bugün · Cumartesi 14 Kasım · 3. ders"), tarih seçici (`max=bugun`, değişince `?tarih=`), "Şimdi yenile" (geçmiş tarihte kapalı), son güncelleme saati, acil alarm şeridi (10 sn `acilDurum`).
- [ ] **Step 5:** Önizleme ekran görüntüleri + `npx tsc --noEmit && npx vitest run && npm run build`; dashboard `unittest discover` OK.
- [ ] **Step 6:** Commit.

### Task 6: Kurallar, devreye alma, doğrulama

**Files:** Modify `tahtayoklama/AGENTS.md` (Frontend bölümü: `arayuz/` istisnası — React/TS/Vite, derlenmiş çıktı `static/pano-cam.*` git'te, çalışma anında CDN yok), `DECISIONS.md` (tek satır), `CHANGELOG.md`.

- [ ] **Step 1:** Belgeleri güncelle; commit.
- [ ] **Step 2 (17:00 TR sonrası):** `sudo systemctl restart farabi-yoklama-dashboard`; `systemctl is-active` → `active`; `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/yeni` → `303`; `/` → `303` (değişmedi).
- [ ] **Step 3:** Atakan tarayıcıda `http://farabi.local/yeni` açar, gerçek veriyle görsel kabul.
- [ ] **Step 4 (ayrı onayla):** `/` → `pano_cam.html`; `test_pano_sablon.py::test_kpi_ilk_ekrani_doldurmaz` (2026-11-11 "yalnız yoklama ızgarası" kararı) bu kararla çelişir — Atakan'a sorulur, test güncellenir ya da kaldırılır.
