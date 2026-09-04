"""
actions/kayit.py — Araç kaydı (tool registry)

Bir aracın TEK kaynağı burasıdır. Gemini'ye giden bildirim (`bildirimler()`)
buradan üretilir; `main.py` artık ikinci bir liste tutmaz.

Neden: bildirim listesi ile `_execute_tool` içindeki dağıtım dalları elle
senkron tutuluyordu ve uyumu bir `grep` tek satırıyla "doğrulanıyordu". Bir
araç eklerken iki yeri birden güncellemeyi unutmak sessiz bir arıza demek:
model aracı çağırır, dağıtım tanımaz.

Kayıttaki üç alan çalışma zamanında gerçekten iş görür:

    zaman_asimi   Araç bu sürede dönmezse İPTAL EDİLİR ve modele "kaynak
                  gelmedi" yanıtı gider. Eskiden zaman aşımı hiç yoktu:
                  ölçülen 55,4 saniyelik bir `ders_icerigi` çağrısı, alım
                  döngüsünün içinde await edildiği için bütün oturumu
                  kilitliyordu (öğrenci sesi de işlenmiyordu).
    calisma       Aracın nasıl koşturulacağı. İki akış var:
                  "isci"     — iş parçacığında, zaman aşımıyla
                  "satirici" — anında, olay döngüsünde (kapanış)
    kip           Hangi ders kipinde açık. "ogretmenli"/"ogretmensiz" araçları
                  hepsi iki kipte de açık. "talimat" (öğretmen talimat modu,
                  2026-08-23) AYRI ve dışlayıcı: o kipte YALNIZCA kip'i
                  "talimat" içeren araçlar model'e bildirilir — normal ders
                  araçları (ders_icerigi, web_search, ...) o kipte hiç
                  görünmez, çünkü o modda ders anlatımı YOK. `bildirimler()`
                  bu yüzden artık bir `kip` argümanı alıyor.

`aciklama` metinleri MODELE gider ve aracın NE ZAMAN çağrılacağını anlatır.
Bunlar taşınırken tek kelimesi değiştirilmedi: metni kısaltmak, modelin aracı
kendiliğinden çağırmayı bırakmasının bilinen yoludur (bkz. CLAUDE.md, sistem
promptunun düşürüldüğü olay).
"""

from dataclasses import dataclass, field

# Ders kipleri — main.py ile aynı dizeler
KIP_HEPSI = ("ogretmenli", "ogretmensiz")

# Öğretmen talimat modu (2026-08-23) — ders YOK, öğretmen tahtayı doğrudan
# sesle yönetir. KIP_HEPSI'ye bilerek DAHİL DEĞİL: bu modda ders_icerigi,
# web_search vb. hiçbir normal ders aracı görünmemeli.
KIP_TALIMAT = "talimat"


@dataclass(frozen=True)
class Arac:
    ad: str
    aciklama: str                  # modele giden metin — BİREBİR korunur
    parametreler: dict             # Gemini şeması
    izin: str                      # erişim etiketi — henüz hiçbir yerde uygulanmıyor
    maliyet: str                   # yerel | dusuk | yuksek
    zaman_asimi: float | None      # saniye; None = uygulanmaz (satırici)
    calisma: str = "isci"          # isci | satirici
    kip: tuple = KIP_HEPSI
    cikti: str = "metin"
    gereken_baglam: tuple = field(default_factory=tuple)


