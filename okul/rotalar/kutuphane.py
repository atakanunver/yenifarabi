"""Kütüphane rotaları. Yetki sunucuda: işlem (ekle/ver/al/rapor) = yönetici + yetkilendirilmiş öğretmen; katalog =
öğrenci/öğretmen/yönetici; Kütüphanem = öğrenci (kendisi) ve veli (yalnızca kendi çocuğu). Yetkisiz = 404.
Kamera görüntüsü sunucuya gelmez: tarayıcı kodu çözer, yalnızca okunan metin `GET /kutuphane/api/kod`'a gider.
"""

import sqlite3

import kutuphane
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response

router = APIRouter(prefix="/kutuphane")
UYE = rol("ogrenci", "veli", "ogretmen", "yonetici")
KATALOG = rol("ogrenci", "ogretmen", "yonetici")
PERSONEL = rol("ogretmen", "yonetici")
PERSONEL_POST = rol("ogretmen", "yonetici", post=True)
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)
OGRENCI_POST = rol("ogrenci", post=True)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
AZAMI_DOSYA = 5 * 1024 * 1024


def _gorevli(conn: sqlite3.Connection, k) -> None:
    if not kutuphane.islem_yetkisi(conn, k):
        raise HTTPException(404)


def _hata(e: kutuphane.KutuphaneHatasi) -> JSONResponse:
    return JSONResponse({"tamam": False, "mesaj": e.mesaj}, status_code=e.kod)


def _ogrenci_id(conn: sqlite3.Connection, k) -> int:
    oid = kutuphane.ogrenci_id_kullanici(conn, k["id"])
    if oid is None:
        raise HTTPException(404)
    return oid


