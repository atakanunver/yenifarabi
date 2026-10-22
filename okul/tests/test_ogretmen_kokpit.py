"""Öğretmen kokpiti: canlı ders kartı, Bugün listesi, ders defteri, Okudum, not defteri."""

import json
from datetime import datetime

import auth
import duyurular
import pytest
import zaman
from ayarlar import AYAR
from fastapi.testclient import TestClient
from kaynaklar import kazanim


@pytest.fixture
def istemci(monkeypatch, ornek, saat):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    AYAR.program_yolu.write_text(
        json.dumps({"siniflar": {"9-A": {"pazartesi": {"1": "matematik", "3": "matematik"}}}}), encoding="utf-8"
    )
    AYAR.zil_yolu.write_text(
        json.dumps({"dersler": [
            {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
            {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
            {"no": 3, "baslangic": "09:50", "bitis": "10:30"},
        ]}), encoding="utf-8",
    )
    AYAR.takvim_yolu.write_text(json.dumps({"tatiller": []}), encoding="utf-8")
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def epoch(saat_str):
    h, m = map(int, saat_str.split(":"))
    return int(datetime(2026, 10, 12, h, m, tzinfo=zaman.TZ).timestamp() * 1000)


def hoca(c):
    return giris(c, "hoca", "hoca-sifre")


# --- canlı ders kartı ---


def test_canli_kart_devam_eden_ders(istemci, saat):
    saat["an"] = datetime(2026, 10, 12, 8, 30)
    hoca(istemci)
    h = istemci.get("/ogretmen").text
    assert 'ders-kart devam' in h and "9. sınıf · A şubesi" in h and "9-A sınıfı" in h
    assert f'data-hedef="{epoch("08:50")}"' in h and "ŞU AN" in h
    assert 'href="/ogretmen/odev/yeni?sinif=9-A&ders=matematik"' in h
    assert 'href="/ogretmen/duyuru?sinif=9-A"' in h and "/ogretmen/not/yeni?sinif=9-A" in h


def test_canli_kart_siradaki_ders_ve_teneffus(istemci, saat):
    saat["an"] = datetime(2026, 10, 12, 9, 20)  # 2. ders (öğretmenin değil); sıradaki 3. ders
    hoca(istemci)
    h = istemci.get("/ogretmen").text
    assert 'ders-kart sirada' in h and 'data-durum="sirada"' in h and f'data-hedef="{epoch("09:50")}"' in h


def test_dersler_bitince_kart_yok(istemci, saat):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    hoca(istemci)
    assert 'id="ders-kart"' not in istemci.get("/ogretmen").text


def test_hafta_sonu_kart_yok(istemci, saat):
    saat["an"] = datetime(2026, 10, 11, 9, 0)  # pazar
    hoca(istemci)
    h = istemci.get("/ogretmen").text
    assert 'id="ders-kart"' not in h and "Bugün neler yapayım?" in h


# --- ders defteri ---


def test_ders_defteri_isaretle_ve_gorunur(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 8, 30)
    csrf = hoca(istemci)
    veri = {"csrf": csrf, "ders_no": 1, "sinif": "9-A", "ders": "matematik"}
    r = istemci.post("/ogretmen/ders-defteri", data=veri, follow_redirects=False)
    assert r.status_code == 303
    istemci.post("/ogretmen/ders-defteri", data=veri)  # tekrar: UPSERT, ikinci satır yok
    assert conn.execute("SELECT count(*), max(islendi) FROM ders_defteri WHERE kullanici_id = ?", (ornek["ogretmen"],)).fetchone()[:] == (1, 1)
    assert "✓ Kazanım işlendi" in istemci.get("/ogretmen").text


def test_ders_defteri_yetki_ve_dogrulama(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 8, 30)
    csrf = hoca(istemci)
    for kotu in (
        {"ders_no": 2, "sinif": "9-A", "ders": "matematik"},  # o saatte dersi yok
        {"ders_no": 1, "sinif": "9-B", "ders": "matematik"},  # sınıfı değil
        {"ders_no": 1, "sinif": "9-A", "ders": "fizik"},  # dersi değil
    ):
        assert istemci.post("/ogretmen/ders-defteri", data={"csrf": csrf, **kotu}).status_code == 404
    assert istemci.post("/ogretmen/ders-defteri", data={"ders_no": 1, "sinif": "9-A", "ders": "matematik"}).status_code == 400  # csrf yok
    csrf_y = giris(istemci, "mudur", "mudur-sifre")
    assert istemci.post("/ogretmen/ders-defteri", data={"csrf": csrf_y, "ders_no": 1, "sinif": "9-A", "ders": "matematik"}).status_code == 404
    assert conn.execute("SELECT count(*) FROM ders_defteri").fetchone()[0] == 0


# --- Bugün neler yapayım? ---


def test_bugun_bos_liste(istemci, saat, conn, yeni_kullanici):
    yeni_kullanici(conn, "ogretmen", "Boş Hoca", "bos", sifre="bos-sifre")
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    giris(istemci, "bos", "bos-sifre")
    assert "Bugün için bekleyen bir şey yok" in istemci.get("/ogretmen").text


def test_bugun_defter_bekleyen_gecmis_ders(istemci, saat):
    saat["an"] = datetime(2026, 10, 12, 9, 20)  # 1. ders bitti, işaretlenmedi
    csrf = hoca(istemci)
    assert "9-A matematik dersinde kazanım işlendi mi?" in istemci.get("/ogretmen").text
    istemci.post("/ogretmen/ders-defteri", data={"csrf": csrf, "ders_no": 1, "sinif": "9-A", "ders": "matematik"})
    assert "dersinde kazanım işlendi mi?" not in istemci.get("/ogretmen").text


def test_okunmamis_duyuru_ve_okudum(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Kurul toplantısı", "Cuma 15:00", "okul", None, None)
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Başka sınıf", "9-B'ye özel", "sinif", "9-B", None)
    csrf = hoca(istemci)
    h = istemci.get("/ogretmen").text
    assert "Okunmamış duyurular" in h and "Kurul toplantısı" in h and "Başka sınıf" not in h
    assert "Okunmamış duyuru: Kurul toplantısı" in h  # Bugün listesinde de görev
    d_id = conn.execute("SELECT id FROM duyuru WHERE baslik = 'Kurul toplantısı'").fetchone()[0]
    assert istemci.post(f"/ogretmen/duyuru/{d_id}/okudum", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert "Kurul toplantısı" not in istemci.get("/ogretmen").text.split("Yayındaki duyurular")[0]
    # görünmeyen (başka sınıfa) duyuru için okudum = 404; csrf'siz reddedilir
    diger_id = conn.execute("SELECT id FROM duyuru WHERE baslik = 'Başka sınıf'").fetchone()[0]
    assert istemci.post(f"/ogretmen/duyuru/{diger_id}/okudum", data={"csrf": csrf}).status_code == 404
    assert istemci.post(f"/ogretmen/duyuru/{d_id}/okudum").status_code == 400


def test_duyuru_formu_sinif_onceden_secili(istemci):
    hoca(istemci)
    assert '<option value="9-A" selected>' in istemci.get("/ogretmen/duyuru?sinif=9-A").text


# --- not defteri ---


def test_not_ekle_listele_tamam_sil(istemci, conn, ornek):
    csrf = hoca(istemci)
    r = istemci.post("/ogretmen/not/yeni", data={"csrf": csrf, "metin": "Yarın deney föyü", "yapilacak": "1", "donus": "ana"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ogretmen"
    assert "Yarın deney föyü" in istemci.get("/ogretmen/not").text
    assert "Yarın deney föyü" in istemci.get("/ogretmen").text  # hem hızlı not özetinde hem Bugün listesinde
    n = conn.execute("SELECT id FROM ogretmen_not").fetchone()[0]
    istemci.post(f"/ogretmen/not/{n}/tamam", data={"csrf": csrf})
    assert conn.execute("SELECT tamam FROM ogretmen_not WHERE id = ?", (n,)).fetchone()[0] == 1
    assert "Notlarımdan · yapılacak" not in istemci.get("/ogretmen").text  # tamamlanan Bugün'den düşer
    istemci.post(f"/ogretmen/not/{n}", data={"csrf": csrf, "metin": "Güncel not"})
    assert "Güncel not" in istemci.get("/ogretmen/not").text
    assert istemci.post(f"/ogretmen/not/{n}/sil", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert conn.execute("SELECT count(*) FROM ogretmen_not").fetchone()[0] == 0


def test_not_dogrulama(istemci):
    csrf = hoca(istemci)
    assert istemci.post("/ogretmen/not/yeni", data={"csrf": csrf, "metin": "   "}).status_code == 422
    assert istemci.post("/ogretmen/not/yeni", data={"csrf": csrf, "metin": "x" * 2001}).status_code == 422
    assert istemci.post("/ogretmen/not/yeni", data={"metin": "csrfsiz"}).status_code == 400


def test_not_sahiplik_izolasyonu(istemci, conn, ornek, yeni_kullanici):
    yeni_kullanici(conn, "ogretmen", "Diğer Hoca", "diger", sifre="diger-sifre")
    csrf = hoca(istemci)
    istemci.post("/ogretmen/not/yeni", data={"csrf": csrf, "metin": "Gizli gözlem"})
    n = conn.execute("SELECT id FROM ogretmen_not").fetchone()[0]
    csrf2 = giris(istemci, "diger", "diger-sifre")
    assert "Gizli gözlem" not in istemci.get("/ogretmen/not").text
    assert istemci.get(f"/ogretmen/not/{n}").status_code == 404
    assert istemci.post(f"/ogretmen/not/{n}", data={"csrf": csrf2, "metin": "ele geçir"}).status_code == 404
    assert istemci.post(f"/ogretmen/not/{n}/tamam", data={"csrf": csrf2}).status_code == 404
    assert istemci.post(f"/ogretmen/not/{n}/sil", data={"csrf": csrf2}).status_code == 404
    assert conn.execute("SELECT metin FROM ogretmen_not WHERE id = ?", (n,)).fetchone()[0] == "Gizli gözlem"
    # yönetici ve öğrenci notlara erişemez
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get("/ogretmen/not").status_code == 404 and istemci.get(f"/ogretmen/not/{n}").status_code == 404
    giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/not").status_code == 404


def test_yonetici_ana_sayfada_not_kutusu_yok(istemci):
    giris(istemci, "mudur", "mudur-sifre")
    h = istemci.get("/ogretmen").text
    assert "Hızlı not" not in h


def test_gocu_28_geri_alma():
    import importlib.util
    import pathlib

    import db

    assert len(db.GOCLER) >= 28
    s = importlib.util.spec_from_file_location("geri_al", pathlib.Path("scripts/geri_al.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    assert "ders_defteri" in m.GERI[28] and "ogretmen_not" in m.GERI[28]
