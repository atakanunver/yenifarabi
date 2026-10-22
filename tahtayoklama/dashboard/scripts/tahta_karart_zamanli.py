"""Zamanlı ekran karartma: dashboard'daki "Ekranı karart" düğmesinin aynısını tüm tahtalarda tetikler.

systemd zamanlayıcısı çağırır (tahtayoklama/systemd/farabi-tahta-karart-*.timer). Yeni iş mantığı yok:
dashboard'un makine API'sini (`/api/ajan/eylem`, eylem=ekran_karart) kullanır, böylece düğmeyle aynı kod
çalışır ve eylem `uzaktan_denetim` tablosuna "ajan:ekran_karart" olarak yazılır.

Kullanım: python tahta_karart_zamanli.py [--kuru]   (--kuru: yalnızca hedef tahtaları listeler)
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ADRES = "http://127.0.0.1/api/ajan"
ANAHTAR_YOLU = Path(__file__).resolve().parent.parent / "config" / "ajan.json"
ZAMAN_ASIMI = 300  # sn; ulaşılamayan tahtada SSH beklemesi uzayabilir


def _istek(yol: str, anahtar: str, govde: dict | None = None) -> dict:
    veri = None if govde is None else json.dumps(govde).encode("utf-8")
    istek = urllib.request.Request(
        ADRES + yol, data=veri, headers={"X-Farabi-Ajan-Key": anahtar, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def main(kuru: bool) -> int:
    anahtar = json.loads(ANAHTAR_YOLU.read_text(encoding="utf-8"))["anahtar"]
    adlar = [t["ad"] for t in _istek("/tahtalar", anahtar)["tahtalar"]]
    print(f"hedef tahtalar: {', '.join(adlar)}")
    if kuru:
        print("--kuru: eylem gönderilmedi.")
        return 0
    sonuclar = _istek("/eylem", anahtar, {"eylem": "ekran_karart", "tahtalar": adlar})["sonuclar"]
    for s in sonuclar:
        print(f"{s['tahta']}: {'tamam' if s['basarili'] else 'BASARISIZ'} ({s['sebep']})")
    return 0 if any(s["basarili"] for s in sonuclar) else 1


if __name__ == "__main__":
    try:
        sys.exit(main("--kuru" in sys.argv[1:]))
    except (urllib.error.URLError, OSError, KeyError, ValueError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        sys.exit(2)
