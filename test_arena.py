"""test_arena.py - Sınıf Arenası Doğrulama ve Entegrasyon Testleri.

1. IP ve sınıf eşleme testi
2. Zil ve ders programı çözümleme testi
3. Yoklama filtreleme (devamsızların elenmesi) testi
4. Dengeli takım oluşturma (cinsiyet ve sayı eşitliği) testi
5. Hazır müfredat soru havuzu testi
6. RAG + Ollama canlı soru üretim uç noktası testi
"""

import re

import pytest
from fastapi.testclient import TestClient

import server
import soru_uretici
import takim_kurucu
import fetih_motoru

client = TestClient(server.app)

# Kaynak biçimi: statik set "MEB Biyoloji 9, s. 124"; soru havuzu "Biyoloji 9, s. 96"
KAYNAK_RE = re.compile(r"^(MEB )?.+, [sp]\. ?\d+")


def test_ip_den_sinif_bul():
    # 9-A tahta IP'si
    assert server._ip_den_sinif_bul("192.168.23.245") == "9-A"
    # 12-B tahta IP'si
    assert server._ip_den_sinif_bul("192.168.23.240") == "12-B"
    # Bilinmeyen IP -> Varsayılan 9-A
    assert server._ip_den_sinif_bul("127.0.0.1") == "9-A"


def test_yoklama_ve_ogrenciler():
    # 12-B sınıfında yoklama kaydı mevcut (4 devamsız öğrenci)
    tum, mevcut, devamsiz = server._ogrencileri_ve_yoklamayi_getir("12-B", ders_no=8)
    assert len(tum) == 17
    assert len(devamsiz) == 4
    assert len(mevcut) == 13

    # Devamsızların 'mevcut' alanı False olmalı
    assert all(not d["mevcut"] for d in devamsiz)
    assert all(m["mevcut"] for m in mevcut)


def test_takim_dengeleme():
    ornek_ogrenciler = [
        {"no": 1, "ad_soyad": "Kız 1", "cinsiyet": "Kız"},
        {"no": 2, "ad_soyad": "Kız 2", "cinsiyet": "Kız"},
        {"no": 3, "ad_soyad": "Kız 3", "cinsiyet": "Kız"},
        {"no": 4, "ad_soyad": "Kız 4", "cinsiyet": "Kız"},
        {"no": 5, "ad_soyad": "Erkek 1", "cinsiyet": "Erkek"},
        {"no": 6, "ad_soyad": "Erkek 2", "cinsiyet": "Erkek"},
        {"no": 7, "ad_soyad": "Erkek 3", "cinsiyet": "Erkek"},
        {"no": 8, "ad_soyad": "Erkek 4", "cinsiyet": "Erkek"},
    ]
    takimlar = takim_kurucu.takimlari_olustur(ornek_ogrenciler, "Biyoloji", takim_sayisi=4)
    assert len(takimlar) == 4

    # Her takımda tam 1 kız ve 1 erkek olmalı (mükemmel denge)
    for t in takimlar:
        assert len(t["ogrenciler"]) == 2
        kiz_sayisi = sum(1 for o in t["ogrenciler"] if o["cinsiyet"] == "Kız")
        erkek_sayisi = sum(1 for o in t["ogrenciler"] if o["cinsiyet"] == "Erkek")
        assert kiz_sayisi == 1
        assert erkek_sayisi == 1

    # Biyoloji temalı isimler
    assert takimlar[0]["name"] == "Mitokondriler"


def test_oturum_api():
    response = client.get("/api/arena/oturum?sinif=9-A")
    assert response.status_code == 200
    data = response.json()

    assert data["sinif"] == "9-A"
    assert "ders_adi" in data
    assert len(data["takimlar"]) >= 2
    assert len(data["sorular"]) == 4

    # Her kategoride 4 soru olmalı
    for kat in data["sorular"]:
        assert len(kat["questions"]) == 4


