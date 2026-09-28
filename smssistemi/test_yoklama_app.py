"""Yoklama SMS web route birim testleri — test_dogum_app.py'deki desen."""

import json
import sqlite3

import pytest
from fastapi import Request

import app
import auth
import db
import yoklama_kaynak
import yoklama_mantik

TARIH = "2026-09-23"

_PANO_SEMA = """
CREATE TABLE yoklama_onbellek (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT NOT NULL,
    sinif TEXT NOT NULL,
    ders_no INTEGER NOT NULL,
    durum TEXT NOT NULL,
    yok_isimleri TEXT,
    izinli_isimleri TEXT,
    kaynak_tahta TEXT,
    kaydedilme_saati TEXT,
    UNIQUE(tarih, sinif, ders_no)
);
"""


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_smssistemi.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


@pytest.fixture
def pano(tmp_path, monkeypatch):
    yol = tmp_path / "yoklama_pano.db"
    conn = sqlite3.connect(yol)
    conn.executescript(_PANO_SEMA)
    conn.commit()
    monkeypatch.setattr(yoklama_kaynak, "YOKLAMA_DB_YOLU", yol)

    def ekle(sinif, ders_no, durum="alindi", yok=(), izinli=(), tarih=TARIH):
        conn.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, "
            "yok_isimleri, izinli_isimleri) VALUES (?, ?, ?, ?, ?, ?)",
            (tarih, sinif, ders_no, durum, json.dumps(list(yok)), json.dumps(list(izinli))),
        )
        conn.commit()

    yield ekle
    conn.close()


def _sahte_oturum_request(conn, token=None):
    if token is None:
        token = auth.oturum_olustur(conn)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/yoklama-sms",
        "headers": [(b"cookie", f"{auth.COOKIE_ADI}={token}".encode())],
    }
    return Request(scope)


def _oturumsuz_request():
    return Request({"type": "http", "method": "GET", "path": "/yoklama-sms", "headers": []})


@pytest.mark.anyio
async def test_oturumsuz_istek_girise_yonlendirir(test_db, pano):
    yanit = await app.yoklama_sms(_oturumsuz_request())
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/giris"


@pytest.mark.anyio
async def test_sayfa_ozet_dondurur(test_db, pano):
    ogr = db.kisi_ekle(test_db, "Ayşe Yılmaz", None, 1, "ogrenci")
    db.kisi_ekle(test_db, "Ayşe Yılmaz Annesi", "05551112233", 1, "veli", ogrenci_kisi_id=ogr)
    sinif_ad = db.siniflar_listele(test_db)[0]["ad"]
    for ders in range(1, 9):
        pano(sinif_ad, ders, yok=["Ayşe Yılmaz"])

    yanit = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih=TARIH)
    ozet = yanit.context["ozet"]
    assert yanit.context["hata"] is None
    assert ozet["esik"] == yoklama_mantik.ESIK_VARSAYILAN
    assert ozet["devamsiz_sayisi"] == 1
    assert ozet["veli_sayisi"] == 1


@pytest.mark.anyio
async def test_esik_parametresi_listeyi_degistirir(test_db, pano):
    sinif_ad = db.siniflar_listele(test_db)[0]["ad"]
    db.kisi_ekle(test_db, "Ali Kaya", None, 1, "ogrenci")
    for ders in range(1, 9):
        pano(sinif_ad, ders, yok=["Ali Kaya"] if ders <= 3 else [])

    dusuk = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih=TARIH, esik=3)
    yuksek = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih=TARIH, esik=4)
    assert dusuk.context["ozet"]["devamsiz_sayisi"] == 1
    assert yuksek.context["ozet"]["devamsiz_sayisi"] == 0


@pytest.mark.anyio
async def test_pano_erisilemezse_sayfa_hata_ile_acilir(test_db, tmp_path, monkeypatch):
    """Pano DB'si yoksa sayfa 500 vermez — 'servis çökse de iş durmaz'."""
    monkeypatch.setattr(yoklama_kaynak, "YOKLAMA_DB_YOLU", tmp_path / "olmayan.db")
    yanit = await app.yoklama_sms(_sahte_oturum_request(test_db))
    assert yanit.context["ozet"] is None
    assert "bulunamadı" in yanit.context["hata"]


@pytest.mark.anyio
async def test_sablon_kaydedilir(test_db, pano):
    istek = _sahte_oturum_request(test_db)
    yanit = await app.yoklama_sablon_kaydet(istek, yoklama_sms_sablonu="  Yeni metin {isim}  ")
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/yoklama-sms?mesaj=sablon_kaydedildi"
    assert db.ayar_oku(test_db, yoklama_mantik.AYAR_SABLON) == "Yeni metin {isim}"


