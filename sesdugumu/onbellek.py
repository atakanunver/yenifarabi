"""Metin → WAV bayt önbelleği (bellek içi). Anahtar boşluk/büyük-küçük harf duyarsız."""
import threading

_TR_BUYUK = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")


def anahtar(metin: str) -> str:
    return " ".join(metin.translate(_TR_BUYUK).lower().split())


class Onbellek:
    def __init__(self) -> None:
        self._veri: dict[str, bytes] = {}
        self._kilit = threading.Lock()

    def al(self, metin: str) -> bytes | None:
        with self._kilit:
            return self._veri.get(anahtar(metin))

    def koy(self, metin: str, wav: bytes) -> None:
        with self._kilit:
            self._veri[anahtar(metin)] = wav

    def __len__(self) -> int:
        return len(self._veri)
