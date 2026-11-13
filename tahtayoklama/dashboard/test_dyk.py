"""dyk.py veri katmanı + scripts/dyk_ice_aktar.py xlsx ayrıştırma testleri (uydurma veri).
Gerçek config/dyk.json'a ASLA dokunmaz (geçici dosya)."""
import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import dyk

_spec = importlib.util.spec_from_file_location(
    "dyk_ice_aktar", Path(__file__).resolve().parent / "scripts" / "dyk_ice_aktar.py")
ice_aktar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ice_aktar)

ORNEK = {
    "siniflar": {
        "11": {"derslik": "10-A", "ad": "11. Sınıf DYK", "dersler": [
            {"kod": "DYK-11-COGRAFYA", "ad": "Coğrafya", "ogretmen": "Hoca A",
             "uyeler": [{"no": 5, "ad_soyad": "Deniz Deneme"}, {"no": 7, "ad_soyad": "Ayşe Örnek"}]}]},
        "12": {"derslik": "12-B", "ad": "12. Sınıf DYK", "dersler": [
            {"kod": "DYK-12-TARIH", "ad": "Tarih / İnkılap Tarihi", "ogretmen": "Hoca B",
             "uyeler": [{"no": 9, "ad_soyad": "Can Sahte"}]}]},
    },
    "program": {
        "11": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30", "kod": "DYK-11-COGRAFYA", "ders_no": 1}],
        "12": [{"gun": "cuma", "bas": "16:00", "bit": "17:30", "kod": "DYK-12-TARIH", "ders_no": 1}],
    },
}


class DykDosyasi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.yol = Path(self._tmp.name) / "dyk.json"
        self.yol.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
        yama = patch.object(dyk, "DYK_DOSYASI", self.yol)
        yama.start()
        self.addCleanup(yama.stop)


class TestOkuma(DykDosyasi):
    def test_dersler_duz_liste_ek_alanlarla(self):
        liste = dyk.dersler()
        self.assertEqual([d["kod"] for d in liste], ["DYK-11-COGRAFYA", "DYK-12-TARIH"])
        self.assertEqual((liste[0]["sinif_grubu"], liste[0]["derslik"]), ("11", "10-A"))
        self.assertEqual((liste[1]["sinif_grubu"], liste[1]["derslik"]), ("12", "12-B"))

    def test_bul(self):
        self.assertEqual(dyk.bul("DYK-12-TARIH")["ogretmen"], "Hoca B")
        self.assertIsNone(dyk.bul("DYK-99-YOK"))

    def test_isimler(self):
        self.assertEqual(dyk.isimler(dyk.bul("DYK-11-COGRAFYA")), {"5": "Deniz Deneme", "7": "Ayşe Örnek"})

    def test_roster_json_sema(self):
        veri = json.loads(dyk.roster_json(dyk.bul("DYK-11-COGRAFYA")))
        self.assertEqual(veri["sinif"], "DYK-11-COGRAFYA")
        self.assertEqual(veri["ad"], "11. sınıf Coğrafya")
        self.assertEqual(veri["ogrenciler"][0], {"no": 5, "ad_soyad": "Deniz Deneme"})

    def test_rosterlari_derslige_gore(self):
        self.assertEqual(list(dyk.rosterlari("10-A")), ["DYK-11-COGRAFYA"])
        self.assertEqual(list(dyk.rosterlari("12-B")), ["DYK-12-TARIH"])
        self.assertEqual(dyk.rosterlari("9-A"), {})
        self.assertEqual(dyk.rosterlari(None), {})

    def test_program_json(self):
        veri = json.loads(dyk.program_json("12-B"))
        self.assertEqual(veri["oturumlar"][0]["kod"], "DYK-12-TARIH")
        self.assertIsNone(dyk.program_json("9-A"))
        self.assertIsNone(dyk.program_json(None))

    def test_dosya_yok_ya_da_bozuk(self):
        bos = {"siniflar": {}, "program": {}}
        self.yol.write_text("{bozuk", encoding="utf-8")
        self.assertEqual(dyk.yukle(), bos)
        self.assertEqual(dyk.dersler(), [])
        self.yol.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(dyk.yukle(), bos)
        self.yol.unlink()
        self.assertEqual(dyk.yukle(), bos)
        self.assertEqual(dyk.rosterlari("10-A"), {})


