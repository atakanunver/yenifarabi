"""Okul bilgisi JSON API'si (/api/okul/*) — Open WebUI "Okul Bilgisi" aracı ve
Farabi kaynak filtresi için (2026-10-04).

- /simdi: Türkiye saatiyle tarih/gün/saat + o anki ders saati/teneffüs (zil.json).
  Filtre her sohbet mesajına bunu ekler (model tarihi uydurmasın).
- /ders-programi: sınıf → şu anki ders / bugün / belirli gün / hafta
  (data/ders_programi.json + zil.json; DB'deki ders_programi tablosu boş).
  Ders programı verisinde öğretmen adı YOK (öğretmen→ders eşlemesi /ogretmen'den).
- /ogrenci: panonun güncel sınıf listesinden (`ogrenciler` tablosu) no + ad soyad + sınıf.
  KVKK: yalnızca okul.json::ogrenci_izinli e-postaları ve Open WebUI admin
  rolü (kullanıcı kararı 2026-10-04: İdare + Öğretmen; tahta hesabı HARİÇ).
  Araç da aynı kontrolü yapar; burası ikinci kapı. Öğrenci adları loga YAZILMAZ.
- /ogretmen: config/ogretmenler.json (scripts/ogretmen_listesi_uret.py, gitignore'lu)
  → ad soyad, verdiği ders kısaltmaları, sınıflar. Aynı izin kuralı (2026-10-13).

Erişim ajan_api.py ile aynı desen ama AYRI anahtar (config/okul.json,
gitignore'lu): bu anahtar herkesin kullandığı araçta durur, tahta eylemi /
yeniden başlatma yetkisi taşımamalı.
"""

import asyncio
import hmac
import json
import logging
import unicodedata
from pathlib import Path

import db
import ders_programi
import okul_sql
import zil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("okul_bilgisi")

OKUL_AYAR_YOLU = Path(__file__).resolve().parent / "config" / "okul.json"
OGRETMEN_YOLU = Path(__file__).resolve().parent / "config" / "ogretmenler.json"
_YEREL = {"127.0.0.1", "::1"}
AZAMI_OGRENCI = 60

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = [
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]
# ders_programi.json gün anahtarları (ASCII)
_GUN_ANAHTARI = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma"}

router = APIRouter(prefix="/api/okul")


def _ayar() -> dict:
    try:
        veri = json.loads(OKUL_AYAR_YOLU.read_text(encoding="utf-8"))
        if not isinstance(veri.get("anahtar"), str) or not veri["anahtar"]:
            raise ValueError("anahtar boş")
        return veri
    except (OSError, ValueError, AttributeError, TypeError):
        raise HTTPException(503, "Okul API anahtarı yapılandırılmamış.")


def _dogrula(request: Request) -> dict:
    if not request.client or request.client.host not in _YEREL:
        raise HTTPException(403, "Yalnızca yerel erişim.")
    ayar = _ayar()
    gelen = request.headers.get("X-Farabi-Okul-Key")
    if not gelen or not hmac.compare_digest(
        gelen.encode("utf-8"), ayar["anahtar"].encode("utf-8")
    ):
        raise HTTPException(401, "Geçersiz anahtar.")
    return ayar


def _sade(metin: str) -> str:
    """Karşılaştırma anahtarı: Türkçe küçük harf, ı/i ve aksan farkı yok sayılır."""
    metin = str(metin).replace("I", "ı").replace("İ", "i").lower().replace("ı", "i")
    metin = unicodedata.normalize("NFKD", metin)
    return "".join(c for c in metin if not unicodedata.combining(c))


def _sinif_anahtari(ad: str) -> str:
    return "".join(c for c in _sade(ad) if c.isalnum())


def _siniflar() -> list[str]:
    return list(ders_programi._yukle().keys())


def _sinif_coz(istenen: str) -> str:
    harita = {_sinif_anahtari(s): s for s in _siniflar()}
    s = harita.get(_sinif_anahtari(istenen or ""))
    if s is None:
        raise HTTPException(404, {"mesaj": "Sınıf bulunamadı.", "gecerli": _siniflar()})
    return s


