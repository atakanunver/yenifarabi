"""test_yerel.py - Türkçe yardımcılar, kapsam eşleme, kazanım, sonuç özeti, statik sayfa denetimleri."""

import asyncio
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import fetih_motoru
import havuz
import logger
import server
import soru_uretici
import sonuc_deposu
import takim_kurucu
import turkce

KOK = Path(__file__).resolve().parent
SAYFALAR = ["sinif_arena.html", "hexafetih.html", "duello.html", "ozet.html"]
client = TestClient(server.app)


# ---------- Türkçe harf ----------
def test_turkce_baslik():
    assert turkce.tr_baslik("ingilizce") == "İngilizce"
    assert turkce.tr_baslik("inkılap tarihi ve atatürkçülük") == "İnkılap Tarihi ve Atatürkçülük"
    assert turkce.tr_baslik("türk dili ve edebiyatı") == "Türk Dili ve Edebiyatı"
    assert turkce.tr_baslik("ığdır ile ılık") == "Iğdır ile Ilık"
    assert turkce.tr_baslik("HEDEF FİZİK") == "Hedef Fizik"
    assert turkce.tr_baslik("t.c. inkılap tarihi") == "T.C. İnkılap Tarihi"
    assert turkce.tr_baslik("") == ""


def test_turkce_kucuk():
    assert turkce.tr_kucuk("İngilizce") == "ingilizce"
    assert turkce.tr_kucuk("IŞIK") == "ışık"
    assert turkce.kapsam_anahtari("  İNKILAP Tarihi ") == "inkılap tarihi"


def test_ders_adi_gosterimi(sahte_dunya):
    assert server._ders_adini_bul("12-A", 1, 5) == "Hedef Fizik"
    assert server._ders_adini_bul("12-A", 1, 6) == "İngilizce"
    assert server._ders_adini_bul("12-A", 1, 7) == "Türk Dili ve Edebiyatı"


# ---------- kapsam eşleme ----------
def test_almanca_kendi_anahtari():
    assert soru_uretici.KAPSAM_ESLEME["almanca"] == "almanca"
    assert server._ders_anahtari("Almanca") == "almanca"
    assert server._ders_anahtari("İngilizce") == "ingilizce"


@pytest.mark.parametrize("ad,anahtar", [
    ("hedef fizik", "fizik"), ("hedef kimya", "kimya"), ("hedef biyoloji", "biyoloji"),
    ("hedef matematik", "matematik"), ("hedef coğrafya", "cografya"), ("hedef tarih", "tarih"),
    ("sınav hazırlık çalışması", "genel"),
])
def test_hedef_dersleri_eslenir(ad, anahtar):
    assert soru_uretici.KAPSAM_ESLEME[ad] == anahtar
    assert server._ders_anahtari(ad.title()) == anahtar or anahtar == "genel"


def test_almanca_sorulari_ingilizce_veya_biyoloji_degil():
    kat = soru_uretici.hazir_sorulari_getir("Almanca")
    assert kat[0]["id"].startswith("alm_") and len(kat) == 4
    harita = fetih_motoru.haritayi_hazirla("Almanca")
    assert len(harita) == 19
    assert all("Almanca" in d["soru"]["kaynak"] for d in harita)
    assert takim_kurucu.takim_isimleri_getir("Almanca")[0]["name"] == "Adler"
    # İngilizce hâlâ kendi setini kullanır
    assert soru_uretici.hazir_sorulari_getir("İngilizce")[0]["id"].startswith("ing_")


def test_almanca_uretim_istemi_almanca_ister(monkeypatch):
    yakalanan = {}

    class SahteIstemci:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, **k):
            yakalanan["payload"] = json
            raise RuntimeError("ağ yok")

    monkeypatch.setattr(soru_uretici.httpx, "AsyncClient", SahteIstemci)
    asyncio.run(soru_uretici.ollama_soru_uret("Almanca", 9, "", []))
    sistem = yakalanan["payload"]["messages"][0]["content"]
    assert "ALMANCA" in sistem and "İngilizce soru ÜRETME" in sistem
    asyncio.run(soru_uretici.ollama_soru_uret("Fizik", 9, "", []))
    assert "ALMANCA" not in yakalanan["payload"]["messages"][0]["content"]