class TestUyeAyristir(unittest.TestCase):
    def test_sutun_uzunlugu_uyusmazsa_hata(self):
        with self.assertRaises(ValueError):
            dyk.uyeleri_ayristir(["1", "2"], ["A"])
    def test_bos_satir_atlanir_ve_alanlar_temizlenir(self):
        self.assertEqual(dyk.uyeleri_ayristir([" 12 ", ""], [" Ali Veli ", ""]),
                         [{"no": 12, "ad_soyad": "Ali Veli"}])

    def test_gecersiz_no_reddedilir(self):
        for no in ("abc", "0", "-3", "1.5"):
            with self.assertRaises(ValueError, msg=no):
                dyk.uyeleri_ayristir([no], ["Ali"])

    def test_ad_bos_ya_da_cok_uzun(self):
        with self.assertRaises(ValueError):
            dyk.uyeleri_ayristir(["5"], [""])
        with self.assertRaises(ValueError):
            dyk.uyeleri_ayristir(["5"], ["x" * 81])

    def test_yinelenen_no_reddedilir(self):
        with self.assertRaises(ValueError):
            dyk.uyeleri_ayristir(["5", "5"], ["Ali", "Can"])


class TestGuncelle(DykDosyasi):
    def test_guncelle_kod_ve_program_degismez(self):
        dyk.guncelle("DYK-11-COGRAFYA", " Hoca C ", [{"no": 1, "ad_soyad": "Sahte Biri"}])
        d = dyk.bul("DYK-11-COGRAFYA")
        self.assertEqual((d["ogretmen"], d["uyeler"]), ("Hoca C", [{"no": 1, "ad_soyad": "Sahte Biri"}]))
        self.assertEqual(dyk.yukle()["program"], ORNEK["program"])
        self.assertEqual(dyk.bul("DYK-12-TARIH")["ogretmen"], "Hoca B")  # diğer ders etkilenmez
        self.assertEqual(oct(os.stat(self.yol).st_mode & 0o777), "0o600")  # öğrenci verisi

    def test_bilinmeyen_kod(self):
        with self.assertRaises(KeyError):
            dyk.guncelle("DYK-11-YOK", "x", [])

    def test_ogretmen_cok_uzun(self):
        with self.assertRaises(ValueError):
            dyk.guncelle("DYK-11-COGRAFYA", "x" * 81, [])
        self.assertEqual(dyk.bul("DYK-11-COGRAFYA")["ogretmen"], "Hoca A")


def _xlsx_yaz(yol: Path, satirlar: list[tuple], baslik_ust_bos: bool = True) -> None:
    """Küçük sahte xlsx: ilk satır boş, 2. satır başlık, sonra veri (sharedStrings'li)."""
    metinler: list[str] = []

    def sid(s: str) -> int:
        if s not in metinler:
            metinler.append(s)
        return metinler.index(s)

    rows = ['<row r="1"><c r="C1"/></row>'] if baslik_ust_bos else []
    r = len(rows) + 1
    rows.append(f'<row r="{r}"><c r="A{r}" t="s"><v>{sid("SIRA")}</v></c><c r="B{r}" t="s"><v>{sid("OKUL NO")}</v></c>'
                f'<c r="C{r}" t="s"><v>{sid("ÖĞRENCİ AD-SOYAD")}</v></c></row>')
    for sira, no, ad in satirlar:
        r += 1
        b = f'<c r="B{r}" t="s"><v>{sid(no)}</v></c>' if isinstance(no, str) else f'<c r="B{r}"><v>{no}</v></c>'
        rows.append(f'<row r="{r}"><c r="A{r}"><v>{sira}</v></c>{b}<c r="C{r}" t="s"><v>{sid(ad)}</v></c></row>')
    rows.append(f'<row r="{r + 1}"><c r="A{r + 1}"/><c r="D{r + 1}"/></row>')  # boş satır
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(yol, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(rows)}</sheetData></worksheet>')
        z.writestr("xl/sharedStrings.xml",
                   f'<sst {ns}>' + "".join(f"<si><t>{m}</t></si>" for m in metinler) + "</sst>")


