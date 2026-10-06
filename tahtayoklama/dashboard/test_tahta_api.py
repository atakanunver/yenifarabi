"""tahta_api.py (/api/v1/tahta/*) ve yoklayici'nın "tahta iter" yolu testleri.

httpx yok → TestClient kullanılamaz; Starlette Request elle kurulur ve
endpoint koroutinleri doğrudan çağrılır (bkz. test_api_durum.py)."""

import asyncio
import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.requests import Request

import admin
import db
import ssh_istemci
import tahta_api
import yoklayici
import zil

TOKEN_A = "token-9a-gizli"
TOKEN_F = "token-fenlab-gizli"
TARIH = "2026-10-06"  # Salı


def _sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


class TestTahtaApi(unittest.TestCase):
    def setUp(self):
        # "Bugün" sabit: TARIH (2026-10-06) — geçmiş/gelecek gün kuralları
        # gerçek takvime göre kaymasın, testler her gün aynı sonucu versin.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self._saat = patch("zil.simdi_istanbul", return_value=datetime(
            2026, 10, 6, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")))
        self._saat.start()
        self.addCleanup(self._saat.stop)
        self._tmp = TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._eski = (db.DB_YOLU, tahta_api.TOKEN_DOSYASI, tahta_api.KAZANIM_DOSYASI)
        tahta_api.KAZANIM_DOSYASI = tmp / "kazanimlar.json"
        tahta_api.KAZANIM_DOSYASI.write_text(json.dumps({
            "haftalar": {"4": "2026-10-05"},
            "kazanimlar": {"9": {"matematik": {"4": "9.1.2. ..."}},
                           "12": {"kimya": {"4": "KİM.12..."}}},
        }, ensure_ascii=False), encoding="utf-8")
        db.DB_YOLU = tmp / "test.db"
        db.semayi_kur()
        tahta_api.TOKEN_DOSYASI = tmp / "tokenlar.json"
        tahta_api.TOKEN_DOSYASI.write_text(
            json.dumps({"9-A": _sha(TOKEN_A), "fenlab": _sha(TOKEN_F)})
        )
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '9-A'), (2, '9-B')")
        conn.execute(
            "INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES "
            "(1, 1, 'Ali Veli'), (1, 2, 'Ayse Kaya')"
        )
        conn.execute(
            "INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id, aktif) VALUES "
            "('9-A', '10.0.0.1', 'ogretmen', 1, 1), "
            "('fenlab', '10.0.0.2', 'ogretmen', NULL, 1)"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU, tahta_api.TOKEN_DOSYASI, tahta_api.KAZANIM_DOSYASI = self._eski
        self._tmp.cleanup()

    # --- yardımcılar ---
    def _istek(self, token=TOKEN_A, govde=None, basliklar=None, yol="/x", method="POST"):
        h = []
        if token is not None:
            h.append((b"authorization", f"Bearer {token}".encode()))
        for k, v in (basliklar or {}).items():
            h.append((k.lower().encode(), v.encode()))
        ham = json.dumps(govde).encode() if govde is not None else b""

        async def receive():
            return {"type": "http.request", "body": ham, "more_body": False}

        scope = {
            "type": "http", "method": method, "path": yol, "headers": h,
            "query_string": b"", "client": ("192.168.23.245", 5000),
        }
        return Request(scope, receive)

    def _kayit(self, **kw):
        k = {"sinif": "9-A", "tarih": TARIH, "ders_no": 1,
             "kaydedilme_saati": "09:00:00", "durumlar": {"1": "yok", "2": "var"}}
        k.update(kw)
        return k

    def _it(self, kayit, token=TOKEN_A):
        return asyncio.run(tahta_api.kayit_al(self._istek(token, kayit)))

    def _satir(self, sinif="9-A", ders_no=1):
        conn = db.baglanti()
        try:
            return conn.execute(
                "SELECT * FROM yoklama_onbellek WHERE tarih=? AND sinif=? AND ders_no=?",
                (TARIH, sinif, ders_no),
            ).fetchone()
        finally:
            conn.close()

    # --- testler ---
    def test_kayit_tokensiz_veya_gecersiz_401(self):
        for token in (None, "yanlis-token"):
            with self.assertRaises(HTTPException) as c:
                asyncio.run(tahta_api.kayit_al(self._istek(token, self._kayit())))
            self.assertEqual(c.exception.status_code, 401)
        self.assertIsNone(self._satir())

    def test_kayit_gecerli_yazilir(self):
        yanit = self._it(self._kayit())
        self.assertEqual(yanit.status_code, 200)
        s = self._satir()
        self.assertEqual(s["durum"], "alindi")
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ali Veli"])
        self.assertEqual(s["kaynak_tahta"], "9-A")
        self.assertEqual(s["kaydedilme_saati"], "09:00:00")

    def test_eski_kayit_yeniyi_ezmez(self):
        self._it(self._kayit(kaydedilme_saati="09:10:00", durumlar={"1": "yok", "2": "var"}))
        self._it(self._kayit(kaydedilme_saati="09:05:00", durumlar={"1": "var", "2": "yok"}))
        s = self._satir()
        self.assertEqual(s["kaydedilme_saati"], "09:10:00")
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ali Veli"])
        # daha yeni olan ezer
        self._it(self._kayit(kaydedilme_saati="09:20:00", durumlar={"1": "var", "2": "yok"}))
        s = self._satir()
        self.assertEqual(s["kaydedilme_saati"], "09:20:00")
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ayse Kaya"])

    def test_ayni_kayit_tekrar_gelince_tarihsel_isimler_bozulmaz(self):
        # 2026-10-06 canlı gerilemesi: öğrenci roster'dan çıkarıldıktan sonra
        # aynı kayıt yeniden itilince isim "No N"e dönüşüyordu.
        self._it(self._kayit(kaydedilme_saati="09:10:00", durumlar={"1": "yok"}))
        conn = db.baglanti()
        conn.execute("UPDATE ogrenciler SET aktif = 0 WHERE no = 1")
        conn.commit()
        conn.close()
        self._it(self._kayit(kaydedilme_saati="09:10:00", durumlar={"1": "yok"}))
        self.assertEqual(json.loads(self._satir()["yok_isimleri"]), ["Ali Veli"])

    def test_atanmamis_fenlab_baska_sinif_kaydi_kabul(self):
        self._it(self._kayit(sinif="9-B", durumlar={}), token=TOKEN_F)
        s = self._satir(sinif="9-B")
        self.assertEqual(s["durum"], "alindi")
        self.assertEqual(s["kaynak_tahta"], "fenlab")

    def test_gecersiz_girdiler_422(self):
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (ad, aktif) VALUES ('10-A', 0)")
        conn.commit()
        conn.close()
        kotu = [
            self._kayit(sinif="YOK-1"),
            self._kayit(sinif="10-A"),
            self._kayit(durumlar={"1": "belki"}),
            self._kayit(ders_no=99),
            self._kayit(tarih="2026-13-45"),
            self._kayit(tarih="bugun"),
        ]
        for k in kotu:
            with self.subTest(k=k):
                with self.assertRaises(HTTPException) as c:
                    self._it(k)
                self.assertEqual(c.exception.status_code, 422)

    def test_nabiz_upsert_ve_taze_nabizli(self):
        yanit = asyncio.run(tahta_api.nabiz_al(
            self._istek(govde={"istemci_surum": "1.0", "yoklama_acik": True})))
        self.assertEqual(yanit.status_code, 200)
        asyncio.run(tahta_api.nabiz_al(
            self._istek(govde={"istemci_surum": "1.1", "yoklama_acik": False})))
        conn = db.baglanti()
        try:
            satirlar = conn.execute("SELECT * FROM tahta_nabiz").fetchall()
            self.assertEqual(len(satirlar), 1)
            self.assertEqual(satirlar[0]["tahta_ad"], "9-A")
            self.assertEqual(satirlar[0]["istemci_surum"], "1.1")
            self.assertEqual(satirlar[0]["yoklama_acik"], 0)
            self.assertEqual(yoklayici._taze_nabizli_tahtalar(conn), {"9-A"})
            conn.execute(
                "UPDATE tahta_nabiz SET son_gorulme = datetime('now', '-10 minutes')")
            conn.commit()
            self.assertEqual(yoklayici._taze_nabizli_tahtalar(conn), set())
        finally:
            conn.close()

    def test_yapilandirma_roster_etag_ve_304(self):
        yanit = asyncio.run(tahta_api.yapilandirma(self._istek(method="GET")))
        govde = json.loads(yanit.body.decode())
        self.assertEqual(govde["sinif"], "9-A")
        conn = db.baglanti()
        try:
            beklenen = admin._roster_payload_olustur(conn, 1)[1].decode()
        finally:
            conn.close()
        self.assertEqual(govde["roster"], beklenen)
        etag = yanit.headers["etag"]
        self.assertTrue(etag)
        y2 = asyncio.run(tahta_api.yapilandirma(
            self._istek(method="GET", basliklar={"If-None-Match": etag})))
        self.assertEqual(y2.status_code, 304)

    def test_yapilandirma_atanmamis_tahta_roster_none(self):
        yanit = asyncio.run(tahta_api.yapilandirma(self._istek(TOKEN_F, method="GET")))
        govde = json.loads(yanit.body.decode())
        self.assertIsNone(govde["roster"])
        self.assertIsNone(govde["sinif"])

    def test_yapilandirma_kazanimlar_duzeye_gore_suzulur(self):
        govde = json.loads(asyncio.run(tahta_api.yapilandirma(
            self._istek(TOKEN_A, method="GET"))).body.decode())
        kz = json.loads(govde["kazanimlar"])
        self.assertEqual(list(kz["kazanimlar"]), ["9"])  # 9-A yalnızca kendi düzeyini alır
        self.assertEqual(kz["haftalar"], {"4": "2026-10-05"})
        govde = json.loads(asyncio.run(tahta_api.yapilandirma(
            self._istek(TOKEN_F, method="GET"))).body.decode())
        self.assertEqual(sorted(json.loads(govde["kazanimlar"])["kazanimlar"]), ["12", "9"])

    def test_yapilandirma_kazanim_dosyasi_yoksa_none(self):
        tahta_api.KAZANIM_DOSYASI.unlink()
        govde = json.loads(asyncio.run(tahta_api.yapilandirma(
            self._istek(TOKEN_A, method="GET"))).body.decode())
        self.assertIsNone(govde["kazanimlar"])

    def test_poll_itilen_kaydi_ezmez_taze_nabiz_ssh_atlanir(self):
        sabit = datetime(2026, 10, 6, 12, 0, tzinfo=zil.ISTANBUL)
        self._it(self._kayit(ders_no=1))
        asyncio.run(tahta_api.nabiz_al(self._istek(govde={})))

        def sahte_ssh():
            return AsyncMock(return_value=SimpleNamespace(basarili=False, stdout=b""))

        def tur(tam):
            ssh = sahte_ssh()
            conn = db.baglanti()
            try:
                with patch.object(zil, "simdi_istanbul", return_value=sabit), \
                        patch.object(ssh_istemci, "tahtanin_kayitlarini_tara", ssh):
                    asyncio.run(yoklayici.bir_tur_calistir(conn, TARIH, tam_tarama=tam))
            finally:
                conn.close()
            return ssh

        ssh = tur(False)
        ipler = {c.args[0] for c in ssh.call_args_list}
        self.assertNotIn("10.0.0.1", ipler)   # 9-A taze nabız → taranmadı
        self.assertIn("10.0.0.2", ipler)      # fenlab → tarandı
        s1 = self._satir(ders_no=1)
        self.assertEqual(s1["durum"], "alindi")
        self.assertEqual(s1["kaynak_tahta"], "9-A")
        for no in (2, 3, 4):
            self.assertNotEqual(self._satir(ders_no=no)["durum"], "tahta_ulasilamaz")

        ssh = tur(True)
        ipler = {c.args[0] for c in ssh.call_args_list}
        self.assertIn("10.0.0.1", ipler)
        self.assertEqual(self._satir(ders_no=1)["durum"], "alindi")



    # --- 2026-10-06: saati yanlış açılan tahta (10-A, CMOS pili) geçmiş
    # günün gerçek kaydını ezemez; gelecek tarih reddedilir.

    def _bugun(self, gun):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return patch("zil.simdi_istanbul",
                     return_value=datetime(2026, 10, gun, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")))

    def test_gecmis_gunun_alindi_satiri_ezilmez(self):
        with self._bugun(6):
            self._it(self._kayit(tarih="2026-10-05", kaydedilme_saati="11:35:00",
                                 durumlar={"1": "yok", "2": "var"}))
            # aynı gün, daha geç saatli, farklı içerik (yanlış saatli tahta)
            yanit = self._it(self._kayit(tarih="2026-10-05", kaydedilme_saati="12:01:00",
                                         durumlar={"1": "var", "2": "yok"}))
        self.assertEqual(yanit.status_code, 200)  # istemci tekrar denemesin
        conn = db.baglanti()
        s = conn.execute("SELECT * FROM yoklama_onbellek WHERE tarih='2026-10-05'").fetchone()
        conn.close()
        self.assertEqual(s["kaydedilme_saati"], "11:35:00")
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ali Veli"])

    def test_gecmis_gun_hic_gorulmemis_kayit_eklenir(self):
        with self._bugun(6):
            self._it(self._kayit(tarih="2026-10-05"))
        conn = db.baglanti()
        s = conn.execute("SELECT durum FROM yoklama_onbellek WHERE tarih='2026-10-05'").fetchone()
        conn.close()
        self.assertEqual(s["durum"], "alindi")

    def test_bugun_yeni_kayit_eskiyi_gunceller(self):
        with self._bugun(6):
            self._it(self._kayit(tarih="2026-10-06", kaydedilme_saati="09:00:00"))
            self._it(self._kayit(tarih="2026-10-06", kaydedilme_saati="09:05:00",
                                 durumlar={"1": "var", "2": "yok"}))
        conn = db.baglanti()
        s = conn.execute("SELECT kaydedilme_saati FROM yoklama_onbellek WHERE tarih='2026-10-06'").fetchone()
        conn.close()
        self.assertEqual(s["kaydedilme_saati"], "09:05:00")

    def test_gelecek_tarih_422(self):
        with self._bugun(6):
            with self.assertRaises(HTTPException) as c:
                self._it(self._kayit(tarih="2026-10-07"))
        self.assertEqual(c.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
