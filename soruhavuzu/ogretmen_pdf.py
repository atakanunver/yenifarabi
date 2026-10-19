"""soruhavuzu/ogretmen_pdf.py — öğretmenin okul portalından gönderdiği PDF'lerden soru havuzuna katkı.

Akış (yalnız 9-10-11; 12. sınıf donmuş): okul /api/soru-istek (X-Soru-Anahtar) → PDF → sayfa metni (PyMuPDF)
→ kaynak_birim (tur='kitap', anahtar 'ogretmen:<pdf>:<sayfa>') → Ollama ile 4 soru/sayfa (kitap istemi; yalnız
sayfa metninden) → gömme ile mükerrer eleme → şekil/grafik kapısı (uretici._gecerli) → AGY denetimi (yalnız bu
birimler) → onaylananlar havuzda 'onayli' → sonuç okula POST edilir. Okul kapalıysa ya da anahtar yoksa adım atlanır."""

import json
import urllib.request

import fitz

from soruhavuzu import denetci, dersler, okul_bildirim, tekrar, uretici, vt, zaman

TABAN = "http://127.0.0.1:9090"
MAKS_SAYFA = 40  # tek PDF'te işlenecek en çok sayfa (≈ 4 soru × 40; Ollama süresi sınırı)
MIN_METIN = 200


