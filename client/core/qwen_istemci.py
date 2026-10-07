"""Farabi Ollama (qwen3.8:27b) akışlı sohbet + araç çağrısı istemcisi."""
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

import requests

# requests okuma zaman aşımı iki satır arası beklemeye uygulanır: hem ilk
# çıktı hem akış ortasında takılma bu sınırla kesilir.
ILK_CIKTI_SN = 8.0


class QwenHatasi(Exception):
    pass


class QwenZamanAsimi(QwenHatasi):
    pass


@dataclass
class AracCagrisi:
    ad: str
    argumanlar: dict = field(default_factory=dict)


def _sema(s):
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _sema(v))
                for k, v in s.items()}
    if isinstance(s, list):
        return [_sema(x) for x in s]
    return s


def araclari_donustur(bildirimler: list[dict]) -> list[dict]:
    """actions/kayit.bildirimler() (Gemini biçimi) → Ollama `tools` biçimi."""
    return [{"type": "function", "function": {
        "name": b["name"], "description": b.get("description", ""),
        "parameters": _sema(b.get("parameters")) or {"type": "object", "properties": {}},
    }} for b in bildirimler]


def _arguman(ham) -> dict:
    if isinstance(ham, dict):
        return ham
    if isinstance(ham, str):
        try:
            v = json.loads(ham)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


class QwenIstemci:
    def __init__(self, taban_url: str, model: str = "qwen3.8:27b", satir_akisi=None) -> None:
        self.url = taban_url.rstrip("/")
        self.model = model
        self._satir_akisi = satir_akisi or self._http_akisi

    def _http_akisi(self, govde: dict, zaman_asimi: float):
        with requests.post(f"{self.url}/api/chat", json=govde, stream=True,
                           timeout=(3, zaman_asimi)) as r:
            r.raise_for_status()
            yield from r.iter_lines()

    def akis(self, mesajlar: list[dict], araclar: list[dict],
             iptal: threading.Event) -> Iterator["str | AracCagrisi"]:
        govde = {"model": self.model, "messages": mesajlar, "stream": True,
                 "think": False, "keep_alive": -1}
        if araclar:
            govde["tools"] = araclar
        try:
            for satir in self._satir_akisi(govde, ILK_CIKTI_SN):
                if iptal.is_set():
                    return
                if not satir:
                    continue
                olay = json.loads(satir)
                if olay.get("error"):
                    raise QwenHatasi(olay["error"])
                m = olay.get("message") or {}
                if m.get("content"):
                    yield m["content"]
                for c in m.get("tool_calls") or []:
                    f = c.get("function") or {}
                    yield AracCagrisi(f.get("name", ""), _arguman(f.get("arguments")))
                if olay.get("done"):
                    return
        except (TimeoutError, requests.Timeout) as e:
            raise QwenZamanAsimi(str(e)) from e
        except requests.RequestException as e:
            raise QwenHatasi(str(e)) from e
