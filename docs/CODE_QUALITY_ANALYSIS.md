# CODE_QUALITY_ANALYSIS — Farabi

> Taban: `dbd3fdd` + kirli ağaç. Tüm rakamlar aşağıdaki **tam komutlarla**
> üretildi; ham çıktılar analiz turunda saklandı.
>
> ```
> .venv-tools/bin/ruff check client server benchmark tahtayoklama --statistics
> .venv-tools/bin/radon cc client server benchmark -s -a
> .venv-tools/bin/radon mi client server benchmark -s
> .venv-tools/bin/vulture client server benchmark --min-confidence 80
> ```
>
> **§21 gereği `ruff --fix` ve `ruff format` ÇALIŞTIRILMADI.**

---

## 0. Sıfırıncı bulgu: lint yapılandırması yok

`pyproject.toml`, `ruff.toml`, `.ruff.toml` — **hiçbiri yok**
(`find . -maxdepth 2 -name pyproject.toml` boş).

Sonuç: aşağıdaki **420** rakamı, ruff **0.16.5**'in o günkü varsayılan kural
kümesidir. Ruff yükseltilirse bu sayı kendi başına değişir ve hiçbir
"iyileştirdik" iddiası taşınabilir olmaz. Bu, §14'ün ("baseline yoksa
'iyileşti' deme") doğrudan ihlal koşuludur.

**Q-00 — ÖNERİ:** minimal `pyproject.toml` içine `[tool.ruff]` yaz:
`target-version`, `line-length` ve **bugün fiilen kabul edilen kural kümesi**.
Kod değişikliği sıfır; yalnızca ölçümü sabitler. **P1** (diğer tüm kalite
işlerinin önkoşulu)

---

## 1. Ölçüm özeti

| Metrik | Değer | Komut |
|---|---|---|
| Ruff bulgusu (toplam) | **420** | `ruff check … --statistics` |
| — otomatik düzeltilebilir | 111 (+19 unsafe) | aynı |
| Ortalama cyclomatic complexity | **A (4,15)**, 768 blok | `radon cc -a` |
| Karmaşıklık dağılımı | A 622 / B 82 / C 47 / **D 15 / E 1 / F 1** | `radon cc` |
| MI "A" olmayan dosya | **3** (2× C, 1× B) | `radon mi -s` |
| Vulture (≥%80 güven) | 33 bulgu | `vulture --min-confidence 80` |
| Server testleri | **65 passed** | `server/venv/bin/python -m pytest server/tests/ -q` |
| Client testleri | **144 passed** | `client/venv/bin/python -m pytest tests/ -q` |

**Ortalama karmaşıklık A (4,15) sağlıklı.** Sorun ortalamada değil,
**yoğunlaşmada**: 768 bloğun 17'si D ve üzeri, bunların 6'sı iki dosyada.

---

## 2. Bulgular

### Q-01 — İki god-file, projedeki tek üç "A olmayan" MI

| Dosya | Satır | MI | En kötü blok |
|---|---|---|---|
| `client/ui.py` | 2.680 | **C (0,00)** | `HudCanvas.paintEvent` — **E (37)** |
| `client/main.py` | 2.123 | **C (0,70)** | `FarabiLive._execute_tool` — **F (52)** |
| `server/dosya.py` | 567 | **B (14,67)** | `_process_data` — D (26) |

Dördüncü sıradaki `server/icerik.py` **A (22,35)** — yani uçurum keskin,
sorun gerçekten bu üç dosyada.

- **KANIT:** `radon mi client server benchmark -s` çıktısında A olmayan
  yalnızca bu üç satır var.
- **RİSK:** `_execute_tool` (F/52) ders anında **22 aracın tamamının**
  dağıtım noktası ve kapsamı **%30**. `paintEvent` (E/37) her karede
  çalışıyor — burada atılan bir istisna HUD'u karartır (Kural 2).
- **ÖNERİ:** §16 sırasıyla, önce characterization test, sonra
  `_execute_tool`'u `kayit.py` registry'sine devret (registry **zaten var**).
- **ÖNCELİK:** **P1**

### Q-02 — 183 çıplak `except Exception` — Farabi'nin en yaygın deseni

`BLE001` bulgusu **183 adet**, tek başına tüm bulguların **%44'ü**.
Yoğunlaştığı yerler:

