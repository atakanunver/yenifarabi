"""Veli izin talebi: iş günü, yetki, CSRF, ek imzası, PDF, bildirimler, 20 gün uyarısı, LAN ucu."""

import json
from datetime import date, datetime

import auth
import dosyalar
import izin
import izin_pdf
import push
import pytest
from ayarlar import AYAR
from fastapi.testclient import TestClient
from kaynaklar import sms, telegram
from tests.test_web_belge_sinav import lan_istemci  # noqa: F401

PDF_VAR = True
try:
    import fpdf  # noqa: F401
except ImportError:
    PDF_VAR = False


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def bildirimler(monkeypatch):
    kayit = {"sms": [], "push": [], "push_sonuc": [], "telegram": []}
    monkeypatch.setattr(sms, "bildirim_gonder", lambda tel, metin: kayit["sms"].append((tel, metin)) or True)
    monkeypatch.setattr(push, "izin_talep_bildir", lambda: kayit["push"].append(1))
    monkeypatch.setattr(push, "izin_sonuc_bildir", lambda vid: kayit["push_sonuc"].append(vid))
    monkeypatch.setattr(telegram, "gonder", lambda metin: kayit["telegram"].append(metin) or 1)
    return kayit


@pytest.fixture(autouse=True)
def takvim(saat):
    AYAR.takvim_yolu.write_text(
        json.dumps({"tatiller": [{"ad": "Ara tatil", "baslangic": "2026-11-16", "bitis": "2026-11-20"}]}),
        encoding="utf-8",
    )
    saat["an"] = datetime(2026, 11, 23, 10, 0, 0)  # noqa: DTZ001 — pazartesi (zaman.simdi naif)
    return saat


def _oturum(c, conn, kid):
    c.cookies.clear()
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c, yol):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


def _talep(c, ogr, baslangic="2026-11-23", bitis="2026-11-24", neden_tur="saglik", neden_metin="", ek=None, csrf=None):
    veri = {
        "csrf": csrf if csrf is not None else _csrf(c, f"/veli/izin?ogr={ogr}"),
        "ogr": str(ogr), "baslangic": baslangic, "bitis": bitis, "neden_tur": neden_tur, "neden_metin": neden_metin,
    }
    files = {"ek": ek} if ek else None
    return c.post("/veli/izin", data=veri, files=files, follow_redirects=False)


def test_is_gunu_hafta_sonu_ve_tatil():
    assert izin.is_gunu(date(2026, 11, 23), date(2026, 11, 29)) == 5  # pzt-pzr
    assert izin.is_gunu(date(2026, 11, 13), date(2026, 11, 23)) == 2  # cuma + ara tatil + pazartesi
    assert izin.is_gunu(date(2026, 11, 28), date(2026, 11, 29)) == 0


def test_talep_olusur_ve_bildirimler_gider(istemci, conn, ornek, bildirimler, monkeypatch):
    monkeypatch.setattr(AYAR, "izin_sms_telefon", "05550000000")
    _oturum(istemci, conn, ornek["veli1"])
    r = _talep(istemci, ornek["ogr1"], bitis="2026-11-29", neden_tur="diger", neden_metin="Düğün")
    assert r.status_code == 303
    t = conn.execute("SELECT * FROM izin_talep").fetchone()
    assert t["gun"] == 5 and t["durum"] == "bekliyor" and t["neden_metin"] == "Düğün"
    assert bildirimler["sms"] and bildirimler["sms"][0][0] == "05550000000"
    assert "Veli Bey" in bildirimler["sms"][0][1] and "Ali Veli" in bildirimler["sms"][0][1]
    assert bildirimler["push"] == [1]
    assert len(bildirimler["telegram"]) == 1
    tg = bildirimler["telegram"][0]
    assert "9-A" in tg and "Ali" not in tg and "Veli Bey" not in tg and "Düğün" not in tg
    assert "Bekliyor" in istemci.get(f"/veli/izin?ogr={ornek['ogr1']}").text


