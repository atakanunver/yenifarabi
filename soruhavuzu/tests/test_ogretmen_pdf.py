import fitz
import numpy as np

from soruhavuzu import ogretmen_pdf, vt

SORU = {"ders": "matematik", "sinif": 10, "konu": "K", "soru": "Üçgenin iç açıları toplamı kaçtır?",
        "kisa_cevap": "180", "secenekler": ["90", "180", "270", "360"], "dogru_index": 1, "zorluk": 1, "kaynak": "E"}


def _pdf(sayfalar=("Üçgenin iç açıları toplamı 180 derecedir. " * 10,) * 2):
    d = fitz.open()
    for m in sayfalar:
        d.new_page().insert_text((40, 60), m[:400] if False else m, fontsize=6)
    b = d.tobytes()
    d.close()
    return b


class SahteEleyici:
    def __init__(self):
        self.gorulen = set()

    def kopya_mi(self, ders, sinif, soru):
        k = (ders, sinif, soru)
        if k in self.gorulen:
            return True
        self.gorulen.add(k)
        return False


def _ist(**k):
    return {"id": 7, "sinif": "10-A", "ders": "matematik", "baslik": "Föy", "soru_bas": None, "soru_bit": None, **k}


def _onayla(conn, boyut=100, birimler=None):
    from soruhavuzu import denetci
    return denetci.paket_denetle(conn, boyut, cagir=lambda m: __import__("json").dumps(
        {"status": "SUCCESS", "response": __import__("json").dumps({"kararlar": [
            {"id": s["id"], "gecerli": True, "neden": "ok"} for s in vt.denetlenecekler(conn, 100, birimler)]})}), birimler=birimler)


def test_isle_uretir_eler_denetler(conn):
    n = {"c": 0}
    def ureten(b):
        n["c"] += 1
        return [dict(SORU, soru=f"Soru {n['c']}?"), dict(SORU)]  # ikinci sayfada SORU tekrar → eleyici atar
    r = ogretmen_pdf.isle(conn, _ist(), _pdf(), ureten=ureten, eleyici=SahteEleyici(), denetle=_onayla, ders_saati_kontrol=False)
    assert r["durum"] == "bitti" and r["onayli"] == 3 and r["red"] == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM kaynak_birim WHERE anahtar LIKE 'ogretmen:7:%'")
        assert cur.fetchone()[0] == 2


def test_dondurulmus_ve_taranmis_ve_ders(conn):
    assert ogretmen_pdf.isle(conn, _ist(sinif="12-A"), _pdf(), ders_saati_kontrol=False)["durum"] == "hata"
    assert "ders eşlenemedi" in ogretmen_pdf.isle(conn, _ist(ders="satranç"), _pdf(), ders_saati_kontrol=False)["not"]
    bos = _pdf(("kısa",))
    assert "taranmış" in ogretmen_pdf.isle(conn, _ist(), bos, ders_saati_kontrol=False)["not"]


def test_sayfa_araligi_secilir(conn):
    pdf = _pdf(("Metin bir iki üç. " * 20,) * 5)
    b = ogretmen_pdf.sayfa_birimleri(pdf, _ist(soru_bas=2, soru_bit=3), "matematik", 10)
    assert [x["anahtar"] for x in b] == ["ogretmen:7:2", "ogretmen:7:3"]


def test_sekil_atifli_soru_havuza_girmez(conn):
    r = ogretmen_pdf.isle(conn, _ist(), _pdf(), ureten=lambda b: [], eleyici=SahteEleyici(), denetle=_onayla, ders_saati_kontrol=False)
    assert r["durum"] == "hata"


def test_calistir_okul_kapali_ya_da_anahtarsiz(conn):
    assert ogretmen_pdf.calistir(conn, bekleyenler=lambda: []) == []
    def patla():
        raise OSError("kapalı")
    assert ogretmen_pdf.calistir(conn, bekleyenler=patla) == []


def test_calistir_durumlari_okula_bildirir(conn):
    olaylar = []
    r = ogretmen_pdf.calistir(
        conn, ders_saati_kontrol=False,
        bekleyenler=lambda: [_ist()], pdf_al=lambda i: _pdf(), ureten=lambda b: [dict(SORU)],
        eleyici=SahteEleyici(), denetle=_onayla,
        sonuc_bildir=lambda *a: olaylar.append(a),
    )
    assert [o[1] for o in olaylar] == ["isleniyor", "bitti"] and r[0]["durum"] == "bitti"
