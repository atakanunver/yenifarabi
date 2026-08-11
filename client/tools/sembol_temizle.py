#!/usr/bin/env python3
"""
tools/sembol_temizle.py — Dönüştürülmüş kitap metnindeki şüpheli sembolleri
yapay zeka desteğiyle temizler (offline hazırlık, API kullanır, ÜCRETLİDİR)

Neden var
---------
`tools/kitap_metin.py` MEB kitaplarındaki bozuk '#' ve '$' işaretlerini
KASITLI olarak tahmin etmiyor (bkz. o dosyanın modül dokümanı): '#' ≤, ≥ ya
da ≠ olabilir, '$' ise · ya da ≥. Bir eşitsizliğin yönünü yanlış öğretmek,
sembolü hiç göstermemekten kötüdür — o yüzden `kitap_metin.py` bu işaretleri
DEĞİŞTİRMEDEN sayar, `ders_icerigi` de modele "bu sayfada semboller şüpheli,
sözle anlat" uyarısı ekler.

Bu betik, öğretmenin isteğiyle (UI'daki "ŞÜPHELİ SEMBOLLERİ TEMİZLE" düğmesi
ya da elle) devreye giren AYRI bir adımdır: her şüpheli sayfa metnini bağlamı
ile birlikte modele gösterir ve YALNIZ emin olduğu değişiklikleri ister. Model
emin değilse işareti OLDUĞU GİBİ bırakır — kör bir "hepsini tahmin et" değil.
`kitap_metin.py`'nin iki katmanlı ilkesini bozmaz, üçüncü bir katman ekler ve
bu katman insan onayıyla (--onayla) ve API çağrısıyla çalışır.

`tools/dogrula.py`'ye KASITLI olarak gömülmedi: dogrula.py ücretsiz, anında
çalışan bir doğrulama kapısı; bu betik ücretli ve dakikalar sürebilir. İkisini
aynı komutta karıştırmak "doğrulama çalıştırdım" derken habersizce API parası
harcamak demek olurdu.

Gemini burada YOK: Gemini artık yalnızca canlı ses oturumunda kullanılıyor
(main.py) — bkz. CLAUDE.md, "Provider notes". Sembol
düzeltme core/saglayicilar.py'nin 'sembol_duzelt' zincirinden geçer (akıl
yürütmesi matematik/belirsizlik çözümüne uygun sağlayıcılar öncelikli).

Kullanım
--------
    python tools/sembol_temizle.py                       # kuru çalışma, tüm kitaplar
    python tools/sembol_temizle.py matematik_9 --onayla   # tek kitap, gerçekten çalıştır
    python tools/sembol_temizle.py --onayla                # tüm kitaplar, gerçekten çalıştır

Ders anında ÇALIŞMAZ — yalnız `tools/kitap_metin.py` ile dönüştürme
tamamlandıktan sonra, elle ya da UI düğmesinden tetiklenir.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

METIN_DIZINI = BASE_DIR / "icerik" / "metin"

SUPHELI = re.compile(r'[a-zA-Z0-9]\s?[#$]\s?[a-zA-Z0-9]')

ISTEM_SABLONU = """Aşağıda bir ders kitabı sayfasının OCR/metin çıkarımından geldi. \
Bu metinde '#' ve '$' işaretleri, kaynak PDF'in font kodlaması bozuk olduğu için \
belirsiz kalmış matematik sembolleridir: '#' işareti ≤, ≥ ya da ≠ olabilir; '$' \
işareti · (çarpma) ya da ≥ olabilir.

GÖREVİN: Yalnızca cümlenin matematiksel bağlamından YÜZDE YÜZ EMİN olduğun \
işaretleri doğru sembolle değiştir. Emin olmadığın her işareti OLDUĞU GİBİ, \
değiştirmeden bırak — bir eşitsizliğin yönünü yanlış yazmak, hiç \
değiştirmemekten kötüdür.

Metni AYNEN, yalnızca emin olduğun işaretleri değiştirerek geri ver. Başka \
hiçbir şey ekleme, açıklama yazma, yalnızca düzeltilmiş sayfa metnini döndür.

