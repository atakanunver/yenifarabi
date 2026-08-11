"""
actions/site_goster.py — İzin verilen sitelerden içerik getirip tahtada gösterir.

GÜVENLİK TASARIMI — burada tarayıcı YOK.

Sınıf tahtasında gerçek bir tarayıcı açmak, öğrenciye denetimsiz internet
vermektir: adres çubuğu, bağlantılar, yeni sekme, geri tuşu... hepsi kaçış
yolu. Bu yüzden araç sayfayı bir tarayıcıda açmaz. Yaptığı şu:

  1. İstenen adres beyaz listede mi diye bakar (alan adı bazlı, tam eşleşme
     ya da alt alan adı). Listede değilse hiçbir şey yapmaz.
  2. Sayfayı sunucu tarafında indirir.
  3. Metni ayıklar — menü, reklam, betik, gezinme bağlantıları atılır.
  4. Temiz metni tahtanın içerik paneline basar.

Böylece öğrenci "başka bir siteye gidemez": gidilecek bir tarayıcı yok.
Yan fayda: Vikipedi maddesi reklamsız ve gezinme gürültüsü olmadan
göründüğü için sınıfta okunması gerçek tarayıcıdan daha kolay.

SINIRI: Etkileşimli içerik (simülasyon, video gömülü, GeoGebra) bu yolla
gösterilemez — yalnızca metin ve tablo gelir. Video için `youtube_video` var.

Beyaz listeyi genişletmek: IZINLI_ALANLAR'a alan adı ekle.
"""

import re
from urllib.parse import urlparse, quote

# Alan adı beyaz listesi. Alt alan adları da kabul edilir:
# "tr.wikipedia.org" -> "wikipedia.org" girdisiyle eşleşir.
IZINLI_ALANLAR = {
    # Resmî / müfredat
    "meb.gov.tr",
    "tdk.gov.tr",              # Türk Dil Kurumu
    "sozluk.gov.tr",           # TDK Güncel Türkçe Sözlük (asıl adres)
    "eba.gov.tr",              # Eğitim Bilişim Ağı — alt alan adları da kapsar:
                               # ogmmateryal.eba.gov.tr (MEB resmî ders materyali)
                               # mebi.eba.gov.tr (LGS/YKS konu anlatım videosu,
                               # konu özeti, çıkmış soru — yalnız metin/menü
                               # kısmı gelir, video oynatılamaz, bkz. SINIRI)
    "tubitak.gov.tr",
    "mgm.gov.tr",              # Meteoroloji — coğrafya dersi
    "tuik.gov.tr",             # İstatistik — matematik/coğrafya
    "ataturk.gov.tr",
    # Başvuru kaynakları
    "wikipedia.org",
    "wikimedia.org",
    "islamansiklopedisi.org.tr",
    "ttk.gov.tr",              # Türk Tarih Kurumu
}

MAX_KARAKTER = 6000            # ders_icerigi ile aynı bütçe (~1.500 token)
ZAMAN_ASIMI  = 12

_TEMIZLE = ("script", "style", "nav", "header", "footer", "aside", "form",
            "noscript", "iframe", "button", "svg")


def _alan(url: str) -> str:
    try:
        ana = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return ana[4:] if ana.startswith("www.") else ana


