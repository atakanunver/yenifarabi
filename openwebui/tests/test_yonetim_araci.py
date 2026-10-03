import asyncio
import re

import farabi_yonetim_araci as fy
import pytest

KAYIT = ["9-A", "9-B", "10-A", "fenlab", "tahta-001"]
ADMIN = {"role": "admin", "email": "mudur@farabi.local", "id": "u1"}
KULLANICI = {"role": "user", "email": "ogr@farabi.local", "id": "u2"}


class Yanit:
    def __init__(self, kod=200, veri=None):
        self.status_code, self._veri = kod, veri

    def json(self):
        if isinstance(self._veri, Exception):
            raise self._veri
        return self._veri


class Sahte:
    """httpx.AsyncClient yerine: çağrıları kaydeder, ağ yok."""

    def __init__(self, eylem_yaniti=None, istisna=None, kayit=None):
        self.cagrilar = []
        self.eylem_yaniti = eylem_yaniti
        self.istisna = istisna
        self.kayit = KAYIT if kayit is None else kayit

    def __call__(self, *a, **k):
        self.kurucu = k
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _yap(self, yontem, url, **k):
        self.cagrilar.append((yontem, url, k))
        if self.istisna and (yontem == "POST" or "canli=1" in str(k.get("params"))):
            raise self.istisna
        if url.endswith("/tahtalar"):
            if (k.get("params") or {}).get("canli") == 0:
                return Yanit(200, {"tahtalar": [{"ad": a} for a in self.kayit]})
            return Yanit(200, {"tahtalar": [
                {"ad": "9-A", "ulasilabilir": True, "oturum": True, "yoklama": True, "chrome": False, "karartildi": False},
                {"ad": "9-B", "ulasilabilir": False, "oturum": False, "yoklama": False, "chrome": False, "karartildi": False}]})
        if yontem == "POST":
            return self.eylem_yaniti or Yanit(200, {"sonuclar": [
                {"tahta": "9-A", "basarili": True, "sebep": "tamam"}]})
        if url.endswith("/sistem"):
            return Yanit(200, {"cpu_yuzde": 12, "bellek_yuzde": 40, "disk_yuzde": 55, "cpu_sicaklik_c": 50,
                               "gpu": [{"sicaklik_c": 60, "kullanim_yuzde": 5, "bellek_yuzde": 80}],
                               "servisler": [{"ad": "Ollama", "durum": "aktif"}]})
        if url.endswith("/yoklama"):
            return Yanit(200, {"tarih": "2026-10-03", "satirlar": [{"sinif": "9-A", "ad": "Ali Veli"}]})
        return Yanit(404, {})

    async def get(self, url, **k):
        return await self._yap("GET", url, **k)

    async def post(self, url, **k):
        return await self._yap("POST", url, **k)

    @property
    def postlar(self):
        return [c for c in self.cagrilar if c[0] == "POST"]


class Onay:
    def __init__(self, sonuc=True):
        self.sonuc, self.olaylar = sonuc, []

    async def __call__(self, olay):
        self.olaylar.append(olay)
        return self.sonuc


@pytest.fixture
def sahte(monkeypatch):
    s = Sahte()
    monkeypatch.setattr(fy.httpx, "AsyncClient", s)
    return s


def _arac(anahtar="GIZLI-ANAHTAR-123"):
    t = fy.Tools()
    t.valves.api_key = anahtar
    return t


def _calistir(korutin):
    return asyncio.run(korutin)


def _eylem(sahte, tahtalar, onay=None, kullanici=ADMIN, eylem="chrome_kapat", url="", **kw):
    onay = Onay(True) if onay is None else onay
    cikti = _calistir(_arac().tahta_eylemi(eylem, tahtalar, url, __user__=kullanici,
                                           __event_call__=onay, **kw))
    return cikti, onay


def _reboot(sahte, tahtalar, onay=None, kullanici=ADMIN):
    onay = Onay(True) if onay is None else onay
    cikti = _calistir(_arac().tahtalari_yeniden_baslat(tahtalar, __user__=kullanici, __event_call__=onay))
    return cikti, onay


def test_valves_varsayilanlari():
    v = fy.Tools().valves
    assert v.api_url == "http://127.0.0.1:8010/api/ajan" and v.api_key == "" and v.zaman_asimi_sn == 60.0