class TestIceAktar(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dizin = Path(self._tmp.name)

    def test_ders_kodu_dosya_adindan(self):
        ders = ice_aktar.ders_kodu
        self.assertEqual(ders("11 COĞRAFYA.xlsx"), "COGRAFYA")
        self.assertEqual(ders("11 DİN.xlsx"), "DIN")
        self.assertEqual(ders("12 EDEBİYAT.xlsx"), "EDEBIYAT")
        self.assertEqual(ders("12 KİMYA.xlsx"), "KIMYA")
        self.assertEqual(ders("12 TARİH (BOTH).xlsx"), "TARIH")
        self.assertEqual(ders("11 tarih.xlsx"), "TARIH")

    def test_xlsx_ayristir_no_int_ve_bos_satir_atlanir(self):
        yol = self.dizin / "a.xlsx"
        _xlsx_yaz(yol, [(7, 105, "Deniz Deneme"), (1, "42", "Ayşe Örnek")])
        self.assertEqual(ice_aktar.xlsx_ayristir(yol),
                         [{"no": 105, "ad_soyad": "Deniz Deneme"}, {"no": 42, "ad_soyad": "Ayşe Örnek"}])

    def test_basliksiz_xlsx_hata(self):
        yol = self.dizin / "b.xlsx"
        with zipfile.ZipFile(yol, "w") as z:
            z.writestr("xl/worksheets/sheet1.xml",
                       '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<sheetData/></worksheet>')
        with self.assertRaises(ValueError):
            ice_aktar.xlsx_ayristir(yol)

    def test_klasor_isle_ve_program(self):
        k = self.dizin / "k11"
        k.mkdir()
        for ad in ("COĞRAFYA", "DİN", "EDEBİYAT", "KİMYA", "TARİH"):
            _xlsx_yaz(k / f"11 {ad}.xlsx", [(1, 10, "Biri Sahte"), (2, 11, "Öteki Sahte")])
        sonuc = ice_aktar.klasor_isle("11", k)
        self.assertEqual(sonuc["derslik"], "10-A")
        self.assertEqual([d["kod"] for d in sonuc["dersler"]],
                         ["DYK-11-COGRAFYA", "DYK-11-DIN", "DYK-11-EDEBIYAT", "DYK-11-KIMYA", "DYK-11-TARIH"])
        self.assertTrue(all(len(d["uyeler"]) == 2 for d in sonuc["dersler"]))
        prog = ice_aktar.program_uret()
        self.assertEqual(len(prog["11"]), 6)
        self.assertEqual(len(prog["12"]), 6)
        self.assertEqual(prog["11"][-1], {"gun": "cumartesi", "bas": "10:40", "bit": "12:10",
                                          "kod": "DYK-11-TARIH", "ders_no": 3})

    def test_ayni_no_ayni_adla_tekrar_atlanir_farkli_adla_hata(self):
        k = self.dizin / "k12a"
        k.mkdir()
        for ad in ("COĞRAFYA", "DİN", "EDEBİYAT", "KİMYA", "TARİH"):
            _xlsx_yaz(k / f"12 {ad}.xlsx", [(1, 10, "Biri Sahte"), (2, 10, "Biri Sahte")])
        with patch("builtins.print"):
            sonuc = ice_aktar.klasor_isle("12", k)
        self.assertTrue(all(len(d["uyeler"]) == 1 for d in sonuc["dersler"]))
        _xlsx_yaz(k / "12 DİN.xlsx", [(1, 10, "Biri Sahte"), (2, 10, "Başka Sahte")])
        with self.assertRaises(ValueError):
            ice_aktar.klasor_isle("12", k)

    def test_eksik_ders_dosyasi_hata(self):
        k = self.dizin / "k12"
        k.mkdir()
        _xlsx_yaz(k / "12 DİN.xlsx", [(1, 10, "Biri Sahte")])
        with self.assertRaises(ValueError):
            ice_aktar.klasor_isle("12", k)


if __name__ == "__main__":
    unittest.main()
