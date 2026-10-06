# CLAUDE.md

**Hazırlayan :** Atakan ÜNVER

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Scope:** the board client (`client/`) only. The repo root `CLAUDE.md` is
the source of truth for architecture, server, deployment and rules; when the
two disagree, the root wins. Dated incident stories and "why it became this
way" narratives that used to live here are in the root `DECISIONS.md` (see
its "Arşiv: client/CLAUDE.md'den taşınan…" section) — this file keeps only
the current state and the rules that came out of them.

## What this is

**Farabi** — a Turkish-language AI teaching assistant for classroom smart
boards, named after Fârâbî (*Muallim-i Sânî*, "The Second Teacher").

A **thin** PyQt6 client on Pardus/Vestel boards (Intel i3-2330M). Voice is a
Gemini Live session held **on the board** — permanently the only voice path.
(A local Pipecat voice node was tried 2026-09-25 on branch
`yerel-ses-pipecat`; it was **permanently cancelled 2026-09-28** because the
hardware cannot support it. Do not add local STT/TTS to the client — see
root `CLAUDE.md` "Şu An Yapılmayacaklar".) Everything else heavy — book/YKS content, page rendering, RAG,
cloud text/vision providers, file processing, past-lesson recall — is an
HTTP call to the Brain server (`server/`, `farabi.local`). The board has no
book/YKS/content store of its own; only small disposable caches under
`icerik/onbellek/`.

**Three kips (lesson modes):**
- `ogretmenli` (default) — a human teacher is present with ~20 students;
  Farabi carries content and questioning, classroom order stays with the
  teacher, addresses them as *"kıymetli öğretmenim"*.
- `ogretmensiz` — study hall / make-up / unstaffed; Farabi is the only
  teacher, order included.
- `talimat` — no lesson at all; the teacher drives the board by voice with
  one-sentence commands (see "Öğretmen talimat modu").

`_ders_kipi` is read from `config/ders_programi.json` first (per slot), then
`config/api_keys.json`. Per-mode behaviour rules live in `core/prompt.txt`.

**Lesson frame:** subject from the timetable; topic and kazanım **only from
the teacher** (spoken or typed) at lesson start. There is no yearly-plan
pipeline anymore — never reintroduce "derive today's topic from the plan",
never ask the class *"nerede kalmıştık"*.

## Project layout

```
main.py            FarabiLive: Live session, tool dispatch, audio loops, lesson
                   opening, mic diagnostics
ui.py              PyQt6 HUD (FarabiUI = the surface actions write to)
farabi_start.sh    venv + launch wrapper
update_farabi.sh   git fetch + update helper for a client checkout
requirements.txt / requirements.lock.txt   (installer uses the lock file)

actions/           one public function per module; registry = kayit.py
core/
  prompt.txt       teaching persona (v2.0) — USER-OWNED
  vision_prompt.txt, prompteski.txt   user-owned, not read by code — don't delete
  ders_motoru.py   lesson engine (state machine), run with enjekte=True
  olaylar.py       in-process asyncio event bus
  program.py       timetable: class × day × period → subject (+ kip)
  zil.py           bell schedule + lesson-period state
  tahta.py         board identity: derslik, grade, sunucu_url, mikrofon,
                   auth headers (tahta_anahtari)
  anahtar.py       Gemini key pool + quota detection
  saglayicilar.py  thin HTTP proxy to server's provider pool (NOT a pool)
  modeller.py      CANLI_MODEL — the Live model name, one place
  transcript.py    lesson record (text only), one file per session
  logger.py        rotating diagnostic log
  version.py       client semver (checked against server GET /api/version)
tools/             offline content-prep scripts — they run on the SERVER
                   against /mnt/farabi-data/farabi/, not on a board. Only
                   dogrula.py and mikrofon_test.py matter board-side.
tests/             pytest, no network, no model
config/            real JSON gitignored; *.example.json templates committed
memory/            UNUSED legacy package — do not re-wire (a shared board
                   must not hold a single-student profile)
planlar/           MEB yearly-plan .xlsx, archive only, no code reads it
logs/              ders/*.txt lesson records, farabi.log (gitignored)
```

On boards, `~/farabi` is a sparse checkout of `client/` only, updated by
cron `farabiguncelle.sh` (`git fetch` + `git reset --hard origin/master`,
20:00). **Exception: 9-A** is a full clone at `~/farabi/repo` (client at
`~/farabi/repo/client`). Deployment details: root `CLAUDE.md`.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python main.py

