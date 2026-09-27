"""
actions/ekrandaki_soruyu_oku.py — ağsız test: `ekrani_gonder` başarılıysa
OCR'a hiç gidilmez; başarısızsa/verilmemişse eski OCR yoluna düşülür;
gizlilik filtresi (ctx["gizli"]) tetiklenince hiçbir şey gönderilmez.

`file_processor` monkeypatch'lenir — gerçek sunucuya hiç gidilmez (bkz.
tests/conftest.py, ağsız test ilkesi).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actions.ekrandaki_soruyu_oku as m


class _SahteWin:
    """`player._win` — yalnızca `_screenshot_sig.emit(ctx)` gerekiyor."""
    def __init__(self, ctx_sonuc: dict):
        self._ctx_sonuc = ctx_sonuc

        class _Sinyal:
            def __init__(_self, sonuc):
                _self._sonuc = sonuc

            def emit(_self, ctx):
                ctx.update(_self._sonuc)
                ctx["event"].set()

        self._screenshot_sig = _Sinyal(ctx_sonuc)


class _SahteOyuncu:
    def __init__(self, ctx_sonuc: dict):
        self._win = _SahteWin(ctx_sonuc)
        self.loglar = []

    def write_log(self, metin):
        self.loglar.append(metin)


def test_basarili_dogrudan_gonderim_ocra_dusmez(tmp_path, monkeypatch):
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"sahte-png")
    oyuncu = _SahteOyuncu({"path": str(yol), "gizli": False})

    ocr_cagrildi = []
    monkeypatch.setattr(m, "file_processor", lambda *a, **kw: ocr_cagrildi.append(1) or "OCR METNİ")

    konusulan = []
    gonderim_argumanlari = []

    def _gonder(yol_arg, talimat_arg):
        gonderim_argumanlari.append((yol_arg, talimat_arg))
        return True

    sonuc = m.ekrandaki_soruyu_oku(
        parameters={"talimat": "çöz ve açıkla"}, player=oyuncu,
        speak=konusulan.append, ekrani_gonder=_gonder,
    )

    assert gonderim_argumanlari == [(str(yol), "çöz ve açıkla")]
    assert ocr_cagrildi == []
    assert "gönderildi" in sonuc.lower()
    # Doğrudan gönderim başarılıysa OCR fallback speak'i (EKRAN etiketli) gitmemeli.
    assert not any(s.startswith("[EKRAN]") for s in konusulan)


def test_gonderim_basarisizsa_ocr_yedegine_duser(tmp_path, monkeypatch):
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"sahte-png")
    oyuncu = _SahteOyuncu({"path": str(yol), "gizli": False})

    monkeypatch.setattr(m, "file_processor", lambda *a, **kw: "OCR METNİ")

    konusulan = []
    sonuc = m.ekrandaki_soruyu_oku(
        parameters={}, player=oyuncu, speak=konusulan.append,
        ekrani_gonder=lambda *_a, **_kw: False,
    )

    assert sonuc == "OCR METNİ"
    assert any(s == "[EKRAN] OCR METNİ" for s in konusulan)


def test_ekrani_gonder_verilmezse_ocr_yedegine_duser(tmp_path, monkeypatch):
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"sahte-png")
    oyuncu = _SahteOyuncu({"path": str(yol), "gizli": False})
    monkeypatch.setattr(m, "file_processor", lambda *a, **kw: "OCR METNİ")

    konusulan = []
    sonuc = m.ekrandaki_soruyu_oku(parameters={}, player=oyuncu, speak=konusulan.append)

    assert sonuc == "OCR METNİ"
    assert any(s == "[EKRAN] OCR METNİ" for s in konusulan)


def test_gizlilik_filtresi_hicbir_sey_gondermez(monkeypatch):
    oyuncu = _SahteOyuncu({"path": "", "gizli": True})

    gonderim_cagrildi = []
    ocr_cagrildi = []
    monkeypatch.setattr(m, "file_processor", lambda *a, **kw: ocr_cagrildi.append(1) or "OCR")

    konusulan = []
    sonuc = m.ekrandaki_soruyu_oku(
        parameters={}, player=oyuncu, speak=konusulan.append,
        ekrani_gonder=lambda *a, **kw: gonderim_cagrildi.append(1) or True,
    )

    assert gonderim_cagrildi == []
    assert ocr_cagrildi == []
    assert "gizlilik" in sonuc.lower() or "kişisel veri" in sonuc.lower()
    assert konusulan  # öğretmene/modele bir şey söylendi


def test_zaman_asimi_ctx_hic_ayarlanmazsa_soylenir():
    class _HicSinyalYok:
        def emit(_self, ctx):
            pass  # event hiç set edilmez

    class _Win:
        _screenshot_sig = _HicSinyalYok()

    class _Oyuncu:
        _win = _Win()

        def write_log(self, *_a):
            pass

    konusulan = []
    orijinal_bekleme = m.CTX_BEKLEME_SN
    try:
        m.CTX_BEKLEME_SN = 0.05
        sonuc = m.ekrandaki_soruyu_oku(parameters={}, player=_Oyuncu(), speak=konusulan.append)
    finally:
        m.CTX_BEKLEME_SN = orijinal_bekleme

    assert "zaman aşımı" in sonuc.lower()
    assert konusulan
