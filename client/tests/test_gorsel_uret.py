"""
actions/gorsel_uret — ağsız test: Gemini çağrısı (`_uret`) monkeypatch'lenir,
gerçek API'ye hiç gidilmez. Kapsanan davranış: konu doğrulaması, anahtar-yok
durumu, kota hatasında tek seferlik anahtar devri, kaydetme+gösterme,
`speak`/`show_image` çağrılarının thread-safe callback'ler üzerinden gitmesi.
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import actions.gorsel_uret as m                 # noqa: E402


class _SahteOyuncu:
    def __init__(self):
        self.loglar = []
        self.gosterilen = None

    def write_log(self, metin):
        self.loglar.append(metin)

    def show_image(self, title, path):
        self.gosterilen = (title, path)


class _SahteImage:
    def __init__(self):
        self.thumbnail_cagrildi = None
        self.kaydedildi = None

    def thumbnail(self, boyut):
        self.thumbnail_cagrildi = boyut

    def save(self, yol, format=None):
        self.kaydedildi = (Path(yol), format)
        Path(yol).parent.mkdir(parents=True, exist_ok=True)
        Path(yol).write_bytes(b"sahte-png")


class _SahteYanit:
    """`inline_data.data`/`mime_type` üretir — gerçek Gemini yanıt şekli
    (`_resimi_cikar` 2026-09-04'te `as_image()`'tan buna geçti, bkz.
    gorsel_uret.py'nin kendi docstring notu: `as_image()` PIL Image değil
    `types.Image` pydantic modeli döndürüyordu, `.thumbnail()` yoktu)."""
    def __init__(self, veri: bytes | None, mime_type: str = "image/png"):
        self._veri = veri
        self._mime_type = mime_type

    @property
    def candidates(self):
        if self._veri is None:
            return []
        inline = type("Inline", (), {"data": self._veri, "mime_type": self._mime_type})()
        parca = type("Parca", (), {"inline_data": inline})()
        icerik = type("Icerik", (), {"parts": [parca]})()
        return [type("Aday", (), {"content": icerik})()]


def test_konu_bos_ise_uretime_gidilmez(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_DIR", tmp_path)
    oyuncu = _SahteOyuncu()
    sonuc = m.gorsel_uret(parameters={"konu": "  "}, player=oyuncu)
    assert "belirtilmedi" in sonuc.lower()
    assert oyuncu.gosterilen is None


def test_anahtar_yoksa_nazikce_basarisiz_olur(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_DIR", tmp_path)

    def _patlar():
        raise RuntimeError("anahtar yok")
    monkeypatch.setattr(m.core_anahtar, "simdiki", _patlar)

    konusulan = []
    sonuc = m.gorsel_uret(parameters={"konu": "hücre zarı"}, speak=konusulan.append)
    assert "anahtarı yok" in sonuc.lower() or "anahtar yok" in sonuc.lower()
    assert konusulan  # kullanıcıya bir şey söylendi


def test_basarili_uretim_kaydeder_ve_gosterir(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(m.core_anahtar, "simdiki", lambda: "sahte-anahtar")

    resim = _SahteImage()
    monkeypatch.setattr(m.PILImage, "open", lambda *_a, **_kw: resim)
    monkeypatch.setattr(m, "_uret", lambda anahtar, istem: _SahteYanit(b"sahte-bayt"))

    oyuncu = _SahteOyuncu()
    konusulan = []
    sonuc = m.gorsel_uret(parameters={"konu": "fotosentez"}, player=oyuncu, speak=konusulan.append)

    assert "oluşturuldu" in sonuc.lower()
    assert resim.thumbnail_cagrildi == m.MAKS_BOYUT
    assert resim.kaydedildi is not None
    assert oyuncu.gosterilen is not None
    assert oyuncu.gosterilen[1] == str(resim.kaydedildi[0])
    assert any("hazır" in s.lower() for s in konusulan)


def test_kota_hatasinda_bir_kez_anahtar_devredilir(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_DIR", tmp_path)

    anahtarlar = ["birinci", "ikinci"]
    monkeypatch.setattr(m.core_anahtar, "simdiki", lambda: anahtarlar[0])
    monkeypatch.setattr(m.core_anahtar, "kota_hatasi_mi", lambda e: True)

    def _devret():
        anahtarlar.pop(0)
        return True
    monkeypatch.setattr(m.core_anahtar, "sonrakine_gec", _devret)
    monkeypatch.setattr(m.PILImage, "open", lambda *_a, **_kw: _SahteImage())

    denemeler = []

    def _sahte_uret(anahtar, istem):
        denemeler.append(anahtar)
        if len(denemeler) == 1:
            raise RuntimeError("429 quota")
        return _SahteYanit(b"sahte-bayt")

    monkeypatch.setattr(m, "_uret", _sahte_uret)

    sonuc = m.gorsel_uret(parameters={"konu": "mitoz"})
    assert denemeler == ["birinci", "ikinci"]
    assert "oluşturuldu" in sonuc.lower()


def test_iki_deneme_de_basarisizsa_nazikce_biter(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(m.core_anahtar, "simdiki", lambda: "tek-anahtar")
    monkeypatch.setattr(m.core_anahtar, "kota_hatasi_mi", lambda e: False)

    def _hep_patlar(anahtar, istem):
        raise RuntimeError("500 boom")
    monkeypatch.setattr(m, "_uret", _hep_patlar)

    konusulan = []
    sonuc = m.gorsel_uret(parameters={"konu": "asit baz"}, speak=konusulan.append)
    assert "oluşturulamadı" in sonuc.lower()
    assert konusulan
