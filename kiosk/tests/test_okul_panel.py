"""okul_panel.py /pano: yetki, Origin, doğrulama, resim yükleme/silme güvenliği, yedek ve atomik yazım."""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("PANEL_SIFRE", "test-sifresi")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import okul_panel  # noqa: E402

AUTH = "Basic " + base64.b64encode(b"admin:" + os.environ["PANEL_SIFRE"].encode()).decode()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@pytest.fixture
def pano(tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "data").mkdir(parents=True)
    (web / "panoresim").mkdir()
    cfg = {"_aciklama": "korunmalı", "okul": "Okul", "slayt_sn": 6, "yks_ay": 6, "yks_gun": 20, "yks_saat": "10:15",
           "farabi_url": "http://farabi.local:9090/api/pano",
           "nobetci_cizelge": {"Bahçe": ["A", "B", "C", "D", "E"], "Zemin Kat": ["F", "G", "H", "I", "J"]}}
    (web / "data" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (web / "data" / "bilgiler.json").write_text(json.dumps([{"k": "BİLİM", "m": "Bir bilgi."}]), encoding="utf-8")
    (web / "data" / "program.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PANO_WEB", str(web))
    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), okul_panel.Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{sunucu.server_port}", web
    sunucu.shutdown()
    sunucu.server_close()


def istek(taban, yol, veri=None, tur="application/x-www-form-urlencoded", auth=AUTH, origin=None):
    basliklar = {"Content-Type": tur}
    if auth:
        basliklar["Authorization"] = auth
    if origin:
        basliklar["Origin"] = origin
    r = urllib.request.Request(taban + yol, data=veri, headers=basliklar)
    try:
        s = urllib.request.build_opener(YonlendirmeYok).open(r)
        return s.status, dict(s.headers), s.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def form(**alanlar):
    return urllib.parse.urlencode(alanlar, doseq=True).encode()


def sonuc(h):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(h["Location"]).query, keep_blank_values=True)
    return q["m"][0], q["h"][0]


def yukle_govdesi(ad, bayt):
    sinir = "XSINIRX"
    govde = (f'--{sinir}\r\nContent-Disposition: form-data; name="dosya"; filename="{ad}"\r\n'
             "Content-Type: application/octet-stream\r\n\r\n").encode() + bayt + f"\r\n--{sinir}--\r\n".encode()
    return govde, f"multipart/form-data; boundary={sinir}"


def cfg(web):
    return json.loads((web / "data" / "config.json").read_text(encoding="utf-8"))


def test_yetkisiz_401_ve_origin_403(pano):
    taban, _ = pano
    assert istek(taban, "/pano", auth=None)[0] == 401
    assert istek(taban, "/pano/yks", form(ay=6, gun=20, saat="10:15"), auth=None)[0] == 401
    assert istek(taban, "/pano/yks", form(ay=6, gun=20, saat="10:15"), origin="http://kotu.example")[0] == 403
    assert istek(taban, "/pano")[0] == 200


def test_nobetci_kaydet_korur_ve_yedekler(pano):
    taban, web = pano
    alanlar = {f"n_{i}_{g}": f"Ad{i}{g}" for i in range(2) for g in range(5)}
    s, h, _ = istek(taban, "/pano/nobetci", form(**alanlar))
    assert s == 303 and "kaydedildi" in sonuc(h)[0]
    c = cfg(web)
    assert c["nobetci_cizelge"]["Bahçe"][0] == "Ad00" and c["nobetci_cizelge"]["Zemin Kat"][4] == "Ad14"
    assert c["_aciklama"] == "korunmalı" and c["farabi_url"].endswith("/api/pano")
    assert list((web / "data").glob("config.json.bak-*"))


def test_nobetci_uzun_ad_reddedilir(pano):
    taban, web = pano
    onceki = cfg(web)
    s, h, _ = istek(taban, "/pano/nobetci", form(n_0_0="x" * 41))
    assert "en fazla 40" in sonuc(h)[1] and cfg(web) == onceki


def test_yks_ve_slayt_sn_dogrulama(pano):
    taban, web = pano
    assert "Geçerli" in sonuc(istek(taban, "/pano/yks", form(ay=2, gun=31, saat="10:15"))[1])[1]
    assert "SS:DD" in sonuc(istek(taban, "/pano/yks", form(ay=6, gun=20, saat="25:99"))[1])[1]
    assert "kaydedildi" in sonuc(istek(taban, "/pano/yks", form(ay=2, gun=29, saat="09:30"))[1])[0]
    assert (cfg(web)["yks_ay"], cfg(web)["yks_gun"], cfg(web)["yks_saat"]) == (2, 29, "09:30")
    assert "2-60" in sonuc(istek(taban, "/pano/slayt-sn", form(slayt_sn=1))[1])[1]
    assert "2-60" in sonuc(istek(taban, "/pano/slayt-sn", form(slayt_sn=61))[1])[1]
    istek(taban, "/pano/slayt-sn", form(slayt_sn=10))
    assert cfg(web)["slayt_sn"] == 10


