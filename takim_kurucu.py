"""takim_kurucu.py - Sınıf Arenası Dengeli Takım ve Tematik İsim Oluşturucu.

Sınıf mevcudunu ve cinsiyet oranını (kız/erkek) eşit dağıtarak 2, 3 veya 4 takım
oluşturur. Ders adına göre eğlenceli ve tematik takım isimleri atar.
"""

import random
from typing import Any

# Ders adına göre tematik takım isimleri
TEMATIK_TAKIMLAR: dict[str, list[dict[str, str]]] = {
    "biyoloji": [
        {"name": "Mitokondriler", "slogan": "Hücrenin Güç Santrali!"},
        {"name": "Ribozomlar", "slogan": "Protein Fabrikası!"},
        {"name": "DNA Kaşifleri", "slogan": "Genetik Kodun Bekçileri!"},
        {"name": "Kloroplastlar", "slogan": "Güneşin Enerjisi!"},
    ],
    "kimya": [
        {"name": "Katalizörler", "slogan": "Tepkimeyi Hızlandıranlar!"},
        {"name": "Kovalentler", "slogan": "Kırılmaz Bağlar!"},
        {"name": "Reaktifler", "slogan": "Dinamik Moleküller!"},
        {"name": "Asit-Bazlar", "slogan": "Nötrleşme Şampiyonları!"},
    ],
    "fizik": [
        {"name": "Kuantumlar", "slogan": "Olasılıkların Efendisi!"},
        {"name": "Fotonlar", "slogan": "Işık Hızında!"},
        {"name": "Manyetikler", "slogan": "Çekim Gücümüz Yüksek!"},
        {"name": "İvmeciler", "slogan": "Hızımıza Yetişilemez!"},
    ],
    "matematik": [
        {"name": "Asal Güçler", "slogan": "Sadece Kendine ve 1'e Bölünenler!"},
        {"name": "Fibonacci Çetesi", "slogan": "Altın Oran Bizimle!"},
        {"name": "Pi Fatihleri", "slogan": "Sonsuz Basamaklı Zeka!"},
        {"name": "Matrisler", "slogan": "Boyutların Hakimi!"},
    ],
    "tarih": [
        {"name": "Akıncılar", "slogan": "Tarihe Yön Verenler!"},
        {"name": "Fatihler", "slogan": "Girdiği Çağı Değiştirenler!"},
        {"name": "Leventler", "slogan": "Denizlerin Fırtınası!"},
        {"name": "Nizamlar", "slogan": "Düzen ve Zafer!"},
    ],
    "türk dili ve edebiyatı": [
        {"name": "Hececiler", "slogan": "Milli Ölçünün Şairleri!"},
        {"name": "Divan Şairleri", "slogan": "Aruzun Zirvesi!"},
        {"name": "Mürekkep Balıkları", "slogan": "Kelamın Gücü!"},
        {"name": "Roman Kahramanları", "slogan": "Unutulmaz Karakterler!"},
    ],
    "coğrafya": [
        {"name": "Meridyenler", "slogan": "Zamanın Efendileri!"},
        {"name": "Musonlar", "slogan": "Doğanın Büyük Gücü!"},
        {"name": "Tektonikler", "slogan": "Yeri Göğü Sarsanlar!"},
        {"name": "Kutup Yıldızları", "slogan": "Yol Gösteren Işık!"},
    ],
    "felsefe": [
        {"name": "Sokratikler", "slogan": "Sorgulanmamış Hayat Yaşanmaya Değmez!"},
        {"name": "Akılcılar", "slogan": "Düşünüyorum Öyleyse Varım!"},
        {"name": "Diyalektikler", "slogan": "Tez, Antitez, Sentez!"},
        {"name": "Filozoflar", "slogan": "Hikmet Arayışçıları!"},
    ],
    "ingilizce": [
        {"name": "Pioneers", "slogan": "Leading the Way!"},
        {"name": "Voyagers", "slogan": "Exploring New Horizons!"},
        {"name": "Pathfinders", "slogan": "Making Our Own Path!"},
        {"name": "Innovators", "slogan": "Thinking Out of the Box!"},
    ],
    "din kültürü ve ahlak bilgisi": [
        {"name": "Hikmetler", "slogan": "Doğruluk ve İrfan!"},
        {"name": "Erdemliler", "slogan": "Güzellikte Yarışanlar!"},
        {"name": "Kandiller", "slogan": "Karanlığı Aydınlatanlar!"},
        {"name": "Adaletliler", "slogan": "Hakkın ve Dürüstlüğün Temsilcileri!"},
    ],
    "bilişim": [
        {"name": "Algoritmalar", "slogan": "Mantığın ve Kodun Gücü!"},
        {"name": "Siber Savunucular", "slogan": "Güvenliğin Mimarları!"},
        {"name": "Yapay Zekalar", "slogan": "Geleceği Şekillendirenler!"},
        {"name": "Kriptocular", "slogan": "Kırılmaz Şifreler!"},
    ],
    "sağlık": [
        {"name": "Şampiyonlar", "slogan": "Zirveye Koşanlar!"},
        {"name": "Dinamikler", "slogan": "Güç, Çeviklik ve Hız!"},
        {"name": "Can Kurtaranlar", "slogan": "İlk Yardım ve Hayat!"},
        {"name": "Maratoncular", "slogan": "Yorulmak Bilmeyenler!"},
    ],
    "beden eğitimi": [
        {"name": "Olimpiyatlar", "slogan": "Daha Hızlı, Daha Yüksek, Daha Güçlü!"},
        {"name": "Fırtınalar", "slogan": "Sahaların Hakimi!"},
        {"name": "Atletler", "slogan": "Disiplin ve Dayanıklılık!"},
        {"name": "Kaptanlar", "slogan": "Takım Ruhu Bizimle!"},
    ],
    "görsel sanatlar": [
        {"name": "Rönesanslar", "slogan": "Sanatın ve Ustalığın Zirvesi!"},
        {"name": "Renk Ustaları", "slogan": "Dünyayı Boyayanlar!"},
        {"name": "Hezarfenler", "slogan": "Yaratıcı Zihinler!"},
        {"name": "Perspektifler", "slogan": "Derinliğin Kaşifleri!"},
    ],
    "müzik": [
        {"name": "Armoniler", "slogan": "Notaların Kusursuz Uyumu!"},
        {"name": "Virtüözler", "slogan": "Sahnelerin Efendisi!"},
        {"name": "Ritimler", "slogan": "Müziğin Kalp Atışı!"},
        {"name": "Solfejler", "slogan": "Sesin Büyüsü!"},
    ],
    "genel": [
        {"name": "Bilge Fatihler", "slogan": "Merak Eden Kazanır!"},
        {"name": "Kaşifler", "slogan": "Bilinmeyeni Arayanlar!"},
        {"name": "Dehalar", "slogan": "Zekanın Zirvesi!"},
        {"name": "Yıldızlar", "slogan": "Işığıyla Parlayanlar!"},
    ],
}

