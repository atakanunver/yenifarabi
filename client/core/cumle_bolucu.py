"""Akan LLM metninden seslendirilecek cümleleri çıkarır."""
import re

_KISALTMA = {"dr", "prof", "vb", "vs", "örn", "bkz", "sn", "av", "doç", "yrd", "no", "s", "sf"}
_SON = re.compile(r"[.!?…]+")


class CumleBolucu:
    """`ekle` tamamlanan cümleleri döner. İlk cümle `ilk_en_az`, sonrakiler
    `en_az` karakterden kısaysa bir sonrakiyle birleştirilir (TTS çağrısı azalır)."""

    def __init__(self, ilk_en_az: int = 12, en_az: int = 25) -> None:
        self._tampon = ""
        self._ilk = True
        self._ilk_en_az, self._en_az = ilk_en_az, en_az

    @staticmethod
    def _sinir_mi(metin: str, son: int) -> bool:
        if metin[son - 1] != ".":
            return True
        onceki = metin[:son].rstrip(".")
        kelime = onceki.split()[-1] if onceki.split() else ""
        return not (kelime.lower() in _KISALTMA or kelime.isdigit())

    def ekle(self, parca: str) -> list[str]:
        self._tampon += parca
        cikti: list[str] = []
        bas = 0
        for m in _SON.finditer(self._tampon):
            son = m.end()
            if son >= len(self._tampon) or not self._tampon[son].isspace():
                continue  # devamı gelmeden ya da "3.5" gibi: karar verme
            if not self._sinir_mi(self._tampon, son):
                continue
            aday = self._tampon[bas:son].strip()
            if len(aday) >= (self._ilk_en_az if self._ilk else self._en_az):
                cikti.append(aday)
                bas = son
                self._ilk = False
        self._tampon = self._tampon[bas:]
        return cikti

    def bitir(self) -> list[str]:
        kalan = " ".join(self._tampon.split())
        self._tampon, self._ilk = "", True
        return [kalan] if kalan else []
