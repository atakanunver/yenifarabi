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
    kip           Hangi ders kipinde açık. Şimdilik hepsi iki kipte de açık.

`aciklama` metinleri MODELE gider ve aracın NE ZAMAN çağrılacağını anlatır.
Bunlar taşınırken tek kelimesi değiştirilmedi: metni kısaltmak, modelin aracı
kendiliğinden çağırmayı bırakmasının bilinen yoludur (bkz. CLAUDE.md, sistem
promptunun düşürüldüğü olay).
"""

from dataclasses import dataclass, field

# Ders kipleri — main.py ile aynı dizeler
KIP_HEPSI = ("ogretmenli", "ogretmensiz")


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
                "ders":  {"type": "STRING", "description": "Subject from the timetable, e.g. 'biyoloji'."},
                "sinif": {"type": "STRING", "description": "Grade, e.g. '9' or '10'."},
            },
            "required": ["soru"],
        },
        izin="mufredat.oku",
        maliyet="dusuk",
        zaman_asimi=8.0,           # server'ın kendi 5sn timeout'u + pay
        cikti="metin",
    ),
    Arac(
        ad="yks_sorulari",
        aciklama=(
            "Fetches past YKS (TYT/AYT) exam questions on the current topic from "
            "a local archive of past exam papers (offline-indexed, keyword-matched — "
            "NOT web search). Call when the teacher or a student asks for 'çıkmış "
            "sorular', 'YKS soruları', 'TYT/AYT sorusu' about the topic being taught. "
            "The returned text is the RAW question only, taken from the exam PDF — "
            "it contains NO solution and NO answer key. After calling: read the "
            "question and its answer choices aloud (it is already shown on screen), "
            "then STOP and wait — ask the class for their answer, or wait for a "
            "teacher instruction, before explaining anything. Do NOT solve it "
            "yourself immediately; this is a quiz-style check, not a worked example "
            "to narrate. Only once a student answers or the teacher gives an "
            "instruction do you work through the solution step by step. If the "
            "archive isn't prepared yet or nothing matches, say so plainly and keep "
            "teaching from the textbook — do NOT invent a question."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "konu": {"type": "STRING", "description": "Topic to search for, e.g. 'türev', 'osmanlı-rus savaşları'."},
                "ders": {"type": "STRING", "description": "Subject, improves matching, e.g. 'matematik'."},
                "adet": {"type": "INTEGER", "description": "How many question pages to fetch (default 3, max 6)."},
            },
            "required": ["konu"],
        },
        izin="sinav.oku",
        maliyet="dusuk",
        zaman_asimi=15.0,
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
        ad="shutdown_farabi",
        aciklama=(
            "Ends the session and closes the assistant completely. "
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
]

_HARITA = {a.ad: a for a in ARACLAR}


def bildirimler() -> list[dict]:
    """Gemini'ye giden araç bildirimleri — kayıttan üretilir."""
    return [
        {"name": a.ad, "description": a.aciklama, "parameters": a.parametreler}
        for a in ARACLAR
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
