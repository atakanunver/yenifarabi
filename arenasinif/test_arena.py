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

    # 3. Zaten sahip olunan bölgeye tekrar hamle yapılırsa puan ve kombo verilmemeli
    hamle_tekrar = client.post(
        "/api/fetih/hamle",
        json={
            "dugum_id": 7,
            "takim_index": 0,
            "dogru_mu": True,
            "saldiri_mi": False,
            "harita": h_data["harita"],
        },
    )
    assert hamle_tekrar.status_code == 200
    assert hamle_tekrar.json()["puan_degisimi"] == 0
    assert hamle_tekrar.json()["kombo_bonus"] == 0
    assert "zaten" in hamle_tekrar.json()["mesaj"]


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
    """Tahta Düellosu HTML, soru hazırlama (karıştırma) ve JSON skor API'lerini doğrular."""
    from fastapi.testclient import TestClient
    client = TestClient(server.app)

    # 1. HTML sayfası
    res = client.get("/duello")
    assert res.status_code == 200
    assert "TAHTA DÜELLOSU" in res.text
    assert "liderlikModal" in res.text

    # 2. Oturum API
    res_oturum = client.get("/api/duello/oturum?sinif=10-A&ders=Biyoloji")
    assert res_oturum.status_code == 200
    veri = res_oturum.json()
    assert veri["durum"] == "ok"
    assert len(veri["ogrenciler"]) > 0
    assert len(veri["sorular"]) == 10
    assert "skorlar" in veri

    # 3. Farklı derslerde (İngilizce, Matematik, Tarih) soru ve şık kontrolü
    for d in ["İngilizce", "Matematik", "Tarih", "Biyoloji"]:
        res_soru = client.get(f"/api/duello/sorular?ders={d}&sinif=10&adet=10")
        assert res_soru.status_code == 200
        veri_soru = res_soru.json()
        assert veri_soru["durum"] == "ok"
        assert len(veri_soru["sorular"]) == 10

        dogru_indexler = set()
        for s in veri_soru["sorular"]:
            sec = s["secenekler"]
            assert len(sec) == 4
            # Şıklarda sahte/boş metin olmamalı ("B şıkkı", "C şıkkı" vb.)
            for metin in sec:
                assert "şıkkı" not in str(metin).lower(), f"Sahte şık tespit edildi: {metin}"
                assert len(str(metin).strip()) > 0
            # Doğru cevap şıklar arasında olmalı
            assert s["a"] in sec
            assert sec[s["dogru_index"]] == s["a"]
            dogru_indexler.add(s["dogru_index"])

        # Doğru şık A, B, C, D arasında dağılmış olmalı (sürekli A olamaz)
        assert len(dogru_indexler) > 1, f"Tüm sorular aynı şıkka ({dogru_indexler}) denk geldi!"

    # 4. JSON Skor Kaydetme API Testi
    skor_istek = {
        "sinif": "10-A",
        "ders": "İngilizce",
        "sol_oyuncu": "Ahmet Yılmaz",
        "sol_puan": 40,
        "sag_oyuncu": "Zeynep Çelik",
        "sag_puan": 20,
        "kazanan": "Ahmet Yılmaz",
        "seri": 1,
    }
    res_kayit = client.post("/api/duello/skor_kaydet", json=skor_istek)
    assert res_kayit.status_code == 200
    kayit_veri = res_kayit.json()
    assert kayit_veri["durum"] == "ok"
    assert kayit_veri["sol_oyuncu"]["toplam_puan"] >= 40
    assert kayit_veri["sol_oyuncu"]["galibiyet"] >= 1

    # 5. JSON Skor Listeleme API Testi
    res_liste = client.get("/api/duello/skorlar?sinif=10-A")
    assert res_liste.status_code == 200
    liste_veri = res_liste.json()
    assert liste_veri["durum"] == "ok"
    assert len(liste_veri["liderlik"]) >= 2
    lider_isimler = [o["ad"] for o in liste_veri["liderlik"]]
    assert "Ahmet Yılmaz" in lider_isimler
    assert "Zeynep Çelik" in lider_isimler


def test_genel_json_skorlari_ve_guvenli_kapatma():
    """Tüm oyunların JSON skor tablosu kaydını ve güvenli arayüz kontrollerini doğrular."""
    import json
    from pathlib import Path

    # 1. POST /api/arena/sonuc-kaydet ile takım ve öğrenci puanı kaydet
    sonuc_istek = {
        "oyun": "sinif_arena",
        "sinif": "9-A",
        "ders": "Biyoloji",
        "katilimcilar": [
            {
                "ad": "Mitokondriler",
                "puan": 450,
                "tur": "takim",
                "kazanan": True,
                "uyeler": ["Ali Veli", "Ayşe Can"],
            },
            {
                "ad": "Ribozomlar",
                "puan": 300,
                "tur": "takim",
                "kazanan": False,
                "uyeler": ["Can Demir", "Zeynep Bal"],
            },
        ],
    }
    res_kaydet = client.post("/api/arena/sonuc-kaydet", json=sonuc_istek)
    assert res_kaydet.status_code == 200
    assert res_kaydet.json()["durum"] == "ok"

    # 2. JSON dosyasının varlığı ve içeriği
    import sonuc_deposu
    json_dosya = sonuc_deposu.json_skor_dosyasi()
    assert json_dosya.exists(), f"{json_dosya} dosyası oluşturulmadı!"
    with open(json_dosya, encoding="utf-8") as f:
        skor_veri = json.load(f)
    assert "siniflar" in skor_veri
    assert "9-A" in skor_veri["siniflar"]
    assert "Mitokondriler" in skor_veri["siniflar"]["9-A"]["takimlar"]

    # 3. GET /api/arena/skorlar?sinif=9-A endpoint kontrolü
    res_skorlar = client.get("/api/arena/skorlar?sinif=9-A")
    assert res_skorlar.status_code == 200
    api_skor = res_skorlar.json()
    assert api_skor["durum"] == "ok"
    assert len(api_skor["takim_liderlik"]) >= 1
    assert any(t["ad"] == "Mitokondriler" for t in api_skor["takim_liderlik"])

    # 4. Arayüz Dosyalarının Güvenlik ve Görev Çubuğu Uyumluluğu
    duello_html = Path("/home/ata/arenasinif/duello.html").read_text(encoding="utf-8")
    assert "safe-tahta-bottom" in duello_html, "duello.html içinde akıllı tahta güvenli alanı tanımlanmamış!"
    assert "duelloKayitRozeti" in duello_html, "duello.html içinde JSON kayıt rozeti eksik!"
    assert "pb-20" in duello_html, "duello.html içinde başlat çubuğu payı eksik!"

    hexafetih_html = Path("/home/ata/arenasinif/hexafetih.html").read_text(encoding="utf-8")
    assert "guvenliSoruModalKapat" in hexafetih_html, "hexafetih.html soru kapatmada onay mekanizması eksik!"
    assert "JSON dosyasına kaydedildi" in hexafetih_html, "hexafetih.html zafer ekranında kayıt rozeti eksik!"

    sinif_arena_html = Path("/home/ata/arenasinif/sinif_arena.html").read_text(encoding="utf-8")
    assert "confirmCloseQuestionModal" in sinif_arena_html, "sinif_arena.html soru kapatmada onay eksik!"
    assert "JSON puan tablosuna kaydedildi" in sinif_arena_html, "sinif_arena.html podyum ekranında kayıt rozeti eksik!"