# ---------- haftanın kazanımı ----------
def test_haftanin_kazanimi(sahte_dunya):
    k = server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 22))
    assert k == ["Kuvvet ve hareket ilişkisini yorumlar.", "İş ve enerji hesaplar."]
    assert server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 27)) is not None  # hafta sonu hâlâ aynı hafta
    assert server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 28)) is None      # hafta 3 verisi yok
    assert server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 13)) is None      # hafta başlamadı
    assert server._haftanin_kazanimi("fenlab", "Hedef Fizik", date(2026, 9, 22)) is None
    assert server._haftanin_kazanimi("12-A", "Fizik", date(2026, 9, 22)) is None
    assert server._haftanin_kazanimi("9-A", "Hedef Fizik", date(2026, 9, 22)) is None


def test_kazanim_dosyasi_yoksa_bozulmaz(sahte_dunya, monkeypatch):
    monkeypatch.setattr(server, "KAZANIMLAR_JSON", sahte_dunya / "yok.json")
    assert server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 22)) is None
    (sahte_dunya / "bozuk.json").write_text("{bozuk", encoding="utf-8")
    monkeypatch.setattr(server, "KAZANIMLAR_JSON", sahte_dunya / "bozuk.json")
    assert server._haftanin_kazanimi("12-A", "Hedef Fizik", date(2026, 9, 22)) is None
    assert "haftanin_kazanimi" in client.get("/api/arena/oturum?sinif=12-A").json()


def test_kazanim_anahtar_kelimeleri():
    kw = havuz.kazanim_anahtar_kelimeleri("Hücre zarından madde geçişini ilgili örneklerle açıklar.")
    assert 1 <= len(kw) <= 3 and all(len(k) >= 5 for k in kw)
    assert havuz.kazanim_anahtar_kelimeleri("") == []


def test_kazanim_havuzda_bulunamazsa_filtresiz_doner():
    def _satir(konu, z, i):
        return (i, konu, z, f"S{i}", f"C{i}", ["a", "b", "c", "d"], 0, "Fizik 12, s. 5")

    tum = [_satir(k, z, i) for i, (k, z) in enumerate((k, z) for k in "ABCD" for z in (1, 2, 3, 4))]
    cagrilar = []

    def sorgu(sql, p):
        cagrilar.append(p)
        return [] if "ILIKE" in sql else tum

    s = havuz.jeopardy_seti("fizik", 12, "Kuvvet ve hareket ilişkisini yorumlar", sorgu=sorgu, kazanim=True)
    assert s and len(s) == 4
    assert any("ILIKE" in str(c) or "%" in str(c) for c in cagrilar)
    # kazanim=False: konu filtresi başarısız olursa eski davranış (None)
    assert havuz.jeopardy_seti("fizik", 12, "Kuvvet", sorgu=sorgu) is None


# ---------- hata günlüğü ----------
def test_log_hata_tekrar_suzulur():
    govde = {"mesaj": "ReferenceError: x is not defined", "user_agent": "t"}
    assert client.post("/api/arena/log-hata", json=govde).json()["durum"] == "kaydedildi"
    assert client.post("/api/arena/log-hata", json=govde).json()["durum"] == "tekrar"
    govde2 = dict(govde, mesaj="baska hata")
    assert client.post("/api/arena/log-hata", json=govde2).json()["durum"] == "kaydedildi"


def test_hata_hiz_siniri_zaman_gectikce_acilir():
    assert server._hata_loglanmali_mi("1.1.1.1", "m", 100.0)
    assert not server._hata_loglanmali_mi("1.1.1.1", "m", 130.0)
    assert server._hata_loglanmali_mi("1.1.1.1", "m", 161.0)
    assert server._hata_loglanmali_mi("2.2.2.2", "m", 130.0)


def test_testler_uretim_loguna_yazmaz():
    assert logger.LOG_DIR != KOK / "logs"
    assert "arena_test_" in str(logger.HATA_LOG_PATH)


