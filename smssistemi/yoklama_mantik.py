"""Yoklama SMS modülü için iş mantığı — saf fonksiyonlar, ağ/thread yok.
`dogum_mantik.py` ile aynı deseni izler: `conn` parametre olarak alınır,
düz dict döner, şablon yalnızca dönen sözlüğü okur.

Yaptığı iş: panonun ders-ders tuttuğu yoklama kayıtlarını (`yoklama_kaynak`)
gün bazında toplayıp "bugün en az N derste yok" olan öğrencileri bulmak, her
birini rehberdeki öğrenci kaydıyla ve onun telefonlu velileriyle eşleştirmek.

Kritik kurallar (hepsi `test_yoklama_mantik.py`'de sınanır):

1. **Yalnızca `durum='alindi'` satırlar sayılır** — hem pay (yok olunan ders)
   hem payda (yoklaması alınan ders). Panonun `yoklayici.py:126`'sı diğer tüm
   durumlarda isim dizilerini BOŞ yazdığı için, 'alinmadi' bir satırı "kimse
   yok değil" sanmak sessiz ve tehlikeli bir hata olurdu.
2. **Hiç `alindi` satırı olmayan sınıf listeden ÇIKARILIR** ve sebebiyle
   `haric_siniflar`'a yazılır. 12-A'nın 2026-09-22'de DHCP kirası bozulunca
   4-8. derslerde `tahta_ulasilamaz` olması tam bu vakadır — o gün o sınıfın
   tüm öğrencilerine "okula gelmedi" SMS'i gitmesi kabul edilemez.
3. **İzinli ders "yok" sayılmaz.** Gün içinde bir kez bile izinli görünen
   öğrenci `izinli_mi` ile işaretlenir ve arayüzde varsayılan SEÇİLİ GELMEZ.
4. **Eşleşmeyen isim sessizce düşürülmez.** Panonun roster'ında numarası
   bulunamayan öğrenci için `yoklayici.py:56` literal `"No 17"` yazar; bu ve
   rehberde karşılığı olmayan isimler `eslesmedi` olarak listede kalır.
5. **Telefonlu velisi olmayan öğrenci `telefonsuz` olarak listelenir**, alıcı
   sayılmaz (kullanıcı kararı: "veli telefonu yoktur desin pas geçsin").
"""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import db
import yoklama_kaynak

_ISTANBUL = ZoneInfo("Europe/Istanbul")

# Kullanıcı kararı (2026-09-23): "bugün en az N derste yok" — varsayılan 4
# (yarım günü aşan devamsızlık), sayfadan değiştirilebilir. 1. derse göre
# karar vermek geç gelen öğrencinin velisine yanlış SMS gönderirdi.
ESIK_VARSAYILAN = 4
ESIK_MIN = 1
ESIK_MAX = 8

AYAR_SABLON = "yoklama_sms_sablonu"
SABLON_VARSAYILAN = "Sayın {isim}, öğrenciniz {ogrenci_adi} bugün derslere katılmamıştır. Bilginize."

# Panonun roster'ında numarası çözülemeyen öğrenci için ürettiği yedek isim
# (`tahtayoklama/dashboard/yoklayici.py:56`) — gerçek bir ada asla eşleşmez.
_COZULMEMIS_ISIM_RE = re.compile(r"^No\s+\d+$")

_DURUM_ACIKLAMA = {
    "alinmadi": "Yoklama alınmamış",
    "tahta_ulasilamaz": "Tahta ulaşılamadı",
    "henuz_baslamadi": "Dersler henüz başlamadı",
    "tahta_atanmamis": "Sınıfa tahta atanmamış",
    "ders_yok_o_gun": "O gün ders yok",
    "veri_yok": "Panoda bugüne ait kayıt yok",
}

# Eşleşme durumları — şablon bunlara göre rozet basar.
ESLESME_TAMAM = "tamam"
ESLESME_TELEFONSUZ = "telefonsuz"
ESLESME_YOK = "eslesmedi"


def bugun_istanbul() -> date:
    """Gün sınırı İstanbul saatine göre — sunucu UTC koşuyor, `date.today()`
    gece yarısından sonra bir önceki günü verebilirdi."""
    return datetime.now(_ISTANBUL).date()


def esigi_sinirla(esik) -> int:
    """Query parametresinden gelen eşiği güvenli aralığa çeker."""
    try:
        deger = int(esik)
    except (TypeError, ValueError):
        return ESIK_VARSAYILAN
    return max(ESIK_MIN, min(ESIK_MAX, deger))