def test_cerceve_requirements_yok():
    assert "requirements" not in fy.__doc__ and "title: Farabi Yönetim" in fy.__doc__


@pytest.mark.parametrize("kullanici", [KULLANICI, None, {}, {"role": "teacher"}])
def test_admin_degilse_ret_http_yok(sahte, kullanici):
    t = _arac()
    onay = Onay()
    cikti = [
        _calistir(t.tahta_durumu(__user__=kullanici)),
        _calistir(t.sunucu_durumu(__user__=kullanici)),
        _calistir(t.yoklama_sorgula(__user__=kullanici)),
        _calistir(t.tahta_eylemi("chrome_kapat", ["9-A"], __user__=kullanici, __event_call__=onay)),
        _calistir(t.tahtalari_yeniden_baslat(["9-A"], __user__=kullanici, __event_call__=onay)),
    ]
    assert sahte.cagrilar == [] and onay.olaylar == []
    assert all("yönetici" in c.lower() for c in cikti)


@pytest.mark.parametrize("sonuc", [False, None, {"error": "x"}, "evet", 1, "true"])
def test_onay_true_degilse_istek_yok(sahte, sonuc):
    cikti, onay = _eylem(sahte, ["9a"], Onay(sonuc))
    assert "İptal" in cikti and sahte.postlar == []
    assert len(onay.olaylar) == 1
    cikti, _ = _reboot(sahte, ["9a"], Onay(sonuc))
    assert "İptal" in cikti and sahte.postlar == []


def test_onay_true_tek_post_normallestirilmis(sahte):
    cikti, _ = _eylem(sahte, ["9a", "9 B", "fenLab"])
    assert len(sahte.postlar) == 1
    _, url, k = sahte.postlar[0]
    assert url.endswith("/eylem")
    assert k["json"] == {"eylem": "chrome_kapat", "tahtalar": ["9-A", "9-B", "fenlab"]}
    assert "✓ 9-A" in cikti


def test_reboot_tek_post(sahte):
    _reboot(sahte, ["9/a"])
    assert len(sahte.postlar) == 1
    assert sahte.postlar[0][1].endswith("/yeniden-baslat")
    assert sahte.postlar[0][2]["json"] == {"tahtalar": ["9-A"]}


def test_event_call_yoksa_ret(sahte):
    cikti = _calistir(_arac().tahta_eylemi("chrome_kapat", ["9-A"], __user__=ADMIN))
    assert "onay penceresi yok" in cikti.lower() and sahte.postlar == []
    cikti = _calistir(_arac().tahtalari_yeniden_baslat(["9-A"], __user__=ADMIN))
    assert "onay penceresi yok" in cikti.lower() and sahte.postlar == []


@pytest.mark.parametrize("girdi,beklenen", [
    (["9a"], ["9-A"]), (["9 A"], ["9-A"]), (["9/a"], ["9-A"]), (["9-a"], ["9-A"]),
    (["FenLab"], ["fenlab"]), (["TAHTA 001"], ["tahta-001"]), (["10a", "9a", "9A"], ["9-A", "10-A"]),
])
def test_normallestirme(girdi, beklenen):
    assert fy.tahtalari_coz(girdi, KAYIT) == (beklenen, [])


@pytest.mark.parametrize("hepsi", ["hepsi", "Tümü", "tum", "ALL"])
def test_hepsi_tum_kayit(sahte, hepsi):
    _eylem(sahte, [hepsi])
    assert sahte.postlar[0][2]["json"]["tahtalar"] == KAYIT


def test_bilinmeyen_ad_onay_ve_istek_yok(sahte):
    cikti, onay = _eylem(sahte, ["9a", "9-Z"])
    assert onay.olaylar == [] and sahte.postlar == []
    assert "9-Z" in cikti and "9-A" in cikti and "fenlab" in cikti
    cikti, onay = _reboot(sahte, ["9-Z"])
    assert onay.olaylar == [] and sahte.postlar == []


def test_bos_liste_ret(sahte):
    _, onay = _eylem(sahte, [])
    assert onay.olaylar == [] and sahte.postlar == []


