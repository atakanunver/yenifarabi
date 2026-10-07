"""Farabi 2.0 uçtan uca gecikme ölçümü (ses → STT → Qwen → TTS). Sınıfa gitmeden önce.

Her test cümlesi önce farabi2-ses ile "öğretmen sesi"ne çevrilir (16 kHz),
sonra gerçek hat koşar: /stt → Qwen akışı (araçlarla) → ilk cümle /tts.
Ölçülen: stt_ms, ilk_token_ms, ilk_ses_ms (STT başı → ilk sesin hazır olması),
araç doğruluğu (beklenen ya da alternatif). Spec hedefleri: sohbet ilk ses
≤ 3000 ms, araçlı turda kalıp ≤ 1000 ms sonra, doğruluk ≥ %90.

Kullanım: ~/farabi/benchmark/venv/bin/python v2_uctan_uca.py
"""
import io
import json
import statistics
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import v2_arac_testi as t  # noqa: E402

SES = "http://bilgehan.local:8060"
OLLAMA = "http://localhost:11434"
YEREL_KURALLAR = (
    "\n\n[YEREL SES KURALLARI] Konuşma diliyle, en fazla 2-3 kısa cümleyle cevap ver. "
    "Yıldız, liste, başlık, numaralandırma, emoji KULLANMA — metin seslendirilecek. "
    "Selamlaşma, hal hatır, teşekkür ve genel sohbette HİÇBİR ARAÇ ÇAĞIRMA; doğrudan cevap ver. "
    "Araç yalnızca öğretmen açıkça bir iş istediğinde (kitaba bak, ekrandaki soruyu oku, video aç, "
    "yoklama al) çağrılır."
)
KALIP = "Hemen bakıyorum hocam."


def post(url, veri, tip):
    r = urllib.request.Request(url, data=veri, headers={"Content-Type": tip})
    with urllib.request.urlopen(r, timeout=60) as y:
        return y.read()


def tts(metin):
    return post(f"{SES}/tts", json.dumps({"metin": metin}).encode(), "application/json")


def yeniden_ornekle_16k(wav24: bytes) -> bytes:
    with wave.open(io.BytesIO(wav24)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
    n = int(len(x) * 16000 / sr)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("<i2")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(y.tobytes())
    return b.getvalue()


def bir_tur(cumle, kip, beklenen, alternatif, araclar):
    ogretmen = yeniden_ornekle_16k(tts(cumle))
    t0 = time.perf_counter()
    metin = json.loads(post(f"{SES}/stt", ogretmen, "audio/wav"))["metin"]
    stt_ms = (time.perf_counter() - t0) * 1000
    govde = {"model": "qwen3.8:27b", "stream": True, "think": False, "keep_alive": -1,
             "tools": araclar,
             "messages": [{"role": "system", "content": t.PROMPTLAR[kip] + YEREL_KURALLAR},
                          {"role": "user", "content": metin}]}
    r = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(govde).encode(),
                               headers={"Content-Type": "application/json"})
    ilk_token = ilk_ses = None
    tampon, secilen = "", None
    with urllib.request.urlopen(r, timeout=120) as y:
        for satir in y:
            o = json.loads(satir)
            m = o.get("message") or {}
            if (m.get("content") or m.get("tool_calls")) and ilk_token is None:
                ilk_token = (time.perf_counter() - t0) * 1000
            if m.get("tool_calls") and secilen is None:
                secilen = m["tool_calls"][0]["function"]["name"]
                if ilk_ses is None:
                    tts(KALIP)
                    ilk_ses = (time.perf_counter() - t0) * 1000
            tampon += m.get("content") or ""
            if ilk_ses is None and len(tampon) >= 12 and any(p in tampon for p in ".!?"):
                tts(tampon.strip())
                ilk_ses = (time.perf_counter() - t0) * 1000
            if o.get("done"):
                break
    if ilk_ses is None and tampon.strip():
        tts(tampon.strip())
        ilk_ses = (time.perf_counter() - t0) * 1000
    return {"cumle": cumle, "kip": kip, "stt_metin": metin, "stt_ms": round(stt_ms),
            "ilk_token_ms": round(ilk_token or -1), "ilk_ses_ms": round(ilk_ses or -1),
            "beklenen": beklenen, "alternatif": alternatif, "secilen": secilen,
            "dogru": secilen in {beklenen, alternatif} if beklenen else secilen is None}


def main():
    araclar = {k: t.build_tools_payload(k) for k in ("ogretmenli", "talimat")}
    sonuc = []
    for cumle, kip, beklenen, alternatif, *_ in t.TEST_CUMLELERI:
        r = bir_tur(cumle, kip, beklenen, alternatif, araclar[kip])
        print(json.dumps(r, ensure_ascii=False), flush=True)
        sonuc.append(r)
    sohbet = [r["ilk_ses_ms"] for r in sonuc if r["beklenen"] is None]
    aracli = [r["ilk_ses_ms"] for r in sonuc if r["beklenen"] is not None]
    ozet = {"n": len(sonuc),
            "stt_medyan_ms": statistics.median(r["stt_ms"] for r in sonuc),
            "sohbet_ilk_ses_medyan_ms": statistics.median(sohbet) if sohbet else None,
            "aracli_ilk_ses_medyan_ms": statistics.median(aracli) if aracli else None,
            "dogruluk": round(sum(r["dogru"] for r in sonuc) / len(sonuc), 3)}
    print(json.dumps(ozet, ensure_ascii=False))
    yol = Path(__file__).parent / "reports" / f"v2_uctan_uca_{time.strftime('%Y%m%d_%H%M%S')}.json"
    yol.parent.mkdir(exist_ok=True)
    yol.write_text(json.dumps({"ozet": ozet, "sonuc": sonuc}, ensure_ascii=False, indent=2))
    print(f"rapor: {yol}")


if __name__ == "__main__":
    main()
