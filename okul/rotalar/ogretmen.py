"""Öğretmen sayfaları (yönetici de kullanabilir): sınıflar, ödev/test oluşturma, sonuçlar, duyuru."""

import logging
import sqlite3

import analitik
import duyurular
import odevler
import yetki
import zaman
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi, kazanim, program, zil
from metin import normalize_isim, sinif_seviyesi, tr_kucuk
from rotalar import ogretmen_liderlik

router = APIRouter(prefix="/ogretmen")
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)


def gorevler(conn: sqlite3.Connection, k: sqlite3.Row) -> list[tuple[str, str]]:
    if k["rol"] == "yonetici":
        return [
            (r[0], "")
            for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
        ]
    return yetki.ogretmen_gorevleri(conn, k["id"])


def _odev(conn: sqlite3.Connection, k: sqlite3.Row, odev_id: int) -> sqlite3.Row:
    odev = odevler.odev_getir(conn, odev_id)
    if odev is None or (k["rol"] != "yonetici" and odev["ogretmen_id"] != k["id"]):
        raise HTTPException(404)
    return odev


def _pano(conn: sqlite3.Connection, k: sqlite3.Row) -> list[dict]:
    """Liderlik mini panosu yardımcı bir özelliktir: hata verirse öğretmen ana sayfası yine açılır."""
    try:
        return ogretmen_liderlik.mini_pano(conn, k)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Liderlik mini panosu hesaplanamadı")
        return []


