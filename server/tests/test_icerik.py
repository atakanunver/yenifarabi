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


class TestKitapBul:
    """9-A, 2026-08-30: ders_icerigi konuya göre matematik_9_2.pdf'i (cilt 2)
    okuyordu ama pdf_sayfa hep matematik_9.pdf'ten (cilt 1) sayfa gösteriyordu
    — aynı ders/sınıf için birden çok kitap varken tercih_dosya olmadan hep
    listedeki İLK kitap seçiliyordu. Bu, o regresyonu kilitler."""

    def _kitaplar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
        (tmp_path / "kitaplar.json").write_text(json.dumps({
            "kitaplar": [
                {"dosya": "matematik_9.pdf", "ders": "matematik", "sinif": "9"},
                {"dosya": "matematik_9_2.pdf", "ders": "matematik", "sinif": "9"},
            ]
        }, ensure_ascii=False), encoding="utf-8")

    def test_tercih_yoksa_ilk_kitap_secilir(self, tmp_path, monkeypatch):
        self._kitaplar(tmp_path, monkeypatch)
        kitap = ic._kitap_bul("matematik", "9")
        assert kitap["dosya"] == "matematik_9.pdf"

    def test_tercih_edilen_cilt_secilir(self, tmp_path, monkeypatch):
        self._kitaplar(tmp_path, monkeypatch)
        kitap = ic._kitap_bul("matematik", "9", tercih_dosya="matematik_9_2.pdf")
        assert kitap["dosya"] == "matematik_9_2.pdf"

    def test_tercih_edilen_dosya_adaylarda_yoksa_ilk_kitaba_duser(self, tmp_path, monkeypatch):
        self._kitaplar(tmp_path, monkeypatch)
        kitap = ic._kitap_bul("matematik", "9", tercih_dosya="olmayan.pdf")
        assert kitap["dosya"] == "matematik_9.pdf"


class TestPdfSayfaMetni:
    """9-A, 2026-08-30: pdf_sayfa çıplak çağrıldığında (ders_icerigi hiç
    çağrılmadan) Farabi sayfa metnini bilmeden içerik uyduruyordu — bu
    endpoint o boşluğu kapatır. Canlı testte bulunan ikinci bir kusuru da
    kilitler: fizik_9.pdf'in dönüştürülmüş metninin %55'i U+FFFD ile kirli
    (yalnızca bu kitapta) — kirli metin modele hiç gönderilmemeli."""

    def _kur(self, tmp_path, monkeypatch, sayfa_metni: dict):
        monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
        (tmp_path / "kitaplar.json").write_text(json.dumps({
            "kitaplar": [{"dosya": "fizik_9.pdf", "ders": "fizik", "sinif": "9",
                          "yol": str(tmp_path / "fizik_9.pdf")}]
        }, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "fizik_9.pdf").write_bytes(b"")  # yalnızca exists() kontrolü için
        ic._METIN_ONBELLEK.clear()
        monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
        (tmp_path / "fizik_9.json").write_text(json.dumps({
            "sayfalar": sayfa_metni
        }, ensure_ascii=False), encoding="utf-8")

    def test_temiz_metin_donuyor(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, {"46": {"metin": "Enerji konusu.", "supheli": 0}})
        yanit = ic.pdf_sayfa_metni_endpoint(sayfa=46, ders="fizik", sinif="9", derslik=None)
        assert yanit.status == "ok"
        assert "Enerji" in yanit.metin

    def test_kirli_metin_bulunamadi_donuyor(self, tmp_path, monkeypatch):
        kirli = "a" * 100 + "�" * 400  # %80 U+FFFD — canlıda ölçülen orana yakın
        self._kur(tmp_path, monkeypatch, {"46": {"metin": kirli, "supheli": 0}})
        yanit = ic.pdf_sayfa_metni_endpoint(sayfa=46, ders="fizik", sinif="9", derslik=None)
        assert yanit.status == "bulunamadi"
        assert yanit.metin is None
