"""Farabi 2.0 — Gemini Live yerine yerel ses hattı (bas-konuş).

FarabiLive'dan türer; araç yürütme, ses çalma, ders motoru, boşta gözcüsü,
susturma FarabiLive'ınkidir. Değişen: `self.session` bir adaptör — v1'de
modele giden her metin (`speak`, `_on_text_command`, ders motoru
bildirimi) YerelOturum'a metin turu olarak gider; görsel tur reddedilir
(ekrandaki_soruyu_oku OCR yoluna düşer — görsel okuma bulutta, spec kararı).
Bkz. docs/superpowers/specs/2026-10-07-farabi2-yerel-ses-design.md.
"""
import asyncio
import io
import re
import uuid
import wave
from dataclasses import dataclass, field

import sounddevice as sd

from actions import kayit
from core import program, tahta, transcript, yerel_ayar
from core.ders_motoru import DersMotoru
from core.logger import get_logger
from core.qwen_istemci import QwenIstemci, araclari_donustur
from core.ses_istemci import SesIstemci
from core.yerel_oturum import YerelOturum
from main import CHANNELS, CHUNK_SIZE, SEND_SAMPLE_RATE, FarabiLive, _ders_kipi

log = get_logger("farabi.yerel")
EN_KISA_KAYIT_SN = 0.4

_YEREL_KURALLAR = yerel_ayar.YEREL_KURALLAR


@dataclass
class _Fc:
    """`_execute_tool`'un beklediği function-call nesnesinin yerel karşılığı."""
    name: str
    args: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


_SAAT_RE = re.compile(r"\[CURRENT DATE & TIME\]\n.*?\n\n", re.DOTALL)


def _saati_sona_al(metin: str) -> str:
    """Dakikalık saat bloğunu talimatın sonuna taşır: başta dururken her yeni
    dakikada Ollama önek önbelleği tutmuyor, tüm talimat yeniden işleniyordu."""
    m = _SAAT_RE.search(metin)
    if not m:
        return metin
    return (metin[:m.start()] + metin[m.end():]).rstrip() + "\n\n" + m.group(0).strip()


def _gorev_hatasini_logla(gorev) -> None:
    if not gorev.cancelled() and gorev.exception() is not None:
        log.error("Yerel tur görevi hata verdi", exc_info=gorev.exception())


def siniflari_sec(ses_modu: str) -> type:
    return FarabiYerel if ses_modu == "yerel" else FarabiLive


