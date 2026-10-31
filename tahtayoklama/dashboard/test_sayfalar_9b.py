"""Task 9b: Sistem alanı sayfaları (tahtalar, sistem durumu, servisler, zamanlanmış görevler, sunucular)
yeni tasarımda: eski sınıf yok (işaretleme + JS dizgeleri), JS'in aradığı kimlik/kanca/uç duruyor, BÜYÜK HARF yazı yok.
Şablonlar DB'siz, doğrudan render edilir (httpx yok → TestClient yok)."""
import re
import unittest
from pathlib import Path

from starlette.requests import Request

import app as uygulama

DIZIN = Path(__file__).resolve().parent
SABLONLAR = DIZIN / "templates"
ESKI = re.compile(
    r"(btn-ikincil|btn-birincil|btn-kucuk|yeni-form|admin-tablo|pill(?:-[a-z]+)?|pano-ozet(?:-[a-z]+)?|kenar-oge|"
    r"kenar-alt-oge|etiket|etiket-uyari|rapor-aciklama|tablo-sarici|kpi(?:-[a-z]+)?|form-kutu|filtre-bar|"
    r"kr-bos(?:-baslik)?|durum-ozet(?:-[a-z]+)?|sorun-[a-z]+|form-grup|form-etiket|form-secim|form-girdi|"
    r"servis-tablo(?:-sarici)?|servis-zaman-tablo|bolum-baslik|ss-link-btn|ss-link-pasif|uz-secim-cubugu|uz-tehlike|"
    r"sunucu-dugme(?:-[a-z]+)?|sunucu-yenile|sunucu-rozet|durum-rozet|durum-kart(?:-[a-z]+)?|saglik-kutu|"
    r"model-rozet(?:-listesi)?|uyari-not|mini-ok|sinif-etiket|son-guncelleme-etiket|"
    r"sunucu-olcum(?:-deger)?|bilgi-kart)")

SAYFALAR = ("uzaktan_yonetim.html", "sistem_durumu.html", "servisler.html", "zamanlanmis_gorevler.html",
            "sunucular.html")