# ---------- sonuç / özet ----------
def test_sonuc_kaydi_ve_ozet():
    govde = {
        "oyun": "sinif_arena", "sinif": "9-A", "ders": "Biyoloji", "kimlik": "abc",
        "katilimcilar": [
            {"ad": "Mitokondriler", "puan": 700, "kazanan": True, "uyeler": ["Ali", "Ayşe"]},
            {"ad": "Ribozomlar", "puan": 300, "uyeler": ["Can"]},
        ],
    }
    assert client.post("/api/arena/sonuc", json=govde).json()["durum"] == "ok"
    govde["katilimcilar"][1]["puan"] = 500  # aynı kimlik: güncellenir, çoğalmaz
    client.post("/api/arena/sonuc", json=govde)
    client.post("/api/arena/sonuc", json={
        "oyun": "duello", "sinif": "9-A", "ders": "Biyoloji",
        "katilimcilar": [{"ad": "Ali", "puan": 80, "tur": "ogrenci", "kazanan": True},
                         {"ad": "Can", "puan": 40, "tur": "ogrenci"}],
    })
    client.post("/api/arena/sonuc", json={"oyun": "hexafetih", "sinif": "10-A", "katilimcilar": [{"ad": "T", "puan": 1}]})

    o = client.get("/api/arena/ozet?sinif=9-A&gun=7").json()
    assert [s["sinif"] for s in o["siniflar"]] == ["9-A"]
    s = o["siniflar"][0]
    assert s["oyun_sayisi"] == 2 and s["bu_hafta"] == 2
    assert s["en_iyi_takimlar"][0] == {"ad": "Mitokondriler", "puan": 700, "oyun": 1, "galibiyet": 1}
    assert s["en_iyi_takimlar"][1]["puan"] == 500
    assert s["en_iyi_ogrenciler"][0]["ad"] == "Ali"
    assert s["katilan_ogrenci_sayisi"] == 3  # Ali, Ayşe, Can
    assert len(s["son_oyunlar"]) == 2
    assert {x["sinif"] for x in client.get("/api/arena/ozet").json()["siniflar"]} == {"9-A", "10-A"}


def test_sonuc_gecersiz_oyun_reddedilir():
    assert client.post("/api/arena/sonuc", json={"oyun": "hack", "katilimcilar": []}).status_code == 422
    assert client.get("/api/arena/ozet?gun=0").status_code == 422


def test_sonuc_veritabani_repo_icinde_degil():
    assert sonuc_deposu.db_yolu().is_relative_to(KOK) is False


def test_ozet_sayfasi_ve_statik():
    r = client.get("/ozet")
    assert r.status_code == 200 and "Katılım ve Skor Özeti" in r.text
    for yol in ("/static/tailwind.css", "/static/hata.js", "/static/vendor/fonts.css",
                "/static/vendor/confetti.browser-1.6.0.js", "/static/vendor/lucide-lite-1.52.0.min.js"):
        assert client.get(yol).status_code == 200, yol


# ---------- sayfa statik denetimleri ----------
JS_ANAHTAR = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "new", "await",
              "async", "else", "do", "try", "super", "void", "delete", "in", "of", "case", "throw", "yield"}
YERLESIK = {"fetch", "setTimeout", "setInterval", "clearTimeout", "clearInterval", "requestAnimationFrame",
            "cancelAnimationFrame", "parseInt", "parseFloat", "isNaN", "alert", "confirm", "prompt",
            "encodeURIComponent", "decodeURIComponent", "confetti", "getComputedStyle", "matchMedia",
            "structuredClone", "queueMicrotask", "sonucGonder", "sonucKimlikYenile", "hataLogla", "reportClientError"}
# şablon dizelerindeki CSS/metin parçaları (fonksiyon çağrısı değil)
YANLIS_POZITIF = {"rgba", "rgb", "ms", "translate", "url", "geçti", "veriyor"}