def test_onay_mesaji_tam_liste_ve_eylem(sahte):
    _, onay = _eylem(sahte, ["9-A", "10-A"], eylem="ekran_karart")
    olay = onay.olaylar[0]
    assert olay["type"] == "confirmation"
    assert "9-A, 10-A" in olay["data"]["message"] and "karart" in olay["data"]["message"].lower()
    assert olay["data"]["title"]


def test_web_ac_url_onayda(sahte):
    _, onay = _eylem(sahte, ["9-A"], eylem="web_ac", url="https://example.org/x")
    assert "https://example.org/x" in onay.olaylar[0]["data"]["message"]
    assert sahte.postlar[0][2]["json"]["url"] == "https://example.org/x"


@pytest.mark.parametrize("url", [
    "", "ftp://x", "example.org", "javascript:alert(1)", "https://", "http:///yol",
    "https://a.example/x [https://meb.gov.tr](https://meb.gov.tr)", "https://a.example/x y",
    "https://a.example/x\nEylem: zararsız", "https://a.example/\tx", "https://a.example/x\x00",
    "https://a.example/<b>", "https://a.example/`x`", "https://a.example/a(b)", "https://a.example/[x]",
    "https://a.example/" + "a" * 2000,
    "https://a.example/x\u202e", "https://a.example/x\u200b", "https://a.example/x\u00a0",
    "https://a.example/x\u2028", "https://örnek.com"])
def test_web_ac_gecersiz_url_ret(sahte, url):
    _, onay = _eylem(sahte, ["9-A"], eylem="web_ac", url=url)
    assert onay.olaylar == [] and sahte.postlar == []


def test_punycode_url_kabul(sahte):
    _, onay = _eylem(sahte, ["9-A"], eylem="web_ac", url="https://xn--rnek-zoa.com")
    assert len(sahte.postlar) == 1 and len(onay.olaylar) == 1


def test_normal_url_kod_araliginda(sahte):
    _, onay = _eylem(sahte, ["9-A"], eylem="web_ac", url="https://meb.gov.tr/x?y=1")
    assert "`https://meb.gov.tr/x?y=1`" in onay.olaylar[0]["data"]["message"]
    assert len(sahte.postlar) == 1


def test_mesajda_tahta_listesi_kod_araliginda(sahte):
    _, onay = _eylem(sahte, ["9-A", "10-A"])
    assert "`9-A, 10-A`" in onay.olaylar[0]["data"]["message"]


def test_gecersiz_eylem_ret(sahte):
    _, onay = _eylem(sahte, ["9-A"], eylem="rm_rf")
    assert onay.olaylar == [] and sahte.postlar == []


def test_reboot_uyarilari(sahte):
    _, onay = _reboot(sahte, ["9-A", "9-B"])
    m = onay.olaylar[0]["data"]["message"]
    assert "9-A, 9-B" in m
    assert "Okul saatinde (ders günü ilk dersten son derse kadar) sunucu reddeder." in m
    assert "9-A açılışta giriş ekranında kalır (otomatik giriş yok)." in m
    _, onay = _reboot(sahte, ["9-B"])
    m = onay.olaylar[0]["data"]["message"]
    assert "Okul saatinde" in m and "giriş ekranında" not in m


def test_409_okul_saati(sahte):
    sahte.eylem_yaniti = Yanit(409, {"durum": "ders_saati"})
    cikti, _ = _reboot(sahte, ["9-A"])
    assert "okul saati" in cikti.lower() and "reddedildi" in cikti


@pytest.mark.parametrize("kod", [401, 403, 503])
def test_erisim_kodlari(sahte, kod):
    sahte.eylem_yaniti = Yanit(kod, {"detail": "ham-gövde-sızmasın"})
    cikti, _ = _eylem(sahte, ["9-A"])
    assert "erişilemedi" in cikti and "ham-gövde" not in cikti


def test_400_bilinmeyen_listesi(sahte):
    sahte.eylem_yaniti = Yanit(400, {"detail": {"bilinmeyen": ["x1"], "gecerli": ["9-A"]}})
    cikti, _ = _eylem(sahte, ["9-A"])
    assert "x1" in cikti