```
22  server/dosya.py        22  client/ui.py         17  client/main.py
11  client/actions/youtube_video.py                  8  server/icerik.py
 5  server/rag.py           5  client/core/zil.py    5  client/actions/pdf_sayfa.py
```

Ayrıca `S110` (`try/except/pass`) **26**, `S112` (`try/except/continue`) **8**.

**Bu bulgu iki gruba ayrılmalı ve karıştırılmamalı:**

**(a) MEŞRU — Kural 2'nin fiilî uygulaması.** Farabi'nin en üst tasarım kısıtı
"asla dersi bozma". `rag.py::_logla`'nın sonundaki çıplak except'in yorumu
bunu açıkça söylüyor: *"Loglama dersi bozmaz — hata olursa yut, cevabı
etkileme."* `rag.py:243`'teki tablo-tarafı sarmalı da aynı gerekçeli.
**Bunlara dokunulmamalı.** Ruff'un burada "hata" demesi, projenin en önemli
kuralını anlamamasıdır.

**(b) SORUNLU — teşhisi imkânsızlaştıran yutmalar.** `S110`
(`except: pass`) 26 adet: hata ne loglanıyor ne yükseltiliyor. `TRY401`
(6 adet, "verbose-log-message") ile birlikte bu, `plan.md`'nin belgelediği
arıza sınıfının **tam sebebi**: `gorsel` zinciri 2026-08-14'ten 2026-09-02'ye
kadar **tamamen ölüydü ve kimse fark etmedi**.