def _tanimsiz_cagrilar(html: str) -> set[str]:
    kod = "\n".join(re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", html, re.S))
    olaylar = " ".join(re.findall(r'\bon[a-z]+="([^"]*)"', html))
    kod = re.sub(r"/\*.*?\*/", "", kod, flags=re.S)
    kod = re.sub(r"(?m)(?<![:\"'])//.*$", "", kod)
    tanim = set(re.findall(r"function\s*\*?\s*([A-Za-z_$][\w$]*)", kod))
    tanim |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)", kod))
    for blok in re.findall(r"(?:const|let|var)\s*\{([^}]*)\}", kod):
        tanim |= {x.strip() for x in blok.split(",")}
    for p in re.findall(r"\(([^()]*)\)\s*=>", kod) + re.findall(r"function\s*[\w$]*\s*\(([^)]*)\)", kod):
        tanim |= set(re.findall(r"[A-Za-z_$][\w$]*", p))
    tanim |= set(re.findall(r"([A-Za-z_$][\w$]*)\s*=>", kod))
    tanim |= set(re.findall(r"catch\s*\((\w+)\)", kod))
    tanim |= set(re.findall(r"(?m)^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", kod))  # sınıf metodları
    cagrilan = set()
    for kaynak in (kod, olaylar):
        cagrilan |= set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", kaynak))
    return {n for n in cagrilan if n not in tanim | JS_ANAHTAR | YERLESIK | YANLIS_POZITIF and not n[0].isupper()}


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfalarda_tanimsiz_fonksiyon_yok(sayfa):
    assert _tanimsiz_cagrilar((KOK / sayfa).read_text(encoding="utf-8")) == set()


def test_hexafetih_sesclick_tanimli_ve_guvenli():
    html = (KOK / "hexafetih.html").read_text(encoding="utf-8")
    m = re.search(r"function sesClick\(\) \{(.*?)\n    \}\n", html, re.S)
    assert m, "sesClick tanımlı olmalı"
    govde = m.group(1)
    assert govde.lstrip().startswith("try {") and "catch" in govde  # sesBaslat dahil her şey try içinde
    assert "sesClick()" in html.split("function dersModalAc")[1][:80]
    assert "sesClick()" in html.split("function sinifModalAc")[1][:80]


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfalarda_dis_kaynak_yok(sayfa):
    html = (KOK / sayfa).read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "")
    assert not re.search(r"https?://", html), f"{sayfa} dış URL içeriyor"
    assert "tailwind.config" not in html and "cdn." not in html
    for yol in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
        assert (KOK / yol.lstrip("/")).exists(), yol


def test_hata_dedupe_istemcide_var():
    js = (KOK / "static" / "hata.js").read_text(encoding="utf-8")
    assert "MAX_RAPOR = 20" in js and "ARALIK_MS = 60000" in js
    for sayfa in ("sinif_arena.html", "hexafetih.html", "duello.html"):
        assert "/static/hata.js" in (KOK / sayfa).read_text(encoding="utf-8")
        assert "/static/sonuc.js" in (KOK / sayfa).read_text(encoding="utf-8") or sayfa == "ozet.html"


def test_kullanilan_lucide_ikonlari_pakette():
    giris = (KOK / "static/vendor/src/lucide-entry.js").read_text(encoding="utf-8")
    paketli = {re.sub(r"(?<!^)(?=[A-Z0-9])", "-", n).lower() for n in re.findall(r"\b([A-Z][A-Za-z0-9]*)\b", giris.split("const icons")[1].split("}")[0])}
    paketli = {p.replace("volume-2", "volume-2").replace("user-x", "user-x") for p in paketli}
    metin = (KOK / "sinif_arena.html").read_text(encoding="utf-8")
    kullanilan = set(re.findall(r'data-lucide["\']?[=,] ?["\']([a-z0-9-]+)["\']', metin))  # attribute + setAttribute(...)
    assert "volume-x" in kullanilan
    assert kullanilan <= paketli, kullanilan - paketli


