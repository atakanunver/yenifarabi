"""Deneme karnelerine Gemini (bulut) ile KİMLİKSİZ yorum yazar: öğrenci analiz/tavsiye, şube ve okul yorumu.

Kullanım (okul/ dizininden):
    venv/bin/python scripts/deneme_yorum.py "<deneme adı>" [--kuru]
Anahtar: GEMINI_API_KEY ortam değişkeni, yoksa tahtaların kullandığı server/config/api_keys_tahta_ortak.json::gemini_api_keys
(kodla okunur, hiçbir yere yazılmaz/basılmaz; kota hatasında sıradaki anahtar denenir).
KVKK: Gemini'ye ad, okul no, şube adı ve öğrenciler arası karşılaştırma GİTMEZ; yalnız bir öğrencinin ders netleri/kazanım
sayıları (öğrenci yorumu) ya da grup ortalamaları (şube/okul yorumu, ≥5 katılımcı). Yalnız BOŞ olanlar üretilir
(idempotent); Gemini hatasında satır boş kalır, betik devam eder, yeniden çalıştırılabilir. Yükleme (deneme_yukle.py)
analiz/tavsiye'yi ezer: yorumları EN SON üret.
"""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import denemeler

MODEL = "gemini-3.5-flash-lite"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
ZAYIF_AZAMI = 10
TAHTA_ANAHTARLARI = Path(__file__).resolve().parents[2] / "server" / "config" / "api_keys_tahta_ortak.json"

SISTEM = (
    "Sen bir lisede deneme sınavı sonuçlarını yorumlayan deneyimli bir ölçme-değerlendirme uzmanı ve öğrenci koçusun. "
    "Kurallar: 1) 'Daha çok çalış' gibi genel geçer tavsiye verme; yalnızca verilen netlere ve kazanımlara dayan, veride olmayan "
    "bilgiyi uydurma. 2) Öğrenciyi başkasıyla karşılaştırma, sıralama ya da risk/etiket kullanma; destekleyici, saygılı ve "
    "somut ol. 3) Kazanım adlarını verildiği gibi an. 4) Türkçe yaz, kısa paragraflar kullan. Çıktı yalnızca istenen JSON olsun. "
    "Bağlam (öğretmen gözlemi): bu denemeler TYT biçimindedir ve 9. ile 10. sınıf konularını ölçer; 11. ve 12. sınıf öğrencileri bu "
    "konuları geçmiş yıllarda görmüştür. Matematik ve geometride düşüş belirgindir ve okulun bilinen asıl eksik alanıdır; "
    "düşük netleri öğrencinin şimdiki sınıf başarısı değil, geçmiş konuların kalıcı öğrenilmesi olarak yorumla ve suçlayıcı olma."
)


def _zayif(veri: dict) -> list[dict]:
    z = denemeler._zayif_kazanimlar(veri.get("kazanimlar"))
    return z[:ZAYIF_AZAMI]


def ogrenci_istemi(veri: dict) -> str:
    satirlar = [f"Toplam net: {veri.get('toplam_net')}"]
    dyb = veri.get("ders_dyb") if isinstance(veri.get("ders_dyb"), dict) else {}
    for ders, net in (veri.get("dersler") or {}).items():
        d = dyb.get(ders)
        ek = f" (doğru {d[0]}, yanlış {d[1]}, boş {d[2]})" if isinstance(d, list) and len(d) == 3 else ""
        satirlar.append(f"- {ders}: net {net}{ek}")
    zayif = _zayif(veri)
    if zayif:
        satirlar.append("Başarısı %50'nin altında kalan kazanımlar:")
        satirlar += [f"- {z['ders']} / {z['kazanim']}: {z['d']} doğru, {z['y']} yanlış, {z['b']} boş" for z in zayif]
    elif not veri.get("kazanimlar"):
        satirlar.append("Bu öğrenci için kazanım ayrıntısı yok; yorumu yalnızca ders netlerine dayandır.")
    return (
        "Bir öğrencinin deneme sonucu:\n" + "\n".join(satirlar) + "\n\n"
        'Öğrenciye "sen" diye hitap eden JSON üret: {"analiz": "güçlü derslerini ve doğru/yanlış/boş dengesini yorumlayan 2-3 cümle", '
        '"tavsiye": "listelenen kazanımlar için somut çalışma reçetesi (hangi konuyu tekrar et, kaç soru çöz) ve bu hafta için 2 mikro hedef; '
        'son cümle: boş ya da yanlış bıraktığı konuların gayretle ve düzenli çalışmayla kapanacağını vurgulayan içten bir "gayret et" cesaretlendirmesi; '
        'toplam 110-150 kelime"}'
    )


def _grup_veri(ozet: dict) -> str:
    satirlar = [f"Katılan öğrenci: {ozet['katilim']}", f"Ortalama net: {ozet['ortalama_net']}"]
    satirlar += [f"- {d}: {n}" for d, n in (ozet.get("ders_ortalamalari") or {}).items()]
    if ozet.get("ortak_eksikler"):
        satirlar.append("Grupta başarısı %50'nin altındaki kazanımlar (başarı %):")
        satirlar += [f"- {e['ders']} / {e['kazanim']}: %{e['basari']}" for e in ozet["ortak_eksikler"]]
    return "\n".join(satirlar)


def sinif_istemi(ozet: dict) -> str:
    return (
        "Bir sınıfın deneme sonucu:\n" + _grup_veri(ozet) + "\n\n"
        'Sınıf öğretmenine hitaben JSON üret: {"yorum": "güçlü/zayıf dersler, ortak kazanım kayıpları ve olası nedenleri, '
        'sınıfta yapılabilecek 2 somut tekrar/etüt önerisi; 120-160 kelime"}'
    )