venv/bin/python -m pytest tests/ -q                               # all (pytest is dev-only, not in requirements.txt)
venv/bin/python -m pytest tests/test_mufredat.py -q               # one file
venv/bin/python -m pytest tests/test_mufredat.py::TestDersEslesir -q
venv/bin/python -m pytest tests/ -q -k "eslesme"                  # by name
venv/bin/python -c "import main"                                  # clean import set
python tools/dogrula.py                                           # content gate (exit 1 = RED)
python tools/mikrofon_test.py --karsilastir                       # per-board mic, ratio <3x = not lesson-ready
```

Lint from the repo root: `.venv-tools/bin/ruff check client` (read the diff
against the baseline, see root `CLAUDE.md`).

`requirements.txt` is derived from the real import set — re-verify with a
clean venv + `python -c "import main"`, don't trim by eye. The lock file must
be generated on the boards' Python (3.11), not the server's.

`tests/conftest.py` points `FARABI_LOG_DIR` / `FARABI_DERS_LOG_DIR` at temp
dirs so tests never write into real lesson records — keep new logging behind
those variables.

Offscreen UI check: `QT_QPA_PLATFORM=offscreen python -c "..."` → build
`MainWindow`, `w.grab().save(...)`. (`grep -i` misses letter-dotted strings
like `F.A.R.A.B.İ`.)

## Configuration

### `config/api_keys.json` (hand-edited, gitignored)

No first-launch wizard, and **nothing in the UI may write this file** (a
removed `SetupOverlay` once rewrote it from scratch and destroyed hand-edited
fields). `MainWindow._check_config()` only reads; if no key is usable it logs
to DERS KAYDI and blocks until fixed by hand. Shared fields (Gemini key,
`mikrofon`, `sunucu_url`) are distributed with `server/config_dagit.sh`.

| Key | Missing means |
|---|---|
| `gemini_api_keys` (list) / `gemini_api_key` (legacy) | client cannot start the Live session |
| `sunucu_url` | falls back to `http://127.0.0.1:8000` — dev only |
| `tahta_anahtari` | every server call gets 401 (auth is mandatory) |
| `derslik` | classroom unknown → grade unknown, `DERSLİK TANIMSIZ` in red. Not copyable between boards |
| `ders_kipi` | `ogretmenli` |
| `os_system` | — |

`camera_index` is dead data (no camera anywhere) — ignore.

### Gemini key pool (`core/anahtar.py`)

On a quota error the session moves to the next key **immediately** and
resets the backoff. Invariants, each a past bug:
- the client is built **inside** the reconnect loop (else a rotated key never
  reaches the SDK);
- rotation resets `fail_streak` (the 3→60 s ladder is tuned for one key);
- `kota_hatasi_mi()` matches narrowly (spending cap, `RESOURCE_EXHAUSTED`,
  429, quota, rate limit) — rotating on any exception turns a bad model name
  into "tried all keys";
- `main.py` reads keys only via `anahtar.simdiki()`; `gorsel_uret` shares the
  same pool.

**Rotation only helps across separate Google Cloud projects** — a spending
cap is per project. (The 2026-09-22 billing block was resolved 2026-09-25
with a new key; all 8 boards share one working key. If Farabi goes silent,
suspect `thinking_config`/config fields before billing — DECISIONS.md
2026-09-27.)

> 2026-10-06: mikrofonsuz mod kullanıcı kararıyla koddan kaldırıldı; Farabi her zaman mikrofonlu çalışır (tahta mikrofonları bozuksa öğretmen MİKROFON düğmesiyle sessize alır)

## Audio — settled facts, do not re-litigate

- **Board mics are a hardware limit, not a code bug.** Speech RMS ~200–450
  vs healthy 1500–8000; raising gain raises the floor equally. Each board
  needs an external mic. Verify with `mikrofon_test.py --karsilastir` (also
  the HUD `MİKROFONU KALİBRE ET` button). Judge levels relative to the
  measured floor, never by absolute RMS.
- On the dev machine `acp` is the correct capture device (the ALC3254
  analog input `hw_Generic_1` captured less at equal gain).
- PulseAudio `default` is mandatory — hardware rejects 16 kHz; don't pin
  `hw:*`.
