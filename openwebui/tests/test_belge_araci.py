import asyncio
import sys
import types

import farabi_belge_araci as fb
import pytest

IDARE = {"role": "user", "id": "u1"}


class Dosya:
    def __init__(self, fid, ad, yol, sahip="u1"):
        self.id, self.filename, self.path, self.user_id = fid, ad, str(yol), sahip


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    kayit = {}

    async def get_file_by_id(fid):
        return kayit.get(fid)

    mod = types.ModuleType("open_webui.models.files")
    mod.Files = types.SimpleNamespace(get_file_by_id=get_file_by_id)
    monkeypatch.setitem(sys.modules, "open_webui.models.files", mod)

    gonderilen = []

    class Yanit:
        status_code = 200

        def __init__(self, veri):
            self._veri = veri

        def json(self):
            return self._veri

    class Istemci:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, headers, json):
            gonderilen.append(json["ad"])
            return Yanit(
                {
                    "durum": "ok",
                    "ad": json["ad"],
                    "arsiv": "kaydedildi",
                    "rag": "yuklendi",
                    "parca": 5,
                }
            )

    monkeypatch.setattr(fb.httpx, "AsyncClient", Istemci)

    def ekle(fid, ad, icerik, sahip="u1"):
        yol = tmp_path / f"{fid}_{ad}"
        yol.write_bytes(icerik)
        kayit[fid] = Dosya(fid, ad, yol, sahip)
        return {"type": "file", "id": fid}

    return ekle, gonderilen


def _calistir(files, dosya_adi="", user=IDARE):
    return asyncio.run(
        fb.Tools().belgeyi_kalici_kaydet(dosya_adi, __files__=files, __user__=user)
    )


def test_dosya_yoksa_kaydettim_dedirtmez(ortam):
    assert "SÖYLEME" in _calistir([])


def test_ayni_icerikli_iki_kopya_tek_gonderilir(ortam):
    ekle, gonderilen = ortam
    sonuc = _calistir(
        [
            ekle("a", "nöbet.pdf", b"x"),
            ekle("b", "nöbet.pdf", b"x"),
            ekle("c", "sınıf.pdf", b"y"),
        ]
    )
    assert gonderilen == ["nöbet.pdf", "sınıf.pdf"]
    assert "tekrar kaydedilmedi" in sonuc and "5 parça" in sonuc


def test_ad_suzgeci(ortam):
    ekle, gonderilen = ortam
    _calistir(
        [ekle("a", "nöbet.pdf", b"x"), ekle("c", "sınıf.pdf", b"y")], dosya_adi="sınıf"
    )
    assert gonderilen == ["sınıf.pdf"]


def test_baskasinin_dosyasi_gonderilmez(ortam):
    ekle, gonderilen = ortam
    sonuc = _calistir([ekle("a", "x.pdf", b"x", sahip="baskasi")])
    assert gonderilen == [] and "SÖYLEME" in sonuc


@pytest.mark.parametrize(
    "yanit, beklenen",
    [
        (None, "KAYDEDİLMEDİ"),
        ({"durum": "desteklenmiyor", "mesaj": "pdf"}, "KAYDEDİLMEDİ"),
        (
            {
                "durum": "rag_hatasi",
                "ad": "a.pdf",
                "arsiv": "kaydedildi",
                "rag": "hata",
            },
            "EKLENEMEDİ",
        ),
        (
            {
                "durum": "ok",
                "ad": "p.xlsx",
                "arsiv": "zaten_vardi",
                "rag": "zaten_yuklu",
            },
            "zaten vardı",
        ),
    ],
)
def test_satir_metinleri(yanit, beklenen):
    assert beklenen in fb._satir("a.pdf", yanit)


# --- 2026-10-16: belgeyi_oku + resmi_yazi_pdf ---

class _OkuIstemci:
    cevap = {"durum": "ok", "sayfa": 2, "ocr_sayfa": 1, "kisaltildi": False,
             "metin": "--- Sayfa 1 ---\nSayı: 123\nKonu: Toplantı"}
    cagrilar = []

    def __init__(self, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url, headers, json):
        _OkuIstemci.cagrilar.append((url, headers, json["ad"]))

        class Y:
            status_code = 200

            def json(self_):
                return _OkuIstemci.cevap

        return Y()


