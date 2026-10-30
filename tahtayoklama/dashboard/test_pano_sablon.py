"""Ana ekran (ders ızgarası) şablonu, yeni tasarım (2026-10-30). Şablon DB'siz render edilir;
hücre doldurma istemci JS'inde olduğundan JS kaynağı metin olarak denetlenir."""
import re
import unittest
from pathlib import Path

from starlette.requests import Request

import app as uygulama

KOK = Path(__file__).parent
CSS = (KOK / "static" / "bilesen.css").read_text(encoding="utf-8")


def _render(tarih="2026-10-30", bugun="2026-10-30"):
    istek = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"",
                     "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})
    return uygulama.templates.get_template("pano.html").render(
        request=istek, tarih=tarih, bugun=bugun,
        siniflar=[{"id": 1, "ad": "9-A"}, {"id": 2, "ad": "10-A"}], sinif_tahta={1: 5},
        ders_saatleri=[{"no": 1, "baslangic": "08:10", "bitis": "08:50"},
                       {"no": 2, "baslangic": "09:00", "bitis": "09:40"}],
        ilk_durum=None)


def _kurallar(secici_parcasi):
    """bilesen.css'te seçicisi verilen parçayı içeren kuralların gövdeleri."""
    govde = re.sub(r"/\*.*?\*/", "", CSS, flags=re.DOTALL)
    return [g for s, g in re.findall(r"([^{}]+)\{([^{}]*)\}", govde) if secici_parcasi in s]


class TestPanoSablon(unittest.TestCase):
    def setUp(self):
        self.html = _render()

    def test_uyari_seridi_izgaranin_ustunde(self):
        self.assertIn('id="uyari-seridi"', self.html)
        self.assertLess(self.html.index('id="uyari-seridi"'), self.html.index('id="pano-tablo"'))
        self.assertRegex(self.html, r'<section class="serit serit-bilgi[^"]*" id="uyari-seridi"')

    def test_uzun_isim_listesi_hucrede_metin(self):
        # Review Focus 1: devamsız isimler çerçevesiz metin, hücrede aşağı sarar; yatay taşma yok
        self.assertIn("el('span', 'isim'", self.html)
        self.assertIn("el('span', 'isim-izinli'", self.html)
        self.assertNotIn("pill", self.html)
        td = _kurallar("#pano-tablo td")
        self.assertTrue(any("white-space: normal" in g and "overflow-wrap: anywhere" in g for g in td))
        for g in _kurallar("#pano-tablo"):
            self.assertNotIn("min-width", g)
        self.assertTrue(_kurallar(".isim"))
        self.assertTrue(_kurallar(".isim-izinli"))

    def test_kpi_ilk_ekrani_doldurmaz(self):
        self.assertNotIn("pano-ozet", self.html)
        bas = self.html.index('<header class="sayfa-basligi">')
        baslik = self.html[bas:self.html.index("</header>", bas)]
        s_bas = self.html.index('id="uyari-seridi"')
        serit = self.html[s_bas:self.html.index("</section>", s_bas)]
        for kimlik in ("ozet-toplam-sinif", "ozet-tam-ders", "ozet-devamsiz", "ozet-bekleyen-ders"):
            self.assertTrue(f'id="{kimlik}"' in baslik or f'id="{kimlik}"' in serit, kimlik)

    def test_baslik_bugun_gun_tarih(self):
        h1 = re.search(r"<h1>(.*?)</h1>", self.html, re.DOTALL).group(1)
        self.assertIn("Bugün · Cuma 30 Ekim", h1)
        self.assertIn('id="baslik-ders"', h1)
        eski = re.search(r"<h1>(.*?)</h1>", _render(tarih="2026-10-12"), re.DOTALL).group(1)
        self.assertIn("Pazartesi 12 Ekim", eski)
        self.assertNotIn("Bugün", eski)
        self.assertIn("Cuma 1 Ocak", re.search(r"<h1>(.*?)</h1>", _render(tarih="2027-01-01", bugun="2027-01-01"), re.DOTALL).group(1))

    def test_degismeyenler_korunur(self):
        for parca in ('id="tarih-secici"', 'id="simdi-yenile"', 'id="son-guncelleme"', 'id="acil-serit"',
                      'id="hucre-9-A-1"', 'data-tahta-id="5"', 'data-sinif="9-A"', 'data-ders-no="1"',
                      "/api/tahta/${hucre.dataset.tahtaId}/baslat", "Tahtada aç", "const ILK_DURUM",
                      "function dersEtiketi", "/api/acil/durum", 'href="/sistem-durumu"'):
            self.assertIn(parca, self.html, parca)
        # Acil düğmesi kabukta; sayfada büyük harf yok
        self.assertNotIn("pano-acil-dugme", self.html)
        self.assertNotIn("ACİL DURUM", self.html)
        self.assertNotIn("AKTİF ALARM", self.html)

    def test_simdi_sutunu_ve_rozetler(self):
        self.assertIn("' · şimdi'", self.html)
        for sinif in ("rozet rozet-yesil", "rozet rozet-amber", "rozet rozet-gri"):
            self.assertIn(sinif, self.html)
        self.assertIn("'Alınmadı'", self.html)

    def test_eski_pano_siniflari_yok(self):
        for eski in ("tablo-sarici", "durum-ozet", "sorun-", "pano-ilerleme", "kr-bos", "aktif-ders-rozet"):
            self.assertNotIn(eski, self.html, eski)

    def test_sayfa_siniflari_bilesen_cssde(self):
        # pano.css (Task 9'da silinecek) olmadan da sayfa biçimlensin
        for secici in (".hucre", ".hucre-simdi", ".th-ders", ".sinif-adi", ".tahta-nokta", ".tahta-acik",
                       ".tahta-kapali", ".ders-etiketi", ".tiklanabilir", ".tetikleniyor", ".hucre-vurgu",
                       ".satir-sorunlu", ".satir-tahta-sorunlu", ".serit-git", ".serit-liste", "#acil-serit",
                       ".hucre-yukleniyor"):
            self.assertTrue(_kurallar(secici), secici)

    def test_js_kimlikleri_sayfada_var(self):
        # Yeniden adlandırılan/kaldırılan bir kimlik JS'te null hatasına yol açmasın
        betik = "".join(re.findall(r"<script>(.*?)</script>", self.html, re.DOTALL))
        for kimlik in set(re.findall(r"getElementById\('([^'$]+)'\)", betik)) | set(re.findall(r"metniYaz\('([^']+)'", betik)):
            self.assertIn(f'id="{kimlik}"', self.html, kimlik)

    def test_bos_durum(self):
        istek = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"",
                         "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})
        html = uygulama.templates.get_template("pano.html").render(
            request=istek, tarih="2026-10-30", bugun="2026-10-30", siniflar=[], sinif_tahta={},
            ders_saatleri=[], ilk_durum=None)
        self.assertIn('class="bos-durum"', html)
        self.assertNotIn('id="pano-tablo"', html)


if __name__ == "__main__":
    unittest.main()