def test_karekod_icerikli_ollama_yaniti_reddedilir(monkeypatch):
    import asyncio
    import json
    import httpx
    import soru_uretici

    sahte_karekod_seti = [
        {
            "id": "kat_1",
            "name": "Biyoloji Kavramları",
            "questions": [
                {"points": 100, "q": "Karekod okutularak ulaşılan simülasyon nedir?", "a": "Hücre zarı", "kaynak": "MEB Biyoloji 9, s. 12"},
                {"points": 200, "q": "Soru 2", "a": "Cevap 2", "kaynak": "MEB Biyoloji 9, s. 12"},
                {"points": 300, "q": "Soru 3", "a": "Cevap 3", "kaynak": "MEB Biyoloji 9, s. 12"},
                {"points": 400, "q": "Soru 4", "a": "Cevap 4", "kaynak": "MEB Biyoloji 9, s. 12"},
            ]
        },
        {"id": "kat_2", "name": "K2", "questions": [{"points": 100, "q": "q", "a": "a"}]},
        {"id": "kat_3", "name": "K3", "questions": [{"points": 100, "q": "q", "a": "a"}]},
        {"id": "kat_4", "name": "K4", "questions": [{"points": 100, "q": "q", "a": "a"}]},
    ]

    class SahteYanit:
        status_code = 200
        def json(self):
            return {"message": {"content": json.dumps(sahte_karekod_seti)}}

    class SahteClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return SahteYanit()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: SahteClient())

    sonuc = asyncio.run(soru_uretici.ollama_soru_uret("Biyoloji", 9, "Hücre"))
    assert sonuc is None, "Karekod içeren Ollama seti elenmeli ve None dönmeli"


def test_ogrenci_no_karisik_tip_siralamasi():
    import takim_kurucu
    ogrenciler = [
        {"no": 10, "ad_soyad": "Onuncu", "cinsiyet": "Erkek"},
        {"no": "5", "ad_soyad": "Besinci", "cinsiyet": "Erkek"},
        {"no": "12-A", "ad_soyad": "Metinli", "cinsiyet": "Kız"},
        {"no": None, "ad_soyad": "Numarasiz", "cinsiyet": "Kız"},
        {"no": 2, "ad_soyad": "Ikinci", "cinsiyet": "Erkek"},
    ]
    takimlar = takim_kurucu.takimlari_olustur(ogrenciler, "Matematik", takim_sayisi=2)
    for t in takimlar:
        nos = [o.get("no") for o in t["ogrenciler"]]
        assert len(nos) > 0


def test_havuz_ders_adi_kapsam_anahtari_normalize():
    import havuz
    yakalanan = []

    def sahte_sorgu(sql, p):
        yakalanan.append((sql, p))
        return []

    # Büyük harfli Türkçe ders adı gönderildiğinde veritabanına kanonik küçük harf gitmeli
    havuz._cek("Biyoloji", 9, "", sahte_sorgu)
    assert yakalanan[0][1][0] == "biyoloji"

    yakalanan.clear()
    havuz._cek("İngilizce", 10, "", sahte_sorgu)
    assert yakalanan[0][1][0] == "ingilizce"


def test_siniflar_arasi_skorlar_hesaplama():
    import sonuc_deposu
    res = sonuc_deposu.siniflar_arasi_skorlar(gun=365)
    assert "siniflar" in res
    assert "toplam_oyun" in res
    assert "toplam_dogru_soru" in res
    if res["siniflar"]:
        top_sinif = res["en_cok_soru_cevaplayan_sinif"]
        assert top_sinif is not None
        assert top_sinif["sira"] == 1
        assert top_sinif["dogru_soru"] >= 0


def test_siniflar_arasi_api_ve_saglik_alias():
    # Sınıflar arası liderlik API kontrolü
    r1 = client.get("/api/arena/siniflar-arasi?gun=30")
    assert r1.status_code == 200
    veri1 = r1.json()
    assert "siniflar" in veri1
    assert "ogrenciler_genel" in veri1

    # /api/saglik takma adı kontrolü
    r2 = client.get("/api/saglik")
    assert r2.status_code == 200
    assert "servisler" in r2.json()


