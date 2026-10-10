"""Giriş (şifre / veli SMS kodu), şifre değiştirme, çıkış, ortak sayfalar."""

import sqlite3

import auth
import duyurular
from deps import ANA_SAYFA, db_conn, https_mi, istemci_ip, mevcut_kullanici, render, rol
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from kaynaklar import sms
from metin import ilk_sifre, normalize_telefon

router = APIRouter()

COK_DENEME = "Çok fazla hatalı deneme yapıldı. 1 dakika bekleyip tekrar deneyin."


def _oturumla_yonlendir(
    request: Request, conn: sqlite3.Connection, kullanici_id: int
) -> RedirectResponse:
    token = auth.oturum_ac(conn, kullanici_id, request.headers.get("user-agent"))
    yanit = RedirectResponse("/", status_code=303)
    auth.cerez_yaz(yanit, token, https_mi(request))
    return yanit


@router.get("/")
def kok(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    k = auth.oturum_kullanici(conn, request.cookies.get(auth.COOKIE_ADI))
    if k is None:
        return RedirectResponse("/giris", status_code=303)
    if k["sifre_degismeli"]:
        return RedirectResponse("/sifre", status_code=303)
    return RedirectResponse(ANA_SAYFA[k["rol"]], status_code=303)


@router.get("/giris")
def giris_sayfasi(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    if auth.oturum_kullanici(conn, request.cookies.get(auth.COOKIE_ADI)):
        return RedirectResponse("/", status_code=303)
    return render(request, "giris.html")


@router.post("/giris")
def giris(
    request: Request,
    kullanici_adi: str = Form(""),
    sifre: str = Form(""),
    conn: sqlite3.Connection = Depends(db_conn),
):
    kadi = kullanici_adi.strip().lower()
    anahtarlar = (f"u:{kadi}", f"ip:{istemci_ip(request)}")
    if any(auth.engelli_mi(conn, a) for a in anahtarlar):
        return render(request, "giris.html", 429, hata=COK_DENEME, kullanici_adi=kadi)
    k = conn.execute(
        "SELECT * FROM kullanici WHERE kullanici_adi = ? AND rol != 'veli' AND aktif = 1",
        (kadi,),
    ).fetchone()
    if k is None or not auth.sifre_dogrula(sifre, k["sifre_hash"]):
        for a in anahtarlar:
            auth.hata_kaydet(conn, a)
        return render(
            request,
            "giris.html",
            401,
            hata="Kullanıcı adı ya da şifre hatalı.",
            kullanici_adi=kadi,
        )
    auth.hatalari_temizle(conn, anahtarlar[0])
    return _oturumla_yonlendir(request, conn, k["id"])


@router.get("/veli-giris")
def veli_giris_sayfasi(request: Request):
    return render(request, "veli_giris.html")


@router.post("/veli-giris")
def veli_giris(
    request: Request,
    telefon: str = Form(""),
    conn: sqlite3.Connection = Depends(db_conn),
):
    tel = normalize_telefon(telefon)
    ip = f"ip:{istemci_ip(request)}"
    if tel is None:
        return render(
            request,
            "veli_giris.html",
            422,
            hata="Cep telefonu numaranızı 05xx xxx xx xx biçiminde girin.",
            telefon=telefon,
        )
    if auth.engelli_mi(conn, ip):
        return render(request, "veli_giris.html", 429, hata=COK_DENEME, telefon=telefon)
    veli = conn.execute(
        "SELECT id FROM kullanici WHERE rol = 'veli' AND aktif = 1 AND telefon = ?",
        (tel,),
    ).fetchone()
    if veli is None:
        auth.hata_kaydet(conn, ip)
        return render(
            request,
            "veli_giris.html",
            404,
            hata="Bu numara okulumuzda kayıtlı bir veli numarası değil. Numaranızı güncellemek için okulla iletişime geçin.",
            telefon=telefon,
        )
    kod = auth.kod_uret(conn, tel)
    try:
        sms.kod_gonder(tel, f"Dijital Okul giris kodunuz: {kod} (5 dakika gecerli)")
    except sms.SmsHatasi as e:
        return render(request, "veli_giris.html", 503, hata=str(e), telefon=telefon)
    return RedirectResponse(f"/veli-kod?telefon={tel}", status_code=303)


@router.get("/veli-kod")
def veli_kod_sayfasi(request: Request, telefon: str = ""):
    return render(request, "veli_kod.html", telefon=normalize_telefon(telefon) or "")


@router.post("/veli-kod")
def veli_kod(
    request: Request,
    telefon: str = Form(""),
    kod: str = Form(""),
    conn: sqlite3.Connection = Depends(db_conn),
):
    tel = normalize_telefon(telefon) or ""
    ip = f"ip:{istemci_ip(request)}"
    if auth.engelli_mi(conn, ip):
        return render(request, "veli_kod.html", 429, hata=COK_DENEME, telefon=tel)
    if not auth.kod_dogrula(conn, tel, kod):
        auth.hata_kaydet(conn, ip)
        return render(
            request,
            "veli_kod.html",
            401,
            hata="Kod hatalı ya da süresi dolmuş. Yeni kod isteyebilirsiniz.",
            telefon=tel,
        )
    veli = conn.execute(
        "SELECT id FROM kullanici WHERE rol = 'veli' AND aktif = 1 AND telefon = ?",
        (tel,),
    ).fetchone()
    if veli is None:
        return render(
            request,
            "veli_kod.html",
            404,
            hata="Bu numaraya bağlı veli hesabı bulunamadı.",
            telefon=tel,
        )
    return _oturumla_yonlendir(request, conn, veli["id"])


@router.get("/sifre")
def sifre_sayfasi(request: Request, k: sqlite3.Row = Depends(mevcut_kullanici)):
    if k["rol"] == "veli":
        return RedirectResponse("/", status_code=303)
    return render(request, "sifre.html", zorunlu=bool(k["sifre_degismeli"]))


@router.post("/sifre")
def sifre_degistir(
    request: Request,
    yeni: str = Form(""),
    yeni2: str = Form(""),
    k: sqlite3.Row = Depends(rol("ogrenci", "ogretmen", "yonetici", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    hata = None
    if len(yeni) < 6:
        hata = "Yeni şifre en az 6 karakter olmalı."
    elif yeni != yeni2:
        hata = "İki şifre birbirini tutmuyor."
    elif yeni == ilk_sifre(k["ad_soyad"]):
        hata = "İlk şifrenden farklı bir şifre seç."
    if hata:
        return render(
            request, "sifre.html", 422, hata=hata, zorunlu=bool(k["sifre_degismeli"])
        )
    conn.execute(
        "UPDATE kullanici SET sifre_hash = ?, sifre_degismeli = 0 WHERE id = ?",
        (auth.sifre_hashle(yeni), k["id"]),
    )
    conn.commit()
    auth.diger_oturumlari_kapat(conn, k["id"], request.state.token)
    return RedirectResponse("/", status_code=303)


@router.post("/cikis")
def cikis(
    request: Request,
    _k: sqlite3.Row = Depends(rol(post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    auth.oturum_kapat(conn, request.state.token)
    request.state.token = None
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(auth.COOKIE_ADI, path="/")
    return yanit


@router.get("/duyurular")
def duyuru_listesi(
    request: Request,
    k: sqlite3.Row = Depends(mevcut_kullanici),
    conn: sqlite3.Connection = Depends(db_conn),
):
    return render(
        request, "duyurular.html", duyurular=duyurular.gorunur_duyurular(conn, k)
    )


@router.get("/kvkk")
def kvkk(request: Request):
    return render(request, "kvkk.html")
