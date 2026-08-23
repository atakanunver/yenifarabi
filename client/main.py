# Hazırlayan: MEB Atakan ÜNVER

import asyncio
import re
import threading
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import FarabiUI
from core import transcript, zil, tahta, anahtar, olaylar, program
from core.ders_motoru import DersMotoru
from core.logger import get_logger, log_path

log = get_logger("main")

from actions import kayit
from actions.ders_icerigi     import ders_icerigi
from actions.kitap_sorusu     import kitap_sorusu
from actions.pdf_sayfa         import pdf_sayfa
from actions.yks_sorulari      import yks_sorulari
from actions.ders_hafizasi     import ders_hafizasi
from actions.file_processor    import file_processor
from actions.site_goster      import site_goster
from actions.youtube_video     import youtube_video
from actions.eba               import eba
from actions.web_search        import web_search as web_search_action
from actions.web_ac            import web_ac
from actions.uygulama_ac       import uygulama_ac
from actions.dosya_ac          import dosya_ac


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
from core import modeller
LIVE_MODEL          = modeller.CANLI_MODEL
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    # Anahtar havuzu core/anahtar.py'de — kota dolunca oturum sıradakine geçer.
    # Buradan da aynı havuzu okumak ŞART: yoksa oturum yeni anahtara geçerken
    # bu modül ölü anahtarı kullanmaya devam eder.
    from core import anahtar
    return anahtar.simdiki()


# Ders kipleri. Bazı derslerde sınıfta insan öğretmen var (Farabi yardımcı),
# bazılarında yok (etüt, telafi, boş ders — Farabi tek öğretmen). Kip
# davranışı ve tonu değiştirdiği için sisteme açıkça bildirilir.
KIP_OGRETMENLI  = "ogretmenli"
KIP_OGRETMENSIZ = "ogretmensiz"

# Öğretmen talimat modu (2026-08-23) — ders YOK. Öğretmen tahtayı, ders
# anlatımı/sınıf yönetimi olmadan, doğrudan TEK CÜMLELİK sesli komutlarla
# yönetir ("google aç", "fizik kitabının 45. sayfasını aç" gibi). ui.py'de
# DERSİ BAŞLAT'ın altındaki düğmeyle seçilir, açılışta varsayılan seçili
# gelir (ui.py'nin kendi notuna bkz). KIP_OGRETMENLI/SIZ'ın aksine
# `_ders_kipi()` bunu ASLA döndürmez — yalnızca `ui.talimat_modu` üzerinden,
# `_build_config()` içinde bağlantı anında uygulanır (ders_dili ile aynı
# "DERSİ BAŞLAT'tan önce seçilir, sonra kilitlenir" deseni).
KIP_TALIMAT = "talimat"

# Talimat modunun TÜM sistem promptu bu — core/prompt.txt'nin (26K, tam
# öğretmenlik personası) yerini TAMAMEN alır, eklenmez. Ders çerçevesi,
# derslik, ders kipi bloğu ve dil yönergesi de BİLEREK yok: bu modda ders
# yok, tek iş sesli komutu doğru araca yönlendirmek.
_TALIMAT_PERSONASI = (
    "Sen Farabi'sin. Şu anda ÖĞRETMEN TALİMAT MODUNDASIN.\n\n"
    "Bu modda DERS ANLATMAZSIN, SORU SORMAZSIN, YOKLAMA ALMAZSIN, sohbet "
    "etmezsin, konuyu açıklamazsın. Tek işin: öğretmenin söylediği TEK "
    "CÜMLELİK sesli komutu dinleyip en uygun aracı çağırmak. Örnekler: "
    "'internet aç', 'google aç', 'eba.gov.tr aç', 'youtube aç', "
    "'9.21.mp3 dosyasını çal', 'atakan.pdf dosyasını aç', 'pardus kalem "
    "uygulamasını aç', 'çizim uygulamasını aç', 'ev dizinini aç', "
    "'fizik kitabının 45. sayfasını aç', 'yks ingilizce 2024 sorularını "
    "göster'.\n\n"
    "KURALLAR:\n"
    "- Bir araç çağırdıktan sonra EN FAZLA tek kısa cümleyle onay ver "
    "(\"Açılıyor.\", \"Tamam.\") — açıklama yapma, ders anlatmaya başlama.\n"
    "- Komutu anlamadıysan ya da hangi aracın uygun olduğundan emin "
    "değilsen, tek cümlelik netleştirme sorusu sor — ASLA tahmin edip "
    "yanlış bir şey açma.\n"
    "- Araç çağırıp onaylamak dışında hiçbir şey yapma: ders anlatma, soru "
    "sorma, yorum yapma, sohbet etme, konuya giriş yapma.\n"
    "- Her zaman Türkçe konuş.\n"
)

# Bu kadar dakika hiç konuşma/öğretmen girdisi olmazsa ders kaydı kapatılıp
# çıkılır. Canlı ses oturumu açık kaldığı sürece ücretli; unutulmuş bir tahta
# bütün geceyi bağlı geçirir.
BOSTA_KAPATMA_DK = 15


def _ders_kipi() -> str:
    """
    O anki ders kipini döndür. Ders programından, yoksa config'ten okunur.

    Varsayılan ÖĞRETMENLİ (kullanıcı kararı): tipik ders 1 öğretmen +
    yaklaşık 20 öğrenci. Etüt, telafi ve boş ders gibi öğretmensiz saatler
    için config'e açıkça "ders_kipi": "ogretmensiz" yazılır.
    """
    # Önce DERS PROGRAMI: etüt, telafi ve boş dersler programda işaretlidir
    # ve kip oradan türer. Her hafta config dosyası düzenlemek yerine
    # program bir kez yazılır.
    try:
        kip_slot = program.kip()
        if kip_slot in (KIP_OGRETMENLI, KIP_OGRETMENSIZ):
            log.info("Ders kipi programdan alındı: %s", kip_slot)
            return kip_slot
    except Exception as e:
        log.debug("Ders programı kipi okunamadı: %s", e)

    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            kip = str(json.load(f).get("ders_kipi", "")).strip().lower()
        return KIP_OGRETMENSIZ if kip == KIP_OGRETMENSIZ else KIP_OGRETMENLI
    except Exception:
        return KIP_OGRETMENLI


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Sen Farabi'sin — sınıftaki akıllı tahtada çalışan yapay zekâ "
            "öğretmensin. Her zaman Türkçe konuş. Cevabı doğrudan vermek yerine "
            "öğrenciyi adım adım düşündür. Emin olmadığın bilgiyi tahmin etme, "
            "web_search ile doğrula."
        )


_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

# Ders kaydı ve ekran logu için gürültü temizliği.
#
# Neden gerekli: 30.07.2026'da gerçek bir derste ders kaydına şunlar sızdı —
# serileşmiş araç çağrısı ve modelin İngilizce iç muhakemesi
# ("thought  The user replied 'Bilmem'..."). Ders kaydı okulun resmî kaydı;
# içine araç içleri girmemeli. Persona da talimatların öğrenciye
# açıklanmamasını söylüyor.
#
# İlk savunma thinking_config.include_thoughts=False (kaynakta keser); bu
# temizleyici ikinci savunma, araç çağrısı sızıntısı için.
_TOOL_ADLARI: list[str] = []          # araç listesi tanımlandıktan sonra doldurulur
_ARAC_RE: re.Pattern | None = None
_THOUGHT_RE = re.compile(r"\bthought\b\s*", re.IGNORECASE)

# Sisteme verilen etiketler SINIFA OKUNMAMALI. 31.07.2026 ders kaydı:
#   "FARABİ  [DERS_ACILISI] Merhaba çocuklar. Bugün 31 Temmuz Cuma..."
# Model, kendisine verilen talimat etiketini cümlenin başında sesli olarak
# tekrarlıyor. İlk savunma promptta ("etiketi okuma"), bu ikinci savunma.
_ETIKET_RE = re.compile(
    r"\[(?:DERS_ACILISI|DERS DURUMU|ÖĞRETMEN KOMUTU|OTURUM DEVAM|"
    r"CURRENT DATE & TIME|DERSLİK|DERS KİPİ[^\]]*)\]\s*",
    re.IGNORECASE)


def _arac_gurultu_deseni() -> re.Pattern:
    """Yalnızca BİLİNEN araç adlarını hedefle — genel bir desen konuşmayı yer."""
    global _ARAC_RE
    if _ARAC_RE is None:
        adlar = "|".join(re.escape(a) for a in _TOOL_ADLARI) or r"(?!x)x"
        _ARAC_RE = re.compile(rf"\b(?:{adlar})\s*\{{[^{{}}]*\}}", re.IGNORECASE)
    return _ARAC_RE


def _konusma_temizle(text: str) -> str:
    """Söylenen sözü ayıkla: araç çağrıları ve düşünce işaretleri çıkar."""
    if not text:
        return ""
    text = _arac_gurultu_deseni().sub(" ", text)
    text = _THOUGHT_RE.sub(" ", text)
    text = _ETIKET_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


# Zil çizelgesi ve ders saati mantığı core/zil.py'de — ui.py de aynı bilgiyi
# sol panelde gösteriyor ve main.py'ı import edemez (döngüsel bağımlılık).
GUN_ADLARI = zil.GUN_ADLARI
_greeting_for_hour = zil.selam


def _ders_saati_durumu(simdi: datetime) -> str:
    """Modele verilecek ders saati cümlesi. Çizelge yoksa boş döner."""
    return zil.ders_durumu(simdi).get("metin", "")


