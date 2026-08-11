"""
Müfredat zincirinin saf işlevleri. Ağ yok, model yok, PDF yok.

Buradaki testlerin her biri gerçekten yaşanmış bir hatayı bekçiliyor;
"kapsama için yazılmış" test yok.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.ders_icerigi import (          # noqa: E402
    _ders_eslesir, gorunen_ad, _kelimeler, _norm,
)


class TestDersEslesir:
    def test_kelime_bazli_eslesme(self):
        # "temel matematik" sorgusu "Temel Düzey Matematik" içinde BİTİŞİK
        # geçmiyor; alt dize aramasıyla sessizce bulunamıyordu.
        assert _ders_eslesir("temel matematik", "11. sınıf Temel Düzey Matematik")

    def test_turkce_harf_farki_engel_degil(self):
        assert _ders_eslesir("cografya", "10. SINIF COĞRAFYA")
        assert _ders_eslesir("COĞRAFYA", "cografya dersi")

    def test_bos_sorgu_hepsini_eslestirir(self):
        assert _ders_eslesir(None, "herhangi bir ders")
        assert _ders_eslesir("", "herhangi bir ders")

    def test_alakasiz_ders_eslesmez(self):
        assert not _ders_eslesir("biyoloji", "10. SINIF FİZİK")


class TestGorunenAd:
    @pytest.mark.parametrize("kod,beklenen", [
        ("TDE", "Türk Dili ve Edebiyatı"),
        ("TDE SBL", "Türk Dili ve Edebiyatı"),
        ("COGRAFYA", "Coğrafya"),
        ("MATEMATIK TD", "Temel Düzey Matematik"),
    ])
    def test_sinifa_okunabilir_ad(self, kod, beklenen):
        # Sınıfa "Tede" ya da "Cografya" denmez.
        assert gorunen_ad(kod) == beklenen

    def test_bilinmeyen_kod_baslik_bicimine_gecer(self):
        assert gorunen_ad("ASTRONOMI") == "Astronomi"


class TestNormalizasyon:
    def test_kisa_kelimeler_atilir(self):
        assert _kelimeler("ve bir de KUVVET") == {"kuvvet"}

    def test_noktalama_temizlenir(self):
        # Noktalama boşluğa dönüşür (araya çift boşluk girebilir; karşılaştırma
        # her yerde kelime bazlı yapıldığı için bu sorun değil).
        assert _norm("BÖLGELER, ÜLKELER!").split() == ["bolgeler", "ulkeler"]


class TestMetinKaynagi:
    """
    Kitap içeriği artık YALNIZ çevrilmiş metinden gelir; PDF çalışma anında
    açılmaz ve Gemini'ye sayfa okutulmaz.
    """

    def test_gorsel_yolu_kaldirildi(self):
        import actions.ders_icerigi as di
        assert not hasattr(di, "_gorsel_cikar")
        kaynak = (Path(di.__file__)).read_text(encoding="utf-8")
        assert "pypdfium2" not in kaynak
        assert "base64" not in kaynak

    def test_metin_cikar_supheli_sayisini_dondurur(self, tmp_path, monkeypatch):
        import actions.ders_icerigi as di
        import json as _json
        di._METIN_ONBELLEK.clear()
        monkeypatch.setattr(di, "METIN_DIZINI", tmp_path)
        (tmp_path / "kitap.json").write_text(_json.dumps({
            "sayfalar": {"5": {"metin": "Kesirler konusu", "supheli": 0},
                         "6": {"metin": "a # b ifadesi",   "supheli": 1}}
        }, ensure_ascii=False), encoding="utf-8")
        metin, supheli = di._metin_cikar(Path("kitap.pdf"), [5, 6])
        assert "Kesirler" in metin and "[s.6]" in metin
        assert supheli == 1