def _ders_listesi(sinif: str, isogun: int, simdiki_no: int | None) -> list[dict]:
    gun = _GUN_ANAHTARI.get(isogun)
    program = ders_programi._yukle().get(sinif, {}).get(gun, {}) if gun else {}
    cikti = []
    for d in zil.ders_saatleri():
        ad = program.get(str(d["no"]))
        if ad:
            cikti.append(
                {
                    "no": d["no"],
                    "baslangic": d["baslangic"],
                    "bitis": d["bitis"],
                    "ders": ad,
                    "simdi": d["no"] == simdiki_no,
                }
            )
    return cikti


def simdi_bilgisi() -> dict:
    an = zil.simdi_istanbul()
    gun_adi = GUNLER[an.isoweekday() - 1]
    tarih_metni = f"{an.day} {AYLAR[an.month - 1]} {an.year} {gun_adi}, saat {an:%H:%M}"
    durum, ders_no = "okul_disi", None
    if zil.okul_gunu_mu(an.date()):
        ders_no = zil.simdiki_ders(an.time())
        ilk, son = zil.ilk_ders_saati(), zil.son_ders_bitis_saati()
        if ders_no is not None:
            durum = "ders"
        elif ilk and son and ilk <= an.time() < son:
            durum = "teneffus"
    ek = {
        "ders": f"{ders_no}. ders saati",
        "teneffus": "teneffüs",
        "okul_disi": "ders saati dışı",
    }[durum]
    return {
        "tarih": an.date().isoformat(),
        "gun": gun_adi,
        "saat": f"{an:%H:%M}",
        "durum": durum,
        "ders_no": ders_no,
        "metin": f"Şu an (Türkiye saati): {tarih_metni} — {ek}.",
    }


@router.get("/simdi")
async def simdi(request: Request):
    _dogrula(request)
    return JSONResponse(simdi_bilgisi())


@router.get("/ders-programi")
async def ders_programi_ucu(request: Request, sinif: str = "", gun: str = "bugun"):
    _dogrula(request)
    ad = _sinif_coz(sinif)
    bilgi = simdi_bilgisi()
    bugun = zil.simdi_istanbul().isoweekday()
    g = _sade(gun or "bugun")
    if g == "hafta":
        hafta = {GUNLER[i - 1]: _ders_listesi(ad, i, None) for i in _GUN_ANAHTARI}
        return JSONResponse(
            {
                "sinif": ad,
                "simdi": bilgi["metin"],
                "hafta": {k: v for k, v in hafta.items() if v},
            }
        )
    if g in ("simdi", "su an", "suan", "bugun"):
        isogun = bugun
    else:
        eslesen = [i for i, adi in enumerate(GUNLER, start=1) if _sade(adi) == g]
        if not eslesen:
            raise HTTPException(400, "gun: simdi | bugun | hafta | Pazartesi..Cuma")
        isogun = eslesen[0]
    simdiki_no = bilgi["ders_no"] if isogun == bugun else None
    dersler = _ders_listesi(ad, isogun, simdiki_no)
    if g in ("simdi", "su an", "suan"):
        dersler = [d for d in dersler if d["simdi"]]
    return JSONResponse(
        {
            "sinif": ad,
            "gun": GUNLER[isogun - 1],
            "durum": bilgi["durum"],
            "simdi": bilgi["metin"],
            "dersler": dersler,
        }
    )


def _ogrenci_izni(request: Request, ayar: dict) -> None:
    eposta = (request.headers.get("X-Farabi-Kullanici") or "").strip().lower()
    rol = (request.headers.get("X-Farabi-Rol") or "").strip().lower()
    izinli = {str(e).strip().lower() for e in ayar.get("ogrenci_izinli", []) if e}
    if not eposta:
        raise HTTPException(403, "Kullanıcı bilgisi yok.")
    if rol != "admin" and eposta not in izinli:
        raise HTTPException(403, "Öğrenci bilgisine bu hesapla erişilemez.")