@router.get("")
def ana(request: Request, k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    if k["rol"] in ("ogrenci", "veli"):
        return RedirectResponse("/kutuphane/benim", status_code=303)
    if not kutuphane.islem_yetkisi(conn, k):
        return RedirectResponse("/kutuphane/katalog", status_code=303)
    kutuphane.ayirtma_temizle(conn)
    r = kutuphane.rapor(conn)
    return render(request, "kutuphane/ana.html", ozet=r, son=kutuphane.son_islemler(conn, 8), ayirtma=len(kutuphane.ayirtmalar(conn)))


# ---- Kamera ile ver / al ----

@router.get("/ver")
def ver_sayfa(request: Request, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return render(request, "kutuphane/islem.html", mod="ver", ayar=kutuphane.ayarlar(conn))


@router.get("/al")
def al_sayfa(request: Request, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return render(request, "kutuphane/islem.html", mod="al", ayar=kutuphane.ayarlar(conn))


@router.get("/api/kod")
def api_kod(kod: str = "", k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return kutuphane.kod_coz(conn, kod[:64])


@router.get("/api/ogrenci")
def api_ogrenci(q: str = "", k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return {"ogrenciler": kutuphane.ogrenci_ara(conn, q[:60]), "limit": kutuphane.ayarlar(conn)["ogrenci_limit"]}


@router.get("/api/isbn")
def api_isbn(isbn: str = "", k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return {"kitap": kutuphane.kitap_isbn(conn, isbn[:20])}


@router.post("/ver")
def ver(
    nusha_id: int = Form(...),
    ogrenci_id: int = Form(...),
    k=Depends(PERSONEL_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _gorevli(conn, k)
    try:
        oid = kutuphane.odunc_ver(conn, nusha_id, ogrenci_id, k["id"])
    except kutuphane.KutuphaneHatasi as e:
        return _hata(e)
    return {"tamam": True, "kayit": kutuphane.odunc_kaydi(conn, oid)}


@router.post("/al")
def al(nusha_id: int = Form(...), k=Depends(PERSONEL_POST), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    try:
        kayit = kutuphane.iade_al(conn, nusha_id, k["id"])
    except kutuphane.KutuphaneHatasi as e:
        return _hata(e)
    return {"tamam": True, "kayit": kayit}


# ---- Kitap ekleme / içe aktarma / etiket ----

def _ekle_sayfa(request, conn, hata="", form=None, durum=200):
    return render(request, "kutuphane/ekle.html", status_code=durum, hata=hata, form=form or {},
                  eklenen=kutuphane.demirbas_bul(conn, request.query_params.get("eklendi", "")))


@router.get("/ekle")
def ekle_sayfa(request: Request, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return _ekle_sayfa(request, conn)


@router.post("/ekle")
def ekle(
    request: Request,
    isbn: str = Form(""),
    demirbas: str = Form(""),
    baslik: str = Form(""),
    yazar: str = Form(""),
    yayinevi: str = Form(""),
    baski_yili: str = Form(""),
    basim_sayisi: str = Form(""),
    tur: str = Form(""),
    raf: str = Form(""),
    k=Depends(PERSONEL_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _gorevli(conn, k)
    form = {"isbn": isbn, "demirbas": demirbas, "baslik": baslik, "yazar": yazar, "yayinevi": yayinevi,
            "baski_yili": baski_yili, "basim_sayisi": basim_sayisi, "tur": tur, "raf": raf}
    try:
        nid = kutuphane.nusha_ekle(conn, **form)
    except kutuphane.KutuphaneHatasi as e:
        return _ekle_sayfa(request, conn, hata=e.mesaj, form=form, durum=e.kod)
    d = conn.execute("SELECT demirbas FROM nusha WHERE id = ?", (nid,)).fetchone()["demirbas"]
    return RedirectResponse(f"/kutuphane/ekle?eklendi={d}", status_code=303)


@router.get("/ice-aktar")
def ice_aktar_sayfa(request: Request, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return render(request, "kutuphane/ice_aktar.html", sonuc=None, hata="")


@router.get("/sablon.xlsx")
def sablon(k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return Response(kutuphane.sablon_xlsx(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="kutuphane_sablon.xlsx"'})


@router.post("/ice-aktar")
async def ice_aktar(
    request: Request,
    dosya: UploadFile = File(...),
    k=Depends(PERSONEL_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _gorevli(conn, k)
    veri = await dosya.read(AZAMI_DOSYA + 1)
    if len(veri) > AZAMI_DOSYA:
        return render(request, "kutuphane/ice_aktar.html", status_code=413, sonuc=None, hata="Dosya en çok 5 MB olabilir.")
    try:
        sonuc = kutuphane.ice_aktar(conn, veri)
    except kutuphane.KutuphaneHatasi as e:
        return render(request, "kutuphane/ice_aktar.html", status_code=e.kod, sonuc=None, hata=e.mesaj)
    return render(request, "kutuphane/ice_aktar.html", sonuc=sonuc, hata="")


@router.get("/etiket")
def etiket(
    request: Request, bas: str = "", bit: str = "", kitap: int | None = None, ek: int = 0,
    k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn),
):
    _gorevli(conn, k)
    return render(request, "kutuphane/etiket.html",
                  nushalar=kutuphane.etiket_nushalari(conn, bas[:30], bit[:30], kitap, ek=bool(ek)),
                  bas=bas, bit=bit, ek=bool(ek), onek=kutuphane.ETIKET_ONEK)


# ---- Liste / ödünçteki / rapor ----

@router.get("/katalog")
def katalog(request: Request, q: str = "", k=Depends(KATALOG), conn: sqlite3.Connection = Depends(db_conn)):
    return render(request, "kutuphane/katalog.html", kitaplar=kutuphane.katalog(conn, q[:80]), q=q,
                  gorevli=kutuphane.islem_yetkisi(conn, k))


@router.get("/kitap/{kitap_id}")
def kitap(request: Request, kitap_id: int, k=Depends(KATALOG), conn: sqlite3.Connection = Depends(db_conn)):
    gorevli = kutuphane.islem_yetkisi(conn, k)
    liste = kutuphane.nushalar(conn, "k.id = ?", (kitap_id,))
    if not liste:
        raise HTTPException(404)
    ogr = kutuphane.ogrenci_id_kullanici(conn, k["id"]) if k["rol"] == "ogrenci" else None
    if not gorevli:  # öğrenci/öğretmen kimin aldığını görmez
        liste = [{x: n[x] for x in ("demirbas", "raf", "durum_ad", "musait", "oduncte", "baslik", "yazar", "yayinevi",
                                    "isbn", "baski_yili", "basim_sayisi", "kitap_id")} for n in liste]
    bende = ogr is not None and any(a["kitap_id"] == kitap_id for a in kutuphane.kutuphanem(conn, ogr)["aktif"])
    ayirtma = next((a for a in kutuphane.ayirtmalar(conn, ogr) if a["kitap_id"] == kitap_id), None) if ogr else None
    return render(request, "kutuphane/kitap.html", nushalar=liste, eser=liste[0], gorevli=gorevli, ogrenci=ogr is not None,
                  bende=bende, ayirtma=ayirtma, durumlar=kutuphane.DURUMLAR, hata=_HATA_METNI.get(request.query_params.get("hata", ""), ""))


@router.post("/nusha/{nusha_id}/durum")
def nusha_durum(
    nusha_id: int, durum: str = Form(""), k=Depends(PERSONEL_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _gorevli(conn, k)
    try:
        kutuphane.nusha_durum_ayarla(conn, nusha_id, durum)
    except kutuphane.KutuphaneHatasi as e:
        raise HTTPException(e.kod) from None
    kitap_id = conn.execute("SELECT kitap_id FROM nusha WHERE id = ?", (nusha_id,)).fetchone()["kitap_id"]
    return RedirectResponse(f"/kutuphane/kitap/{kitap_id}", status_code=303)


@router.get("/oduncte")
def oduncte(request: Request, geciken: int = 0, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    kutuphane.ayirtma_temizle(conn)
    yetki.erisim_kaydet(conn, k, "kutuphane_gecikenler" if geciken else "kutuphane_oduncte", None, istemci_ip(request))
    return render(request, "kutuphane/oduncte.html", liste=kutuphane.aktif_odunclar(conn, bool(geciken)), geciken=bool(geciken),
                  ayirtmalar=kutuphane.ayirtmalar(conn))


@router.get("/rapor")
def rapor(request: Request, k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return render(request, "kutuphane/rapor.html", r=kutuphane.rapor(conn))


@router.get("/rapor.xlsx")
def rapor_xlsx(k=Depends(PERSONEL), conn: sqlite3.Connection = Depends(db_conn)):
    _gorevli(conn, k)
    return Response(kutuphane.rapor_xlsx(conn), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="kutuphane_rapor.xlsx"'})


# ---- Ayarlar (yalnızca yönetici) ----

@router.get("/ayarlar")
def ayarlar(request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    return render(request, "kutuphane/ayarlar.html", ayar=kutuphane.ayarlar(conn), sinir=kutuphane.AYAR_SINIR,
                  ogretmenler=kutuphane.ogretmenler(conn), hata="", kaydedildi=request.query_params.get("kaydedildi"))


@router.post("/ayarlar")
async def ayarlar_kaydet(request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    form = await request.form()
    try:
        kutuphane.ayar_kaydet(conn, {"odunc_gun": form.get("odunc_gun"), "ogrenci_limit": form.get("ogrenci_limit"),
                                     "hatirlatma": 1 if form.get("hatirlatma") else 0})
        kutuphane.yetkilileri_ayarla(conn, [int(i) for i in form.getlist("yetkili") if str(i).isdigit()])
    except kutuphane.KutuphaneHatasi as e:
        return render(request, "kutuphane/ayarlar.html", status_code=e.kod, ayar=kutuphane.ayarlar(conn), sinir=kutuphane.AYAR_SINIR,
                      ogretmenler=kutuphane.ogretmenler(conn), hata=e.mesaj, kaydedildi=None)
    return RedirectResponse("/kutuphane/ayarlar?kaydedildi=1", status_code=303)


# ---- Kütüphanem (öğrenci / veli) + ayırtma ----

@router.get("/benim")
def benim(request: Request, ogr: int | None = None, k=Depends(rol("ogrenci", "veli")), conn: sqlite3.Connection = Depends(db_conn)):
    cocuklar, cocuk = [], None
    if k["rol"] == "veli":
        cocuklar = yetki.veli_cocuklari(conn, k["id"])
        cocuk = next((c for c in cocuklar if ogr is None or c["id"] == ogr), None)
        if cocuk is None:
            if ogr is not None:
                raise HTTPException(404)
            return render(request, "kutuphane/benim.html", veri=None, cocuklar=[], cocuk=None)
        yetki.erisim_kaydet(conn, k, "kutuphane", cocuk["id"], istemci_ip(request))
        oid = cocuk["id"]
    else:
        oid = _ogrenci_id(conn, k)
    return render(request, "kutuphane/benim.html", veri=kutuphane.kutuphanem(conn, oid), cocuklar=cocuklar, cocuk=cocuk,
                  hazir_gun=kutuphane.HAZIR_GUN)


@router.post("/ayirt/{kitap_id}")
def ayirt(kitap_id: int, k=Depends(OGRENCI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    try:
        kutuphane.ayirt(conn, kitap_id, _ogrenci_id(conn, k))
    except kutuphane.KutuphaneHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return RedirectResponse(f"/kutuphane/kitap/{kitap_id}?hata={_HATA_KODU.get(e.mesaj, 'genel')}", status_code=303)
    return RedirectResponse("/kutuphane/benim", status_code=303)


@router.post("/ayirtma/{ayirtma_id}/iptal")
def ayirtma_iptal(ayirtma_id: int, k=Depends(OGRENCI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    try:
        kutuphane.ayirtma_iptal(conn, ayirtma_id, _ogrenci_id(conn, k))
    except kutuphane.KutuphaneHatasi:
        raise HTTPException(404) from None
    return RedirectResponse("/kutuphane/benim", status_code=303)


# URL'den metin yansıtılmaz: hata yalnızca bilinen kodla taşınır, şablon koddan metne çevirir.
_HATA_KODU = {
    "Bu kitap şu an rafta; kütüphaneden alabilirsin.": "rafta",
    "Bu kitap zaten sende.": "sende",
    "Bu kitabı zaten ayırttın.": "zaten",
    f"En çok {kutuphane.AYIRTMA_LIMIT} kitap ayırtabilirsin.": "limit",
}
_HATA_METNI = {v: m for m, v in _HATA_KODU.items()} | {"genel": "Ayırtma yapılamadı."}
