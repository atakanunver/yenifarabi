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


def _soru_sor(monkeypatch, kaynaklar):
    """kitap_sorusu'nu ağsız çalıştırır; sunucu yanıtı `kaynaklar` ile sahte."""
    _onbellegi_doldur(monkeypatch)
    monkeypatch.setattr(m, "_sunucu_url", lambda: "http://sahte")
    monkeypatch.setattr(m, "_auth_headers", dict)

    class _Yanit:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "ok", "answer": "Cevap.", "sources": kaynaklar, "latency_ms": 1}

    monkeypatch.setattr(m.requests, "post", lambda *a, **k: _Yanit())
    return m.kitap_sorusu(parameters={"soru": "hücre nedir?", "ders": "biyoloji", "sinif": "9"})


def test_kaynakta_tur_yoksa_cikti_degismez(monkeypatch):
    sonuc = _soru_sor(monkeypatch, [
        {"book": "9. Sınıf Biyoloji", "page": 84},
        {"book": "9. Sınıf Biyoloji", "page": 85},
    ])
    assert sonuc.endswith("Kaynak: 9. Sınıf Biyoloji, s. 84, 85")


def test_tablo_kaynagi_tablo_eki_alir(monkeypatch):
    sonuc = _soru_sor(monkeypatch, [
        {"book": "9. Sınıf Biyoloji", "page": 84, "tur": "metin"},
        {"book": "9. Sınıf Biyoloji", "page": 85, "tur": "tablo"},
    ])
    assert sonuc.endswith("Kaynak: 9. Sınıf Biyoloji, s. 84, 85 (tablo)")


def test_ayni_sayfada_metin_ve_tablo_tek_girdi(monkeypatch):
    sonuc = _soru_sor(monkeypatch, [
        {"book": "9. Sınıf Biyoloji", "page": 84, "tur": "metin"},
        {"book": "9. Sınıf Biyoloji", "page": 85, "tur": "tablo"},
        {"book": "9. Sınıf Biyoloji", "page": 84, "tur": "tablo"},
    ])
    assert sonuc.endswith("Kaynak: 9. Sınıf Biyoloji, s. 84 (tablo), 85 (tablo)")
