"""Geçen haftanın KESİN birincileri için kartı üretip veri/gorseller/ arşivine bırakır.

Tahtaya GÖNDERMEZ (gönderim yalnız panelden, elle). Idempotent: o hafta için kart varsa üretmez (`--zorla` ile yeniden).
Arka plan: panelde onaylı arka plan varsa o, yoksa varsayılan prompt ile AI'dan (günlük üretim sınırına sayılır).
Systemd: systemd/farabi-gorsel-hafta.timer (Pazartesi 06:10). Log satırlarında öğrenci adı yok.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gorsel


def calistir(zorla: bool = False) -> int:
    try:
        veri = gorsel.hafta_kazananlari(None, gecici=False)
    except gorsel.GorselHatasi as e:
        print(f"HATA: kazananlar alınamadı: {e}")
        return 1
    hafta = str(veri.get("hafta") or "")
    kategoriler = veri.get("kategoriler") or {}
    if not veri.get("kesin") or not any(kategoriler.get(k) for k in ("maraton", "etkinlik")):
        print(f"aday yok (hafta {hafta})")
        return 0
    durum = gorsel.durum_oku()
    var = durum["hafta_kartlari"].get(hafta)
    if var and (gorsel.GORSEL_DIZINI / var[:10] / var).is_file() and not zorla:
        print(f"hafta {hafta}: kart zaten var ({var}), atlandı")
        return 0
    try:
        onayli = durum.get("onayli_arka_plan")
        if onayli and Path(onayli).is_file():
            arka = Path(onayli)
        else:
            if not gorsel.uretim_hakki_al():
                print(f"HATA: günlük {gorsel.GUNLUK_SINIR} üretim sınırı dolu")
                return 1
            arka = gorsel.arsivle("arka-plan", gorsel.ai_arka_plan(gorsel.VARSAYILAN_PROMPT))
        yol = gorsel.kart_uret_ve_arsivle(kategoriler, "hafta-kart", arka)
    except gorsel.GorselHatasi as e:
        print(f"HATA: {e}")
        return 1
    gorsel.durum_guncelle(hafta_kartlari={**gorsel.durum_oku()["hafta_kartlari"], hafta: yol.name})
    print(f"hafta {hafta}: kart üretildi ({yol.name})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Geçen haftanın birincileri için kart üretir (tahtaya göndermez).")
    ap.add_argument("--zorla", action="store_true", help="o hafta için kart olsa da yeniden üret")
    return calistir(ap.parse_args(argv).zorla)


if __name__ == "__main__":
    sys.exit(main())
