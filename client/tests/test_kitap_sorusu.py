"""
actions/kitap_sorusu — kitap eşleme mantığı ağsız test edilir.

Kritik davranış: `ders` verilmeden eşleme YAPILMAMALI. `_ders_eslesir(None, ...)`
boş sorguda her kitabı kabul ettiği için (ders_icerigi.py'nin kataloglama
kipi için bilinçli tasarımı), bu koruma olmadan sınıf düzeyi tutan İLK kitap
seçilip yanlış dersten kaynaklı bir cevap üretilebilirdi.
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import actions.kitap_sorusu as m               # noqa: E402

_SAHTE_KITAPLAR = [
    {"id": 1, "dosya_adi": "biyoloji-9.pdf",  "sinif": 9,  "ders": "Biyoloji"},
    {"id": 8, "dosya_adi": "fizik-10.pdf",    "sinif": 10, "ders": "Fizik"},
    {"id": 5, "dosya_adi": "biyoloji-10.pdf", "sinif": 10, "ders": "Biyoloji"},
]


def _onbellegi_doldur(monkeypatch):
    monkeypatch.setattr(m, "_KITAP_ONBELLEK", list(_SAHTE_KITAPLAR))


def test_ders_verilmeden_eslesme_yapilmaz(monkeypatch):
    _onbellegi_doldur(monkeypatch)
    assert m._kitap_id_bul(None, "10") is None


def test_ders_ve_sinif_verilince_dogru_kitap_secilir(monkeypatch):
    _onbellegi_doldur(monkeypatch)
    assert m._kitap_id_bul("fizik", "10") == 8
    assert m._kitap_id_bul("biyoloji", "10") == 5
    assert m._kitap_id_bul("biyoloji", "9") == 1


def test_eslesmeyen_ders_none_doner(monkeypatch):
    _onbellegi_doldur(monkeypatch)
    assert m._kitap_id_bul("kimya", "10") is None