def test_roster_db_fallback(sahte_dunya, monkeypatch):
    """Roster JSON dosyası yoksa veya boşsa, YOKLAMA_DB ogrenciler tablosundan okur."""
    import sqlite3
    bos_roster = sahte_dunya / "bos_roster"
    bos_roster.mkdir()
    monkeypatch.setattr(server, "ROSTER_DIR", bos_roster)

    test_db = sahte_dunya / "test_pano.db"
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE siniflar (id INTEGER PRIMARY KEY, ad TEXT)")
    conn.execute("CREATE TABLE ogrenciler (id INTEGER PRIMARY KEY, sinif_id INTEGER, no INTEGER, ad_soyad TEXT, cinsiyet TEXT, aktif INTEGER)")
    conn.execute("CREATE TABLE yoklama_onbellek (id INTEGER PRIMARY KEY, tarih TEXT, sinif TEXT, ders_no INTEGER, yok_isimleri TEXT, izinli_isimleri TEXT)")
    conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '9-A')")
    conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad, cinsiyet, aktif) VALUES (1, 101, 'Ayşe Yılmaz', 'Kız', 1)")
    conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad, cinsiyet, aktif) VALUES (1, 102, 'Mehmet Kaya', 'Erkek', 1)")
    conn.execute("INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, yok_isimleri, izinli_isimleri) VALUES ('2026-10-13', '9-A', 1, '[\"Mehmet Kaya\"]', '[]')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(server, "YOKLAMA_DB", test_db)

    tum, mevcut, devamsiz = server._ogrencileri_ve_yoklamayi_getir("9-A", ders_no=1)
    assert len(tum) == 2
    assert len(mevcut) == 1
    assert len(devamsiz) == 1
    assert mevcut[0]["ad_soyad"] == "Ayşe Yılmaz"
    assert devamsiz[0]["ad_soyad"] == "Mehmet Kaya"


def test_gorsel_sanatlar_esleme_ve_oturum():
    """Görsel Sanatlar ders adı çözümleme ve oyun haritası/oturum entegrasyonu."""
    assert server._ders_anahtari("Görsel Sanatlar") == "gorsel_sanatlar"
    assert server._ders_anahtari("Görsel Sanatlar ve Müzik") == "gorsel_sanatlar"
    
    # Oturum API testi
    res = client.get("/api/arena/oturum?sinif=9-A&ders=Görsel+Sanatlar")
    assert res.status_code == 200
    veri = res.json()
    assert veri["ders_adi"] == "Görsel Sanatlar"
    assert len(veri["sorular"]) == 4

    # HexaFetih harita testi
    import fetih_motoru
    harita = fetih_motoru.haritayi_hazirla("Görsel Sanatlar", 9)
    assert len(harita) == 19







# ---------- Soru hatalı bildirimi (okul portalına köprü) ----------
class _SahteYanit:
    def __init__(self, kod):
        self.status_code = kod


def _sahte_istemci(kod=200, hata=False, kayit=None):
    class _C:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if hata:
                raise server.httpx.ConnectError("kapalı")
            if kayit is not None:
                kayit.append((url, json, headers))
            return _SahteYanit(kod)

    return _C


def test_soru_bildir_anahtarsiz_kapali(monkeypatch):
    monkeypatch.setattr(server, "_okul_soru_anahtari", lambda: "")
    r = client.post("/api/arena/soru-bildir", json={"sid": 5, "tur": "sacma", "sube": "9-A"})
    assert r.status_code == 503 and r.json()["durum"] == "kapali"


def test_soru_bildir_okula_iletir_ve_okul_kapaliysa_bozulmaz(monkeypatch):
    kayit = []
    monkeypatch.setattr(server, "_okul_soru_anahtari", lambda: "k")
    monkeypatch.setattr(server.httpx, "AsyncClient", _sahte_istemci(200, kayit=kayit))
    r = client.post("/api/arena/soru-bildir", json={"sid": 5, "tur": "sacma", "sube": "9-A"})
    assert r.status_code == 200 and r.json() == {"durum": "ok"}
    assert kayit[0][1] == {"soru_id": 5, "tur": "sacma", "sube": "9-A"} and kayit[0][2] == {"X-Soru-Anahtar": "k"}
    monkeypatch.setattr(server.httpx, "AsyncClient", _sahte_istemci(400))
    assert client.post("/api/arena/soru-bildir", json={"sid": 5, "tur": "x", "sube": "9-A"}).status_code == 400
    monkeypatch.setattr(server.httpx, "AsyncClient", _sahte_istemci(hata=True))
    r = client.post("/api/arena/soru-bildir", json={"sid": 5, "tur": "sacma", "sube": "9-A"})
    assert r.status_code == 503 and r.json()["durum"] == "hata"


def test_sayfalar_soru_bildir_betigini_yukler_ve_betik_var():
    for sayfa in ("sinif_arena.html", "hexafetih.html", "duello.html"):
        assert "/static/soru-bildir.js" in (KOK / sayfa).read_text(encoding="utf-8")
    assert client.get("/static/soru-bildir.js").status_code == 200
