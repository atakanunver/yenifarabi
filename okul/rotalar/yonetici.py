"""Yönetici sayfaları: özet, Excel aktarımı, kullanıcılar, görevler, eşleşmeyen yoklama, erişim kaydı."""

import sqlite3
from datetime import timedelta

import auth
import ice_aktar
import zaman
from deps import ROL_ADLARI, db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from kaynaklar import KaynakHatasi, yoklama
from metin import ilk_sifre, tr_kucuk

router = APIRouter(prefix="/yonetici")
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)
TURLER = {"ogrenci": ice_aktar.OGRENCI_BASLIK, "ogretmen": ice_aktar.OGRETMEN_BASLIK}


def _platform_ogrencileri(conn: sqlite3.Connection) -> dict[int, str]:
    return {r[0]: r[1] for r in conn.execute("SELECT okul_no, sinif FROM ogrenci")}


@router.get("")
def ana(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    sayilar = dict(
        conn.execute(
            "SELECT rol, count(*) FROM kullanici WHERE aktif = 1 GROUP BY rol"
        ).fetchall()
    )
    degismemis = conn.execute(
        "SELECT count(*) FROM kullanici WHERE aktif = 1 AND sifre_degismeli = 1 AND rol != 'veli'"
    ).fetchone()[0]
    siniflar = conn.execute(
        "SELECT g.sinif, count(*) AS mevcut,"
        " (SELECT count(*) FROM odev o WHERE o.sinif = g.sinif) AS odev,"
        " (SELECT count(*) FROM odev_teslim t JOIN odev o ON o.id = t.odev_id WHERE o.sinif = g.sinif) AS teslim"
        " FROM ogrenci g GROUP BY g.sinif ORDER BY g.sinif"
    ).fetchall()
    baslangic = (zaman.simdi() - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        yok = yoklama.sinif_yok_sayilari(baslangic)
        eslesmeyen = len(yoklama.eslesmeyenler(_platform_ogrencileri(conn), baslangic))
    except KaynakHatasi:
        yok, eslesmeyen = None, None
    return render(
        request,
        "yonetici/ana.html",
        sayilar=sayilar,
        degismemis=degismemis,
        siniflar=siniflar,
        yok=yok,
        eslesmeyen=eslesmeyen,
    )


@router.get("/aktarim")
def aktarim(request: Request, k=Depends(YONETICI)):
    return render(request, "yonetici/aktarim.html", turler=TURLER)


@router.get("/sablon/{tur}.xlsx")
def sablon(tur: str, k=Depends(YONETICI)):
    if tur not in TURLER:
        raise HTTPException(404)
    return Response(
        ice_aktar.sablon(TURLER[tur]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{tur}_sablonu.xlsx"'},
    )


@router.post("/aktarim/{tur}")
async def aktarim_onizle(
    tur: str,
    request: Request,
    dosya: UploadFile,
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if tur not in TURLER:
        raise HTTPException(404)
    veri = await dosya.read()
    try:
        o = (
            ice_aktar.ogrenci_onizle(veri)
            if tur == "ogrenci"
            else ice_aktar.ogretmen_onizle(veri)
        )
    except ice_aktar.AktarimHatasi as e:
        return render(request, "yonetici/aktarim.html", 422, turler=TURLER, hata=str(e))
    taslak = ice_aktar.taslak_kaydet(conn, tur, o.satirlar) if o.satirlar else None
    return render(request, "yonetici/onizleme.html", tur=tur, onizleme=o, taslak=taslak)


@router.post("/aktarim/{tur}/onay")
def aktarim_onay(
    tur: str,
    request: Request,
    taslak: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    satirlar = ice_aktar.taslak_al(conn, taslak, tur)
    if satirlar is None:
        raise HTTPException(400, "Önizlemenin süresi dolmuş. Dosyayı tekrar yükleyin.")
    try:
        sonuc = (
            ice_aktar.ogrenci_uygula(conn, satirlar)
            if tur == "ogrenci"
            else ice_aktar.ogretmen_uygula(conn, satirlar)
        )
    except ice_aktar.AktarimHatasi as e:
        raise HTTPException(400, str(e)) from e
    ice_aktar.taslak_sil(conn, taslak)
    return render(request, "yonetici/aktarim_sonuc.html", tur=tur, sonuc=sonuc)


@router.get("/kullanicilar")
def kullanicilar(
    request: Request,
    rol_: str = "",
    q: str = "",
    degismemis: int = 0,
    k=Depends(YONETICI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    sql = "SELECT u.*, o.sinif, o.okul_no FROM kullanici u LEFT JOIN ogrenci o ON o.kullanici_id = u.id WHERE 1 = 1"
    params: list = []
    if rol_ in ROL_ADLARI:
        sql += " AND u.rol = ?"
        params.append(rol_)
    if degismemis:
        sql += " AND u.sifre_degismeli = 1 AND u.rol != 'veli'"
    liste = conn.execute(
        sql + " ORDER BY u.rol, o.sinif, u.ad_soyad", params
    ).fetchall()
    if q.strip():
        aranan = tr_kucuk(q.strip())
        liste = [
            u
            for u in liste
            if aranan in tr_kucuk(u["ad_soyad"])
            or aranan in (u["kullanici_adi"] or "")
            or aranan in (u["telefon"] or "")
        ]
    return render(
        request,
        "yonetici/kullanicilar.html",
        liste=liste[:300],
        toplam=len(liste),
        rol_=rol_,
        q=q,
        degismemis=degismemis,
    )


@router.post("/kullanici/{kid}/sifirla")
def sifre_sifirla(
    kid: int,
    request: Request,
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    u = conn.execute(
        "SELECT * FROM kullanici WHERE id = ? AND rol != 'veli'", (kid,)
    ).fetchone()
    if u is None:
        raise HTTPException(404)
    sifre = ilk_sifre(u["ad_soyad"])
    conn.execute(
        "UPDATE kullanici SET sifre_hash = ?, sifre_degismeli = 1 WHERE id = ?",
        (auth.sifre_hashle(sifre), kid),
    )
    conn.commit()
    auth.diger_oturumlari_kapat(conn, kid, None)
    return render(request, "yonetici/sifre_sifirlandi.html", u=u, sifre=sifre)


@router.post("/kullanici/{kid}/durum")
def durum_degistir(
    kid: int, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    if kid == k["id"]:
        raise HTTPException(400, "Kendi hesabınızı pasifleştiremezsiniz.")
    conn.execute("UPDATE kullanici SET aktif = 1 - aktif WHERE id = ?", (kid,))
    conn.commit()
    auth.diger_oturumlari_kapat(conn, kid, None)
    return RedirectResponse("/yonetici/kullanicilar", status_code=303)


@router.get("/gorevler")
def gorevler(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    liste = conn.execute(
        "SELECT g.*, u.ad_soyad FROM ogretmen_gorev g JOIN kullanici u ON u.id = g.ogretmen_id ORDER BY u.ad_soyad, g.sinif, g.ders"
    ).fetchall()
    ogretmenler = conn.execute(
        "SELECT id, ad_soyad FROM kullanici WHERE rol = 'ogretmen' AND aktif = 1 ORDER BY ad_soyad"
    ).fetchall()
    siniflar = [
        r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
    ]
    return render(
        request,
        "yonetici/gorevler.html",
        liste=liste,
        ogretmenler=ogretmenler,
        siniflar=siniflar,
    )


@router.post("/gorevler")
def gorev_ekle(
    ogretmen_id: int = Form(...),
    sinif: str = Form(""),
    ders: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not sinif.strip() or not ders.strip():
        raise HTTPException(400, "Sınıf ve ders boş olamaz.")
    conn.execute(
        "INSERT OR IGNORE INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, ?, ?)",
        (ogretmen_id, sinif.strip().upper(), tr_kucuk(ders.strip())),
    )
    conn.commit()
    return RedirectResponse("/yonetici/gorevler", status_code=303)


@router.post("/gorevler/sil")
def gorev_sil(
    ogretmen_id: int = Form(...),
    sinif: str = Form(""),
    ders: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    conn.execute(
        "DELETE FROM ogretmen_gorev WHERE ogretmen_id = ? AND sinif = ? AND ders = ?",
        (ogretmen_id, sinif, ders),
    )
    conn.commit()
    return RedirectResponse("/yonetici/gorevler", status_code=303)


@router.get("/eslesmeyen")
def eslesmeyen(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    baslangic = (zaman.simdi() - timedelta(days=60)).strftime("%Y-%m-%d")
    try:
        liste = yoklama.eslesmeyenler(_platform_ogrencileri(conn), baslangic)
    except KaynakHatasi:
        liste = None
    return render(request, "yonetici/eslesmeyen.html", liste=liste)


@router.get("/erisim")
def erisim(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    liste = conn.execute(
        "SELECT e.*, u.ad_soyad, u.rol, o.ad_soyad AS ogrenci FROM erisim_log e"
        " JOIN kullanici u ON u.id = e.kullanici_id LEFT JOIN ogrenci o ON o.id = e.ogrenci_id"
        " ORDER BY e.id DESC LIMIT 300"
    ).fetchall()
    return render(request, "yonetici/erisim.html", liste=liste)