ARACLAR: list[Arac] = [
    Arac(
        ad="ders_icerigi",
        aciklama=(
            "Fetches textbook pages for the subject and topic the teacher gave. "
            "Call with ders + konu (and ideally sinif) after the teacher has "
            "stated today's topic — this is the book skeleton, not the lesson "
            "frame. The frame (subject from the timetable, topic/outcome from "
            "the teacher) is already known; do NOT use this to discover which "
            "lesson it is or to invent a learning outcome from yearly plans. "
            "Prefer this over web_search for textbook content; use web_search "
            "to deepen the explanation after the book skeleton is in hand."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "liste":        {"type": "BOOLEAN", "description": "true = list indexed textbooks (optional catalogue)."},
                "ders":         {"type": "STRING",  "description": "Subject from the timetable / teacher, e.g. 'matematik'."},
                "sinif":        {"type": "STRING",  "description": "Grade, e.g. '9' or '10'."},
                "tema":         {"type": "STRING",  "description": "Theme/unit name if known."},
                "konu":         {"type": "STRING",  "description": "Topic the teacher stated — used to narrow pages."},
                "sayfa_adedi":  {"type": "INTEGER", "description": "How many pages to fetch (default 6, max 12)."},
            },
            "required": [],
        },
        izin="mufredat.oku",
        maliyet="dusuk",
        zaman_asimi=20.0,          # ölçüm: önbellekli 0,03 sn, önbelleksiz ilk tarama 11,7 sn
        cikti="markdown",
    ),
    Arac(
        ad="kitap_sorusu",
        aciklama=(
            "Answers a concrete question against the textbook via the server's "
            "RAG pipeline (retrieval + rerank + threshold + LLM + number-check) — "
            "NOT a topic walkthrough. Call this when a student or teacher asks a "
            "specific factual question 'kitapta ne yazıyor', 'kitaba göre', or "
            "any question that should be answered strictly from the book with a "
            "citable source. Do NOT use this to fetch pages for explaining a "
            "topic — that is ders_icerigi's job. The answer is already source- "
            "checked by the server: read it back as given, do not add or "
            "invent anything beyond it. If the server has no matching book or "
            "is unreachable, this returns a limiting instruction — follow it "
            "silently, do not tell the class about a technical problem."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "soru":  {"type": "STRING", "description": "The student's/teacher's exact question."},
                "ders":  {"type": "STRING", "description": "Subject from the timetable, e.g. 'biyoloji'. REQUIRED — without it the tool refuses to guess a book (avoids answering a physics question from the biology book)."},
                "sinif": {"type": "STRING", "description": "Grade, e.g. '9' or '10'."},
            },
            "required": ["soru", "ders"],
        },
        izin="mufredat.oku",
        maliyet="dusuk",
        zaman_asimi=16.0,          # server'ın kendi GET(5s)+POST(10s) toplamı + pay
        # Öğretmen talimat modunda da açık (2026-08-23, gerçek sınıf testi
        # sonrası eklendi — öğretmen kitaba dayalı tek soru bekliyordu) —
        # tek soruya kaynaklı tek cevap, ders anlatımı değil; pdf_sayfa/
        # yks_sorulari ile aynı gerekçe.
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="metin",
    ),
    Arac(
        ad="pdf_sayfa",
        aciklama=(
            "Shows one SPECIFIC page number from the current textbook on "
            "screen, as an IMAGE — the original PDF layout is preserved "
            "(diagrams, tables, formulas stay intact, nothing is reflowed "
            "into text). Call when the teacher or a student asks to see a "
            "specific page, e.g. '9. sayfayı göster/yansıt', 'kitabın 15. "
            "sayfasını aç'. No topic/theme matching happens here — this is "
            "purely a page-number lookup. Do NOT use this for topic "
            "narration (that's ders_icerigi) or answering a question "
            "(that's kitap_sorusu). The tool result now also includes the "
            "page's real text when available (labeled SAYFA METNİ) — base "
            "any narration strictly on that text, never invent page content "
            "if it's missing."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "sayfa": {"type": "INTEGER", "description": "The PDF page number to show (1-indexed)."},
                "ders":  {"type": "STRING",  "description": "Subject from the timetable, e.g. 'biyoloji'. REQUIRED — without it the tool refuses to guess a book."},
                "sinif": {"type": "STRING",  "description": "Grade, e.g. '9' or '10'."},
            },
            "required": ["sayfa", "ders"],
        },
        izin="mufredat.oku",
        maliyet="dusuk",
        zaman_asimi=10.0,          # yerel PDF render — ölçüm: önbelleksiz ilk çağrı 131,7 ms (biyoloji-9 s.9)
        # Öğretmen talimat modunda da açık ("fizik kitabının 45. sayfasını
        # aç" birebir bu araç) — ders_icerigi gibi TÜM kitabı gezinme değil,
        # tek sayfa lookup olduğu için o modun "ders anlatımı yok" kuralını
        # ihlal etmiyor.
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="gorsel",
    ),
    Arac(
        ad="yks_sorulari",
        aciklama=(
            "Fetches past YKS (TYT/AYT) exam questions on the current topic from "
            "a local archive of past exam papers (offline-indexed, keyword-matched — "
            "NOT web search). Call when the teacher or a student asks for 'çıkmış "
            "sorular', 'YKS soruları', 'TYT/AYT sorusu' about the topic being taught. "
            "Shows the ACTUAL exam page as an IMAGE (original PDF layout preserved, "
            "not reflowed text) and returns the raw question text for you to read "
            "aloud — it contains NO solution and NO answer key. "
            "ONE QUESTION AT A TIME: call with 'konu' (+ideally 'ders') to start a "
            "new sequence — this shows only the FIRST matching question, even if "
            "more matched. After calling: read the question and its answer choices "
            "aloud (it is already shown on screen as an image), then STOP and wait — "
            "ask the class for their answer, or wait for a teacher instruction, "
            "before explaining anything. Do NOT solve it yourself immediately. "
            "NEVER move to the next matched question on your own — only when the "
            "teacher explicitly says so (aloud with your name, or via the written "
            "teacher panel, or something like 'sıradaki soru'), call again with "
            "sonraki=true and NO 'konu' to advance within the SAME sequence. "
            "Calling with a new 'konu' always starts a fresh sequence. If the "
            "archive isn't prepared yet or nothing matches, say so plainly and "
            "keep teaching from the textbook — do NOT invent a question."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "konu":     {"type": "STRING",  "description": "Topic to search for, e.g. 'türev', 'osmanlı-rus savaşları'. Start (or restart) a sequence."},
                "ders":     {"type": "STRING",  "description": "Subject, improves matching, e.g. 'matematik'."},
                "adet":     {"type": "INTEGER", "description": "How many questions to match into the sequence (default 3, max 6) — only used when starting a new sequence with 'konu'; ignored on sonraki=true calls."},
                "sonraki":  {"type": "BOOLEAN", "description": "true = advance to the NEXT question in the current sequence (omit 'konu'). Only on an explicit teacher command — never on your own initiative."},
            },
            "required": [],
        },
        izin="sinav.oku",
        maliyet="dusuk",
        zaman_asimi=15.0,
        # Öğretmen talimat modunda da açık ("yks ingilizce 2024 sorularını
        # göster" birebir bu araç) — tek soru gösterme, ders anlatımı değil.
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="metin",
    ),
    Arac(
        ad="ders_hafizasi",
        aciklama=(
            "Recalls what was covered in a PAST lesson on this board — 'geçen ders "
            "ne işlemiştik', 'nereye kadar gelmiştik' style questions. Reads Farabi's "
            "OWN local lesson records (logs/ders/*.txt on this board), NOT the "
            "textbook and NOT the server RAG — do not confuse with ders_icerigi "
            "(textbook topic walkthrough) or kitap_sorusu (sourced Q&A against the "
            "book). Call with 'konu' (+ optionally 'ders') to find a specific past "
            "topic; call with NEITHER to recall the most recent past lesson in "
            "general. Never recalls the CURRENT lesson (excluded automatically). "
            "Returns the raw past transcript for you to paraphrase into a short, "
            "conversational 2-3 sentence reminder — do NOT read it verbatim to the "
            "class. Not a presented question, answer immediately, no waiting/silence "
            "protocol. If there's no matching (or no) past lesson yet, say so "
            "plainly — do NOT invent what a past lesson covered."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "konu": {"type": "STRING", "description": "Topic to recall, e.g. 'hücre zarı'. Omit for 'what was our last lesson' in general."},
                "ders": {"type": "STRING", "description": "Subject, improves matching, e.g. 'biyoloji'. Optional."},
            },
            "required": [],
        },
        izin="gecmis.oku",
        maliyet="dusuk",
        zaman_asimi=10.0,
        cikti="metin",
    ),
    Arac(
        ad="site_goster",
        aciklama=(
            "Shows content from an approved reference website on the board. "
            "Use for dictionary definitions (TDK), encyclopedia articles "
            "(Wikipedia), official curriculum pages (MEB, EBA, and its "
            "ogmmateryal.eba.gov.tr materials portal), statistics (TÜİK), "
            "weather data (MGM), history sources (TTK), and — when the "
            "teacher asks for exam-prep material (LGS/YKS topic summaries or "
            "past questions) — mebi.eba.gov.tr; note only its text/menu "
            "content comes through, not its lecture videos (this tool shows "
            "no video, see below). "
            "Give either a full URL or just a search term — a term is looked up "
            "on Turkish Wikipedia. "
            "ONLY whitelisted domains work; anything else is refused, so do not "
            "promise the class you will open an arbitrary site. This returns "
            "cleaned TEXT, not a live page: interactive content, embedded video "
            "and simulations cannot be shown this way — use youtube_video for "
            "video. Prefer ders_icerigi for textbook content; use this when the "
            "class needs a definition or a reference source."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "url":   {"type": "STRING", "description": "Full address of the approved page."},
                "arama": {"type": "STRING", "description": "Term to look up on Turkish Wikipedia if no URL is given."},
            },
            "required": [],
        },
        izin="kaynak.site",
        maliyet="dusuk",
        zaman_asimi=10.0,
        cikti="metin",
    ),
    Arac(
        ad="file_processor",
        aciklama=(
            "Processes a document or image the teacher or student dropped onto the "
            "board. Handles PDF lecture notes and worksheets (summarize/extract_text), "
            "Word and text documents (summarize/fix/reformat), images of handwritten "
            "work (describe/ocr), spreadsheets (analyze/stats), presentations "
            "(summarize), and JSON/XML data. "
            "Audio, video, archives and source code are NOT supported — deliberately, "
            "since they are not classroom material. "
            "ALWAYS call this when a file has been uploaded and a command is given "
            "about it. If the command is ambiguous, pick the most useful action for "
            "studying that file type — usually 'summarize'."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file.",
                },
                "action": {
                    "type": "STRING",
                    "description": (
                        "What to do with the file. Examples by type:\n"
                        "image: describe | ocr | info\n"
                        "pdf: summarize | extract_text | to_word | info\n"
                        "docx/txt: summarize | fix | reformat | word_count | to_bullet\n"
                        "csv/excel: analyze | stats | filter | sort | info\n"
                        "json/xml: validate | format | analyze\n"
                        "pptx: summarize | extract_text | analyze"
                    ),
                },
                "instruction": {
                    "type": "STRING",
                    "description": "Free-form instruction. E.g. 'bu konuyu lise seviyesinde özetle', 'sadece formülleri çıkar'",
                },
                "format":    {"type": "STRING",  "description": "Target format for conversion. E.g. 'pdf', 'csv', 'png'"},
                "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
                "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
                "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
                "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
                "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            },
            "required": [],
        },
        izin="dosya.oku",
        maliyet="yuksek",
        zaman_asimi=45.0,          # büyük PDF özeti uzun sürer; sınıf bunu bekleyerek yapar
        cikti="metin",
    ),
    Arac(
        ad="web_search",
        aciklama=(
            "Searches the web. Use when the student asks about a fact, date, formula, "
            "definition, current event, or anything you are not certain about — "
            "ALWAYS prefer searching over guessing. Accuracy matters more than speed "
            "when teaching. "
            "Modes: 'search' (default), 'news' (current events for history/geography), "
            "'research' (deep comprehensive answer for a topic explanation), "
            "'compare' (side-by-side comparison of two concepts)."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Concepts to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect"},
            },
            "required": ["query"],
        },
        izin="ag.arama",
        maliyet="yuksek",
        zaman_asimi=20.0,
        cikti="metin",
    ),
    Arac(
        ad="youtube_video",
        aciklama=(
            "Finds or summarizes educational videos. Use when a topic is easier shown "
            "than told, when the student asks for a konu anlatım video, or when they "
            "want a video they are watching summarized."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action, e.g. 'türev konu anlatımı'"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to a file (summarize only)"},
                "url":    {"type": "STRING", "description": "Video URL for summarize/get_info action"},
            },
            "required": [],
        },
        izin="ag.video",
        maliyet="yuksek",
        zaman_asimi=30.0,
        cikti="metin",
    ),
    Arac(
        ad="eba",
        aciklama=(
            "Opens EBA (Eğitim Bilişim Ağı, the official MEB education portal) "
            "content — lesson videos and question/worksheet PDFs. Use 'video' when "
            "the teacher or student wants an EBA konu anlatım video, and 'pdf' when "
            "they give an EBA link to a question sheet or document. "
            "Only eba.gov.tr links are accepted — refuses anything else. "
            "Prefer this over youtube_video specifically when EBA is named or an "
            "eba.gov.tr link is given."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "video | pdf (default: video)"},
                "query":  {"type": "STRING", "description": "Topic to search for (video action, when no direct URL is known)"},
                "url":    {"type": "STRING", "description": "Direct eba.gov.tr URL — required for pdf action, optional for video"},
            },
            "required": [],
        },
        izin="ag.video",
        maliyet="yuksek",
        zaman_asimi=30.0,
        cikti="metin",
    ),
    Arac(
        ad="web_ac",
        aciklama=(
            "ÖĞRETMEN TALİMAT MODU ONLY. Opens a REAL web browser to a site "
            "or URL — 'internet aç', 'google aç', 'eba.gov.tr aç', 'youtube "
            "aç'. Call once per single-sentence command, then confirm in "
            "ONE short sentence — do not explain, do not start teaching."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "hedef": {"type": "STRING", "description": "Site name, domain or URL, e.g. 'google', 'eba.gov.tr', 'youtube'."},
            },
            "required": ["hedef"],
        },
        izin="sistem.tarayici",
        maliyet="yerel",
        zaman_asimi=8.0,
        kip=(KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="uygulama_ac",
        aciklama=(
            "ÖĞRETMEN TALİMAT MODU ONLY. Launches a known desktop app — "
            "'pardus kalem uygulamasını aç', 'çizim uygulamasını aç', 'dosya "
            "yöneticisini aç'. Only a small fixed set of apps is recognized; "
            "if unsure ask the teacher to name one of the known ones rather "
            "than guessing."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "uygulama": {"type": "STRING", "description": "App name as the teacher said it, e.g. 'kalem', 'çizim', 'dosya yöneticisi'."},
            },
            "required": ["uygulama"],
        },
        izin="sistem.uygulama",
        maliyet="yerel",
        zaman_asimi=8.0,
        kip=(KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="dosya_ac",
        aciklama=(
            "ÖĞRETMEN TALİMAT MODU ONLY. Opens a folder or a specific file "
            "by name under the board's home directory — 'ev dizinini aç', "
            "'atakan.pdf dosyasını aç', '9.21.mp3 dosyasını çal'. xdg-open "
            "picks the right app (PDF viewer, media player, ...) automatically."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "hedef": {"type": "STRING", "description": "Folder keyword (e.g. 'ev dizini', 'masaüstü') or a file name (e.g. '9.21.mp3', 'atakan.pdf')."},
            },
            "required": ["hedef"],
        },
        izin="sistem.dosya",
        maliyet="yerel",
        zaman_asimi=10.0,
        kip=(KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="pencere_kapat",
        aciklama=(
            "ÖĞRETMEN TALİMAT MODU ONLY. Closes an open window/app by matching "
            "its title — 'youtube'u kapat', 'çizim uygulamasını kapat', "
            "'tarayıcıyı kapat'. Works for anything opened by web_ac/"
            "uygulama_ac, including browser windows (title match, not process "
            "tracking — a browser tab usually hands off to an already-running "
            "browser process, so tracking the launch PID would not work)."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "hedef": {"type": "STRING", "description": "Words expected in the window's title, e.g. 'youtube', 'çizim', 'chrome'."},
            },
            "required": ["hedef"],
        },
        izin="sistem.pencere",
        maliyet="yerel",
        zaman_asimi=8.0,
        kip=(KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="talimat_modundan_cik",
        aciklama=(
            "ÖĞRETMEN TALİMAT MODU ONLY. Exits command-only mode and returns "
            "to a normal taught lesson — 'öğretmen talimat modundan çık', "
            "'normal derse dön'. Call this ONLY on an explicit request to "
            "leave the mode, never on your own initiative."
        ),
        parametreler={"type": "OBJECT", "properties": {}},
        izin="sistem.mod",
        maliyet="yerel",
        zaman_asimi=None,
        calisma="satirici",
        kip=(KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="ekran_goruntusu_al",
        aciklama=(
            "Takes a screenshot of the board's OWN screen (whatever is "
            "currently shown — a book page, content panel text, etc.) and "
            "adds it to the lesson log. NOT a camera — this board has no "
            "camera hardware, this only captures the on-screen display "
            "itself. Call when the teacher explicitly asks to save/log what "
            "is currently on screen, e.g. 'ekran görüntüsü al', 'bunu "
            "kaydet'."
        ),
        parametreler={"type": "OBJECT", "properties": {}},
        izin="ekran.yakala",
        maliyet="yerel",
        zaman_asimi=8.0,
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="onay",
    ),
    Arac(
        ad="ekrandaki_soruyu_oku",
        aciklama=(
            "Captures the board's OWN screen (not a camera — this board has "
            "none) and reads/solves/explains whatever question or content is "
            "currently displayed, via cloud OCR. Call when the teacher or a "
            "student asks about 'ekrandaki soru/yazı/görsel' without it "
            "coming from ders_icerigi/pdf_sayfa/kitap_sorusu (e.g. something "
            "manually opened, drawn, or pasted on screen). Prefer "
            "kitap_sorusu/ders_icerigi for textbook content — this is for "
            "reading whatever is ACTUALLY on screen right now, sight-unseen."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "talimat": {"type": "STRING", "description": "What to do with what's read, e.g. 'çöz ve açıkla', 'özetle'. Defaults to reading, solving, and explaining."},
            },
            "required": [],
        },
        izin="ekran.yakala",
        maliyet="dusuk",
        zaman_asimi=45.0,
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="metin",
    ),
    Arac(
        ad="yoklama_al",
        aciklama=(
            "Opens the board's external, touch-based attendance app "
            "(tahtayoklama) at the very start of a lesson, alongside the "
            "spoken roll call. Fire-and-forget — do not wait for or narrate "
            "a result beyond the confirmation text returned. Call this once, "
            "right when you begin YOKLAMA (the lesson's first step), not "
            "later and not more than once per lesson."
        ),
        parametreler={"type": "OBJECT", "properties": {}},
        izin="uygulama.baslat",
        maliyet="yerel",
        zaman_asimi=5.0,
        cikti="onay",
    ),
    Arac(
        ad="shutdown_farabi",
        aciklama=(
            "Ends the CURRENT LESSON and returns the board to its "
            "pre-lesson waiting state — the process itself stays running; "
            "the teacher presses DERSİ BAŞLAT again for the next lesson. "
            "Call this when the student says goodbye, wants to stop studying, "
            "or asks to close the app. The student can say this in ANY language."
        ),
        parametreler={"type": "OBJECT", "properties": {}},
        izin="oturum.kapat",
        maliyet="yerel",
        zaman_asimi=None,
        calisma="satirici",
        cikti="onay",
    ),
    Arac(
        ad="gorsel_uret",
        aciklama=(
            "Generates an educational image/diagram for the given topic and "
            "shows it on screen. Fire-and-forget — runs in the background "
            "after this call returns, do not wait for or narrate a result "
            "beyond the confirmation text; the board announces separately "
            "when the image is ready. Requires 'konu' (topic); never guess "
            "it if the teacher/student didn't give one, ask instead. Use "
            "sparingly — this is a slow, paid generation call, not a "
            "substitute for pdf_sayfa/ders_icerigi textbook content."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "konu": {"type": "STRING", "description": "What to draw/generate an image about."},
            },
            "required": ["konu"],
        },
        izin="gorsel.uret",
        maliyet="yuksek",
        zaman_asimi=None,
        calisma="satirici",
        cikti="onay",
    ),
]

_HARITA = {a.ad: a for a in ARACLAR}


def bildirimler(kip: str | None = None) -> list[dict]:
    """
    Gemini'ye giden araç bildirimleri — kayıttan üretilir.

    `kip` verilmezse (main.py'nin başlangıç banner'ı / araç sayısı logu gibi
    bilgilendirme amaçlı çağrılarda) TÜM araçlar döner, filtre uygulanmaz.
    `kip` verilirse yalnızca `kip in a.kip` olan araçlar döner — oturuma
    fiilen giden liste bu şekilde hesaplanır (bkz. main.py._build_config).
    """
    return [
        {"name": a.ad, "description": a.aciklama, "parameters": a.parametreler}
        for a in ARACLAR
        if kip is None or kip in a.kip
    ]


def bul(ad: str) -> Arac | None:
    return _HARITA.get(ad)


def adlar() -> list[str]:
    return [a.ad for a in ARACLAR]


def zaman_asimi(ad: str, varsayilan: float = 15.0) -> float | None:
    a = _HARITA.get(ad)
    return varsayilan if a is None else a.zaman_asimi


def kipte_acik(ad: str, kip: str) -> bool:
    a = _HARITA.get(ad)
    return True if a is None else (kip in a.kip)
