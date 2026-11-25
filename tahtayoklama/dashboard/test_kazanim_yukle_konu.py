"""scripts/kazanim_yukle.py tema/konu çıkarımı (2026-11-25). Plan dosyası
okunmaz (docx/openpyxl bu venv'de yok); tablo_satirlari elle kurulmuş
satırlarla, gerçek planlarda görülen başlıklarla beslenir."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import kazanim_yukle as ky


def tablo(*satirlar):
    return [[(m, None) for m in s] for s in satirlar]


class TestBaslikTuru(unittest.TestCase):
    def test_gercek_basliklar(self):
        for m in ("ÜNİTE", "TEMA", "ÜNİTE/TEMA", "ÜNİTE/ TEMA", "Theme", "ÖĞRENME ALANI",
                  "ÖĞRENME ALANI / TEMA", "ÜNİTE KONULAR", "Ünite"):
            self.assertEqual(ky.baslik_turu(m), "tema", m)
        for m in ("KONU", "KONU (İÇERİK ÇERÇEVESİ)", "İÇERİK ÇERÇEVESİ", "KONU / İÇERİK",
                  "ALT ÖĞRENME ALANI", "CONTENT FRAME", "Öğrenme Alanı / Konu",
                  "METİN TAHLİLİ (ANLAMA) OKUMA BECERİLERİ ALANI - KONU / İÇERİK ÇERÇEVESİ"):
            self.assertEqual(ky.baslik_turu(m), "konu", m)

    def test_grup_ve_kazanim_basliklari_degil(self):
        for m in ("ÜNİTE/TEMA - İÇERİK ÇERÇEVESİ", "ÜNİTE - KONU", "ÜNİTE İÇERİK ÇERÇEVESİ",
                  "THEME / CONTENT FRAME", "ÖĞRENME ÇIKTILARI", "KAZANIM", "HAFTA", ""):
            self.assertIsNone(ky.baslik_turu(m), m)


class TestTemaKonuTemizle(unittest.TestCase):
    def test_tekrar_bosluk_kisaltma(self):
        self.assertEqual(ky.tema_konu_temizle("2. ÜNİTE: GELİŞİMİ ANLAMAK" * 3), "2. ÜNİTE: GELİŞİMİ ANLAMAK")
        self.assertEqual(ky.tema_konu_temizle("  Fizik\n Bilimi "), "Fizik Bilimi")
        self.assertLessEqual(len(ky.tema_konu_temizle("kelime " * 80)), ky.MAKS_UZUNLUK + 1)
        self.assertEqual(ky.tema_konu_temizle("Optik"), "Optik")  # kısa ama gerçek tema

    def test_yer_tutucular(self):
        for m in ("OKUL TEMELLİ PLANLAMA*", "SCHOOL BASED PLANNING", "SINAV HAFTASI",
                  "ARATATİL12-16 Nisan", "", None, "1."):
            self.assertEqual(ky.tema_konu_temizle(m), "", m)


class TestTabloSatirlari(unittest.TestCase):
    def test_sutunlar_ve_bant(self):
        t = tablo(
            ["TARİH", "HAFTA", "SAAT", "ÜNİTE", "İÇERİK ÇERÇEVESİ", "ÖĞRENME ÇIKTILARI"],
            ["14-18 Eylül", "1. Hafta", "2", "1. ÜNİTE: X", "Konu A", "FB.9.1.1. Kazanım"],
            ["", "", "", "dipnot", "imza", "açıklama devam"],  # devam satırı: tema/konu alınmaz
            ["21-25 Eylül", "2. Hafta", "2", "Yıl Sonu", "Yıl Sonu", "Yıl Sonu"],  # satır boyu bant
        )
        r = list(ky.tablo_satirlari(t, {}))
        self.assertEqual(r[0][0], 1)
        self.assertEqual(r[0][5:], ("1. ÜNİTE: X", "Konu A"))
        self.assertEqual(r[1][5:], ("", ""))
        self.assertEqual(r[2][5:], ("", ""))

    def test_kazanim_ciktisi_degismez(self):
        t = tablo(
            ["TARİH", "HAFTA", "SAAT", "ÜNİTE", "KONU", "KAZANIM"],
            ["14-18 Eylül", "1. Hafta", "2", "Ü", "K", "9.1.1. Bir"],
        )
        r = list(ky.tablo_satirlari(t, {}))
        self.assertEqual(r[0][:5], (1, ky.date(2026, 9, 14), "9.1.1. Bir", None, False))

    def test_edebiyat_tablo_temasi(self):
        t = tablo(
            ["TEMA", "1", "1. TEMA: SÖZÜN İNCELİĞİ", "ÖĞRENME ÇIKTILARI VE SÜREÇ BİLEŞENLERİ"],
            ["HAFTA", "GÜN", "OKUMA BECERİLERİ ALANI - KONU / İÇERİK ÇERÇEVESİ", "OKUMA BECERİLERİ ALANI – ÖĞRENME ÇIKTILARI"],
            ["1.", "", "Şiir", "TDE1.1. Okur"],
            ["2.", "", "", "SOSYAL ETKİNLİK"],
        )
        r = list(ky.tablo_satirlari(t, {}))
        self.assertEqual(r[0][5:], ("1. TEMA: SÖZÜN İNCELİĞİ", "Şiir"))
        self.assertEqual(r[1][5], "")  # yer tutucu haftaya tablo teması yazılmaz

    def test_basliksiz_devam_tablosu_ofset(self):
        bellek = {}
        list(ky.tablo_satirlari(tablo(
            ["AY", "HAFTA", "SAAT", "ÜNİTE/TEMA", "KONU (İÇERİK ÇERÇEVESİ)", "ÖĞRENME ÇIKTILARI"],
            ["EYLÜL", "1. Hafta: 14-18 Eylül", "6", "SAYILAR", "Üslü", "9.1.1. A"],
        ), bellek))
        r = list(ky.tablo_satirlari(tablo(
            ["5. Hafta: 12-16 Ekim", "6", "GEOMETRİ", "Alan", "10.1.3. B", "a) süreç"],
        ), bellek))
        self.assertEqual(r[0][2], "10.1.3. B")
        self.assertEqual(r[0][5:], ("GEOMETRİ", "Alan"))


if __name__ == "__main__":
    unittest.main()