- **Do not re-add VAD / `realtime_input_config` /
  `AutomaticActivityDetection`** — it made Farabi completely deaf. Audio
  config is exactly `output_audio_transcription={}`,
  `input_audio_transcription={}`. `language_codes`/`language_hints` are
  rejected by the Live endpoint (session never opens) even though the SDK
  has the fields. Classroom noise is handled by the prompt's "KALABALIK VE
  GÜRÜLTÜ" rule.
- **Open, not root-caused:** stutter while Farabi speaks on 9-A (echo
  without AEC vs CPU/audio underrun on the i3). Next step is measuring
  `pidstat`/`pw-top` during a real stutter — don't write a cause without
  that. Details: DECISIONS.md 2026-08-30.

## Architecture

### Session lifecycle (`main.py`)

1. `_log_startup_banner()` — model, prompt size, tool count, the **actual
   default** audio devices (`sd.default.device`), frame, kip, classroom.
2. `_build_config()` — time, lesson frame (or `[KONU BEKLENİYOR]`), kip
   block, `[DERSLİK]`, `core/prompt.txt`, language directive. **No
   `thinking_config`** — it silenced the Live model (every turn 0 bytes of
   audio, DECISIONS.md 2026-09-27); `tests/test_oturum_yapilandirmasi.py`
   expects `thinking_config is None` in both `_build_config` and
   `_build_talimat_config`. No student-memory block.
   **Both `system_instruction` and `tools` must actually reach
   `LiveConnectConfig`** — each was silently missing once, and the model then
   either had no persona or *narrated* calling tools that didn't exist.
   `tests/test_oturum_yapilandirmasi.py` asserts both. If tool use goes quiet,
   check this before touching prompt wording.
3. Connects to `CANLI_MODEL` (`core/modeller.py`).
4. Audio loops + 15 s mic diagnostic. The session starts only on a
   double-click of **DERSİ BAŞLAT** (idle sessions cost money); idle timeout
   `BOSTA_KAPATMA_DK` (15).
5. `_send_session_opening()` — hour-aware greeting, day, time, period,
   subject. Missing topic/kazanım → ask the **teacher**, don't start
   attendance or teaching. The opening says "sadece bu açılış turunda araç
   çağırma" — keep any opening rule scoped to the turn. Typed `konu:` /
   `kazanım:` / `ders:` lines update `_current_lesson`.
6. On reconnect `_oturum_devam_notu()` (`[OTURUM DEVAM] … SELAMLAMA YAPMA`)
   is sent instead of the opening; stale `mudahale` is cleared.
7. Lesson end (`shutdown_farabi` → `_dersi_bitir`) does **not** exit the
   process: `_DersBitti` parks the loop until the next DERSİ BAŞLAT; the
   transcript is POSTed to `/api/egitim/ders_kaydi_yedek` (6 s wrap, silent
   on failure).

Reconnect backoff: 3, 6, 12, 24, 48, max 60 s; identical errors log the
traceback once; 3 failures log likely causes on screen; every 10th is
CRITICAL.

Instruction markers (`[DERS_ACILISI]`, `[DERS DURUMU]`, `[ÖĞRETMEN KOMUTU]`,
`[OTURUM DEVAM]`) are stripped from the transcript by `_ETIKET_RE`; the clock
is handed over as `%H:%M` (never 12-hour).

### Lesson language (`ui.ders_dili`)

🇬🇧/🇩🇪 buttons next to DERSİ BAŞLAT run the lesson in English/German.
Chosen **before** DERSİ BAŞLAT and then locked — a Live connection's
`system_instruction` can't change mid-connection. `core/prompt.txt` stays
Turkish, single source; a `[DİL KURALI]` directive appended last tells the
model to speak the target language. Any hard-coded Turkish in the opening
must branch on `ders_dili` (`_acilis_selam_gun`); `core/zil.py` stays
Turkish because it also feeds the UI. Tests: `TestDersDili`,
`TestAcilisSelamGun`.

### Tool dispatch

Declarations come only from `actions/kayit.py` (`TOOL_DECLARATIONS =
kayit.bildirimler(kip)`). Adding a tool = `actions/<name>.py` + an
`Arac(...)` entry + an `elif` in `_execute_tool`; `tests/test_arac_kaydi.py`
fails if they drift. Tool descriptions (`aciklama`) go to the model verbatim
— shortening them is a known way to make the model stop calling a tool.