def sablonu_oku(conn) -> str:
    return db.ayar_oku(conn, AYAR_SABLON) or SABLON_VARSAYILAN


def _sinif_ozetleri(satirlar: list[dict]) -> tuple[dict, list[dict]]:
    """Ders satırlarını sınıf bazında toplar.

    Döner: (`dahil`, `haric`) — `dahil` yalnızca en az bir 'alindi' dersi olan
    sınıfları içerir: {sinif: {"alinan": n, "yok": {isim: adet},
    "izinli": {isim}}}. `haric` ise sebebiyle birlikte dışarıda bırakılanlar.
    """
    toplam: dict[str, dict] = {}
    for satir in satirlar:
        sinif = satir["sinif"]
        girdi = toplam.setdefault(
            sinif, {"alinan": 0, "yok": {}, "izinli": set(), "durumlar": {}}
        )
        durum = satir["durum"]
        if durum != yoklama_kaynak.DURUM_ALINDI:
            # Sebep raporlayabilmek için hangi durumun kaç kez geçtiğini say.
            girdi["durumlar"][durum] = girdi["durumlar"].get(durum, 0) + 1
            continue
        girdi["alinan"] += 1
        # Aynı derste hem yok hem izinli görünemez; izinli önceliklidir
        # (kural 3) — izinli ders "yok" sayılmaz.
        izinliler = set(satir["izinli_isimleri"])
        girdi["izinli"].update(izinliler)
        for isim in satir["yok_isimleri"]:
            if isim in izinliler:
                continue
            girdi["yok"][isim] = girdi["yok"].get(isim, 0) + 1

    dahil = {s: v for s, v in toplam.items() if v["alinan"] > 0}
    haric = []
    for sinif, v in sorted(toplam.items(), key=lambda kv: db._sinif_sira_anahtari(kv[0])):
        if v["alinan"] > 0:
            continue
        # En çok tekrar eden durum sebep olarak gösterilir.
        sebep = max(v["durumlar"].items(), key=lambda kv: kv[1])[0] if v["durumlar"] else "veri_yok"
        haric.append(
            {
                "sinif": sinif,
                "sebep": sebep,
                "aciklama": _DURUM_ACIKLAMA.get(sebep, sebep),
                "ders_sayisi": sum(v["durumlar"].values()),
            }
        )
    return dahil, haric


def _kayitsiz_siniflar(conn, gorulen: set[str]) -> list[dict]:
    """Rehberde gerçek bir sınıf olarak duran ama panoda bugüne ait HİÇ
    satırı olmayan sınıflar. Sessizce yok saymak yerine uyarıya yazılır —
    bir sınıfın panodan tamamen düşmesi de bir arıza belirtisidir.
    ('Personel' / 'Bilinmeyen Sınıf' sahte satırları regex'e takılmaz.)"""
    eksik = []
    for sinif in db.siniflar_listele(conn):
        ad = sinif["ad"]
        if db._SINIF_AD_RE.match(ad) and ad not in gorulen:
            eksik.append(
                {
                    "sinif": ad,
                    "sebep": "veri_yok",
                    "aciklama": _DURUM_ACIKLAMA["veri_yok"],
                    "ders_sayisi": 0,
                }
            )
    return eksik


