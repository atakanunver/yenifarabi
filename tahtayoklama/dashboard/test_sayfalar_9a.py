"""Task 9a: yoklama, iletişim ve diğer sayfalar yeni tasarımda (eski sınıf yok, JS'in aradığı kimlikler duruyor)."""
import re
import unittest
from pathlib import Path

DIZIN = Path(__file__).resolve().parent
SABLONLAR = DIZIN / "templates"
ESKI = re.compile(
    r"\b(btn-ikincil|btn-birincil|btn-kucuk|yeni-form|admin-tablo|pill(?:-[a-z]+)?|pano-ozet(?:-[a-z]+)?|kenar-oge|"
    r"kenar-alt-oge|etiket|etiket-uyari|rapor-aciklama|tablo-sarici|kpi(?:-[a-z]+)?|form-kutu|filtre-bar|"
    r"kr-bos(?:-baslik)?|durum-ozet(?:-[a-z]+)?|sorun-[a-z]+|form-grup|form-etiket|form-secim|form-girdi)\b")

# şablon -> (kimlikler/öznitelikler ki sayfa JS'i ya da test arar)
SAYFALAR = {
    "bugun.html": [],
    "admin_rapor.html": ['name="baslangic"', 'name="bitis"', 'name="sinif_id"', "/admin/rapor/csv?tip=ozet",
                         "/admin/rapor/csv?tip=detay", 'id="detay"'],
    "aylik_ozet.html": ["/aylik-ozet?ay="],
    "kulup_yoklama.html": ['name="tarih"', 'action="/kulup-yoklama"'],
    "veli_mesajlari.html": ['id="vm-liste"', 'data-id="{{ m.id }}"', 'data-eylem="sil"', 'data-eylem="engelle"',
                            "vm-engel-neden", "vm-onay"],
    "acil.html": ['id="durum"', 'id="tatbikat"', 'id="yanlis"', 'id="ekran-kapat"', 'id="anons-sec"',
                  'id="anons-cal"', 'id="tahta-mod"', 'id="tahta-mod-degistir"', 'id="sonuc-blok"',
                  'id="sonuc"', 'id="olaylar"', "data-zil=", 'id="mod-kutu"', 'id="mod-yazi"', "acil-dugme"],
    "yakinda.html": [],
    "kazanim_rapor.html": ['id="btn-sonuc-guncelle"', 'id="btn-sms-gonder"', 'id="btn-yeni-test-ac"',
                           'id="kr-uret-panel"', 'id="kr-uret-form"', 'id="kr-sinif"', 'id="kr-ders"',
                           'id="kr-tarih"', 'id="btn-test-uret-kaydet"'],
}


class TestSayfalar9a(unittest.TestCase):
    def test_eski_sinif_yok(self):
        for ad in list(SAYFALAR):
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            kullanilan = []
            for kume in re.findall(r'class="([^"]*)"', metin):
                kullanilan += [s for s in kume.split() if ESKI.fullmatch(s)]
            self.assertEqual(kullanilan, [], ad)
        js = (DIZIN / "static" / "veli_mesajlari.js").read_text(encoding="utf-8")
        self.assertIsNone(ESKI.search(js))

    def test_kimlikler_duruyor(self):
        for ad, parcalar in SAYFALAR.items():
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            for p in parcalar:
                self.assertIn(p, metin, f"{ad}: {p}")

    def test_buyuk_harf_yazi_yok(self):
        for ad in SAYFALAR:
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            self.assertNotIn("text-transform", metin, ad)
            govde = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|<script.*?</script>|<[^>]+>", " ", metin, flags=re.DOTALL)
            self.assertIsNone(re.search(r"\b[A-ZÇĞİÖŞÜ]{4,}\b(?:\s+[A-ZÇĞİÖŞÜ]{2,}\b)*", govde), ad)

    def test_satir_ici_stil_ham_renk_yok(self):
        for ad in SAYFALAR:
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", metin), ad)
            self.assertNotIn("rgba(", metin, ad)


if __name__ == "__main__":
    unittest.main()