def _izinli(url: str) -> tuple[bool, str]:
    """Alan adı beyaz listede mi? (izin, alan_adı) döndürür."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False, _alan(url)
    alan = _alan(url)
    if not alan:
        return False, ""
    for izinli in IZINLI_ALANLAR:
        if alan == izinli or alan.endswith("." + izinli):
            return True, alan
    return False, alan


def _metin_ayikla(html: str) -> tuple[str, str]:
    """Sayfadan başlık ve okunabilir gövde metnini çıkar."""
    from bs4 import BeautifulSoup
    try:
        çorba = BeautifulSoup(html, "lxml")
    except Exception:
        çorba = BeautifulSoup(html, "html.parser")

    baslik = (çorba.title.get_text(strip=True) if çorba.title else "").strip()

    for etiket in çorba(list(_TEMIZLE)):
        etiket.decompose()
    # Vikipedi'nin düzenleme/kaynak bağlantıları ve dipnot işaretleri
    for sinif in ("mw-editsection", "reference", "navbox", "infobox",
                  "toc", "sidebar", "metadata"):
        for e in çorba.select(f".{sinif}"):
            e.decompose()

    gövde = çorba.find("main") or çorba.find("article") or çorba.body or çorba
    parcalar = []
    for e in gövde.find_all(["h1", "h2", "h3", "p", "li", "caption", "th", "td"]):
        t = e.get_text(" ", strip=True)
        if len(t) < 3:
            continue
        if e.name in ("h1", "h2", "h3"):
            parcalar.append(f"\n## {t}")
        elif e.name == "li":
            parcalar.append(f"- {t}")
        else:
            parcalar.append(t)

    metin = "\n".join(parcalar)
    metin = re.sub(r"\[\d+\]", "", metin)          # [1] dipnot işaretleri
    metin = re.sub(r"\n{3,}", "\n\n", metin)
    return baslik, metin.strip()


def site_goster(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    url   = (p.get("url") or "").strip()
    arama = (p.get("arama") or "").strip()

    # Adres verilmemiş ama arama terimi varsa Vikipedi'de ara
    if not url and arama:
        url = "https://tr.wikipedia.org/wiki/" + quote(arama.replace(" ", "_"))

    if not url:
        return "Gösterilecek bir adres ya da arama terimi belirtilmedi."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    izinli, alan = _izinli(url)
    if not izinli:
        log(f"[Site] REDDEDİLDİ: {alan or url[:40]}")
        return (
            f"'{alan or url}' izin verilen siteler arasında değil, açamam. "
            f"Ders için kullanabileceğim kaynaklar: Vikipedi, TDK sözlüğü, "
            f"MEB, EBA, TÜİK, Meteoroloji, Türk Tarih Kurumu. "
            f"Bu bilgiyi web_search ile arayabilirim."
        )

    log(f"[Site] {alan} açılıyor…")
    try:
        import requests
        yanit = requests.get(
            url,
            timeout=ZAMAN_ASIMI,
            headers={
                # HTTP başlıkları latin-1 ile kodlanır; Türkçe "ı" harfi burada
                # UnicodeEncodeError veriyordu. Başlık ASCII kalmalı.
                "User-Agent": "Farabi/1.0 (school lesson assistant)",
                "Accept-Language": "tr-TR,tr;q=0.9",
            },
            allow_redirects=True,
        )
        # Yönlendirme beyaz listenin dışına çıkmış olabilir — tekrar denetle
        son_izinli, son_alan = _izinli(yanit.url)
        if not son_izinli:
            log(f"[Site] yönlendirme reddedildi: {son_alan}")
            return (f"Adres '{son_alan}' adresine yönlendirdi ve orası izinli "
                    f"listede değil. Açmadım.")
        yanit.raise_for_status()
    except Exception as e:
        return (f"Sayfa açılamadı ({type(e).__name__}). "
                f"Bilgiyi web_search ile arayabilirim.")

    if "html" not in yanit.headers.get("Content-Type", "").lower():
        return "Bu adres bir web sayfası değil, gösteremem."

    baslik, metin = _metin_ayikla(yanit.text)
    if not metin:
        return (f"'{baslik or alan}' sayfasından okunabilir metin çıkaramadım. "
                f"Sayfa büyük olasılıkla etkileşimli içerik barındırıyor.")

    kirpildi = len(metin) > MAX_KARAKTER
    if kirpildi:
        metin = metin[:MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"

    bas = [f"KAYNAK: {baslik or alan}", f"Adres: {yanit.url}"]
    if kirpildi:
        bas.append("Not: sayfa uzun olduğu için kısaltıldı.")
    sonuc = "\n".join(bas) + "\n\n" + metin

    if player is not None and hasattr(player, "show_content"):
        player.show_content(f"🌐 {(baslik or alan)[:40]}", sonuc)
    return sonuc
