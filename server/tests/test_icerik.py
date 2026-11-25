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


_KAZANIM_KITAPLAR = {"kitaplar": [
    {"dosya": "biyoloji-9.pdf", "ders": "biyoloji", "sinif": "9", "yol": "biyoloji-9.pdf"},
    {"dosya": "fizik-9.pdf", "ders": "fizik", "sinif": "9", "yol": "fizik-9.pdf"},
    {"dosya": "biyoloji-10.pdf", "ders": "biyoloji", "sinif": "10", "yol": "biyoloji-10.pdf"},
]}


class TestKazanimSayfaBul:
    """ders_icerigi ön araması: kazanım → kitap sayfa aralığı tablosu
    (ESLEME_DIR/kazanim_sayfa.json + kazanim_sayfa_elle.json)."""

    @staticmethod
    def _kayit(**kw):
        k = {"sinif": "9", "ders": "biyoloji", "hafta": "3", "kazanim_kodu": "BİY.9.1.2",
             "kazanim": "Canlıların ortak özelliklerini açıklar.",
             "plan_konu": "Canlıların Ortak Özellikleri", "plan_tema": "Yaşam",
             "kitap": "biyoloji-9.pdf", "bolum_no": "1.2", "baslik": "CANLILARIN ORTAK ÖZELLİKLERİ",
             "ilk_sayfa": 23, "son_sayfa": 30, "yontem": "kod"}
        k.update(kw)
        return k

    def _kur(self, tmp_path, monkeypatch, otomatik=None, elle=None):
        monkeypatch.setattr(ic, "ESLEME_DIR", tmp_path)
        if otomatik is not None:
            (tmp_path / "kazanim_sayfa.json").write_text(
                json.dumps({"kayitlar": otomatik}, ensure_ascii=False), encoding="utf-8")
        if elle is not None:
            (tmp_path / "kazanim_sayfa_elle.json").write_text(
                json.dumps({"kayitlar": elle}, ensure_ascii=False), encoding="utf-8")

    def test_plan_konusu_tam_eslesir(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()])
        kitap, bolum = ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "9")
        assert kitap["dosya"] == "biyoloji-9.pdf"
        assert bolum == {"no": "1.2", "tur": "Bölüm", "ad": "CANLILARIN ORTAK ÖZELLİKLERİ",
                         "ilk_sayfa": 23, "son_sayfa": 30, "yontem": "metin"}

    def test_kelime_orutusmesiyle_eslesir(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()])
        _, bolum = ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "ortak özellikleri canlılar hücre", "", "biyoloji", "9")
        assert bolum["ilk_sayfa"] == 23

    def test_konu_yoksa_tema_kullanilir(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()])
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "", "Canlıların Ortak Özellikleri", "biyoloji", "9") is not None

    def test_elle_dosya_otomatigi_ezer(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()],
                  elle=[self._kayit(hafta=None, ilk_sayfa=40, son_sayfa=44)])
        _, bolum = ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "9")
        assert (bolum["ilk_sayfa"], bolum["son_sayfa"]) == (40, 44)

    def test_ayni_kodlu_iki_hafta_korunur_ve_elle_ikisini_ezer(self, tmp_path, monkeypatch):
        h3 = self._kayit()
        h5 = self._kayit(hafta="5", plan_konu="Hücre Zarı ve Madde Geçişi",
                         baslik="HÜCRE ZARI", bolum_no="1.1.4", ilk_sayfa=50, son_sayfa=60)
        self._kur(tmp_path, monkeypatch, otomatik=[h3, h5])
        _, b3 = ic._kazanim_sayfa_bul(_KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri",
                                      "", "biyoloji", "9")
        _, b5 = ic._kazanim_sayfa_bul(_KAZANIM_KITAPLAR, "Hücre Zarı ve Madde Geçişi",
                                      "", "biyoloji", "9")
        assert b3["ilk_sayfa"] == 23
        assert (b5["ilk_sayfa"], b5["no"]) == (50, "1.1.4")  # bolum_no string kalır
        self._kur(tmp_path, monkeypatch, otomatik=[h3, h5],
                  elle=[self._kayit(hafta=None, ilk_sayfa=90, son_sayfa=95)])
        _, b = ic._kazanim_sayfa_bul(_KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri",
                                     "", "biyoloji", "9")
        assert b["ilk_sayfa"] == 90
        # elle kayıt hafta içermediği için aynı koddaki iki otomatik kaydı da ezer
        kayitlar = ic._kazanim_sayfa_kayitlari()
        assert [k["ilk_sayfa"] for k in kayitlar] == [90]

    def test_elle_kayit_haftali_ise_yalniz_o_haftayi_ezer(self, tmp_path, monkeypatch):
        h3 = self._kayit()
        h5 = self._kayit(hafta="5", ilk_sayfa=50, son_sayfa=60)
        self._kur(tmp_path, monkeypatch, otomatik=[h3, h5],
                  elle=[self._kayit(hafta="5", ilk_sayfa=90, son_sayfa=95)])
        assert sorted(k["ilk_sayfa"] for k in ic._kazanim_sayfa_kayitlari()) == [23, 90]

    def test_kodsuz_kayit_hafta_ile_ezilir(self, tmp_path, monkeypatch):
        a3 = self._kayit(kazanim_kodu=None)
        a5 = self._kayit(kazanim_kodu=None, hafta="5", ilk_sayfa=50, son_sayfa=60)
        self._kur(tmp_path, monkeypatch, otomatik=[a3, a5],
                  elle=[self._kayit(kazanim_kodu=None, hafta="5", ilk_sayfa=90, son_sayfa=95)])
        assert sorted(k["ilk_sayfa"] for k in ic._kazanim_sayfa_kayitlari()) == [23, 90]

    def test_sinif_ve_ders_suzmesi(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()])
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "10") is None
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "fizik", "9") is None
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", None, None) is not None

    def test_tablo_yoksa_none(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch)
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "9") is None

    def test_bozuk_tablo_sessizce_none(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch)
        (tmp_path / "kazanim_sayfa.json").write_text("{bozuk", encoding="utf-8")
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "9") is None

    def test_esik_altinda_none(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit()])
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "volkanlar depremler magma kabuk", "", "biyoloji", "9") is None

    def test_kitap_bulunamazsa_kayit_atlanir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ic, "DATA_DIR", tmp_path)  # kitaplar/ altında dosya yok
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit(kitap="yok.pdf")])
        assert ic._kazanim_sayfa_bul(
            _KAZANIM_KITAPLAR, "Canlıların Ortak Özellikleri", "", "biyoloji", "9") is None

    def test_endpoint_tablo_yokken_bolum_bula_duser(self, tmp_path, monkeypatch):
        self._kur(tmp_path, monkeypatch)
        monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
        monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
        monkeypatch.setattr(ic, "OZET_DIZINI", tmp_path)
        monkeypatch.setattr(ic, "ONBELLEK", tmp_path)
        monkeypatch.setattr(ic, "SAYFA_ONBELLEK", tmp_path / "onb.json")
        ic._METIN_ONBELLEK.clear()
        (tmp_path / "kitaplar.json").write_text(json.dumps({"kitaplar": [
            {"dosya": "biyoloji-9.pdf", "ders": "biyoloji", "sinif": "9",
             "yol": str(tmp_path / "biyoloji-9.pdf"),
             "bolumler": [{"no": 1, "tur": "Ünite", "ad": "Hücre bölünmesi",
                           "ilk_sayfa": 5, "son_sayfa": 6}]}]}, ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "biyoloji-9.pdf").write_bytes(b"")
        (tmp_path / "biyoloji-9.json").write_text(json.dumps({"sayfalar": {
            "5": {"metin": "Hücre bölünmesi mitoz.", "supheli": 0}}}, ensure_ascii=False),
            encoding="utf-8")
        yanit = ic.ders_icerigi_endpoint(ic.KonuIstek(
            ders="biyoloji", sinif="9", konu="Hücre bölünmesi", sayfa_adedi=1))
        assert yanit.status == "ok" and "mitoz" in yanit.metin

    def test_endpoint_tabloyu_kullanir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
        monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
        monkeypatch.setattr(ic, "OZET_DIZINI", tmp_path)
        monkeypatch.setattr(ic, "ONBELLEK", tmp_path)
        monkeypatch.setattr(ic, "SAYFA_ONBELLEK", tmp_path / "onb.json")
        ic._METIN_ONBELLEK.clear()
        self._kur(tmp_path, monkeypatch, otomatik=[self._kayit(ilk_sayfa=7, son_sayfa=8)])
        (tmp_path / "kitaplar.json").write_text(json.dumps({"kitaplar": [
            {"dosya": "biyoloji-9.pdf", "ders": "biyoloji", "sinif": "9",
             "yol": str(tmp_path / "biyoloji-9.pdf"), "bolumler": []}]}, ensure_ascii=False),
            encoding="utf-8")
        (tmp_path / "biyoloji-9.pdf").write_bytes(b"")
        (tmp_path / "biyoloji-9.json").write_text(json.dumps({"sayfalar": {
            "7": {"metin": "Canlıların ortak özellikleri hücre.", "supheli": 0}}}, ensure_ascii=False),
            encoding="utf-8")
        yanit = ic.ders_icerigi_endpoint(ic.KonuIstek(
            ders="biyoloji", sinif="9", konu="Canlıların Ortak Özellikleri", sayfa_adedi=1))
        assert yanit.status == "ok" and "[s.7]" in yanit.metin
