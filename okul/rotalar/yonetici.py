"""Yönetici sayfaları: özet, Excel aktarımı, kullanıcılar, görevler, eşleşmeyen yoklama, erişim kaydı."""

import re
import sqlite3
from datetime import timedelta

import analitik
import auth
import belirli_gunler
import duyurular
import ice_aktar
import yetki
import zaman
from deps import ROL_ADLARI, db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from kaynaklar import KaynakHatasi, sms, yoklama
from metin import ilk_sifre, normalize_telefon, tr_kucuk

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
        belirli_gunler=belirli_gunler.bugun(),
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


@router.get("/kullanici/ekle")
def kullanici_ekle_form(request: Request, k=Depends(YONETICI)):
    return render(request, "yonetici/kullanici_ekle.html", hata="", d={})


@router.post("/kullanici/ekle")
def kullanici_ekle(
    request: Request,
    rol_: str = Form(...),
    ad_soyad: str = Form(...),
    kullanici_adi: str = Form(""),
    okul_no: str = Form(""),
    sinif: str = Form(""),
    telefon: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    d = {"rol_": rol_, "ad_soyad": ad_soyad, "kullanici_adi": kullanici_adi,
         "okul_no": okul_no, "sinif": sinif, "telefon": telefon}

    def hata(m):
        return render(request, "yonetici/kullanici_ekle.html", status_code=400, hata=m, d=d)

    ad = " ".join(ad_soyad.split())
    if rol_ not in ("ogrenci", "ogretmen", "yonetici"):
        return hata("Rol seçin.")
    if not ad:
        return hata("Ad soyad boş olamaz.")
    try:
        if rol_ == "ogrenci":
            if not okul_no.strip().isdigit():
                return hata("Okul numarası rakam olmalı.")
            sn = ice_aktar._sinif(sinif)
            if sn is None:
                return hata("Sınıf geçersiz (örn. 9-A).")
            if conn.execute(
                "SELECT 1 FROM ogrenci WHERE okul_no = ?", (int(okul_no),)
            ).fetchone():
                return hata("Bu okul numarası zaten kayıtlı.")
            ice_aktar.ogrenci_uygula(
                conn, [{"okul_no": int(okul_no), "ad_soyad": ad, "sinif": sn, "veliler": []}]
            )
            kadi = str(int(okul_no))
        else:
            kadi = kullanici_adi.strip().lower()
            if not re.fullmatch(r"[a-z0-9._-]{3,30}", kadi):
                return hata("Kullanıcı adı 3-30 karakter, yalnızca a-z 0-9 . _ - olmalı.")
            if conn.execute(
                "SELECT 1 FROM kullanici WHERE kullanici_adi = ?", (kadi,)
            ).fetchone():
                return hata("Bu kullanıcı adı zaten kullanılıyor.")
            tel = normalize_telefon(telefon) if telefon.strip() else None
            if telefon.strip() and not tel:
                return hata("Telefon geçersiz.")
            conn.execute(
                "INSERT INTO kullanici (rol, ad_soyad, kullanici_adi, telefon, sifre_hash, sifre_degismeli, olusturma)"
                " VALUES (?, ?, ?, ?, ?, 1, ?)",
                (rol_, ad, kadi, tel, auth.sifre_hashle(ilk_sifre(ad)), zaman.simdi_str()),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return hata("Kayıt oluşturulamadı (çakışan bilgi).")
    u = conn.execute("SELECT * FROM kullanici WHERE kullanici_adi = ?", (kadi,)).fetchone()
    return render(request, "yonetici/sifre_sifirlandi.html", u=u, sifre=ilk_sifre(ad), yeni=True)


@router.post("/kullanici/{kid}/sil")
def kullanici_sil(
    kid: int, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    """Yalnızca hiç kaydı olmayan hesabı siler; bağlı kayıt (FK) varsa dokunmaz."""
    if kid == k["id"]:
        raise HTTPException(400, "Kendi hesabınızı silemezsiniz.")
    u = conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()
    if u is None:
        raise HTTPException(404)
    try:
        conn.execute("DELETE FROM oturum WHERE kullanici_id = ?", (kid,))
        conn.execute("DELETE FROM ogretmen_gorev WHERE ogretmen_id = ?", (kid,))
        conn.execute("DELETE FROM veli_ogrenci WHERE veli_id = ?", (kid,))
        conn.execute("DELETE FROM veli_ogrenci WHERE ogrenci_id IN (SELECT id FROM ogrenci WHERE kullanici_id = ?)", (kid,))
        conn.execute("DELETE FROM ogrenci WHERE kullanici_id = ?", (kid,))
        conn.execute("DELETE FROM kullanici WHERE id = ?", (kid,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(
            409, "Bu hesabın kayıtları var (XP, oyun, mesaj vb.); silinemez. 'Pasifleştir' kullanın."
        ) from None
    return RedirectResponse("/yonetici/kullanicilar", status_code=303)



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


@router.get("/duyurular")
def duyuru_okuma_liste(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    liste = conn.execute(
        "SELECT d.*, u.ad_soyad AS yazar, (SELECT min(zaman) FROM duyuru_okuma) AS kayit_basi"
        " FROM duyuru d JOIN kullanici u ON u.id = d.yazar_id ORDER BY d.yayin DESC, d.id DESC LIMIT 100"
    ).fetchall()
    ozet = {d["id"]: duyurular.okuma_raporu(conn, d)["roller"] for d in liste}
    return render(request, "yonetici/duyurular.html", liste=liste, ozet=ozet)


@router.get("/duyurular/{duyuru_id}")
def duyuru_okuma_detay(
    duyuru_id: int,
    request: Request,
    k=Depends(YONETICI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    d = conn.execute(
        "SELECT d.*, u.ad_soyad AS yazar FROM duyuru d JOIN kullanici u ON u.id = d.yazar_id WHERE d.id = ?",
        (duyuru_id,),
    ).fetchone()
    if d is None:
        raise HTTPException(404)
    rapor = duyurular.okuma_raporu(conn, d)
    return render(request, "yonetici/duyuru_okuma.html", d=d, **rapor)


_ROL_RENK = {"ogrenci": "#2446c7", "ogretmen": "#1e8c5a", "veli": "#c08adb", "yonetici": "#d7263d"}


def _cizgiler(gunluk: list[dict]) -> tuple[list[dict], int]:
    """Rol başına SVG çizgi noktaları (300x100); veri olmayan günler çizgiye girmez."""
    en_cok = max((n for d in gunluk if d["roller"] for n in d["roller"].values()), default=0) or 1
    adet = max(len(gunluk) - 1, 1)
    cikti = []
    for r, renk in _ROL_RENK.items():
        nokta = [
            f"{300 * i / adet:.1f},{96 - 92 * d['roller'][r] / en_cok:.1f}"
            for i, d in enumerate(gunluk)
            if d["roller"]
        ]
        if nokta:
            cikti.append({"rol": r, "ad": ROL_ADLARI[r], "renk": renk, "nokta": " ".join(nokta)})
    return cikti, en_cok


@router.get("/analitik")
def kullanim_analitigi(
    request: Request,
    bas: str = "",
    bit: str = "",
    rol_f: str = Query("", alias="rol"),
    sinif: str = "",
    duzey: str = "",
    k=Depends(YONETICI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    """Kullanım analitiği (yalnızca sayaç, akademik veriyle ilgisiz). Filtreler sunucuda beyaz listeyle doğrulanır."""
    analitik.bosalt()
    f = analitik.filtre_coz(conn, bas, bit, rol_f, sinif, duzey, ROL_ADLARI)
    gunluk = analitik.gunluk(conn, f)
    cizgiler, cizgi_en_cok = _cizgiler(gunluk)
    saat = analitik.saat_dagilimi(conn, f)
    ozellikler = analitik.ozellikler(conn, f)
    terk = analitik.oturum_terk(conn, f)
    ozet = analitik.ozet(conn, f)
    return render(
        request,
        "yonetici/analitik.html",
        f=f,
        ilk=analitik.veri_baslangici(conn),
        ozet=ozet,
        gunluk=gunluk,
        gun_en_cok=max((d["n"] or 0 for d in gunluk), default=0) or 1,
        cizgiler=cizgiler,
        cizgi_en_cok=cizgi_en_cok,
        hafta=analitik.haftanin_gunu(gunluk),
        saat=saat,
        saat_en_cok=max(saat) or 1,
        ozellikler=ozellikler,
        terk=terk,
        oneriler=analitik.oneriler(ozet, ozellikler, terk),
        siniflar=analitik.siniflar(conn),
        duzeyler=analitik.duzeyler(conn),
        az_veri=analitik.AZ_VERI,
    )
# --- SMS paneli (smssistemi /api/arac üzerinden; 2026-10-21) -----------------

SMS_TURLER = {
    "veli": "Veliler",
    "ogrenci": "Öğrenciler",
    "personel": "Personel / öğretmenler",
}


def _sms_siniflar(conn: sqlite3.Connection) -> list[str]:
    return ["TÜM OKUL"] + [
        r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
    ]


def _sms_form(request, conn, hata="", durum=200, **form):
    try:
        kayitlar, liste_hata = sms.gonderimler(), ""
    except KaynakHatasi as e:
        kayitlar, liste_hata = [], str(e)
    return render(
        request,
        "yonetici/sms.html",
        status_code=durum,
        turler=SMS_TURLER,
        siniflar=_sms_siniflar(conn),
        kayitlar=kayitlar,
        hata=hata,
        liste_hata=liste_hata,
        form=form,
    )


@router.get("/sms")
def sms_panel(
    request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    return _sms_form(request, conn)


@router.post("/sms/taslak")
def sms_taslak(
    request: Request,
    tur: str = Form(...),
    sinif: str = Form(""),
    metin: str = Form(""),
    test_telefon: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if tur not in SMS_TURLER:
        raise HTTPException(404)
    form = dict(tur=tur, sinif=sinif, metin=metin, test_telefon=test_telefon)
    try:
        t = sms.taslak(tur, sinif, metin, test_telefon.strip())
    except KaynakHatasi as e:
        return _sms_form(request, conn, hata=str(e), durum=422, **form)
    return render(
        request, "yonetici/sms_onizle.html", t=t, tur=tur, tur_ad=SMS_TURLER[tur]
    )


@router.post("/sms/gonder")
def sms_gonder(
    request: Request,
    tur: str = Form(...),
    taslak_id: str = Form(...),
    alici_sayisi: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if tur not in SMS_TURLER:
        raise HTTPException(404)
    try:
        sonuc = sms.taslak_gonder(
            tur,
            taslak_id,
            int(alici_sayisi) if alici_sayisi.strip().isdigit() else None,
        )
    except KaynakHatasi as e:
        return _sms_form(request, conn, hata=str(e), durum=422)
    yetki.erisim_kaydet(
        conn,
        k,
        f"sms_gonder:{sonuc['gonderim_id']}:{tur}:{sonuc['sinif']}:{sonuc['alici_sayisi']}",
        None,
        istemci_ip(request),
    )
    return RedirectResponse(f"/yonetici/sms/{sonuc['gonderim_id']}", status_code=303)


@router.get("/sms/{gonderim_id}")
def sms_detay(gonderim_id: str, request: Request, k=Depends(YONETICI)):
    try:
        d = sms.gonderim(gonderim_id)
    except KaynakHatasi as e:
        return render(
            request, "yonetici/sms_detay.html", status_code=404, d=None, hata=str(e)
        )
    hatali = sum(1 for s in d["satirlar"] if s["durum"] == "hata")
    return render(request, "yonetici/sms_detay.html", d=d, hata="", hatali=hatali)


@router.post("/sms/{gonderim_id}/tekrar")
def sms_tekrar(
    gonderim_id: str,
    request: Request,
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        sonuc = sms.tekrar(gonderim_id)
    except KaynakHatasi as e:
        return render(
            request, "yonetici/sms_detay.html", status_code=422, d=None, hata=str(e)
        )
    yetki.erisim_kaydet(
        conn,
        k,
        f"sms_tekrar:{sonuc['gonderim_id']}:{gonderim_id}:{sonuc['alici_sayisi']}",
        None,
        istemci_ip(request),
    )
    return RedirectResponse(f"/yonetici/sms/{sonuc['gonderim_id']}", status_code=303)
