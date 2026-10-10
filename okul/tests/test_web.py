"""Uçtan uca: giriş akışları, zorunlu şifre değişimi, CSRF, yetki matrisi (404), sayfaların render'ı."""

import io
import json

import auth
import ice_aktar
import odevler
import openpyxl
import pytest
from ayarlar import AYAR
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, kazanim, sms


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    monkeypatch.setattr(kazanim, "havuz_dersleri", lambda seviye: ["matematik"])
    monkeypatch.setattr(
        kazanim,
        "havuz_sorulari",
        lambda seviye, ders, limit=40: [
            {
                "id": 5,
                "konu": "Kesir",
                "soru": "H?",
                "secenekler": ["a", "b", "c", "d"],
                "dogru_index": 1,
            }
        ],
    )
    monkeypatch.setattr(
        kazanim,
        "havuz_sorulari_getir",
        lambda idler: (
            [
                {
                    "id": 5,
                    "konu": "Kesir",
                    "soru": "H?",
                    "secenekler": ["a", "b", "c", "d"],
                    "dogru_index": 1,
                }
            ]
            if 5 in idler
            else []
        ),
    )
    AYAR.program_yolu.write_text(
        json.dumps(
            {
                "siniflar": {
                    "9-A": {
                        d: {"1": "matematik"}
                        for d in ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    r = c.post(
        "/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def test_guvenlik_basliklari_ve_giris_sayfasi(istemci):
    r = istemci.get("/giris")
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert "Kullanıcı adı" in r.text


def test_girissiz_sayfa_girise_yonlendirir(istemci):
    r = istemci.get("/ogrenci", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/giris"


def test_basarili_giris_role_gore_yonlendirir_ve_cerez_uzun_omurlu(istemci, ornek):
    r = istemci.post(
        "/giris",
        data={"kullanici_adi": "HOCA", "sifre": "hoca-sifre"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    cerez = r.headers["set-cookie"]
    assert (
        "HttpOnly" in cerez
        and "Max-Age=31536000" in cerez
        and "samesite=lax" in cerez.lower()
    )
    assert istemci.get("/", follow_redirects=False).headers["location"] == "/ogretmen"
    # her istekte çerez yenilenir (kayan oturum)
    assert "Max-Age=31536000" in istemci.get("/ogretmen").headers["set-cookie"]


def test_hatali_sifre_ve_deneme_siniri(istemci, ornek):
    for _ in range(5):
        assert (
            istemci.post(
                "/giris", data={"kullanici_adi": "hoca", "sifre": "x"}
            ).status_code
            == 401
        )
    r = istemci.post("/giris", data={"kullanici_adi": "hoca", "sifre": "hoca-sifre"})
    assert r.status_code == 429


def test_veli_sifreyle_giremez(istemci, ornek, conn):
    conn.execute(
        "UPDATE kullanici SET kullanici_adi = 'veli1', sifre_hash = ? WHERE id = ?",
        (auth.sifre_hashle("v"), ornek["veli1"]),
    )
    conn.commit()
    assert (
        istemci.post(
            "/giris", data={"kullanici_adi": "veli1", "sifre": "v"}
        ).status_code
        == 401
    )


def test_zorunlu_sifre_degisimi_ve_csrf(istemci, ornek, conn):
    conn.execute(
        "UPDATE kullanici SET sifre_hash = ?, sifre_degismeli = 1 WHERE id = ?",
        (auth.sifre_hashle("ali123"), ornek["ogr1_k"]),
    )
    conn.commit()
    csrf = giris(istemci, "101", "ali123")
    assert (
        istemci.get("/ogrenci", follow_redirects=False).headers["location"] == "/sifre"
    )
    assert (
        istemci.post(
            "/sifre", data={"yeni": "yenisifre1", "yeni2": "yenisifre1"}
        ).status_code
        == 400
    )  # csrf yok
    r = istemci.post("/sifre", data={"csrf": csrf, "yeni": "ali123", "yeni2": "ali123"})
    assert r.status_code == 422 and "İlk şifrenden farklı" in r.text
    r = istemci.post(
        "/sifre",
        data={"csrf": csrf, "yeni": "yenisifre1", "yeni2": "yenisifre1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert istemci.get("/ogrenci").status_code == 200


def test_veli_sms_girisi(istemci, ornek, monkeypatch):
    giden = []
    monkeypatch.setattr(
        sms, "kod_gonder", lambda tel, metin: giden.append((tel, metin))
    )
    r = istemci.post(
        "/veli-giris", data={"telefon": "0532 111 22 33"}, follow_redirects=False
    )
    assert (
        r.status_code == 303
        and r.headers["location"] == "/veli-kod?telefon=05321112233"
    )
    kod = giden[0][1].split(": ")[1][:6]
    assert (
        istemci.post(
            "/veli-kod",
            data={
                "telefon": "05321112233",
                "kod": "000000" if kod != "000000" else "111111",
            },
        ).status_code
        == 401
    )
    r = istemci.post(
        "/veli-kod", data={"telefon": "05321112233", "kod": kod}, follow_redirects=False
    )
    assert r.status_code == 303
    r = istemci.get("/veli")
    assert r.status_code == 200 and "Ali Veli" in r.text


def test_kayitsiz_veli_numarasi(istemci, ornek, monkeypatch):
    monkeypatch.setattr(
        sms, "kod_gonder", lambda tel, metin: pytest.fail("SMS gönderilmemeli")
    )
    r = istemci.post("/veli-giris", data={"telefon": "05559998877"})
    assert r.status_code == 404 and "kayıtlı bir veli numarası değil" in r.text


def test_sms_servisi_kapaliysa_acik_hata(istemci, ornek, monkeypatch):
    def patla(tel, metin):
        raise sms.SmsHatasi("SMS servisine şu an ulaşılamıyor.")

    monkeypatch.setattr(sms, "kod_gonder", patla)
    r = istemci.post("/veli-giris", data={"telefon": "05321112233"})
    assert r.status_code == 503 and "ulaşılamıyor" in r.text


def _veli_girisi(istemci, monkeypatch):
    giden = []
    monkeypatch.setattr(sms, "kod_gonder", lambda tel, metin: giden.append(metin))
    istemci.post("/veli-giris", data={"telefon": "05321112233"})
    istemci.post(
        "/veli-kod", data={"telefon": "05321112233", "kod": giden[0].split(": ")[1][:6]}
    )


@pytest.mark.parametrize(
    "kadi,sifre,yasak",
    [
        (
            "101",
            "ali-sifre",
            [
                "/yonetici",
                "/veli",
                "/ogretmen",
                "/ogretmen/sinif/9-A",
                "/yonetici/kullanicilar",
            ],
        ),
        (
            "hoca",
            "hoca-sifre",
            [
                "/yonetici",
                "/ogrenci",
                "/veli",
                "/ogretmen/sinif/9-B",
                "/yonetici/aktarim",
            ],
        ),
    ],
)
def test_yetki_matrisi_404(istemci, ornek, kadi, sifre, yasak):
    giris(istemci, kadi, sifre)
    for yol in yasak:
        assert istemci.get(yol).status_code == 404, yol


def test_veli_baska_cocugu_goremez(istemci, ornek, monkeypatch, conn):
    _veli_girisi(istemci, monkeypatch)
    for yol in (
        "/veli",
        "/veli/devamsizlik",
        "/veli/kazanim",
        "/veli/odevler",
        "/veli/program",
    ):
        assert istemci.get(f"{yol}?ogr={ornek['ogr2']}").status_code == 404, yol
        assert istemci.get(f"{yol}?ogr={ornek['ogr1']}").status_code == 200, yol
    assert istemci.get("/ogrenci").status_code == 404
    kayit = conn.execute(
        "SELECT count(*) FROM erisim_log WHERE kullanici_id = ? AND ogrenci_id = ?",
        (ornek["veli1"], ornek["ogr1"]),
    ).fetchone()[0]
    assert kayit >= 5


def test_ogrenci_baska_sinifin_odevini_goremez(istemci, ornek, conn, saat):
    oid = odevler.odev_olustur(
        conn,
        ornek["ogretmen"],
        "9-B",
        "matematik",
        "klasik",
        "B ödevi",
        "",
        "2026-10-20",
        [],
    )
    giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/ogrenci/odev/{oid}").status_code == 404


def test_ogretmen_baskasinin_odevini_goremez(
    istemci, ornek, conn, yeni_kullanici, saat
):
    diger = yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="diger-sifre")
    oid = odevler.odev_olustur(
        conn, ornek["ogretmen"], "9-A", "matematik", "klasik", "A", "", "2026-10-20", []
    )
    giris(istemci, "diger", "diger-sifre")
    assert istemci.get(f"/ogretmen/odev/{oid}").status_code == 404


def test_tum_sayfalar_render_olur_dis_kaynak_yokken(
    istemci, ornek, conn, saat, monkeypatch
):
    def yok(*a, **k):
        raise KaynakHatasi("yok")

    monkeypatch.setattr(kazanim, "form_sonuclari", yok)
    odevler.odev_olustur(
        conn,
        ornek["ogretmen"],
        "9-A",
        "matematik",
        "klasik",
        "Ödev A",
        "",
        "2026-10-20",
        [],
    )
    giris(istemci, "101", "ali-sifre")
    for yol in (
        "/ogrenci",
        "/ogrenci/odevler",
        "/ogrenci/kazanimlar",
        "/ogrenci/program",
        "/duyurular",
        "/kvkk",
    ):
        r = istemci.get(yol)
        assert r.status_code == 200, yol
    assert "şu an alınamıyor" in istemci.get("/ogrenci").text
    istemci.cookies.clear()
    giris(istemci, "hoca", "hoca-sifre")
    for yol in (
        "/ogretmen",
        "/ogretmen/sinif/9-A",
        "/ogretmen/odev/yeni",
        "/ogretmen/odev/yeni?tur=test&havuz_ders=matematik",
        "/ogretmen/program",
        "/ogretmen/duyuru",
        "/ogretmen/odev/1",
    ):
        assert istemci.get(yol).status_code == 200, yol
    istemci.cookies.clear()
    giris(istemci, "mudur", "mudur-sifre")
    for yol in (
        "/yonetici",
        "/yonetici/aktarim",
        "/yonetici/kullanicilar?degismemis=1",
        "/yonetici/gorevler",
        "/yonetici/eslesmeyen",
        "/yonetici/erisim",
        "/yonetici/sablon/ogrenci.xlsx",
    ):
        assert istemci.get(yol).status_code == 200, yol


def test_ogretmen_test_verir_ogrenci_cozer(istemci, ornek, conn):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    r = istemci.post(
        "/ogretmen/odev/yeni",
        data={
            "csrf": csrf,
            "sinif": "9-A",
            "ders": "matematik",
            "tur": "test",
            "baslik": "Kesir testi",
            "teslim": "2030-01-01T10:00",
            "soru_1": "1/2+1/2?",
            "sik_1_0": "1",
            "sik_1_1": "2",
            "sik_1_2": "0",
            "sik_1_3": "1/4",
            "dogru_1": "0",
            "kazanim_1": "Kesir toplama",
            "havuz": "5",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    oid = int(r.headers["location"].rsplit("/", 1)[1])
    sorular = odevler.sorular(conn, oid)
    assert len(sorular) == 2 and sorular[1]["kaynak"] == "havuz:5"
    # yetkisiz sınıfa ödev verilemez
    assert (
        istemci.post(
            "/ogretmen/odev/yeni",
            data={
                "csrf": csrf,
                "sinif": "9-B",
                "ders": "matematik",
                "baslik": "x",
                "teslim": "2030-01-01",
            },
        ).status_code
        == 404
    )

    istemci.cookies.clear()
    csrf = giris(istemci, "101", "ali-sifre")
    assert "Kesir testi" in istemci.get("/ogrenci/odevler").text
    r = istemci.post(
        f"/ogrenci/odev/{oid}/test",
        data={"csrf": csrf, f"s{sorular[0]['id']}": "0", f"s{sorular[1]['id']}": "3"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "50" in istemci.get(f"/ogrenci/odev/{oid}").text
    assert (
        istemci.post(f"/ogrenci/odev/{oid}/test", data={"csrf": csrf}).status_code
        == 400
    )  # tek seferlik
    assert "Kesir toplama" in istemci.get("/ogrenci/kazanimlar").text


def test_yonetici_excel_aktarimi(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    wb = openpyxl.Workbook()
    wb.active.append(ice_aktar.OGRENCI_BASLIK)
    wb.active.append(
        [301, "Zeynep Çelik", "10-A", "Anne Çelik", "05550001122", None, None]
    )
    b = io.BytesIO()
    wb.save(b)
    r = istemci.post(
        "/yonetici/aktarim/ogrenci",
        data={"csrf": csrf},
        files={"dosya": ("o.xlsx", b.getvalue())},
    )
    assert r.status_code == 200 and "1 geçerli satır" in r.text
    taslak = r.text.split('name="taslak" value="')[1].split('"')[0]
    r = istemci.post(
        "/yonetici/aktarim/ogrenci/onay", data={"csrf": csrf, "taslak": taslak}
    )
    assert r.status_code == 200 and "zeynep123" in r.text
    assert (
        conn.execute("SELECT sinif FROM ogrenci WHERE okul_no = 301").fetchone()[0]
        == "10-A"
    )
    assert (
        istemci.post(
            "/yonetici/aktarim/ogrenci/onay", data={"csrf": csrf, "taslak": taslak}
        ).status_code
        == 400
    )


def test_yonetici_sifre_sifirlar(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    r = istemci.post(
        f"/yonetici/kullanici/{ornek['ogr1_k']}/sifirla", data={"csrf": csrf}
    )
    assert r.status_code == 200 and "ali123" in r.text
    assert (
        conn.execute(
            "SELECT sifre_degismeli FROM kullanici WHERE id = ?", (ornek["ogr1_k"],)
        ).fetchone()[0]
        == 1
    )


def test_duyuru_akisi(istemci, ornek):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert (
        istemci.post(
            "/ogretmen/duyuru",
            data={
                "csrf": csrf,
                "hedef_tur": "sinif",
                "hedef": "9-B",
                "baslik": "x",
                "metin": "y",
            },
        ).status_code
        == 404
    )
    r = istemci.post(
        "/ogretmen/duyuru",
        data={
            "csrf": csrf,
            "hedef_tur": "sinif",
            "hedef": "9-A",
            "baslik": "Gezi",
            "metin": "Cuma gezi var",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    istemci.cookies.clear()
    giris(istemci, "101", "ali-sifre")
    assert "Gezi" in istemci.get("/ogrenci").text
    istemci.cookies.clear()
    giris(istemci, "201", "ayse-sifre")
    assert "Gezi" not in istemci.get("/duyurular").text


def test_cikis(istemci, ornek):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert (
        istemci.post("/cikis", data={"csrf": csrf}, follow_redirects=False).status_code
        == 303
    )
    assert (
        istemci.get("/ogretmen", follow_redirects=False).headers["location"] == "/giris"
    )


def test_pwa_dosyalari(istemci):
    assert istemci.get("/manifest.webmanifest").json()["name"] == "ŞMUAL Dijital Okul"
    assert "caches" in istemci.get("/sw.js").text
