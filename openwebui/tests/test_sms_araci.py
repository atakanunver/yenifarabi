import farabi_sms_araci as fs


def test_gun_adi_aractan_gelir():
    assert fs._gunlu("2026-10-14 10:00") == "14.10.2026 Çarşamba 10:00"
    assert fs._gunlu("2026-10-17 08:30") == "17.10.2026 Cumartesi 08:30"
    assert fs._gunlu("bozuk") == "bozuk"


# --- toplu hedefler (öğrenci / personel / tüm okul) ---

import asyncio


class _Sahte(fs.Tools):
    def __init__(self, yanit):
        super().__init__()
        self.yanit = yanit
        self.cagrilar = []

    async def _istek(self, yontem, yol, govde=None):
        self.cagrilar.append((yontem, yol, govde))
        return self.yanit


def _taslak_yaniti(sinif="9-A", n=5):
    return 200, {"taslak_id": "ab12", "sinif": sinif, "alici_sayisi": n, "metin": "Merhaba", "gecerlilik_dk": 30}


def test_ogrenci_taslagi_dogru_uca_gider():
    t = _Sahte(_taslak_yaniti("11-B", 21))
    s = asyncio.run(t.ogrenci_sms_taslak("11b", "Yarın tören var."))
    assert t.cagrilar == [("POST", "/ogrenci-taslak", {"sinif": "11b", "metin": "Yarın tören var."})]
    assert "GÖNDERİLMEDİ" in s and "11-B öğrencileri" in s and "21 alıcı" in s and "ÖNEMLİ" not in s


def test_personel_taslagi_sinifsiz_gider():
    t = _Sahte(_taslak_yaniti("Personel", 23))
    s = asyncio.run(t.personel_sms_taslak("Toplantı var."))
    assert t.cagrilar == [("POST", "/personel-taslak", {"metin": "Toplantı var."})]
    assert "personeli" in s and "23 alıcı" in s


def test_tum_okul_taslagi_alici_sayisi_onayini_hatirlatir():
    t = _Sahte(_taslak_yaniti("TÜM OKUL", 190))
    s = asyncio.run(t.veli_sms_taslak("TÜM", "Kermes var."))
    assert "tüm okul velileri" in s and "ÖNEMLİ" in s and "(190)" in s and "alici_sayisi" in s


def test_gonder_alici_sayisini_yalniz_verilince_iletir():
    t = _Sahte((200, {"sinif": "TÜM OKUL", "alici_sayisi": 190, "gonderim_id": "g1"}))
    s = asyncio.run(t.veli_sms_gonder("ab12", 190))
    assert t.cagrilar[-1] == ("POST", "/veli-gonder", {"taslak_id": "ab12", "alici_sayisi": 190})
    assert "tüm okul velilerine" in s and "190 alıcı" in s
    t2 = _Sahte((200, {"sinif": "9-A", "alici_sayisi": 5, "gonderim_id": "g2"}))
    asyncio.run(t2.veli_sms_gonder("ab12"))
    assert t2.cagrilar[-1] == ("POST", "/veli-gonder", {"taslak_id": "ab12"})


def test_hata_ve_ulasilamadi_gonderilmedi_der():
    t = _Sahte((429, {"detail": "Günlük toplu SMS sınırı aşılır"}))
    assert "İşlem YAPILMADI (429)" in asyncio.run(t.ogrenci_sms_gonder("ab12"))
    import httpx

    class Bozuk(fs.Tools):
        async def _istek(self, *a, **k):
            raise httpx.ConnectError("x")

    assert "işlem YAPILMADI" in asyncio.run(Bozuk().personel_sms_gonder("ab12"))