def test_takim_yenile_api():
    response = client.post(
        "/api/arena/takim-yenile",
        json={"sinif": "9-A", "ders": "Kimya", "takim_sayisi": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["durum"] == "ok"
    assert len(data["takimlar"]) == 3
    # Kimya temalı isimler
    assert data["takimlar"][0]["name"] == "Katalizörler"


def test_log_hata_api():
    response = client.post(
        "/api/arena/log-hata",
        json={
            "mesaj": "Test Hatasi: Dokunmatik tiklama hatasi",
            "kaynak_url": "http://farabi.local:8030/",
            "satir": 120,
            "sutun": 15,
            "stack": "Error at onClick...",
            "user_agent": "Pardus Chromium ETAP",
        },
    )
    assert response.status_code == 200
    assert response.json()["durum"] == "kaydedildi"


def test_saglik_api():
    response = client.get("/api/arena/saglik")
    assert response.status_code == 200
    data = response.json()
    assert "genel_durum" in data
    assert "servisler" in data
    assert "farabi_brain" in data["servisler"]
    assert "ollama" in data["servisler"]
    assert "yoklama_db" in data["servisler"]


def test_loglar_api():
    response = client.get("/api/arena/loglar?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "toplam" in data
    assert "loglar" in data
    assert isinstance(data["loglar"], list)


def test_favicon_api():
    response = client.get("/favicon.ico")
    assert response.status_code == 204


def test_fetih_sayfasi():
    response = client.get("/fetih")
    assert response.status_code == 200
    assert "HexaFetih" in response.text
    assert "hex-canvas" in response.text


def test_fetih_oturum_api():
    response = client.get("/api/fetih/oturum?sinif=10-A&ders=Biyoloji")
    assert response.status_code == 200
    data = response.json()
    assert data["durum"] == "ok"
    assert data["sinif"] == "10-A"
    assert data["ders"] == "Biyoloji"
    assert len(data["harita"]) == 19
    assert len(data["takimlar"]) == 4

    # Takım isimlerinin hem name hem isim olarak dolu ve geçerli olduğunu doğrula
    for t in data["takimlar"]:
        assert "name" in t and len(t["name"]) > 0
        assert "isim" in t and len(t["isim"]) > 0
        assert t["name"] == t["isim"]
        assert "undefined" not in t["name"].lower()

    # Başkent düğümü kontrolü (id: 0)
    baskent = data["harita"][0]
    assert baskent["id"] == 0
    assert baskent["tip"] == "baskent"
    assert baskent["puan"] == 350
    assert baskent["seviye"] == 3
    assert len(baskent["komsular"]) == 6


def test_fetih_hamle_api():
    # Önce harita al
    resp = client.get("/api/fetih/oturum?sinif=9-A&ders=Biyoloji")
    harita = resp.json()["harita"]

    # 1. Başarılı Boş Petek Fethi (id: 7, 100 puanlık kenar)
    hamle_resp = client.post(
        "/api/fetih/hamle",
        json={
            "dugum_id": 7,
            "takim_index": 0,
            "dogru_mu": True,
            "saldiri_mi": False,
            "harita": harita,
        },
    )
    assert hamle_resp.status_code == 200
    h_data = hamle_resp.json()
    assert h_data["durum"] == "ok"
    assert h_data["puan_degisimi"] == 100
    assert h_data["yeni_sahip"] == 0

    # 2. Başarısız Saldırı (-50 puan)
    hamle_saldiri_hata = client.post(
        "/api/fetih/hamle",
        json={
            "dugum_id": 7,
            "takim_index": 1,
            "dogru_mu": False,
            "saldiri_mi": True,
            "harita": h_data["harita"],
        },
    )
    assert hamle_saldiri_hata.status_code == 200
    assert hamle_saldiri_hata.json()["puan_degisimi"] == -50
    # Sahip değişmemeli (hala Takım 0 olmalı)
    assert hamle_saldiri_hata.json()["yeni_sahip"] == 0


def test_tum_derslerin_soru_bankasi():
    """Tüm 14 ders için hem HexaFetih hem Sınıf Arenası soru havuzunun tam ve geçerli olduğunu doğrular."""
    ornek_ogrenciler = [
        {"no": 1, "ad_soyad": "Ahmet Yılmaz", "cinsiyet": "Erkek", "mevcut": True},
        {"no": 2, "ad_soyad": "Ayşe Kaya", "cinsiyet": "Kız", "mevcut": True},
        {"no": 3, "ad_soyad": "Mehmet Demir", "cinsiyet": "Erkek", "mevcut": True},
        {"no": 4, "ad_soyad": "Zeynep Çelik", "cinsiyet": "Kız", "mevcut": True},
    ]

    for ders in server.TUM_DERSLER:
        # 1. HexaFetih testi: 19 petek, her petekte 4 seçenek ve doğru cevap
        harita = fetih_motoru.haritayi_hazirla(ders)
        assert len(harita) == 19, f"{ders} için 19 petek olmalı"
        for d in harita:
            assert "konu" in d and len(d["konu"]) > 0
            soru = d["soru"]
            assert len(soru["secenekler"]) == 4
            assert soru["dogru_cevap"] in soru["secenekler"]
            assert KAYNAK_RE.match(soru["kaynak"]), f"{ders} HexaFetih sorusunda geçersiz kaynak: {soru['kaynak']}"

        # 2. Sınıf Arenası (Jeopardy) testi: 4 kategori, her kategoride 4 soru
        sorular = soru_uretici.hazir_sorulari_getir(ders)
        assert len(sorular) == 4, f"{ders} için 4 kategori olmalı"
        for kat in sorular:
            assert len(kat["questions"]) == 4
            puanlar = [q["points"] for q in kat["questions"]]
            assert puanlar == [100, 200, 300, 400]
            for q in kat["questions"]:
                assert len(q["q"]) > 0
                assert len(q["a"]) > 0
                assert KAYNAK_RE.match(q["kaynak"]), f"{ders} Jeopardy sorusunda geçersiz kaynak: {q['kaynak']}"

        # 3. Tematik Takım testi: 4 takım, isimler dolu ve tematik
        takimlar = takim_kurucu.takimlari_olustur(ornek_ogrenciler, ders, takim_sayisi=4)
        assert len(takimlar) == 4
        for t in takimlar:
            assert len(t["name"]) > 0
            assert t["name"] == t["isim"]
            assert "undefined" not in t["name"].lower()


def test_duello_endpoints():
    """Tahta Düellosu HTML ve API uç noktalarını doğrular."""
    from fastapi.testclient import TestClient
    client = TestClient(server.app)

    # 1. HTML sayfası
    res = client.get("/duello")
    assert res.status_code == 200
    assert "TAHTA DÜELLOSU" in res.text

    # 2. Oturum API
    res_oturum = client.get("/api/duello/oturum?sinif=10-A&ders=Biyoloji")
    assert res_oturum.status_code == 200
    veri = res_oturum.json()
    assert veri["durum"] == "ok"
    assert len(veri["ogrenciler"]) > 0
    assert len(veri["sorular"]) == 10

    # 3. Soru API
    res_soru = client.get("/api/duello/sorular?ders=Biyoloji&sinif=10&adet=10")
    assert res_soru.status_code == 200
    veri_soru = res_soru.json()
    assert veri_soru["durum"] == "ok"
    assert len(veri_soru["sorular"]) == 10

