#!/usr/bin/env python3
"""
tools/onbellek_isit.py — Ders öncesi önbellek ısıtma (offline)

Neden var
---------
Canlı testte ölçüldü (31.07.2026, 00:29): model kendi kararıyla
`ders_icerigi`'yi çağırdı ve sayfa seçimi önbelleksiz ilk taramaya takıldı —
sınıfın gördüğü birkaç saniye sessizlikti. İlk çağrının bedeli ders içinde
ödenemez; bu betik o bedeli **dersten önce** öder: verilen konu için sayfa
seçimini yapar ve diske yazar. Ders sırasındaki aynı çağrı sonra önbellekten
döner (ölçüm: 0,03 sn).

Ders yalnızca kitaplar üzerinden işlenir; konu her zaman öğretmenden gelir,
hiçbir yerde otomatik tespit edilmez. Bu yüzden bu betik de konuyu TAHMİN
ETMEZ — ders/sınıf/konu elle verilir (öğretmenin bir gün önce söylediği
konu). Yıllık plandan "yarının konusu" çıkarmaya çalışan eski otomatik mod
kaldırıldı: konu artık hiçbir yerde önceden yazılı durmuyor.

Kullanım
--------
    python tools/onbellek_isit.py --ders matematik --sinif 9 --konu "Kümeler" --onayla
    python tools/onbellek_isit.py --ders fizik --sinif 10 --konu "Kuvvet ve Hareket"   # kuru çalışma

Gece, örn. cron ile çalıştırılmak üzere tasarlandı — öğretmen yarının
konu(lar)ını önceden bildirdiyse.
"""

import argparse
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from actions.ders_icerigi import ders_icerigi  # noqa: E402
from core import tahta                          # noqa: E402


def _isit(ders: str, sinif: str, konu: str, onayla: bool = False) -> float:
    """Tek bir konu için önbelleği doldur. Geçen süreyi döndürür."""
    p = {"ders": ders, "sinif": sinif, "konu": konu}

    etiket = f"{ders} {sinif}. sınıf — {konu}"
    if not onayla:
        print(f"  [kuru çalışma] {etiket}")
        return 0.0

    t0 = time.time()
    sonuc = ders_icerigi(p)
    sure = time.time() - t0
    ilk_satir = (sonuc or "").splitlines()[0][:70] if sonuc else "(boş)"
    print(f"  {etiket:50} {sure:6.1f} sn  {ilk_satir}")
    return sure


def main() -> int:
    ap = argparse.ArgumentParser(description="Ders öncesi önbellek ısıtma")
    ap.add_argument("--ders", required=True, help="Ders adı (örn. matematik)")
    ap.add_argument("--sinif", help="Sınıf düzeyi (örn. 9) — verilmezse tahtanın derslik ayarından alınır")
    ap.add_argument("--konu", required=True, help="Öğretmenin verdiği konu, örn. 'Kümeler'")
    ap.add_argument("--onayla", action="store_true",
                    help="Gerçekten çalıştır (aksi hâlde yalnız ne yapılacağını yazar)")
    a = ap.parse_args()

    if not a.onayla:
        print("KURU ÇALIŞMA. Gerçekten ısıtmak için --onayla ekleyin.\n")

    sinif = a.sinif or tahta.sinif_duzeyi() or ""

    sure = 0.0
    try:
        sure = _isit(a.ders, sinif, a.konu, a.onayla)
    except Exception as e:
        print(f"  ✖ {a.ders}: {type(e).__name__}: {str(e)[:90]}")
        return 1

    if a.onayla:
        print(f"\n{sure:.1f} saniye. Ders sırasında aynı çağrı önbellekten dönecek.")
    else:
        print("Gerçekten ısıtmak için: --onayla")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
