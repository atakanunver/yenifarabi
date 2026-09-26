"""voice_node/araclar_cli/wav_istemci.py — Faz 1b test istemcisi.

Bir WAV dosyasını GERÇEK tel protokolüyle (bkz. `serializer.py` docstring'i)
ses düğümüne gönderir, cevabı `.wav` olarak kaydeder ve zamanlama/araç-çağrısı
özetini JSON olarak basar. Tahtanın PyQt istemcisinin (Faz 1c, henüz
yazılmadı) yerini TUTMAZ — yalnızca ölçüm/hata ayıklama içindir.

⚠️ `arac_cagri` mesajlarına verilen `arac_sonuc` SİMÜLE edilmiştir (aşağıdaki
`SAHTE_ARAC_SONUCU`) — gerçek tahta davranışını YANSITMAZ, yalnızca
`pdf_sayfa`/`yks_sorulari` gibi tahta araçlarının 10/15 sn'lik zaman aşımına
takılıp testi bloklamaması için var.

Kullanım:
    venv/bin/python araclar_cli/wav_istemci.py \\
        --url ws://127.0.0.1:8030/ses --board-key <anahtar> \\
        --kip ogretmenli --ders Biyoloji \\
        --girdi tests/audio/soru1.wav --cikti /tmp/cevap1.wav
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import wave

import websockets

SAHTE_ARAC_SONUCU = {"durum": "ok", "not": "wav_istemci sentetik sonuç — gerçek tahta değil"}

CIKIS_ORNEKLEME_HIZI = 24000
SESSIZLIK_ZAMAN_ASIMI_SN = 2.0
GENEL_ZAMAN_ASIMI_SN = 30.0


def _wav_oku(yol: str) -> tuple[bytes, int]:
    with wave.open(yol, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{yol}: mono 16-bit PCM WAV bekleniyor")
        return w.readframes(w.getnframes()), w.getframerate()


def _wav_yaz(yol: str, pcm: bytes, ornekleme_hizi: int) -> None:
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ornekleme_hizi)
        w.writeframes(pcm)


async def _calistir(
    *,
    url: str,
    board_key: str,
    kip: str,
    ders: str | None,
    girdi_wav: str,
    cikti_wav: str,
    ptt_parca_bayt: int = 3200,
) -> dict:
    pcm, sr = _wav_oku(girdi_wav)
    if sr != 16000:
        print(
            f"UYARI: '{girdi_wav}' {sr} Hz — 16000 Hz bekleniyor, ses OLDUĞU GİBİ "
            "gönderiliyor (gerçek ölçüm için önce 16 kHz mono'ya yeniden örnekleyin).",
            file=sys.stderr,
        )

    tam_url = f"{url}?kip={kip}"
    if ders:
        tam_url += f"&ders={ders}"

    zamanlar: dict[str, float] = {}
    arac_cagrilari: list[dict] = []
    transkript_metni: str | None = None
    metrikler: dict[str, int] = {}
    ses_cikti = bytearray()
    ilk_ses_zamani: float | None = None

    async with websockets.connect(
        tam_url,
        additional_headers={"X-Farabi-Board-Key": board_key},
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({"tip": "ptt_basla"}))
        for i in range(0, len(pcm), ptt_parca_bayt):
            await ws.send(pcm[i : i + ptt_parca_bayt])
        ptt_bitir_zamani = time.monotonic()
        await ws.send(json.dumps({"tip": "ptt_bitir"}))
        zamanlar["ptt_bitir_gonderildi"] = ptt_bitir_zamani

        genel_baslangic = time.monotonic()
        while True:
            if time.monotonic() - genel_baslangic > GENEL_ZAMAN_ASIMI_SN:
                print("UYARI: genel zaman aşımı, bekleme sonlandırılıyor", file=sys.stderr)
                break
            try:
                mesaj = await asyncio.wait_for(ws.recv(), timeout=SESSIZLIK_ZAMAN_ASIMI_SN)
            except TimeoutError:
                if ilk_ses_zamani is not None:
                    break  # ses geldi ve sessizlik başladı — tur bitti say
                continue  # henüz ses yok (uzun tool_call olabilir), beklemeye devam

            simdi = time.monotonic()
            if isinstance(mesaj, bytes | bytearray):
                if ilk_ses_zamani is None:
                    ilk_ses_zamani = simdi
                    zamanlar["ilk_ses_bayti"] = simdi
                ses_cikti.extend(mesaj)
                continue

            veri = json.loads(mesaj)
            tip = veri.get("tip")
            if tip == "transkript":
                transkript_metni = veri.get("metin")
                zamanlar.setdefault("transkript", simdi)
            elif tip == "metrik":
                # SON değer tutulur (İLK değil): `gozlemci.py` bağlantı
                # açılışında bazı işlemcilerin sıfır değerli bir başlangıç
                # metriği yayınladığını gösterdi (canlı testte bulundu) —
                # anlamlı olan, turun SONUNDA raporlanan nihai süre.
                asama = veri.get("asama")
                if asama:
                    metrikler[asama] = veri.get("ms")
            elif tip == "arac_cagri":
                arac_cagrilari.append(veri)
                await ws.send(json.dumps({
                    "tip": "arac_sonuc", "id": veri.get("id"), "sonuc": dict(SAHTE_ARAC_SONUCU),
                }))
            elif tip == "hata":
                print("HATA:", veri.get("mesaj"), file=sys.stderr)

    _wav_yaz(cikti_wav, bytes(ses_cikti), CIKIS_ORNEKLEME_HIZI)

    uctan_uca_ms = (
        int((ilk_ses_zamani - ptt_bitir_zamani) * 1000) if ilk_ses_zamani is not None else None
    )

    return {
        "girdi_wav": girdi_wav,
        "cikti_wav": cikti_wav,
        "transkript": transkript_metni,
        "metrikler_ms": metrikler,
        "arac_cagrilari": arac_cagrilari,
        "uctan_uca_ms": uctan_uca_ms,
        "cikti_ses_bayt": len(ses_cikti),
    }


def main() -> None:
    ayrıştırıcı = argparse.ArgumentParser(description=__doc__)
    ayrıştırıcı.add_argument("--url", default="ws://127.0.0.1:8030/ses")
    ayrıştırıcı.add_argument("--board-key", required=True)
    ayrıştırıcı.add_argument("--kip", default="ogretmenli")
    ayrıştırıcı.add_argument("--ders", default=None)
    ayrıştırıcı.add_argument("--girdi", required=True, help="Girdi WAV (mono 16-bit, 16 kHz)")
    ayrıştırıcı.add_argument("--cikti", required=True, help="Çıktı WAV yolu (24 kHz üretilir)")
    args = ayrıştırıcı.parse_args()

    sonuc = asyncio.run(
        _calistir(
            url=args.url, board_key=args.board_key, kip=args.kip, ders=args.ders,
            girdi_wav=args.girdi, cikti_wav=args.cikti,
        )
    )
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
