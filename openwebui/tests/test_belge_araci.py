import asyncio
import sys
import types

import farabi_belge_araci as fb
import pytest

IDARE = {"role": "user", "id": "u1"}


class Dosya:
    def __init__(self, fid, ad, yol, sahip="u1"):
        self.id, self.filename, self.path, self.user_id = fid, ad, str(yol), sahip


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    kayit = {}

    async def get_file_by_id(fid):
        return kayit.get(fid)

    mod = types.ModuleType("open_webui.models.files")
    mod.Files = types.SimpleNamespace(get_file_by_id=get_file_by_id)
    monkeypatch.setitem(sys.modules, "open_webui.models.files", mod)

    gonderilen = []

    class Yanit:
        status_code = 200

        def __init__(self, veri):
            self._veri = veri

        def json(self):
            return self._veri

    class Istemci:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, headers, json):
            gonderilen.append(json["ad"])
            return Yanit(
                {
                    "durum": "ok",
                    "ad": json["ad"],
                    "arsiv": "kaydedildi",
                    "rag": "yuklendi",
                    "parca": 5,
                }
            )

    monkeypatch.setattr(fb.httpx, "AsyncClient", Istemci)

    def ekle(fid, ad, icerik, sahip="u1"):
        yol = tmp_path / f"{fid}_{ad}"
        yol.write_bytes(icerik)
        kayit[fid] = Dosya(fid, ad, yol, sahip)
        return {"type": "file", "id": fid}

    return ekle, gonderilen


def _calistir(files, dosya_adi="", user=IDARE):
    return asyncio.run(
        fb.Tools().belgeyi_kalici_kaydet(dosya_adi, __files__=files, __user__=user)
    )


def test_dosya_yoksa_kaydettim_dedirtmez(ortam):
    assert "SÖYLEME" in _calistir([])


def test_ayni_icerikli_iki_kopya_tek_gonderilir(ortam):
    ekle, gonderilen = ortam
    sonuc = _calistir(
        [
            ekle("a", "nöbet.pdf", b"x"),
            ekle("b", "nöbet.pdf", b"x"),
            ekle("c", "sınıf.pdf", b"y"),
        ]
    )
    assert gonderilen == ["nöbet.pdf", "sınıf.pdf"]
    assert "tekrar kaydedilmedi" in sonuc and "5 parça" in sonuc


def test_ad_suzgeci(ortam):
    ekle, gonderilen = ortam
    _calistir(
        [ekle("a", "nöbet.pdf", b"x"), ekle("c", "sınıf.pdf", b"y")], dosya_adi="sınıf"
    )
    assert gonderilen == ["sınıf.pdf"]


def test_baskasinin_dosyasi_gonderilmez(ortam):
    ekle, gonderilen = ortam
    sonuc = _calistir([ekle("a", "x.pdf", b"x", sahip="baskasi")])
    assert gonderilen == [] and "SÖYLEME" in sonuc


@pytest.mark.parametrize(
    "yanit, beklenen",
    [
        (None, "KAYDEDİLMEDİ"),
        ({"durum": "desteklenmiyor", "mesaj": "pdf"}, "KAYDEDİLMEDİ"),
        (
            {
                "durum": "rag_hatasi",
                "ad": "a.pdf",
                "arsiv": "kaydedildi",
                "rag": "hata",
            },
            "EKLENEMEDİ",
        ),
        (
            {
                "durum": "ok",
                "ad": "p.xlsx",
                "arsiv": "zaten_vardi",
                "rag": "zaten_yuklu",
            },
            "zaten vardı",
        ),
    ],
)
def test_satir_metinleri(yanit, beklenen):
    assert beklenen in fb._satir("a.pdf", yanit)
