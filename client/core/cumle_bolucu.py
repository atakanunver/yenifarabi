"""Akan LLM metninden seslendirilecek cümleleri çıkarır."""
import re

from core.metin_duzelt import sira_sayisi_mi

_KISALTMA = {"dr", "prof", "vb", "vs", "örn", "bkz", "sn", "av", "doç", "yrd", "no", "s", "sf"}
_SON = re.compile(r"[.!?…]+|,")


class CumleBolucu:
    """`ekle` tamamlanan cümleleri döner. İlk cümle `ilk_en_az`, sonrakiler
    `en_az` karakterden kısaysa bir sonrakiyle birleştirilir (TTS çağrısı azalır).
    İlk parça `ilk_virgul_en_az` karakteri bulunca virgülde de kesilir: ilk tam
    cümlenin TTS'i ~2,5 sn sürüyordu, kısa ilk parça ilk sesi öne çeker."""

    def __init__(self, ilk_en_az: int = 12, en_az: int = 25,
                 ilk_virgul_en_az: int = 20) -> None:
        self._tampon = ""
        self._ilk = True
        self._ilk_en_az, self._en_az = ilk_en_az, en_az
        self._ilk_virgul_en_az = ilk_virgul_en_az

    @staticmethod
    def _sinir_mi(metin: str, son: int) -> bool | None:
        """True/False; None = karar için sonraki kelime henüz gelmedi."""
        if metin[son - 1] != ".":
            return True
        onceki = metin[:son].rstrip(".")
        kelime = onceki.split()[-1] if onceki.split() else ""
        if kelime.lower() in _KISALTMA:
            return False
        if kelime.isdigit():  # "12. sınıf" bölünmez, "Cevap 12. Şimdi" bölünür
            sonraki = metin[son:].split(maxsplit=1)
            if not sonraki or len(metin[son:].lstrip()) == len(sonraki[0]):
                return None  # sonraki kelime tamamlanmadı
            return not sira_sayisi_mi(sonraki[0].strip(",.;:!?\"'"))
        return True

    def ekle(self, parca: str) -> list[str]:
        self._tampon += parca
        cikti: list[str] = []
        bas = 0
        for m in _SON.finditer(self._tampon):
            son = m.end()
            if son >= len(self._tampon) or not self._tampon[son].isspace():
                continue  # devamı gelmeden ya da "3.5" gibi: karar verme
            sinir = self._sinir_mi(self._tampon, son)
            if sinir is None:
                break  # sonraki kelime gelmeden karar verme
            if not sinir:
                continue
            aday = self._tampon[bas:son].strip()
            if m.group() == ",":
                esik = self._ilk_virgul_en_az if self._ilk else None
            else:
                esik = self._ilk_en_az if self._ilk else self._en_az
            if esik is not None and len(aday) >= esik:
                cikti.append(aday)
                bas = son
                self._ilk = False
        self._tampon = self._tampon[bas:]
        return cikti

    def bitir(self) -> list[str]:
        kalan = " ".join(self._tampon.split())
        self._tampon, self._ilk = "", True
        return [kalan] if kalan else []