@router.get("")
def ana(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    t_gorevler = gorevler(conn, k)
    an = zaman.simdi()
    bugun = an.date()
    gun_adi = program.GUNLER[bugun.weekday()]
    z_durum = zil.durum(an)

    # 1. Görevler + bu haftanın kazanımı
    gorevler_bilgi = []
    for s, d in t_gorevler:
        kz = kazanim.haftalik_kazanim(s, d, bugun) if d else None
        gorevler_bilgi.append({"sinif": s, "ders": d, "kazanim": kz})

    # 2. Bugünkü dersler ve şu anki / sıradaki ders
    bugunku_dersler = []
    su_anki_ders = None
    siradaki_ders = None

    if gun_adi in program.OKUL_GUNLERI and not zil.tatil_adi(bugun):
        try:
            ders_saatleri = dict((d[0], (d[1], d[2])) for d in zil.dersler())
        except KaynakHatasi:
            ders_saatleri = {}

        for s, d in t_gorevler:
            if not d:
                continue
            hedef = normalize_isim(d)
            try:
                g_dersleri = program.gun_dersleri(s, gun_adi)
            except KaynakHatasi:
                g_dersleri = []
            for no, ders_adi in g_dersleri:
                if normalize_isim(ders_adi) == hedef:
                    saat_aralik = ders_saatleri.get(no)
                    saat_str = (
                        f"{saat_aralik[0]} - {saat_aralik[1]}"
                        if saat_aralik
                        else ""
                    )
                    kz = kazanim.haftalik_kazanim(s, ders_adi, bugun)
                    bugunku_dersler.append({
                        "no": no,
                        "sinif": s,
                        "ders": ders_adi,
                        "saat": saat_str,
                        "baslangic": saat_aralik[0] if saat_aralik else "",
                        "bitis": saat_aralik[1] if saat_aralik else "",
                        "kazanim": kz,
                        "aktif": False,
                    })
        bugunku_dersler.sort(key=lambda x: x["no"])

        aktif_no = z_durum.get("no") if z_durum.get("tur") == "ders" else None
        if aktif_no:
            for item in bugunku_dersler:
                if item["no"] == aktif_no:
                    item["aktif"] = True
                    su_anki_ders = item
                    break

        if not su_anki_ders:
            siradaki_no = None
            if z_durum.get("tur") == "once":
                siradaki_no = 1
            elif z_durum.get("tur") in ("teneffus", "ogle"):
                siradaki_no = z_durum.get("sonraki")

            if siradaki_no:
                for item in bugunku_dersler:
                    if item["no"] == siradaki_no:
                        siradaki_ders = item
                        break

    return render(
        request,
        "ogretmen/ana.html",
        gorevler=t_gorevler,
        gorevler_bilgi=gorevler_bilgi,
        bugunku_dersler=bugunku_dersler,
        su_anki_ders=su_anki_ders,
        siradaki_ders=siradaki_ders,
        gun_adi=program.GUN_ADLARI.get(gun_adi, gun_adi.capitalize()),
        odevler=odevler.ogretmen_odevleri(conn, k)[:10],
        duyurular=duyurular.gorunur_duyurular(conn, k, 5),
        liderlik_pano=_pano(conn, k),
    )


@router.get("/sinif/{sinif}")
def sinif(
    sinif: str,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not yetki.sinif_yetkili(conn, k, sinif):
        raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, f"sinif_listesi:{sinif}", None, istemci_ip(request))
    ogrenciler = conn.execute(
        "SELECT o.*, u.foto, (SELECT count(*) FROM veli_ogrenci v WHERE v.ogrenci_id = o.id) AS veli_sayisi"
        " FROM ogrenci o LEFT JOIN kullanici u ON u.id = o.kullanici_id WHERE o.sinif = ? ORDER BY o.okul_no",
        (sinif,),
    ).fetchall()
    return render(request, "ogretmen/sinif.html", sinif=sinif, ogrenciler=ogrenciler)


@router.get("/odev/yeni")
def odev_formu(
    request: Request,
    sinif: str = "",
    ders: str = "",
    tur: str = "klasik",
    havuz_ders: str = "",
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    secenekler = gorevler(conn, k)
    if not sinif and secenekler:
        sinif, ders = secenekler[0]
    if sinif and ders and not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise HTTPException(404)
    havuz_dersleri, havuz, havuz_hata = [], [], False
    if tur == "test" and sinif:
        try:
            havuz_dersleri = kazanim.havuz_dersleri(sinif_seviyesi(sinif))
            if havuz_ders:
                havuz = kazanim.havuz_sorulari(sinif_seviyesi(sinif), havuz_ders)
        except KaynakHatasi:
            havuz_hata = True
    return render(
        request,
        "ogretmen/odev_yeni.html",
        secenekler=secenekler,
        sinif=sinif,
        ders=ders,
        tur=tur,
        havuz_ders=havuz_ders,
        havuz_dersleri=havuz_dersleri,
        havuz=havuz,
        havuz_hata=havuz_hata,
        soru_sayisi=5,
    )


@router.post("/odev/yeni")
async def odev_olustur(
    request: Request,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    form = await request.form()
    sinif = str(form.get("sinif", "")).strip()
    ders = tr_kucuk(str(form.get("ders", "")).strip())
    tur = str(form.get("tur", "klasik"))
    if not sinif or not ders or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise HTTPException(404)
    try:
        havuz_idler = [int(x) for x in form.getlist("havuz") if str(x).isdigit()]
        havuz = kazanim.havuz_sorulari_getir(havuz_idler) if tur == "test" else []
        sorular = (
            odevler.form_sorulari({a: str(v) for a, v in form.items()}, havuz)
            if tur == "test"
            else []
        )
        odev_id = odevler.odev_olustur(
            conn,
            k["id"],
            sinif,
            ders,
            tur,
            str(form.get("baslik", "")),
            str(form.get("aciklama", "")),
            str(form.get("teslim", "")),
            sorular,
        )
    except (odevler.OdevHatasi, KaynakHatasi) as e:
        raise HTTPException(400, str(e)) from e
    analitik.istekten(request, "ogretmen_odev_olustur", str(odev_id))
    return RedirectResponse(f"/ogretmen/odev/{odev_id}", status_code=303)


@router.get("/odev/{odev_id}")
def odev_sonuc(
    odev_id: int,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    odev = _odev(conn, k, odev_id)
    yetki.erisim_kaydet(conn, k, f"odev_sonuc:{odev_id}", None, istemci_ip(request))
    return render(
        request,
        "ogretmen/odev_sonuc.html",
        odev=odev,
        tablo=odevler.sonuc_tablosu(conn, odev),
        sorular=odevler.sorular(conn, odev_id) if odev["tur"] == "test" else [],
        soru_ist=odevler.soru_istatistik(conn, odev),
    )


@router.post("/odev/{odev_id}/sil")
def odev_sil(
    odev_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _odev(conn, k, odev_id)
    conn.execute("DELETE FROM odev WHERE id = ?", (odev_id,))
    conn.commit()
    return RedirectResponse("/ogretmen", status_code=303)


@router.get("/duyuru")
def duyuru_formu(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    siniflar = yetki.kullanici_siniflari(conn, k)
    if siniflar is None:
        siniflar = [
            r[0]
            for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
        ]
    return render(
        request,
        "duyuru_yaz.html",
        siniflar=siniflar,
        duyurular=duyurular.gorunur_duyurular(conn, k, 30),
    )


@router.post("/duyuru")
def duyuru_ekle(
    request: Request,
    baslik: str = Form(""),
    metin: str = Form(""),
    hedef_tur: str = Form("sinif"),
    hedef: str = Form(""),
    bitis: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    hedef_deger = hedef or None if hedef_tur != "okul" else None
    if not baslik.strip() or not metin.strip():
        raise HTTPException(400, "Başlık ve metin boş olamaz.")
    if not duyurular.ekleyebilir_mi(conn, k, hedef_tur, hedef_deger):
        raise HTTPException(404)
    bitis_str = f"{bitis} 23:59:59" if bitis else None
    duyurular.duyuru_ekle(
        conn, k["id"], baslik, metin, hedef_tur, hedef_deger, bitis_str
    )
    return RedirectResponse("/duyurular", status_code=303)


@router.post("/duyuru/{duyuru_id}/sil")
def duyuru_sil(
    duyuru_id: int,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not duyurular.sil(conn, k, duyuru_id):
        raise HTTPException(404)
    return RedirectResponse("/duyurular", status_code=303)


@router.get("/program")
def ders_programi(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    try:
        haftalik = program.ogretmen_haftalik(yetki.ogretmen_gorevleri(conn, k["id"]))
    except KaynakHatasi:
        haftalik = None
    return render(request, "ogretmen/program.html", program=haftalik)
