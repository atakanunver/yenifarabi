"""Zamanlı tahta eylemi: dashboard'un makine API'si (`/api/ajan/eylem`) üzerinden seçilen eylemi tahtalarda çalıştırır.

`farabi-zamanlayici olustur` ile üretilen `farabi-gorev-*.service` birimleri çağırır. Mantık yok: düğmelerle aynı kod
(`uzaktan_yonetim.EYLEMLER`) çalışır, eylem `uzaktan_denetim`'e "ajan:<eylem>" olarak yazılır.

Kullanım: python tahta_eylem_zamanli.py <eylem> <tahta1,tahta2|hepsi> [--kuru]
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ADRES = "http://127.0.0.1/api/ajan"
ANAHTAR_YOLU = Path(__file__).resolve().parent.parent / "config" / "ajan.json"
ZAMAN_ASIMI = 300  # sn; ulaşılamayan tahtada SSH beklemesi uzayabilir
EYLEMLER = ("ekran_karart", "ekran_kaldir", "yoklama_kapat", "chrome_kapat")


def _istek(yol: str, anahtar: str, govde: dict | None = None) -> dict:
    veri = None if govde is None else json.dumps(govde).encode("utf-8")
    istek = urllib.request.Request(
        ADRES + yol, data=veri, headers={"X-Farabi-Ajan-Key": anahtar, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def main(eylem: str, tahtalar: str, kuru: bool) -> int:
    if eylem not in EYLEMLER:
        print(f"HATA: bilinmeyen eylem: {eylem}", file=sys.stderr)
        return 2
    anahtar = json.loads(ANAHTAR_YOLU.read_text(encoding="utf-8"))["anahtar"]
    if tahtalar == "hepsi":
        adlar = [t["ad"] for t in _istek("/tahtalar", anahtar)["tahtalar"]]
    else:
        adlar = [a for a in tahtalar.split(",") if a]
    print(f"{eylem}: {', '.join(adlar)}")
    if kuru:
        print("--kuru: eylem gönderilmedi.")
        return 0
    sonuclar = _istek("/eylem", anahtar, {"eylem": eylem, "tahtalar": adlar})["sonuclar"]
    for s in sonuclar:
        print(f"{s['tahta']}: {'tamam' if s['basarili'] else 'BASARISIZ'} ({s['sebep']})")
    return 0 if any(s["basarili"] for s in sonuclar) else 1


if __name__ == "__main__":
    argumanlar = [a for a in sys.argv[1:] if a != "--kuru"]
    if len(argumanlar) != 2:
        print("kullanım: tahta_eylem_zamanli.py <eylem> <tahtalar|hepsi> [--kuru]", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(argumanlar[0], argumanlar[1], "--kuru" in sys.argv[1:]))
    except (urllib.error.URLError, OSError, KeyError, ValueError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(2)
