#!/usr/bin/env python3
"""dashboard/scripts/zil_yukle.py — tahtayoklama/data/zil.json'u okulun
resmi ders saatleri kaynağından üretir/doğrular ve tahtalara dağıtır.

Kaynak: `mudur/giris cikis saatleri.jpg` — e-Okul "Anadolu Lisesi İşlemleri"
ekranının "Ders Saatleri" tablosu (2026-09-14'te elle okunup doğrulandı,
aşağıdaki VARSAYILAN_SAATLER ile BİREBİR eşleşiyor — o an zaten
tahtayoklama/data/zil.json'da olan değerlerle de aynı, yani bu script
üretimde olanı yeniden üretiyor).

Neden görsel ayrıştırma (OCR) YOK
----------------------------------
Kaynak bir PDF vektör tablosu değil (mudur/ders_programi_yukle.py'nin
okuduğu siniflar.pdf gibi), düz bir JPG ekran görüntüsü — pdfplumber işe
yaramaz. OCR eklemek yeni bir ağır bağımlılık (kök CLAUDE.md Kural 8) ve
zil çizelgesi okul saatleri değişmediği sürece yılda belki bir kez
değişiyor — orantısız. Bunun yerine görselin içeriği elle okunup
VARSAYILAN_SAATLER'e gömüldü; okul saatleri DEĞİŞTİĞİNDE ya bu sabit elle
güncellenmeli ya da --saatler ile ayrı bir JSON dosyası verilmeli
(bkz. --saatler-sablon çıktısı).

Ne yapar
--------
1. VARSAYILAN_SAATLER'i (ya da --saatler ile verilen dosyayı) doğrular
   (saat formatı, artan sıra, çakışma yok, en az 1 ders).
2. tahtayoklama/data/zil.json'u üretir — dashboard/zil.py'nin okuduğu ve
   yoklama.py'nin tahtada okuduğu AYNI şema.
3. --no-dagit verilmedikçe server/tahtalar.json'daki her tahtaya (ya da
   --tahta ile tek birine) SCP ile ~/tahtayoklama/data/zil.json olarak
   yazar — ogretmen kullanıcısı + mevcut SSH anahtarıyla
   (dashboard/ssh_istemci.py, sudo GEREKMEZ, yalnızca kendi home dizinine
   yazıyor).

Kullanım (dashboard/ dizininden)
----------------------------------
    venv/bin/python scripts/zil_yukle.py                    # üret + tüm tahtalara dağıt
    venv/bin/python scripts/zil_yukle.py --tahta 9-B         # yalnızca tek tahtaya dağıt
    venv/bin/python scripts/zil_yukle.py --no-dagit          # yalnızca data/zil.json'u üret/doğrula
    venv/bin/python scripts/zil_yukle.py --saatler yeni.json # okul saatleri değiştiğinde
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ssh_istemci  # noqa: E402

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
TAHTAYOKLAMA_DIR = DASHBOARD_DIR.parent
SERVER_DIR = TAHTAYOKLAMA_DIR.parent / "server"

TAHTALAR_JSON = SERVER_DIR / "tahtalar.json"
ZIL_JSON_CIKTI = TAHTAYOKLAMA_DIR / "data" / "zil.json"
UZAK_ZIL_YOLU = "tahtayoklama/data/zil.json"

DERS_SURESI_DK = 40
TENEFFUS_DK = 10
DERS_GUNLERI = [1, 2, 3, 4, 5]

# mudur/giris cikis saatleri.jpg'nin "Ders Saatleri" tablosundaki 8 satır,
# aynı sırayla (2026-09-14'te görselden elle okundu).
VARSAYILAN_SAATLER = [
    (1, "08:10", "08:50"),
    (2, "09:00", "09:40"),
    (3, "09:50", "10:30"),
    (4, "10:40", "11:20"),
    (5, "11:30", "12:10"),
    (6, "13:30", "14:10"),
    (7, "14:20", "15:00"),
    (8, "15:10", "15:50"),
]

_SAAT_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _dakikaya_cevir(saat: str) -> int:
    s, d = saat.split(":")
    return int(s) * 60 + int(d)


def _saatleri_dogrula(saatler: list[tuple[int, str, str]]) -> None:
    if not saatler:
        raise ValueError("En az bir ders saati gerekli.")
    onceki_bitis = -1
    for no, baslangic, bitis in saatler:
        for etiket, deger in (("başlangıç", baslangic), ("bitiş", bitis)):
            if not _SAAT_RE.match(deger):
                raise ValueError(f"{no}. ders {etiket} saati geçersiz: {deger!r} (beklenen SS:DD)")
        b, e = _dakikaya_cevir(baslangic), _dakikaya_cevir(bitis)
        if e <= b:
            raise ValueError(f"{no}. ders bitişi başlangıcından önce/aynı: {baslangic}-{bitis}")
        if b < onceki_bitis:
            raise ValueError(f"{no}. ders bir öncekiyle çakışıyor (başlangıç {baslangic} < önceki bitiş)")
        onceki_bitis = e


def _ogle_arasini_bul(dersler: list[dict]) -> dict:
    """İki ders arasındaki EN BÜYÜK boşluk öğle arası kabul edilir —
    teneffüsler (10 dk) ile karışmasın diye, sabit ders indeksine
    bağlı kalınmıyor (program 8'den az/çok derse çıkarsa da çalışır)."""
    en_buyuk: tuple[int, str, str] | None = None
    for a, b in zip(dersler, dersler[1:]):
        bosluk = _dakikaya_cevir(b["baslangic"]) - _dakikaya_cevir(a["bitis"])
        if en_buyuk is None or bosluk > en_buyuk[0]:
            en_buyuk = (bosluk, a["bitis"], b["baslangic"])
    if en_buyuk is None:
        raise ValueError("Öğle arası hesaplanamadı — en az 2 ders gerekli.")
    return {"baslangic": en_buyuk[1], "bitis": en_buyuk[2]}


def zil_json_uret(saatler: list[tuple[int, str, str]]) -> dict:
    _saatleri_dogrula(saatler)
    dersler = [{"no": no, "baslangic": b, "bitis": e} for no, b, e in saatler]
    return {
        "_aciklama": [
            "Ders saati çizelgesi — tahtayoklama'nın KENDİ kopyası, Farabi'nin",
            "client/config/zil.json'undan BAĞIMSIZ (2026-08-19, kullanıcı kararı:",
            "yoklama sistemi Farabi kurulu olmayan tahtalarda da çalışabilmeli,",
            "bu yüzden Farabi'nin config dosyasına çalışma zamanında bağımlı olamaz).",
            "Kaynak: mudur/giris cikis saatleri.jpg (e-Okul Ders Saatleri ekranı) —",
            "bkz. dashboard/scripts/zil_yukle.py. Okul zili değişirse bu script",
            "yeniden çalıştırılıp tüm tahtalara dağıtılmalı.",
        ],
        "ders_suresi_dk": DERS_SURESI_DK,
        "teneffus_dk": TENEFFUS_DK,
        "dersler": dersler,
        "ogle_arasi": _ogle_arasini_bul(dersler),
        "ders_gunleri": DERS_GUNLERI,
    }


def _tahtalari_yukle(tek_tahta: str | None) -> dict[str, dict]:
    if not TAHTALAR_JSON.exists():
        print(f"HATA: {TAHTALAR_JSON} bulunamadı.", file=sys.stderr)
        sys.exit(1)
    veri = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
    tahtalar = {ad: bilgi for ad, bilgi in veri.items() if not ad.startswith("_")}
    if tek_tahta is None:
        return tahtalar
    if tek_tahta not in tahtalar:
        print(f"HATA: '{tek_tahta}' {TAHTALAR_JSON}'da kayıtlı değil.", file=sys.stderr)
        sys.exit(1)
    return {tek_tahta: tahtalar[tek_tahta]}


async def _dagit(tahtalar: dict[str, dict]) -> None:
    for ad, bilgi in tahtalar.items():
        sonuc = await ssh_istemci.scp_gonder(
            bilgi["ip"], bilgi.get("kullanici", "ogretmen"),
            ZIL_JSON_CIKTI, UZAK_ZIL_YOLU,
        )
        if sonuc.basarili:
            print(f"  ✓ {ad} ({bilgi['ip']}): {UZAK_ZIL_YOLU} yazıldı.")
        elif sonuc.zaman_asimi:
            print(f"  ✗ {ad} ({bilgi['ip']}): zaman aşımı — ulaşılamıyor olabilir.")
        else:
            print(f"  ✗ {ad} ({bilgi['ip']}): HATA — {sonuc.stderr.decode(errors='replace').strip()[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saatler", type=Path, help="VARSAYILAN_SAATLER yerine kullanılacak [[no,baslangic,bitis],...] JSON dosyası.")
    parser.add_argument("--tahta", help="Yalnızca bu tahtaya dağıt (server/tahtalar.json'daki ad).")
    parser.add_argument("--no-dagit", action="store_true", help="Yalnızca data/zil.json'u üret/doğrula, tahtalara yazma.")
    args = parser.parse_args()

    if args.saatler:
        ham = json.loads(args.saatler.read_text(encoding="utf-8"))
        saatler = [(int(no), b, e) for no, b, e in ham]
    else:
        saatler = VARSAYILAN_SAATLER

    try:
        cikti = zil_json_uret(saatler)
    except ValueError as e:
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)

    ZIL_JSON_CIKTI.write_text(json.dumps(cikti, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ {ZIL_JSON_CIKTI} üretildi ({len(saatler)} ders, öğle arası "
          f"{cikti['ogle_arasi']['baslangic']}-{cikti['ogle_arasi']['bitis']}).")

    if args.no_dagit:
        print("--no-dagit verildi, tahtalara yazılmadı.")
        return

    tahtalar = _tahtalari_yukle(args.tahta)
    print(f"\nTahtalara dağıtılıyor ({', '.join(tahtalar)})...")
    asyncio.run(_dagit(tahtalar))


if __name__ == "__main__":
    main()
