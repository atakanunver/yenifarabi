#!/usr/bin/env python3
"""okul_ana -> tahta anlık görüntüsü (zil.json, ders_programi.json) üreticisi.

Çıktı biçimi mevcut betiklerle BAYT DÜZEYİNDE aynı (zil: sonda '\\n'; program: yok).
Anahtar sırası jsonb'ye güvenmez (jsonb anahtarları yeniden sıralar) — açıkça kurulur.
`yayin.yayinla` bu modülü 'json' hedefi olarak kullanır; --kontrol canlı dosyalarla karşılaştırır.
"""

import json
import sys

from okul_ana_yayin import F, KOPYA, sorgu

GUN_ADI = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma"}


def veri_dizini():
    from pathlib import Path

    return Path(KOPYA) / "data" if KOPYA else F / "tahtayoklama/data"


def _yil():
    return int(sorgu("select id from okul_ana.ogretim_yili where aktif")[0][0])


def ayarlar(yil):
    return {
        k: json.loads(v)
        for k, v in sorgu(
            f"select anahtar,deger::text from okul_ana.ayar where yil_id={yil}"
        )
    }


def zil_json_uret():
    yil = _yil()
    a = ayarlar(yil)
    dersler = [
        {"no": int(no), "baslangic": b[:5], "bitis": e[:5]}
        for no, b, e in sorgu(
            f"select ders_no,baslangic,bitis from okul_ana.zil "
            f"where yil_id={yil} and gun_tipi='normal' order by ders_no"
        )
    ]
    ogle = a["ogle_arasi"]
    cikti = {
        "_aciklama": a["_aciklama"],
        "ders_suresi_dk": a["ders_suresi_dk"],
        "teneffus_dk": a["teneffus_dk"],
        "dersler": dersler,
        "ogle_arasi": {"baslangic": ogle["baslangic"], "bitis": ogle["bitis"]},
        "ders_gunleri": a["ders_gunleri"],
    }
    return json.dumps(cikti, ensure_ascii=False, indent=2) + "\n"


def program_json_uret():
    yil = _yil()
    a = ayarlar(yil)
    siniflar = {}
    for sad, gun, no, ders in sorgu(
        f"select s.ad,p.gun,p.ders_no,p.ders from okul_ana.ders_programi p "
        f"join okul_ana.sinif s on s.id=p.sinif_id where p.yil_id={yil} "
        f"order by s.seviye, s.ad, p.gun, p.ders_no"
    ):
        siniflar.setdefault(sad, {}).setdefault(GUN_ADI[int(gun)], {})[str(int(no))] = (
            ders
        )
    cikti = {
        "_kaynak": a["program_kaynak"],
        "_uretim_araci": a["program_uretim_araci"],
        "siniflar": siniflar,
    }
    return json.dumps(cikti, ensure_ascii=False, indent=2)


DOSYALAR = {"zil.json": zil_json_uret, "ders_programi.json": program_json_uret}


def kontrol():
    tamam = True
    for ad, uret in DOSYALAR.items():
        yeni = uret().encode("utf-8")
        eski = (veri_dizini() / ad).read_bytes()
        ok = yeni == eski
        tamam &= ok
        print(("OK   " if ok else "FAIL ") + ad + f"  [{len(yeni)} / {len(eski)} bayt]")
    return tamam


if __name__ == "__main__":
    sys.exit(0 if kontrol() else 1)