VARSAYILAN_TAKIMLAR = [
    {"name": "Kırmızı Ejderler", "slogan": "Ateşli ve Kararlı!"},
    {"name": "Mavi Şimşekler", "slogan": "Hızlı ve Keskin!"},
    {"name": "Yeşil Kartallar", "slogan": "Göklerin Hakimi!"},
    {"name": "Sarı Kaplanlar", "slogan": "Atik ve Cesur!"},
]

TAKIM_RENKLERI = [
    {
        "id": 1,
        "color": "from-rose-500 to-red-600",
        "borderColor": "border-rose-500",
        "textColor": "text-rose-400",
        "bgBadge": "bg-rose-500/20",
    },
    {
        "id": 2,
        "color": "from-blue-500 to-indigo-600",
        "borderColor": "border-blue-500",
        "textColor": "text-blue-400",
        "bgBadge": "bg-blue-500/20",
    },
    {
        "id": 3,
        "color": "from-emerald-500 to-green-600",
        "borderColor": "border-emerald-500",
        "textColor": "text-emerald-400",
        "bgBadge": "bg-emerald-500/20",
    },
    {
        "id": 4,
        "color": "from-amber-500 to-yellow-600",
        "borderColor": "border-amber-500",
        "textColor": "text-amber-400",
        "bgBadge": "bg-amber-500/20",
    },
]


def normalize_ders_adi(s: str) -> str:
    if not s:
        return ""
    return s.replace("İ", "i").replace("I", "ı").lower().strip()


def _ders_anahtari(ders_adi: str) -> str:
    """Türkçe karakterleri ve boşlukları normalleştirir."""
    temiz = normalize_ders_adi(ders_adi)
    for k in TEMATIK_TAKIMLAR:
        k_norm = normalize_ders_adi(k)
        if k_norm in temiz or temiz in k_norm:
            return k
    return "varsayilan"


def takim_isimleri_getir(ders_adi: str, adet: int = 4) -> list[dict[str, str]]:
    k = _ders_anahtari(ders_adi)
    havuz = TEMATIK_TAKIMLAR.get(k, VARSAYILAN_TAKIMLAR)
    secilen = havuz[:adet]
    while len(secilen) < adet:
        idx = len(secilen)
        secilen.append(VARSAYILAN_TAKIMLAR[idx % len(VARSAYILAN_TAKIMLAR)])
    return secilen


def takimlari_olustur(
    ogrenciler: list[dict[str, Any]],
    ders_adi: str = "",
    takim_sayisi: int = 4,
) -> list[dict[str, Any]]:
    """Mevcut öğrencileri cinsiyet ve kişi sayısı eşit olacak şekilde takımlara böler."""
    takim_sayisi = max(2, min(4, takim_sayisi))
    isimler = takim_isimleri_getir(ders_adi, takim_sayisi)

    # Takım iskeletleri
    takimlar: list[dict[str, Any]] = []
    for i in range(takim_sayisi):
        stil = TAKIM_RENKLERI[i]
        meta = isimler[i]
        takimlar.append({
            "id": stil["id"],
            "name": meta["name"],
            "isim": meta["name"],
            "slogan": meta.get("slogan", ""),
            "color": stil["color"],
            "borderColor": stil["borderColor"],
            "textColor": stil["textColor"],
            "bgBadge": stil["bgBadge"],
            "score": 0,
            "ogrenciler": [],
        })

    # Cinsiyetlere göre grupla ve karıştır
    kizlar = [o for o in ogrenciler if str(o.get("cinsiyet", "")).lower().startswith("k")]
    erkekler = [o for o in ogrenciler if not str(o.get("cinsiyet", "")).lower().startswith("k")]

    random.shuffle(kizlar)
    random.shuffle(erkekler)

    # Kızları dengeli dağıt
    for idx, kiz in enumerate(kizlar):
        takim_idx = idx % takim_sayisi
        takimlar[takim_idx]["ogrenciler"].append(kiz)

    # Erkekleri dengeli dağıt (ters yönden veya offsetli başlayarak sayı dengesini korur)
    offset = len(kizlar) % takim_sayisi
    for idx, erkek in enumerate(erkekler):
        takim_idx = (idx + offset) % takim_sayisi
        takimlar[takim_idx]["ogrenciler"].append(erkek)

    # Her takımdaki öğrencileri numaralarına göre sırala
    for t in takimlar:
        t["ogrenciler"].sort(key=lambda o: o.get("no", 0))

    return takimlar