def test_sms_telefonu_bossa_sms_atlanir(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    assert _talep(istemci, ornek["ogr1"]).status_code == 303
    assert bildirimler["sms"] == [] and bildirimler["push"] == [1]


def test_dogrulamalar(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    o = ornek["ogr1"]
    assert _talep(istemci, o, baslangic="2026-11-25", bitis="2026-11-24").status_code == 422
    assert _talep(istemci, o, baslangic="2026-11-28", bitis="2026-11-29").status_code == 422  # yalnız hafta sonu
    assert _talep(istemci, o, baslangic="2026-11-23", bitis="2026-12-31").status_code == 422  # > 30 gün
    assert _talep(istemci, o, neden_tur="diger", neden_metin="").status_code == 422
    assert _talep(istemci, o, neden_tur="saglik", neden_metin="x" * 301).status_code == 422
    assert _talep(istemci, o, neden_tur="uydurma").status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0


def test_saatte_uc_talep(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    for _ in range(3):
        assert _talep(istemci, ornek["ogr1"]).status_code == 303
    assert _talep(istemci, ornek["ogr1"]).status_code == 429


def test_baska_velinin_cocugu_404(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    csrf = _csrf(istemci, f"/veli/izin?ogr={ornek['ogr1']}")
    assert istemci.get(f"/veli/izin?ogr={ornek['ogr2']}").status_code == 404
    assert _talep(istemci, ornek["ogr2"], csrf=csrf).status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0


def test_csrf_eksik_reddedilir(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    assert _talep(istemci, ornek["ogr1"], csrf="").status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0


@pytest.mark.parametrize("anahtar", ["ogretmen", "ogr1_k", "veli1"])
def test_yonetici_sayfasi_diger_rollere_404(istemci, conn, ornek, anahtar):
    _oturum(istemci, conn, ornek[anahtar])
    assert istemci.get("/yonetici/izinler").status_code == 404
    assert istemci.post("/yonetici/izinler/1/karar", data={"karar": "onayla"}).status_code == 404


def test_ek_imza_reddi(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["veli1"])
    r = _talep(istemci, ornek["ogr1"], ek=("rapor.pdf", b"bu bir metin dosyasidir", "application/pdf"))
    assert r.status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0


def _yeni_talep(istemci, conn, ornek, ek=None, **kw):
    _oturum(istemci, conn, ornek["veli1"])
    assert _talep(istemci, ornek["ogr1"], ek=ek, **kw).status_code == 303
    return conn.execute("SELECT * FROM izin_talep ORDER BY id DESC").fetchone()


def test_ek_ve_pdf_yalniz_sahibi_ve_yonetici(istemci, conn, ornek, bildirimler, yeni_kullanici):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    t = _yeni_talep(istemci, conn, ornek, ek=("rapor.png", png, "image/png"))
    assert t["ek_tur"] == "png"
    r = istemci.get(f"/veli/izin/{t['id']}/ek")
    assert r.status_code == 200 and r.content == png
    veli2 = yeni_kullanici(conn, "veli", "Başka Veli", telefon="05329998877")
    conn.execute("INSERT INTO veli_ogrenci (veli_id, ogrenci_id) VALUES (?, ?)", (veli2, ornek["ogr2"]))
    conn.commit()
    _oturum(istemci, conn, veli2)
    assert istemci.get(f"/veli/izin/{t['id']}/ek").status_code == 404
    assert istemci.get(f"/veli/izin/{t['id']}/pdf").status_code == 404
    _oturum(istemci, conn, ornek["ogretmen"])
    assert istemci.get(f"/yonetici/izinler/{t['id']}/ek").status_code == 404
    _oturum(istemci, conn, ornek["yonetici"])
    assert istemci.get(f"/yonetici/izinler/{t['id']}/ek").status_code == 200


@pytest.mark.skipif(not PDF_VAR, reason="fpdf2 kurulu değil")
def test_pdf_turkce_uretilir(istemci, conn, ornek, bildirimler):
    conn.execute("UPDATE ogrenci SET ad_soyad = 'Çağrı Şükrü Öğüt İnce' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    t = _yeni_talep(istemci, conn, ornek, neden_tur="resmi", neden_metin="Nüfus müdürlüğü işlemi")
    assert t["pdf_depo"]
    r = istemci.get(f"/veli/izin/{t['id']}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    _oturum(istemci, conn, ornek["yonetici"])
    assert istemci.get(f"/yonetici/izinler/{t['id']}/pdf").content.startswith(b"%PDF-")


@pytest.mark.skipif(not PDF_VAR, reason="fpdf2 kurulu değil")
def test_pdf_uretici_dogrudan():
    veri = izin_pdf.uret({
        "okul_adi": "Şehit Ğİ Lisesi", "sinif": "9-A", "okul_no": 101, "ogrenci": "Ilgın Şıkşık",
        "baslangic": "23.11.2026", "bitis": "24.11.2026", "gun": 2, "mazeret": "sağlık durumu",
        "fiil": "edemeyecektir", "tarih": "23.11.2026", "veli": "Gülşen Öztürk", "telefon": "", "ek_var": True,
    })
    assert veri.startswith(b"%PDF-")
    assert "edemeyecektir" in izin_pdf.dilekce_metni({
        "sinif": "9-A", "okul_no": 1, "ogrenci": "A", "baslangic": "x", "bitis": "y", "gun": 1, "mazeret": "m",
        "fiil": "edemeyecektir",
    })


def test_pdf_yoksa_talep_yine_olusur(istemci, conn, ornek, bildirimler, monkeypatch):
    monkeypatch.setattr(izin_pdf, "uret", lambda a: None)
    t = _yeni_talep(istemci, conn, ornek)
    assert t["pdf_depo"] is None
    assert istemci.get(f"/veli/izin/{t['id']}/pdf").status_code == 404


def test_onay_veliye_sms_ve_push(istemci, conn, ornek, bildirimler):
    t = _yeni_talep(istemci, conn, ornek)
    _oturum(istemci, conn, ornek["yonetici"])
    sayfa = istemci.get("/yonetici")
    assert "Veli izin talepleri" in sayfa.text and "1 bekleyen" in sayfa.text
    yol = f"/yonetici/izinler/{t['id']}"
    assert istemci.post(yol + "/karar", data={"karar": "onayla"}).status_code == 400  # CSRF yok
    r = istemci.post(yol + "/karar", data={"csrf": _csrf(istemci, yol), "karar": "onayla"}, follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT durum FROM izin_talep WHERE id = ?", (t["id"],)).fetchone()[0] == "onaylandi"
    tel, metin = bildirimler["sms"][-1]
    assert tel == "05321112233" and "onaylanmıştır" in metin and "Ali Veli" in metin
    assert bildirimler["push_sonuc"] == [ornek["veli1"]]
    # ikinci karar yok sayılır (ikinci SMS gitmez)
    n = len(bildirimler["sms"])
    istemci.post(yol + "/karar", data={"csrf": _csrf(istemci, yol), "karar": "reddet"})
    assert len(bildirimler["sms"]) == n
    assert conn.execute("SELECT durum FROM izin_talep WHERE id = ?", (t["id"],)).fetchone()[0] == "onaylandi"


def test_ret_yalniz_push(istemci, conn, ornek, bildirimler):
    t = _yeni_talep(istemci, conn, ornek)
    _oturum(istemci, conn, ornek["yonetici"])
    yol = f"/yonetici/izinler/{t['id']}"
    istemci.post(yol + "/karar", data={"csrf": _csrf(istemci, yol), "karar": "reddet"})
    assert bildirimler["sms"] == [] and bildirimler["push_sonuc"] == [ornek["veli1"]]


def _onayli_ekle(conn, ornek, bas, bit, gun):
    conn.execute(
        "INSERT INTO izin_talep (veli_id, ogrenci_id, baslangic, bitis, gun, neden_tur, durum, olusturma)"
        " VALUES (?, ?, ?, ?, ?, 'saglik', 'onaylandi', '2026-11-01 10:00:00')",
        (ornek["veli1"], ornek["ogr1"], bas, bit, gun),
    )
    conn.commit()


def test_yirmi_gun_asim_uyarisi(istemci, conn, ornek, bildirimler):
    _onayli_ekle(conn, ornek, "2026-10-01", "2026-10-20", 19)
    _onayli_ekle(conn, ornek, "2026-06-01", "2026-06-20", 15)  # geçen öğretim yılı: sayılmaz
    assert izin.hak_ozeti(conn, ornek["ogr1"])["kullanilan"] == 19
    t = _yeni_talep(istemci, conn, ornek)  # 2 gün → 21 > 20
    _oturum(istemci, conn, ornek["yonetici"])
    sayfa = istemci.get(f"/yonetici/izinler/{t['id']}").text
    assert "19 gün" in sayfa and "aşılıyor" in sayfa
    _onayli_ekle(conn, ornek, "2026-11-02", "2026-11-03", 2)
    _oturum(istemci, conn, ornek["veli1"])
    assert "hakkı (20 gün) doldu" in istemci.get(f"/veli/izin?ogr={ornek['ogr1']}").text


def test_api_izinler(lan_istemci, conn, ornek, monkeypatch):  # noqa: F811
    _onayli_ekle(conn, ornek, "2026-11-23", "2026-11-25", 3)
    conn.execute(
        "INSERT INTO izin_talep (veli_id, ogrenci_id, baslangic, bitis, gun, neden_tur, durum, olusturma)"
        " VALUES (?, ?, '2026-11-23', '2026-11-25', 3, 'saglik', 'bekliyor', '2026-11-22 10:00:00')",
        (ornek["veli1"], ornek["ogr2"]),
    )
    conn.commit()
    yol = "/api/izinler?tarih=2026-11-24"
    monkeypatch.setattr(AYAR, "izin_anahtar", "gizli")
    assert lan_istemci.get(yol).status_code == 404
    assert lan_istemci.get(yol, headers={"X-Izin-Anahtar": "yanlis"}).status_code == 404
    h = {"X-Izin-Anahtar": "gizli"}
    assert lan_istemci.get(yol, headers={**h, "CF-Connecting-IP": "1.2.3.4"}).status_code == 404
    assert lan_istemci.get(yol, headers={**h, "X-Forwarded-For": "1.2.3.4"}).status_code == 404
    r = lan_istemci.get(yol, headers=h)
    assert r.status_code == 200 and r.json() == {"tarih": "2026-11-24", "siniflar": {"9-A": ["101"]}}
    assert lan_istemci.get("/api/izinler?tarih=2026-11-26", headers=h).json()["siniflar"] == {}
    assert lan_istemci.get("/api/izinler?tarih=bozuk", headers=h).status_code == 400
    monkeypatch.setattr(AYAR, "izin_anahtar", "")
    assert lan_istemci.get(yol, headers={"X-Izin-Anahtar": ""}).status_code == 404


def test_telegram_ayar_bossa_gondermez(monkeypatch):
    def patla(*a, **k):
        raise AssertionError("ağa çıkmamalı")

    monkeypatch.setattr(telegram.httpx, "post", patla)
    assert telegram.gonder("x") == 0


def test_bildirim_sms_istemcisi(monkeypatch):
    cagri = {}

    class Yanit:
        status_code = 200

    def sahte(url, json, headers, timeout, trust_env):
        cagri.update(url=url, json=json, headers=headers)
        return Yanit()

    monkeypatch.setattr(sms.httpx, "post", sahte)
    assert sms.bildirim_gonder("05321112233", "a" * 400) is True
    assert cagri["url"].endswith("/api/arac/bildirim-sms")
    assert cagri["headers"] == {"X-Sms-Arac-Key": AYAR.sms_anahtar}
    assert len(cagri["json"]["metin"]) == 320


def test_yonetici_mukerrer_talebi_siler(istemci, conn, ornek, bildirimler):
    t = _yeni_talep(istemci, conn, ornek)
    _oturum(istemci, conn, ornek["yonetici"])
    yol = f"/yonetici/izinler/{t['id']}"
    istemci.post(yol + "/karar", data={"csrf": _csrf(istemci, yol), "karar": "onayla"})
    assert izin.kullanilan_gun(conn, ornek["ogr1"], date(2026, 11, 23)) == t["gun"]
    pdf = dosyalar.yol(izin.EK_KLASOR, t["pdf_depo"])
    assert pdf.exists()
    assert istemci.post(yol + "/sil", data={}).status_code == 400  # CSRF yok
    r = istemci.post(yol + "/sil", data={"csrf": _csrf(istemci, yol)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/yonetici/izinler"
    assert conn.execute("SELECT COUNT(*) FROM izin_talep WHERE id = ?", (t["id"],)).fetchone()[0] == 0
    assert izin.kullanilan_gun(conn, ornek["ogr1"], date(2026, 11, 23)) == 0
    assert not pdf.exists()
    assert istemci.get(yol).status_code == 404



def _ekle(c, ogr, baslangic="2026-11-23", bitis="2026-11-24", neden_tur="saglik", neden_metin="", csrf=None):
    veri = {
        "csrf": csrf if csrf is not None else _csrf(c, "/yonetici/izinler/ekle"),
        "ogrenci": str(ogr), "baslangic": baslangic, "bitis": bitis, "neden_tur": neden_tur, "neden_metin": neden_metin,
    }
    return c.post("/yonetici/izinler/ekle", data=veri, follow_redirects=False)


def test_yonetici_manuel_izin_onayli_olusur(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["yonetici"])
    assert istemci.get("/yonetici/izinler/ekle").status_code == 200  # {talep_id} rotasıyla çakışmaz
    r = _ekle(istemci, ornek["ogr2"], neden_metin="Telefonla bildirildi")
    assert r.status_code == 303 and r.headers["location"] == "/yonetici/izinler"
    t = izin.detay(conn, conn.execute("SELECT id FROM izin_talep").fetchone()[0])
    assert t["durum"] == "onaylandi" and t["gun"] == 2 and t["idare_girisi"] is True
    assert t["veli_id"] == t["karar_veren"] == ornek["yonetici"]
    assert t["karar_zamani"] == t["olusturma"] and t["pdf_depo"] is None
    assert izin.onayli_siniflar(conn, "2026-11-23") == {"9-B": ["201"]}
    assert izin.kullanilan_gun(conn, ornek["ogr2"], date(2026, 11, 23)) == 2
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = ?", (f"izin_ekle:{t['id']}",)).fetchone()[0] == 1
    assert bildirimler == {"sms": [], "push": [], "push_sonuc": [], "telegram": []}
    liste = istemci.get("/yonetici/izinler").text
    assert "İdare girişi" in liste and "🗑 İptal" in liste and "veli Müdür Bey" not in liste


def test_veli_talebi_idare_girisi_degil(istemci, conn, ornek, bildirimler):
    t = _yeni_talep(istemci, conn, ornek)
    assert izin.detay(conn, t["id"])["idare_girisi"] is False


def test_manuel_izin_csrf_ve_rol(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["yonetici"])
    assert _ekle(istemci, ornek["ogr1"], csrf="").status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0
    for anahtar in ("veli1", "ogretmen", "ogr1_k"):
        _oturum(istemci, conn, ornek[anahtar])
        assert istemci.get("/yonetici/izinler/ekle").status_code == 404
        veri = {"ogrenci": str(ornek["ogr1"]), "baslangic": "2026-11-23", "bitis": "2026-11-23", "neden_tur": "saglik"}
        assert istemci.post("/yonetici/izinler/ekle", data=veri).status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0


def test_manuel_izin_gecersiz_girdi_formu_tekrar_gosterir(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["yonetici"])
    o = ornek["ogr1"]
    assert _ekle(istemci, o, baslangic="2026-11-28", bitis="2026-11-29").status_code == 422  # hafta sonu
    assert _ekle(istemci, o, baslangic="2026-11-25", bitis="2026-11-24").status_code == 422
    assert _ekle(istemci, o, neden_tur="diger").status_code == 422
    r = _ekle(istemci, 99999)
    assert r.status_code == 422 and "Öğrenci seçin" in r.text
    assert _ekle(istemci, 0).status_code == 422
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0
    # saatte 3 sınırı idare girişine uygulanmaz
    for _ in range(4):
        assert _ekle(istemci, o).status_code == 303


def test_idare_izin_listeden_iptal_edilir(istemci, conn, ornek, bildirimler):
    _oturum(istemci, conn, ornek["yonetici"])
    _ekle(istemci, ornek["ogr1"])
    tid = conn.execute("SELECT id FROM izin_talep").fetchone()[0]
    assert izin.kullanilan_gun(conn, ornek["ogr1"], date(2026, 11, 23)) == 2
    assert istemci.post(f"/yonetici/izinler/{tid}/sil", data={}).status_code == 400
    r = istemci.post(
        f"/yonetici/izinler/{tid}/sil", data={"csrf": _csrf(istemci, "/yonetici/izinler")}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == "/yonetici/izinler"
    assert conn.execute("SELECT COUNT(*) FROM izin_talep").fetchone()[0] == 0
    assert izin.kullanilan_gun(conn, ornek["ogr1"], date(2026, 11, 23)) == 0


def test_yonetici_ana_izin_bolumu(istemci, conn, ornek):
    _oturum(istemci, conn, ornek["yonetici"])
    h = istemci.get("/yonetici").text
    assert "<h2>İZİN</h2>" in h and 'href="/yonetici/izinler/ekle"' in h and "Veli izin talepleri" in h
    assert h.count('href="/yonetici/izinler"') == 1
