# CLAUDE.md

**Hazırlayan :** Atakan ÜNVER

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Farabi** — a Turkish-language AI teaching assistant for classroom smart boards.
Named after Fârâbî, the Turkic-Islamic polymath titled *Muallim-i Sânî*
("The Second Teacher", after Aristotle).

**Target:** a standalone Linux smart board client, one board at a time, no
central server. A school-server architecture (`farabi-server`) was explored and
then dropped — do not reintroduce a "phase 2 server" framing into new code or
docs. Every board runs independently: its own config files, its own API keys,
its own local content index.

> ⚠️ **Reconciled 2026-08-09, updated 2026-08-11** with the repo root's
> `CLAUDE.md`/`docs/mimari.md`: the long-term target is a local "Brain"
> server (Ollama, RAG/pgvector) with an ideally-thin client. **Voice is the
> one deliberate, permanent exception (decided 2026-08-11):** local STT/TTS
> was evaluated and cancelled — Gemini Live's realtime turn-taking/barge-in
> is hard to replicate with a separate VAD→STT→LLM→TTS pipeline, and that
> engineering effort was judged not worth it for this project (could be tried
> in a different project, not this one). So: **student voice permanently goes
> to Gemini Live (cloud)** — this is accepted, not temporary. Educational
> *content* (book text, RAG answers) is the part that's local and stays local
> — that privacy goal is met via `server/` (see `docs/mimari.md` §14). *This*
> file's "no central server, standalone client" framing still describes the
> current, working implementation (Gemini Live for voice + five text/vision
> cloud providers for everything else) — the text/vision provider dependency
> (`core/saglayicilar.py`) is a separate, still-open question, not resolved
> by the voice decision. Don't quietly rewrite this file to pretend content
> already flows through `server/`; the client isn't wired to it yet.

**Two lesson modes.** In a normal lesson a human teacher is present with ~20
students and Farabi is the assistant: it carries content and questioning while
classroom order stays with the teacher, and it addresses the teacher as
*"kıymetli öğretmenim"*. In study hall, make-up and unstaffed lessons nobody
else is there and Farabi is the only teacher, responsible for order too. The
mode is injected as its own system-prompt block (`_ders_kipi` in `main.py`),
read from `config/ders_programi.json` first, then `config/api_keys.json`.
**Default is `ogretmenli`.** Per-mode behaviour rules live in `core/prompt.txt`.

**Lesson frame:** subject from `ders_programi.json`; topic and kazanım from the
teacher at the start of the lesson. Do not re-introduce yearly-plan
auto-detection into `_current_lesson` or the opening.

## Project layout

(No line counts here on purpose — they drift every commit and re-adding them just
schedules the next cleanup. Byte sizes are kept only where size is the point: the
persona files and the data directories.)

