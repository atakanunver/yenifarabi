"""
tools/sembol_temizle.py'nin sayaç mantığı. Ağ yok — _sayfayi_temizle mock'lanır.

Regresyon testi: eski_supheli, kayit["supheli"] üzerine yazılmadan ÖNCE
yakalanmıyordu, bu yüzden "kaç sayfa düzeltildi" sayacı hep 0 kalıyordu
(veri doğru yazılıyordu, yalnızca rapor yanlıştı — ölçüldü: fizik-10.pdf s.88).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import sembol_temizle as st  # noqa: E402


def test_gercekten_duzelen_sayfa_dogru_sayilir(tmp_path, monkeypatch):
    kitap_json = tmp_path / "test-kitap.json"
    kitap_json.write_text(json.dumps({
        "kitap": "test-kitap.pdf",
        "sayfalar": {
            "5": {"metin": "a # b ifadesi", "supheli": 1},
        },
    }), encoding="utf-8")

    # Model işaretini kesin çözdü varsayımı: temiz metinde artık şüpheli yok
    monkeypatch.setattr(st, "_sayfayi_temizle", lambda ham: "a ≤ b ifadesi")

    sonuc = st.kitabi_temizle(kitap_json, onayla=True)

    assert sonuc["sayfa"] == 1
    assert sonuc["degisen"] == 1, "gerçekten düzelen sayfa 'degisen' sayacına yansımalı"

    guncel = json.loads(kitap_json.read_text(encoding="utf-8"))
    assert guncel["sayfalar"]["5"]["supheli"] == 0
    assert guncel["sayfalar"]["5"]["ai_temizlendi"] is True


def test_emin_olunmayan_sayfa_degismez_ama_metin_yine_de_guncellenebilir(tmp_path, monkeypatch):
    kitap_json = tmp_path / "test-kitap.json"
    kitap_json.write_text(json.dumps({
        "kitap": "test-kitap.pdf",
        "sayfalar": {
            "5": {"metin": "a # b ifadesi", "supheli": 1},
        },
    }), encoding="utf-8")

    # Model metni biraz değiştirdi (ör. ek açıklama) ama şüpheli işareti aynı kaldı
    monkeypatch.setattr(st, "_sayfayi_temizle", lambda ham: "a # b ifadesi (emin değilim)")

    sonuc = st.kitabi_temizle(kitap_json, onayla=True)

    assert sonuc["degisen"] == 0, "şüpheli sayısı azalmadıysa 'degisen' sayılmamalı"
    guncel = json.loads(kitap_json.read_text(encoding="utf-8"))
    assert guncel["sayfalar"]["5"]["supheli"] == 1


def test_ai_cagrisi_basarisiz_olursa_sayfa_degismeden_kalir(tmp_path, monkeypatch):
    kitap_json = tmp_path / "test-kitap.json"
    kitap_json.write_text(json.dumps({
        "kitap": "test-kitap.pdf",
        "sayfalar": {"5": {"metin": "a # b", "supheli": 1}},
    }), encoding="utf-8")

    def _patlar(ham):
        raise RuntimeError("402 Insufficient Balance")

    monkeypatch.setattr(st, "_sayfayi_temizle", _patlar)
    sonuc = st.kitabi_temizle(kitap_json, onayla=True)

    assert sonuc["degisen"] == 0
    guncel = json.loads(kitap_json.read_text(encoding="utf-8"))
    assert guncel["sayfalar"]["5"]["metin"] == "a # b"
    assert "ai_temizlendi" not in guncel["sayfalar"]["5"]