# ── Ders dili — açılış konuşmasının VERBATIM kısımları için ────────────────
# core/zil.py bilerek Türkçe kalır (HUD panelini de besliyor); ders açılışı
# ayrı bir tüketici, burada çözülür. Yalnız "aynen şu olsun" diye modele
# VERİLEN sabit cümleler için gerekli — geri kalan açılış talimatları
# Türkçe kalabilir, model _build_config()'teki dil direktifiyle zaten hedef
# dilde konuşmaya yönlendiriliyor (bkz. "Ders dili" bloğu).
_GUN_ADLARI_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]
_GUN_ADLARI_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                 "Samstag", "Sonntag"]


def _acilis_selam_gun(ders_dili: str, simdi: datetime) -> tuple[str, str]:
    saat = simdi.hour
    if ders_dili == "en":
        selam = "Good morning" if 5 <= saat < 12 else \
                "Good afternoon" if saat < 18 else "Good evening"
        return selam, _GUN_ADLARI_EN[simdi.weekday()]
    if ders_dili == "de":
        selam = "Guten Morgen" if 5 <= saat < 12 else \
                "Guten Tag" if saat < 18 else "Guten Abend"
        return selam, _GUN_ADLARI_DE[simdi.weekday()]
    return _greeting_for_hour(saat), GUN_ADLARI[simdi.weekday()]


# Araç bildirimleri TEK KAYNAKTAN gelir: actions/kayit.py.
# Eskiden bu dosyada uzun bir liste vardı ve `_execute_tool` içindeki dağıtım
# dallarıyla elle senkron tutuluyordu; uyumu bir grep tek satırı kontrol
# ediyordu. Kayıt ayrıca her araca zaman aşımı, izin ve maliyet sınıfı verir —
# zaman aşımı olmadığı için ölçülen 55 sn'lik bir çağrı bütün oturumu
# kilitleyebiliyordu.
TOOL_DECLARATIONS = kayit.bildirimler()

_TOOL_ADLARI = kayit.adlar()

# --- Plugin system ---


