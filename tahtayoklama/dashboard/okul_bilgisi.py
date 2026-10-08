"""Okul bilgisi JSON API'si (/api/okul/*) — Open WebUI "Okul Bilgisi" aracı ve
Farabi kaynak filtresi için (2026-10-04).

- /simdi: Türkiye saatiyle tarih/gün/saat + o anki ders saati/teneffüs (zil.json).
  Filtre her sohbet mesajına bunu ekler (model tarihi uydurmasın).
- /ders-programi: sınıf → şu anki ders / bugün / belirli gün / hafta
  (data/ders_programi.json + zil.json; DB'deki ders_programi tablosu boş).
  Öğretmen adı veri kaynağında YOK — öğretmene göre sorgu yapılamaz.
- /ogrenci: panonun güncel sınıf listesinden (`ogrenciler` tablosu) no + ad soyad + sınıf.
  KVKK: yalnızca okul.json::ogrenci_izinli e-postaları ve Open WebUI admin
  rolü (kullanıcı kararı 2026-10-04: İdare + Öğretmen; tahta hesabı HARİÇ).
  Araç da aynı kontrolü yapar; burası ikinci kapı. Öğrenci adları loga YAZILMAZ.

Erişim ajan_api.py ile aynı desen ama AYRI anahtar (config/okul.json,
gitignore'lu): bu anahtar herkesin kullandığı araçta durur, tahta eylemi /
yeniden başlatma yetkisi taşımamalı.
"""

import hmac
import json
import logging
import unicodedata
from pathlib import Path

import db
import ders_programi
import zil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("okul_bilgisi")

OKUL_AYAR_YOLU = Path(__file__).resolve().parent / "config" / "okul.json"
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
