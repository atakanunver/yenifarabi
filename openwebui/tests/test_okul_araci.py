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


OGT = {
    "ogretmenler": [
        {"ad_soyad": "YILMAZ SAFİYE", "dersler": ["İng"], "siniflar": ["9-A", "9-B"]}
    ],
    "toplam": 1,
}


def test_ogretmen_bilgisi(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGT))
    cikti = _c(t.ogretmen_bilgisi(ad="safiye", __user__=IDARE))
    assert "YILMAZ SAFİYE" in cikti and "İng" in cikti and "9-A, 9-B" in cikti
    assert s.cagrilar[0][2] == {"ad": "safiye"}


def test_ogretmen_tahta_reddedilir_istek_atilmaz(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGT))
    assert "erişilemez" in _c(t.ogretmen_bilgisi(__user__=TAHTA))
    assert s.cagrilar == []


def test_ogretmen_yoksa_uydurma_uyarisi(monkeypatch):
    t, _ = _arac(monkeypatch, Yanit(200, {"ogretmenler": [], "toplam": 0}))
    assert "uydurma" in _c(t.ogretmen_bilgisi(ad="x", __user__=IDARE))


# --- 2026-10-16: Atos senaryoları ---------------------------------------------

OGR_IL = {
    "toplam": 1,
    "ogrenciler": [
        {
            "ad_soyad": "Çağla Yıldız", "okul_no": 11, "sinif": "9-A", "dogum_tarihi": "2011-03-04",
            "ogrenci_telefon": "05550000001",
            "veliler": [{"rol": "Anne", "ad_soyad": "Selma Yıldız", "telefon": "05550000002"},
                        {"rol": "Baba", "ad_soyad": "Hasan Yıldız", "telefon": ""}],
        }
    ],
}


def test_iletisim_yalniz_yonetici(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR_IL))
    assert "yalnızca yönetici" in _c(t.ogrenci_iletisim(ad="Çağla", __user__=IDARE))
    assert s.cagrilar == []  # izinsiz hesapta sunucuya hiç gidilmez


def test_iletisim_cikti_ve_sms_anahtari(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR_IL))
    t.valves.sms_api_key = "SMSK"
    cikti = _c(t.ogrenci_iletisim(ad="Çağla", __user__=ADMIN))
    assert "05550000002" in cikti and "Baba Hasan Yıldız: kayıtlı değil" in cikti and "04.03.2011" in cikti
    url, basliklar, params = s.cagrilar[0]
    assert url.endswith("/ogrenci-iletisim") and basliklar == {"X-Sms-Arac-Key": "SMSK"}
    assert params["ad"] == "Çağla"


def test_iletisim_ulasilamadi_istisna_metni_sizmaz(monkeypatch):
    t, _ = _arac(monkeypatch, istisna=RuntimeError("SIR-AYRINTI"))
    assert _c(t.ogrenci_iletisim(ad="x", __user__=ADMIN)) == fo.ULASILAMADI


def test_aile_listesi_icin_ozel_arac_yonlendirmesi():
    assert "ogrenci_ozel_durum" in fo.Tools.ogrenci_iletisim.__doc__


def test_okulda_yoklama_alinmadi_mevcut_sayilmaz(monkeypatch):
    v = {"tarih": "2026-10-16", "simdi": "Şu an: Cuma", "not": "n",
         "siniflar": [{"sinif": "9-A", "toplam": 17, "yoklama": "alinmadi"},
                      {"sinif": "9-B", "toplam": 17, "yoklama": "alindi", "ders_no": 2, "mevcut": 15,
                       "yok": ["Elif Ç."], "izinli": ["Sevgi Ç."]}],
         "dersi_olan_ogretmenler": [{"ad_soyad": "ÇİÇEK AYŞE", "sinif": "9-B"}]}
    t, _ = _arac(monkeypatch, Yanit(200, v))
    c = _c(t.okulda_kimler_var(__user__=IDARE))
    assert "9-A: yoklama alınmadı" in c and "15/17 mevcut" in c and "Elif Ç." in c and "ÇİÇEK AYŞE (9-B)" in c
    assert "tahta" not in c.lower()
    assert fo.OGRENCI_RET == _c(t.okulda_kimler_var(__user__=TAHTA))


def test_ogretmen_simdi_iki_ayse(monkeypatch):
    v = {"simdi": "Şu an: ...", "ogretmenler": [
        {"ad_soyad": "ÇİÇEK AYŞE", "dersler": ["Mat"], "simdi_ders": {"no": 1, "sinif": "11-A"},
         "bugun": [{"no": 1, "baslangic": "08:10", "bitis": "08:50", "sinif": "11-A"}]},
        {"ad_soyad": "KARAKOÇ AYŞE MERVE", "dersler": ["Ing"], "simdi_ders": None, "bugun": []}]}
    t, _ = _arac(monkeypatch, Yanit(200, v))
    c = _c(t.ogretmen_simdi("Ayşe", __user__=IDARE))
    assert "ÇİÇEK AYŞE" in c and "ŞU AN 1. derste 11-A" in c and "KARAKOÇ AYŞE MERVE" in c and "şu an dersi yok" in c


def test_pdf_yalniz_yonetici_ve_filtre_sart(monkeypatch):
    t, s = _arac(monkeypatch, Yanit(200, OGR_IL))
    assert "yalnızca yönetici" in _c(t.ogrenci_listesi_pdf(dogum_yili="2010", __user__=IDARE))
    assert "belirtin" in _c(t.ogrenci_listesi_pdf(__user__=ADMIN))
    assert s.cagrilar == []


def test_pdf_uretimi_turkce_karakter():
    pytest.importorskip("fpdf")
    veri = fo.Tools()._pdf_uret("2010 Doğumlular", OGR_IL["ogrenciler"], True)
    assert veri[:5] == b"%PDF-" and len(veri) > 1000
