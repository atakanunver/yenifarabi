#!/usr/bin/env python3
"""
tools/kitap_ozet.py — Dönüştürülmüş kitaplar için özet + zenginleştirme
çıkarır (offline hazırlık, API kullanır, ÜCRETLİDİR)

Neden var
---------
Ders yalnızca kitap sayfalarından işleniyor (yıllık plan yok); ama tek
başına bir bölümün sayfa metni bazen dersin genel çerçevesini görmeye
yetmiyor. Bu betik, bir kitap dönüştürüldükten sonra (tools/kitap_metin.py)
İKİ şey üretir:

  1. KISA ÖZET — kitabın bölümlerinden örnek sayfalar okunur, core/
     saglayicilar.py'nin 'kitap_ozet' zincirinden birkaç cümlelik özet
     istenir.
  2. ZENGİNLEŞTİRME — ders + sınıf + bölüm adlarından, konuyu
     derinleştirecek örnek soru/kaynak fikirleri için DDG ile ham sonuç
     çekilir (actions/web_search.py ile aynı mekanizma), sonra
     saglayicilar.py'nin 'arama_sentez' zinciriyle Türkçe bir metne derlenir.

Gemini burada YOK: Gemini artık yalnızca canlı ses oturumunda kullanılıyor
(main.py) — bkz. CLAUDE.md, "Provider notes". Eskiden
bu betik Gemini'nin grounded google_search aracını kullanıyordu; onun tam
eşdeğeri diğer sağlayıcılarda yok, ama iş zaten ARAMA (DDG) + SENTEZ (salt
metin) diye ikiye ayrılabiliyor — actions/web_search.py'deki aynı desen.

Çıktı `icerik/ozet/<kitap>.json`'a yazılır. `actions/ders_icerigi.py` bunu
varsa okur ve sayfa içeriğinin başına kısa özeti ekler (`_kitap_ozeti`) —
YENİ BİR ARAÇ DEĞİL, mevcut `ders_icerigi` çağrısına gömülü: içerik hâlâ
yalnızca tek bir tool call'la modele gidiyor.

Ders anında ÇALIŞMAZ — yalnız dönüştürme tamamlandıktan sonra, elle ya da
UI düğmesinden ("KİTAP ÖZETİ ÇIKAR") tetiklenir.

Kullanım
--------
    python tools/kitap_ozet.py                       # kuru çalışma, tüm kitaplar
    python tools/kitap_ozet.py matematik_9 --onayla   # tek kitap, gerçekten çalıştır
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

METIN_DIZINI = BASE_DIR / "icerik" / "metin"
KITAP_PATH   = BASE_DIR / "icerik" / "kitaplar.json"
OZET_DIZINI  = BASE_DIR / "icerik" / "ozet"

ORNEK_SAYFA_ADEDI  = 6      # kitap başına özetlemek için okunacak örnek sayfa
ORNEK_METIN_SINIRI = 9000   # modele giden örnek metnin karakter sınırı

OZET_ISTEMI = """Aşağıda bir ders kitabından bölüm adları ve birkaç örnek sayfa \
metni var. Bu kitabın genel çerçevesini, öğretmenin dersi planlarken hızlıca \
okuyabileceği 3-5 cümlelik bir ÖZETLE anlat. Hangi ana konuları kapsadığını \
söyle, sayfa numarası ya da alıntı verme, yalnızca düz metin özet döndür.

DERS: {ders} — {sinif}. sınıf
BÖLÜMLER: {bolumler}