def okul_istemi(ozet: dict) -> str:
    sube = [s["ortalama_net"] for s in ozet.get("subeler", []) if s.get("ortalama_net") is not None]
    aralik = f"Şube ortalamaları arasındaki en düşük ve en yüksek net: {min(sube)} - {max(sube)}" if sube else ""
    return (
        "Bir okulun deneme sonucu:\n" + _grup_veri(ozet) + ("\n" + aralik if aralik else "") + "\n\n"
        'Okul yönetimine yönetici özeti olarak JSON üret: {"yorum": "genel tablo, okul genelinde ortak kazanım açıkları ve zümre/destekleme '
        'kursları için 3 maddelik eylem planı; 150-200 kelime"}'
    )


def yanit_ayristir(metin: str) -> dict | None:
    try:
        d = json.loads(metin)
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) and all(isinstance(v, str) for v in d.values()) and d else None


def anahtarlar(ortam: str | None, dosya: Path) -> list[str]:
    """Önce ortam değişkeni, sonra tahta ortak yapılandırması; boş/bozuk dosya sessizce boş liste verir."""
    if ortam:
        return [ortam]
    try:
        liste = json.loads(dosya.read_text(encoding="utf-8")).get("gemini_api_keys")
    except (OSError, ValueError, AttributeError):
        return []
    return [k for k in liste if isinstance(k, str) and k] if isinstance(liste, list) else []


def gemini(istem: str) -> dict | None:
    """Gemini'yi çağırır; JSON sözlük ya da None (hata ayrıntısı anahtar/URL içermez)."""
    anahtar_listesi = anahtarlar(os.environ.get("GEMINI_API_KEY"), TAHTA_ANAHTARLARI)
    if not anahtar_listesi:
        print("Gemini anahtarı bulunamadı", file=sys.stderr)
        return None
    govde = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": SISTEM}]},
            "contents": [{"role": "user", "parts": [{"text": istem}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
    ).encode()
    for deneme in range(3):
        anahtar = anahtar_listesi[deneme % len(anahtar_listesi)]
        try:
            istek = urllib.request.Request(
                URL, govde, {"Content-Type": "application/json", "x-goog-api-key": anahtar}
            )
            with urllib.request.urlopen(istek, timeout=60) as r:
                metin = json.load(r)["candidates"][0]["content"]["parts"][0]["text"]
            return yanit_ayristir(metin)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503):
                print(f"Gemini HTTP {e.code}", file=sys.stderr)
                return None
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError):
            pass
        time.sleep(2 * (deneme + 1))
    print("Gemini yanıt vermedi", file=sys.stderr)
    return None


def uret(conn: sqlite3.Connection, deneme_id: int, cagri, kuru: bool = False) -> dict:
    """Boş yorumları üretir. `cagri(istem) -> dict | None` (test için enjekte edilir)."""
    s = {"ogrenci": 0, "sinif": 0, "okul": 0, "hata": 0}
    satirlar = conn.execute(
        "SELECT okul_no, veri FROM deneme_ogrenci WHERE deneme_id = ? AND girdi = 1 AND analiz = ''",
        (deneme_id,),
    ).fetchall()
    for r in satirlar:
        try:
            veri = json.loads(r["veri"])
        except ValueError:
            continue
        if kuru:
            s["ogrenci"] += 1
            continue
        c = cagri(ogrenci_istemi(veri))
        if not c or "analiz" not in c or "tavsiye" not in c:
            s["hata"] += 1
            continue
        with conn:
            conn.execute(
                "UPDATE deneme_ogrenci SET analiz = ?, tavsiye = ? WHERE deneme_id = ? AND okul_no = ?",
                (c["analiz"], c["tavsiye"], deneme_id, r["okul_no"]),
            )
        s["ogrenci"] += 1
    siniflar = [x[0] for x in conn.execute(
        "SELECT DISTINCT g.sinif FROM deneme_ogrenci o JOIN ogrenci g ON g.okul_no = o.okul_no"
        " WHERE o.deneme_id = ? AND o.girdi = 1 ORDER BY g.sinif", (deneme_id,))]
    hedefler = [(sn, denemeler.sinif_ozeti(conn, deneme_id, sn, yalniz_yayinda=False), sinif_istemi, "sinif") for sn in siniflar]
    hedefler.append(("", denemeler.okul_ozeti(conn, deneme_id, yalniz_yayinda=False), okul_istemi, "okul"))
    for anahtar, ozet, istem_fn, tur in hedefler:
        if not ozet or ozet["ortalama_net"] is None or denemeler.yorum_oku(conn, deneme_id, anahtar):
            continue
        if kuru:
            s[tur] += 1
            continue
        c = cagri(istem_fn(ozet))
        if not c or not c.get("yorum"):
            s["hata"] += 1
            continue
        denemeler.yorum_yaz(conn, deneme_id, anahtar, c["yorum"])
        s[tur] += 1
    return s


def main(argv: list[str]) -> int:
    kuru = "--kuru" in argv
    adlar = [a for a in argv if not a.startswith("--")]
    if len(adlar) != 1:
        print(__doc__)
        return 2
    conn = db.baglanti()
    try:
        d = conn.execute("SELECT id FROM deneme WHERE ad = ?", (adlar[0],)).fetchone()
        if d is None:
            print("Deneme bulunamadı.", file=sys.stderr)
            return 1
        s = uret(conn, d["id"], gemini, kuru=kuru)
    finally:
        conn.close()
    print(f"{'[KURU] ' if kuru else ''}üretilen: öğrenci={s['ogrenci']} sınıf={s['sinif']} okul={s['okul']} hata={s['hata']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
