"""Bilgehan farabi2-ses servisine ince HTTP istemcisi."""
import requests


class SesServisiHatasi(Exception):
    pass


class SesIstemci:
    # (bağlanma, okuma): Bilgehan tamamen kapalıyken bağlanma 10 sn beklemesin.
    def __init__(self, taban_url: str, oturum=None) -> None:
        self.url = taban_url.rstrip("/")
        self._o = oturum or requests.Session()

    def saglik(self) -> bool:
        try:
            r = self._o.get(f"{self.url}/saglik", timeout=3)
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except Exception:  # noqa: BLE001 — sağlık denetimi asla patlamaz
            return False

    def stt(self, wav: bytes) -> str:
        try:
            r = self._o.post(f"{self.url}/stt", data=wav,
                             headers={"Content-Type": "audio/wav"}, timeout=(2, 5))
            r.raise_for_status()
            return str(r.json().get("metin", "")).strip()
        except (requests.RequestException, ValueError) as e:
            raise SesServisiHatasi(f"stt: {e}") from e

    def tts(self, metin: str) -> bytes:
        try:
            r = self._o.post(f"{self.url}/tts", json={"metin": metin}, timeout=(2, 10))
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            raise SesServisiHatasi(f"tts: {e}") from e