- **ÖNERİ:** Toplu düzeltme **yapma** (Kural: "büyük ölçekli otomatik düzeltme
  yapılmaz"). Yalnızca **26 adet `S110`**'u tek tek gözden geçir: her birine
  `log.debug(...)` ekle ya da bilinçliyse `# noqa: S110` + gerekçe. Davranış
  değişmez, görünürlük kazanılır.
- **ÖNCELİK:** **P2** (ama `saglayicilar.py` ve `proxy.py`'dekiler **P1** —
  sağlayıcı çürümesini gizleyen tam olarak bunlar)

### Q-03 — 29 adet `DTZ` (naive datetime) — DOKUNMA BÖLGESİ

```
6  tahtayoklama/yoklama.py     3  client/core/transcript.py
3  client/core/ders_motoru.py  2  client/core/zil.py    2  client/core/program.py
```

CLAUDE.md açıkça: *"DTZ / timezone: Farabi'nin İstanbul/Türkiye saat mantığı
kontrol edilmeden değiştirilmez."* Ve dosya listesi bunun **neden** böyle
olduğunu gösteriyor: `zil.py` (zil senkronizasyonu), `program.py` (ders
programı), `ders_motoru.py` (ders akışı), `yoklama.py` (yoklama) — hepsi
CLAUDE.md'nin "özellikle korunacak davranışlar" listesinde.

- **ÖNERİ:** **Bu turda ve sonraki turda dokunma.** Ayrı, tek başına bir iş
  olarak ele alınmalı ve gerçek zil saatleriyle doğrulanmalı.
- **ÖNCELİK:** **P3** (kasıtlı olarak geriye atıldı — düşük değer, yüksek risk)

### Q-04 — Gerçek Python hataları: 11 bulgu, **1 tanesi çalışma-zamanı hatası**

`ruff check --select F821,F841,F402,F401,B017,B018`:

| Dosya:satır | Kural | Değerlendirme |
|---|---|---|
| **`tahtayoklama/pdf_disari_aktar.py:155`** | **F821 Undefined name `_sube_harfi`** | ⚠️ **GERÇEK HATA** — bu satıra ulaşıldığında `NameError`. Yoklama PDF dışa aktarımı. |
| `client/ui.py:1678` | F402 `anahtar` import'u döngü değişkeniyle gölgeleniyor | ⚠️ Gerçek gölgeleme; şu an zararsız görünüyor ama kırılgan |
| `tahtayoklama/dashboard/scripts/ilk_yukleme.py:69` | F841 `cur` atanıp kullanılmıyor | muhtemel kopyala-yapıştır artığı |
| `client/ui.py:5`, `client/config/__init__.py:2`, +3 test dosyası | F401 kullanılmayan import | zararsız |
| `server/tests/test_auth.py:186` | B018 işe yaramaz ifade | testte, zararsız |
| `server/tests/test_ders_hafizasi.py:121` | B017 `pytest.raises(Exception)` | test **çok gevşek** — herhangi bir hata geçer |

- **F821, `tahtayoklama/` kapsamında.** CLAUDE.md bunu ayrı bir proje sayıyor
  ama **ruff komutuna dahil ediyor** ve yoklama "korunacak davranışlar"
  listesinde. Bu turda **kod değiştirilmedi** (§21), ama bu bulgu
  `REFACTORING_PLAN.md`'de **P0-adayı** olarak listelendi.
- **ÖNCELİK:** F821 → **P0/P1** (ulaşılabilirliği doğrulanmalı), gerisi **P3**

### Q-05 — Ölü kod: `client/memory/` gerçekten ölü

`vulture` + coverage + import grafiği üçü birden aynı sonucu veriyor:

| Dosya | Satır | Coverage | Importer |
|---|---|---|---|
| `client/memory/memory_manager.py` | 143 | **%0** | **yok** |
| `client/memory/config_manager.py` | 37 | **%0** | **yok** |

`grep -rn "memory_manager\|config_manager" client/ --include=*.py \| grep -v
"^client/memory/"` → **boş çıktı**.

`client/tools/` de %0 coverage'ta (~740 satır) ama **ölü değil** — CLAUDE.md'ye
göre server'ın client kopyasında çalışıyor. Karıştırılmamalı.

Vulture'ın diğer 33 bulgusunun çoğu **yanlış pozitif**: `frames`/`time_info`
(sounddevice callback imzası), `exc_type`/`tb` (`__exit__` protokolü),
`izole_oturum`/`program_dosyasi` (pytest fixture'ları), `msgs` (test
yardımcıları). Bunlar dokunulmamalı.

- **ÖNERİ:** `client/memory/` sil (`long_term.json` dahil, ama önce içeriğine
  bak — §20 "önce hedefe bak"). **P2**

### Q-06 — 35 adet `RUF100` (kullanılmayan `noqa`)

Test dosyalarında yoğunlaşmış (test_auth 4, test_board_auth 2, …). Bunlar
geçmişte gerçek olan ama artık geçerli olmayan susturmalar — yani lint
susturmaları **çürümüş**. Zararsız ama Q-00'ın (yapılandırma yok) doğrudan
belirtisi.

- **ÖNCELİK:** **P3**, Q-00 ile birlikte tek seferde temizlenir.

### Q-07 — Tip ipucu / statik tip denetimi tamamen yok

`mypy` ve `pyright` **hiçbir venv'de kurulu değil** (`ls */venv/bin` ile
doğrulandı). Kod kısmen tip ipuçlu (`rag.py`, `auth.py` iyi durumda;
`ui.py`, `main.py` büyük ölçüde ipucusuz) ama **hiç denetlenmiyor**.

- **RİSK:** Q-04'teki F821 tam olarak bir tip denetleyicinin ilk saniyede
  yakalayacağı sınıftan.
- **ÖNERİ:** Kural 8 gereği **önce onay** — `mypy`/`pyright` yeni bir araç.
  Öneri: `.venv-tools`'a kur (üretim venv'lerine **değil**), yalnızca
  `server/` üzerinde ve `--ignore-missing-imports` ile başla.
- **ÖNCELİK:** **P2, ONAY GEREKTİRİR**

---

## 3. Puan

**Kod kalitesi: 6 / 10.**

Artı (ölçülmüş): ortalama karmaşıklık **A (4,15)**; 768 bloğun 622'si A;
90 dosyanın 87'si MI A; bandit'te **0 High**; testlerin tamamı geçiyor
(65 + 144); kod yorumları olağanüstü — `rag.py` kararların gerekçesini ve
**ölçüm rakamlarını** taşıyor, bu çoğu projede bulunmaz.

Eksi (ölçülmüş): iki god-file MI 0,00/0,70 ve tek F(52) bloğu (Q-01);
lint yapılandırması yok, dolayısıyla 420 rakamı taşınabilir değil (Q-00);
26 sessiz `except: pass` sağlayıcı çürümesini gizledi (Q-02b); 1 gerçek
`F821` (Q-04); statik tip denetimi hiç yok (Q-07).
