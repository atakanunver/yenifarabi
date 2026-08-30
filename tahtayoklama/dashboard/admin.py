"""Faz 5 — yönetim ekranları: tahta↔sınıf atama, roster düzenleme, senkron.

server/tahtalar.json'a hiçbir yazma YAPILMAZ — bu router yalnızca panonun
kendi SQLite DB'sini değiştirir (bkz. CLAUDE.md).
"""

import csv
import io
import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import ssh_istemci
import zil

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

_SINIF_AD_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_DURUM_ETIKETI = {
    "alindi": "Alındı",
    "alinmadi": "Alınmadı",
    "henuz_baslamadi": "Henüz başlamadı",
    "tahta_ulasilamaz": "Tahta ulaşılamaz",
    "tahta_atanmamis": "Tahta atanmadı",
}
_RAPOR_VARSAYILAN_GUN = 30


def _oturum_sarti(request: Request, conn) -> None:
    if not auth.dogrula(request, conn):
        raise HTTPException(401, "Oturum geçersiz.")


# ----------------------------------------------------------------------
# Tahta ↔ sınıf atama
# ----------------------------------------------------------------------

def _tahtalar_ve_siniflar(conn) -> tuple[list[dict], list[dict]]:
    tahtalar = [dict(r) for r in conn.execute(
        "SELECT t.id, t.ad, t.ip, t.mac, t.aktif, t.sinif_id, s.ad AS sinif_adi "
        "FROM tahtalar t LEFT JOIN siniflar s ON s.id = t.sinif_id "
        "ORDER BY t.ad"
    )]
    siniflar = [dict(r) for r in conn.execute(
        "SELECT id, ad FROM siniflar WHERE aktif = 1 ORDER BY ad"
    )]
    return tahtalar, siniflar


def _roster_payload_olustur(conn, sinif_id: int) -> tuple[dict, bytes]:
    """Bir sınıfın kayıtlı öğrenci listesini yoklama.py'nin beklediği roster
    JSON'una çevirir — cinsiyet yoksa anahtarı hiç yazmaz (`null` değil),
    `9-A.example.json` şemasıyla birebir."""
    sinif = conn.execute("SELECT id, ad FROM siniflar WHERE id = ?", (sinif_id,)).fetchone()
    if sinif is None:
        raise HTTPException(404, "Sınıf bulunamadı.")
    ogrenciler = [dict(r) for r in conn.execute(
        "SELECT no, ad_soyad, cinsiyet FROM ogrenciler WHERE sinif_id = ? AND aktif = 1 ORDER BY no",
        (sinif_id,),
    )]
    ogrenci_listesi = []
    for o in ogrenciler:
        girdi = {"no": o["no"], "ad_soyad": o["ad_soyad"]}
        if o["cinsiyet"]:
            girdi["cinsiyet"] = o["cinsiyet"]
        ogrenci_listesi.append(girdi)
    payload = json.dumps(
        {"sinif": sinif["ad"], "ogrenciler": ogrenci_listesi}, ensure_ascii=False, indent=2
    ).encode("utf-8")
    return dict(sinif), payload


async def _tahtaya_roster_gonder(tahta: dict, sinif_ad: str, payload: bytes) -> dict:
    """Yeni roster'ı tahtaya yazar VE aynı dizindeki diğer eski roster
    dosyalarını siler — bir tahta her zaman TEK bir sınıfı göstermeli, eski
    dosyalar bırakılırsa tahta↔sınıf ataması değiştikten sonra öğretmenin
    sınıf seçme kutusunda önceki (artık geçersiz) sınıflar da görünmeye
    devam ediyordu (bkz. CLAUDE.md, 2026-08-24 swap notu — önceden elle SSH
    ile siliniyordu, artık her yüklemede otomatik)."""
    sinif_adi_dogrulanmis = ssh_istemci.ad_dogrula(sinif_ad)
    dizin = "~/tahtayoklama/data/roster"
    uzak_yol = f"{dizin}/{sinif_adi_dogrulanmis}.json"
    komut = (
        f"cat > {uzak_yol}.tmp && mv {uzak_yol}.tmp {uzak_yol} && "
        f"find {dizin} -maxdepth 1 -name '*.json' "
        f"! -name '{sinif_adi_dogrulanmis}.json' -delete"
    )
    sonuc = await ssh_istemci.komut_calistir(
        tahta["ip"], tahta["ssh_kullanici"], komut, stdin_bytes=payload
    )
    return {
        "tahta": tahta["ad"],
        "basarili": sonuc.basarili,
        "detay": sonuc.stderr.decode("utf-8", errors="replace")[:200] if not sonuc.basarili else "",
    }