SAYFA METNİ:
---
{sayfa_metni}
---"""


def _json_oku(yol: Path):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sayfayi_temizle(sayfa_metni: str) -> str:
    from core import saglayicilar
    return saglayicilar.metin_uret("sembol_duzelt", ISTEM_SABLONU.format(sayfa_metni=sayfa_metni))


def kitabi_temizle(kitap_json: Path, onayla: bool) -> dict:
    veri = _json_oku(kitap_json)
    if not veri or not veri.get("sayfalar"):
        return {"kitap": kitap_json.name, "hata": "okunamadı ya da boş"}

    supheli_sayfalar = [(no, kayit) for no, kayit in veri["sayfalar"].items()
                        if int(kayit.get("supheli") or 0) > 0]

    if not supheli_sayfalar:
        return {"kitap": veri.get("kitap", kitap_json.name), "sayfa": 0, "degisen": 0}

    if not onayla:
        return {"kitap": veri.get("kitap", kitap_json.name),
                "sayfa": len(supheli_sayfalar), "degisen": None}

    degisen_sayfa = 0
    yeni_supheli_toplam = 0

    for no, kayit in supheli_sayfalar:
        ham = kayit.get("metin", "")
        eski_supheli = int(kayit.get("supheli") or 0)   # kayit["supheli"] altta üzerine
                                                          # yazılmadan ÖNCE yakalanmalı —
                                                          # aksi hâlde karşılaştırma kendi
                                                          # kendisiyle olur ve hep False çıkar
                                                          # (ölçüldü: fizik-10.pdf s.88 gerçekte
                                                          # 1→0 düzeldi ama "0 düzeltildi" dendi)
        try:
            temiz = _sayfayi_temizle(ham)
        except Exception as e:
            print(f"    s.{no}: AI çağrısı başarısız ({type(e).__name__}: {e}), atlanıyor")
            yeni_supheli_toplam += eski_supheli
            continue

        kalan = len(SUPHELI.findall(temiz))
        if temiz and temiz != ham:
            kayit["metin"] = temiz
            kayit["supheli"] = kalan
            kayit["ai_temizlendi"] = True
            if kalan < eski_supheli:
                degisen_sayfa += 1
        yeni_supheli_toplam += kalan

    veri["supheli_sembol"] = sum(int(k.get("supheli") or 0) for k in veri["sayfalar"].values())
    kitap_json.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")

    return {"kitap": veri.get("kitap", kitap_json.name),
            "sayfa": len(supheli_sayfalar), "degisen": degisen_sayfa}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dönüştürülmüş kitap metnindeki şüpheli sembolleri AI ile temizler")
    ap.add_argument("kitaplar", nargs="*",
                    help="Belirli kitap dosya adı/stem'i (boşsa icerik/metin altındaki hepsi)")
    ap.add_argument("--onayla", action="store_true",
                    help="Gerçekten çalıştır (API çağrısı yapar, ücretlidir). "
                         "Aksi hâlde yalnız kaç sayfa etkileneceğini yazar.")
    a = ap.parse_args()

    if not METIN_DIZINI.exists():
        print("icerik/metin/ yok — önce tools/kitap_metin.py çalıştırılmalı.")
        return 1

    if a.kitaplar:
        hedefler = [METIN_DIZINI / f"{Path(k).stem}.json" for k in a.kitaplar]
        hedefler = [h for h in hedefler if h.exists()]
    else:
        hedefler = sorted(METIN_DIZINI.glob("*.json"))

    if not hedefler:
        print("Temizlenecek kitap bulunamadı.")
        return 1

    if not a.onayla:
        print("KURU ÇALIŞMA — hiçbir API çağrısı yapılmayacak. "
              "Gerçekten temizlemek için --onayla ekleyin.\n")

    toplam_sayfa = 0
    for hedef in hedefler:
        t0 = time.time()
        try:
            sonuc = kitabi_temizle(hedef, a.onayla)
        except Exception as e:
            print(f"  ✖ {hedef.name}: {type(e).__name__}: {str(e)[:90]}")
            continue
        if sonuc.get("hata"):
            print(f"  ✖ {sonuc['kitap']}: {sonuc['hata']}")
            continue
        if sonuc["sayfa"] == 0:
            print(f"  = {sonuc['kitap']}: şüpheli sembol yok")
            continue
        toplam_sayfa += sonuc["sayfa"]
        if sonuc["degisen"] is None:
            print(f"  [kuru çalışma] {sonuc['kitap']}: {sonuc['sayfa']} şüpheli sayfa")
        else:
            sure = time.time() - t0
            print(f"  {sonuc['kitap']}: {sonuc['sayfa']} sayfa tarandı, "
                  f"{sonuc['degisen']} sayfa düzeltildi ({sure:.1f} sn)")

    if not a.onayla:
        print(f"\nToplam {toplam_sayfa} şüpheli sayfa. Gerçekten temizlemek için: --onayla")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
