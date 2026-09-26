"""
server/tests/ses_degerlendirme.py — Faz 1a GERÇEK Ollama araç-seçimi
değerlendirmesi.

pytest TOPLAMAZ (dosya adı `test_` ÖNEKİYLE BAŞLAMIYOR — bilerek; ayrıca
tüm gerçek iş `if __name__ == "__main__":` altında, bir pytest keşfi
dosyayı import etse bile hiçbir ağ çağrısı TETİKLENMEZ). Çalıştır:

    cd server && venv/bin/python tests/ses_degerlendirme.py

GERÇEK Ollama'ya (127.0.0.1:11434, qwen2.5:14b) 20 Türkçe istem gönderir ve
modelin HANGİ aracı (ya da hiçbirini) seçtiğini ölçer — plan kapısı:
≥ 19/20. Yalnızca `_ollama_turu` (KARAR adımı) çağrılır — `_ajan_calistir`'in
tam ajan döngüsü (kitap_sorusu → gerçek RAG, ders_icerigi → gerçek NAS/PDF)
BİLEREK devre dışı: bu script yalnızca ARAÇ SEÇİMİNİ (routing) ölçer, DB'ye
`metrik`/`soru_log` satırı YAZMAZ (dashboard sayımını kirletmez — plan
"Kesin sınırlar"). Uçtan uca RAG/ders_icerigi yürütmesi ayrı bir adımda
(gerçek dev uvicorn + curl/openai SDK, plan "Gerçek" madde 1-2) zaten
birkaç sayılı istekle doğrulanıyor.

Her istem TEK bir gerçek Ollama turu alır (yeniden deneme YOK) — üretimdeki
`_ajan_calistir`'in "boş cevapta bir kez yeniden dene" davranışı burada
BİLEREK uygulanmıyor: amaç modelin HAM ilk-atış routing kalitesini ölçmek,
üretim yumuşatmasının bunu gizlemesini değil.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ses_cephe

DERSLIK = "9-A"
SINIF_DUZEYI = "9"

# (kategori, kip, ders_baglam, istem, beklenen_arac)
# beklenen_arac None => araçsız (serbest) tek cümlelik sohbet cevabı beklenir.
ISTEMLER: list[tuple[str, str, str | None, str, str | None]] = [
    # ── Bilgi soruları (8, farklı derslerden) — kitap_sorusu beklenir ──────
    ("bilgi", "ogretmenli", "biyoloji",     "Mitokondri nedir, kitaba göre anlatır mısın?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "biyoloji",     "Fotosentez neden gerçekleşir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "fizik",        "Newton'un hareket yasaları nelerdir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "tarih",        "Osmanlı Devleti ne zaman kuruldu?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "matematik",    "Küme kavramı nedir?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "kimya",        "Atomun yapısı nasıldır?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "din kültürü",  "Kur'an-ı Kerim ne zaman indirilmeye başlandı?", "kitap_sorusu"),
    ("bilgi", "ogretmenli", "coğrafya",     "Türkiye'nin iklim tiplerini nasıl sınıflandırabiliriz?", "kitap_sorusu"),
    # ── Konu anlatımı (3) — ders_icerigi beklenir ──────────────────────────
    ("konu", "ogretmenli", "biyoloji",   "Hücre bölünmesi konusunu anlatır mısın?", "ders_icerigi"),
    ("konu", "ogretmenli", "matematik",  "Şimdi türev konusunu işleyelim.", "ders_icerigi"),
    ("konu", "ogretmenli", "tarih",      "Osmanlı'nın kuruluş dönemini anlat.", "ders_icerigi"),
    # ── Sayfa açma (3) — pdf_sayfa beklenir ────────────────────────────────
    ("sayfa", "ogretmenli", "biyoloji", "Kitabın 45. sayfasını göster.", "pdf_sayfa"),
    ("sayfa", "ogretmenli", "fizik",    "12. sayfayı aç.", "pdf_sayfa"),
    ("sayfa", "ogretmenli", "tarih",    "Lütfen 78. sayfayı ekrana yansıt.", "pdf_sayfa"),
    # ── Çıkmış soru (2) — yks_sorulari beklenir ────────────────────────────
    ("yks", "ogretmenli", "matematik", "Türev konusunda çıkmış bir YKS sorusu gösterir misin?", "yks_sorulari"),
    ("yks", "ogretmenli", "matematik", "TYT matematik çıkmış sorularından biri var mı?", "yks_sorulari"),
    # ── Talimat-kipi kapatma (1) — pencere_kapat beklenir ──────────────────
    ("talimat", "talimat", None, "youtube'u kapat", "pencere_kapat"),
    # ── Sohbet (3) — araçsız serbest cevap beklenir ────────────────────────
    ("sohbet", "ogretmenli", None, "Günaydın Farabi, nasılsın?", None),
    ("sohbet", "ogretmenli", None, "Teşekkür ederim, çok yardımcı oldun.", None),
    ("sohbet", "ogretmenli", None, "Bugün hava çok güzel değil mi?", None),
]


async def _tek_istem_calistir(client, kategori: str, kip: str, ders: str | None,
                               istem: str, beklenen: str | None) -> dict:
    sistem = ses_cephe._sistem_mesaji(kip, DERSLIK, SINIF_DUZEYI, ders)
    araclar = ses_cephe._kip_icin_araclar(kip)
    mesajlar = [{"role": "user", "content": istem}]

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
    # qwen bazen tool_calls yerine ham "<tool_call>{...}" / "{"name":...}"
    # JSON'unu İÇERİK olarak yazabiliyor — sesli okunursa TTS bunu okur,
    # bu da fiilen bir routing hatasıdır (advisor notu).
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
    print(f"SKOR: {dogru}/{toplam}  (kapı: >= 19/20)")
    print("KAPI:", "PASS" if dogru >= 19 else "FAIL")

    araçsiz = [s for s in sonuclar if s["bilgi_araçsiz"]]
    if araçsiz:
        print()
        print("Bilgi sorusunun ARAÇSIZ (serbest) cevaplandığı örnekler:")
        for s in araçsiz:
            print(f"  - {s['istem']}  (alınan: {s['alinan']})")


if __name__ == "__main__":
    main()