@router.get("/tahtalar", response_class=HTMLResponse)
async def tahtalar_listesi(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tahtalar, siniflar = _tahtalar_ve_siniflar(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "admin_tahtalar.html", {"tahtalar": tahtalar, "siniflar": siniflar}
    )


@router.post("/tahtalar/{tahta_id}")
async def tahta_guncelle(request: Request, tahta_id: int):
    """Tahtaya bir liste (sınıf) atar ve — atanan bir liste varsa — SEÇİLEN
    LİSTEYİ AYNI İSTEKTE bu tek tahtaya SSH ile yazar. Önceden atama ve
    senkronizasyon iki ayrı ekrandaydı (tahta ataması burada, senkron
    butonu /admin/siniflar/{id}/ogrenciler'de); bu ayrım canlıda bir kez
    "atama yaptım ama tahtaya hiçbir şey gitmedi" hatasına yol açtı (bkz.
    CLAUDE.md, 2026-08-24) — tek adımda birleştirildi."""
    form = await request.form()
    sinif_id_ham = form.get("sinif_id", "")
    sinif_id = int(sinif_id_ham) if sinif_id_ham else None
    aktif = 1 if form.get("aktif") == "on" else 0

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tahta = conn.execute(
            "SELECT id, ad, ip, ssh_kullanici FROM tahtalar WHERE id = ?", (tahta_id,)
        ).fetchone()
        if tahta is None:
            raise HTTPException(404, "Tahta bulunamadı.")
        conn.execute(
            "UPDATE tahtalar SET sinif_id = ?, aktif = ?, guncelleme_zamani = datetime('now') "
            "WHERE id = ?",
            (sinif_id, aktif, tahta_id),
        )
        conn.commit()

        sonuc = None
        if sinif_id is not None:
            sinif, payload = _roster_payload_olustur(conn, sinif_id)
            sonuc = await _tahtaya_roster_gonder(dict(tahta), sinif["ad"], payload)

        tahtalar, siniflar = _tahtalar_ve_siniflar(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "admin_tahtalar.html",
        {"tahtalar": tahtalar, "siniflar": siniflar, "sonuc": sonuc, "sonuc_tahta_id": tahta_id},
    )


@router.post("/tahtalar")
async def tahta_ekle(request: Request):
    form = await request.form()
    ad = (form.get("ad") or "").strip()
    ip = (form.get("ip") or "").strip()
    ssh_kullanici = (form.get("ssh_kullanici") or "ogretmen").strip()
    python_yolu = (form.get("python_yolu") or "/home/ogretmen/tahtayoklama/venv/bin/python").strip()

    try:
        ssh_istemci.ad_dogrula(ad)
    except ValueError:
        raise HTTPException(400, "Geçersiz tahta adı (yalnızca harf/rakam/-/_ kullanılabilir).")
    if not ip:
        raise HTTPException(400, "IP boş olamaz.")

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        conn.execute(
            "INSERT INTO tahtalar (ad, ip, ssh_kullanici, python_yolu) VALUES (?, ?, ?, ?)",
            (ad, ip, ssh_kullanici, python_yolu),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/admin/tahtalar", status_code=303)


# ----------------------------------------------------------------------
# Roster düzenleyici
# ----------------------------------------------------------------------

@router.get("/siniflar", response_class=HTMLResponse)
async def siniflar_listesi(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        siniflar = [dict(r) for r in conn.execute(
            "SELECT s.id, s.ad, s.aktif, COUNT(o.id) AS ogrenci_sayisi "
            "FROM siniflar s LEFT JOIN ogrenciler o ON o.sinif_id = s.id AND o.aktif = 1 "
            "GROUP BY s.id ORDER BY s.ad"
        )]
    finally:
        conn.close()
    return templates.TemplateResponse(request, "admin_siniflar.html", {"siniflar": siniflar})


@router.post("/siniflar")
async def sinif_ekle(request: Request):
    form = await request.form()
    ad = (form.get("ad") or "").strip()
    if not _SINIF_AD_RE.match(ad):
        raise HTTPException(400, "Geçersiz sınıf adı (yalnızca harf/rakam/-/_ kullanılabilir).")

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        conn.execute("INSERT INTO siniflar (ad) VALUES (?)", (ad,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/admin/siniflar", status_code=303)


@router.get("/siniflar/{sinif_id}/ogrenciler", response_class=HTMLResponse)
async def sinif_ogrencileri(request: Request, sinif_id: int):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        sinif = conn.execute("SELECT id, ad FROM siniflar WHERE id = ?", (sinif_id,)).fetchone()
        if sinif is None:
            raise HTTPException(404, "Sınıf bulunamadı.")
        ogrenciler = [dict(r) for r in conn.execute(
            "SELECT no, ad_soyad, cinsiyet FROM ogrenciler "
            "WHERE sinif_id = ? AND aktif = 1 ORDER BY no",
            (sinif_id,),
        )]
        tahtalar = [dict(r) for r in conn.execute(
            "SELECT ad, ip FROM tahtalar WHERE sinif_id = ? AND aktif = 1", (sinif_id,)
        )]
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "admin_sinif_ogrenciler.html",
        {"sinif": dict(sinif), "ogrenciler": ogrenciler, "tahtalar": tahtalar},
    )


@router.post("/siniflar/{sinif_id}/ogrenciler")
async def sinif_ogrencilerini_kaydet(request: Request, sinif_id: int):
    form = await request.form()
    no_listesi = form.getlist("no")
    ad_listesi = form.getlist("ad_soyad")
    cinsiyet_listesi = form.getlist("cinsiyet")

    satirlar = []
    for no, ad_soyad, cinsiyet in zip(no_listesi, ad_listesi, cinsiyet_listesi):
        no = no.strip()
        ad_soyad = ad_soyad.strip()
        if not no or not ad_soyad:
            continue  # boş satır (yeni-ekle satırı boş bırakıldıysa) atlanır
        try:
            no_int = int(no)
        except ValueError:
            raise HTTPException(400, f"Geçersiz öğrenci no: {no!r}")
        satirlar.append((no_int, ad_soyad, cinsiyet.strip() or None))

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        sinif = conn.execute("SELECT id FROM siniflar WHERE id = ?", (sinif_id,)).fetchone()
        if sinif is None:
            raise HTTPException(404, "Sınıf bulunamadı.")
        # Komple değiştir — sınıf başına ~20 öğrenci, düşük frekanslı işlem,
        # satır-satır fark almaktan daha basit ve doğru (bkz. plan.md).
        conn.execute("DELETE FROM ogrenciler WHERE sinif_id = ?", (sinif_id,))
        conn.executemany(
            "INSERT INTO ogrenciler (sinif_id, no, ad_soyad, cinsiyet) VALUES (?, ?, ?, ?)",
            [(sinif_id, no, ad, c) for no, ad, c in satirlar],
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(f"/admin/siniflar/{sinif_id}/ogrenciler", status_code=303)


# ----------------------------------------------------------------------
# Tahtaya senkronize et
# ----------------------------------------------------------------------

@router.post("/siniflar/{sinif_id}/senkronize")
async def sinif_senkronize(request: Request, sinif_id: int):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        sinif, payload = _roster_payload_olustur(conn, sinif_id)
        tahtalar = [dict(r) for r in conn.execute(
            "SELECT id, ad, ip, ssh_kullanici FROM tahtalar WHERE sinif_id = ? AND aktif = 1",
            (sinif_id,),
        )]
    finally:
        conn.close()

    sonuclar = [await _tahtaya_roster_gonder(t, sinif["ad"], payload) for t in tahtalar]

    if not tahtalar:
        sonuclar.append({"tahta": None, "basarili": False, "detay": "Bu sınıfa bağlı hiçbir tahta yok."})

    conn2 = db.baglanti()
    try:
        s2 = conn2.execute("SELECT id, ad FROM siniflar WHERE id = ?", (sinif_id,)).fetchone()
        o2 = [dict(r) for r in conn2.execute(
            "SELECT no, ad_soyad, cinsiyet FROM ogrenciler WHERE sinif_id = ? AND aktif = 1 ORDER BY no",
            (sinif_id,),
        )]
        t2 = [dict(r) for r in conn2.execute(
            "SELECT ad, ip FROM tahtalar WHERE sinif_id = ? AND aktif = 1", (sinif_id,)
        )]
    finally:
        conn2.close()

    return templates.TemplateResponse(
        request, "admin_sinif_ogrenciler.html",
        {"sinif": dict(s2), "ogrenciler": o2, "tahtalar": t2, "senkron_sonuclari": sonuclar},
    )


# ----------------------------------------------------------------------
# Geriye dönük raporlama
# ----------------------------------------------------------------------

def _rapor_araligi(baslangic: str | None, bitis: str | None) -> tuple[str, str]:
    """Geçersiz/eksik girdide son 30 güne düşer; bitiş bugünü geçemez,
    başlangıç bitişten sonra olamaz (varsayılana düşülür)."""
    bugun = zil.simdi_istanbul().date()
    varsayilan_baslangic = (bugun - timedelta(days=_RAPOR_VARSAYILAN_GUN - 1)).isoformat()
    varsayilan_bitis = bugun.isoformat()
    try:
        b = ssh_istemci.tarih_dogrula(baslangic) if baslangic else varsayilan_baslangic
        s = ssh_istemci.tarih_dogrula(bitis) if bitis else varsayilan_bitis
    except ValueError:
        return varsayilan_baslangic, varsayilan_bitis
    if s > bugun.isoformat():
        s = bugun.isoformat()
    if b > s:
        return varsayilan_baslangic, varsayilan_bitis
    return b, s


def _rapor_verisi(conn, baslangic: str, bitis: str, sinif_ad: str | None) -> list[dict]:
    """(tarih, sınıf, ders) satırlarını döner — ders_yok_o_gun (hafta sonu/
    tatil) satırları rapordan gürültü olduğu için baştan filtrelenir."""
    sorgu = (
        "SELECT tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri, "
        "kaynak_tahta, kaydedilme_saati "
        "FROM yoklama_onbellek WHERE tarih BETWEEN ? AND ? AND durum != 'ders_yok_o_gun'"
    )
    parametreler: list = [baslangic, bitis]
    if sinif_ad:
        sorgu += " AND sinif = ?"
        parametreler.append(sinif_ad)
    sorgu += " ORDER BY tarih, sinif, ders_no"

    satirlar = []
    for r in conn.execute(sorgu, parametreler):
        d = dict(r)
        d["yok_isimleri"] = json.loads(d["yok_isimleri"] or "[]")
        d["izinli_isimleri"] = json.loads(d["izinli_isimleri"] or "[]")
        d["durum_etiketi"] = _DURUM_ETIKETI.get(d["durum"], d["durum"])
        satirlar.append(d)
    return satirlar


def _devamsizlik_sayaci(satirlar: list[dict]) -> list[dict]:
    """(sınıf, öğrenci) çiftine göre yok/izinli sayımı — isim çakışmasını
    önlemek için sınıf da anahtara dahil (aynı isim farklı sınıflarda olabilir)."""
    sayac: dict[tuple[str, str], dict] = {}
    for satir in satirlar:
        for isim in satir["yok_isimleri"]:
            girdi = sayac.setdefault((satir["sinif"], isim), {"sinif": satir["sinif"], "ad_soyad": isim, "yok": 0, "izinli": 0})
            girdi["yok"] += 1
        for isim in satir["izinli_isimleri"]:
            girdi = sayac.setdefault((satir["sinif"], isim), {"sinif": satir["sinif"], "ad_soyad": isim, "yok": 0, "izinli": 0})
            girdi["izinli"] += 1
    liste = list(sayac.values())
    liste.sort(key=lambda x: (-x["yok"], -x["izinli"], x["sinif"], x["ad_soyad"]))
    return liste


@router.get("/rapor", response_class=HTMLResponse)
async def rapor(request: Request, baslangic: str | None = None, bitis: str | None = None, sinif_id: str | None = None):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        b, s = _rapor_araligi(baslangic, bitis)

        siniflar = [dict(r) for r in conn.execute("SELECT id, ad FROM siniflar WHERE aktif = 1 ORDER BY ad")]
        sinif_ad = None
        sinif_id_int = int(sinif_id) if sinif_id else None
        if sinif_id_int is not None:
            eslesme = conn.execute("SELECT ad FROM siniflar WHERE id = ?", (sinif_id_int,)).fetchone()
            sinif_ad = eslesme["ad"] if eslesme else None

        detay = _rapor_verisi(conn, b, s, sinif_ad)
        devamsizlik = _devamsizlik_sayaci(detay)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request, "admin_rapor.html",
        {
            "baslangic": b, "bitis": s, "siniflar": siniflar, "sinif_id": sinif_id_int,
            "detay": detay, "devamsizlik": devamsizlik,
        },
    )


def _csv_yanit(dosya_adi: str, basliklar: list[str], satirlar: list[list]) -> StreamingResponse:
    arabellek = io.StringIO()
    yazici = csv.writer(arabellek, delimiter=";")
    yazici.writerow(basliklar)
    yazici.writerows(satirlar)
    # utf-8-sig: Excel'in Türkçe karakterleri (ğşıöüç) BOM olmadan bozması engellenir.
    veri = arabellek.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([veri]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{dosya_adi}"'},
    )


@router.get("/rapor/csv")
async def rapor_csv(request: Request, tip: str, baslangic: str | None = None, bitis: str | None = None, sinif_id: str | None = None):
    if tip not in ("detay", "ozet"):
        raise HTTPException(400, "Geçersiz rapor tipi.")

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        b, s = _rapor_araligi(baslangic, bitis)
        sinif_ad = None
        if sinif_id:
            eslesme = conn.execute("SELECT ad FROM siniflar WHERE id = ?", (int(sinif_id),)).fetchone()
            sinif_ad = eslesme["ad"] if eslesme else None
        detay = _rapor_verisi(conn, b, s, sinif_ad)
    finally:
        conn.close()

    if tip == "detay":
        satirlar = [
            [d["tarih"], d["sinif"], d["ders_no"], d["durum_etiketi"],
             ", ".join(d["yok_isimleri"]), ", ".join(d["izinli_isimleri"]), d["kaynak_tahta"] or ""]
            for d in detay
        ]
        return _csv_yanit(
            f"yoklama_detay_{b}_{s}.csv",
            ["Tarih", "Sınıf", "Ders", "Durum", "Yok", "İzinli", "Kaynak tahta"],
            satirlar,
        )

    devamsizlik = _devamsizlik_sayaci(detay)
    satirlar = [[d["sinif"], d["ad_soyad"], d["yok"], d["izinli"]] for d in devamsizlik]
    return _csv_yanit(
        f"devamsizlik_ozeti_{b}_{s}.csv",
        ["Sınıf", "Öğrenci", "Yok sayısı", "İzinli sayısı"],
        satirlar,
    )
