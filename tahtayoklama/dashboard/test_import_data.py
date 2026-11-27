"""Sentetik e-Okul dosyaları ile kuru karşılaştırma ve kayıt testleri."""

import csv
import unittest
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from scripts import import_data as imp


class TestImport(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dizin = Path(tmp.name)
        self.c = MagicMock()
        self.veri = self.enterContext(patch.object(imp, "veri", wraps=imp.veri))
        self.veri.ogrenciler.return_value = [
            {
                "okul_no": no,
                "ad_soyad": "Deneme Kişisi",
                "cinsiyet": "Kız",
                "telefon": None,
                "dogum_tarihi": date(2000, 1, 1),
                "aktif": True,
                "sinif": "9-A",
            }
            for no in (99001, 99002)
        ]
        self.veri.siniflar.return_value = [{"ad": "9-A"}]

    def test_csv_kuru_ve_yazma(self):
        self.veri.ogrenciler.return_value[0]["ad_soyad"] = "AYŞE IŞIK"
        yol = self.dizin / "liste.csv"
        with yol.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter=";").writerows(
                [
                    ["Ön bilgi"],
                    ["Adı", "Soyadı", "Sınıf/Şube", "Öğrenci No", "Cinsiyet"],
                    ["Ayşe", "Işık", "9. Sınıf / A Şubesi", "99001", "Kız"],
                    ["Yeni", "Soyadı", "9/B", "99002", ""],
                    ["şule", "ilgin", "9-B", "99003", "E"],
                    ["Test", "Kaydı", "9", "99004", "E"],
                    ["Test", "Kaydı", "9-B", "99003", "E"],
                ]
            )
        beklenen = (
            {"eklenecek": 1, "güncellenecek": 1, "değişmeyen": 1, "hatalı": 2},
            {"9-A": 1, "9-B": 2},
            {"şube yok": 1, "tekrarlanan no": 1},
            [],
            1,
        )
        self.assertEqual(imp.aktar(self.c, yol), beklenen)
        self.veri.sinif_ekle.assert_not_called()
        self.veri.ogrenci_kaydet.assert_not_called()
        self.veri.sinif_ekle.return_value = self.veri.ogrenci_kaydet.return_value = None
        self.assertEqual(imp.aktar(self.c, yol, True), beklenen)
        self.veri.sinif_ekle.assert_called_once_with(self.c, "9-B")
        self.veri.ogrenci_kaydet.assert_any_call(
            self.c, 99002, "YENİ SOYADI", "Kız", None, "2000-01-01", "9-B", yeni=False
        )
        self.veri.ogrenci_kaydet.assert_any_call(
            self.c, 99003, "ŞULE İLGİN", "Erkek", None, None, "9-B", yeni=True
        )
        self.assertEqual(self.veri.ogrenci_kaydet.call_count, 2)

    def test_xlsx_seyrek_sutunlar(self):
        yol = self.dizin / "liste.xlsx"
        root = ET.Element(
            "worksheet",
            xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        )
        data = ET.SubElement(root, "sheetData")
        for n, values in enumerate(
            [
                ["Başlık"],
                ["Sınıf", "Adı Soyadı", "OKUL NO"],
                ["9/A", "Deneme Kişisi", "99001"],
            ],
            1,
        ):
            row = ET.SubElement(data, "row")
            for col, value in zip(["B", "E", "H"], values):
                c = ET.SubElement(row, "c", r=f"{col}{n}", t="inlineStr")
                ET.SubElement(ET.SubElement(c, "is"), "t").text = value
        with zipfile.ZipFile(yol, "w") as z:
            z.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
            z.writestr("xl/worksheets/sheet2.xml", ET.tostring(root))
        self.assertEqual(imp.aktar(self.c, yol)[0]["değişmeyen"], 1)

    def xlsx(self, sayfalar):
        yol = self.dizin / "liste.xlsx"
        kitap = ET.Element(
            "workbook",
            {
                "xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            },
        )
        liste = ET.SubElement(kitap, "sheets")
        baglar = ET.Element("Relationships")
        with zipfile.ZipFile(yol, "w") as z:
            for n, (ad, rows) in enumerate(sayfalar.items(), 1):
                hedef = f"worksheets/sheet{n}.xml"
                ET.SubElement(liste, "sheet", name=ad, attrib={"r:id": f"r{n}"})
                ET.SubElement(baglar, "Relationship", Id=f"r{n}", Target=hedef)
                data = ET.Element("sheetData")
                for j, values in enumerate(rows, 1):
                    row = ET.SubElement(data, "row")
                    for col, value in zip("ABCDEFGH", values):
                        c = ET.SubElement(row, "c", r=f"{col}{j}", t="inlineStr")
                        ET.SubElement(ET.SubElement(c, "is"), "t").text = value
                root = ET.Element("worksheet")
                root.append(data)
                z.writestr("xl/" + hedef, ET.tostring(root))
            z.writestr("xl/workbook.xml", ET.tostring(kitap))
            z.writestr("xl/_rels/workbook.xml.rels", ET.tostring(baglar))
        return yol

    def test_seviye_ve_basliktan_sube(self):
        self.veri.ogrenciler.return_value[1]["sinif"] = "12-B"
        for sinif in ("10-A", "10/A", "10 A"):
            with self.subTest(sinif=sinif):
                yol = self.xlsx(
                    {
                        "Dokuz": [
                            ["OKUL NO", "Adı Soyadı", "SINIF"],
                            ["99001", "Deneme Kişisi", "9. Sınıf"],
                            ["99003", "Yeni Kişi", "9.Sınıf"],
                            ["99002", "Seviye Farkı", "9.Sınıf"],
                        ],
                        "On iki": [
                            ["OKUL NO", "ADI SOYADI", "SINIF"],
                            ["99002", "Yeni Ad", "12.SINIF"],
                        ],
                        "On": [
                            [sinif + "  SINIFI ÖĞRENCİ LİSTESİ"],
                            [
                                "OKUL NO",
                                "ÖĞRENCİ AD-SOYAD",
                                "VELİ ADI",
                                "TC",
                                "TELEFON",
                            ],
                            ["99004", "Deneme Yeni", "Örnek Veli", "", ""],
                            ["x", "Test", "", "", ""],
                            ["99005", "", "", "", ""],
                        ],
                        "Açıklama": [],
                    }
                )
                self.assertEqual(
                    imp.aktar(self.c, yol),
                    (
                        {
                            "eklenecek": 1,
                            "güncellenecek": 1,
                            "değişmeyen": 1,
                            "hatalı": 4,
                        },
                        {"9-A": 1, "12-B": 1, "10-A": 1},
                        {"şube yok": 2, "no geçersiz": 1, "ad boş": 1},
                        ["Açıklama"],
                        3,
                    ),
                )
        self.veri.sinif_ekle.assert_not_called()
        self.veri.ogrenci_kaydet.assert_not_called()

    def test_taninmayan_sayfa_cikis_kodu(self):
        yol = self.xlsx({"Boş liste": [["Açıklama"]]})
        with patch.object(imp.psycopg, "connect"), redirect_stdout(StringIO()) as out:
            self.assertEqual(imp.main([str(yol)]), 2)
        self.assertIn("tanınmayan sayfa: Boş liste", out.getvalue())

    def test_dsn_zorunlu(self):
        with (
            patch.dict(imp.os.environ, {}, clear=True),
            patch.object(imp.psycopg, "connect") as baglan,
        ):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as hata:
                imp.main(["liste.csv", "--uygula"])
            self.assertEqual(hata.exception.code, 2)
            baglan.assert_not_called()