| Field | Runtime effect |
|---|---|
| `zaman_asimi` | `asyncio.wait_for` in `_isci`; on timeout the model is told the resource didn't arrive (the thread itself runs on) |
| `calisma` | `isci` (thread, awaited with timeout) · `satirici` (inline: `shutdown_farabi`, `talimat_modundan_cik`) · `arkaplan` (thread, **not** awaited — `gorsel_uret`; the tool reports back itself via thread-safe `speak`/`show_image` and enforces its own timeout) |
| `kip` | which tools are offered per kip; `talimat` is exclusive — normal lesson tools never appear there |

`izin`/`maliyet` are metadata only, nothing enforces them. Tool calls run
off the receive loop (`_araclari_calistir`), log timing (`ARAÇ ◀ …`), and warn
over 10 s. Call shape: `fn(parameters=args, player=ui, speak=self.speak)`.

**Server-backed tools fail silent.** Every non-`ok` path returns a
restrictive "stay inside the known kazanım, invent nothing" text
(`_SINIRLI_DEVAM`), never raises into the session. That text is binding,
not permission to improvise.

### Capability boundary — do not cross it

For `ogretmenli`/`ogretmensiz` tools: no app launching, terminal execution,
OS settings, browser automation, messaging or process management.
`file_processor` handles documents/images only (code support was removed —
it once ran uploaded `.py` files). `reminder` and `save_memory` were removed
and stay removed. The boundary is about `actions/`; `ui.py` shells out only
for mic calibration.

Known, **deliberate or open** exceptions:
- **Talimat kip tools** (`web_ac`, `uygulama_ac`, `dosya_ac`,
  `pencere_kapat`) — user decision, see below. Don't extend that trust to
  lesson kips without asking.
- **`geogebra`** — opens a locked `chrome --app` window on a localhost page,
  all kips (user-approved exception, 2026-09-25).
- **`yoklama_al`** — `subprocess.Popen`s `tahtayoklama/yoklama.py` (re-added
  2026-09-02 as a registered tool). ⚠️ It looks for
  `<client>/../tahtayoklama/yoklama.py`, which exists only on 9-A's full
  clone; on sparse-checkout boards tahtayoklama lives at `~/tahtayoklama`,
  so the tool returns "bulunamadı" there.
- **Open holes, not settled behaviour:** `youtube_video` `play` →
  `xdg-open` (uncontrolled browser), and `summarize` with `save: true`
  writes to `~/Desktop` and opens it. `eba` `video` has the same `xdg-open`
  pattern (EBA is a JS SPA, no scraping possible).

### Öğretmen talimat modu (`KIP_TALIMAT`)

No lesson; teacher voice commands only. Selected with `🎓 ÖĞRENCİ MODU` /
`👨‍🏫 ÖĞRETMEN MODU` under DERSİ BAŞLAT (both set `ui.talimat_modu`).
**Defaults to Öğretmen** at launch; read at
connect, locked after DERSİ BAŞLAT.

- `_build_talimat_config()` replaces prompt + frame + kip + language with
  `_TALIMAT_PERSONASI` only; `_ders_motoru_dongusu()` no-ops; the opening is
  one line.
- Tools: `web_ac` (real browser, no whitelist — only `file:`/`javascript:`/
  `data:` blocked), `uygulama_ac` (hand-written name→command table:
  `pardus-pen`, `drawing`, `nemo`, `gnome-calculator`, `evince`,
  `gnome-screenshot` — deliberately not every installed app, no terminal on
  purpose; add entries by hand), `dosya_ac` (`$HOME` only), `pencere_kapat` (`wmctrl -c` by
  **title substring**, not PID — `xdg-open` hands off to an existing browser
  and exits), `talimat_modundan_cik`, plus `pdf_sayfa`, `kitap_sorusu`,
  `yks_sorulari`, `geogebra`, the two screen tools.
- **Why allowed:** the mic has no speaker authentication; the user chose
  "trust the room" knowingly. Don't narrow back to a whitelist.
- Persona rules that came from the first classroom test: never guess a
  required parameter, ask; textbook content is never a local file
  (`pdf_sayfa`/`kitap_sorusu`, not `dosya_ac`); relay what a tool actually
  returned, never an assumed success.