def _rosterlar() -> list[dict]:
    """Güncel sınıf listesi = panonun `ogrenciler` tablosu (aktif öğrenciler).
    Tahtalara giden yoklama listesi de buradan üretilir. 2026-10-08'e kadar
    sunucudaki eski data/roster/*.json kopyalarından okunuyordu (2026-09-12
    anlık görüntüsü, güncel değildi)."""
    conn = db.baglanti()
    try:
        satirlar = conn.execute(
            "SELECT o.no, o.ad_soyad, s.ad AS sinif FROM ogrenciler o "
            "JOIN siniflar s ON s.id = o.sinif_id "
            "WHERE o.aktif = 1 ORDER BY s.ad, o.no"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"no": str(r["no"]), "ad_soyad": r["ad_soyad"], "sinif": r["sinif"]}
        for r in satirlar
        if r["ad_soyad"]
    ]


@router.get("/ogrenci")
async def ogrenci(request: Request, sinif: str = "", ad: str = "", no: str = ""):
    ayar = _dogrula(request)
    _ogrenci_izni(request, ayar)
    if not (sinif.strip() or ad.strip() or no.strip()):
        raise HTTPException(400, "sinif, ad ya da no gerekli.")
    liste = _rosterlar()
    if sinif.strip():
        anahtar = _sinif_anahtari(sinif)
        liste = [o for o in liste if _sinif_anahtari(o["sinif"]) == anahtar]
    if no.strip():
        liste = [o for o in liste if o["no"] == no.strip()]
    if ad.strip():
        parcalar = _sade(ad).split()
        liste = [o for o in liste if all(p in _sade(o["ad_soyad"]) for p in parcalar)]
    # KVKK: ad/sorgu metni loga yazılmaz, yalnızca sayı.
    log.info("okul/ogrenci sorgusu: %d sonuç", len(liste))
    return JSONResponse({"ogrenciler": liste[:AZAMI_OGRENCI], "toplam": len(liste)})


def _ogretmenler() -> list[dict]:
    try:
        veri = json.loads(OGRETMEN_YOLU.read_text(encoding="utf-8"))
        return [o for o in veri.get("ogretmenler", []) if o.get("ad_soyad")]
    except (OSError, ValueError, AttributeError, TypeError):
        raise HTTPException(503, "Öğretmen listesi yüklenmemiş.")


@router.get("/ogretmen")
async def ogretmen(request: Request, ad: str = ""):
    ayar = _dogrula(request)
    _ogrenci_izni(request, ayar)
    liste = _ogretmenler()
    if ad.strip():
        parcalar = _sade(ad).split()
        liste = [o for o in liste if all(p in _sade(o["ad_soyad"]) for p in parcalar)]
    log.info("okul/ogretmen sorgusu: %d sonuç", len(liste))
    return JSONResponse({"ogretmenler": liste, "toplam": len(liste)})


# --- 2026-10-16: öğretmen anlık durumu + "bugün okulda kimler var" (Atos senaryoları) ---


def _ogretmen_programi() -> dict:
    try:
        return json.loads(OGRETMEN_YOLU.read_text(encoding="utf-8")).get("program", {})
    except (OSError, ValueError, AttributeError, TypeError):
        raise HTTPException(503, "Öğretmen listesi yüklenmemiş.")


def _ogretmen_slotlari(isogun: int) -> dict[str, list[dict]]:
    """Öğretmen adı → o günün ders hücreleri ([{no, baslangic, bitis, sinif}], ders sırasıyla)."""
    gun = _GUN_ANAHTARI.get(isogun)
    saatler = {d["no"]: d for d in zil.ders_saatleri()}
    sonuc: dict[str, list[dict]] = {}
    if not gun:
        return sonuc
    for sinif, gunler in _ogretmen_programi().items():
        for no, adlar in (gunler.get(gun) or {}).items():
            saat = saatler.get(int(no))
            for ad in adlar:
                sonuc.setdefault(ad, []).append(
                    {
                        "no": int(no),
                        "baslangic": saat["baslangic"] if saat else "",
                        "bitis": saat["bitis"] if saat else "",
                        "sinif": sinif,
                    }
                )
    for liste in sonuc.values():
        liste.sort(key=lambda x: x["no"])
    return sonuc


