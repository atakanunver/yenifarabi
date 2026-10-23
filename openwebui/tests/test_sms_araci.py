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

    assert "işlem YAPILMADI" in asyncio.run(Bozuk().veli_sms_gonder("ab12"))


# --- kişiye özel (okul_no ile) ---


def test_kisisel_taslak_okul_no_ile_ve_veli_varsayilan():
    t = _Sahte((200, {"taslak_id": "k1", "oge_sayisi": 2, "alici_sayisi": 3, "bulunamayan": [999],
                      "alicisiz": [], "ornek_metin": "Sayın veli", "gecerlilik_dk": 30}))
    s = asyncio.run(t.kisisel_sms_taslak("101, 102;999", "Sayın veli"))
    assert t.cagrilar == [("POST", "/kisisel-taslak", {"ogeler": [
        {"okul_no": 101, "metin_sablon": "Sayın veli"}, {"okul_no": 102, "metin_sablon": "Sayın veli"},
        {"okul_no": 999, "metin_sablon": "Sayın veli"}], "kime": "veli"})]
    assert "GÖNDERİLMEDİ" in s and "k1" in s and "3 alıcı" in s and "999" in s


def test_kisisel_taslak_gecersiz_no_istek_atmaz():
    t = _Sahte((200, {}))
    assert "okul numaraları" in asyncio.run(t.kisisel_sms_taslak("Ayşe", "m"))
    assert "En az bir" in asyncio.run(t.kisisel_sms_taslak(" ", "m"))
    assert t.cagrilar == []


def test_kisisel_gonder():
    t = _Sahte((200, {"gonderim_id": "g", "oge_sayisi": 1, "alici_sayisi": 2}))
    s = asyncio.run(t.kisisel_sms_gonder("k1"))
    assert t.cagrilar == [("POST", "/kisisel-gonder", {"taslak_id": "k1"})]
    assert "2 alıcı" in s