- `self._ders_kipi` is recomputed on **every** `_build_config()` from
  `_ders_kipi_taban` (never mutated) — test fixtures building a bare
  `FarabiLive.__new__` must set `_ders_kipi_taban` too.
- Exiting: `talimat_modundan_cik` sets `ui.talimat_modu = False` directly
  (plain attribute, synchronous) and separately emits `_talimat_cikis_sig`
  for the button visuals — don't collapse the two (same pattern as
  `muted` / `_mute_sig` / `_set_muted`). `_TalimatCikisi` is
  raised from a `tg.create_task()` watcher (not from inside `_execute_tool`,
  whose try/except swallows it) and `run()` checks
  `_talimat_cikis_istendi` **before** the backoff logic → immediate
  reconnect, never logged as an error.

### Tools (current behaviour)

- **`ders_icerigi`** — POSTs `{ders, konu, sinif, tema, derslik}` to
  `/api/egitim/ders_icerigi`; matching runs in `server/icerik.py`. Call with
  the **teacher's** ders+konu after the frame is known; no args = book
  catalogue. Grade defaults from this board's `derslik`
  (`tahta.sinif_duzeyi()`). It is also where `transcript.log_frame()` is
  called — the one point both typed and spoken frames pass through.
- **`kitap_sorusu`** — a concrete question to the server RAG
  (`/api/egitim/question`); returns a source-checked answer to be read as
  given. `ders` is **required** (without it a grade-only match picked the
  wrong subject's book). The `Kaynak: …, s. …` line dedupes pages and marks
  a page ` (tablo)` when any of its sources has server `sources[].tur ==
  "tablo"` (chunk_tablo); a missing `tur` counts as text (2026-10-01).
  Book list cached in `_KITAP_ONBELLEK`. Timeouts:
  GET 5 s, POST 10 s (worst measured 5.3 s), registry `zaman_asimi=16`.
  Imports `_ders_eslesir` from `ders_icerigi.py` — underscored but shared,
  don't rename.
- **`pdf_sayfa`** — one page number, no topic matching, `ders` required.
  Downloads the PNG (≤30-file LRU cache in `icerik/onbellek/pdf_sayfa/`),
  shows it, then fetches `/api/egitim/pdf_sayfa_metni` and gives the model
  the real page text (otherwise it invents content). Sends `derslik` so the
  server picks the same volume `ders_icerigi` chose.
- **`yks_sorulari`** — one past exam question at a time as a page image
  (server `yks.py`, `derslik`-keyed session); advancing needs an explicit
  `sonraki=true`. No answer key: the model works the solution when asked.
- **`ders_hafizasi`** — recalls a PAST lesson on this board via
  `/api/egitim/ders_hafizasi` against the server's backed-up transcripts;
  the current session's file is excluded.
- **`site_goster`** — browser-free by design: page fetched, stripped, shown
  as text. Domain whitelist with suffix match, re-checked **after
  redirects** (tested rejections: `tr.wikipedia.org.evil.com`,
  `file:///etc/passwd`); `eba.gov.tr` covers `ogmmateryal.`/`mebi.`. HTTP headers must
  be latin-1. Text/tables only.
- **`eba`** — `video` opens via `xdg-open`; `pdf` downloads (eba.gov.tr
  only) and extracts text **locally** (pdfplumber → PyPDF2), no file written.
- **`geogebra`** — live GeoGebra: a stdlib HTTP bridge on 127.0.0.1 serves the
  offline bundle to a `chrome --app` page that long-polls `/komut` and
  reports per-command results to `/sonuc` (rejected commands go back to the
  model). Bundle (~120 MB) not in git: pre-copied to
  `icerik/geogebra/GeoGebra` (`server/geogebra_dagit.sh`), server fallback at
  `/geogebra/`. Stalled loader → one Chrome restart; every reopen bumps
  `surum`; delivery is acknowledged and deduped by id. CAS commands only in
  the classic app. Details: DECISIONS.md 2026-09-25.
- **`gorsel_uret`** — generates a new image with Gemini Image (same key
  pool), **client-side only**, `arkaplan` mode; the model gets an immediate
  "hazırlanıyor" and is told later when it's shown. Saved ≤1600×1200 in
  `icerik/onbellek/uretilen_gorseller/` (LRU), by real `mime_type`.
- **`ekran_goruntusu_al` / `ekrandaki_soruyu_oku`** — capture the board's
  OWN screen only (`primaryScreen().grabWindow(0)`, via `_screenshot_sig` on
  the GUI thread), LRU 20 in `icerik/onbellek/ekran_goruntusu/`. No camera
  exists or is planned. Since 2026-09-27 `ekrandaki_soruyu_oku` sends the
  image **directly to Gemini** as a `send_client_content` user turn
  (`FarabiLive.ekrani_modele_gonder`, ≤1024px JPEG q70, tagged `[EKRAN]`);
  `file_processor`'s `ocr` is only the fallback. `send_realtime_input(video=…)`
  was measured to misread digits on a real board — not used. It runs
  `arkaplan` (immediate ack, result in a later turn). Before grabbing, Farabi
  minimises itself if it is the front window (`ui.py::
  _ekran_goruntusu_yakala`/`_ekran_goruntusu_cek`, prior state restored) and
  skips capture if the active window title (`xprop`) matches a personal-data
  filter (yoklama/e-Okul/MEBBİS/tahtayoklama; an `xprop` failure doesn't
  block). A typed "ekranı oku" (`main.py::_ekran_okuma_komutu_mu`) triggers
  it directly from `_on_teacher_command` instead of reaching the model.
- **`file_processor`, `web_search`, `youtube_video`** — text/vision work goes
  through `core/saglayicilar.py` → server proxy (no Gemini). `youtube-
  transcript-api` is unpinned and has broken the API once — when touching
  it, call it with a real video ID.

### Persona — `core/prompt.txt`

User-owned; don't rewrite without being asked. **Do not put textbook
content in it** — content belongs behind a tool call.

**The `SINIRLARIN` block is load-bearing:** one mic, **no speaker
identity** (no per-student reports/percentages); remaining time is known
**only from `[DERS DURUMU]`** (the prompt's clock is built once per connect);
**no private channel** (teacher evaluation is subject-level and nameless).
If diarization or a ticking clock ever lands, rewrite that block — don't
delete it. Exam mode has no session state: Farabi announces entry and exit
aloud so the transcript is the anchor.

### Lesson engine (`core/ders_motoru.py`, `enjekte=True`)

Code owns the flow (`BEKLIYOR → YOKLAMA → … → OZET → ODEV → BITTI`), the
remaining minutes (`zil.ders_durumu()['kalan_dk']`) and a closed set of
suggestions (`ADIM_OZET`, `FARKLI_ANLATIM`, `KONTROL_SORUSU`, `DURAKLAT`). Injection rules, each from a real failure: send
`turn_complete=True`; nothing in the first `ENJEKSIYON_GECIKMESI_SN` (75 s)
and never while `_is_speaking`; `[DERS DURUMU]` only on change (step or
20/10/5/2-minute band via `_sure_bandi()`), never periodic. **The teacher
always wins:** `gec()` forces a step; `duraklat()` is a latched pause cleared only by `devam`;
typed commands use the time-limited `mudahale()` (`MUDAHALE_SURESI_DK` = 5).

### Teacher panel (`ui.py`)

Mid-lesson intervention buttons are exactly **DURDUR**, **DEVAM ET** and
(2026-09-27) **⏹ DERSİ BİTİR** — by decision; everything else is typed.
DERSİ BİTİR exists because mode/mic choices lock at DERSİ BAŞLAT: it is
double-tap only, enabled only while a session is open, and goes through
`ui.on_ders_bitir` → `FarabiLive._on_ders_bitir` → the normal
`_dersi_bitir()` teardown (re-entry-guarded by `_ders_bitiriliyor`; a tap
during a reconnect is honoured before the next connect). DERSİ BAŞLAT,
language, mode and mic-mode buttons are pre-lesson setup, not
interventions. **Everything typed into
the input box is a teacher instruction**, sent as `[ÖĞRETMEN KOMUTU] …` via
`on_teacher_command` → `_on_teacher_command`, which also drives the engine,
parses `konu:`/`kazanım:`/`ders:`, and writes an `ÖĞRETMEN` line to the
transcript. The marker is load-bearing: the prompt's `ÖĞRETMEN KOMUTLARI`
block lets marked instructions override pedagogical defaults ("cevabı
göster", "sadece ipucu"); spoken words never get it. **No auth on the
board** — anyone at the touchscreen can type; none is planned.

### Event bus (`core/olaylar.py`)

In-process asyncio fan-out, fixed event names (`ARAC_BASLADI`,
`ARAC_ZAMAN_ASIMI`, `DURUM_DEGISTI`, `OGRETMEN_MUDAHALE`, …); `abone()` rejects unknown
names (a typo'd subscription is the hardest failure to find); subscriber
exceptions are swallowed and logged.

### Timetable and bells

- `core/program.py` + `config/ders_programi.json`: `sınıf → gün → ders saati
  → ders` (+ optional `kip`). `program.simdiki_ders()` →
  `_programdan_cerceve()` gives subject + period only. Empty slot → ask the
  teacher; a board without a timetable must still teach.
- `core/zil.py` + `config/zil.json`: 08:20 start, 40-min lessons, 10-min
  breaks, lunch 12:20–13:00; `ders_durumu()` returns a UI label (`kisa`) and
  a model sentence (`metin`). Lives in `core/` because `ui.py` can't import
  `main.py`. **Keep time phrases suffix-free** ("ilk dersin başlama saati
  08:20") — the model inflects Turkish suffixes correctly, code doesn't.
- Both files are gitignored and school-wide; the server keeps separate
  copies (root `CLAUDE.md`, "üç bağımsız kopya").

### UI (`ui.py`)

Three columns: classroom/date/lesson panel + metrics · animated HUD +
`ContentPanel` · DERS KAYDI log, drop zone, mic calibration, input, mute.
`F4` mute, `F11` fullscreen. `HudCanvas` plays `Farabi.gif`, falling back
to text. Mic calibration button = `_mikrofon_kalibre`. `core.zil`/`core.tahta` are imported in
`try/except` — missing config leaves panels blank, never crashes. **Window
size is computed** (94% of `availableGeometry()`), never fixed. Content
panel has text (`_show_content`) and image (`_show_image`, zoom `None` = fit
width) modes; the pen/eraser drawing layer (`_CizilebilirGorsel`) is
button-only, never a model tool, and not saved.

### Logging

- `logs/ders/<timestamp>_<derslik>.txt` — one file per session (path cached
  for the process, so reconnects don't fragment it). **Text only, never
  audio.** Labels ÖĞRENCİ / FARABİ / ÖĞRETMEN (typed input only) / SİSTEM;
  no student identity. A cut-off turn is flushed as its own line marked
  `(kesildi)`.
- `logs/farabi.log` — diagnostics, rotating 5 × 1 MB.
- **Gemini token usage** (`core/kullanim.py`, 2026-10-02): every Live message
  carrying `usage_metadata` logs a `TOKEN tur=… girdi=… yanit=… toplam=…`
  line to `farabi.log`; `TOKEN BAĞLANTI ÖZETİ` per connection close and
  `TOKEN DERS ÖZETİ` per lesson, the latter also written as one SİSTEM line
  (`Gemini token kullanımı: …`) into the lesson record so it reaches
  `server/yedekler/ders_kaydi/`. Messages are summed as-is (no dedupe) —
  whether Live sends one usage message per turn or several is **unverified**,
  so read `en_buyuk_baglam` for the context trend, not the summed `girdi`.
  All of it is wrapped to never raise into the receive loop.
- Chain-of-thought and serialized tool calls once leaked into the record.
  Since `thinking_config` was removed (2026-09-27) the **only** defence is
  `_konusma_temizle()` (`_THOUGHT_RE` + tool-call pattern), which matches
  **known tool names only** (a generic pattern eats real speech).

### Providers and quota

Among cloud providers Gemini Live is the only realtime option;
Groq/OpenRouter etc. can't replace the voice path, and the local voice node
was permanently cancelled (2026-09-28) — voice stays on Gemini Live. Every non-realtime text/vision task goes through
`core/saglayicilar.py` → `server/saglayicilar.py` (chains, cooldowns, model
IDs live there); `metin_uret`/`gorsel_uret` keep their signatures and raise
`RuntimeError` on total failure, which callers turn into their own
"don't invent" text. Providers retire models without notice — check current
IDs rather than trusting old ones.

The biggest cost lever is not the model but **idle sessions**: gate on
DERSİ BAŞLAT, close on `BOSTA_KAPATMA_DK`. Stretching a day's Gemini quota
means keys from **separate** Cloud projects. No budget dashboard exists —
size pools from `farabi.log` measurements, not guesses.