@pytest.mark.anyio
async def test_secilen_veli_idleri_gonderime_dogru_mesajla_gecer(test_db, pano, monkeypatch):
    """Sayfa → `/gonder` kesişimi: sayfanın tabloya bastığı id'ler VELİ id'si
    olmalı ve `{isim}`/`{ogrenci_adi}` doğru kişilere çözülmeli. Bu testin
    olmaması hâlinde, şablon yanlışlıkla ÖĞRENCİ id'si basıyor olsa bile
    diğer tüm testler geçerdi.

    `_gonderim_calistir` monkeypatch'lenir — aksi hâlde gerçek modem
    bağlantısı kurulup gerçek SMS gönderilirdi.
    """
    sinif_ad = db.siniflar_listele(test_db)[0]["ad"]
    ogr = db.kisi_ekle(test_db, "Ayşe Yılmaz", None, 1, "ogrenci")
    veli_id = db.kisi_ekle(
        test_db, "Hatice Yılmaz", "05551112233", 1, "veli", ogrenci_kisi_id=ogr
    )
    for ders in range(1, 9):
        pano(sinif_ad, ders, yok=["Ayşe Yılmaz"])

    # 1) Sayfa gerçekten VELİ id'si sunuyor mu?
    sayfa = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih=TARIH)
    kayit = sayfa.context["ozet"]["ogrenciler"][0]
    assert [v["id"] for v in kayit["veliler"]] == [veli_id]
    assert veli_id != ogr, "veli ve öğrenci id'si aynı olamaz — test anlamsızlaşır"

    # 2) O id'lerle /gonder çağrıldığında üretilen mesaj doğru mu?
    yakalanan = {}
    monkeypatch.setattr(
        app,
        "_gonderim_calistir",
        lambda gid, kisiler, bekleme: yakalanan.update(id=gid, kisiler=kisiler),
    )
    yanit = await app.gonder(
        _sahte_oturum_request(test_db),
        secilen_kisi_ids=str(veli_id),
        mesaj=yoklama_mantik.SABLON_VARSAYILAN,
    )

    assert yanit.status_code == 303
    assert yanit.headers["location"].startswith("/durum/")
    isim, telefon, metin = yakalanan["kisiler"][0]
    assert (isim, telefon) == ("Hatice Yılmaz", "05551112233")
    assert metin == "Sayın Hatice Yılmaz, öğrenciniz Ayşe Yılmaz bugün derslere katılmamıştır. Bilginize."


@pytest.mark.anyio
async def test_sablon_checkboxlara_veli_idlerini_basar(test_db, pano):
    """Şablonun kendisi sınanır: tablodaki checkbox'ların `value`'su VELİ id'si
    olmalı. Bir üstteki test mantık katmanını doğrular; burada `v.id` yerine
    yanlışlıkla `o.ogrenci_kisi_id` yazılması yakalanır."""
    import re

    from jinja2 import Environment, FileSystemLoader

    sinif_ad = db.siniflar_listele(test_db)[0]["ad"]
    ogr = db.kisi_ekle(test_db, "Ayşe Yılmaz", None, 1, "ogrenci")
    veli_id = db.kisi_ekle(
        test_db, "Hatice Yılmaz", "05551112233", 1, "veli", ogrenci_kisi_id=ogr
    )
    telefonsuz = db.kisi_ekle(test_db, "Emre Şahin", None, 1, "ogrenci")
    for ders in range(1, 9):
        pano(sinif_ad, ders, yok=["Ayşe Yılmaz", "Emre Şahin"])

    sayfa = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih=TARIH)
    ozet = sayfa.context["ozet"]

    class _URL:
        path = "/yoklama-sms"

    class _Req:
        url = _URL()

    html = Environment(loader=FileSystemLoader("templates")).get_template(
        "yoklama_sms.html"
    ).render(
        request=_Req(), ozet=ozet, hata=None, mesaj=None,
        sablon_varsayilan=yoklama_mantik.SABLON_VARSAYILAN,
        esik_min=1, esik_max=8, bugun=ozet["tarih"],
    )

    secilebilir = re.findall(r'class="veli-secim" value="(\d+)"', html)
    assert secilebilir == [str(veli_id)], "checkbox'lar yalnızca veli id'si taşımalı"
    assert str(ogr) not in secilebilir and str(telefonsuz) not in secilebilir
    # Telefonsuz öğrenci listeden düşmez, etiketiyle görünür.
    assert "Emre Şahin" in html
    assert "Veli telefonu yoktur" in html


@pytest.mark.anyio
async def test_gecmis_tarihte_gonder_butonu_basilmaz(test_db, pano):
    """Mesaj metni 'bugün okula gelmemiştir' diyor — geçmiş tarih listesiyle
    gönderim veliye yanlış günü bildirirdi."""
    from jinja2 import Environment, FileSystemLoader

    sinif_ad = db.siniflar_listele(test_db)[0]["ad"]
    ogr = db.kisi_ekle(test_db, "Ayşe Yılmaz", None, 1, "ogrenci")
    db.kisi_ekle(test_db, "Hatice Yılmaz", "05551112233", 1, "veli", ogrenci_kisi_id=ogr)
    for ders in range(1, 9):
        pano(sinif_ad, ders, yok=["Ayşe Yılmaz"], tarih="2026-09-20")

    sayfa = await app.yoklama_sms(_sahte_oturum_request(test_db), tarih="2026-09-20")
    ozet = sayfa.context["ozet"]
    assert ozet["bugun_mu"] is False
    assert ozet["devamsiz_sayisi"] == 1

    class _URL:
        path = "/yoklama-sms"

    class _Req:
        url = _URL()

    html = Environment(loader=FileSystemLoader("templates")).get_template(
        "yoklama_sms.html"
    ).render(
        request=_Req(), ozet=ozet, hata=None, mesaj=None,
        sablon_varsayilan=yoklama_mantik.SABLON_VARSAYILAN,
        esik_min=1, esik_max=8, bugun="2026-09-23",
    )
    assert 'id="gonder-btn"' not in html
    assert "Geçmiş tarihte gönderim kapalı" in html