def _ogrenciyi_eslestir(
    conn, ad_soyad: str, sinif_id: int | None, sinif_adi_ile: dict[int, str]
) -> tuple[str, dict | None, list[dict], str | None]:
    """İsim → rehberdeki öğrenci → telefonlu veliler.
    Döner: (eslesme_durumu, ogrenci|None, veliler, not).

    Eşleştirme SINIF KAPSAMLIDIR ve bilinçli olarak öyle kalır: aynı ad iki
    farklı sınıfta bulunabilir, sınıfsız eşleştirme yanlış ailenin telefonuna
    SMS gönderme riski taşır. Ama isim başka bir sınıfta bulunuyorsa bu bir
    veri uyuşmazlığı belirtisidir (öğrenci sınıf değiştirmiş, bir taraftaki
    liste bayat) — SMS yine gönderilmez, fakat sebep `not` alanında
    kullanıcıya söylenir. 2026-09-23'te canlı veride gerçekten bulundu:
    panoda 11-A görünen bir öğrenci rehberde 11-B kayıtlıydı."""
    if _COZULMEMIS_ISIM_RE.match(ad_soyad.strip()):
        return ESLESME_YOK, None, [], "Panoda öğrenci numarası çözülememiş"
    if sinif_id is None:
        return ESLESME_YOK, None, [], "Bu sınıf rehberde kayıtlı değil"
    # `kisi_bul_isimle` SQL içinde tr_norm() kullanır — Türkçe İ/I ve boşluk
    # farkları burada zaten tolere edilir (db.py:315).
    ogrenci = db.kisi_bul_isimle(conn, ad_soyad, sinif_id, "ogrenci")
    if ogrenci is None:
        baska = db.kisi_bul_isimle_sinifsiz(conn, ad_soyad, "ogrenci")
        if baska is not None:
            baska_sinif = sinif_adi_ile.get(baska["sinif_id"], "?")
            return ESLESME_YOK, None, [], f"Rehberde {baska_sinif} sınıfında kayıtlı"
        return ESLESME_YOK, None, [], "Rehberde bu isimde öğrenci yok"
    veliler = db.veliler_ogrenci_ile(conn, ogrenci["id"])
    if not veliler:
        return ESLESME_TELEFONSUZ, ogrenci, [], None
    return ESLESME_TAMAM, ogrenci, veliler, None


def devamsiz_ozet(conn, tarih: str | None = None, esik: int = ESIK_VARSAYILAN) -> dict:
    """Sayfanın okuduğu tek yapı. `yoklama_kaynak.YoklamaKaynakYok` fırlatabilir."""
    hedef_tarih = tarih or bugun_istanbul().isoformat()
    esik = esigi_sinirla(esik)

    satirlar = yoklama_kaynak.gunun_satirlari(hedef_tarih)
    dahil, haric = _sinif_ozetleri(satirlar)
    haric += _kayitsiz_siniflar(conn, set(dahil) | {h["sinif"] for h in haric})
    haric.sort(key=lambda h: db._sinif_sira_anahtari(h["sinif"]))

    siniflar = db.siniflar_listele(conn)
    sinif_id_ile = {s["ad"]: s["id"] for s in siniflar}
    sinif_adi_ile = {s["id"]: s["ad"] for s in siniflar}

    ogrenciler = []
    for sinif in sorted(dahil, key=db._sinif_sira_anahtari):
        veri = dahil[sinif]
        for ad_soyad, yok_sayisi in veri["yok"].items():
            if yok_sayisi < esik:
                continue
            durum, ogrenci, veliler, not_metni = _ogrenciyi_eslestir(
                conn, ad_soyad, sinif_id_ile.get(sinif), sinif_adi_ile
            )
            ogrenciler.append(
                {
                    "sinif": sinif,
                    "ad_soyad": ad_soyad,
                    "yok_sayisi": yok_sayisi,
                    "alinan_sayisi": veri["alinan"],
                    "izinli_mi": ad_soyad in veri["izinli"],
                    "eslesme_durumu": durum,
                    "eslesme_notu": not_metni,
                    "ogrenci_kisi_id": ogrenci["id"] if ogrenci else None,
                    "veliler": veliler,
                }
            )

    ogrenciler.sort(key=lambda o: (db._sinif_sira_anahtari(o["sinif"]), -o["yok_sayisi"], o["ad_soyad"]))

    ulasilabilir = [o for o in ogrenciler if o["eslesme_durumu"] == ESLESME_TAMAM]
    return {
        "tarih": hedef_tarih,
        "bugun_mu": hedef_tarih == bugun_istanbul().isoformat(),
        "esik": esik,
        "sablon": sablonu_oku(conn),
        "ogrenciler": ogrenciler,
        "haric_siniflar": haric,
        "dahil_sinif_sayisi": len(dahil),
        "devamsiz_sayisi": len(ogrenciler),
        "ulasilabilir_sayisi": len(ulasilabilir),
        "veli_sayisi": sum(len(o["veliler"]) for o in ulasilabilir),
        "telefonsuz_sayisi": sum(
            1 for o in ogrenciler if o["eslesme_durumu"] == ESLESME_TELEFONSUZ
        ),
        "eslesmeyen_sayisi": sum(1 for o in ogrenciler if o["eslesme_durumu"] == ESLESME_YOK),
        "izinli_sayisi": sum(1 for o in ogrenciler if o["izinli_mi"]),
    }