def test_bilgiler_ekle_sil_bos_liste_reddi(pano):
    taban, web = pano
    istek(taban, "/pano/bilgiler", form(k=["BİLİM", "TARİH", "X"], m=["Bir bilgi.", "Yeni bilgi", ""]))
    liste = json.loads((web / "data" / "bilgiler.json").read_text(encoding="utf-8"))
    assert liste == [{"k": "BİLİM", "m": "Bir bilgi."}, {"k": "TARİH", "m": "Yeni bilgi"}]  # boş metin silindi
    assert "boş olamaz" in sonuc(istek(taban, "/pano/bilgiler", form(k=["A"], m=[""]))[1])[1]
    assert len(json.loads((web / "data" / "bilgiler.json").read_text(encoding="utf-8"))) == 2


def test_resim_yukle_cakisma_ve_reddedilenler(pano):
    taban, web = pano
    govde, tur = yukle_govdesi("Güzel Resim.png", PNG)
    assert "yüklendi" in sonuc(istek(taban, "/pano/resim-yukle", govde, tur)[1])[0]
    assert "yüklendi" in sonuc(istek(taban, "/pano/resim-yukle", govde, tur)[1])[0]
    assert sorted(f.name for f in (web / "panoresim").iterdir()) == ["Güzel-Resim-2.png", "Güzel-Resim.png"]
    g2, t2 = yukle_govdesi("a.png", b"GIF89a" + b"\x00" * 50)
    assert "Yalnızca JPG" in sonuc(istek(taban, "/pano/resim-yukle", g2, t2)[1])[1]
    g3, t3 = yukle_govdesi("sahte.jpg", b"MZ-calistirilabilir" + b"\x00" * 50)  # uzantı jpg ama içerik değil
    assert "Yalnızca JPG" in sonuc(istek(taban, "/pano/resim-yukle", g3, t3)[1])[1]
    g4, t4 = yukle_govdesi("../../etc/evil.jpg", JPG)  # yol gezintisi adı temizlenir
    assert "yüklendi" in sonuc(istek(taban, "/pano/resim-yukle", g4, t4)[1])[0]
    assert not (web.parent / "etc").exists() and (web / "panoresim" / "evil.jpg").exists()


def test_resim_cok_buyuk_reddedilir(pano):
    taban, web = pano
    g, t = yukle_govdesi("b.png", PNG + b"\x00" * (okul_panel.RESIM_LIMIT + 10))  # sınırı az aşar: mesajla reddedilir
    s, h, _ = istek(taban, "/pano/resim-yukle", g, t)
    assert s == 303 and "6 MB" in sonuc(h)[1]
    g, t = yukle_govdesi("b.png", PNG + b"\x00" * (okul_panel.RESIM_LIMIT + 200_000))  # çok büyük: gövde okunmadan 413
    assert istek(taban, "/pano/resim-yukle", g, t)[0] == 413
    assert list((web / "panoresim").iterdir()) == []


def test_resim_sil_yalniz_listedeki_ve_geri_alinabilir(pano):
    taban, web = pano
    (web / "panoresim" / "a.jpg").write_bytes(JPG)
    assert "silindi" in sonuc(istek(taban, "/pano/resim-sil", form(ad="a.jpg"))[1])[0]
    assert not (web / "panoresim" / "a.jpg").exists()
    assert [f.name for f in (web.parent / "panoresim-silinen").iterdir()][0].endswith("-a.jpg")
    for kotu in ("../data/config.json", "/etc/passwd", "yok.jpg", ""):
        assert "bulunamadı" in sonuc(istek(taban, "/pano/resim-sil", form(ad=kotu))[1])[1]
    assert (web / "data" / "config.json").exists()


def test_eski_senkron_uyarisi(pano):
    taban, web = pano
    assert b"dk" in istek(taban, "/pano")[2] and b"g\xc3\xbcncellenmiyor" not in istek(taban, "/pano")[2]
    eski = time.time() - 40 * 60
    os.utime(web / "data" / "program.json", (eski, eski))
    assert "güncellenmiyor" in istek(taban, "/pano")[2].decode()


def test_yedek_sayisi_sinirli(pano):
    taban, web = pano
    for _ in range(okul_panel.YEDEK_ADEDI + 3):
        istek(taban, "/pano/slayt-sn", form(slayt_sn=7))
        time.sleep(1.05)  # yedek adı saniye çözünürlüklü
    assert len(list((web / "data").glob("config.json.bak-*"))) == okul_panel.YEDEK_ADEDI


def test_bilinmeyen_pano_yolu_404(pano):
    taban, _ = pano
    assert istek(taban, "/pano/yok", form(a=1))[0] == 404