@router.get("/ogretmen-simdi")
async def ogretmen_simdi(request: Request, ad: str = ""):
    """Eşleşen HER öğretmen için (aynı ad birden çok kişide olabilir) şu anki ders + bugünkü dersler."""
    ayar = _dogrula(request)
    _ogrenci_izni(request, ayar)
    if not ad.strip():
        raise HTTPException(400, "ad gerekli.")
    parcalar = _sade(ad).split()
    liste = [o for o in _ogretmenler() if all(p in _sade(o["ad_soyad"]) for p in parcalar)]
    bilgi = simdi_bilgisi()
    slotlar = _ogretmen_slotlari(zil.simdi_istanbul().isoweekday())
    sonuc = []
    for o in liste:
        bugun = slotlar.get(o["ad_soyad"], [])
        simdiki = next((x for x in bugun if x["no"] == bilgi["ders_no"]), None)
        sonuc.append(
            {
                "ad_soyad": o["ad_soyad"],
                "dersler": o.get("dersler") or [],
                "simdi_ders": simdiki,
                "bugun": bugun,
            }
        )
    log.info("okul/ogretmen-simdi sorgusu: %d sonuç", len(sonuc))
    return JSONResponse({"simdi": bilgi["metin"], "durum": bilgi["durum"], "ogretmenler": sonuc})


def _bugun_yoklamasi(tarih: str) -> dict[str, dict]:
    """sinif → bugünkü EN SON yoklama kaydı ({ders_no, yok, izinli})."""
    conn = db.baglanti()
    try:
        satirlar = conn.execute(
            "SELECT sinif, ders_no, yok_isimleri, izinli_isimleri FROM yoklama_onbellek "
            "WHERE tarih = ? AND durum = 'alindi' ORDER BY ders_no",
            (tarih,),
        ).fetchall()
    finally:
        conn.close()
    sonuc: dict[str, dict] = {}
    for r in satirlar:  # ders_no artan: sonuncu kazanır
        def _liste(ham):
            try:
                v = json.loads(ham or "[]")
                return [str(x) for x in v] if isinstance(v, list) else []
            except ValueError:
                return []

        sonuc[_sinif_anahtari(r["sinif"])] = {
            "ders_no": r["ders_no"],
            "yok": _liste(r["yok_isimleri"]),
            "izinli": _liste(r["izinli_isimleri"]),
        }
    return sonuc


@router.get("/okulda")
async def okulda(request: Request, tarih: str = ""):
    """Bugün okulda kimler var: sınıf sınıf yoklama (mevcut/yok/izinli) + şu an dersi olan öğretmenler.
    Yoklama alınmamış sınıf için "alınmadı" döner — tüm liste mevcut sayılmaz."""
    ayar = _dogrula(request)
    _ogrenci_izni(request, ayar)
    an = zil.simdi_istanbul()
    gun = tarih.strip() or an.date().isoformat()
    yoklama = _bugun_yoklamasi(gun)
    mevcut_sayisi: dict[str, int] = {}
    for o in _rosterlar():
        mevcut_sayisi[o["sinif"]] = mevcut_sayisi.get(o["sinif"], 0) + 1
    siniflar = []
    for sinif in sorted(mevcut_sayisi):
        toplam = mevcut_sayisi[sinif]
        y = yoklama.get(_sinif_anahtari(sinif))
        if y is None:
            siniflar.append({"sinif": sinif, "toplam": toplam, "yoklama": "alinmadi"})
        else:
            yok, izinli = y["yok"], y["izinli"]
            siniflar.append(
                {
                    "sinif": sinif,
                    "toplam": toplam,
                    "yoklama": "alindi",
                    "ders_no": y["ders_no"],
                    "mevcut": max(toplam - len(yok) - len(izinli), 0),
                    "yok": yok,
                    "izinli": izinli,
                }
            )
    bilgi = simdi_bilgisi()
    ogretmenler = []
    if gun == an.date().isoformat() and bilgi["ders_no"] is not None:
        for ad, slotlar in _ogretmen_slotlari(an.isoweekday()).items():
            for s in slotlar:
                if s["no"] == bilgi["ders_no"]:
                    ogretmenler.append({"ad_soyad": ad, "sinif": s["sinif"]})
    log.info("okul/okulda sorgusu: %d sınıf", len(siniflar))
    return JSONResponse(
        {
            "tarih": gun,
            "simdi": bilgi["metin"],
            "siniflar": siniflar,
            "dersi_olan_ogretmenler": sorted(ogretmenler, key=lambda x: x["ad_soyad"]),
            "not": "Öğretmen için giriş-çıkış kaydı yok; liste yalnızca ders programına göre şu an dersi olanlardır.",
        }
    )


