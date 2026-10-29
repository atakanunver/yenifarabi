"""Gemini yorum betiği: istemler KİMLİKSİZ, hata toleranslı, idempotent. Gemini çağrısı sahte."""

import json

import denemeler
import pytest
from scripts import deneme_yorum as y

VERI = {
    "toplam_net": 62.75,
    "dersler": {"Türkçe": 30.0, "Matematik-1": 7.0},
    "ders_dyb": {"Türkçe": [31, 4, 5], "Matematik-1": [8, 4, 18]},
    "kazanimlar": [
        {"ders": "Türkçe", "kazanim": "Ses olayları", "d": 0, "y": 1, "b": 0},
        {"ders": "Matematik-1", "kazanim": "Üslü sayılar", "d": 1, "y": 2, "b": 1},
        {"ders": "Türkçe", "kazanim": "Paragraf", "d": 3, "y": 0, "b": 0},
    ],
}


def test_ogrenci_istemi_zayif_kazanimlari_ve_netleri_icerir():
    t = y.ogrenci_istemi(VERI)
    assert "62.75" in t and "Üslü sayılar" in t and "Ses olayları" in t
    assert "Paragraf" not in t  # güçlü kazanım zayıf listede yok


def test_ogrenci_istemi_kazanim_yoksa_belirtir():
    t = y.ogrenci_istemi({**VERI, "kazanimlar": []})
    assert "kazanım ayrıntısı yok" in t.lower()


def test_sinif_ve_okul_istemi_sube_adi_ve_isim_icermez():
    ozet = {
        "katilim": 6, "ortalama_net": 30.5, "ders_ortalamalari": {"Türkçe": 15.0},
        "ortak_eksikler": [{"ders": "Türkçe", "kazanim": "Paragraf", "basari": 20}],
        "subeler": [{"sinif": "11-A", "katilim": 6, "ortalama_net": 30.5}],
        "ogrenciler": [{"ad": "Gizli Ad", "okul_no": 77, "net": 5}],
    }
    for t in (y.sinif_istemi(ozet), y.okul_istemi(ozet)):
        assert "11-A" not in t and "Gizli Ad" not in t and "77" not in t
        assert "30.5" in t and "Paragraf" in t


def _kur(conn, ornek, sayi_ogr=1):
    did = conn.execute("INSERT INTO deneme (ad, yayinda, olusturma) VALUES ('D', 0, 'x')").lastrowid
    conn.execute(
        "INSERT INTO deneme_ogrenci (deneme_id, okul_no, veri) VALUES (?, 101, ?)",
        (did, json.dumps(VERI)),
    )
    conn.commit()
    return did


def test_uret_yalniz_bos_yorumlari_doldurur_ve_kimlik_sizdirmaz(conn, ornek):
    did = _kur(conn, ornek)
    istemler = []

    def sahte(istem):
        istemler.append(istem)
        return {"analiz": "ANALIZ METNI", "tavsiye": "TAVSIYE METNI"}

    s = y.uret(conn, did, sahte)
    assert s["ogrenci"] == 1
    r = conn.execute("SELECT analiz, tavsiye FROM deneme_ogrenci WHERE okul_no = 101").fetchone()
    assert (r["analiz"], r["tavsiye"]) == ("ANALIZ METNI", "TAVSIYE METNI")
    for t in istemler:
        for yasak in ("Ali Veli", "101", "9-A"):
            assert yasak not in t
    # ikinci çalıştırma dolu satıra dokunmaz
    sahte2 = lambda i: pytest.fail("dolu satır için tekrar çağrılmamalı")  # noqa: E731
    assert y.uret(conn, did, sahte2)["ogrenci"] == 0


def test_uret_gemini_hatasinda_satir_bos_kalir_betik_devam_eder(conn, ornek):
    did = _kur(conn, ornek)
    s = y.uret(conn, did, lambda i: None)
    assert s["ogrenci"] == 0 and s["hata"] == 1
    assert conn.execute("SELECT analiz FROM deneme_ogrenci").fetchone()[0] == ""


def test_uret_kuru_cagri_yapmaz_ve_yazmaz(conn, ornek):
    did = _kur(conn, ornek)
    s = y.uret(conn, did, lambda i: pytest.fail("kuru çağrı yapmamalı"), kuru=True)
    assert s["ogrenci"] == 1  # üretilecek sayı
    assert conn.execute("SELECT analiz FROM deneme_ogrenci").fetchone()[0] == ""


def test_yanit_ayristir_json_ve_bozuk():
    assert y.yanit_ayristir('{"analiz": "a", "tavsiye": "b"}') == {"analiz": "a", "tavsiye": "b"}
    assert y.yanit_ayristir("json değil") is None
    assert y.yanit_ayristir('{"analiz": 1}') is None  # değerler metin olmalı
    assert y.yanit_ayristir("[]") is None


def test_anahtarlar_ortam_oncelikli_sonra_dosya_bozuksa_bos(tmp_path):
    f = tmp_path / "k.json"
    f.write_text(json.dumps({"gemini_api_keys": ["a", "", 5, "b"]}), encoding="utf-8")
    assert y.anahtarlar("ENV", f) == ["ENV"]
    assert y.anahtarlar(None, f) == ["a", "b"]
    assert y.anahtarlar(None, tmp_path / "yok.json") == []
    f.write_text("bozuk", encoding="utf-8")
    assert y.anahtarlar(None, f) == []
    f.write_text(json.dumps({"gemini_api_keys": "tek"}), encoding="utf-8")
    assert y.anahtarlar(None, f) == []


def test_ogrenci_istemi_gayret_cesaretlendirmesi_ister():
    t = y.ogrenci_istemi(VERI).lower()
    assert "gayret" in t