def _istek(yol: str, veri: dict | None = None, zaman_asimi: int = 60) -> bytes:
    istek = urllib.request.Request(
        TABAN + yol,
        data=None if veri is None else json.dumps(veri).encode("utf-8"),
        headers={"X-Soru-Anahtar": okul_bildirim.anahtar(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:
        return r.read()


def bekleyenler() -> list[dict]:
    if not okul_bildirim.anahtar():
        return []
    return json.loads(_istek("/api/soru-istek"))["istekler"]


def pdf_al(pdf_id: int) -> bytes:
    return _istek(f"/api/soru-istek/{pdf_id}/pdf", zaman_asimi=120)


def sonuc_bildir(pdf_id: int, durum: str, onayli: int = 0, red: int = 0, not_: str = "") -> None:
    try:
        _istek(f"/api/soru-istek/{pdf_id}/sonuc", {"durum": durum, "onayli": onayli, "red": red, "not": not_})
    except Exception as e:
        print(f"[ogretmen-pdf] sonuç bildirilemedi ({pdf_id}): {type(e).__name__}: {e}", flush=True)


def sayfa_birimleri(pdf: bytes, istek: dict, ders: str, sinif: int) -> list[dict]:
    """Seçilen sayfa aralığındaki yeterli metinli sayfalar → kaynak birimleri (taranmış sayfalar atlanır)."""
    birimler = []
    with fitz.open(stream=pdf, filetype="pdf") as belge:
        bas = istek.get("soru_bas") or 1
        bit = istek.get("soru_bit") or len(belge)
        for no in range(max(1, bas), min(bit, len(belge)) + 1):
            metin = belge[no - 1].get_text().strip()
            if len(metin) < MIN_METIN:
                continue
            birimler.append(
                {
                    "tur": "kitap",
                    "anahtar": f"ogretmen:{istek['id']}:{no}",
                    "ders": ders,
                    "sinif": sinif,
                    "etiket": f"{istek['baslik'][:60]} (öğretmen PDF), s. {no}",
                    "metin": metin[: 6000],
                }
            )
            if len(birimler) >= MAKS_SAYFA:
                break
    return birimler


def isle(conn, istek: dict, pdf: bytes, ureten=None, eleyici=None, denetle=None, ders_saati_kontrol: bool = True) -> dict:
    """Tek isteği işler → {'durum': 'bitti'|'hata'|'bekliyor', 'onayli', 'red', 'not'}."""
    ureten = ureten or uretici.uret
    denetle = denetle or denetci.paket_denetle
    try:
        sinif = int(str(istek["sinif"]).split("-", 1)[0])
    except ValueError:
        return {"durum": "hata", "onayli": 0, "red": 0, "not": "sınıf anlaşılamadı"}
    if sinif in vt.DONDURULMUS_SINIFLAR or sinif not in (9, 10, 11):
        return {"durum": "hata", "onayli": 0, "red": 0, "not": "bu sınıf için soru üretimi kapalı"}
    ders = dersler.ders_anahtari(istek["ders"])
    if ders is None or ders not in uretici.DERSLER:
        return {"durum": "hata", "onayli": 0, "red": 0, "not": f"ders eşlenemedi: {istek['ders']}"}
    birimler = sayfa_birimleri(pdf, istek, ders, sinif)
    if not birimler:
        return {"durum": "hata", "onayli": 0, "red": 0, "not": "PDF'te okunabilir metin yok (taranmış olabilir)"}
    eleyici = eleyici or _eleyici(conn)
    bidler, uretilen = [], 0
    for b in birimler:
        if ders_saati_kontrol and not zaman.uretim_serbest():
            return {"durum": "bekliyor", "onayli": 0, "red": 0, "not": "ders saati — sonra devam"}
        bid = vt.birim_ekle(conn, b["tur"], b["anahtar"], b["ders"], b["sinif"], b["etiket"], b["metin"])
        bid = bid or vt.birim_bul(conn, b["anahtar"])
        bidler.append(bid)
        try:
            for s in ureten(b):
                if not eleyici.kopya_mi(s["ders"], s["sinif"], s["soru"]):
                    vt.soru_ekle(conn, bid, s)
                    uretilen += 1
            vt.birim_isaretle(conn, bid, "islendi")
        except Exception as e:
            conn.rollback()
            vt.birim_isaretle(conn, bid, "hata", f"{type(e).__name__}: {e}"[:200])
    if not uretilen:
        return {"durum": "hata", "onayli": 0, "red": 0, "not": "metinden soru üretilemedi ya da hepsi mükerrer/şekil atıflı"}
    for _ in range(10):  # her pakette ≤100 soru; ilerleme yoksa dur
        if denetle(conn, 100, birimler=bidler) == 0:
            break
    with conn.cursor() as cur:
        cur.execute("SELECT durum, count(*) FROM soru WHERE birim_id = ANY(%s) GROUP BY 1", (bidler,))
        say = dict(cur.fetchall())
    if say.get("uretildi"):  # AGY yanıt vermediyse sonraki tura kalır
        return {"durum": "bekliyor", "onayli": say.get("onayli", 0), "red": say.get("red", 0), "not": "denetim bekliyor"}
    return {"durum": "bitti", "onayli": say.get("onayli", 0), "red": say.get("red", 0), "not": ""}


def _eleyici(conn):
    e = tekrar.Eleyici(tekrar._gomucu())
    e.yukle(conn)
    return e


def calistir(conn, ders_saati_kontrol: bool = True, **enj) -> list[dict]:
    """Bekleyen tüm istekleri işler. Okul kapalı/anahtarsızsa [] döner; üretim turunu asla bozmaz."""
    try:
        istekler = enj.pop("bekleyenler", bekleyenler)()
    except Exception as e:
        print(f"[ogretmen-pdf] okul okunamadı: {type(e).__name__}: {e}", flush=True)
        return []
    sonuc = []
    for ist in istekler:
        if ders_saati_kontrol and not zaman.uretim_serbest():
            print("[ogretmen-pdf] ders saati — durduruldu", flush=True)
            break
        al, bildir = enj.get("pdf_al", pdf_al), enj.get("sonuc_bildir", sonuc_bildir)
        bildir(ist["id"], "isleniyor")
        try:
            r = isle(conn, ist, al(ist["id"]), ders_saati_kontrol=ders_saati_kontrol,
                     **{k: v for k, v in enj.items() if k in ("ureten", "eleyici", "denetle")})
        except Exception as e:
            conn.rollback()
            r = {"durum": "hata", "onayli": 0, "red": 0, "not": f"{type(e).__name__}: {e}"[:200]}
        bildir(ist["id"], r["durum"], r["onayli"], r["red"], r["not"])
        print(f"[ogretmen-pdf] #{ist['id']} {ist['sinif']} {ist['ders']}: {r}", flush=True)
        sonuc.append({"id": ist["id"], **r})
    return sonuc
