#!/usr/bin/env python3
"""
tools/dogrula.py — İçerik doğrulama kapısı (offline, ders anında değil)

Neden var
---------
Kitap indeksi sessizce üretiliyor ve hatası SINIFTA ortaya çıkıyordu. Ölçülen
örnek: `fizik-10.pdf` indekslenmiş, sayfa aralıkları doğru, ama dört ünitenin
de adı "ÖLÇME VE DEĞERLENDİRME" (yayıncının sayfa üstbilgisi). `ders_icerigi`
"kitap bölümü eşleşmedi" diyor; model de kitapsız anlatmaya devam ediyor. Yani
veri kalitesi hatası, derste doğaçlama olarak görünüyor.

Bu betik aynı hatayı ÜRETİM ANINDA yakalar ve ne yapılacağını söyler. Ders
yalnızca kitaplar üzerinden işlenir (yıllık plan bu zincirde yok); bu yüzden
burada yalnızca kitap indeksi ve elle eşlemeler doğrulanır.

Şüpheli sembollerin AI ile temizlenmesi bu betiğin işi DEĞİL — bkz.
tools/sembol_temizle.py (ayrı, isteğe bağlı, API çağrısı yapan betik).

Kullanım
--------
    python tools/dogrula.py                    # kitap indeksi + eşlemeler
    python tools/dogrula.py --sessiz           # yalnız özet ve çıkış kodu

Çıkış kodu: 0 = geçti, 1 = en az bir RED var (CI/kurulum betiği için).
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from actions.ders_icerigi import _elle_eslemeler, _json_oku, KITAP_PATH  # noqa: E402

# Bir bölüm kitabın bu kadarından fazlasını kaplıyorsa indeks işe yaramaz:
# sayfa seçimi bütün kitabı taramak zorunda kalır (ölçüm: 233 sayfa = 55,4 sn).
TEK_BOLUM_ORANI = 0.70

GECTI, UYARI, RED = "GEÇTİ", "UYARI", "RED"


def _satir(durum: str, baslik: str, aciklama: str = "") -> dict:
    return {"durum": durum, "baslik": baslik, "aciklama": aciklama}


def kitaplari_dogrula(kitaplar: dict) -> list[dict]:
    sonuc = []
    if not kitaplar:
        return [_satir(RED, "kitaplar.json okunamadı",
                       "python tools/kitap_index.py kitaplar/ --json icerik/kitaplar.json")]

    eslenen_kitaplar = {e.get("kitap") for e in _elle_eslemeler()}

    for k in kitaplar.get("kitaplar", []):
        dosya = k.get("dosya", "?")
        bolumler = k.get("bolumler", [])
        sayfa_sayisi = k.get("sayfa_sayisi") or 0
        elle_var = dosya in eslenen_kitaplar

        if not bolumler:
            sonuc.append(_satir(
                GECTI if elle_var else RED,
                f"{dosya}: hiç bölüm çıkarılamadı",
                "Elle eşleme mevcut." if elle_var else
                "Kitap indekslenemedi; ders içeriği getirilemez."))
            continue

        adlar = [(b.get("ad") or "").strip().upper() for b in bolumler]
        if len(bolumler) > 1 and len(set(adlar)) == 1:
            sonuc.append(_satir(
                GECTI if elle_var else RED,
                f"{dosya}: {len(bolumler)} bölümün adı da aynı ({adlar[0][:40]!r})",
                "Elle eşleme mevcut." if elle_var else
                "Yayıncı üstbilgisi ünite adı taşımıyor. Konu/tema ile asla "
                f"eşleşmez. Çözüm: icerik/eslemeler/{Path(dosya).stem}.json"))

        for b in bolumler:
            try:
                kapsam = (int(b["son_sayfa"]) - int(b["ilk_sayfa"]) + 1)
            except Exception:
                continue
            if sayfa_sayisi and kapsam / sayfa_sayisi > TEK_BOLUM_ORANI:
                sonuc.append(_satir(
                    GECTI if elle_var else RED,
                    f"{dosya}: tek bölüm kitabın %{100*kapsam/sayfa_sayisi:.0f}'ini kaplıyor "
                    f"(s.{b['ilk_sayfa']}-{b['son_sayfa']})",
                    "Elle eşleme mevcut." if elle_var else
                    "Bölüm sınırları çıkarılamamış. Sayfa seçimi bütün kitabı "
                    "tarar ve ders ortasında saniyeler sürer."))
    return sonuc


def eslemeleri_dogrula() -> list[dict]:
    sonuc = []
    for esleme in _elle_eslemeler():
        dosya = esleme.get("kitap", "?")
        for b in esleme.get("bolumler", []):
            try:
                ilk, son = int(b["ilk_sayfa"]), int(b["son_sayfa"])
            except Exception:
                sonuc.append(_satir(RED, f"{dosya}: bölüm sayfa numarası okunamadı",
                                    json.dumps(b, ensure_ascii=False)[:120]))
                continue
            if ilk > son:
                sonuc.append(_satir(RED, f"{dosya}: ilk_sayfa > son_sayfa ({ilk}>{son})"))
            if not (b.get("temalar") or b.get("ad")):
                sonuc.append(_satir(RED, f"{dosya}: bölümde tema yok"))
        if esleme.get("bolumler"):
            sonuc.append(_satir(GECTI, f"{dosya}: {len(esleme['bolumler'])} elle eşleme"))
    return sonuc


def main() -> int:
    ap = argparse.ArgumentParser(description="Farabi içerik doğrulama kapısı")
    ap.add_argument("--sessiz", action="store_true", help="Yalnız özet")
    a = ap.parse_args()

    kitaplar = _json_oku(KITAP_PATH)

    satirlar = kitaplari_dogrula(kitaplar) + eslemeleri_dogrula()

    if not a.sessiz:
        isaret = {GECTI: "✔", UYARI: "▲", RED: "✖"}
        for s in satirlar:
            print(f"{isaret[s['durum']]} {s['baslik']}")
            if s["aciklama"]:
                for satir in s["aciklama"].split("\n"):
                    print(f"    {satir}")

    red = sum(1 for s in satirlar if s["durum"] == RED)
    uyari = sum(1 for s in satirlar if s["durum"] == UYARI)
    print(f"\nÖzet: {len(satirlar)} kontrol · {red} RED · {uyari} UYARI")
    if red:
        print("RED olan kitaplar yayımlanmamalı; elle eşleme yazın "
              "(icerik/eslemeler/<kitap>.json).")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
