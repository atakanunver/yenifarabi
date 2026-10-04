"""uzak_model.py testleri — gerçek HTTP, sahte farabi-embed sunucusu (model yok)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
import uzak_model


class _Sahte(BaseHTTPRequestHandler):
    istekler: list = []
    hata_kodu: int | None = None

    def do_POST(self):
        govde = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).istekler.append(
            (self.path, self.headers.get("X-Farabi-Embed-Key"), govde)
        )
        if type(self).hata_kodu:
            self.send_response(type(self).hata_kodu)
            self.end_headers()
            return
        if self.path == "/embed":
            yanit = {
                "vektorler": [[float(len(m)), 1.0, 0.0] for m in govde["metinler"]]
            }
        else:
            yanit = {"skorlar": [0.1 * (i + 1) for i in range(len(govde["ciftler"]))]}
        veri = json.dumps(yanit).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(veri)))
        self.end_headers()
        self.wfile.write(veri)

    def log_message(self, *a):
        pass


@pytest.fixture
def sunucu():
    _Sahte.istekler = []
    _Sahte.hata_kodu = None
    s = HTTPServer(("127.0.0.1", 0), _Sahte)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


class _Yerel:
    def __init__(self):
        self.cagri = 0

    def encode(self, metinler, normalize_embeddings=True, **kw):
        self.cagri += 1
        return np.array([9.0, 9.0, 9.0], dtype=np.float32)


def test_tek_metin_1b_vektor_ve_anahtar(sunucu):
    e, _ = uzak_model.olustur(sunucu, "gizli")
    v = e.encode("abcd", normalize_embeddings=True)
    assert v.shape == (3,) and v.dtype == np.float32 and v[0] == 4.0
    yol, anahtar, govde = _Sahte.istekler[0]
    assert (yol, anahtar) == ("/embed", "gizli")
    assert govde == {"metinler": ["abcd"], "normalize": True}


def test_liste_2b_vektor(sunucu):
    e, _ = uzak_model.olustur(sunucu, "k")
    assert e.encode(["a", "bb"]).shape == (2, 3)


def test_rerank_skorlari(sunucu):
    _, r = uzak_model.olustur(sunucu, "k")
    s = r.predict([("soru", "a"), ("soru", "b")])
    assert s.dtype == np.float32 and list(np.round(s, 2)) == [0.1, 0.2]
    assert _Sahte.istekler[0][2] == {"ciftler": [["soru", "a"], ["soru", "b"]]}


def test_sunucu_kapaliysa_yerele_duser_ve_bekler():
    yerel = _Yerel()
    e, r = uzak_model.olustur(
        "http://127.0.0.1:9", "k", yerel_embed=yerel, zaman_asimi=1
    )
    assert e.encode("x")[0] == 9.0
    assert yerel.cagri == 1
    # bekleme süresinde uzak tekrar denenmez, rerank hemen hata verir
    assert not e.istemci.ulasilabilir()
    with pytest.raises(ConnectionError):
        r.predict([("a", "b")])


def test_http_hatasinda_yerele_duser(sunucu):
    _Sahte.hata_kodu = 500
    yerel = _Yerel()
    e, _ = uzak_model.olustur(sunucu, "k", yerel_embed=yerel)
    assert e.encode("x")[0] == 9.0


def test_yerel_yoksa_hata_yukselir():
    e, _ = uzak_model.olustur("http://127.0.0.1:9", "k", zaman_asimi=1)
    with pytest.raises(Exception):
        e.encode("x")


def test_ayar_oku_ortam_once(monkeypatch, tmp_path):
    (tmp_path / "embed.json").write_text('{"url": "http://dosya:1", "anahtar": "d"}')
    monkeypatch.setattr(uzak_model, "AYAR_DOSYASI", tmp_path / "embed.json")
    monkeypatch.setenv("FARABI_EMBED_URL", "http://ortam:1")
    monkeypatch.setenv("FARABI_EMBED_ANAHTAR", "o")
    assert uzak_model.ayar_oku() == ("http://ortam:1", "o")


def test_ayar_oku_dosyadan(monkeypatch, tmp_path):
    (tmp_path / "embed.json").write_text('{"url": "http://dosya:1", "anahtar": "d"}')
    monkeypatch.setattr(uzak_model, "AYAR_DOSYASI", tmp_path / "embed.json")
    monkeypatch.delenv("FARABI_EMBED_URL", raising=False)
    assert uzak_model.ayar_oku() == ("http://dosya:1", "d")


def test_ayar_yoksa_bos(monkeypatch, tmp_path):
    monkeypatch.setattr(uzak_model, "AYAR_DOSYASI", tmp_path / "yok.json")
    monkeypatch.delenv("FARABI_EMBED_URL", raising=False)
    assert uzak_model.ayar_oku() == ("", "")


def test_toplu_gomme_modeli_uzak(monkeypatch, sunucu):
    monkeypatch.setenv("FARABI_EMBED_URL", sunucu)
    monkeypatch.setenv("FARABI_EMBED_ANAHTAR", "k")
    m = uzak_model.toplu_gomme_modeli("BAAI/bge-m3")
    assert isinstance(m, uzak_model.UzakEmbed)
    assert m.istemci.zaman_asimi == uzak_model.TOPLU_ZAMAN_ASIMI_SN
    assert m.encode(["a", "bb"], normalize_embeddings=True, show_progress_bar=False).shape == (2, 3)


def test_uzak_gomme_batch_size_ile_boler(sunucu):
    e, _ = uzak_model.olustur(sunucu, "k")
    v = e.encode([str(i) for i in range(10)], batch_size=4)
    assert v.shape == (10, 3)
    assert [len(g["metinler"]) for _, _, g in _Sahte.istekler] == [4, 4, 2]
