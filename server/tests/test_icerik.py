"""
server/icerik.py'nin saf içerik-çıkarma işlevi. Ağ yok, model yok, PDF yok.

client/tests/test_mufredat.py::TestMetinKaynagi::test_metin_cikar_supheli_sayisini_dondurur'dan
taşındı (2026-08-14, server-taşıma) — `_metin_cikar`/`_METIN_ONBELLEK`/
`METIN_DIZINI` artık burada yaşıyor.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import icerik as ic  # noqa: E402


class TestMetinCikar:
    def test_supheli_sayisini_dondurur(self, tmp_path, monkeypatch):
        ic._METIN_ONBELLEK.clear()
        monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
        (tmp_path / "kitap.json").write_text(json.dumps({
            "sayfalar": {"5": {"metin": "Kesirler konusu", "supheli": 0},
                         "6": {"metin": "a # b ifadesi",   "supheli": 1}}
        }, ensure_ascii=False), encoding="utf-8")
        metin, supheli = ic._metin_cikar(Path("kitap.pdf"), [5, 6])
        assert "Kesirler" in metin and "[s.6]" in metin
        assert supheli == 1
