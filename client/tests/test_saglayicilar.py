"""
core/saglayicilar.py'nin sağlayıcı-zinciri mantığı. Ağ yok, gerçek API
anahtarı yok — istemciler mock'lanır.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import saglayicilar as sg  # noqa: E402


@pytest.fixture(autouse=True)
def _soguma_durumunu_temizle():
    """_son_basarisizlik modül seviyesinde paylaşılan bir sözlük — testler
    arasında sızmasın diye her testten önce/sonra temizlenir."""
    sg._son_basarisizlik.clear()
    yield
    sg._son_basarisizlik.clear()


def _sahte_yanit(metin: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=metin))]
    )


class _SahteIstemci:
    def __init__(self, davranis):
        """davranis: metin döndüren ya da Exception fırlatan bir callable."""
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )
        self._davranis = davranis

    def _create(self, model, messages):
        sonuc = self._davranis(model, messages)
        if isinstance(sonuc, Exception):
            raise sonuc
        return _sahte_yanit(sonuc)


class TestZinciriDene:
    def test_ilk_saglayicida_anahtar_yoksa_sonrakine_gecer(self, monkeypatch):
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("groq", "model-a"), ("mistral", "model-b")])

        def _sahte_istemci(saglayici):
            if saglayici == "groq":
                return None  # anahtar yok
            return _SahteIstemci(lambda model, msgs: "mistral cevabı")

        monkeypatch.setattr(sg, "_istemci", _sahte_istemci)
        sonuc = sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                                 evrensel_yedek=False)
        assert sonuc == "mistral cevabı"

    def test_hata_veren_saglayici_atlanip_sonrakine_gecilir(self, monkeypatch):
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("deepseek", "model-a"), ("mistral", "model-b")])

        def _sahte_istemci(saglayici):
            if saglayici == "deepseek":
                return _SahteIstemci(lambda model, msgs: RuntimeError("429 rate limit"))
            return _SahteIstemci(lambda model, msgs: "yedek sağlayıcı cevabı")

        monkeypatch.setattr(sg, "_istemci", _sahte_istemci)
        sonuc = sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                                 evrensel_yedek=False)
        assert sonuc == "yedek sağlayıcı cevabı"

    def test_hicbir_saglayici_calismazsa_hata_yukselir(self, monkeypatch):
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("groq", "model-a"), ("mistral", "model-b")])
        monkeypatch.setattr(sg, "_istemci", lambda saglayici: None)

        with pytest.raises(RuntimeError, match="test_gorev"):
            sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                             evrensel_yedek=False)

    def test_bos_yanit_da_basarisiz_sayilir(self, monkeypatch):
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("groq", "model-a")])
        monkeypatch.setattr(sg, "_istemci",
                            lambda saglayici: _SahteIstemci(lambda m, msgs: "   "))

        with pytest.raises(RuntimeError):
            sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                             evrensel_yedek=False)

    def test_tanimsiz_gorev_hata_verir(self):
        with pytest.raises(RuntimeError, match="Tanımsız görev"):
            sg._zinciri_dene("hic-boyle-bir-gorev-yok",
                             [{"role": "user", "content": "x"}])


class TestMesajBicimi:
    def test_metin_uret_sistem_mesaji_ekler(self, monkeypatch):
        yakalanan = {}

        def _sahte_zinciri_dene(gorev, mesajlar, evrensel_yedek=True):
            yakalanan["gorev"] = gorev
            yakalanan["mesajlar"] = mesajlar
            return "ok"

        monkeypatch.setattr(sg, "_zinciri_dene", _sahte_zinciri_dene)
        sg.metin_uret("belge_ozet", "kullanıcı istemi", sistem="sistem talimatı")

        assert yakalanan["gorev"] == "belge_ozet"
        assert yakalanan["mesajlar"][0] == {"role": "system", "content": "sistem talimatı"}
        assert yakalanan["mesajlar"][1] == {"role": "user", "content": "kullanıcı istemi"}

    def test_gorsel_uret_coklu_icerik_ve_evrensel_yedeksiz(self, monkeypatch):
        yakalanan = {}

        def _sahte_zinciri_dene(gorev, mesajlar, evrensel_yedek=True):
            yakalanan["gorev"] = gorev
            yakalanan["mesajlar"] = mesajlar
            yakalanan["evrensel_yedek"] = evrensel_yedek
            return "ok"

        monkeypatch.setattr(sg, "_zinciri_dene", _sahte_zinciri_dene)
        sg.gorsel_uret("gorsel", "bu görseli anlat", b"\x00\x01", "image/jpeg")

        assert yakalanan["gorev"] == "gorsel"
        assert yakalanan["evrensel_yedek"] is False
        icerik = yakalanan["mesajlar"][0]["content"]
        assert icerik[0] == {"type": "text", "text": "bu görseli anlat"}
        assert icerik[1]["type"] == "image_url"
        assert icerik[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


class TestSoguma:
    def test_kota_hatasi_soguma_kaydi_birakir(self, monkeypatch):
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("deepseek", "model-a"), ("mistral", "model-b")])
        monkeypatch.setattr(sg, "_istemci", lambda s: _SahteIstemci(
            lambda m, msgs: RuntimeError("402 Insufficient Balance")
        ) if s == "deepseek" else _SahteIstemci(lambda m, msgs: "cevap"))

        sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}], evrensel_yedek=False)
        assert sg._sogumada_mi("deepseek")
        assert not sg._sogumada_mi("mistral")

    def test_soguyan_saglayici_istemci_hic_kurulmadan_atlanir(self, monkeypatch):
        sg._son_basarisizlik["deepseek"] = __import__("time").monotonic()
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("deepseek", "model-a"), ("mistral", "model-b")])

        cagrilan = []

        def _sahte_istemci(saglayici):
            cagrilan.append(saglayici)
            return _SahteIstemci(lambda m, msgs: "cevap")

        monkeypatch.setattr(sg, "_istemci", _sahte_istemci)
        sonuc = sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                                 evrensel_yedek=False)

        assert sonuc == "cevap"
        assert "deepseek" not in cagrilan, "soğumadaki sağlayıcı için istemci hiç kurulmamalı"
        assert "mistral" in cagrilan

    def test_alakasiz_hata_soguma_baslatmaz(self, monkeypatch):
        """Bir kerelik ağ hatası/geçersiz istek sağlayıcıyı 4 saatliğine
        devre dışı bırakmamalı — bkz. core/anahtar.kota_hatasi_mi() ile aynı
        dar-eşleşme gerekçesi."""
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev",
                            [("deepseek", "model-a"), ("mistral", "model-b")])
        monkeypatch.setattr(sg, "_istemci", lambda s: _SahteIstemci(
            lambda m, msgs: ConnectionError("connection reset by peer")
        ) if s == "deepseek" else _SahteIstemci(lambda m, msgs: "cevap"))

        sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}], evrensel_yedek=False)
        assert not sg._sogumada_mi("deepseek")

    def test_basarili_cagri_eski_soguma_kaydini_temizler(self, monkeypatch):
        """Süresi zaten dolmuş bir soğuma kaydı (deneme yine de yapılır)
        başarılı çağrıdan sonra sözlükten silinmeli — büyümesin diye."""
        import time
        sg._son_basarisizlik["groq"] = time.monotonic() - sg.SOGUMA_SURESI_SN - 100
        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev", [("groq", "model-a")])
        monkeypatch.setattr(sg, "_istemci",
                            lambda s: _SahteIstemci(lambda m, msgs: "cevap"))

        assert not sg._sogumada_mi("groq")   # süresi dolmuş, denemeye engel değil
        sonuc = sg._zinciri_dene("test_gorev", [{"role": "user", "content": "x"}],
                                 evrensel_yedek=False)
        assert sonuc == "cevap"
        assert "groq" not in sg._son_basarisizlik


class TestGorevZincirleri:
    def test_her_zincir_tanimli_saglayicilara_isaret_eder(self):
        for gorev, zincir in sg.GOREV_ZINCIRLERI.items():
            assert zincir, f"{gorev}: zincir boş olamaz"
            for saglayici, model in zincir:
                assert saglayici in sg.SAGLAYICI_TANIMLARI, \
                    f"{gorev}: bilinmeyen sağlayıcı '{saglayici}'"
                assert model

    def test_gorsel_zinciri_evrensel_yedekte_yok(self):
        assert sg._EVRENSEL_METIN_YEDEK[0] not in dict(sg.GOREV_ZINCIRLERI["gorsel"])