# şablon -> sayfa JS'inin ve testlerin aradığı kimlik / kanca / uç parçaları
KIMLIKLER = {
    "uzaktan_yonetim.html": [
        'id="tahta-secim"', 'id="uzaktan-tablo"', 'id="tumunu-sec"', 'id="secimi-kaldir"', 'id="durum-yenile-btn"',
        'id="son-guncelleme-uzaktan"', 'id="duyuru"', 'id="duyuru-form"', 'name="tum_okul"', 'name="sesli_oku"',
        'name="mesaj"', 'name="tip"', 'id="canli-ekranlar"', 'id="canli-bilgi"', 'id="sag-menu"', 'id="sag-menu-baslik"',
        'data-yol="yeniden-baslat"', 'data-yol="duvar-kagidi"', 'data-onay=', 'id="sonuc-alani"', 'duyuru-ekle-btn',
        'data-tahta=', 'class="hucre-baglanti', 'class="hucre-oturum', 'class="hucre-yoklama', 'class="hucre-chrome',
        'class="hucre-ekran', 'class="hucre-ss', 'class="hucre-sistem', 'id="satir-',
        "querySelectorAll('.uz-eylem-form')", "classList.contains('uz-genel-form')", "confirm(form.dataset.onay)",
        "/admin/uzaktan/api/durumlar", "closest('.duyuru-ekle-btn')", "closest('.canli-kart')",
        "/admin/uzaktan/ekran-goruntusu/", "confirm(`${ad}",
    ],
    "sistem_durumu.html": [
        'id="son-guncelleme-durum"', 'id="saglik-ozet"', 'id="durum-izgara"', 'id="gpu-izgara"',
        'id="servis-tablo-govde"', 'id="tahta-tablo-govde"', 'id="uzak-listesi"', 'id="ai-kart"', 'id="db-kart"',
        'id="rag-kart"', 'id="trend-izgara"', 'id="model-listesi"', 'id="trend-ipucu"', 'id="kart-bellek"',
        'id="deger-cpu"', 'id="alt-cpu"', 'id="deger-cpu-kullanim"', 'id="alt-cpu-kullanim"', 'id="deger-bellek"',
        'id="alt-bellek"', 'id="deger-disk"', 'id="alt-disk"', 'id="deger-diskio"', 'id="alt-diskio"',
        'id="deger-calisma"', 'id="alt-calisma"', "/api/sistem-durumu?trend=1", "closest('.trend-svg')",
        "data-noktalar", "trend-imlec", "setInterval(durumGuncelle, 15000)",
    ],
    "servisler.html": [
        'id="yenile"', 'id="servis-kartlari"', 'id="zamanlayicilar"', 'id="zamanlayicilar-baslik"',
        'id="ders-saati-rozeti"', 'id="sh-durum"', 'id="sh-kapsam"', 'id="log-paneli"', 'id="log-baslik"',
        'id="log-uyari"', 'id="log-kopyala"', 'id="log-kapat"', 'id="log-son-hata"', 'id="log-icerik"',
        'id="onay-penceresi"', 'id="onay-baslik"', 'id="onay-metin"', 'id="onay-uyari"', 'id="onay-evet"',
        "<span></span>", "'/api/servisler/eylem'", "'/api/servisler/log/'", "fetch('/api/servisler')",
        "method: 'POST'", "birim: b.birim, eylem: eylem, onay: onay", "x.s === 409", "onayAc(", "setInterval(",
    ],
    "zamanlanmis_gorevler.html": [
        'id="yenile"', 'id="gorev-ekle"', 'id="farabi-tablo"', 'id="panel-tablo"', 'id="tahta-tablo"',
        'id="sistem-tablo"', 'id="ders-saati-rozeti"', 'id="onay-penceresi"', 'id="onay-metin"', 'id="onay-uyari"',
        'id="onay-evet"', 'id="form-penceresi"', 'id="form-baslik"', 'id="gorev-form"', 'id="alan-ad"',
        'id="alan-sablon"', 'id="alan-tahta"', 'id="f-ad"', 'id="f-sablon"', 'id="f-hepsi"', 'id="f-tahtalar"',
        'id="f-gunler"', 'id="f-saat"', 'id="f-ifade"', 'id="f-hata"', 'id="f-vazgec"', 'id="f-kaydet"',
        "/zamanlanmis-gorevler/api/liste", "/zamanlanmis-gorevler/api/tahtalar", "/zamanlanmis-gorevler/api/eylem",
        "method: 'POST'", "x.s === 409", "onayAc(",
    ],
    "sunucular.html": [
        'id="yenile-dugme"', 'id="son-guncelleme-durum"', 'id="sunucu-listesi"', 'id="ozel-listesi"',
        "/api/sunucular", "/proxy`", "data-makine", ".sunucu-proxy", "dataset.makine", "method: 'POST'",
        "setInterval(", "classList.add('gizli')",
    ],
}

# Kısaltma olarak meşru, büyük harfle yazılan sözcükler
KISALTMA = {"EBYS", "HTTP", "VRAM", "JSON", "POST", "NTP", "SQL", "TCP", "OnCalendar"}
BUYUK = re.compile(r"\b[A-ZÇĞİÖŞÜ]{4,}\b")


