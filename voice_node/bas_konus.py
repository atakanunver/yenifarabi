"""voice_node/bas_konus.py — Faz 1b: bas-konuş (push-to-talk) kontrolcüsü.

PLAN SAPMASI (raporda işaretli): plan taslağı "ptt_basla -> aşağı akışa
VADUserStartedSpeakingFrame + ProposedUserStartedSpeakingFrame; ptt_bitir ->
~200ms bekle, sonra Stopped çerçeveleri" diyor — ses akışının BASILI
SÜRESİNCE canlı olarak STT'ye gerçek zamanlı aktığını varsayan bir okuma.
Kaynak incelemesi (`turns/user_stop/external_user_turn_stop_strategy.py`,
`services/stt_service.py::SegmentedSTTService`) şunu gösterdi: boş-basış
filtresi tam olarak bu noktada uygulanamaz — `ExternalUserTurnStopStrategy
(wait_for_transcript=True)` bir `TranscriptionFrame` gelene kadar turu
KAPATMAZ; STT'ye hiç ses gönderilmezse (boş basış) transkript hiç gelmez ve
tur SONSUZA kadar açık kalır (yığında bekleyen bir "kilitlenme").

Bu yüzden BasKonus BASILI TUTULAN SÜRE BOYUNCA ham sesi aşağı akışa
GEÇİRMEZ — kendi tamponunda toplar. `ptt_bitir` geldiğinde (serializer'ın
~200ms geciktirdiği kontrol mesajı — bkz. `serializer.py` docstring'i, aynı
ses-kuyruğu yarışı burada da geçerli: BasKonus'a ulaşan ses de
`_audio_in_queue` üzerinden akıyor) TÜM basılı segment üzerinde Silero VAD
(`voice_confidence`) ile TEK SEFERDE bir konuşma kontrolü yapılır:

  - konuşma YOKSA: hiçbir şey aşağı akışa gönderilmez — tur hiç AÇILMAZ,
    STT'ye hiçbir şey gitmez, kilitlenme riski YOK (plan madde "Silero
    yalnızca boş-basış filtresi" — sonucu aynı, yolu farklı).
  - konuşma VARSA: VADUserStartedSpeakingFrame + ProposedUserStartedSpeakingFrame
    -> TEK bir InputAudioRawFrame (tüm basılı segment) -> VADUserStoppedSpeakingFrame
    + ProposedUserStoppedSpeakingFrame, hepsi TEK bir `process_frame` çağrısı
    içinde sırayla push edilir (frame'ler `SystemFrame` alt sınıfı olduğu
    için pipeline'da kuyruklanmadan sırayla işlenir) — `SegmentedSTTService`
    tüm segmenti tek seferde alır, gecikme MALİYETİ YOK (segmented STT zaten
    yalnızca Stop anında çalışıyordu).

Tuş basılı DEĞİLKEN gelen ham ses (plan: "Tuş basılı değilken gelen ses
düşürülür") sessizce yutulur.
"""

from __future__ import annotations

import asyncio
import logging

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = logging.getLogger("ses_dugumu.bas_konus")

GIRIS_ORNEKLEME_HIZI = 16000


def _bos_basis_kontrolcusu() -> SileroVADAnalyzer:
    analiz = SileroVADAnalyzer(sample_rate=GIRIS_ORNEKLEME_HIZI, params=VADParams(confidence=0.7))
    # `sample_rate=` yapıcıya verilse de `VADAnalyzer.__init__` gerçek
    # `_sample_rate`'i 0 bırakıyor — yalnızca `set_sample_rate()` onu
    # ayarlıyor (normalde pipeline'ın kendi VAD bağlama noktası bunu
    # çağırıyor; burada bağımsız kullanıldığı için ELLE çağrılmalı, yoksa
    # `num_frames_required()` 256'ya (8kHz varsayılanı) düşüyor ve
    # `voice_confidence()` HER ZAMAN "Error analyzing audio... Supported
    # sampling rates" hatasıyla sessizce 0.0 dönüyor — canlı testte
    # bulundu: TÜM basışlar "boş basış" sayılıyordu.
    analiz.set_sample_rate(GIRIS_ORNEKLEME_HIZI)
    return analiz


