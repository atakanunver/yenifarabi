"""sistem_durumu.py birim testleri (2026-09-25, Farabi Health genişletmesi)."""
import asyncio
import json
import unittest
from unittest.mock import patch

import sistem_durumu as sd
import tahta_saglik


class TestYardimcilar(unittest.TestCase):
    def test_sure_saniye_gin_bicimleri(self):
        self.assertAlmostEqual(sd._sure_saniye("5.580262s"), 5.580262)
        self.assertAlmostEqual(sd._sure_saniye("842.1ms"), 0.8421)
        self.assertAlmostEqual(sd._sure_saniye("1m4s"), 64)
        self.assertAlmostEqual(sd._sure_saniye("1h10m9s"), 4209)
        self.assertIsNone(sd._sure_saniye("abc"))

    def test_gin_satiri_yalnizca_chat_generate(self):
        chat = '[GIN] 2026/09/22 - 06:04:03 | 200 | 25.141516223s |  192.168.23.243 | POST     "/api/chat"'
        pull = '[GIN] 2026/09/03 - 15:43:59 | 200 |          1m5s |                 | POST     "/api/pull"'
        self.assertIsNotNone(sd._GIN_RE.search(chat))
        self.assertIsNone(sd._GIN_RE.search(pull))

    def test_port_bul(self):
        self.assertEqual(sd._port_bul("farabi-api", "argv[]=uvicorn main:app --host 0.0.0.0 --port 8000 ;", ""), 8000)
        self.assertEqual(sd._port_bul("ollama", "argv[]=ollama serve", "OLLAMA_HOST=0.0.0.0:11434 X=1"), 11434)
        # son tanım kazanır (drop-in'ler)
        self.assertEqual(sd._port_bul("ollama", "", "OLLAMA_HOST=0.0.0.0:11434 OLLAMA_HOST=0.0.0.0"), 11434)
        self.assertEqual(sd._port_bul("open-webui", "", "PORT=80"), 80)

    def test_ortam_degiskeni_son_tanim(self):
        self.assertEqual(sd._ortam_degiskeni("CUDA_VISIBLE_DEVICES= CUDA_VISIBLE_DEVICES=1", "CUDA_VISIBLE_DEVICES"), "1")

    def test_saglik_etiketi(self):
        self.assertEqual(sd._saglik_etiketi(False, None), "hata")
        self.assertEqual(sd._saglik_etiketi(True, {"durum": "down", "kod": None, "ms": None}), "hata")
        self.assertEqual(sd._saglik_etiketi(True, {"durum": "up", "kod": 200, "ms": 5000}), "yavas")
        self.assertEqual(sd._saglik_etiketi(True, {"durum": "up", "kod": 200, "ms": 3}), "ok")

    def test_zil_401_ayakta_sayilir(self):
        self.assertEqual(sd._http_sonucu({"kod": 401, "ms": 2, "hata": None}, (200, 401))["durum"], "up")
        self.assertEqual(sd._http_sonucu({"kod": 500, "ms": 2, "hata": None}, (200,))["durum"], "down")


class TestTopla(unittest.TestCase):
    def test_canli_toplama_eski_anahtarlari_korur_ve_sir_sizdirmaz(self):
        """kenar.js'in okuduğu anahtarlar (cpu.sicaklik_c, servisler[].aktif) korunmalı;
        birim Environment'ındaki proxy parolası JSON'a girmemeli."""
        veri = asyncio.run(sd.durum_topla(trend=True))
        for anahtar in ("cpu", "gpu", "bellek", "disk", "servisler", "ollama_modelleri",
                        "yukleme", "calisma_suresi", "saglik", "ai", "veritabani", "trend"):
            self.assertIn(anahtar, veri)
        for s in veri["servisler"]:
            self.assertIn("aktif", s)
            self.assertIn("etiket", s)
        metin = json.dumps(veri, ensure_ascii=False)
        self.assertNotIn("Environment", metin)
        self.assertNotIn("HTTPS_PROXY", metin)
        self.assertNotIn("@192.168.23.243", metin)

    def test_tahtalar_anahtari_her_cagride_okunur(self):
        ornek = [{"tahta_ad": "9-A", "durum": "iyi"}]
        with patch.object(sd, "_tahtalar_oku", return_value=ornek):
            veri = asyncio.run(sd.durum_topla())
        self.assertEqual(veri["tahtalar"], ornek)

    def test_tahtalar_db_hatasinda_bos_liste_sayfa_bozulmaz(self):
        with patch.object(tahta_saglik, "liste", side_effect=RuntimeError("db yok")):
            veri = asyncio.run(sd.durum_topla())
        self.assertEqual(veri["tahtalar"], [])
        self.assertIn("cpu", veri)

    def test_trend_istenmezse_eklenmez(self):
        veri = asyncio.run(sd.durum_topla())
        self.assertNotIn("trend", veri)

    def test_uzak_kontrol_modeme_baglanmaz(self):
        hedefler = []
        with patch.object(sd, "_tcp_prob", side_effect=lambda h, p: hedefler.append((h, p)) or
                          {"kod": "tcp", "ms": 1.0, "hata": None}), \
             patch.object(sd, "_http_prob", side_effect=lambda url: hedefler.append(url) or
                          {"kod": 200, "ms": 1.0, "hata": None}):
            for tanim in sd.UZAK_SERVISLER:
                sd._uzak_kontrol(tanim)
        self.assertFalse(any("192.168.8." in str(h) for h in hedefler))


class TestDbSorguRag(unittest.TestCase):
    def test_rag_istatistikleri_webui_satirlarini_dislar(self):
        # rag_24s, rag_7g, rag_son, rag_30dk — dördü de metrik'ten okur
        self.assertEqual(sd._DB_SORGU.count("FROM metrik"), 4)
        self.assertEqual(sd._DB_SORGU.count("coalesce(sonuc, '') NOT LIKE 'webui_%'"), 4)


if __name__ == "__main__":
    unittest.main()