ÖRNEK SAYFA METNİ:
---
{ornek_metin}
---"""


def _json_oku(yol: Path):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return None


def _metinden_ozet_uret(ders: str, sinif, bolumler: list[str], ornek_metin: str) -> str:
    from core import saglayicilar
    istem = OZET_ISTEMI.format(
        ders=ders or "?", sinif=sinif or "?",
        bolumler=", ".join(bolumler) or "?",
        ornek_metin=ornek_metin[:ORNEK_METIN_SINIRI])
    return saglayicilar.metin_uret("kitap_ozet", istem)


def _zenginlestirme_uret(ders: str, sinif, bolumler: list[str]) -> str:
    """
    Konuyu derinleştirecek örnek soru/kaynak fikirleri — DDG'den ham sonuç,
    saglayicilar.py'nin 'arama_sentez' zinciriyle Türkçe metne derlenir.
    actions/web_search.py'deki _ddg_search/_format_ddg ile aynı yol.
    """
    from actions.web_search import _ddg_search, _format_ddg
    from core import saglayicilar

    sorgu = (f"{ders} {sinif}. sınıf {', '.join(bolumler[:5])} konularını "
             f"derinleştirecek örnek soru fikirleri ve güvenilir kaynaklar")
    sonuclar = _ddg_search(sorgu, max_results=8)
    if not sonuclar:
        return ""
    ham = _format_ddg(sorgu, sonuclar)
    istem = (f"Aşağıdaki arama sonuçlarından, {ders} {sinif}. sınıf konusunu "
             f"derinleştirecek örnek soru fikirleri ve güvenilir kaynakları "
             f"Türkçe, kısa bir listeye derle:\n\n{ham}")
    return saglayicilar.metin_uret("arama_sentez", istem)


def _ornek_metni_topla(kitap_metni: dict, adet: int) -> str:
    sayfalar = kitap_metni.get("sayfalar", {})
    numaralar = sorted(int(n) for n in sayfalar if n.isdigit())
    if not numaralar:
        return ""
    adim = max(1, len(numaralar) // adet)
    secilen = numaralar[::adim][:adet]
    parcalar = []
    for n in secilen:
        t = (sayfalar.get(str(n), {}).get("metin") or "").strip()
        if t:
            parcalar.append(f"[s.{n}]\n{t}")
    return "\n\n".join(parcalar)


def kitap_ozeti_uret(kitap_kaydi: dict, kitap_metin_json: Path, onayla: bool) -> dict:
    ad = kitap_metin_json.stem
    kitap_metni = _json_oku(kitap_metin_json)
    if not kitap_metni or not kitap_metni.get("sayfalar"):
        return {"kitap": ad, "hata": "metin bulunamadı — önce kitap_metin.py çalıştırılmalı"}

    ders  = kitap_kaydi.get("ders", "")
    sinif = kitap_kaydi.get("sinif", "")
    bolumler = [b.get("ad", "") for b in kitap_kaydi.get("bolumler", []) if b.get("ad")]

    if not onayla:
        return {"kitap": ad, "onayla": False}

    ornek_metin = _ornek_metni_topla(kitap_metni, ORNEK_SAYFA_ADEDI)

    ozet = zenginlestirme = ""
    try:
        ozet = _metinden_ozet_uret(ders, sinif, bolumler, ornek_metin)
    except Exception as e:
        print(f"    özet üretilemedi: {type(e).__name__}: {e}")
    try:
        zenginlestirme = _zenginlestirme_uret(ders, sinif, bolumler)
    except Exception as e:
        print(f"    zenginleştirme üretilemedi: {type(e).__name__}: {e}")

    if not ozet and not zenginlestirme:
        return {"kitap": ad, "hata": "hem özet hem zenginleştirme başarısız"}

    OZET_DIZINI.mkdir(parents=True, exist_ok=True)
    hedef = OZET_DIZINI / f"{ad}.json"
    hedef.write_text(json.dumps({
        "kitap": kitap_kaydi.get("dosya", f"{ad}.pdf"),
        "ders": ders, "sinif": sinif,
        "ozet": ozet,
        "zenginlestirme": zenginlestirme,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"kitap": ad, "onayla": True}


def _kitap_kaydi_bul(kayitlar_by_dosya: dict, ad: str) -> dict:
    kayit = kayitlar_by_dosya.get(f"{ad}.pdf")
    if kayit:
        return kayit
    for dosya, k in kayitlar_by_dosya.items():
        if Path(dosya).stem == ad:
            return k
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dönüştürülmüş kitaplar için özet + zenginleştirme üretir")
    ap.add_argument("kitaplar", nargs="*",
                    help="Belirli kitap dosya adı/stem'i (boşsa icerik/metin altındaki hepsi)")
    ap.add_argument("--onayla", action="store_true",
                    help="Gerçekten çalıştır (API çağrısı yapar, ücretlidir). "
                         "Aksi hâlde yalnız hangi kitapların işleneceğini yazar.")
    a = ap.parse_args()

    if not METIN_DIZINI.exists():
        print("icerik/metin/ yok — önce tools/kitap_metin.py çalıştırılmalı.")
        return 1

    kitaplar_index = _json_oku(KITAP_PATH) or {"kitaplar": []}
    kayitlar_by_dosya = {k.get("dosya", ""): k for k in kitaplar_index.get("kitaplar", [])}

    if a.kitaplar:
        hedefler = [METIN_DIZINI / f"{Path(k).stem}.json" for k in a.kitaplar]
        hedefler = [h for h in hedefler if h.exists()]
    else:
        hedefler = sorted(METIN_DIZINI.glob("*.json"))

    if not hedefler:
        print("Özetlenecek kitap bulunamadı.")
        return 1

    if not a.onayla:
        print("KURU ÇALIŞMA — hiçbir API çağrısı yapılmayacak. "
              "Gerçekten özetlemek için --onayla ekleyin.\n")

    for hedef in hedefler:
        ad = hedef.stem
        kayit = _kitap_kaydi_bul(kayitlar_by_dosya, ad)

        t0 = time.time()
        try:
            sonuc = kitap_ozeti_uret(kayit, hedef, a.onayla)
        except Exception as e:
            print(f"  ✖ {ad}: {type(e).__name__}: {str(e)[:90]}")
            continue

        if sonuc.get("hata"):
            print(f"  ✖ {sonuc['kitap']}: {sonuc['hata']}")
        elif not a.onayla:
            print(f"  [kuru çalışma] {sonuc['kitap']}")
        else:
            print(f"  {sonuc['kitap']}: özet + zenginleştirme yazıldı ({time.time()-t0:.1f} sn)")

    if not a.onayla:
        print("\nGerçekten özetlemek için: --onayla")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