def test_sebep_cevirisi_ve_uyari(sahte):
    sahte.eylem_yaniti = Yanit(200, {"sonuclar": [
        {"tahta": "9-A", "basarili": True, "sebep": "tamam", "uyari": "otomatik giriş yok"},
        {"tahta": "9-B", "basarili": False, "sebep": "ulasilamadi"},
        {"tahta": "10-A", "basarili": False, "sebep": "zaman_asimi"},
        {"tahta": "fenlab", "basarili": False, "sebep": "oturum_yok"},
        {"tahta": "tahta-001", "basarili": False, "sebep": "bekleme"}]})
    cikti, _ = _eylem(sahte, ["hepsi"])
    assert "✓ 9-A" in cikti and "otomatik giriş yok" in cikti
    assert "✗ 9-B (ulaşılamadı)" in cikti
    assert "zaman aşımı" in cikti and "oturum" in cikti and "bekleme" in cikti.lower()


def test_ag_istisnasi_kisa_hata_sizinti_yok(sahte):
    sahte.istisna = RuntimeError("baglanti 192.168.5.23 GIZLI-ANAHTAR-123 patladi")
    cikti, _ = _eylem(sahte, ["9-A"])
    assert "192.168" not in cikti and "GIZLI" not in cikti and "patladi" not in cikti
    assert "Sonuç alınamadı" in cikti and "işlem yapılmış olabilir" in cikti and "tahta_durumu" in cikti
    assert "ulaşılamadı" not in cikti
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", cikti)


def test_yeniden_baslat_ag_istisnasi_sonuc_belirsiz(sahte):
    sahte.istisna = RuntimeError("zaman asimi")
    cikti = _calistir(_arac().tahtalari_yeniden_baslat(["9-A"], __user__=ADMIN, __event_call__=Onay(True)))
    assert "Sonuç alınamadı" in cikti and "işlem yapılmış olabilir" in cikti and "tahta_durumu" in cikti
    assert "ulaşılamadı" not in cikti


def test_okuma_ag_istisnasi(sahte):
    sahte.istisna = RuntimeError("192.168.5.23 GIZLI-ANAHTAR-123")
    cikti = _calistir(_arac().tahta_durumu(__user__=ADMIN))
    assert "192.168" not in cikti and "GIZLI" not in cikti


def test_basliklar(sahte):
    _eylem(sahte, ["9-A"])
    for _, _, k in sahte.cagrilar:
        assert k["headers"]["X-Farabi-Ajan-Key"] == "GIZLI-ANAHTAR-123"
        assert k["headers"]["X-Farabi-Kaynak"] == "openwebui:mudur@farabi.local"
    assert sahte.kurucu["timeout"] == 60.0


def test_okuma_metotlari_onay_istemez_ve_ozet(sahte):
    t = _arac()
    d = _calistir(t.tahta_durumu(__user__=ADMIN))
    assert "9-A" in d and "9-B" in d
    assert sahte.cagrilar[0][2]["params"] == {"canli": 1}
    s = _calistir(t.sunucu_durumu(__user__=ADMIN))
    assert "CPU" in s and "Ollama" in s
    y = _calistir(t.yoklama_sorgula(sinif="9-A", __user__=ADMIN))
    assert "Ali Veli" in y
    yoklama = next(c for c in sahte.cagrilar if c[1].endswith("/yoklama"))
    assert yoklama[2]["params"] == {"sinif": "9-A"}
    assert sahte.postlar == []


def test_durum_yayimlayici(sahte):
    olaylar = []

    async def emit(o):
        olaylar.append(o)
    _eylem(sahte, ["9-A"], __event_emitter__=emit)
    assert olaylar[0] == {"type": "status", "data": {"description": olaylar[0]["data"]["description"], "done": False}}
    assert olaylar[-1]["data"]["done"] is True


def test_ow_acik_parametreler_gizli_ve_spec():
    import inspect
    for ad in ("tahta_durumu", "sunucu_durumu", "yoklama_sorgula", "tahta_eylemi", "tahtalari_yeniden_baslat"):
        f = getattr(fy.Tools, ad)
        assert inspect.iscoroutinefunction(f) and f.__doc__
        for p in inspect.signature(f).parameters:
            assert p == "self" or p.startswith("__") or f":param {p}:" in f.__doc__