KAZANIM_YOLU = Path(__file__).resolve().parent.parent / "data" / "kazanimlar.json"


def _dosya_tablolari() -> dict:
    """Öğretmen programı ve haftalık kazanımlar (dosya kaynaklı); dosya yoksa/bozuksa o tablo boş kalır."""
    try:
        program = _ogretmen_programi()
    except HTTPException:
        program = {}
    try:
        kazanim = json.loads(KAZANIM_YOLU.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kazanim = {}
    saatler = {d["no"]: d for d in zil.ders_saatleri()}
    simdi = okul_sql.simdi_tablosu(simdi_bilgisi(), zil.simdi_istanbul().isoweekday())
    return {**okul_sql.ogretmen_programi_tablosu(program, saatler), **okul_sql.kazanim_tablosu(kazanim), **simdi}


@router.post("/sql")
async def sql(request: Request):
    """Atos'un tek veri ucu: okul_ana + yoklama tablolarında salt-okunur SELECT (bkz. okul_sql.py).
    Öğrenci/veli telefonu içerdiği için yalnızca yönetici (admin) rolü."""
    ayar = _dogrula(request)
    if (request.headers.get("X-Farabi-Rol") or "").strip().lower() != "admin":
        raise HTTPException(403, "SQL sorgusu yalnızca yönetici hesabıyla yapılabilir.")
    dsn = ayar.get("sql_dsn")
    if not dsn:
        raise HTTPException(503, "SQL bağlantısı yapılandırılmamış.")
    try:
        govde = await request.json()
        sorgu = govde.get("sorgu") if isinstance(govde, dict) else None
    except ValueError:
        govde, sorgu = None, None
    if not isinstance(sorgu, str):
        raise HTTPException(400, "Gövde {\"sorgu\": \"SELECT ...\"} olmalı.")
    # Dosya/rapor üretimi daha çok satır isteyebilir (sınıf listesi, devamsızlık dökümü); en çok 2000.
    satir = govde.get("azami_satir")
    azami = min(max(satir, 1), 2000) if isinstance(satir, int) and not isinstance(satir, bool) else okul_sql.AZAMI_SATIR

    def _calistir():
        tablolar = {**okul_sql.pg_tablolari(dsn), **okul_sql.yoklama_tablolari(db.DB_YOLU), **_dosya_tablolari()}
        return okul_sql.calistir(sorgu, okul_sql.personel_esle(tablolar), azami_satir=azami)

    try:
        sonuc = await asyncio.to_thread(_calistir)
    except okul_sql.SqlHatasi as e:
        log.info("okul/sql reddedildi: %s", e)
        return JSONResponse({"hata": str(e)}, status_code=400)
    log.info("okul/sql: %d satır (kullanıcı %s)", len(sonuc["satirlar"]), request.headers.get("X-Farabi-Kullanici", "?"))
    return JSONResponse(sonuc)