class FarabiLive:

    def __init__(self, ui: FarabiUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command  = self._on_text_command
        self.ui.on_teacher_command = self._on_teacher_command
        self._turn_done_event: asyncio.Event | None = None
        self._briefing_sent = False          # ders açılışı süreç başına bir kez
        # YouTube videosu açılınca mikrofon otomatik kapatılır (bkz.
        # `_video_icin_duraklat`); DEVAM ET bunu da geri açmalı, yoksa
        # öğretmen video bitince mikrofonu ayrıca elle açmak zorunda kalır.
        self._video_yuzunden_susturuldu = False
        # Oturumu öğretmen başlatır; olay run() içinde kurulur (loop gerekiyor).
        self._oturum_izni: asyncio.Event | None = None
        # time.monotonic() DEĞİL — cihaz uyku/askıya alma modundan uyandığında
        # CLOCK_MONOTONIC askıda geçen süreyi saymaz, _boşta_gozcusu uzun bir
        # uykuyu hiç göremezdi (bkz. _boşta_gozcusu docstring'i).
        self._son_etkinlik = time.time()
        self._kapaniyor    = False
        # O anki ders çerçevesi. Ders ADI programdan gelir; konu ve kazanım
        # öğretmenin yazdığı/söylediği metinden. Yıllık plan (Excel→plan.json)
        # oturum çerçevesini doldurmaz — plandan otomatik kazanım tespiti yok.
        self._program_slotu = None
        self._current_lesson: dict | None = None
        try:
            self._program_slotu = program.simdiki_ders()
        except Exception as e:
            log.error("Ders programı okunamadı: %s", e)

        if self._program_slotu:
            self._current_lesson = self._programdan_cerceve(self._program_slotu)

        # Ders kipi: sınıfta insan öğretmen var mı?
        self._ders_kipi = _ders_kipi()

        # Ders motoru GÖZLEMCİ kipinde: adımı, kalan süreyi ve önerileri
        # hesaplar, loglar ve arayüze yazar; oturuma HİÇBİR ŞEY göndermez
        # (`enjekte=False`). Ders akışına müdahale eden bir değişikliği önce
        # gerçek derste izlemek, sonra açmak gerekir — bkz. core/ders_motoru.py.
        # ENJEKSİYON AÇIK. Karar: dersi sanal öğretmen planlayıp anlatacak,
        # öğretmenin sürekli müdahalesine gerek kalmayacak. Bunun ön şartı
        # modelin SAATİ BİLMESİ: [CURRENT DATE & TIME] oturum başına bir kez
        # kuruluyor ve dakikalar akmıyor. Motor, kalan süreyi ve adımı
        # değiştikçe oturuma bildirir; 40 dakikalık planı model buna göre kurar.
        self.motor = DersMotoru(
            kip=self._ders_kipi,
            cerceve=self._current_lesson,
            sinif=tahta.derslik(),
            enjekte=True,
        )

    def _on_teacher_command(self, anahtar: str, metin: str,
                            veri: dict | None = None) -> None:
        """
        Öğretmen paneli ve yazılı giriş → oturuma talimat.

        Sınıfta klavye tahtanın başında durur; yazan kişi öğretmendir. Bu
        yüzden metin [ÖĞRETMEN KOMUTU] etiketiyle gider ve persona onu
        pedagojik varsayılanların ÜSTÜNDE tutar (core/prompt.txt). Etiket
        şart: aynı cümleyi bir öğrenci sesle de söyleyebilir, ama "cevabı
        göster" yalnızca öğretmenden gelirse üç adım kuralını geçersiz kılar.
        """
        veri = veri or {}
        # Öğretmen yazıyorsa ders boşta değildir — sınıf sessizken öğretmenin
        # klavyeyle çalıştığı bir dersi boşta sayıp kapatmak yanlış olur.
        self.etkinlik_bildir()

        # Yazılı öğretmen talimatı kalıcı ders kaydına da düşer. Eskiden
        # yalnızca ekrandaki (geçici) DERS KAYDI paneline yazılıyordu —
        # logs/ders/*.txt'de hiç yoktu, bu yüzden dosyayı sonradan okuyan biri
        # (ör. bir hatayı araştırırken) modelin NEDEN öyle davrandığını
        # gösteren en önemli parçayı — öğretmenin ne yazdığını — hiç göremiyordu.
        # "[ÖĞRETMEN KOMUTU] " öneki ÖĞRETMEN etiketiyle zaten tekrar olacağı
        # için kayıtta atılır.
        transcript.log_line("ogretmen", metin.removeprefix("[ÖĞRETMEN KOMUTU] "))

        try:
            if anahtar == "durdur":
                # Kalıcı duraklatma: yalnızca DEVAM ET kaldırır.
                self.motor.duraklat(True)
                # Sesi ANINDA kes. Modele "duraklat" demek yeterli değil:
                # o yalnızca üretimi durdurur, kuyrukta bekleyen ses çalmaya
                # devam eder ve öğretmen DURDUR'a bastıktan sonra Farabi
                # konuşmayı sürdürür. Sınıfta bu "düğme çalışmıyor" demek.
                if self._loop:
                    self._loop.call_soon_threadsafe(self._sesi_sustur)
                self.ui.set_state("IDLE")
            elif anahtar == "devam":
                self.motor.duraklat(False)
                self.motor.mudahale(False)
                if self._video_yuzunden_susturuldu:
                    # Videoyla birlikte otomatik kapatılan mikrofonu da geri
                    # aç — yoksa DEVAM ET'e basan öğretmen sınıfın artık
                    # duyulmadığını fark etmeyebilir.
                    self.ui.muted = False
                    self._video_yuzunden_susturuldu = False
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
            else:
                # Yazılı komut: motor bir süre öneri üretmesin ama kilitlenmesin
                # (core/ders_motoru.MUDAHALE_SURESI_DK).
                self.motor.mudahale(True)
                self._cerceveyi_ogretmenden_guncelle(metin)
        except Exception as e:
            log.error("Öğretmen komutu işlenemedi (%s): %s", anahtar, e)

        log.info("ÖĞRETMEN KOMUTU: %s", anahtar)
        self._on_text_command(metin)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                olaylar.yayinla(olaylar.OGRETMEN_MUDAHALE, komut=anahtar),
                self._loop)

    def _video_icin_duraklat(self) -> None:
        """
        YouTube'dan video açılınca Farabi kendi kendine DURDUR verir.

        Video ekranda kendi sesiyle oynarken mikrofon açık kalırsa Farabi
        video sesini öğrenci konuşması sanıp araya girer. DURDUR düğmesi bunu
        tek başına çözmez: yalnızca ders motorunu ve o an üretilmekte olan
        sesi durdurur, mikrofonu KAPATMAZ (bkz. `_on_teacher_command`). Bu
        yüzden burada `duraklat` + `_sesi_sustur`'ün yanına `ui.muted = True`
        de eklenir — mikrofon kapanmazsa `_listen_audio` video sesini
        oturuma göndermeye devam eder.

        Kalıcı bir duraklatmadır (`mudahale` gibi süreli değil): video ne
        zaman bittiğini Farabi bilemez, öğretmen DEVAM ET'e basana kadar
        duraklatılmış ve mikrofonu kapalı kalır.
        """
        self.motor.duraklat(True)
        self._sesi_sustur()
        self.ui.muted = True
        self._video_yuzunden_susturuldu = True
        self.ui.set_state("IDLE")
        self.ui.write_log(
            "SYS: YouTube videosu açıldı — mikrofon kapatıldı, ders duraklatıldı. "
            "Devam için DEVAM ET."
        )
        log.info("YouTube videosu açıldı: mikrofon otomatik kapatıldı, ders duraklatıldı.")

    def _programdan_cerceve(self, slot: dict) -> dict | None:
        """
        Ders programından yalnızca ders adını ve saatini al.

        Konu/kazanım burada boş kalır — öğretmen ders başında yazar veya söyler.
        """
        ders = (slot.get("ders") or "").strip()
        if not ders:
            return None
        log.info("Ders programından çerçeve: %s. ders · %s (konu öğretmen bekleniyor)",
                 slot.get("ders_no"), ders)
        return {
            "subject": ders,
            "unit": "",
            "topic": "",
            "kazanim": "",
            "kazanim_kodu": "",
            "kazanimlar": [],
            "period": slot.get("ders_no"),
        }

    def _cerceveyi_ogretmenden_guncelle(self, metin: str) -> None:
        """
        Öğretmen girişinden konu/kazanım çıkar (ör. 'konu: Türev · kazanım: …').

        Anahtar yoksa dokunma — serbest talimatlar da aynı kutudan gelir.
        """
        if not metin:
            return
        # [ÖĞRETMEN KOMUTU] öneki varsa ayıkla
        ham = re.sub(r"^\[ÖĞRETMEN KOMUTU\]\s*", "", metin, flags=re.I).strip()
        # Virgülden sonrası (ör. "konu: türev, çıkmış soru göster") talimat
        # metnidir, konu değil — eskiden "kazanım:" yoksa satırın sonuna kadar
        # her şeyi konu sayıyordu ve _current_lesson'a bütün cümle yazılıyordu.
        konu_m = re.search(
            r"konu\s*[:：]\s*(.+?)(?=\s*,|\s*(?:kazan[ıi]m)\s*[:：]|$)",
            ham, re.I | re.S,
        )
        kaz_m = re.search(r"kazan[ıi]m\s*[:：]\s*(.+)$", ham, re.I | re.S)
        ders_m = re.search(
            r"(?m)^\s*ders\s*[:：]\s*(.+?)(?=\s*(?:konu|kazan[ıi]m)\s*[:：]|$)",
            ham, re.I,
        )
        if not (konu_m or kaz_m or ders_m):
            return
        if self._current_lesson is None:
            self._current_lesson = {
                "subject": "", "unit": "", "topic": "", "kazanim": "",
                "kazanim_kodu": "", "kazanimlar": [], "period": None,
            }
        if ders_m:
            self._current_lesson["subject"] = ders_m.group(1).strip()
            self.motor.durum.ders_adi = self._current_lesson["subject"]
        if konu_m:
            self._current_lesson["topic"] = konu_m.group(1).strip()
            self.motor.durum.konu = self._current_lesson["topic"]
        if kaz_m:
            self._current_lesson["kazanim"] = kaz_m.group(1).strip()
        log.info("Çerçeve öğretmenden güncellendi: ders=%s konu=%s",
                 self._current_lesson.get("subject"),
                 self._current_lesson.get("topic"))

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        log.error("Öğrenciye hata bildirildi: %s — %s", tool_name, short)
        self.speak(f"Efendim, {tool_name} bir hatayla karşılaştı. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Talimat modu DERSİ BAŞLAT'tan önce ui.py'de seçilir; ders_dili ile
        # aynı desen — bağlantı anında (her (yeniden)bağlanışta) okunur, bu
        # yüzden self._ders_kipi burada, __init__'teki timetable/config
        # değerinin ÜZERİNE geçersiz kılınır.
        if getattr(getattr(self, "ui", None), "talimat_modu", False):
            self._ders_kipi = KIP_TALIMAT
        if self._ders_kipi == KIP_TALIMAT:
            return self._build_talimat_config()

        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        # 24 SAATLİK biçim. Eskiden "%I:%M %p" (12 saatlik) veriliyordu ve
        # model gece 00:20'yi sınıfa "saat 12:20" diye okuyordu — açılışa
        # geçen saat ile promptdaki saat aynı biçimde olmalı.
        time_str = now.strftime("%d.%m.%Y %A — saat %H:%M")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this when the lesson or the student refers to time.\n\n"
        )

        parts = [time_ctx]

        # Ders çerçevesi — Farabi'nin konu dışına çıkmama kuralı buna dayanır.
        # Konu/kazanım öğretmenden gelir; boş alanlar "plandan geldi" ima etmez.
        lesson = self._current_lesson
        if lesson:
            fields = [
                ("Ders",    lesson.get("subject")),
                ("Ünite",   lesson.get("unit")),
                ("Konu",    lesson.get("topic")),
                ("Kazanım", lesson.get("kazanim")),
            ]
            dolu = [(label, value) for label, value in fields if value]
            if dolu:
                lesson_ctx = "[BUGÜNKÜ DERS — DERS ÇERÇEVEN BUDUR]\n" + "\n".join(
                    f"{label}: {value}" for label, value in dolu
                )
                parts.append(lesson_ctx + "\n")
            if not lesson.get("topic") and not lesson.get("kazanim"):
                parts.append(
                    "[KONU BEKLENİYOR]\n"
                    "Ders adı biliniyor olabilir ama konu ve kazanım henüz "
                    "yok. Öğretmenden (yazı veya ses) konu ve kazanımı al; "
                    "almadan yoklamaya veya anlatıma geçme.\n"
                )

        # ŞU AN HANGİ DERS? Öğretmenin el programından gelir ve kritik bilgidir:
        # Farabi bunu bilmiyorsa sınıfa sormak zorunda kalıyor, öğretmen de
        # her ders aynı soruyu cevaplıyordu.
        slot = getattr(self, "_program_slotu", None)
        if slot:
            parts.append(
                f"[ŞU ANKİ DERS — DERS PROGRAMINDAN]\n"
                f"{slot.get('sinif', '')} sınıfı, {slot.get('ders_no')}. ders "
                f"saati, ders: {slot.get('ders', '')}. "
                f"Bu bilgi okulun ders programından gelir; sınıfa 'hangi "
                f"dersteyiz' diye SORMA, sen biliyorsun.\n"
            )

        # Bu tahta hangi derslikte? Farabi kime ders verdiğini bilmeli.
        derslik = tahta.derslik()
        if derslik:
            parts.append(
                f"[DERSLİK]\nBu tahta {derslik} sınıfında duruyor. Ders verdiğin "
                f"sınıf budur; plan ve kitap ararken {tahta.sinif_duzeyi()}. sınıf "
                f"düzeyini varsay.\n"
            )

        # Ders kipi — sınıfta insan öğretmen var mı? Tonu ve düzen sorumluluğunu
        # bu belirler. Kipe göre davranış kuralları core/prompt.txt içindedir.
        if self._ders_kipi == KIP_OGRETMENLI:
            parts.append(
                "[DERS KİPİ: ÖĞRETMENLİ]\n"
                "Sınıfta bir insan öğretmen ve yaklaşık 20 öğrenci var. Sınıf "
                "düzeni ve disiplin ÖĞRETMENİN sorumluluğunda; senin işin "
                "içeriği anlatmak ve öğrenciyi düşündürmek. Öğretmen söz "
                "aldığında sus ve bekle. Öğretmene 'kıymetli öğretmenim' diye "
                "hitap et, sınıfa 'çocuklar' de.\n"
            )
        else:
            parts.append(
                "[DERS KİPİ: ÖĞRETMENSİZ]\n"
                "Sınıfta insan öğretmen yok, yaklaşık 20 öğrenci var. Dersin "
                "akışı, sınıfın konuya odaklanması ve söylediğin her bilginin "
                "doğruluğu senin sorumluluğunda. Sınıfa 'çocuklar' de.\n"
            )

        parts.append(sys_prompt)

        # ── Ders dili ────────────────────────────────────────────────────────
        # Varsayılan Türkçe. core/prompt.txt TEK KAYNAK olarak Türkçe kalır —
        # üç dile çevirip üç kopya bakımı yapmak yerine modele "yukarıdaki
        # pedagojik kuralları anla, ama TÜM dersi hedef dilde işle" denir.
        # Öğretmen panelinden (ui.py) DERSİ BAŞLAT'tan ÖNCE seçilir; Live'da
        # bir bağlantının system_instruction'ı kurulduktan sonra
        # değişemeyeceği için burada yalnızca İLK bağlantıda okunur — ders
        # ortasında dil değişimi desteklenmez (bkz. ui.py'deki not).
        ders_dili = getattr(getattr(self, "ui", None), "ders_dili", None) or "tr"

        if ders_dili == "en":
            dil_direktifi = (
                "[LANGUAGE RULE — VERY IMPORTANT]\n"
                "The pedagogical instructions above are written in Turkish — read "
                "and internalize them, but conduct the ENTIRE lesson in ENGLISH: "
                "every word you speak, from the opening greeting to the closing "
                "summary, must be English. Do not switch back to Turkish even if "
                "a student speaks Turkish to you — answer in English. Still call "
                "yourself 'Farabi'. Address the class as 'students' or 'everyone', "
                "and — in the mode with a human teacher present — the teacher as "
                "'dear teacher'. Speak numbers, times and units in English (e.g. "
                "'twenty-three degrees', 'nine ten'). Keep the level appropriate "
                "for a Turkish high-school classroom learning in English.\n"
            )
        elif ders_dili == "de":
            dil_direktifi = (
                "[SPRACHREGEL — SEHR WICHTIG]\n"
                "Die pädagogischen Anweisungen oben sind auf Türkisch verfasst — "
                "verstehe und befolge sie, aber halte die GESAMTE Unterrichtsstunde "
                "auf DEUTSCH ab: jedes Wort, von der Begrüßung bis zur "
                "Zusammenfassung, muss Deutsch sein. Wechsle nicht zurück ins "
                "Türkische, auch wenn ein Schüler Türkisch spricht — antworte auf "
                "Deutsch. Nenne dich weiterhin 'Farabi'. Sprich die Klasse mit "
                "'Schülerinnen und Schüler' oder 'liebe Klasse' an, und — im Modus "
                "mit anwesender Lehrkraft — die Lehrkraft mit 'liebe Lehrkraft'. "
                "Sprich Zahlen, Uhrzeiten und Einheiten auf Deutsch (z. B. "
                "'dreiundzwanzig Grad', 'zehn nach neun'). Halte das Niveau für "
                "eine türkische Oberstufenklasse angemessen, die auf Deutsch lernt.\n"
            )
        else:
            dil_direktifi = (
                "[DİL KURALI — ÇOK ÖNEMLİ]\n"
                "Her zaman TÜRKÇE konuş ve TÜRKÇE yanıt ver. Öğrenci başka bir dilde "
                "konuşsa bile sen Türkçe cevap ver. Kendine 'Farabi' de. Sınıfa "
                "'çocuklar' ya da 'arkadaşlar' diye hitap et; tek bir öğrenciyle "
                "konuşuyorsan adıyla seslen. Lise seviyesinde, sade ve anlaşılır bir "
                "Türkçe kullan. Sayıları, saatleri ve birimleri Türkçe söyle "
                "(örn. 'yirmi üç derece', 'saat dokuzu on geçiyor'). Gereksiz İngilizce "
                "kelime kullanma; terimin Türkçesi varsa onu tercih et.\n"
            )
        parts.append(dil_direktifi)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            # BU SATIR UNUTULMUŞTU — yukarıdaki `parts` listesi kuruluyor ama
            # config'e hiç verilmiyordu, yani Farabi PERSONASIZ çalışıyordu:
            # core/prompt.txt, ders çerçevesi, derslik, ders kipi ve Türkçe
            # kuralı modele HİÇ ulaşmıyordu. Açılışta "Sistem promptu:
            # prompt.txt (8033 karakter)" diye loglandığı için çalışıyor
            # görünüyordu; dosya okunup atılıyordu.
            #
            # Görünen sonucu: prompt.txt'teki ARAÇ KULLANIMI tablosu modele
            # gitmediği için Farabi ders_icerigi ve web_search'ü kendiliğinden
            # çağırmıyordu. Araç TANIMLARI gidiyordu (tools=...), ama hangi
            # durumda hangisini çağıracağını söyleyen metin gitmiyordu.
            system_instruction="\n".join(parts),
            # BU SATIR DA UNUTULMUŞTU — system_instruction ile aynı hata, aynı
            # yerde. `TOOL_DECLARATIONS` kuruluyordu ama config'e HİÇ
            # verilmiyordu: model araçların varlığından habersizdi.
            #
            # Görünen sonucu: model aracı çağırmak yerine ÇAĞIRIYORMUŞ GİBİ
            # KONUŞUYORDU. 30.07.2026 ders kaydı, 23:25 —
            #   ÖĞRENCİ: "YouTube'dan bir video çevirir misin konuyla ilgili?"
            #   FARABİ:  "...`youtube_video` aracını çağırıyorum.
            #            (`youtube_video` çağırıldı...) Çocuklar, şu an ekranda
            #            ... bir video dönüyor."
            # Ekranda hiçbir şey yoktu; farabi.log'da o oturumda tek bir
            # "ARAÇ ▶" satırı bile yok. Model, olmayan bir yeteneği sınıfa
            # anlatmıştı.
            #
            # Bir aracın çalışması İKİ şeye bağlı: bildirimin buradan gitmesi
            # ve ne zaman çağrılacağını söyleyen metnin system_instruction
            # içinde olması. Araç sessizce hiç çağrılmıyorsa önce bu iki
            # satıra bakın.
            # Kip'e göre filtrelenir (kayit.bildirimler(kip)) — talimat
            # moduna özel araçlar (web_ac, uygulama_ac, dosya_ac) normal
            # derste modele HİÇ bildirilmez. TOOL_DECLARATIONS (filtresiz)
            # yalnızca başlangıç banner'ındaki toplam araç sayısı için kalır.
            tools=[{"function_declarations": kayit.bildirimler(self._ders_kipi)}],
            output_audio_transcription={},
            # NOT: SDK'nın AudioTranscriptionConfig'inde language_codes /
            # language_hints alanları görünüyor ama Live API sunucusu bunları
            # REDDEDİYOR ("Unknown name language_codes at
            # setup.input_audio_transcription"). Denendi ve doğrulandı —
            # buraya alan eklemeyin, oturum hiç açılmaz.
            # Türkçe transkripsiyon kalitesi yerine aşağıdaki VAD ayarıyla
            # iyileştiriliyor (ilk hece kesilmesi ve kelime ortası kesme).
            input_audio_transcription={},
            # ── SES ALGILAMA AYARI DENENDİ VE GERİ ALINDI ──────────────────
            # realtime_input_config / AutomaticActivityDetection ile kalabalık
            # sınıf için ayar yapıldı (start/end sensitivity, prefix_padding,
            # silence_duration). SONUÇ: Farabi konuşanı hiç duymadı — oturum
            # açılıyor, selamlıyor, ama öğrenciden HİÇ transkript gelmiyor.
            # Ayardan önceki oturumlarda 11 öğrenci satırı vardı, sonrasındaki
            # dört oturumda sıfır. Önce yalnızca start_sensitivity geri alındı,
            # yetmedi; blok tamamen kaldırıldı.
            #
            # BURAYA VAD AYARI EKLEMEYİN. Varsayılan davranış çalışıyor.
            # Kalabalık sınıf gürültüsü, core/prompt.txt'teki "KALABALIK VE
            # GÜRÜLTÜ" kuralıyla (tek tek konuşalım uyarısı) ele alınıyor —
            # yani model tarafında, ses katmanında değil.
            session_resumption=types.SessionResumptionConfig(),
            # Modelin iç muhakemesi yanıt akışına karışmasın — ders kaydına
            # İngilizce düşünce metni sızıyordu. Düşünme devam eder, yalnızca
            # dışa verilmez.
            thinking_config=types.ThinkingConfig(include_thoughts=False),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    def _build_talimat_config(self) -> types.LiveConnectConfig:
        """
        Öğretmen talimat modu — kısa, ayrı bir sistem promptu ve yalnızca
        kip="talimat" araçları (kayit.bildirimler(KIP_TALIMAT)). Ses/oturum
        ayarları (session_resumption, thinking_config, speech_config,
        transkripsiyon) `_build_config()`'teki ile BİREBİR aynı tutulur —
        bunlar gerçek arızalarla ayarlanmış, kipe bağlı değil.
        """
        araclar = kayit.bildirimler(KIP_TALIMAT)
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=_TALIMAT_PERSONASI,
            tools=[{"function_declarations": araclar}],
            output_audio_transcription={},
            input_audio_transcription={},
            session_resumption=types.SessionResumptionConfig(),
            thinking_config=types.ThinkingConfig(include_thoughts=False),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _isci(self, ad: str, islev):
        """
        Ağır aracı iş parçacığında çalıştır ve KAYITTAKİ SÜREDE bitmezse bırak.

        `run_in_executor` iptal edilemez — iş parçacığı arka planda devam eder.
        Burada iptal edilen BEKLEME'dir ve sınıf için önemli olan budur: ders
        artık bir araca kilitlenmez. Ölçülen en kötü hâl 55,4 saniyeydi ve o
        süre boyunca öğrenci sesi bile işlenmiyordu.
        """
        sure = kayit.zaman_asimi(ad)
        gorev = asyncio.get_event_loop().run_in_executor(None, islev)
        if sure is None:
            return await gorev
        return await asyncio.wait_for(gorev, timeout=sure)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        _t0 = asyncio.get_event_loop().time()
        log.info("ARAÇ ▶ %s | argümanlar: %s", name, args)
        await olaylar.yayinla(olaylar.ARAC_BASLADI, ad=name, argumanlar=args)
        self.ui.set_state("THINKING")

        result = "Done."

        try:
            if name == "ders_icerigi":
                r = await self._isci(
                    name, lambda: ders_icerigi(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Ders içeriği bulunamadı."

            elif name == "kitap_sorusu":
                r = await self._isci(
                    name, lambda: kitap_sorusu(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Kitap sorusu yanıtlanamadı."

            elif name == "pdf_sayfa":
                r = await self._isci(
                    name, lambda: pdf_sayfa(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Sayfa gösterilemedi."

            elif name == "yks_sorulari":
                r = await self._isci(
                    name, lambda: yks_sorulari(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Çıkmış soru bulunamadı."

            elif name == "ders_hafizasi":
                r = await self._isci(
                    name, lambda: ders_hafizasi(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Geçmiş ders kaydı bulunamadı."

            elif name == "site_goster":
                r = await self._isci(
                    name, lambda: site_goster(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Sayfa gösterilemedi."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await self._isci(
                    name, lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "web_search":
                r = await self._isci(name, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
                # Mirror substantial results to the on-screen content panel
                if r and len(r) > 120:
                    mode  = args.get("mode", "search").upper()
                    query = args.get("query") or ", ".join(args.get("items", []))
                    label = f"{mode} — {query[:38]}" if query else mode
                    self.ui.show_content(label, r)

            elif name == "youtube_video":
                r = await self._isci(name, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."
                action = args.get("action", "play").lower().strip()
                if action == "play" and args.get("query", "").strip():
                    self._video_icin_duraklat()
                    result += (
                        " Mikrofon kapatıldı ve ders duraklatıldı — video oynarken "
                        "konuşma, üstüne anlatma. Öğretmen DEVAM ET diyene kadar sessiz "
                        "kal."
                    )

            elif name == "eba":
                r = await self._isci(name, lambda: eba(parameters=args, response=None, player=self.ui))
                result = r or "Done."
                action = args.get("action", "video").lower().strip()
                if action == "video":
                    self._video_icin_duraklat()
                    result += (
                        " Mikrofon kapatıldı ve ders duraklatıldı — video oynarken "
                        "konuşma, üstüne anlatma. Öğretmen DEVAM ET diyene kadar sessiz "
                        "kal."
                    )

            elif name == "web_ac":
                r = await self._isci(name, lambda: web_ac(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "uygulama_ac":
                r = await self._isci(name, lambda: uygulama_ac(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "dosya_ac":
                r = await self._isci(name, lambda: dosya_ac(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_farabi":
                self.ui.write_log("SYS: Ders bitirme isteği alındı.")
                self.speak("Görüşmek üzere, iyi çalışmalar.")
                # Bulundu (2026-08-18): eskiden burada doğrudan os._exit(0)
                # çağıran ayrı bir thread vardı — _temiz_kapan()'ı hiç
                # çağırmıyordu, o yüzden ders normal "hoşça kal" ile
                # bittiğinde ne transkriptin kapanış satırı yazılıyordu ne de
                # server'a ders kaydı yedeği (POST /api/egitim/ders_kaydi_yedek)
                # gidiyordu — server'daki yedekler/ders_kaydi/ hep boştu.
                # _temiz_kapan zaten _boşta_gozcusu'nda kullanılan, test
                # edilmiş coroutine; burada da onu çağırıyoruz.
                async def _kapat():
                    await asyncio.sleep(1)  # veda cümlesi çalınsın diye
                    await self._temiz_kapan("ders bitti")
                asyncio.create_task(_kapat())

            else:
                result = f"Unknown tool: {name}"

        except asyncio.TimeoutError:
            # Ders bir araca kilitlenmez. Model kazanım metniyle devam etsin;
            # sınıfın sessizce beklemesi en kötü seçenektir.
            sure = kayit.zaman_asimi(name)
            result = (f"{name} aracı {sure:.0f} saniyede yanıt vermedi ve iptal edildi. "
                      f"SINIFA TEKNİK SORUN ANLATMA — 'ulaşamıyorum', 'teknik aksaklık', "
                      f"'sistem' gibi sözler etme. Elindeki kazanım metniyle sınırlı "
                      f"kalarak anlatmaya DEVAM ET; kitapta olmayan bilgi uydurma. "
                      f"Gerekirse aracı daha dar bir istekle (tema ya da hafta vererek) "
                      f"sessizce yeniden çağır.")
            log.warning("ARAÇ ⏱ %s zaman aşımına uğradı (%s sn).", name, sure)
            self.ui.write_log(f"SYS: {name} zaman aşımı ({sure:.0f} sn).")
            await olaylar.yayinla(olaylar.ARAC_ZAMAN_ASIMI, ad=name, sure=sure)

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            log.exception("ARAÇ ✖ %s başarısız (%s): %s", name, type(e).__name__, e)
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        _dt = asyncio.get_event_loop().time() - _t0
        log.info("ARAÇ ◀ %s | %.2f sn | %d karakter | %s",
                 name, _dt, len(str(result)), str(result)[:120].replace(chr(10), " "))
        if _dt > 10:
            log.warning("%s aracı %.1f saniye sürdü — sınıfta bu uzun bir sessizlik.", name, _dt)
        await olaylar.yayinla(olaylar.ARAC_BITTI, ad=name, sure=round(_dt, 2),
                              karakter=len(str(result)))
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        log.debug("Mikrofon görevi başladı.")
        loop = asyncio.get_event_loop()

        # Mikrofon tanısı: "duymuyor" şikâyetinde sorunun mikrofonda mı yoksa
        # transkripsiyonda mı olduğunu ayırt etmek için ses SEVİYESİ ölçülür.
        # Yalnızca sayı tutulur, ses kaydedilmez.
        self._mic_chunk = 0     # mikrofondan alınıp gönderilen paket
        self._mic_atlanan = 0   # Farabi konuşurken atılan paket
        self._mic_tepe  = 0     # en yüksek ani genlik
        self._mic_rms_top = 0.0 # RMS toplamı (ortalama enerji için)

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                farabi_speaking = self._is_speaking
            if farabi_speaking or self.ui.muted:
                # Farabi konuşurken kendi sesini duymaması için girdi atılır.
                # Bu sayaç olmadan "mikrofon çalışmıyor" sanılabiliyordu.
                self._mic_atlanan += 1
            if not farabi_speaking and not self.ui.muted:
                data = indata.tobytes()
                self._mic_chunk += 1
                try:
                    import numpy as _np
                    d = _np.asarray(indata, dtype=_np.float64)
                    tepe = int(_np.abs(d).max())
                    if tepe > self._mic_tepe:
                        self._mic_tepe = tepe
                    self._mic_rms_top += float(_np.sqrt((d ** 2).mean()))
                except Exception:
                    pass
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        async def _mic_tani():
            """
            15 saniyede bir mikrofon durumunu bildir.

            EŞİKLER MUTLAK DEĞİL, GÜRÜLTÜ TABANINA GÖRELİ.

            Mutlak eşik kullanmak hatalıydı. Ölçüm (30.07.2026): aynı
            mikrofonun ortam gürültüsü, sistem kazancına göre 40 kat
            değişiyor —
                kazanç %100 -> ortam rms 453
                kazanç  %70 -> ortam rms 158
                kazanç  %50 -> ortam rms  67
                kazanç  %30 -> ortam rms  12
            Yani "rms 400 = konuşma" kuralı %100 kazançta sessiz odayı
            konuşma sanıyor, %30 kazançta gerçek konuşmayı kaçırıyor.
            10 tahtalı dağıtımda her tahtanın tabanı da farklı olacak.

            Çözüm: ilk pencereleri GÜRÜLTÜ TABANI ölçümü olarak kullan,
            sonra konuşmayı tabana göre tanımla (taban x4 ve en az +120).
            Tepe genlik yalnızca kırpılma tespiti için — tek başına
            yanıltıcıdır, kapı sesi tepeyi 18000'e çıkarır.
            """
            taban: float | None = None        # ölçülen gürültü tabanı
            pencere = 0

            while True:
                await asyncio.sleep(15)
                adet, atlanan = self._mic_chunk, self._mic_atlanan
                tepe = self._mic_tepe
                rms  = (self._mic_rms_top / adet) if adet else 0.0
                self._mic_chunk = self._mic_atlanan = self._mic_tepe = 0
                self._mic_rms_top = 0.0
                pencere += 1

                if adet == 0 and atlanan == 0:
                    log.error("MİKROFON: 15 saniyede hiç ses paketi gelmedi — "
                              "aygıt yakalamıyor ya da mikrofon kapalı.")
                    continue
                if adet == 0:
                    log.info("MİKROFON: girdi alınmadı çünkü Farabi konuşuyordu "
                             "(%d paket atlandı). Bu normal.", atlanan)
                    continue

                # İlk pencere taban kabul edilir; sonrakiler tabanı aşağı çeker
                if taban is None:
                    taban = rms
                    log.info("MİKROFON: gürültü tabanı ölçüldü (rms=%d). "
                             "Konuşma eşiği: %d.", int(taban), int(max(taban * 4, taban + 120)))
                    continue
                taban = min(taban, rms)
                esik = max(taban * 4, taban + 120)

                if tepe >= 32000:
                    log.warning("MİKROFON: KIRPILMA (tepe=%d, rms=%d). Kazanç çok "
                                "yüksek; sinyal bozuluyor ve transkripsiyon "
                                "güvenilmez. Öneri: kazancı düşür.", tepe, int(rms))
                elif rms >= esik:
                    log.info("MİKROFON: konuşma var (rms=%d, eşik=%d, taban=%d, "
                             "%d paket).", int(rms), int(esik), int(taban), adet)
                else:
                    log.warning("MİKROFON: konuşma algılanmıyor (rms=%d < eşik=%d, "
                                "taban=%d). Ortam sesinden ayrışan bir konuşma yok.",
                                int(rms), int(esik), int(taban))

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                log.info("Mikrofon akışı açık (%d Hz).", SEND_SAMPLE_RATE)
                tani = asyncio.create_task(_mic_tani())
                try:
                    while True:
                        await asyncio.sleep(0.1)
                finally:
                    tani.cancel()
        except Exception as e:
            log.exception("Mikrofon hatası: %s", e)
            raise

    async def _receive_audio(self):
        log.debug("Alım görevi başladı.")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        # Öğrenci söze girdi: model üretmeyi kesti ama BİZİM
                        # kuyruğumuzda çalınmamış ses duruyor. Boşaltılmazsa
                        # Farabi öğrencinin üstüne eski cümlesini konuşmaya
                        # devam eder — sınıfta "takıldı, dondu" diye görünen
                        # şey budur. Live API'nin bu sinyali işlenmek zorunda.
                        if getattr(sc, "interrupted", False):
                            atilan = self._sesi_sustur()
                            log.info("Sözü kesildi — çalınmamış %d ses paketi "
                                     "atıldı.", atilan)
                            self.etkinlik_bildir()

                            # Kesilen turun YARIM kalan metnini kendi satırında
                            # kaydedip arabellekleri SIFIRLA — aksi hâlde bir
                            # SONRAKİ turun metni bunun ÜSTÜNE eklenip tek,
                            # dev ve anlamsız bir satırda birleşiyordu. Ölçüldü
                            # (02.08.2026, logs/ders/2026-08-02.txt, 11:30:22):
                            # öğretmenin "Matematik, permütasyon" dediği an,
                            # Farabi'nin kesilen önceki cümlesiyle aynı FARABİ
                            # satırına karışmış, ders kaydı okunamaz olmuştu.
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                transcript.log_line("ogrenci", full_in)
                            in_buf = []

                            full_out = _konusma_temizle(" ".join(out_buf))
                            if full_out:
                                self.ui.canli_satir_guncelle(full_out + " (kesildi)")
                                self.ui.canli_satir_bitir()
                                transcript.log_line("farabi", full_out + " (kesildi)")
                            out_buf = []

                        # Akan altyazı: metin ekrana SES ÇALINMADAN ÖNCE/EŞZAMANLI
                        # yazılsın diye her transkripsiyon PARÇASI geldiğinde satır
                        # güncellenir — eskiden yalnızca turn_complete'te TEK SEFERDE
                        # yazılıyordu, o noktada ses zaten baştan sona çalınmış
                        # oluyordu (karar: 2026-08-11, "önce metin sonra ses").
                        # `response.data` (ses) burada hiç geciktirilmiyor —
                        # audio_in_queue'ya her zamanki gibi anında düşüyor.
                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                if not out_buf:
                                    self.ui.canli_satir_baslat("Farabi: ")
                                out_buf.append(txt)
                                self.ui.canli_satir_guncelle(_konusma_temizle(" ".join(out_buf)))

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                transcript.log_line("ogrenci", full_in)
                                self.etkinlik_bildir()
                            in_buf = []

                            full_out = _konusma_temizle(" ".join(out_buf))
                            if full_out:
                                self.ui.canli_satir_bitir()
                                transcript.log_line("farabi", full_out)
                                self.etkinlik_bildir()
                            out_buf = []

                    if response.tool_call:
                        # Araçlar ALIM DÖNGÜSÜNÜN İÇİNDE çalıştırılmaz. Eskiden
                        # burada await ediliyorlardı; ölçülen 55,4 saniyelik bir
                        # çağrı boyunca döngü duruyor, öğrenci sesi bile
                        # işlenmiyordu. Artık ayrı görev: yanıt hazır olunca
                        # gönderilir, döngü akmaya devam eder.
                        cagrilar = list(response.tool_call.function_calls)
                        for fc in cagrilar:
                            log.info("Araç çağrısı geldi: %s", fc.name)
                        asyncio.create_task(self._araclari_calistir(cagrilar))
        except Exception as e:
            log.exception("Alım döngüsü hatası: %s", e)
            traceback.print_exc()
            raise

    async def _araclari_calistir(self, cagrilar) -> None:
        """Araçları alım döngüsünün dışında çalıştır ve yanıtları geri gönder."""
        try:
            yanitlar = [await self._execute_tool(fc) for fc in cagrilar]
            if self.session:
                await self.session.send_tool_response(function_responses=yanitlar)
        except Exception as e:
            log.exception("Araç yanıtı gönderilemedi: %s", e)

    # Oturum kurulduktan sonra ders durumu bildirimi için beklenecek süre.
    # Açılışın sesli olarak bitmesi gerekir: araya giren bir metin turu,
    # modelin selamlamayı yarıda kesip baştan almasına yol açıyordu.
    ENJEKSIYON_GECIKMESI_SN = 75

    async def _ders_motoru_dongusu(self) -> None:
        """
        Ders adımını ve kalan süreyi tazele; değişince modele bildir.

        Bildirimde ÜÇ kural, üçü de gerçek bir arızadan geliyor:

        1. `turn_complete=True` — eskiden False gönderiliyordu. Yarım bırakılan
           kullanıcı turu oturumu bekler hâlde tutuyor, model konuşmaya hiç
           başlayamıyordu ("dinliyor, düşünüyor, dinliyor" döngüsü).
        2. Oturum açılır açılmaz gönderilmez. Bildirim açılış selamının üstüne
           binince model selamlamayı yeniden yapıyordu.
        3. Farabi konuşurken gönderilmez; kendi cümlesini kesmesin.

        Talimat modunda TAMAMEN devre dışı — o modda ders yok, adım/süre/
        öneri kavramlarının hiçbiri anlamlı değil (bkz. KIP_TALIMAT).
        """
        if getattr(self, "_ders_kipi", None) == KIP_TALIMAT:
            return
        await asyncio.sleep(self.ENJEKSIYON_GECIKMESI_SN)
        onceki = None
        while True:
            try:
                durum = self.motor.guncelle()
                imza = (durum.adim, durum.kalan_dk)
                if imza != onceki:
                    onceki = imza
                    self.ui.write_log(f"DERS: {self.motor.hud_satiri()}")
                    await olaylar.yayinla(
                        olaylar.DURUM_DEGISTI, **durum.sozluk()
                    )
                    oneri = self.motor.oneri()
                    if oneri:
                        log.info("Ders motoru önerisi: %s — %s",
                                 oneri["eylem"], oneri["gerekce"])

                metin = self.motor.enjeksiyon_metni()
                if metin and self.session and not self._is_speaking:
                    log.info("Ders durumu bildirildi: %s",
                             metin.splitlines()[0])
                    await self.session.send_client_content(
                        turns={"role": "user", "parts": [{"text": metin}]},
                        turn_complete=True,
                    )
            except Exception as e:
                log.error("Ders motoru döngüsü hatası: %s", e)
            await asyncio.sleep(30)

    async def _oturum_devam_notu(self) -> None:
        """
        Yeniden bağlanmadan sonra: SELAMLAMA YOK, dersi sürdür.

        Yeni oturumun modeli önceki konuşmayı hatırlamaz; sistem promptu ise
        açılışta selam vermeyi söyler. Kısa bir devam notu bunu keser.

        KRİTİK — iki ayrı dal: "dersin ortasındasın, sürdür" demek yalnızca
        gerçekten bir konu/kazanım biliniyorsa doğrudur. Konu henüz
        belirlenmemişken bu talimat modeli UYDURMAYA itiyordu — ölçüldü
        (02.08.2026, logs/ders/2026-08-02.txt, 09:52:13): bağlantı dersin çok
        erken bir anında (öğretmen henüz konu bile söylememişken) koptu,
        model "[OTURUM DEVAM]"ı "dersin ortasındayım" diye okudu ve var
        olmayan bir "türev" konusunu icat edip "kaldığımız yerden devam
        edelim" dedi. `_current_lesson`/`motor.durum`da gerçekten konu yoksa
        modele bunu AÇIKÇA söylüyoruz — "sınırlı devam et" ilkesi burada da
        geçerli.
        """
        await asyncio.sleep(0.3)
        if not self.session:
            return

        if getattr(self, "_ders_kipi", None) == KIP_TALIMAT:
            await self.session.send_client_content(
                turns={"parts": [{"text":
                    "[OTURUM DEVAM] Bağlantı yenilendi. SELAMLAMA YAPMA, tek "
                    "kısa cümleyle talimat modunda hazır olduğunu bildir."
                }]},
                turn_complete=True,
            )
            self.ui.write_log("SYS: Bağlantı yenilendi (talimat modu).")
            return

        d = self.motor.durum
        biliniyor = bool(d.ders_adi or d.konu)

        if biliniyor:
            satirlar = [
                "[OTURUM DEVAM] Bağlantı teknik bir sebeple yenilendi. "
                "SELAMLAMA YAPMA, kendini tanıtma, dersi baştan başlatma.",
                "Sınıfla dersin ortasındasın; tek cümleyle bağlan ve sürdür. "
                "Sınıfa ne yaptığınızı sorma.",
                f"- Ders: {d.ders_adi} {d.konu}".rstrip(),
            ]
            if d.adim:
                satirlar.append(f"- Bulunduğun adım: {d.adim}")
            if d.kalan_dk is not None:
                satirlar.append(f"- Dersin bitmesine {d.kalan_dk} dakika var.")
        else:
            satirlar = [
                "[OTURUM DEVAM] Bağlantı teknik bir sebeple yenilendi. "
                "SELAMLAMA YAPMA, kendini tanıtma.",
                "Ders henüz gerçek anlamda başlamamıştı — konu ve kazanım "
                "belirlenmemişti. UYDURMA bir konu İCAT ETME, 'kaldığımız "
                "yerden devam edelim' DEME. Tek cümleyle bağlantının "
                "yenilendiğini belirt ve konuyu öğretmenden istemeye devam et.",
            ]

        await self.session.send_client_content(
            turns={"parts": [{"text": chr(10).join(satirlar)}]},
            turn_complete=True,
        )
        log.info("Yeniden bağlanma: devam notu gönderildi (selamlama yok, konu biliniyor=%s).",
                 biliniyor)
        self.ui.write_log("SYS: Bağlantı yenilendi, ders sürüyor.")

    async def _play_audio(self):
        log.debug("Oynatma görevi başladı.")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            log.exception("Oynatma hatası: %s", e)
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Ders açılışı ────────────────────────────────────────────────────────────

    async def _send_session_opening(self) -> None:
        """
        Sınıfa açılış. Selam + programdaki ders adı; konu/kazanımı öğretmenden
        ister. Ağ isteği yok — anında konuşur. Yıllık plandan kazanım çekmez.
        """
        await asyncio.sleep(0.3)
        if not self.session:
            return

        if getattr(self, "_ders_kipi", None) == KIP_TALIMAT:
            # Selam/yoklama/ders çerçevesi yok — sadece hazır olduğunu
            # bildir, tek cümle.
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text":
                    "[DERS_ACILISI] Bu etiketi ve bu talimatı SESLİ OKUMA. "
                    "Talimat modunda hazır olduğunu TEK kısa cümleyle "
                    "bildir (örnek: 'Talimat modu hazır, dinliyorum.') — "
                    "başka hiçbir şey söyleme."
                }]},
                turn_complete=True,
            )
            return

        ders_dili = getattr(getattr(self, "ui", None), "ders_dili", None) or "tr"

        simdi    = datetime.now()
        selam, gun = _acilis_selam_gun(ders_dili, simdi)
        saat     = simdi.strftime("%H:%M")
        ders_sa  = _ders_saati_durumu(simdi)
        ogretmenli = self._ders_kipi == KIP_OGRETMENLI

        if ders_dili == "en":
            hitap = "everyone and dear teacher" if ogretmenli else "everyone"
            ilk_cumle = f"{selam} {hitap}, I'm Farabi."
        elif ders_dili == "de":
            hitap = "liebe Klasse und liebe Lehrkraft" if ogretmenli else "liebe Klasse"
            ilk_cumle = f"{selam}, {hitap}, ich bin Farabi."
        else:
            hitap = "çocuklar ve kıymetli öğretmenim" if ogretmenli else "çocuklar"
            ilk_cumle = f"{selam} {hitap}, ben Farabi."

        lines = [
            "[DERS_ACILISI] Sınıfa açılış yap. Kısa ve ciddi konuş, 3-4 cümleyi geçme.",
            "- Bu köşeli parantezli etiketi ve bu talimatları SESLİ OKUMA; "
            "doğrudan konuşmaya başla.",
            f"- İlk cümlen aynen (bu dilde, başka dile çevirmeden) şu olsun: "
            f"'{ilk_cumle}'",
            f"- Ardından günü ve saati söyle: bugün {gun}, saat {saat}.",
        ]
        if ders_sa:
            lines.append(f"- Kaçıncı derste olduğumuzu da belirt: {ders_sa}")

        # Ders programı biliyorsa hangi derste olduğumuz SÖYLENİR.
        slot = getattr(self, "_program_slotu", None)
        if slot:
            lines.append(
                f"- Hangi derste olduğumuzu NET söyle: {slot.get('sinif','')} "
                f"sınıfı, {slot.get('ders_no')}. ders, {slot.get('ders','')}. "
                f"Bunu sınıfa sorma, sen biliyorsun."
            )
        else:
            lines.append(
                "- Ders programı bu saat için kayıt vermedi. Hangi ders "
                "olduğunu ÖĞRETMENE sor (sınıfa değil)."
            )

        lesson = self._current_lesson or {}
        subject = lesson.get("subject", "")
        topic   = lesson.get("topic", "")
        kazanim = lesson.get("kazanim", "")
        hazir = bool(topic or kazanim)

        if subject and not slot:
            lines.append(f"- Bugünkü dersi duyur: {subject}.")

        if hazir:
            if topic:
                lines.append(f"- Konuyu duyur: {topic}.")
            if kazanim:
                lines.append(
                    f"- Dersin kazanımını tek cümleyle, kendi sözlerinle söyle: {kazanim}"
                )
            lines.append(
                "- Yoklama al: 'Arkadaşlar, derse gelmeyen öğrencilerin "
                "isimlerini söyler misiniz?' de ve cevabı bekle."
            )
            lines.append(
                "- Gelen isimleri tek seferde tekrarla ('Bugün X ve Y yok, "
                "not aldım') ve yoklamayı kapat. İsim listesini tartışma, "
                "sebep sorma, yorum yapma."
            )
            lines.append(
                "- Sonra 'Yoklamayı aldıysak başlayalım.' de ve DERSİ ANLATMAYA "
                "BAŞLA: 40 dakikalık planını iki cümleyle duyur, ardından ilk "
                "adıma (ön bilgi sorusu) geç. İzin isteme, onay bekleme."
            )
        else:
            # Konu/kazanım öğretmenindir — plandan veya sınıftan tahmin etme.
            if ders_dili == "en":
                hitap_og = "Dear teacher" if ogretmenli else "The teacher"
            elif ders_dili == "de":
                hitap_og = "Liebe Lehrkraft" if ogretmenli else "Die Lehrkraft"
            else:
                hitap_og = ("kıymetli öğretmenim" if ogretmenli else "öğretmene").capitalize()
            lines.append(
                f"- Konu ve kazanım henüz belli değil. {hitap_og} "
                "bugünkü konuyu ve kazanımı yazmasını veya söylemesini iste. "
                "Sınıfa 'hangi konudayız' / 'nerede kalmıştık' diye SORMA."
            )
            lines.append(
                "- Konu veya kazanım gelene kadar yoklama alma ve anlatıma "
                "başlama; beklediğini tek cümleyle belirt."
            )

        dil_satiri = {
            "en": "- Speak entirely in ENGLISH — see the [LANGUAGE RULE] above.",
            "de": "- Sprich vollständig auf DEUTSCH — siehe [SPRACHREGEL] oben.",
        }.get(ders_dili, "- Tamamen TÜRKÇE konuş.")

        lines += [
            # Yasak yalnızca BU açılış turu için: selam anında verilmeli,
            # araç çağrısı onu geciktirir.
            "- Sadece bu açılış turunda araç çağırma; sonraki turlarda serbestsin.",
            "- '[DERS_ACILISI]' ifadesini ASLA söyleme.",
            dil_satiri,
        ]

        await self.session.send_client_content(
            turns={"parts": [{"text": chr(10).join(lines)}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Ders açılışı gönderildi.")

    # ── main loop ───────────────────────────────────────────────────────────

    def _log_startup_banner(self) -> None:
        """Tahtadan uzaktan tanı koyabilmek için ortam künyesi."""
        log.info("=" * 58)
        log.info("Farabi başlıyor | model=%s", LIVE_MODEL)
        log.info("Kök dizin: %s", BASE_DIR)
        log.info("Log dosyası: %s", log_path())
        log.info("Ders kaydı : %s", transcript.session_file())
        try:
            log.info("Sistem promptu: %s (%d karakter)",
                     PROMPT_PATH.name, len(_load_system_prompt()))
        except Exception as e:
            log.warning("Sistem promptu okunamadı: %s", e)
        # Araç bildirimlerinin gerçekten config'e girdiğini görmek için.
        # "Prompt okundu" satırı vardı ama promptun config'e verilip
        # verilmediğini göstermiyordu; araç listesi de aynı biçimde sessizce
        # düşmüştü. Bu satır oturumu açmadan önce sayıyı basar.
        log.info("Araçlar: %d bildirim (%s)",
                 len(TOOL_DECLARATIONS), ", ".join(_TOOL_ADLARI))
        try:
            slot = getattr(self, "_program_slotu", None)
            if slot:
                log.info("Ders programı: %s. ders · %s · %s",
                         slot.get("ders_no"), slot.get("sinif"), slot.get("ders"))
            elif program.cizelge():
                log.info("Ders programı: bu saat için kayıt yok "
                         "(konu/kazanım öğretmenden beklenecek)")
            else:
                log.warning("Ders programı YOK (config/ders_programi.json). "
                            "Farabi hangi derste olduğunu öğretmene soracak.")
        except Exception as e:
            log.debug("Program künyesi yazılamadı: %s", e)
        try:
            devs = sd.query_devices()
            gir = [d["name"] for d in devs if d["max_input_channels"] > 0]
            cik = [d["name"] for d in devs if d["max_output_channels"] > 0]
            # Listedeki ilk aygıtı değil, gerçekten KULLANILAN varsayılanı yaz.
            # Önceki sürüm ilkini yazıyordu ve tanıyı yanlış yöne çekiyordu.
            vg, vc = sd.default.device
            def _ad(i):
                try:
                    return devs[i]["name"] if i is not None and i >= 0 else "YOK"
                except Exception:
                    return "?"
            log.info("Ses girişi : varsayılan=%s  (%d aygıt)", _ad(vg), len(gir))
            log.info("Ses çıkışı : varsayılan=%s  (%d aygıt)", _ad(vc), len(cik))
            if not gir:
                log.error("Mikrofon bulunamadı — Farabi öğrenciyi duyamaz.")
            if not cik:
                log.error("Hoparlör bulunamadı — Farabi konuşamaz.")
        except Exception as e:
            log.error("Ses aygıtları sorgulanamadı: %s", e)
        log.info("Ders çerçevesi: %s",
                 self._current_lesson or "yok (öğretmenden beklenecek)")
        log.info("Ders kipi: %s", self._ders_kipi)
        log.info("Derslik: %s", tahta.etiket())
        log.info("=" * 58)

    # ── Oturum izni: dersi ÖĞRETMEN başlatır ────────────────────────────────
    #
    # Otomatik bağlanma bilerek yok. Canlı ses oturumu açık durduğu sürece
    # ücretlendiriliyor ve tahta gün boyu (teneffüs, öğle, gece, hafta sonu,
    # tatil) bağlı kalırsa fatura dersin kendisinden değil boşta beklemeden
    # doluyor — ölçüldü: haftada 168 saat oturuma karşılık 26,7 saat gerçek
    # ders. Bağlantıyı öğretmenin çift tıklamasına bağlamak bu israfı bitirir.
    #
    # Not: çift tıklama tek tık yerine bilerek seçildi — tahta dokunmatik ve
    # sınıftaki herhangi bir öğrenci tek tıkla oturum başlatabilirdi.

    def oturum_baslat(self) -> None:
        """UI iş parçacığından çağrılır: dersi başlat."""
        if not self._loop:
            return
        self._loop.call_soon_threadsafe(self._oturum_izni.set)

    def _sesi_sustur(self) -> int:
        """
        Çalınmayı bekleyen sesi at ve kaç paket atıldığını döndür.

        DURDUR'un ve söz kesmenin ANINDA etkili olması buna bağlı: modele
        "dur" demek yalnızca ÜRETİMİ durdurur, kuyruktaki saniyelerce ses
        çalmaya devam eder.
        """
        atilan = 0
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                    atilan += 1
                except asyncio.QueueEmpty:
                    break
        self.set_speaking(False)
        return atilan

    def etkinlik_bildir(self) -> None:
        """Konuşma ya da öğretmen girdisi oldu — boşta sayacını sıfırla."""
        self._son_etkinlik = time.time()

    async def _boşta_gozcusu(self) -> None:
        """
        BOSTA_KAPATMA_DK boyunca hiç konuşma/öğretmen girdisi olmazsa ders
        kaydını kapatıp programı sonlandır.

        Sayaç ses seviyesine değil TRANSKRİPTE bağlı: bu donanımda mikrofon
        taban gürültüsü hiçbir zaman sıfır değil, "ses var mı" ölçütü hiç
        tetiklenmezdi. Farabi konuşurken de boşta sayılmaz — sınıfın sessizce
        dinlediği bir anlatım boşluk değildir.

        `time.monotonic()` DEĞİL, `time.time()` (duvar saati) kullanılıyor —
        bulundu (2026-08-18): cihaz uyku/askıya alma moduna girdiğinde
        `CLOCK_MONOTONIC` askıda geçen süreyi SAYMAZ, bu yüzden 45 dakikalık
        gerçek bir uyku bu gözcüyü hiç tetiklemiyordu (`farabi.log`'da
        18:06-18:52 arası tam sessizlik kanıtıyla doğrulandı) — hem
        `BOSTA_KAPATMA_DK` boşuna işlemiyordu hem de oturum bayat
        `[CURRENT DATE & TIME]` ile 45 dakika daha sürdü (session_resumption
        reconnect'i atlıyor, `_build_config` yeniden çağrılmıyor). Duvar
        saati uyanınca doğru "gecen"i görür, gözcü tetiklenir, `_temiz_kapan`
        çağrılır — bir sonraki oturum TAZE saatle açılır.
        """
        while True:
            await asyncio.sleep(20)
            if self._is_speaking:
                self.etkinlik_bildir()
                continue
            gecen = time.time() - self._son_etkinlik
            if gecen >= BOSTA_KAPATMA_DK * 60:
                log.info("%d dakikadır sessizlik — ders kaydı kapatılıp "
                         "çıkılıyor.", BOSTA_KAPATMA_DK)
                self.ui.write_log(
                    f"SYS: {BOSTA_KAPATMA_DK} dk sessizlik — ders kapatılıyor.")
                await self._temiz_kapan("boşta kalma")
                return

    @staticmethod
    def _ders_kaydini_yedekle() -> None:
        """Kapanan oturumun ders kaydı dosyasını sunucuya tek seferlik
        yedekler (server/main.py `POST /api/egitim/ders_kaydi_yedek`).
        SENKRON/BLOKLAYICI — çağıran bunu bir iş parçacığında çalıştırmalı.
        Sessizce başarısız olur: bir yedekleme hatası dersi/kapanışı ASLA
        kesintiye uğratmamalı (kitap_sorusu.py'nin sessiz geri-düşüş
        disipliniyle aynı ruhta)."""
        import requests

        from core import tahta

        try:
            yol = transcript.session_file()
            if not yol.exists():
                return
            icerik = yol.read_text(encoding="utf-8")
            requests.post(
                f"{tahta.sunucu_url()}/api/egitim/ders_kaydi_yedek",
                json={"derslik": tahta.derslik() or "bilinmeyen-derslik",
                      "dosya_adi": yol.name, "icerik": icerik},
                timeout=5.0,
            )
        except Exception as e:
            log.info("Ders kaydı yedeklenemedi (sessiz devam): %s", e)

    async def _temiz_kapan(self, sebep: str) -> None:
        """
        Ders kaydını kapatıp çık. `os._exit` KULLANMA — o, transkriptin
        kapanış satırını ve dosya boşaltmayı atlar; "kendini hafızaya alıp
        kapansın" isteğinin tam da kaybettiği şey budur.
        """
        try:
            transcript.log_line("sistem", f"— Oturum kapandı ({sebep}) —")
            transcript.log_session_end()
        except Exception as e:
            log.error("Ders kaydı kapatılamadı: %s", e)
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._ders_kaydini_yedekle),
                timeout=6.0,
            )
        except Exception as e:
            log.info("Ders kaydı yedekleme adımı atlandı: %s", e)
        log.info("Kapanıyor: %s", sebep)
        self._kapaniyor = True
        self._oturum_izni.clear()
        os._exit(0)

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._oturum_izni = asyncio.Event()
        self.ui.on_session_start = self.oturum_baslat
        self._log_startup_banner()

        # PİLOT/TEST AŞAMASI (2026-08-15) burada `self.ui.oto_baslat()` ile
        # tahta açılır açılmaz dersi otomatik başlatıyordu, çift tıkla
        # beklemiyordu. 2026-08-17: öğretmen isteğiyle geri alındı — DERSİ
        # BAŞLAT'a çift tıklamak yeniden ZORUNLU, aşağıdaki "öğretmen
        # başlatana kadar hiçbir bağlantı kurulmaz" davranışı geçerli.
        # `ui.py`'deki `FarabiUI.oto_baslat`/`MainWindow._oto_baslat_sig`
        # köprüsü hâlâ duruyor, sadece buradan çağrılmıyor — pilot testi
        # yeniden gerekirse tek satır eklemek yeterli.

        fail_streak = 0          # üst üste başarısız bağlantı sayısı
        last_error  = None       # aynı hata tekrar ediyor mu

        while True:
            # Öğretmen başlatana kadar HİÇBİR bağlantı kurulmaz.
            if not self._oturum_izni.is_set():
                self.ui.set_state("SLEEPING")
                self.ui.write_log("SYS: Ders bekleniyor — DERSİ BAŞLAT'a çift tıklayın.")
                await self._oturum_izni.wait()
                self.etkinlik_bildir()

            try:
                log.info("Gemini Live oturumu açılıyor... (deneme %d, anahtar %s)",
                         fail_streak + 1, anahtar.durum())
                self.ui.set_state("THINKING")
                config = self._build_config()

                # İstemci DÖNGÜ İÇİNDE kuruluyor. Eskiden döngünün dışındaydı;
                # anahtar devri eklenince orada kalsaydı yeni anahtar SDK'ya
                # hiç ulaşmaz, devir sessizce hiçbir işe yaramazdı.
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    log.info("Oturum açıldı. (anahtar %s)", anahtar.durum())
                    if fail_streak:
                        log.info("Bağlantı %d denemeden sonra düzeldi.", fail_streak)
                    fail_streak = 0
                    last_error  = None
                    anahtar.basarili()      # devir sayacını sıfırla
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: Farabi çevrimiçi.")
                    transcript.log_session_start()
                    self.ui.oturum_baslandi()

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._ders_motoru_dongusu())
                    tg.create_task(self._boşta_gozcusu())

                    # Oturum yenilendiyse öğretmen müdahalesi bayatlamıştır;
                    # yeni oturuma "duraklat" önerisiyle başlamak yanlış.
                    if self.motor.durum.ogretmen_mudahalesi and \
                            not self.motor.durum.duraklatildi:
                        self.motor.mudahale(False)

                    # Ders açılışı — süreç başına bir kez. Sonraki bağlantılarda
                    # selamlama DEĞİL, devam notu gider.
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_session_opening())
                    else:
                        tg.create_task(self._oturum_devam_notu())

            except Exception as e:
                fail_streak += 1
                sig = f"{type(e).__name__}: {e}"
                if sig == last_error:
                    # Aynı hata tekrarlıyor — yığın izini her seferinde basma,
                    # log dosyasını şişirip asıl sorunu gömüyor.
                    log.error("Oturum hatası yineliyor (%dx): %s", fail_streak, sig)
                else:
                    log.exception("Oturum hatası (%s): %s", type(e).__name__, e)
                    last_error = sig

                # Kota dolduysa sıradaki anahtarı DENE — bekleme yapmadan.
                # Geri çekilme (backoff) tek anahtar için ayarlanmıştı; havuzu
                # dolaşırken 3-6-12 sn beklemek dersin ortasında dakikalarca
                # sessizlik demek. Ayrıca fail_streak sıfırlanır, yoksa "3 kez
                # bağlanılamadı" tanısı biz sadece listeyi gezerken tetiklenir.
                if anahtar.kota_hatasi_mi(e):
                    onceki = anahtar.durum()
                    if anahtar.sonrakine_gec():
                        log.warning("Kota doldu (anahtar %s) — sıradaki anahtara "
                                    "geçiliyor: %s", onceki, anahtar.durum())
                        self.ui.write_log(f"SYS: Kota doldu, anahtar {anahtar.durum()} deneniyor.")
                        fail_streak = 0
                        last_error  = None
                        self.session = None
                        continue
                    log.error("Havuzdaki %d anahtarın hepsinde kota dolu. "
                              "NOT: harcama sınırı Google Cloud PROJESİ başınadır — "
                              "anahtarlar aynı projedense hepsi aynı sınırı paylaşır.",
                              anahtar.adet())
                    self.ui.write_log("SYS: Tüm anahtarlarda kota dolu.")
            finally:
                self.session = None
                self.ui.oturum_kapandi()

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")
            transcript.log_session_end()

            # Üst üste hatada giderek artan bekleme: 3, 6, 12, 24, 48, en çok 60 sn.
            # Kalıcı bir arıza varsa (yanlış API anahtarı, ağ yok) saniyede bir
            # deneyip logu boğmasın; geçici kopmada da hızlı toparlansın.
            delay = min(3 * (2 ** max(0, fail_streak - 1)), 60) if fail_streak else 3

            if fail_streak == 3:
                log.error(
                    "3 kez üst üste bağlanılamadı. Muhtemel nedenler: "
                    "API anahtarı geçersiz, internet yok ya da model adı hatalı. "
                    "Ayrıntı için yukarıdaki yığın izine bakın."
                )
                self.ui.write_log("SYS: Bağlantı kurulamıyor — ağ ve API anahtarını kontrol edin.")
            elif fail_streak >= 10 and fail_streak % 10 == 0:
                log.critical(
                    "%d kez üst üste bağlanılamadı. Tahta ders veremiyor, "
                    "müdahale gerekiyor.", fail_streak
                )

            log.warning("Oturum kapandı — %d saniye sonra yeniden bağlanılacak.", delay)
            await asyncio.sleep(delay)

def main():
    ui = FarabiUI("face.png")

    def runner():
        ui.wait_for_api_key()
        farabi = FarabiLive(ui)
        try:
            asyncio.run(farabi.run())
        except KeyboardInterrupt:
            print("\n🔴 Kapatılıyor...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
