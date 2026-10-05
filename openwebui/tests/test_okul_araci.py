import asyncio

import farabi_okul_araci as fo
import pytest

IDARE = {"role": "user", "email": "idare@farabi.local", "id": "u1"}
OGRETMEN = {"role": "user", "email": "ogretmen@farabi.local", "id": "u2"}
TAHTA = {"role": "user", "email": "tahta@farabi.local", "id": "u3"}
ADMIN = {"role": "admin", "email": "mudur@x", "id": "u4"}


class Yanit:
    def __init__(self, kod=200, veri=None):
        self.status_code, self._veri = kod, veri

    def json(self):
        return self._veri


class Sahte:
    def __init__(self, yanit=None, istisna=None):
        self.cagrilar, self.yanit, self.istisna = [], yanit, istisna

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        self.cagrilar.append((url, headers, params))
        if self.istisna:
            raise self.istisna
        return self.yanit


def _arac(monkeypatch, yanit=None, istisna=None):
    s = Sahte(yanit, istisna)
    monkeypatch.setattr(fo.httpx, "AsyncClient", s)
    t = fo.Tools()
    t.valves.api_key = "OKUL"
    t.valves.ogrenci_izinli = "idare@farabi.local, ogretmen@farabi.local"
    return t, s


def _c(coro):
    return asyncio.run(coro)


DERS = {
    "sinif": "11-A",
    "gun": "Pazartesi",
    "durum": "ders",
    "simdi": "Şu an (Türkiye saati): 5 Ekim 2026 Pazartesi, saat 08:20 — 1. ders saati.",
    "dersler": [
        {
            "no": 1,
            "baslangic": "08:10",
            "bitis": "08:50",
            "ders": "kimya",
            "simdi": True,
        }
    ],
}


def test_ders_programi_cevabi_ve_basliklar(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, DERS))
    cikti = _c(t.ders_programi("11-A", "simdi", __user__=TAHTA))
    assert (
        "11-A" in cikti and "kimya" in cikti and "08:10" in cikti and "(şu an)" in cikti
    )
    url, basliklar, params = s.cagrilar[0]
    assert url.endswith("/ders-programi") and params == {
        "sinif": "11-A",
        "gun": "simdi",
    }
    assert basliklar["X-Farabi-Okul-Key"] == "OKUL"


def test_ders_yoksa_acik_mesaj(monkeypatch):
    t, _ = _arac(monkeypatch, Yanit(200, {**DERS, "durum": "okul_disi", "dersler": []}))
    assert "ders yok" in _c(t.ders_programi("11-A", "simdi", __user__=OGRETMEN))


def test_hafta(monkeypatch):
    hafta = {"sinif": "11-A", "simdi": "x", "hafta": {"Pazartesi": DERS["dersler"]}}
    t, _ = _arac(monkeypatch, Yanit(200, hafta))
    cikti = _c(t.ders_programi("11-A", "hafta", __user__=OGRETMEN))
    assert "Pazartesi" in cikti and "kimya" in cikti


def test_bilinmeyen_sinif_gecerlileri_soyler(monkeypatch):
    t, _ = _arac(monkeypatch, Yanit(404, {"detail": {"gecerli": ["9-A", "11-A"]}}))
    cikti = _c(t.ders_programi("13-Z", __user__=OGRETMEN))
    assert "bulunamadı" in cikti and "11-A" in cikti


def test_ag_hatasi_istisna_metni_sizdirmaz(monkeypatch):
    t, _ = _arac(monkeypatch, istisna=RuntimeError("192.168.1.1 gizli"))
    cikti = _c(t.ders_programi("11-A", __user__=OGRETMEN))
    assert "ulaşılamadı" in cikti and "192.168" not in cikti


OGR = {
    "ogrenciler": [{"no": "101", "ad_soyad": "Ayşe Yılmaz", "sinif": "11-A"}],
    "toplam": 1,
}


@pytest.mark.parametrize("kullanici", [IDARE, OGRETMEN, ADMIN])
def test_izinli_hesap_ogrenci_gorur(monkeypatch, kullanici):
    t, s = _arac(monkeypatch, Yanit(200, OGR))
    cikti = _c(t.ogrenci_bilgisi(ad="ayşe", __user__=kullanici))
    assert "Ayşe Yılmaz" in cikti and "101" in cikti and "11-A" in cikti
    _, basliklar, params = s.cagrilar[0]
    assert basliklar["X-Farabi-Kullanici"] == kullanici["email"]
    assert basliklar["X-Farabi-Rol"] == kullanici["role"]
    assert params == {"sinif": "", "ad": "ayşe", "no": ""}


def test_tahta_hesabi_reddedilir_istek_atilmaz(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR))
    cikti = _c(t.ogrenci_bilgisi(sinif="11-A", __user__=TAHTA))
    assert cikti == fo.OGRENCI_RET and s.cagrilar == []


def test_kullanicisiz_reddedilir(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR))
    assert _c(t.ogrenci_bilgisi(sinif="11-A")) == fo.OGRENCI_RET and s.cagrilar == []


def test_sunucu_403_de_ret(monkeypatch):
    t, _ = _arac(monkeypatch, Yanit(403, {"detail": "x"}))
    assert _c(t.ogrenci_bilgisi(sinif="11-A", __user__=IDARE)) == fo.OGRENCI_RET


def test_bos_sorgu_istek_atmaz(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR))
    assert (
        "sınıf, ad ya da numara" in _c(t.ogrenci_bilgisi(__user__=IDARE))
        and s.cagrilar == []
    )


def test_sonuc_yoksa_uydurma_uyarisi(monkeypatch):
    t, _ = _arac(monkeypatch, Yanit(200, {"ogrenciler": [], "toplam": 0}))
    cikti = _c(t.ogrenci_bilgisi(ad="kimse", __user__=IDARE))
    assert "bulunamadı" in cikti and "uydurma" in cikti.lower()