```
main.py                  FarabiLive: Live session, tool dispatch, audio loops,
                         lesson opening, mic diagnostics
ui.py                    PyQt6 HUD. FarabiUI is the surface actions write to.
                         Also hosts the content-prep buttons (book/YKS
                         conversion, AI symbol cleanup, book summary — see
                         "Content pipeline" below) and the startup check that
                         refreshes `icerik/kitaplar.json` when `kitaplar/`
                         changed
setup.py                 pip install + a pointer to copy the config/*.example
                         files (see README.md). Nothing else — the fork's
                         stale `playwright install` line and the semantic-
                         index rebuild step (that subsystem is gone, see
                         below) were removed
farabi_start.sh          venv + launch wrapper
Farabi.gif               HUD animation (placeholder art; swap freely)
dersgiriscikis.png       school bell-schedule photo — provenance for zil.json

actions/                 one public function per module — the
                         registry declares ten tools (`shutdown_farabi`
                         runs inline, it has no module). No camera/screen
                         capture anywhere (`screen_processor.py` removed
                         2026-08-09 — unused, and violated the no-camera
                         privacy rule; see git history if it's ever needed
                         again)
  kayit.py               TOOL REGISTRY — the single source for declarations,
                         timeouts, permissions, cost class (see below)
  ders_icerigi.py        textbook pages for the teacher's subject + topic.
                         `KITAP_PATH`/`_json_oku`/`_ders_eslesir` are now
                         imported by kitap_sorusu.py AND pdf_sayfa.py too —
                         renaming them breaks both, even though underscored
                         (pdf_sayfa.py's own `render_pdf_sayfa()` has the same
                         fragility in reverse — it's deliberately public and
                         imported by yks_sorulari.py)
  kitap_sorusu.py        answers a concrete, source-checked question via the
                         server's RAG pipeline (`server/rag.py`), added
                         2026-08-11 — NOT a topic walkthrough, that's
                         ders_icerigi's job (see below)
  pdf_sayfa.py            renders one specific PDF page number as an IMAGE
                         (PyMuPDF/fitz — already a dependency, no new one
                         added) with zoom +/- and pan in the content panel,
                         added 2026-08-12. Exposes `render_pdf_sayfa()` as a
                         deliberately public/reusable render helper — imported
                         by yks_sorulari.py too, so the fitz rendering logic
                         lives in one place. See kayit.py's `pdf_sayfa` entry
                         and ui.py's `show_image`/`_olcekle_goruntu`.
  yks_sorulari.py        past YKS exam questions on the topic, keyword-matched
                         against tools/yks_metin.py output. Shows ONE question
                         at a time as an actual PDF page IMAGE (via
                         pdf_sayfa.render_pdf_sayfa — original layout, not
                         reflowed text), module-level `_OTURUM` dict tracks
                         which matched question is current for the process
                         lifetime. Advancing to the next matched question
                         needs an explicit `sonraki=true` call — never
                         automatic, see core/prompt.txt's SESLİ HİTAP/SORU
                         SUNUM PROTOKOLÜ. Question only, no solution; model
                         must work the solution itself (see below)
  file_processor.py      documents and images only (narrowed, see below)
  youtube_video.py       lesson videos
  eba.py                 EBA (MEB portal) lesson videos + question PDFs, added
                         2026-08-09 (see "eba" section below)
  web_search.py          DuckDuckGo (primary, free) + core/saglayicilar.py
                         synthesis — no Gemini (see "Provider notes" below)
  site_goster.py         whitelisted reference sites, no browser

core/
  prompt.txt         26K teaching persona (v2.0) — USER-OWNED
  vision_prompt.txt 1.0K vision persona — USER-OWNED, easy to miss
  ders_motoru.py         LESSON ENGINE — deterministic state machine; the class
                         defaults to observer mode, `main.py` runs it with
                         `enjekte=True` (see below)
  olaylar.py             in-process event bus (asyncio, no broker)
  program.py             timetable: day × period × class → subject (see below)
  zil.py                 bell schedule + lesson-period state (shared, see below)
  tahta.py               which classroom this board stands in (shared, see below)
  modeller.py            CANLI_MODEL only now — Live model name, one place
  anahtar.py             Gemini API key pool + quota detection (Live only)
  saglayicilar.py        SIX-PROVIDER POOL for everything non-realtime (Groq,
                         Mistral, DeepSeek, OpenRouter, NVIDIA NIM) — see
                         "Provider notes and API quota" below
  logger.py              rotating diagnostic log
  transcript.py          lesson record (text only, never audio)

memory/                  UNUSED at runtime (legacy package; `save_memory` removed).
                         Do not re-wire into `_build_config` or the tool registry
                         without an explicit request — a shared classroom board
                         must not hold a single-student profile.

tools/                   not part of a lesson — see the invariant below.
                         Reachable from a UI button (kitap/YKS conversion,
                         AI symbol cleanup, book summary) as well as the
                         command line — see "Content pipeline" below
  kitap_index.py         textbook PDFs          → icerik/kitaplar.json (offline)
  kitap_metin.py         textbook PDFs          → icerik/metin/<kitap>.json
                         (offline, NO API) — the runtime text source; run it on
                         every book (see below)
  dogrula.py             CONTENT VALIDATION GATE for the book index + hand
                         mappings — catches silently-bad indexes (offline,
                         free, no API)
  sembol_temizle.py      AI-ASSISTED symbol cleanup for pages `kitap_metin.py`
                         flagged ambiguous ('#'/'$') — a separate, opt-in,
                         PAID step; see "Content pipeline" below
  kitap_ozet.py          book summary + web-sourced enrichment questions,
                         written to icerik/ozet/<kitap>.json — PAID, opt-in;
                         `ders_icerigi` reads the summary if present
  onbellek_isit.py       pre-lesson page-selection warming for one konu
                         (offline; the topic is always given by hand, never
                         auto-detected — see below)
  mikrofon_test.py       per-board mic verification (setup / field use)
  yks_metin.py           YKS exam PDFs → icerik/yks_metin/<dosya>.txt (offline,
                         NO API, no symbol-repair layer) — the runtime text
                         source for `yks_sorulari` (see below)

tests/                   pytest; pure functions only, no network, no model
  test_mufredat.py       subject matching, display names, text-source helpers
  test_ders_motoru.py    lesson engine states, suggestions, injection
  test_arac_kaydi.py     registry ↔ dispatch, timeouts, permissions
  test_program.py        timetable slots, aliases, mode per slot
  test_oturum_yapilandirmasi.py  built config carries system_instruction + tools,
                         lesson-language directive text (see "Lesson language")
  test_kitap_index_sira.py  fitz header/page-number ordering regression (see
                         "kitap_index.py'nin fitz geçişi" under Content pipeline)
  test_oturum_devam.py   reconnect sends [OTURUM DEVAM], never re-greets
  test_ogretmen_komutu_kaydi.py  typed teacher instructions reach the
                         persistent lesson record, not just the on-screen panel
  test_transcript.py     ÖĞRETMEN label written distinctly from ÖĞRENCİ/FARABİ
  test_alim_dongusu_kesinti.py  `_receive_audio` clears out_buf/in_buf on
                         `interrupted` so a cut-off turn's text can't merge
                         into the next turn's line (see below)
  test_saglayicilar.py   six-provider chain fallback/skip logic (mocked
                         clients, no network — see "Provider notes" below)
  test_sembol_temizle.py  AI symbol-cleanup page counting and failure handling
  test_kitap_sorusu.py   book-matching refuses without `ders` (network-free,
                         monkeypatched cache — see kitap_sorusu section below)

config/
  api_keys.json          gemini_api_key, os_system, ders_kipi, derslik
                         (gitignored — see Config keys below; may still carry
                         a leftover camera_index key, now dead/ignored)
  api_keys.example.json  same shape, committed as template — hand-copy this,
                         there is no setup wizard that writes api_keys.json
  zil.json               bell schedule (gitignored)
  zil.example.json       same values, committed as template
  ders_programi.json     timetable (gitignored)
  ders_programi.example.json   same shape, committed as template

planlar/           2.3M  MEB yearly-plan .xlsx — ARCHIVE ONLY, not read by any
                         code path anymore (see below). Left on disk because
                         it's the teacher's source material, not because
                         anything consumes it; see planlar/BURAYA_NE_KONUR.md
kitaplar/         ~1.0G  textbook PDFs — DROP DIRECTORY (gitignored except the
                         note); see kitaplar/BURAYA_NE_KONUR.md. `kitap_metin.py`
                         and the HUD button both glob `kitaplar/*.pdf` non-
                         recursively — any scratch PDF dropped at the top level
                         (a manual split, an OCR intermediate) gets converted
                         as if it were a textbook. `kitaplar/_manuel_calisma/`
                         is the parking spot for that kind of leftover; a
                         subdirectory is invisible to the top-level glob.
YKS/                     YKS (TYT/AYT) past exam-paper PDFs — DROP DIRECTORY,
                         same shape as kitaplar/, no marker file yet. One
                         consumer, offline: tools/yks_metin.py (plain text,
                         read at runtime by `yks_sorulari`).
icerik/             15M  generated index + caches (GITIGNORED, regenerable)
  metin/<kitap>.json     extracted page text — what `ders_icerigi` actually
                         reads at runtime; produced by tools/kitap_metin.py
  ozet/<kitap>.json      OPTIONAL book summary + web enrichment, produced by
                         tools/kitap_ozet.py; `ders_icerigi` prepends the
                         summary when present, silently skips it otherwise
  onbellek/              page-selection cache (_sayfa_secimi.json)
  eslemeler/*.json       HAND-WRITTEN theme→page maps — the one thing under
                         icerik/ that is NOT generated, and is committed
logs/                    ders/*.txt lesson records, farabi.log (GITIGNORED)
```

Data flows one way for **books**: `kitaplar/` → `tools/` → `icerik/` →
`ders_icerigi` at runtime. Nothing in `actions/` opens PDFs without going
through `icerik/`. `ders_icerigi` prefers `icerik/metin/<kitap>.json` and only
falls back to opening the PDF for a book that has not been through
`kitap_metin.py` — the slow path, not the intended one.

**A lesson is driven only by kitaplar/, never by the yearly plan.** Subject
comes from `config/ders_programi.json` (`program.simdiki_ders()` →
`_programdan_cerceve`); topic and kazanım come from the teacher (typed or
spoken) at lesson start; `ders_icerigi` matches that topic straight against
the book index. The yearly-plan pipeline (`plan_parse.py` → `icerik/plan.json`,
the `dogrula.py` plan/coverage checks, `gunun_adaylari`/`ders_cercevesi_yap`
in `ders_icerigi.py`) was **removed entirely**, not merely unused — there is
no `icerik/plan.json` anymore and no code path reads `planlar/`. Do not
reintroduce a "derive today's topic from the plan" path; topic/kazanım only
ever come from the teacher.

**`tools/` invariant.** `kitap_index.py`, `kitap_metin.py`, `sembol_temizle.py`
and `kitap_ozet.py` are content preparation: run **once, offline** (or from a
UI button — still not during a lesson, see "Content pipeline" below), never
while a class is waiting. `sembol_temizle.py` and `kitap_ozet.py` additionally
cost real API calls — they default to a dry run and require `--onayla`.
`mikrofon_test.py` is not content — it is board verification, run at install
time and whenever a board is suspected deaf. The same two-phase measurement is
also reachable at runtime from a HUD button (`_mikrofon_kalibre` in `ui.py`),
which is deliberate: whoever is standing at the board is the one who needs the
answer.

**No semantic/embedding search.** `sentence-transformers` and `torch` were
removed from `requirements.txt`; page selection is word-overlap only (see
"Page selection" below). This was a deliberate simplification, not a
regression to work around — the kept dependency is much lighter for a board
install, and the word-overlap scorer already had to exist as the fallback.

### Config keys (`config/api_keys.json`)

| Key | Set by | Missing means |
|---|---|---|
| `gemini_api_keys` | hand-edited, list | falls back to the single key |
| `gemini_api_key` | hand-edited (legacy singular) | client cannot start (blocks the LIVE session only — see below) |
| `groq_api_key` | hand-edited | that provider skipped in every `core/saglayicilar.py` chain it appears in |
| `mistral_api_key` | hand-edited | same |
| `deepseek_api_key` | hand-edited | same |
| `openrouter_api_key` | hand-edited | same (this one is also the universal text fallback — see "Provider notes" below) |
| `nvidia_api_key` | hand-edited | same |
| `os_system` | hand-edited | — |
| `ders_kipi` | hand-edited | defaults to `ogretmenli` (`_ders_kipi`, `main.py`) |
| `derslik` | hand-edited, per board | classroom unknown — see below |
| `camera_index` | dead (writer removed 2026-08-09) | ignored — no camera code reads or writes it |

### API key pool (`core/anahtar.py`)

`gemini_api_keys` is a list; on a quota error the session moves to the next key
**without waiting**, resets `fail_streak`, and retries immediately. Template in
`config/api_keys.example.json`.

Three things that make this work, each of which was a way to get it wrong:

- **The client is built inside the reconnect loop.** It used to be constructed
  once above `while True`, where a rotated key would never reach the SDK.
- **Rotation resets the backoff.** The 3→6→12→24→48→60 s ladder and the "3
  failures = log likely causes" diagnostic are tuned for one key; walking a
  ten-key pool through them means minutes of classroom silence and a false
  "check your API key" verdict while nothing is actually wrong.
- **`kota_hatasi_mi()` matches narrowly** — spending cap, `RESOURCE_EXHAUSTED`,
  429, quota, rate limit. Rotating on *any* exception turns a wrong model name or
  a bad key into "tried all ten and gave up", the exact misdiagnosis the reconnect
  section exists to prevent. Verified: the real 1011 string and 429 match;
  `Unknown name language_codes`, connection refused and invalid-key do not.

**Only one Gemini key reader now: `main.py`.** (`screen_processor.py` was the
second reader; it was removed 2026-08-09 — no camera/screen capture anywhere
in this repo anymore, see "Project layout" above.) It goes through
`anahtar.simdiki()` — used to open `api_keys.json` itself, which would leave
it on the dead key after the session rotated. Every other former reader
(`web_search.py`, `file_processor.py`, `youtube_video.py`) was migrated off
Gemini entirely — see "Provider notes and API quota" below,
`core/saglayicilar.py`. `ders_icerigi.py` and `site_goster.py` call **no** AI
API at all (the image-transcription path that once made `ders_icerigi` a key
reader is gone — see "Do not re-add the image path" below — and
`site_goster` only fetches and cleans a page server-side), so they don't need
a key and aren't in this list.

**Rotation only helps across separate Google Cloud projects.** A monthly spending
cap is per project, so ten keys minted in one project share one cap and the pool
fails over ten times into the same 1011.

`camera_index` is now dead data: it was written by the removed
`screen_processor.py` (probed camera indices 0–5, saved via `_save_config_key`).
Nothing reads or writes it anymore — safe to ignore or delete by hand from
`api_keys.json`, not load-bearing for anything.

## ⚠️ Microphone: hardware limit, not a code bug — RESOLVED as a requirement

The "Farabi does not hear me" problem was traced to microphone sensitivity, not
software. Measured on the dev machine (Dell G15, internal DMIC via `acp`):

| Condition | RMS | Healthy range |
|---|---|---|
| Silent room | 8–16 | — |
| Speech at normal distance | 200–450 | **1500–8000** |
| Gain raised to 200% | floor 160, speech 272 | ratio only 1.7x |

The mic is not faulty — it captures speech about 10x too quietly, and raising
gain does not help because the noise floor rises by the same factor, leaving
signal-to-noise unchanged. **Each board needs an external microphone** (USB
conference or ceiling mic). Verify per board with
`python tools/mikrofon_test.py --karsilastir` — a ratio below 3x means that board
is not lesson-ready. The same check is on the HUD (`MİKROFONU KALİBRE ET`), run in a
background thread with the result in the content panel, so it can be done at the
board without a terminal.

Facts already established, do not re-litigate:
- `acp` **is** the correct capture device. The ALC3254 analog input
  (`hw_Generic_1`) was tested at equal gain and unmuted: it captures less.
- Hardware devices reject 16 kHz (48 kHz only), so PulseAudio `default` is
  mandatory — do not try to pin `hw:*` at 16 kHz.
- Nothing in the client can fix this. `realtime_input_config` was tried and made
  Farabi completely deaf (next section).

Two of my own diagnostic mistakes are worth remembering:
1. **Absolute RMS thresholds were wrong.** The noise floor moves ~40x with system
   gain, so a fixed "rms 400 = speech" rule reported a silent room as speech.
   `_listen_audio`'s diagnostic now measures the floor first and bands relative
   to it.
2. **A single startup transient was misread as clipping.** Opening the stream
   produces a pop that hits 32768; judging clipping by the run's max peak made
   `mikrofon_test.py` recommend *lowering* gain when the real problem was too
   little signal. It now skips the first blocks and judges clipping by the
   proportion of samples at the ceiling.
3. **A logarithmic level bar hid the answer.** rms 500 → 29 bars, rms 5000 → 40
   bars, so speech and room noise looked identical and the level appeared "flat".
   Now square-root scaled.

Interpreting levels without knowing *when* the speaker was talking produced two
wrong diagnoses. The two-phase `--karsilastir` mode exists because of that:
it measures silence and speech itself and reports the ratio.

## ⚠️ Do not re-add VAD / audio-detection config

`realtime_input_config` / `AutomaticActivityDetection` was added to tune for a
crowded classroom (start/end sensitivity, prefix padding, silence duration) and
it **made Farabi completely deaf**: sessions opened, it greeted, zero student
transcripts arrived. Evidence: 11 student lines before the change, 0 across four
sessions after. Reverting only `start_of_speech_sensitivity` was not enough; the
whole block had to go.

Audio config is now exactly:

```python
output_audio_transcription={},
input_audio_transcription={},
```

Also rejected server-side (tested): `language_codes` and `language_hints` on
`input_audio_transcription`. The SDK exposes those fields but the Live API returns
`Unknown name "language_codes"` and the session never opens. **A field existing in
the SDK does not mean the endpoint accepts it.** Accepted and kept:
`realtime_input_config` is gone, `thinking_config` stays.

Classroom noise is handled in the model instead — the "KALABALIK VE GÜRÜLTÜ" rule
in `core/prompt.txt` ("Lütfen sessiz olalım ve tek tek konuşalım").

## Running the board client

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

**No first-launch wizard.** `config/api_keys.json` is hand-authored only, same
as `zil.json`/`ders_programi.json` — copy `config/api_keys.example.json` and
fill it in. A `SetupOverlay` first-launch dialog used to exist in `ui.py`; it
was removed because on any missing/incomplete config it rewrote
`config/api_keys.json` **from scratch** with just `{"gemini_api_key",
"os_system"}`, silently destroying a hand-edited `derslik`, `ders_kipi`, or
`gemini_api_keys` pool that didn't happen to also satisfy that exact shape.
`MainWindow._check_config()` now only *reads* (via `core.anahtar.adet()`,
the same pool-aware reader every other module uses) and, if nothing usable is
found, logs an error to the DERS KAYDI panel and leaves `_ready=False` —
`FarabiUI.wait_for_api_key()` blocks the session thread until the operator
fixes the file by hand and restarts. Do not reintroduce anything that writes
`api_keys.json` from the UI.

`requirements.txt` is derived from the actual import set and verified by a
clean-venv install plus `python -c "import main"` — re-verify that way rather
than trimming by eye.

### Verifying a change

There is no linter or formatter configured. What exists:

```bash
venv/bin/python -m pytest tests/ -q        # no network, no model
venv/bin/python -m pytest tests/test_mufredat.py -q         # one file
venv/bin/python -m pytest tests/test_mufredat.py::TestDersEslesir -q       # one class
venv/bin/python -m pytest "tests/test_mufredat.py::TestDersEslesir::test_kelime_bazli_eslesme" -q
venv/bin/python -m pytest tests/ -q -k "eslesme"            # by name substring
venv/bin/python -c "import main"           # clean import set
python tools/dogrula.py                    # content gate (exit 1 = RED)
python tools/mikrofon_test.py --karsilastir   # per-board mic, ratio <3x = not lesson-ready
```

`pytest` is a dev-only dependency and is deliberately **not** in
`requirements.txt` — the board install stays minimal.

**Two defects found only by running it** (31.07.2026, live session):

- **The model reads instruction markers aloud.** Lesson record: `FARABİ
  [DERS_ACILISI] Merhaba çocuklar…`. Defended twice, like the chain-of-thought
  leak: the opening now says not to read the marker, and `_ETIKET_RE` strips
  `[DERS_ACILISI]`, `[DERS DURUMU]`, `[ÖĞRETMEN KOMUTU]`, `[OTURUM DEVAM]` from
  the transcript.
- **The clock was handed over in 12-hour form.** `time_ctx` used `%I:%M %p`, so
  at 00:20 Farabi told the class *"saat 12:20"*. It is `%H:%M` now — the same
  format the opening already used.

**Verified working:** clean install, Live session, audio tasks, HUD animation,
live tool calls (`ders_icerigi`, `web_search`), lesson-record file,
opening line with day/time/period. **Not verified:** reliable microphone input
(above), real smart-board hardware, touchscreen, camera.

## Architecture

### Session lifecycle (`main.py`)

1. `_log_startup_banner()` — model, prompt size, tool count, **actual default**
   audio devices, lesson frame, lesson mode, classroom; ERROR when no mic/speaker. It used to
   print the *first* device in the list, which sent diagnosis down the wrong path;
   it now prints what `sd.default.device` resolves to.
2. `_build_config()` — time, lesson frame (`_current_lesson`: subject from
   timetable, topic/kazanım from teacher when known), `[KONU BEKLENİYOR]` when
   those are empty, lesson-mode block, `[DERSLİK]` block (`core/tahta.py`,
   omitted when unset), `core/prompt.txt`, language directive (see "Lesson
   language" below), `thinking_config(include_thoughts=False)`. **No student-memory block** —
   `save_memory` and `format_memory_for_prompt` are gone from the live path.

   **Two things must actually be passed to `LiveConnectConfig`, and both were
   silently missing at different times: `system_instruction` and `tools`.**

   `tools=[{"function_declarations": TOOL_DECLARATIONS}]` was absent entirely —
   the declarations were built and dropped, so the model never knew any tool
   existed. The symptom was worse than silence: it **narrated calling a tool**.
   From the lesson record, 30.07.2026 23:25 —
   *"…`youtube_video` aracını çağırıyorum. (`youtube_video` çağırıldı…)
   Çocuklar, şu an ekranda … bir video dönüyor."* — with nothing on screen and
   not one `ARAÇ ▶` line in that session's log. A comment in this very file
   asserted "Araç TANIMLARI gidiyordu (tools=…)"; it did not.

   A tool works only when **both** are true: the declaration reaches the model
   (`tools=`) and the text saying when to call it reaches it
   (`system_instruction`). `tests/test_oturum_yapilandirmasi.py` now asserts the
   built config carries both; the startup banner logs the tool count.

   **The assembled prompt must actually be passed as `system_instruction`.** It
   once was not: `parts` was built and then dropped, so the returned
   `LiveConnectConfig` carried no system instruction and Farabi ran with **no
   persona at all** — no teaching rules, no tool-usage table, no lesson frame.
   It looked healthy because startup logs `Sistem promptu: prompt.txt (8033
   karakter)`; the file was read and discarded. The visible symptom was Farabi
   never calling `ders_icerigi` or `web_search` on its own: tool *declarations*
   reached the model, the text saying *when* to call them did not. If tool use
   goes quiet again, check this line before touching prompt wording.
3. Connects to `models/gemini-2.5-flash-native-audio-preview-12-2025`.
4. Four audio-loop tasks + the 15 s mic diagnostic. Session starts only when
   the teacher double-clicks **DERSİ BAŞLAT** (idle live sessions cost money).
5. `_send_session_opening()` once per process — hour-aware greeting (plus
   *"kıymetli öğretmenim"* in teacher mode), day, time, lesson period, then the
   subject from the timetable. If topic/kazanım are missing, ask the
   **teacher** (not the class) and do **not** start attendance or teaching
   until they arrive. Never invent them from anywhere — there is no yearly
   plan to fall back on anymore, topic/kazanım only ever come from the
   teacher. Never ask the class *"nerede kalmıştık"*.

   Typed teacher lines matching `konu:` / `kazanım:` / `ders:` update
   `_current_lesson` via `_cerceveyi_ogretmenden_guncelle`.

   The opening ends with **"sadece bu açılış turunda araç çağırma"**. It used to say
   "hiçbir araç çağırma" — the model read that as session-wide. Keep any new
   opening rule scoped to the turn.

### Lesson language (`ui.ders_dili`, `main._acilis_selam_gun`)

Two HUD buttons next to **DERSİ BAŞLAT** (🇬🇧 İngilizce, 🇩🇪 Almanca) let the
teacher run the whole lesson in English or German instead of Turkish.
Clicking a language button toggles it; clicking it again (or never clicking
either) leaves `ders_dili` at the default `"tr"`.

**Must be chosen before DERSİ BAŞLAT, not mid-lesson.** A Gemini Live
connection's `system_instruction` cannot change after the connection opens.
`_build_config()` reads `self.ui.ders_dili` once, when building the config
for the (re)connect — since the client is built inside the reconnect loop
(see above), a language chosen before the first connection stays correct
across reconnects too, but there is no supported way to switch language
*during* an already-open session without forcing a reconnect. Both language
buttons are disabled the moment DERSİ BAŞLAT is pressed (`ui.py`).

**`core/prompt.txt` stays Turkish-authored, single source.** Translating a
26K-character, carefully-tuned persona into three languages and keeping them
in sync was rejected outright — the model is instead told (in the language
directive, appended last in `parts`) to *read the Turkish pedagogical rules
above but speak entirely in the target language*. This relies on Gemini's
ordinary cross-lingual instruction-following (the same thing it already does
translating English web-search results into Turkish) rather than triplicating
maintenance.

**Two hard-coded-Turkish spots had to be found and fixed, or the feature
would silently not work**, same class of bug as the missing
`system_instruction`/`tools` lines above — each one *looked* like a detail,
each one would have made the model open an "English" lesson by literally
speaking Turkish:

- The opening's verbatim first line (`"İlk cümlen aynen şu olsun: '{selam}
  {hitap}, ben Farabi.'"`) was built from `core/zil.py`'s Turkish-only
  `selam()`/`GUN_ADLARI` — `core/zil.py` stays Turkish (it also feeds the
  UI's date/time panel, which must stay Turkish regardless of lesson
  language). `main._acilis_selam_gun(ders_dili, simdi)` computes a
  language-appropriate greeting/day name locally instead, used only for the
  opening's verbatim line.
- A second, independent `"- Tamamen TÜRKÇE konuş."` line was appended to the
  *opening's own instruction turn*, separate from and in addition to the
  `[DİL KURALI]` block in `system_instruction` — the general language
  directive alone would not have overridden this more specific, later
  instruction for the opening. Now branches on `ders_dili` (`"- Speak
  entirely in ENGLISH…"` / `"- Sprich vollständig auf DEUTSCH…"`).

**A third spot existed in `actions/screen_processor.py`, since removed
(2026-08-09, see "Project layout") — kept here as history, the lesson about
easy-to-miss unreachable config blocks still applies to any future per-module
persona/session.** It was easy to miss for exactly the reason
`core/vision_prompt.txt` is already flagged "USER-OWNED, easy to miss" in
this doc. That module opened its **own**, separate
Gemini Live sub-session (screen/webcam vision that speaks its answer
directly — see "Provider notes and API quota" for why this couldn't be
migrated off Gemini) with its own persona file and its own hard-coded
`"- Tamamen TÜRKÇE konuş."` line, completely unreachable from
`main.py._build_config()`'s `[DİL KURALI]` block. Without a fix, a student
showing their screen mid-"English lesson" would get a Turkish-speaking
vision module — a jarring, silent break of the feature `main.py` otherwise
delivers correctly. Fixed the same way as `core/prompt.txt`:
`core/vision_prompt.txt` stays Turkish, single source; `_sistem_promptu(ders_dili)`
appends the same style of EN/DE directive. `_VisionSession._session_loop()`'s
`config` (previously built once, before the `while True` reconnect loop —
unlike `main.py`, this one genuinely didn't need per-connection freshness
for anything else) now rebuilds every (re)connection so a language chosen
before `screen_process` is first called is picked up correctly; the value
comes from `self._player.ders_dili` (`self._player` is the `FarabiUI` bridge,
same object `main.py` passes as `player=self.ui` when dispatching the tool).

`tests/test_oturum_yapilandirmasi.py::TestDersDili` and `::TestAcilisSelamGun`
cover the `main.py` side: the directive text per language, the `"tr"` default
when `ui.ders_dili` is absent entirely (not just empty — a bare
`FarabiLive.__new__(...)` test double has no `.ui` at all, which is why the
read is `getattr(getattr(self, "ui", None), "ders_dili", None) or "tr"`, not
a single-level `getattr`), and the greeting/day tables for en/de.
(`tests/test_screen_processor_dili.py` covered the vision-module side the same
way — removed along with the module.)

**Reconnect is backoff'd**: 3, 6, 12, 24, 48, max 60 s. A repeated identical error
logs its traceback once then one line per retry; at 3 failures it logs likely
causes and writes to the on-screen log; every 10th logs CRITICAL. This system
caught both the `language_codes` and the VAD regressions.

### Tool dispatch

**Declarations come from `actions/kayit.py`, not from a list in `main.py`.**
`TOOL_DECLARATIONS = kayit.bildirimler()`. Adding a tool: create
`actions/<name>.py`, add an `Arac(...)` entry to the registry, add an `elif`
branch in `_execute_tool`. `tests/test_arac_kaydi.py` fails if the two drift —
that test replaces the grep one-liner that used to live here.

The registry carries three fields that do real work at runtime:

| Field | Effect |
|---|---|
| `zaman_asimi` | enforced via `asyncio.wait_for` in `_isci`. **There used to be none**, and a measured 55.4 s `ders_icerigi` call froze the whole session |
| `calisma` | `isci` (thread + timeout) / `satirici` (inline: shutdown). A third mode, `daemon`, existed only for the removed `screen_process` (spoke for itself, so a generic worker wrapper would've broken it) — no current tool uses it, don't reintroduce it without a tool that genuinely needs its own thread |
| `kip` | filters which tools are offered per lesson mode (`kip in a.kip` in `bildirimler()`) |

`izin` and `maliyet` are set on every `Arac` and asserted non-empty by
`tests/test_arac_kaydi.py`, but nothing reads them at runtime — they're
metadata for a human scanning the registry, not live behavior. Don't build
logic that assumes they're enforced anywhere.

`run_in_executor` cannot truly be cancelled — the thread runs on. What the
timeout cancels is the **wait**, and that is what matters in a classroom: the
lesson is no longer hostage to one tool. On timeout the model is told the
resource did not arrive and to stay inside the kazanım text.

**Tool calls no longer run inside the receive loop.** `_receive_audio` spawns
`_araclari_calistir` and keeps reading; during the old inline await nothing was
processed, not even student audio.

Tool calls log timing (`ARAÇ ◀ web_search | 2.14 sn | 850 karakter`); over 10 s
logs a WARNING — in a classroom that is a long silence.

Actions are called as `module_function(parameters=args, player=ui, speak=self.speak)`.
Heavy work runs via `loop.run_in_executor`.

**Capability boundary — do not cross it.** No app launching, terminal execution,
OS settings, browser automation, messaging, or process management. `reminder` was
removed (the bell schedule is the timer; a desktop notification firing over a
later class is actively harmful). `file_processor` was narrowed to PDF, Word, text,
spreadsheets, presentations, JSON/XML and images: audio, video, archive and **code**
support were removed because its code handler ran `subprocess.run(["python", file])`
— a student could drop a `.py` and execute it. That was a real hole in this stated
boundary, not a hypothetical.

**This boundary is scoped to `actions/` — the tools the model calls live, during
a lesson.** It is not a claim that `ui.py` itself never shells out; it already
did (`subprocess.run` for mic calibration and book conversion) before this line
was written. `ui.py`'s `_terminalde_calistir` (teacher-triggered, from the
`KİTAPLARI METNE DÖNÜŞTÜR` button — see "Content pipeline" below) opens a real
terminal window; that is deliberate, teacher-initiated admin tooling with no
student-facing surface, not a capability reachable from inside a lesson. If a
future change makes any `actions/` module call `_terminalde_calistir` or
anything like it, that *would* cross this boundary — don't do that.

**`youtube_video` currently breaks this boundary in two reachable ways, not yet
fixed.** `action: "play"` calls `_open_url` → `subprocess.Popen(["xdg-open", url])`,
handing the board an uncontrolled system browser window — the same escape-route
class `site_goster` was built to avoid. `action: "summarize", save: true` calls
`_save_summary`, which writes the summary to `~/Desktop` and then opens it with
`xdg-open`/`notepad.exe`/`open -t` — file writing *and* app launching, both
against the stated rule. README's "Bilinen sorunlar" only flags the first; the
Desktop-write-and-open path isn't documented anywhere. No fix is scheduled —
treat both as open holes, not settled behavior, until someone rewrites
`youtube_video` to stop shelling out (kiosk-mode playback or dropping the
save-and-open step).

### `eba` (`actions/eba.py`, added 2026-08-09) — EBA video + question PDFs

Two actions, deliberately asymmetric:

- **`video`** — same `xdg-open` pattern as `youtube_video`'s `play`, extended
  to EBA on purpose (explicit call, not an oversight): eba.gov.tr is a JS/SPA
  site with no server-rendered search results to scrape (verified via `curl`,
  2026-08-09 — the HTML is an empty app shell), so unlike YouTube there's no
  way to resolve "first matching video" without a real browser. A direct
  `eba.gov.tr` URL opens straight; a bare topic query opens EBA's search page
  instead of a specific video, and the teacher/student picks from there. This
  is the **same capability-boundary violation** `youtube_video` already has
  (see above) — not a new hole, an EBA-scoped instance of the existing one.
- **`pdf`** — does **not** open a browser. Downloads the PDF server-side
  (`requests`, whitelisted to `eba.gov.tr` only) and extracts text the same
  way `actions/file_processor.py::_process_pdf` does (pdfplumber → PyPDF2
  fallback), then prints it to the content panel via `player.show_content`.
  No file written to disk, no app launched — this action does **not** cross
  the capability boundary.

Both actions refuse any URL whose host isn't `eba.gov.tr` or a subdomain of
it (`_izinli`, same suffix-match principle as `site_goster._izinli`).

### `ders_icerigi` — book skeleton, not lesson frame

Call with the **teacher's** `ders` + `konu` (and ideally `sinif`) after the
frame is known. This tool fetches textbook pages; it must **not** invent
today's subject or kazanım, and the session opening must not tell the model
to "learn the outcome from a plan" — there is no yearly plan in this chain at
all anymore (see "Project layout" above). `tema` is still accepted (it
matches a chapter name more precisely than a raw topic string) but is
optional; when it's empty the tool matches `_bolum_bul` against `konu`
directly. If neither is given, it returns the book catalogue instead of
guessing.

**Failure text is BINDING, not permission to improvise.** Fallback paths return
`_SINIRLI_DEVAM`: stay inside the known kazanım text, invent nothing, call the
tool again with a narrower request. If you reword it, keep it restrictive.

**Hand-written mappings win over the index** (`icerik/eslemeler/<kitap>.json`,
JSON so no new dependency). `_bolum_bul` consults them first. This is the fix
for indexes the publisher's page headers ruin: `fizik-10.pdf` had all four unit
names as `ÖLÇME VE DEĞERLENDİRME`; `cografya-10.pdf` was one unit covering the
whole book. Page numbers are **PDF pages**, not the book's printed numbers.

**The page scan is capped** at `TARAMA_SINIRI` (60) pages, striding over larger
ranges. Unbounded, a 233-page "unit" took 55.4 s inside a live lesson.

**Grade defaults to the board's classroom.** If the call names no `sinif`, it
becomes `tahta.sinif_duzeyi()`, so a board configured `"derslik": "10-A"`
searches 10th-grade books without anyone saying "10. sınıf". The substitution
logs `sınıf dersliktan alındı: <n>`.

Subject matching is **word-based, not substring**: `"temel matematik"` does not
appear contiguously inside `"Temel Düzey Matematik"` and used to fail silently.
`_ders_eslesir()` requires every query word to appear somewhere.

Theme→book match requires ≥50% word overlap; below that it returns what it has
rather than risk teaching the wrong theme. Pages are narrowed inside the theme
by keyword scoring against the konu — see "Page selection" below (no
semantic/embedding ranking; that subsystem was removed). Output capped at
6000 chars (~1.5k tokens); if `icerik/ozet/<kitap>.json` exists (see
"Content pipeline" below), a one-line book summary is prepended.

### `kitap_sorusu` — sourced Q&A via server, not a page fetch

Added 2026-08-11. Calls `server/`'s RAG pipeline (`POST /api/egitim/question`
— retrieval + rerank + threshold + LLM + number-check, see `docs/mimari.md`
§8) for a **concrete question**, not a topic to teach. `ders_icerigi` hands
the model raw pages to narrate from; this tool hands back an already
source-checked answer string that must be read as given, not elaborated on.

**`ders` is required in the schema and enforced in code** (`_kitap_id_bul`
returns `None` if `ders` is falsy) — found via live testing 2026-08-11:
without it, the board's classroom grade (`tahta.sinif_duzeyi()`) alone could
match the *first* book at that grade level regardless of subject, e.g. a
physics question answered — with a citation — from the biology book. `ders`
closes that; `sinif` still defaults from the board if omitted.

The server's book list (`GET /api/egitim/kitaplar`) is fetched once and
cached in `_KITAP_ONBELLEK` for the process lifetime — same pattern as
`_METIN_ONBELLEK` in `ders_icerigi.py`.

**Every non-`ok` path returns `_SINIRLI_DEVAM`, never raises.** Server
unreachable, no matching book, `yetersiz_kaynak`, `sayi_kontrolu_reddi`, and
the server's own `hata` status (its internal exception text is deliberately
not exposed over the API — "Brain karar verir" — it's in the server's
`soru_log` instead) all degrade silently; `main.py`'s `speak_error` alarm is
never triggered by this tool. Timeouts: `GET` 5 s, `POST` 10 s (measured
worst case 5.3 s, no headroom before 2026-08-11 — raised from 5 s), registry
`zaman_asimi=16.0` to cover both.

### `pdf_sayfa` — one page number, rendered as an image, no topic matching

Added 2026-08-12. Renders a single PDF page with PyMuPDF (`fitz.open(...)
.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))`, `ZOOM=2.0`) to a PNG cached at
`icerik/onbellek/pdf_sayfa/<kitap>_s<sayfa>.png`, then calls
`player.show_image(title, path)`. Call for "9. sayfayı göster/yansıt" —
**no** theme/topic matching happens (unlike `ders_icerigi`), the page number
is used as-is. Image, not text, deliberately: a page rendered to text loses
diagrams/tables/formulas exactly the way `tools/kitap_metin.py` warns about
for `ders_icerigi`.

**Same `ders`-required discipline as `kitap_sorusu`** (`_kitap_bul` returns
`None` if `ders` is falsy) — same reasoning: without it, the board's grade
alone could match the wrong subject's book for that grade.

**UI side (`ui.py`):** the content-panel overlay now has two mutually
exclusive display modes — `_show_content` (text, `QTextEdit`) and
`_show_image` (this tool, `QLabel` inside a `QScrollArea`). Zoom is
`self._image_zoom: float | None` — `None` means "fit to panel width",
recomputed on window resize; a number is a fixed multiplier set by the
`−`/`⛶ SIĞDIR`/`+` buttons above the image and left alone on resize once the
teacher has manually zoomed. `QScroller.grabGesture(...,
LeftMouseButtonGesture)` is attempted for touch/drag panning on the board;
wrapped in `try/except` since it's a nice-to-have, not load-bearing —
scrollbars work regardless.

**Reuse:** `render_pdf_sayfa()` is a standalone render helper (raises on
error, produces no class-facing text itself) that `yks_sorulari.py` imports
directly for its own page rendering, so the fitz rendering logic lives in
exactly one place — see `pdf_sayfa.py`'s module docstring.

### `yks_sorulari` — past exam questions, one at a time, shown as an image

Fetches YKS (TYT/AYT) past exam questions on the current topic from
`icerik/yks_metin/*.txt` (produced offline by `tools/yks_metin.py`, see
"Content pipeline" below) for **matching only** (word-overlap, per page,
`===SAYFA <n>===` markers). For **display**, added 2026-08-12: the actual PDF
page from `client/YKS/<dosya>.pdf` is rendered via `pdf_sayfa.render_pdf_sayfa`
and shown with `player.show_image` — original layout preserved (diagrams,
tables, answer choices), not reflowed text. The question text returned to the
model is still the raw extracted text, for it to read aloud — not the source
of truth for what's on screen.

**One question at a time, advance only on command.** A module-level `_OTURUM`
dict (`{"adaylar": [...], "index": -1}`, process-lifetime, same pattern as
`_METIN_ONBELLEK`) holds the current matched sequence. Calling with `konu`
(+ optionally `ders`, `adet`) starts a **new** sequence and shows only the
first match, even if more matched. Calling again with `sonraki=true` and
**no** `konu` advances to the next stored match and shows *that* page;
calling with a new `konu` always restarts the sequence from scratch. This is
enforced by the tool holding index state, but *when* to call `sonraki` is a
prompt-level decision — see core/prompt.txt's SESLİ HİTAP/SORU SUNUM
PROTOKOLÜ — never triggered automatically by the tool itself.

There is no answer key or worked solution in the source PDFs (they're
marketed as "tamamı video çözümlü" — solutions are in an external video, not
the text), so the tool cannot supply one; the `aciklama` in `actions/kayit.py`
tells the model to read the question to the class, then go silent and wait —
work the solution itself only once asked, step by step, rather than treating
this as a quiz to withhold answers on.

There's no book/subject filter in the YKS archive's metadata, so a `ders`
hint just gets folded into the query words to bias matching, it doesn't
restrict which file is searched. Measured 0.26 s for a full-archive keyword
search with all 8 files converted (2.8 MB text, ~1,300 pages) — no
semantic/embedding ranking exists anywhere in this repo anymore, so there's
nothing to fall back from. If `icerik/yks_metin/` is empty (conversion never
run — via the HUD's "YKS SORULARINI METNE DÖNÜŞTÜR" button or
`tools/yks_metin.py` by hand), the tool refuses and tells the model to keep
teaching from the textbook instead of inventing a question — same "fallback
text is binding" principle as `ders_icerigi`'s `_SINIRLI_DEVAM`.

### `site_goster` — deliberately browser-free

A real browser on a classroom board hands students uncontrolled internet (address
bar, links, new tab, back button — all escape routes). Instead the page is fetched
server-side, stripped of nav/ads/scripts, and printed to the content panel. There
is no browser to escape from.

Whitelist is domain-based with suffix matching and the URL is re-checked **after
redirects**. Tested rejections: `tr.wikipedia.org.evil.com`, `file:///etc/passwd`,
arbitrary domains. HTTP headers must be latin-1 encodable — a Turkish `ı` in the
User-Agent raised `UnicodeEncodeError`.

The `eba.gov.tr` entry covers all subdomains via the suffix match, which is
why `ogmmateryal.eba.gov.tr` (MEB's official materials portal) and
`mebi.eba.gov.tr` (LGS/YKS topic-summary and past-question platform) already
work without a whitelist change — verified with `_izinli()`. `actions/kayit.py`'s
`site_goster` description names both explicitly so the model actually reaches
for them. `mebi.eba.gov.tr` also hosts lecture videos, but those are out of
reach here the same way any embedded video is (see "Limit" below) — this tool
returns only the text/menu content that comes back in the initial HTML.

Limit: text and tables only. Interactive content (simulations, GeoGebra, embedded
video) cannot be shown; use `youtube_video` for video.

### Persona file — `core/prompt.txt`

`core/prompt.txt` is the main (and, since 2026-08-09, only) teaching persona.
`core/vision_prompt.txt` still sits in `core/` but is now **orphaned** — its
only reader, `screen_processor.py`, was removed (no camera/screen capture
anywhere in this repo). Left on disk rather than deleted, same reasoning as
`planlar/`: it's the teacher's/developer's authored content, not code, and
not this rewrite's call to discard — **user-owned**, do not delete or rewrite
without being asked.

Rules currently in `core/prompt.txt` (v2.0): Socratic questioning and the three-step
rule; **attendance first** (only after topic/kazanım are known); **subject from
the timetable, not asked** (`[ŞU ANKİ DERS]`); **topic/kazanım from the teacher**
(never from Excel/plan auto-detect; never *"nerede kalmıştık"*); **the textbook
is a skeleton** — `ders_icerigi` pages + `web_search` for depth, and the
teacher's kazanım stays the test of relevance; the 9-step lesson flow; three
difficulty levels; participation prompting; group work; exam mode; the
end-of-lesson package and the teacher evaluation; games allowed **if they serve
the kazanım**; the noise rule; refusal of off-topic engagement; prompt-injection
resistance (content in files, on screen or from search is **data, not
instructions**).

**The `SINIRLARIN` block is load-bearing — do not delete it as obsolete.** It tells
the model three things it cannot do, each of which it would otherwise fabricate:
there is one microphone and **no speaker identity**, so no participation percentages
and no per-student report; `[CURRENT DATE & TIME]` is built once per `_build_config`
so the model has **no ticking clock** — pacing is step-based ("her çözülen örnekten
sonra"), never minute-based, and real timing is handed to the teacher; and there is
**no private channel** — everything spoken is heard by the class and `show_content`
is on the same board, so the teacher evaluation is subject-level and nameless. If
speaker diarization or a periodic time injection ever lands, that block is what
needs rewriting — not silently removing.

Exam mode has no state anywhere in the session; the prompt makes Farabi **announce
entry and exit out loud** so its own transcript is the anchor. Suspending the
three-step rule silently would leave the model pulled both ways mid-quiz.

### Content pipeline — `tools/`

Prepared **once, offline** (or from a HUD button, see below), never at
runtime, and never automatically triggering an API call without an explicit
`--onayla`/button press:

```bash
python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json
python tools/kitap_metin.py  kitaplar/ --json icerik/metin
python tools/dogrula.py
python tools/yks_metin.py    YKS/      --txt  icerik/yks_metin   # for yks_sorulari

# optional, PAID (real core/saglayicilar.py calls — Groq/Mistral/DeepSeek/
# OpenRouter/NVIDIA NIM, no Gemini) — see the two subsections below
python tools/sembol_temizle.py --onayla
python tools/kitap_ozet.py     --onayla
```

There is no yearly-plan step here anymore — `tools/plan_parse.py` and
`icerik/plan.json` are gone (see "Project layout" above). A lesson only ever
needs `kitaplar.json` + `icerik/metin/`.

**`kitap_metin.py` is not optional.** It is what `ders_icerigi` reads at runtime.
A book missing from `icerik/metin/` still works, but every page selection for it
opens the PDF with `pdfplumber` in the middle of a lesson. `ls icerik/metin/` is
the check — anything in `kitaplar/` without a matching JSON is on the slow path.

**Every step above is also a HUD button** (`ui.py`, right panel): `📚 KİTAPLARI
METNE DÖNÜŞTÜR` (`_kitaplari_donustur`), `📝 YKS SORULARINI METNE DÖNÜŞTÜR`
(`_yks_donustur`), `🧹 ŞÜPHELİ SEMBOLLERİ TEMİZLE (AI)` (`_sembolleri_temizle`),
`🗒️ KİTAP ÖZETİ ÇIKAR (AI)` (`_kitap_ozeti_cikar`). The first two share
`_terminalde_donustur`, the AI-paid two share `_api_calisan_dugmeyi_baslat` —
both run in a **visible terminal window**, not silently. It used to be
`subprocess.run(capture_output=True)` — no output until the whole run finished,
which on a large/scanned book looked like the app had frozen. `_terminalde_calistir`
(module-level in `ui.py`) launches the script in the first available terminal
emulator (`x-terminal-emulator`, `gnome-terminal`, `konsole`, `xfce4-terminal`,
`xterm`) so the teacher sees the script's own progress lines live; falls back
to the old silent `subprocess.run` only if no terminal is found. This is
scoped to these admin buttons, not to `_icerik_hazirlik_kontrolu` (the startup
check) — that one still runs silent/background, because it can fire while the
HUD is coming up right before a lesson, and a terminal window stealing focus
over the board at that moment is the same class of harm that got `reminder`
removed. See "Capability boundary" below for why this doesn't conflict with the
no-terminal-execution rule. Pressing a paid button **is** the `--onayla`
confirmation — both scripts are invoked with it already set.

**`_icerik_hazirlik_kontrolu` also refreshes `icerik/kitaplar.json` on every
startup**, silently, before the two conversion steps: it diffs the PDF
filenames in `kitaplar/` against the `dosya` fields already in
`kitaplar.json` and runs `kitap_index.py` only if something's missing
(`_kitaplar_json_guncelle`). A book dropped into `kitaplar/` becomes
searchable without anyone remembering to run the indexer by hand — it still
needs `kitap_metin.py` (button or startup check) before its pages are fast.

**`yks_metin.py` is the same idea for `yks_sorulari`, run separately** — it's
not part of `dogrula.py`'s gate (that gate validates the *textbook* index, unit
coverage, theme names; the exam-question archive has no such structure to
validate). Skipping it just means `yks_sorulari` refuses every call until
`icerik/yks_metin/` exists — measured: 8 files (~2.8 MB PDFs → text, 1,300
pages) converted in 4m9s on this dev machine, one-time cost.

**`sembol_temizle.py` is a separate, opt-in, PAID third layer on top of
`kitap_metin.py`'s two-layer repair** (see below) — it sends each page that
still carries an ambiguous `#`/`$` to the text model with instructions to
replace a symbol **only when certain**, and leave it alone otherwise; anything
left ambiguous still gets the "read this sentence, not the symbol" warning at
runtime. Deliberately kept out of `dogrula.py` (which is free and instant) and
out of `kitap_metin.py` (which is free and runs on every conversion) — mixing
a paid, non-deterministic step into either would make a normal conversion or
validation run silently cost money.

**Two bugs found in a real run** (02.08.2026, live `--onayla`, real
DeepSeek/Mistral keys):

- **The "kaç sayfa düzeltildi" counter always reported 0**, even when a page
  genuinely got fixed (verified: `fizik-10.pdf` s.88 went from `supheli: 1`
  to `supheli: 0`, `ai_temizlendi: true` — real fix, wrong report). Cause:
  `kayit["supheli"]` was overwritten with the new count *before* being
  compared against the old one, so the comparison was against itself and
  could never be true. Fixed by capturing `eski_supheli` first. The
  written data was never wrong, only the summary line — worth remembering
  before assuming a "0 düzeltildi" run did nothing.
- **A single failing provider call could silently block for minutes**
  (measured: one page took 464 s with no output) — `openai`'s client
  retries 429/5xx internally with backoff *before* our own
  `_zinciri_dene` gets a chance to move to the next provider, so a
  provider we're about to skip anyway (DeepSeek returning a permanent 402
  "Insufficient Balance" is never going to succeed by retrying) still ate
  real wall-clock time on every single call. Fixed in
  `core/saglayicilar.py._istemci()`: `max_retries=0, timeout=30.0` on the
  `OpenAI(...)` client — provider-level failover already exists one layer
  up, the SDK's own retry was pure redundant latency stacked on top of it.

**`kitap_ozet.py` produces `icerik/ozet/<kitap>.json`** — a short book
summary (from a handful of sample pages) plus a grounded-web-search block of
enrichment question ideas for the book's chapters (same `google_search` tool
`web_search.py` uses). Not a new tool the model calls: `ders_icerigi`'s
`_kitap_ozeti()` reads the summary file if present and prepends it to the
page content it already returns, so a lesson still costs exactly one tool
call.

`kitap_index.py` handles "Ünite" (older books) and "Tema" (Maarif Modeli books,
which put the name inside the header: `1. Tema / Sayılar`), single file or whole
directory.

**MEB math/physics PDFs have a broken symbol font**: `R"R` should be `R→R`,
`6c, d !R` should be `∀c, d ∈ R`, `a$c` should be `a·c`. `pdfplumber` and
`pdftotext` produce identical corruption — it is the PDF. Measured: prose book 0
occurrences, matematik-9 125, matematik-10 78.

**This is now fixed offline, in text, with no API call** (`tools/kitap_metin.py`),
and the fix is deliberately two-layer:

- **unambiguous corruption is repaired** — `R"R`→`R→R`, `x!R`→`x ∈ R`, `6x`→`∀x`.
- **ambiguous corruption is never guessed, only counted** — `#` may be ≤, ≥ or ≠
  and `$` may be `·` or ≥. `ders_icerigi` reads that count (`supheli`) and appends
  a warning telling the model not to read the formula symbol by symbol. Teaching
  an inequality the wrong way round is worse than not showing the symbol at all.

**Do not re-add the image path.** Pages used to be rendered with `pypdfium2` and
transcribed by Gemini. It burned a real API call per new theme and its measured
worst case mid-lesson was a 20 s timeout (31.07.2026 live session). `_gorsel_cikar`
is gone and the note at the foot of `actions/ders_icerigi.py` says so — the broken
symbols are solved by the two layers above, not by pictures.

**Sayfa metni `PyMuPDF` (fitz) ile çıkarılıyor, `pdfplumber` ile değil** —
`kitap_metin.py` ve (02.08.2026'dan beri) `kitap_index.py` içinde; diğer
araçlarda (`file_processor`, `ders_icerigi`, `yks_metin`) `pdfplumber` hâlâ
duruyor, çünkü onlar tek seferde bir belge işliyor, bir kitaplığın tamamını
taramıyor. Gerekçe ölçüldü: `pdfplumber`, 300+ sayfalık görsel ağırlıklı
`tarih-10.pdf`'de (161 MB) her sayfanın ayrıştırılmış nesnelerini önbellekte
tutup 5+ GB'a çıkıp bu makinede (7,1 GB RAM) OOM'a düşüyordu —
`sayfa.close()` bile yetmedi. `fitz` aynı kitabı 7,1 sn'de, 246 MB sabit
bellekle bitiriyor. `kitap_index.py` aynı OOM'u kendi başına, `pdfplumber`
üzerinde tekrar üretti (ölçüldü: `_kitaplar_json_guncelle`'in ardı ardına
tetiklediği 3 eşzamanlı süreç ~4,6 GB'a çıkıp makineyi takasa düşürdü) — bu
hem `fitz`'e geçişi hem `kitap_metin.py`/`yks_metin.py`'deki `fcntl` kilit
desenini `kitap_index.py`'ye eklemeyi gerektirdi (aynı hedefe iki süreç
birden yazmasın diye).

**`kitap_index.py`'nin fitz geçişi bir REGRESYON içeriyordu, "tüm özellikleri
test et" isteği sırasında bulundu.** `indexle()` ünite/tema başlığını
yalnızca sayfanın İLK SATIRINDAN okuyor. `sayfa.get_text()` (varsayılan,
`sort=False`) fitz'in PDF'in dahili nesne sırasını izler; birçok kitapta
sayfa numarası (üstbilgi/kenar boşluğu nesnesi) başlıktan ÖNCE geliyor, bu
yüzden ilk satır "1. Tema" değil "15" gibi bir sayı oluyordu ve `BOLUM_RE`
hiç eşleşmiyordu. Ölçüldü: gerçek kitaplıkta (13 kitap) `sort=False` ile
yalnızca 3'ünde bölüm tespit ediliyordu — **`biyoloji-9.pdf` dahil, daha önce
(pdfplumber ile) 2/2 doğru tespit edilen bir kitap SIFIRA düşmüştü**, ve bu
`ders_icerigi`'yi o kitap için tamamen köreltiyordu ("Kitap bölümü
eşleşmedi"). `sayfa.get_text(sort=True)` (konum sıralı: üstten alta, soldan
sağa) düzeltti — 9 kitapta iyileşme, hiçbirinde gerileme (`tarih-10.pdf` ve
`waymark-*.pdf` ikisinde de 0 kaldı, muhtemelen taranmış/düzensiz sayfa
düzeni, sıralamadan bağımsız bir ayrı sorun). `tests/test_kitap_index_sira.py`
sentetik bir PDF'le (sayfa numarası nesnesi önce eklenir, başlık nesnesi
sayfada daha yukarıda ama SONRA eklenir — ölçülen gerçek düzenin taklidi)
bunu kilitler; `kitaplar/` bir DROP DIRECTORY olduğu (gitignore'da, her
makinede olmaması normal) için test gerçek bir kitaba bağımlı değil.

**Görsel OCR yedeği var, ama DAR ve SAYFA GÖVDESİNİN üzerine hiç yazmıyor —
bu, "Do not re-add the image path" ile ÇELİŞMİYOR, farklı bir şey.** Eski yol
her yeni temada Gemini'ye görüntü gönderiyordu (API, kota, ders-ortası gecikme).
Bu yol tamamen yerel (`tesseract`), yalnız `kitap_metin.py`'nin offline dönüştürme
adımında çalışır, asla derste değil. Her sayfada `sayfa.get_images()` ile büyük
görseller (harita, tablo-görseli, diyagram — <150×150 px ikon/logo elenir) tek
tek kırpılıp OCR'lanır ve sonuç **gövde metnine EKLENİR**, üzerine yazılmaz;
`"[SAYFADAKİ GÖRSEL/HARİTA METNİ — OCR ile okundu, hatalı olabilir]"` etiketiyle
ayrılır — `#`/`$` şüpheli sembol uyarısıyla aynı ilke: belirsiz/hatalı olabilecek
içerik asla sessizce iyi metinle karıştırılmaz. Ölçüldü ve KASITLI olarak dar:
tam sayfa OCR, zaten metin İÇEREN bir sayfada (tarih-10.pdf) denendi, sonuç
`fitz`'in çıkardığından daha kötüydü (tablo çerçeveleri "eT3.", "ee ee ee" gibi
gürültüye dönüştü) — bu yüzden OCR yalnız görsel dikdörtgenleri hedefler, gövde
metnini yeniden okumaz. Aynı mekanizma taranmış (metin katmanı hiç olmayan) bir
sayfayı da ayrıca kod yazmadan kurtarır: öyle bir sayfada gövde tek büyük bir
görseldir, döngü onu da yakalar. `tesseract`/`tesseract-ocr-tur` sistemde yoksa
(`sudo apt install tesseract-ocr tesseract-ocr-tur` — pip değil, apt paketi)
sessizce atlanır, kitap yine dönüşür. Kapatmak için: `--ocr-yok`. Ölçüldü:
12 kitaplık kitaplığın tamamında görsel OCR toplam ~20 dakika (tek seferlik,
offline; en ağırı `tarih-10.pdf` ~5 dk, 308 büyük görsel).

The `gorsel` marker itself still exists and is **inert at runtime**: `kitap_index.py`
still sets `yontem: "gorsel"` on units with ≥3 corrupt symbols, but `ders_icerigi`
only logs that field. Nothing branches on it. It is an index-quality signal now,
not an extraction mode — don't wire behaviour back onto it.

Indexing quality varies by publisher and **the gate now measures it**
(`tools/dogrula.py`). matematik and biyoloji index cleanly. `fizik-10` and
`cografya-10` do not, and the earlier note here — "page ranges are still right" —
was wrong for coğrafya: its index is a *single* unit spanning s.9–241, i.e. the
whole book, which is where the 55.4 s page scan came from. Both are now fixed by
hand in `icerik/eslemeler/`, which is the supported answer for any book whose
running headers carry no unit name.

**One cache now, plus one in-process cache:**
- `icerik/onbellek/_sayfa_secimi.json` — page selection, on disk. Without it every
  call re-scored all ~86 pages of a theme: 13.3 s versus 0.03 s.
- `_METIN_ONBELLEK` in `ders_icerigi` — a converted book (0.5–2 MB of JSON) is held
  in memory for the life of the process; one lesson hits the same book repeatedly.

The `icerik/onbellek/<kitap>-s<ilk>-<son>.md` files are **leftovers from the
removed Gemini transcription** — nothing reads them. Delete freely. Same for a
stray `icerik/plan.json` if one is sitting on disk (measured: 3.9M) — debris
from the removed yearly-plan pipeline (see "Project layout" above); no code
path reads or writes it anymore.

**A cold page selection is still the slow moment**, and how slow depends on the
book: a converted book is scored in memory, an unconverted one opens the PDF and
is bounded by `TARAMA_SINIRI` (60 pages, striding over larger ranges). Either way,
warm it before a lesson, not during one.

**Do not put textbook content in the system prompt.** The persona is ~1.4k tokens,
a theme is 13–37k. Content belongs behind a tool call.

### Page selection: hand-written mapping first, word-overlap underneath

Where the book index is good, unit-level lookup is deterministic and nothing
beats it:

```
teacher konu (+ ders / tema) → book index → volume + pages → icerik/metin
```

Verified name-for-name for matematik-9 (7/7 across both volumes) and for
cografya-10 (7/7 against the printed table of contents).

**But "we always know where the answer is" was too strong.** Measured:
`fizik-10` matched **zero** unit names by header alone because the publisher's
page headers name every unit `ÖLÇME VE DEĞERLENDİRME`. Name matching fails
exactly where the publisher is sloppy, and no amount of matcher cleverness
fixes a name that is not there. The fix is a hand-written mapping
(`icerik/eslemeler/`) — deterministic, auditable, ~20 minutes per book — and
it always wins over the auto-index.

**Ranking pages *within* an already-resolved chapter is word-overlap only —
no semantic/embedding search.** `tools/semantic_index.py` (a local
`sentence-transformers` embedding index) existed at one point and was
**removed**: `sentence-transformers`/`torch` are gone from
`requirements.txt`, and `ders_icerigi._ilgili_sayfalar` has no import to try
before falling back — the word-overlap scorer against `konu` is the only
path now. This was a deliberate simplification (lighter board install, one
fewer subsystem to keep correct), not a regression to route around; do not
reintroduce a vector index without a concrete, measured reason the
word-overlap scorer is failing.

Symbol-heavy units are only as good as `kitap_metin.py`'s repair layer (plus
the optional `tools/sembol_temizle.py` AI pass, see "Content pipeline"
above) — the ambiguous symbols are flagged rather than silently resolved
unless that separate, paid step has been run.

### Lesson engine (`core/ders_motoru.py`) — INJECTING (`enjekte=True`)

The lesson flow is code's job, not the model's. The engine owns the step
(`BEKLIYOR → YOKLAMA → … → OZET → ODEV → BITTI`), the remaining minutes (from
`zil.ders_durumu()`, which now also returns `kalan_dk` as a number) and a closed
set of suggestions (`ADIM_OZET`, `FARKLI_ANLATIM`, `KONTROL_SORUSU`,
`DURAKLAT`).

**Three rules govern injection, each from a real failure** (reported symptom:
*"açılıyor, konuyu anlatmaya başlayamıyor, sonra tekrar selam veriyor, dinliyor
düşünüyor dinliyor döngüsü"*):

1. **`turn_complete=True`.** It was sent as `False`, leaving an open user turn;
   the session sat waiting and the model never got to speak.
2. **Nothing for the first `ENJEKSIYON_GECIKMESI_SN` (75 s) of a session,** and
   never while `_is_speaking`. A status block landing on top of the greeting made
   the model start the greeting over.
3. **Threshold-based, not per-minute.** `kalan_dk` changes every minute and was
   part of the signature, so a notice went out every minute. Now the signature
   uses `_sure_bandi()` (20/10/5/2) plus step and suggestion.

On reconnect the client sends `_oturum_devam_notu()` instead of the opening —
`[OTURUM DEVAM] … SELAMLAMA YAPMA`. The new session's model remembers nothing and
the persona tells it to greet, which is the other half of the repeated-greeting
bug. Stale `mudahale` is also cleared on reconnect (an explicit `duraklat()` is
not).

**Injection is now ON** (`enjekte=True`). It was an observer first, then turned
on when the requirement became "Farabi plans and delivers the 40 minutes without
the teacher steering". That requirement needs the model to know the clock, and
the engine is the only thing that can tell it — `[CURRENT DATE & TIME]` is built
once per `_build_config` and never ticks. `[DERS DURUMU]` blocks go in on change
only (step, 10/5/2-minute thresholds), never periodically; identical state is
suppressed.

**This is the rewrite CLAUDE.md warned about**: the `SINIRLARIN` clock bullet in
`core/prompt.txt` used to say "you have no clock, never speak in minutes". It now
says the remaining time is known **only from `[DERS DURUMU]`**, and step-based
pacing applies when no such notice has arrived. The speaker-identity and
private-channel bullets are untouched — those constraints did not change.

**The teacher always wins**: `mudahale()` pauses suggestions, `gec()` forces a
step. An engine that overrides the teacher is worse than no engine.

### Event bus (`core/olaylar.py`)

In-process `asyncio` fan-out, no broker — 15–20 boards produce a few events per
second each. Fixed event names (`ARAC_BASLADI`, `ARAC_ZAMAN_ASIMI`,
`DURUM_DEGISTI`, …); `abone()` rejects unknown ones, because a typo'd
subscription that never fires is the hardest failure to find. Subscriber
exceptions are swallowed and logged: a lesson must not stop because a log line
failed.

### Cache warming (`tools/onbellek_isit.py`) — pay the cost before the lesson

Measured in a live run (31.07.2026, 00:29): the model called `ders_icerigi` on
its own for a `gorsel` theme, the uncached Gemini transcription ran past the
20 s tool timeout, and the class got 20 s of silence followed by a contentless
continuation. Warming that same kazanım offline took **57.1 s**; the identical
call afterwards returns in **0.03 s**.

**That original cost is gone with the image path** — warming no longer spends API
calls. What it warms is `_sayfa_secimi.json`, which matters most for a book
that has not been through `kitap_metin.py`, since selecting its pages means
opening the PDF.

**The topic must be given by hand** (`--ders --sinif --konu`) — there is no
automatic "what's tomorrow's topic" source anymore. The script used to fall
back to `gunun_adaylari` (yearly-plan candidates) when the timetable didn't
resolve a topic; that function is gone along with the plan pipeline, and
warming without a `konu` can't select real pages anyway (it would just
re-fetch the book catalogue). Whoever runs this — the evening before, e.g.
via cron — needs the teacher to have already said what topic tomorrow
covers. **Dry by default** — `--onayla` is still required.

Two symptoms that mean the cache is cold rather than something being broken: a
`ders_icerigi` timeout in the log, and Farabi telling the class about a
"teknik aksaklık" (the timeout text now explicitly forbids that phrasing).

### Content validation gate (`tools/dogrula.py`)

Run it after `kitap_index.py`, and before trusting a new book. It fails a
book when every unit carries the same name, when one unit covers >70% of the
pages, or when a mapping file is malformed. Exit code 1 on any RED, so an
installer can gate on it. Free and instant — no API call, no plan/coverage
check (the yearly-plan pipeline it used to validate against is gone; see
"Project layout" above). AI-assisted symbol cleanup is a **separate** script
(`tools/sembol_temizle.py`, paid, opt-in) — deliberately not folded into this
gate, so running `dogrula.py` never silently costs money.

Bad index data used to surface **in the classroom** as improvisation; this moves
the failure to a report. A book with a hand-written mapping passes even if its
auto-index is bad — that is the intended escape hatch.

### Timetable (`core/program.py`, `config/ders_programi.json`)

**This supplies the subject name.** `zil.json` knows bell times only; there is
no yearly plan anywhere in this repo anymore. The file maps
`sınıf → gün → ders saati → ders` (a slot may also carry `kip`), so the board
knows at startup: *3. ders · 9-A · Matematik* — topic and kazanım still empty
until the teacher provides them.

Chain: `program.simdiki_ders()` → `_programdan_cerceve()` → `current_lesson`
with `subject` + `period` only.

**No timetable / empty slot:** ask the **teacher** for the subject (and
topic); do not ask the class and do not invent a subject from anywhere else —
there is no fallback candidate list. A board without a timetable must still
teach once the teacher speaks, same principle as `ui.py` surviving a missing
`zil.json`.

`ders_kipi` reads the **timetable first** (`program.kip()`), then
`config/api_keys.json` — study hall and make-up periods are a property of the
schedule.

### Teacher panel (`ui.py`) — two intervention buttons, on purpose

The **intervention** controls in `ÖĞRETMEN PANELİ` are exactly **DURDUR** and
**DEVAM ET**. Everything else that touches an *already-running* lesson was
removed by decision: the virtual teacher plans and runs the 40-minute lesson,
and a system needing constant teacher intervention is a system not doing its
job. Anything else the teacher wants mid-lesson is typed — the input box
already sends teacher instructions. Those two stay as buttons because when
they are needed there is no time to type (someone walks in, a phone rings).

The same grid also holds **DERSİ BAŞLAT** and, since the lesson-language
feature (see "Lesson language" above), the two language buttons — these are
not interventions, they are **pre-lesson setup**, made once before the
connection opens and then locked (the language buttons disable themselves
the moment DERSİ BAŞLAT is pressed). That's a different category from "the
teacher needs to redirect a lesson in progress," so it doesn't reopen the
"two buttons only" decision above.

`durdur` is a **latched** pause (`motor.duraklat()`), cleared only by `devam` —
a lesson that resumes on its own defeats the reason it was stopped. Typed
commands use the **time-limited** `motor.mudahale()` (`MUDAHALE_SURESI_DK`),
because with no "devam" for them, a latch would silence the engine for the rest
of the lesson.

**Everything typed into the input box counts as a teacher instruction.** In a
classroom the keyboard is at the board: students speak, the teacher types. The
box is labelled `ÖĞRETMEN GİRİŞİ · YAZILAN = TALİMAT` and its text is sent with
the same marker as the buttons.

Commands reach the session as `[ÖĞRETMEN KOMUTU] <metin>` through
`FarabiUI.on_teacher_command` → `FarabiLive._on_teacher_command`, which also
drives the lesson engine (`mudahale()` / `duraklat()`), parses optional
`konu:` / `kazanım:` / `ders:` into `_current_lesson`, and emits
`OGRETMEN_MUDAHALE`.

**The marker is load-bearing.** `core/prompt.txt` has an `ÖĞRETMEN KOMUTLARI`
block saying marked instructions **override the pedagogical defaults** — "cevabı
göster" suspends the three-step rule for that turn, "sadece ipucu" holds the
answer back even in exam mode. Without it the model hedges ("doğrudan vermek
istemem ama…") instead of complying. A student saying the same words out loud
gets the normal rules; the marker is what separates them, and it is only ever
attached by the panel and the input box.

**No auth on the board.** Any student standing at the touchscreen can type into
the teacher box. There is no role-gating anywhere in this repo and none is
planned — if that becomes a real problem, it needs a local solution (PIN,
physical key, teacher-only device), not a server to defer it to.

### Model names (`core/modeller.py` for Live, `core/saglayicilar.py` for everything else)

`gemini-2.5-flash` **was retired mid-flight** (verified 31.07.2026: 404 "no
longer available", and `gemini-2.5-flash-lite` with it). At the time every
non-realtime call went through Gemini too, so it broke at once — the visible
symptom was `ders_icerigi` returning "Kitap içeriği okunamadı" after 17.1 s
while the class waited, with nothing explaining why. `ders_icerigi` itself
calls no AI API at all now (see "Content pipeline"), so that specific failure
mode is gone, but the lesson generalizes: **any** provider can retire a model
without notice.

`core/modeller.py` now holds only `CANLI_MODEL` (Live audio) — no fallback
logic left there, because it has exactly one consumer shape (the Live
session) and no alternative model to fall back to if the Live name breaks.
`core/saglayicilar.py` holds every other model name, one per
`(sağlayıcı, model)` pair in `GOREV_ZINCIRLERI`; a bad model id there fails
that one provider (caught, logged) and the chain moves to the next provider
— the fallback is provider-level, not a same-provider alternate-model retry
like Gemini's old `uret()` used to do. Measured for Gemini at the time of
writing: `gemini-3.6-flash` ✔, `gemini-flash-latest` ✔, `gemini-3.5-flash`
503, `gemini-2.5-flash*` 404 (kept for history; not relevant to `CANLI_MODEL`,
which is a different model family).

### Bell schedule (`core/zil.py`, `config/zil.json`)

Real school times from `dersgiriscikis.png`: 1st lesson 08:20, 40-minute lessons,
10-minute breaks, lunch 12:20–13:00, 8th lesson ends 15:20. Same every day, Mon–Fri.
`zil.ders_durumu()` distinguishes in-lesson, break, lunch, before-first, after-last
and non-school-day, returning both a short UI label (`kisa`) and a full sentence
for the model (`metin`).

**Why it lives in `core/` and not `main.py`.** Two consumers need it: `main.py`
injects the lesson period into the system prompt, and `ui.py` shows it in the
date/time panel — and `ui.py` cannot import `main.py` without a circular import.
`main._ders_saati_durumu()` is now a thin delegate; put new schedule logic in
`core/zil.py`. `core/tahta.py` is shared for the same reason (prompt + HUD label
+ `ders_icerigi`), which is why both are in `core/` rather than beside their
callers.

**Turkish suffix lesson:** phrases were built as `"ilk ders 08:20'te"` and the model
parroted the wrong suffix (correct `08:20'de`; it depends on the spoken number —
yirmi**de**, on**da**, kırk**ta**). Solving that in code is brittle. The phrases are
now **suffix-free** ("ilk dersin başlama saati 08:20") and the model inflects
correctly on its own. Apply the same approach to any new time or number phrasing.

### UI (`ui.py`)

PyQt6, three columns — left: classroom + date/time/lesson panel and system
metrics; center: animated HUD + `ContentPanel`; right: activity log
(`DERS KAYDI`), `FileDropZone`, mic-calibration button, text input, mute. States
shown in Turkish; internal keys unchanged. `F4` mute, `F11` fullscreen.

`ui.py` imports `core.zil` and `core.tahta` in `try/except` and keeps running with
those panels blank when `zil.json` or `derslik` is missing — a board with no
schedule configured must still teach. An unset classroom shows `DERSLİK TANIMSIZ`
in red, because a board that does not know its own class also mis-defaults the
grade in `ders_icerigi`.

**Window size is computed, never fixed.** The old hard-coded 980x700 overflowed
the screen: under HiDPI the *logical* area is far smaller than the panel size
suggests (dev machine: 2208x1242 physical → 1104x590 logical at 2x). It now takes
94% of `availableGeometry()`, clamps to a minimum, and centres on the active
screen. Don't reintroduce a fixed size — the target boards' resolutions are
unknown.

`HudCanvas` loads `Farabi.gif`, falling back to drawing the name as text.

When sweeping user-visible strings, remember `grep -i <name>` misses letter-dotted
forms like `F.A.R.A.B.İ`. Render offscreen and look:
`QT_QPA_PLATFORM=offscreen python -c "..."` → construct `MainWindow`, `w.grab().save(...)`.

### Logging — two separate streams

- **`logs/ders/YYYY-AA-GG.txt`** — the lesson record, kept locally on the board.
  **Text only; audio is never recorded.** Lines labelled ÖĞRENCİ / FARABİ /
  **ÖĞRETMEN** / SİSTEM — no student identity (one mic, can't distinguish
  students; anything spoken is ÖĞRENCİ regardless of who said it).
  Honours `FARABI_DERS_LOG_DIR`; `tests/conftest.py` points it at a temp dir
  for the same reason as `FARABI_LOG_DIR` below — a real gap until
  02.08.2026, when a test writing a real transcript line would have landed
  in the actual lesson record.
- **`logs/farabi.log`** — diagnostics, rotating 5 × 1 MB. Honours
  `FARABI_LOG_DIR`; `tests/conftest.py` points it at a temp dir so pytest runs
  stop writing "Ders adımı: …" lines into the file you read to find out what
  happened in a real lesson.

**ÖĞRETMEN is a distinct label from ÖĞRENCİ, and it did not exist until
02.08.2026.** Only *written* teacher input (panel buttons, the input box —
anything that goes out as `[ÖĞRETMEN KOMUTU] ...`) gets it; spoken input
still can't be attributed to the teacher specifically (see SINIRLARIN in
`core/prompt.txt`) and stays ÖĞRENCİ. Before this, `_on_teacher_command()`
sent the instruction to the model and showed it on the **on-screen** DERS
KAYDI panel (`ui.py`, ephemeral) but never called `transcript.log_line()` —
the persistent daily file only ever showed Farabi's resulting *response*,
never the teacher's actual instruction that caused it. Found by reading a
real lesson transcript to debug reported model misbehavior and being unable
to tell what the teacher had actually typed. Fixed in `_on_teacher_command()`
(`main.py`): logs `metin` with the `"[ÖĞRETMEN KOMUTU] "` prefix stripped
(the ÖĞRETMEN label already says that) for every teacher action, including
DURDUR/DEVAM ET, not only free-typed instructions.

The lesson record once leaked a serialized tool call and the model's **English
chain-of-thought** about a student ("Struggles with understanding…"). Two defences
now: `thinking_config(include_thoughts=False)` at the source, and
`_konusma_temizle()` which strips tool-call-shaped text. The sanitizer targets
**known tool names only** — a generic pattern would eat ordinary speech.

**A student interrupting mid-answer used to merge two turns into one unreadable
line.** `_receive_audio` (`main.py`) buffers `out_buf`/`in_buf` per turn and
only ever flushed them to the transcript on `turn_complete`. On
`server_content.interrupted` it discarded the unplayed audio queue and logged
— it did **not** flush or reset the text buffers, so a cut-off turn's partial
text just sat there and got prepended onto the **next** turn's text at the
following flush. Measured (02.08.2026, `logs/ders/2026-08-02.txt`, 11:30:22):
the teacher's "Matematik, permütasyon" landed in the same `FARABİ` line as
Farabi's previous, cut-off sentence. Fixed by flushing `in_buf`/`out_buf` to
the transcript (each in its own line, `out_buf`'s marked `(kesildi)`) and
resetting both to `[]` right in the `interrupted` branch, covered by
`tests/test_alim_dongusu_kesinti.py` against a fake, finite `session.receive()`
event sequence (no network).

### Memory — removed from the live path

`save_memory` is no longer in `actions/kayit.py`, `_execute_tool`, or the
persona tool table. `_build_config` does not inject a memory block. The
`memory/` package may still sit on disk but must stay unused: a shared classroom
board cannot hold one student profile, and "where did we leave off" continuity
confused openings. Do not re-wire it in without a concrete design for how a
board shared by ~20 students tracks one profile — that problem was never
solved, not deferred to infrastructure that doesn't exist.

### `youtube_video.py` transcript fetch — library API drift (found by running every feature, not by reading code)

`_get_transcript()` was **completely broken** — `youtube-transcript-api` isn't
version-pinned in `requirements.txt`, `pip install` pulled 1.2.4, and that
release removed the classmethod the code called
(`YouTubeTranscriptApi.list_transcripts(video_id)`) in favor of an instance
method (`YouTubeTranscriptApi().list(video_id)`); it also changed
`transcript.fetch()`'s items from dicts (`entry["text"]`) to a
`FetchedTranscriptSnippet` dataclass (`entry.text`). Every call raised
`AttributeError` and was swallowed by the function's own `except Exception`,
so `youtube_video(action="summarize", ...)` silently returned "transcript
unavailable" for **every** video — this was invisible from `_handle_summarize`'s
code alone; it only surfaced by actually calling `_get_transcript()` against a
real video ID during a "run and test every feature" pass (02.08.2026). Fixed
to the current API; `_scrape_video_info`/`get_info` (no library call, pure
HTML scraping) was never affected. Same lesson as `core/modeller.py`'s Gemini
retirement and the `kitap_index.py` fitz-ordering bug above: a dependency
silently drifting out from under unpinned code is a recurring failure class
here, not a one-off — when in doubt, actually call the function with real
input rather than trusting that unchanged code still matches its library's
current API.

## Provider notes and API quota

Gemini Live is the only realtime option and **that is now its only job in this
repo**. **Groq and OpenRouter cannot replace it for the voice path** — neither
offers realtime bidirectional audio, so switching means a second pipeline
(VAD → STT → LLM → TTS) with manual barge-in and a separate Turkish TTS
problem. **This is now the permanent decision (2026-08-11), not just a
practical stopgap** — a local voice pipeline was evaluated and explicitly
cancelled for this project (see `docs/mimari.md` §14). `main.py`'s main
session is now the **only** Gemini consumer left
(`screen_processor.py`'s vision sub-session was the second one, removed
2026-08-09 — see "Project layout"); see "API key pool" above for the key
pool it uses.

**Every non-realtime text/vision task moved to `core/saglayicilar.py`** — a
six-provider pool (Groq, Mistral, DeepSeek, OpenRouter, NVIDIA NIM; Hugging
Face deliberately excluded, its free-tier limits aren't published/predictable
enough for anything time-sensitive). All five expose an OpenAI-compatible
`/chat/completions` endpoint, so one client library (`openai`) covers all of
them — only `base_url` + `api_key` + `model` change. Consumers:

| Task (`GOREV_ZINCIRLERI` key) | Used by | Primary → fallback |
|---|---|---|
| `gorsel` | `file_processor.py` image describe/OCR/analyze (uploaded files) | Groq → NVIDIA NIM |
| `arama_sentez` | `web_search.py` (all modes), `kitap_ozet.py` enrichment | DeepSeek → (universal: OpenRouter) |
| `belge_ozet` | `file_processor.py` text tasks (PDF/docx/txt/csv/json/pptx) | DeepSeek → Mistral → (universal) |
| `video_ozet` | `youtube_video.py` transcript summary | DeepSeek → Groq → (universal) |
| `kitap_ozet` | `tools/kitap_ozet.py` book summary | NVIDIA NIM → DeepSeek → (universal) |
| `sembol_duzelt` | `tools/sembol_temizle.py` | DeepSeek → Mistral → (universal) |

"(universal)" = `openrouter/free`, OpenRouter's own auto-router — appended to
every **text** chain as a last resort (never to `gorsel`: free vision models
are unreliable enough that a failed image task should surface as a failure,
not silently degrade). A chain member with no key configured, or that raises
any exception (429, 5xx, timeout, bad model id), is skipped and the next one
tried — unlike `core/anahtar.py`'s Gemini pool, **any** exception triggers the
next provider here, not just quota-shaped ones, because each provider is a
wholly separate service; a "model not found" on Groq says nothing about
Mistral. If every provider in a chain fails, `saglayicilar.metin_uret`/
`gorsel_uret` **raises** — callers get a real exception to catch and turn
into their own "stay inside what you know, don't invent" fallback text, same
principle as `ders_icerigi`'s `_SINIRLI_DEVAM`.

**Why `screen_processor.py` was NOT migrated despite being "vision":** it
opens its own Gemini **Live** sub-session — image in, spoken audio out,
played directly through the speakers (`calisma="daemon"` in
`actions/kayit.py`, the tool that "speaks for itself"). That is realtime
voice synthesis, the same constraint as the main session; none of the five
providers do it. Only `file_processor.py`'s image actions (a photo of
homework, uploaded — text out, no speaking) are genuinely vision-to-*text*
and could move.

**Model names live in `core/saglayicilar.py`, one place, same reasoning as
`core/modeller.py`'s Gemini deprecation handling** — these providers retire
models at least as fast as Gemini did (Groq deprecated `llama-3.3-70b-
versatile` in June 2026). Verify current IDs before assuming: console.groq.com/
docs/models, api-docs.deepseek.com, docs.mistral.ai/getting-started/models,
build.nvidia.com, openrouter.ai/models. A stale model id makes that one
provider fail (caught, logged, next provider tried) — it does not need a
Gemini-style automatic-fallback layer of its own because the provider-level
fallback already covers it.

**The biggest cost lever for the voice path is not the model: it is a board
holding a live audio session all day.** Gate the session on the bell
schedule and add an idle timeout (`BOSTA_KAPATMA_DK` in `main.py`, currently
15 minutes) — an unattended board left connected burns quota for nothing.

**Getting through a full teaching day before Gemini quota runs out is a
per-board key management problem**, not a server problem — see the API key
pool section above (`core/anahtar.py`). The two things that actually stretch
a day's quota:

- **Multiple keys across separate Google Cloud projects**, not multiple keys in
  one project — a spending cap is per project, so keys sharing a project share
  one cap and rotation just fails over into the same wall faster
  (`kota_hatasi_mi()` / rotation notes above).
- **Killing idle sessions** (`BOSTA_KAPATMA_DK`) so quota is spent on lessons
  actually happening, not on a board sitting connected between periods.

There is no dashboard or budget tracker for either the Gemini pool or the
six-provider pool yet — if quota exhaustion becomes a recurring problem, the
next step is watching `farabi.log` for which provider actually rotates in a
real day and sizing the relevant pool from that measurement, not guessing.
