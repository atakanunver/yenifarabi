"""
server/tests/ses_degerlendirme_set2.py — Faz 1b İKİNCİ (daha önce
GÖRÜLMEMİŞ) araç-seçimi değerlendirmesi.

`ses_degerlendirme.py`'nin (Faz 1a) 20 istemi üzerinde ölçüldüğü için o
sayı iyimser — bu script, PERSONA'ya HİÇ dokunmadan (`ses_persona.txt`
DEĞİŞTİRİLMEDİ), aynı yöntemle (yalnızca `_ollama_turu` — KARAR adımı,
gerçek RAG/`ders_icerigi` yürütülmez, `metrik`/`soru_log`'a satır YAZILMAZ)
YENİ 20 istemle Faz 1b bitiş raporu için ayrı bir ölçüm sağlar.

pytest TOPLAMAZ (dosya adı `test_` ile BAŞLAMIYOR — `ses_degerlendirme.py`
ile AYNI bilinçli desen). Çalıştır:

    cd server && venv/bin/python tests/ses_degerlendirme_set2.py

Kapı: ≥ 19/20 (plan). Bilgi sorusunun araçsız (serbest) cevaplandığı her
örnek ayrıca raporlanır.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ses_cephe

DERSLIK = "9-A"
SINIF_DUZEYI = "9"

# (kategori, kip, ders_baglam, istem, beklenen_arac) — set 1'deki (ses_degerlendirme.py)
# HİÇBİR istemle AYNI DEĞİL, kategori dağılımı BİREBİR aynı: 8 bilgi (farklı
# derslerden), 3 konu anlatımı, 3 sayfa açma, 2 çıkmış soru, 1 talimat-kipi
# kapatma, 3 sohbet.
ISTEMLER: list[tuple[str, str, str | None, str, str | None]] = [
    # ── Bilgi soruları (8, farklı derslerden) — kitap_sorusu beklenir ──────
    ("bilgi", "ogretmenli", "biyoloji",     "Hücre zarının görevi nedir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "biyoloji",     "Canlılar nasıl sınıflandırılır?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "fizik",        "Kuvvet nedir, birimi nedir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "tarih",        "İstanbul'un fethi hangi yıl gerçekleşti?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "matematik",    "Asal sayı ne demektir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "kimya",        "Periyodik tablo neye göre düzenlenmiştir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "coğrafya",     "Türkiye'de nüfus dağılımını etkileyen faktörler nelerdir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "din kültürü",  "Beş vakit namaz nedir, kısaca anlatır mısın?", "kitap_sorusu"),
    # ── Konu anlatımı (3) — ders_icerigi beklenir ──────────────────────────
    ("konu", "ogretmenli", "fizik",      "Kuvvet ve hareket konusunu işleyelim.", "ders_icerigi"),
    ("konu", "ogretmenli", "kimya",      "Şimdi periyodik sistem konusunu anlat.", "ders_icerigi"),
    ("konu", "ogretmenli", "coğrafya",   "İklim tipleri konusunu baştan anlatır mısın?", "ders_icerigi"),
    # ── Sayfa açma (3) — pdf_sayfa beklenir ────────────────────────────────
    ("sayfa", "ogretmenli", "matematik", "23. sayfayı ekrana getirir misin?", "pdf_sayfa"),
    ("sayfa", "ogretmenli", "kimya",     "Kitaptan 60. sayfayı aç.", "pdf_sayfa"),
    ("sayfa", "ogretmenli", "coğrafya",  "Şu 8. sayfayı gösterir misin?", "pdf_sayfa"),
    # ── Çıkmış soru (2) — yks_sorulari beklenir ────────────────────────────
    ("yks", "ogretmenli", "kimya",   "Periyodik tablo ile ilgili çıkmış bir AYT sorusu var mı?", "yks_sorulari"),
    ("yks", "ogretmenli", "biyoloji", "Genetik konusunda çıkmış TYT sorularından gösterir misin?", "yks_sorulari"),
    # ── Talimat-kipi kapatma (1) — pencere_kapat beklenir ──────────────────
    ("talimat", "talimat", None, "tarayıcıyı kapat", "pencere_kapat"),
    # ── Sohbet (3) — araçsız serbest cevap beklenir ────────────────────────
    ("sohbet", "ogretmenli", None, "İyi dersler Farabi, hoşça kal.", None),
    ("sohbet", "ogretmenli", None, "Sen bir yapay zekâ mısın?", None),
    ("sohbet", "ogretmenli", None, "Bugün canım hiç ders çalışmak istemiyor.", None),
]


async def _tek_istem_calistir(client, kategori: str, kip: str, ders: str | None,
                               istem: str, beklenen: str | None) -> dict:
    sistem = ses_cephe._sistem_mesaji(kip, DERSLIK, SINIF_DUZEYI, ders)
    araclar = ses_cephe._kip_icin_araclar(kip)
    mesajlar = [{"role": "user", "content": istem}]

    import time
    t0 = time.monotonic()
    icerik_parcalari: list[str] = []
    alinan_arac: str | None = None
    hata: str | None = None
    async for olay in ses_cephe._ollama_turu(client, sistem, mesajlar, araclar):
        if olay[0] == "icerik":
            icerik_parcalari.append(olay[1])
        elif olay[0] == "arac":
            alinan_arac = olay[1]
        elif olay[0] == "hata":
            hata = olay[1]
    sure_ms = int((time.monotonic() - t0) * 1000)

    icerik_metni = "".join(icerik_parcalari)
    ham_arac_sizintisi = alinan_arac is None and icerik_metni.strip().startswith(("<tool_call>", "{\"name\""))

    if hata:
        sonuc = "FAIL"
        alinan_gosterim = f"[HATA: {hata}]"
    elif alinan_arac is not None:
        alinan_gosterim = alinan_arac
        sonuc = "PASS" if alinan_arac == beklenen else "FAIL"
    elif not icerik_metni.strip():
        alinan_gosterim = "[BOŞ]"
        sonuc = "FAIL"
    else:
        alinan_gosterim = "[HAM SIZINTI]" if ham_arac_sizintisi else "[İÇERİK]"
        sonuc = "PASS" if beklenen is None and not ham_arac_sizintisi else "FAIL"

    return {
        "kategori": kategori, "istem": istem, "beklenen": beklenen or "-",
        "alinan": alinan_gosterim, "sonuc": sonuc, "sure_ms": sure_ms,
        "bilgi_araçsiz": kategori == "bilgi" and alinan_arac is None,
    }


async def _calistir() -> list[dict]:
    client = ses_cephe._istemci_fabrikasi()
    sonuclar = []
    try:
        for kategori, kip, ders, istem, beklenen in ISTEMLER:
            sonuc = await _tek_istem_calistir(client, kategori, kip, ders, istem, beklenen)
            sonuclar.append(sonuc)
            print(f"[{sonuc['sonuc']:4}] {kategori:8} {sonuc['sure_ms']:6} ms  "
                  f"beklenen={sonuc['beklenen']:14} alinan={sonuc['alinan']:14} · {istem}")
    finally:
        await client.aclose()
    return sonuclar


def main() -> None:
    sonuclar = asyncio.run(_calistir())
    dogru = sum(1 for s in sonuclar if s["sonuc"] == "PASS")
    toplam = len(sonuclar)

    print()
    print(f"SKOR (SET 2 — daha önce görülmemiş): {dogru}/{toplam}  (kapı: >= 19/20)")
    print("KAPI:", "PASS" if dogru >= 19 else "FAIL")

    araçsiz = [s for s in sonuclar if s["bilgi_araçsiz"]]
    if araçsiz:
        print()
        print("Bilgi sorusunun ARAÇSIZ (serbest) cevaplandığı örnekler:")
        for s in araçsiz:
            print(f"  - {s['istem']}  (alınan: {s['alinan']})")


if __name__ == "__main__":
    main()