def _istek(yol):
    return Request({"type": "http", "method": "GET", "path": yol, "headers": [], "query_string": b"",
                    "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})


def _render(ad, **baglam):
    return uygulama.templates.env.get_template(ad).render(request=_istek("/x"), **baglam)


def _uzaktan(yukleniyor, sonuclar):
    def t(ad, ulasilabilir, **ek):
        d = {"ad": ad, "ip": "10.0.0.1", "ulasilabilir": ulasilabilir, "oturum": "acik", "yoklama": True,
             "chrome": False, "karartildi": True, "cpu": "i5", "ram_gb": 8}
        d.update(ek)
        return d
    tahtalar = [t("9-A", None), t("10-A", True), t("11-A", False, oturum="kilitli", cpu=None),
                t("12-A", True, oturum="giris_ekrani"), t("12-B", True, oturum="bilinmiyor")]
    return _render("uzaktan_yonetim.html", tahtalar=tahtalar, yukleniyor=yukleniyor, sonuclar=sonuclar)


def _tum_cikti(ad):
    if ad == "uzaktan_yonetim.html":
        sonuclar = [{"tahta": "10-A", "basarili": True, "detay": "yapıldı"},
                    {"tahta": None, "basarili": False, "detay": "Hiçbir tahta seçilmedi."}]
        return _uzaktan(True, None) + _uzaktan(False, sonuclar)
    return _render(ad)


def _gorunen_yazi(html):
    """Betik dışı görünen metin + data-onay/title/placeholder/aria-label değerleri."""
    govde = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL)
    nitelik = re.findall(r'(?:data-onay|title|placeholder|aria-label)="([^"]*)"', govde)
    return re.sub(r"<[^>]+>", " ", govde) + " " + " ".join(nitelik)


def _betik_dizgeleri(html):
    """<script> içindeki tırnaklı dizgelerin etiketsiz, ${} içermeyen metni."""
    out = []
    for betik in re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL):
        for g in re.findall(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`([^`]*)`", betik):
            m = next(x for x in g if x is not None) if any(x is not None for x in g) else ""
            m = re.sub(r"\$\{.*?\}", " ", m)
            out.append(re.sub(r"<[^>]+>", " ", m))
    return out


class TestSayfalar9b(unittest.TestCase):
    def test_eski_sinif_yok(self):
        for ad in SAYFALAR:
            ham = (SABLONLAR / ad).read_text(encoding="utf-8")
            kullanilan = []
            for kume in re.findall(r'class="([^"]*)"', re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", ham, flags=re.DOTALL)):
                kullanilan += [s for s in kume.split() if ESKI.fullmatch(s)]
            # tırnaklı her dizge (JS sınıf adları, Jinja sözlük değerleri): sınıf listesi gibi ayrıştırılır
            for g in re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"", ham):
                for parca in "".join(g).split():
                    if ESKI.fullmatch(parca):
                        kullanilan.append(parca)
            self.assertEqual(kullanilan, [], ad)

    def test_render_eski_sinif_yok(self):
        for ad in SAYFALAR:
            html = _tum_cikti(ad)
            kullanilan = [s for k in re.findall(r'class="([^"]*)"', html) for s in k.split() if ESKI.fullmatch(s)]
            self.assertEqual(kullanilan, [], ad)

    def test_kimlikler_ve_kancalar_duruyor(self):
        for ad, parcalar in KIMLIKLER.items():
            metin = (SABLONLAR / ad).read_text(encoding="utf-8") + _tum_cikti(ad)
            for p in parcalar:
                self.assertIn(p, metin, f"{ad}: {p}")

    def test_uzaktan_her_post_formu_kancali(self):
        """Fiziksel tahtaya giden her form uz-eylem-form kancasını taşımalı (seçim + onay JS'i buna bağlı)."""
        html = _uzaktan(False, None)
        formlar = re.findall(r"<form\b[^>]*>", html)
        post = [f for f in formlar if 'method="post"' in f and "/admin/uzaktan/" in f]
        self.assertGreaterEqual(len(post), 10)
        for f in post:
            self.assertRegex(f, r'class="[^"]*\buz-eylem-form\b', f)
        yb = [f for f in post if "/yeniden-baslat" in f]
        self.assertEqual(len(yb), 1)
        self.assertIn("data-onay=", yb[0])
        gk = [f for f in post if "/duyuru-kapat" in f]
        self.assertIn("uz-genel-form", gk[0])
        for ek in ("yoklama-ac", "yoklama-kapat", "web-ac", "chrome-kapat", "ekran-karart", "ekran-kaldir",
                   "duvar-kagidi", "yeniden-baslat", "duyuru", "duyuru-kapat"):
            self.assertTrue(any(f'action="/admin/uzaktan/{ek}"' in f for f in post), ek)

    def test_buyuk_harf_yazi_yok(self):
        for ad in SAYFALAR:
            html = _tum_cikti(ad)
            self.assertNotIn("text-transform", html, ad)
            yazilar = [_gorunen_yazi(html)] + _betik_dizgeleri(html)
            for y in yazilar:
                y = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", y)
                bulunan = [b for b in BUYUK.findall(y) if b not in KISALTMA]
                self.assertEqual(bulunan, [], f"{ad}: {y[:80]}")

    def test_satir_ici_stil_ham_renk_yok(self):
        for ad in SAYFALAR:
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", metin), ad)
            self.assertNotIn("rgba(", metin, ad)

    def test_basliklar_cumle_duzeni(self):
        for ad in SAYFALAR:
            metin = (SABLONLAR / ad).read_text(encoding="utf-8")
            for etiket in re.findall(r"\{% block (?:baslik|baslik_etiketi) %\}(.*?)\{% endblock %\}", metin):
                baslik = etiket.split("—")[0].strip()
                kelimeler = baslik.split()
                self.assertFalse(any(k[:1].isupper() for k in kelimeler[1:]), f"{ad}: {baslik}")


if __name__ == "__main__":
    unittest.main()