def _wav_ayir(wav: bytes) -> bytes:
    """24 kHz mono 16-bit WAV → ham PCM (oynatma kuyruğu ham int16 bekler)."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.readframes(w.getnframes())


def _wav_yap(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SEND_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


class _OturumAdaptoru:
    """Gemini `session` arayüzünün yerel karşılığı (yalnızca kullanılan kısım)."""

    def __init__(self, oturum) -> None:
        self._oturum = oturum

    async def send_client_content(self, turns=None, turn_complete=True):
        parcalar = (turns or {}).get("parts", [])
        if any("inline_data" in p for p in parcalar):
            raise RuntimeError("yerel modda görsel tur yok — OCR yoluna düş")
        metin = " ".join(p.get("text", "") for p in parcalar).strip()
        if metin:
            asyncio.get_running_loop().create_task(
                self._oturum.metin_turu(metin, kaynak="sistem")
            ).add_done_callback(_gorev_hatasini_logla)


class FarabiYerel(FarabiLive):
    def __init__(self, ui) -> None:
        super().__init__(ui)
        self.ses = SesIstemci(yerel_ayar.ses_dugumu_url())
        self.oturum: YerelOturum | None = None
        self._kayit: list[bytes] = []
        self._kayit_akisi = None
        ui.on_ptt_bas = self._ptt_bas
        ui.on_ptt_birak = self._ptt_birak

    # ── Bas-konuş (UI iş parçacığından çağrılır) ────────────────────────
    # Qt yuvasında yakalanmayan istisna tüm uygulamayı düşürür (Kural 2) —
    # gövdeler try içinde; self.oturum ders sonunda None'a dönebilir, yerel al.
    def _ptt_bas(self) -> None:
        try:
            self._ptt_bas_ic()
        except Exception as e:  # noqa: BLE001
            log.exception("Bas-konuş başlatılamadı: %s", e)

    def _ptt_bas_ic(self) -> None:
        oturum, loop = self.oturum, self._loop
        if oturum:
            oturum.iptal()
            oturum.dinliyor = True
        if loop:
            loop.call_soon_threadsafe(self._sesi_sustur)
        self._akisi_kapat()  # `released` kaybolduysa eski akış açık kalmasın
        self._kayit = []

        def cb(indata, frames, t, status):
            self._kayit.append(bytes(indata))

        try:
            self._kayit_akisi = sd.RawInputStream(
                samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", callback=cb)
            self._kayit_akisi.start()
        except Exception as e:  # noqa: BLE001 — mikrofon yoksa ders bozulmaz (Kural 2)
            log.error("Mikrofon açılamadı: %s", e)
            self._kayit_akisi = None
            if oturum:
                oturum.dinliyor = False
            self.ui.uyari_goster("Mikrofon açılamadı.")
            return
        self.ui.set_state("LISTENING")

    def _akisi_kapat(self) -> None:
        akis, self._kayit_akisi = self._kayit_akisi, None
        if akis is None:
            return
        try:
            akis.stop()
            akis.close()
        except Exception as e:  # noqa: BLE001 — USB mikrofon çıkarılmış olabilir
            log.warning("Mikrofon akışı kapatılamadı: %s", e)

    def _ptt_birak(self) -> None:
        try:
            self._ptt_birak_ic()
        except Exception as e:  # noqa: BLE001
            log.exception("Bas-konuş bitirilemedi: %s", e)

    def _ptt_birak_ic(self) -> None:
        oturum, loop = self.oturum, self._loop
        if oturum:
            oturum.dinliyor = False
        if self._kayit_akisi is None:
            return
        self._akisi_kapat()
        pcm = b"".join(self._kayit)
        if len(pcm) / 2 / SEND_SAMPLE_RATE < EN_KISA_KAYIT_SN or not (loop and oturum):
            self.set_speaking(False)
            return
        self.ui.set_state("THINKING")
        self.etkinlik_bildir()
        asyncio.run_coroutine_threadsafe(self._ses_turu_calistir(_wav_yap(pcm)), loop)

    async def _ses_turu_calistir(self, wav: bytes) -> None:
        oturum = self.oturum
        try:
            if oturum:
                await oturum.ses_turu(wav)
        except Exception as e:  # noqa: BLE001 — tur çökse de tahta donmaz
            log.exception("Ses turu hatası: %s", e)
        finally:
            # Boş/filtrelenmiş STT ya da hata: hiçbir şey çalmadıysa "düşünüyor"da kalma.
            if self.audio_in_queue.empty() and not self._is_speaking:
                self.set_speaking(False)

    def _sesi_sustur(self) -> int:
        """DURDUR ve söz kesme: kuyruğun yanında Qwen/TTS üretimini de keser
        (v1'de bunu Gemini bağlantısını yenilemek yapıyordu)."""
        oturum = self.oturum
        if oturum:
            oturum.iptal()
        return super()._sesi_sustur()

    # ── YerelOturum'a verilen geri çağrılar ─────────────────────────────
    async def _arac_calistir(self, ad: str, args: dict) -> str:
        yanit = await self._execute_tool(_Fc(ad, args))
        return str((getattr(yanit, "response", None) or {}).get("result", "Tamam."))

    def _cal(self, wav: bytes) -> None:
        # Küçük parçalar: _sesi_sustur kuyruğu boşaltınca en çok bir parça
        # (~40 ms) çalar; tek parça cümle ise saniyelerce sürer.
        self._turn_done_event.set()
        pcm, adim = _wav_ayir(wav), CHUNK_SIZE * 2
        for i in range(0, len(pcm), adim):
            self.audio_in_queue.put_nowait(pcm[i:i + adim])

    def _goster(self, kim: str, metin: str) -> None:
        if kim == "ogretmen":
            self.ui.write_log(f"You: {metin}")
            transcript.log_line("ogrenci", metin)
            self.etkinlik_bildir()
        elif kim == "farabi":
            self.ui.write_log(f"Farabi: {metin}")
            transcript.log_line("farabi", metin)
        else:
            self.ui.uyari_goster(metin)

    def _sistem_metni(self) -> str:
        return _saati_sona_al(self._build_config().system_instruction + _YEREL_KURALLAR)

    async def _ders_bitti_bekle(self) -> None:
        while not self._ders_bitti_istendi:
            await asyncio.sleep(0.5)

    # ── Ana döngü ───────────────────────────────────────────────────────
    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._oturum_izni = asyncio.Event()
        self.ui.on_session_start = self.oturum_baslat
        self.ui.on_ders_bitir = self._on_ders_bitir
        self._log_startup_banner()
        while True:
            self.ui.set_state("SLEEPING")
            self.ui.write_log("SYS: Ders bekleniyor — DERSİ BAŞLAT'a çift tıklayın.")
            await self._oturum_izni.wait()
            if not await asyncio.to_thread(self.ses.saglik):
                log.error("Ses servisi kapalı: %s", self.ses.url)
                self.ui.uyari_goster("Ses servisi kapalı (Bilgehan) — Farabi başlatılamadı.")
                self._oturum_izni.clear()
                self.ui.dersi_sifirla()
                continue
            try:
                await self._ders_hazirla()
                self.audio_in_queue = asyncio.Queue()
                self._turn_done_event = asyncio.Event()
                self.oturum = YerelOturum(
                    self.ses, QwenIstemci(yerel_ayar.ollama_url()),
                    sistem_metni=self._sistem_metni,
                    araclar=lambda: araclari_donustur(kayit.bildirimler(self._ders_kipi)),
                    arac_calistir=self._arac_calistir, cal=self._cal, metin_goster=self._goster)
                self.session = _OturumAdaptoru(self.oturum)
                log.info("Yerel ses oturumu açıldı (ses: %s)", self.ses.url)
                self.ui.oturum_baslandi()
                self.ui.ptt_goster(True)
                self.ui.set_state("LISTENING")
                async with asyncio.TaskGroup() as tg:
                    gorevler = [tg.create_task(self._play_audio()),
                                tg.create_task(self._ders_motoru_dongusu()),
                                tg.create_task(self._boşta_gozcusu())]
                    await self._ders_bitti_bekle()
                    for g in gorevler:
                        g.cancel()
            except* asyncio.CancelledError:
                pass
            except* Exception as eg:  # noqa: BLE001 — oturum çökerse bekleme durumuna dön
                log.exception("Yerel oturum hatası: %s", eg.exceptions)
            finally:
                self._oturumu_kapat()

    def _oturumu_kapat(self) -> None:
        """Ders sonu: v1 run()'ın ders bitişi sıfırlamalarının yerel karşılığı."""
        oturum, self.oturum = self.oturum, None
        if oturum:
            oturum.iptal()  # süren tur araç çalıştırmasın, sesi sonraki derse taşımasın
        self.session = None
        self.ui.ptt_goster(False)
        self.ui.oturum_kapandi()
        self.set_speaking(False)
        self._video_yuzunden_susturuldu = False
        self.ui.muted = False
        self._ders_bitti_istendi = False
        self._ders_bitiriliyor = False
        self._oturum_izni.clear()
        transcript.yeni_oturum_baslat()
        self.ui.dersi_sifirla()

    async def _ders_hazirla(self) -> None:
        """v1 run()'ın ders başı hazırlığı (main.py, "ZAMANA BAĞLI durum" bloğu)."""
        self._program_slotu = None
        try:
            self._program_slotu = program.simdiki_ders()
        except Exception as e:  # noqa: BLE001
            log.error("Ders programı okunamadı: %s", e)
        self._current_lesson = (self._programdan_cerceve(self._program_slotu)
                                if self._program_slotu else None)
        await self._cerceveye_plan_kazanimi_ekle()
        self._ders_kipi_taban = self._ders_kipi = _ders_kipi()
        self.motor = DersMotoru(kip=self._ders_kipi_taban, cerceve=self._current_lesson,
                                sinif=tahta.derslik(), enjekte=True)