def test_belgeyi_oku_metin_ve_ocr_uyarisi(ortam, monkeypatch):
    ekle, _ = ortam
    monkeypatch.setattr(fb.httpx, "AsyncClient", _OkuIstemci)
    _OkuIstemci.cagrilar.clear()
    f = ekle("f1", "yazi.pdf", b"%PDF-1")
    cikti = asyncio.run(fb.Tools().belgeyi_oku("", __files__=[f], __user__=IDARE))
    assert "Sayı: 123" in cikti and "1 sayfa OCR" in cikti and "[okunamadı]" in cikti
    assert _OkuIstemci.cagrilar[0][0].endswith("/api/webui/belge-oku")


def test_belgeyi_oku_dosya_yoksa_uydurtmaz(ortam):
    cikti = asyncio.run(fb.Tools().belgeyi_oku("", __files__=[], __user__=IDARE))
    assert "bulunamadı" in cikti and "uydurma" in cikti


def test_belgeyi_oku_baskasinin_dosyasi_okunmaz(ortam, monkeypatch):
    ekle, _ = ortam
    monkeypatch.setattr(fb.httpx, "AsyncClient", _OkuIstemci)
    _OkuIstemci.cagrilar.clear()
    f = ekle("f2", "gizli.pdf", b"%PDF-1", sahip="baska")
    cikti = asyncio.run(fb.Tools().belgeyi_oku("", __files__=[f], __user__=IDARE))
    assert "bulunamadı" in cikti and _OkuIstemci.cagrilar == []


def test_resmi_yazi_bos_metin_ve_pdf_uretimi():
    t = fb.Tools()
    assert "boş olamaz" in asyncio.run(t.resmi_yazi_pdf("", "x", __user__=IDARE))
    pytest.importorskip("fpdf")
    veri = fb.Tools._yazi_pdf("Toplantı Daveti", "Birinci paragraf.\n\nİkinci paragraf ğüşiöç.", "", "", "", "", "Okul Müdürü")
    assert veri[:5] == b"%PDF-"


# --- ogrenci_ozel_durum ---

def _durum_istemci(monkeypatch, veri, kod=200):
    cagrilar = []

    class Y:
        status_code = kod

        def json(self):
            return veri

    class I:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, headers, json):
            cagrilar.append((url, headers, json))
            return Y()

    monkeypatch.setattr(fb.httpx, "AsyncClient", I)
    return cagrilar


ADMIN_U = {"role": "admin", "id": "u1"}


def test_ozel_durum_yalniz_yonetici(monkeypatch):
    c = _durum_istemci(monkeypatch, {})
    assert "yalnızca yönetici" in asyncio.run(fb.Tools().ogrenci_ozel_durum(__user__=IDARE))
    assert c == []


def test_ozel_durum_liste_ve_bos_sonuc(monkeypatch):
    veri = {"durum": "ok", "kaynak": "bilgi.docx", "toplam_kayit": 5, "ogrenciler": [
        {"ad_soyad": "Ayşe Örnek", "sinif": "9-A", "okul_no": "11", "ana_baba": "AYRI", "maddi": "-", "hastalik": "--"}]}
    c = _durum_istemci(monkeypatch, veri)
    t = fb.Tools()
    t.valves.api_key = "WK"
    cikti = asyncio.run(t.ogrenci_ozel_durum("ana_baba", "9-A", __user__=ADMIN_U))
    assert "Ayşe Örnek — 9-A, no 11; ana-baba: AYRI" in cikti and "maddi" not in cikti.split("no 11;")[1]
    assert c[0][0].endswith("/ogrenci-durum/getir") and c[0][1] == {"X-Farabi-WebUI-Key": "WK"} and c[0][2] == {"tur": "ana_baba", "sinif": "9-A"}
    _durum_istemci(monkeypatch, {"durum": "ok", "kaynak": "b.docx", "toplam_kayit": 5, "ogrenciler": []})
    assert "uyan öğrenci yok" in asyncio.run(fb.Tools().ogrenci_ozel_durum(__user__=ADMIN_U))


def test_ozel_durum_servis_yoksa(monkeypatch):
    _durum_istemci(monkeypatch, None, kod=500)
    assert "ulaşılamadı" in asyncio.run(fb.Tools().ogrenci_ozel_durum(__user__=ADMIN_U))
