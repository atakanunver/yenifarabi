"""kazanim_rapor.py testleri (/kazanim-rapor). httpx yok → route fonksiyonu
doğrudan, elle kurulmuş Starlette Request ile çağrılır (test_sunucular.py
deseni). RAPOR_DIZINI ve db.DB_YOLU geçici dizine yamalanır."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import db
import kazanim_rapor as kr
from fastapi.requests import Request
from fastapi.responses import RedirectResponse

RAPOR = {
    "sinif": "9-A",
    "uretim": "2026-10-08T04:55:52+03:00",
    "aralik": {"baslangic": None, "bitis": None},
    "esikler": {"zorlanilan_esik": 0.5, "eksik_esik": 0.5, "guclu_esik": 0.8, "kazanim_min_soru": 2},
    "testler": [{
        "id": 1, "ders": "kimya", "hafta": 4, "tarih": "2026-10-08",
        "kazanim": "KİM.9.1.3", "form_url": "https://forms.gle/abc", "katilim": 2,
        "ortalama_oran": 0.4,
        "sorular": [{
            "sira": 1, "soru": "Atom modeli neydi?", "kazanim_satiri": "KİM.9.1.3",
            "dogru_orani": 0.25, "cevap_sayisi": 4,
            "en_cok_secilen_yanlis": {"sik_harfi": "A", "oran": 0.75},
        }],
    }],
    "kazanimlar": [
        {"ders": "kimya", "kazanim_satiri": "KİM.GÜÇLÜ-KAZANIM", "soru_sayisi": 2, "cevap_sayisi": 4, "dogru_orani": 0.9, "zorlanilan": False},
        {"ders": "kimya", "kazanim_satiri": "KİM.ZORLANILAN-KAZANIM", "soru_sayisi": 10, "cevap_sayisi": 40, "dogru_orani": 0.3, "zorlanilan": True},
    ],
    "ogrenciler": [
        {"okul_no": 1, "test_sayisi": 1, "dogru": 3, "toplam": 10, "oran": 0.3,
         "kazanimlar": [{"ders": "kimya", "kazanim_satiri": "KİM.9.1.3", "soru": 10, "dogru": 3,
                         "oran": 0.3, "durum": "eksik", "sayfalar": ["Kimya 9, s. 54-55"]}],
         "eksik_sayisi": 1, "guclu_sayisi": 0},
        {"okul_no": 999, "test_sayisi": 1, "dogru": 5, "toplam": 10, "oran": 0.5,
         "kazanimlar": [], "eksik_sayisi": 0, "guclu_sayisi": 0},
    ],
}


def _istek(cerez="gecerli", yol="/kazanim-rapor"):
    basliklar = [(b"host", b"farabi.local")]
    if cerez:
        basliklar.append((b"cookie", f"{__import__('auth').COOKIE_ADI}={cerez}".encode()))
    return Request({
        "type": "http", "method": "GET", "path": yol, "root_path": "",
        "scheme": "http", "server": ("farabi.local", 8010), "query_string": b"",
        "headers": basliklar, "client": ("127.0.0.1", 5555),
    })


class KazanimRaporTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        kok = Path(self._tmp.name)
        self._eski_db, self._eski_dizin = db.DB_YOLU, kr.RAPOR_DIZINI
        db.DB_YOLU = kok / "t.db"
        kr.RAPOR_DIZINI = kok / "rapor"
        kr.RAPOR_DIZINI.mkdir()
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO oturumlar (token) VALUES ('gecerli')")
        conn.execute("INSERT INTO siniflar (ad) VALUES ('9-A')")
        sid = conn.execute("SELECT id FROM siniflar WHERE ad='9-A'").fetchone()["id"]
        conn.executemany(
            "INSERT INTO ogrenciler (sinif_id, no, ad_soyad, aktif) VALUES (?,?,?,?)",
            [(sid, 1, "Ayşe Yılmaz", 1), (sid, 2, "Mehmet Demir", 1), (sid, 3, "Pasif Öğrenci", 0)],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU, kr.RAPOR_DIZINI = self._eski_db, self._eski_dizin
        self._tmp.cleanup()

    def _rapor_yaz(self, ad="9-A", veri=RAPOR):
        (kr.RAPOR_DIZINI / f"{ad}.json").write_text(
            veri if isinstance(veri, str) else json.dumps(veri, ensure_ascii=False), encoding="utf-8"
        )

    def _sayfa(self, sinif=None, cerez="gecerli"):
        return asyncio.run(kr.kazanim_rapor_sayfa(_istek(cerez), sinif))

    def _html(self, sinif=None):
        yanit = self._sayfa(sinif)
        self.assertEqual(yanit.status_code, 200)
        return yanit.body.decode("utf-8")

    def test_oturumsuz_giris_sayfasina_yonlenir(self):
        self._rapor_yaz()
        for cerez in (None, "yanlis"):
            yanit = self._sayfa(cerez=cerez)
            self.assertIsInstance(yanit, RedirectResponse)
            self.assertEqual(yanit.headers["location"], "/giris")

    def test_oturumlu_sayfa_icerigi(self):
        self._rapor_yaz()
        html = self._html()
        self.assertIn("Ayşe Yılmaz", html)
        self.assertIn("ZORLANILAN-KAZANIM", html)
        self.assertIn("%75 A şıkkını seçti", html)
        self.assertIn("Kimya 9, s. 54-55", html)
        self.assertIn("https://forms.gle/abc", html)
        self.assertIn("Zorlanılan kazanım", html)
        # zorlanılan kazanım güçlü olanın üstünde
        self.assertLess(html.index("ZORLANILAN-KAZANIM"), html.index("GÜÇLÜ-KAZANIM"))

    def test_eslesmeyen_numara(self):
        self._rapor_yaz()
        html = self._html()
        self.assertIn("Eşleşmeyen numaralar", html)
        self.assertIn("999", html)

    def test_eslesme_varsa_uyari_yok(self):
        veri = json.loads(json.dumps(RAPOR))
        veri["ogrenciler"] = veri["ogrenciler"][:1]
        self._rapor_yaz(veri=veri)
        self.assertNotIn("Eşleşmeyen numaralar", self._html())

    def test_katilmadi_listesi(self):
        self._rapor_yaz()
        html = self._html()
        self.assertIn("Katılmadı", html)
        self.assertIn("Mehmet Demir", html)      # testi yapmayan aktif öğrenci
        self.assertNotIn("Pasif Öğrenci", html)  # pasif öğrenci listelenmez

    def test_dosya_yok_empty_state(self):
        html = self._html()
        self.assertIn("Henüz kazanım raporu üretilmemiş", html)

    def test_olmayan_sinif_empty_state(self):
        self._rapor_yaz()
        self.assertIn("rapor bulunamadı", self._html("12-Z"))

    def test_bozuk_json_empty_state(self):
        self._rapor_yaz(veri="{bozuk")
        self.assertIn("bozuk", self._html())
        self._rapor_yaz(veri="[1, 2]")
        self.assertIn("biçimi tanınmadı", self._html())

    def test_bos_rapor_empty_state(self):
        self._rapor_yaz(veri={"sinif": "9-A", "testler": [], "kazanimlar": [], "ogrenciler": []})
        self.assertIn("henüz veri yok", self._html())

    def test_alanlari_eksik_rapor_500_vermez(self):
        self._rapor_yaz(veri={"testler": [{"sorular": "x"}], "ogrenciler": [{"okul_no": None}], "kazanimlar": [1, None]})
        self.assertIn("Kazanım raporu", self._html())

    def test_yol_enjeksiyonu(self):
        (Path(self._tmp.name) / "x.json").write_text(json.dumps(RAPOR), encoding="utf-8")
        self._rapor_yaz()
        for kotu in ("../x", "..%2Fx", "/etc/passwd", "9-A/../../x", "9-A.json"):
            html = self._html(kotu)
            self.assertIn("rapor bulunamadı", html)
            self.assertNotIn("Ayşe Yılmaz", html)

    def test_sinif_adlari_yalniz_guvenli_dosyalar(self):
        self._rapor_yaz("10-B")
        self._rapor_yaz("9-A")
        self._rapor_yaz("kotu ad")
        self.assertEqual(kr.sinif_adlari(), ["9-A", "10-B"])


if __name__ == "__main__":
    unittest.main()