class BasKonus(FrameProcessor):
    """Tahtadan gelen `ptt_basla` / `ptt_bitir` / `arac_sonuc` / `baglam`
    kontrol paketlerini pipeline çerçevelerine çevirir.

    `arac_futures`: `araclar.py`'nin doldurduğu, `call_id -> asyncio.Future`
    sözlüğü — `arac_sonuc` geldiğinde ilgili future çözülür (plan "Tahta
    araçları" köprüsü). `baglam_geldi`: kip/ders değiştiğinde çağrılan
    senkron ya da async callback (`oturum.py` bağlar).
    """

    def __init__(
        self,
        *,
        arac_futures: dict[str, asyncio.Future],
        baglam_geldi=None,
        vad=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._arac_futures = arac_futures
        self._baglam_geldi = baglam_geldi
        self._basili = False
        self._tampon = bytearray()
        # `vad`: testlerde gerçek Silero modelini yüklemeden sahte bir VAD
        # enjekte etmek için (bkz. tests/test_bas_konus.py) — üretimde hep
        # None, gerçek SileroVADAnalyzer kullanılır.
        self._vad = vad or _bos_basis_kontrolcusu()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            if self._basili:
                self._tampon += frame.audio
            # Basılı değilken gelen ses düşürülür (plan) — aşağı akışa
            # GEÇİRİLMEZ.
            return

        if isinstance(frame, InputTransportMessageFrame):
            await self._kontrol_isle(frame.message)
            return

        await self.push_frame(frame, direction)

    async def _kontrol_isle(self, mesaj: dict) -> None:
        tip = mesaj.get("tip")
        if tip == "ptt_basla":
            self._basili = True
            self._tampon = bytearray()
        elif tip == "ptt_bitir":
            await self._ptt_bitir_isle()
        elif tip == "arac_sonuc":
            self._arac_sonuc_isle(mesaj)
        elif tip == "baglam":
            if self._baglam_geldi is not None:
                sonuc = self._baglam_geldi(mesaj)
                if asyncio.iscoroutine(sonuc):
                    await sonuc
        else:
            log.warning("bilinmeyen kontrol mesajı tipi: %r", tip)

    async def _ptt_bitir_isle(self) -> None:
        if not self._basili:
            return  # eşleşmeyen/geç kalan ptt_bitir — yok say
        self._basili = False
        pcm = bytes(self._tampon)
        self._tampon = bytearray()

        if not pcm:
            return

        konusma_var = await asyncio.to_thread(self._konusma_var_mi, pcm)
        if not konusma_var:
            log.info("boş basış — segmentte konuşma bulunamadı, STT'ye gönderilmedi")
            return

        await self.push_frame(VADUserStartedSpeakingFrame())
        await self.push_frame(ProposedUserStartedSpeakingFrame())
        await self.push_frame(
            InputAudioRawFrame(audio=pcm, sample_rate=GIRIS_ORNEKLEME_HIZI, num_channels=1)
        )
        await self.push_frame(VADUserStoppedSpeakingFrame())
        await self.push_frame(ProposedUserStoppedSpeakingFrame())

    def _konusma_var_mi(self, pcm: bytes) -> bool:
        """Basılı tutulan segmentte Silero VAD'a göre konuşma var mı —
        senkron, `asyncio.to_thread` içinde çağrılır (birkaç saniyelik
        ses için onnxruntime CPU çıkarımı ~birkaç10 ms sürer)."""
        cerceve_bayt = self._vad.num_frames_required() * 2
        if cerceve_bayt <= 0:
            return True
        esik = self._vad.params.confidence
        for i in range(0, len(pcm) - cerceve_bayt + 1, cerceve_bayt):
            parca = pcm[i : i + cerceve_bayt]
            if len(parca) < cerceve_bayt:
                break
            if self._vad.voice_confidence(parca) >= esik:
                return True
        return False

    def _arac_sonuc_isle(self, mesaj: dict) -> None:
        call_id = mesaj.get("id")
        if not call_id:
            log.warning("arac_sonuc mesajında 'id' yok")
            return
        gelecek = self._arac_futures.pop(call_id, None)
        if gelecek is None:
            log.warning("arac_sonuc: bilinmeyen/zaman aşımına uğramış id=%s", call_id)
            return
        if not gelecek.done():
            gelecek.set_result(mesaj.get("sonuc") or {})
