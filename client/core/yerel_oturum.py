"""Farabi 2.0 yerel konuşma turu: STT → Qwen (araçlı, akışlı) → cümle → TTS → çal.

Gemini Live'ın yerine geçer; araçların kendisi değişmez (FarabiYerel
`arac_calistir` olarak mevcut `_execute_tool`'u verir). Bkz. spec
docs/superpowers/specs/2026-10-07-farabi2-yerel-ses-design.md.
"""
import asyncio
import logging
import re
import threading

from core.cumle_bolucu import CumleBolucu
from core.kaliplar import KALIPLAR
from core.metin_duzelt import seslendirme_icin
from core.qwen_istemci import AracCagrisi, QwenZamanAsimi
from core.ses_istemci import SesServisiHatasi

log = logging.getLogger("farabi.yerel")

AZAMI_ARAC = 3
RISKLI = {"yoklama_al": "onay_yoklama", "youtube_video": "onay_video",
          "shutdown_farabi": "onay_kapat"}
_BEKLEME_KALIBI = {"kitap_sorusu": "kitap", "ders_icerigi": "kitap", "pdf_sayfa": "kitap",
                   "ekrandaki_soruyu_oku": "ekran", "ekran_goruntusu_al": "ekran"}
_EVET = re.compile(r"\b(evet|tamam|olur|aç|al|kapat|onaylıyorum)\b", re.IGNORECASE)


class YerelOturum:
    def __init__(self, ses, qwen, sistem_metni, araclar, arac_calistir, cal, metin_goster,
                 azami_gecmis: int = 12) -> None:
        self.ses, self.qwen = ses, qwen
        self._sistem, self._araclar = sistem_metni, araclar
        self._arac_calistir, self._cal, self._goster = arac_calistir, cal, metin_goster
        self._azami = azami_gecmis
        self.gecmis: list[dict] = []
        self._iptal = threading.Event()
        self._nesil = 0
        self._bekleyen: AracCagrisi | None = None
        self._tts_hata_serisi = 0
        self._kilit: asyncio.Lock | None = None

    def iptal(self) -> None:
        """Süren turu keser; eski turun bekleyen cümleleri çalınmaz (nesil sayacı)."""
        self._nesil += 1
        self._iptal.set()

    async def _seslendir(self, metin: str, nesil: int) -> None:
        if nesil != self._nesil:
            return
        try:
            wav = await asyncio.to_thread(self.ses.tts, seslendirme_icin(metin))
            self._tts_hata_serisi = 0
        except SesServisiHatasi as e:
            log.warning("TTS hatası: %s", e)
            self._goster("farabi", metin)
            self._tts_hata_serisi += 1
            if self._tts_hata_serisi == 3 and not await asyncio.to_thread(self.ses.saglik):
                self._goster("sistem", "Ses servisi kapalı (Bilgehan)")
            return
        if nesil == self._nesil:
            self._cal(wav)

    async def _kalip(self, anahtar: str, nesil: int) -> None:
        await self._seslendir(KALIPLAR[anahtar], nesil)

    async def ses_turu(self, wav: bytes) -> None:
        nesil = self._nesil
        try:
            metin = await asyncio.to_thread(self.ses.stt, wav)
        except SesServisiHatasi as e:
            log.warning("STT hatası: %s", e)
            await self._kalip("duyamadim", nesil)
            return
        if metin:
            await self.metin_turu(metin)

    async def metin_turu(self, metin: str, kaynak: str = "ogretmen") -> None:
        """Bir konuşma turu. kaynak: ogretmen | arac (speak) | sistem (ders motoru vb.)."""
        if self._kilit is None:  # olay döngüsüne bağlı; ilk kullanımda kur
            self._kilit = asyncio.Lock()
        async with self._kilit:
            self._iptal.clear()
            nesil = self._nesil
            if kaynak == "ogretmen":
                self._goster("ogretmen", metin)
                if self._bekleyen is not None:
                    cagri, self._bekleyen = self._bekleyen, None
                    if _EVET.search(metin):
                        sonuc = await self._araci_calistir(cagri, nesil)
                        self.gecmis.append({"role": "tool", "content": sonuc})
                    else:
                        await self._kalip("iptal", nesil)
                    return
            self.gecmis.append({"role": "user", "content": metin})
            await self._model_dongusu(nesil)

    async def _araci_calistir(self, cagri: AracCagrisi, nesil: int) -> str:
        await self._kalip(_BEKLEME_KALIBI.get(cagri.ad, "bakiyorum"), nesil)
        try:
            return str(await self._arac_calistir(cagri.ad, cagri.argumanlar))
        except Exception as e:  # noqa: BLE001 — araç hatası Qwen'e sonuç olarak döner
            log.exception("Araç hatası: %s", cagri.ad)
            return f"Araç hatası ({cagri.ad}): {str(e)[:120]}"

    async def _model_dongusu(self, nesil: int) -> None:
        arac_sayisi = 0
        while True:
            mesajlar = ([{"role": "system", "content": self._sistem()}]
                        + self.gecmis[-self._azami:])
            araclar = self._araclar() if arac_sayisi < AZAMI_ARAC else []
            bolucu, metin, cagrilar = CumleBolucu(), "", []
            kuyruk: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def uret(mesajlar=mesajlar, araclar=araclar):
                try:
                    for x in self.qwen.akis(mesajlar, araclar, self._iptal):
                        loop.call_soon_threadsafe(kuyruk.put_nowait, x)
                except Exception as e:  # noqa: BLE001 — ana döngüye taşınır
                    loop.call_soon_threadsafe(kuyruk.put_nowait, e)
                loop.call_soon_threadsafe(kuyruk.put_nowait, None)

            uretici = asyncio.ensure_future(asyncio.to_thread(uret))
            hata = None
            try:
                while (x := await kuyruk.get()) is not None:
                    if isinstance(x, Exception):
                        hata = x
                        continue
                    if nesil != self._nesil:
                        continue
                    if isinstance(x, AracCagrisi):
                        cagrilar.append(x)
                        continue
                    metin += x
                    for c in bolucu.ekle(x):
                        await self._seslendir(c, nesil)
            finally:
                await uretici
            if hata is not None:
                log.warning("Qwen hatası: %s", hata)
                await self._kalip("yogunum" if isinstance(hata, QwenZamanAsimi) else "hata", nesil)
                return
            if nesil != self._nesil:
                if metin:
                    self.gecmis.append({"role": "assistant", "content": metin + " (kesildi)"})
                return
            for c in bolucu.bitir():
                await self._seslendir(c, nesil)
            if not cagrilar:
                self.gecmis.append({"role": "assistant", "content": metin})
                return
            self.gecmis.append({"role": "assistant", "content": metin, "tool_calls": [
                {"function": {"name": c.ad, "arguments": c.argumanlar}} for c in cagrilar]})
            for c in cagrilar:
                if c.ad in RISKLI:
                    self._bekleyen = c
                    await self._kalip(RISKLI[c.ad], nesil)
                    self.gecmis.append({"role": "tool", "content": "Öğretmenin onayı bekleniyor."})
                    return
                sonuc = await self._araci_calistir(c, nesil)
                self.gecmis.append({"role": "tool", "content": sonuc})
                arac_sayisi += 1
