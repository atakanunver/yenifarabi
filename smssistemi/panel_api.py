"""smssistemi/panel_api.py — dashboard'un çektiği veli mesajları API'si.

Kimlik: X-Sms-Panel-Key başlığı = config/panel.json {"anahtar": ...}.
Dosya yoksa/boşsa 503 (fail-closed). Tam telefon numarası yanıta ÇIKMAZ.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import db
import otomasyon
import veli_mesaj

router = APIRouter(prefix="/api/panel")

PANEL_AYAR_YOLU = Path(__file__).resolve().parent / "config" / "panel.json"


def _anahtar() -> str:
    try:
        return str(json.loads(PANEL_AYAR_YOLU.read_text(encoding="utf-8")).get("anahtar") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def anahtar_dogrula(x_sms_panel_key: str | None = Header(default=None, alias="X-Sms-Panel-Key")) -> None:
    beklenen = _anahtar()
    if not beklenen:
        raise HTTPException(status_code=503, detail="Panel anahtarı tanımlı değil.")
    if not x_sms_panel_key or not hmac.compare_digest(beklenen, x_sms_panel_key):
        raise HTTPException(status_code=401, detail="Geçersiz ya da eksik panel anahtarı")


def _satir(r) -> dict:
    return {
        "id": r["id"],
        "kisi_ad": r["kisi_ad"],
        "kisi_tur": r["kisi_tur"],
        "sinif": r["sinif"],
        "telefon": veli_mesaj.telefon_maskele(r["telefon"]),
        "metin": r["metin"],
        "zaman": r["modem_zaman"],
        "cikis_talebi": r["cikis_talebi"],
        "okundu": r["okundu"],
        "spam_neden": r["spam_neden"] if r["spam"] else None,
    }


@router.get("/veli-mesajlari", dependencies=[Depends(anahtar_dogrula)])
def liste(okunmamis: int = 0, limit: int = 100, spam: int = 0):
    limit = max(1, min(int(limit), 500))
    sorgu = f"SELECT * FROM veli_mesajlari WHERE spam = {1 if spam else 0}"
    if okunmamis:
        sorgu += " AND okundu = 0"
    sorgu += " ORDER BY modem_zaman DESC, id DESC LIMIT ?"
    conn = db.baglanti()
    try:
        return {"mesajlar": [_satir(r) for r in conn.execute(sorgu, (limit,)).fetchall()]}
    finally:
        conn.close()


_OTOMASYON_ALANLAR = ("durum", "veli_sms_sayisi", "basarili_sayisi", "hatali_sayisi", "dahil_sinif_sayisi",
                      "haric_sinif_sayisi", "haric_sebepleri")


@router.get("/otomasyon-durum", dependencies=[Depends(anahtar_dogrula)])
def otomasyon_durum():
    """Bugünkü devamsızlık SMS'i çalışmalarının ÖZETİ (yalnız sayılar; isim/telefon yok). Çalışmadıysa None."""
    bugun = otomasyon.bugun_istanbul().isoformat()
    conn = db.baglanti()
    try:
        def ozet(sonuc):
            return {k: sonuc.get(k) for k in _OTOMASYON_ALANLAR} if sonuc and sonuc.get("tarih") == bugun else None

        # ilk_ders/ogle: dashboard Bugün kartının okuduğu eski anahtarlar (taşınan kural 1/2)
        yanit = {"tarih": bugun}
        for servis in ("ilk_ders", "ogle"):
            yanit[servis] = ozet(otomasyon.son_sonuc_oku(conn, servis))
        yanit["kurallar"] = [
            {"id": k["id"], "ad": k["ad"], "saat": k["saat"], "ders_no": k["ders_no"], "aktif": k["aktif"],
             "bugun": ozet(k["son_sonuc"])}
            for k in otomasyon.kurallar(conn)
        ]
        return yanit
    finally:
        conn.close()


@router.get("/veli-mesajlari/sayac", dependencies=[Depends(anahtar_dogrula)])
def sayac():
    conn = db.baglanti()
    try:
        r = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(cikis_talebi), 0) AS c "
            "FROM veli_mesajlari WHERE okundu = 0 AND spam = 0"
        ).fetchone()
        return {"okunmamis": r["n"], "cikis_talebi_okunmamis": r["c"]}
    finally:
        conn.close()


@router.post("/veli-mesajlari/{mesaj_id}/okundu", dependencies=[Depends(anahtar_dogrula)])
def okundu(mesaj_id: int):
    conn = db.baglanti()
    try:
        cur = conn.execute("UPDATE veli_mesajlari SET okundu = 1 WHERE id = ?", (mesaj_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mesaj bulunamadı.")
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/veli-mesajlari/{mesaj_id}", dependencies=[Depends(anahtar_dogrula)])
def sil(mesaj_id: int):
    conn = db.baglanti()
    try:
        cur = conn.execute("DELETE FROM veli_mesajlari WHERE id = ?", (mesaj_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mesaj bulunamadı.")
        return {"ok": True}
    finally:
        conn.close()


class EngelGovde(BaseModel):
    neden: str | None = None


def _idare_numaralari() -> set[str]:
    import arac_api  # geç içe aktarma (döngüsel bağımlılık riski)

    try:
        return {veli_mesaj.ulusal(tel) for _ad, tel in arac_api.yonetim_alicilari()}
    except Exception:  # noqa: BLE001 - fail-closed: idare listesi okunamazsa engelleme yapılmaz
        raise HTTPException(status_code=503, detail="İdare numaraları okunamadı.") from None


@router.post("/veli-mesajlari/{mesaj_id}/engelle", dependencies=[Depends(anahtar_dogrula)])
def engelle(mesaj_id: int, govde: EngelGovde | None = None):
    neden = ((govde.neden if govde else None) or "").strip()[:80] or None
    idare = _idare_numaralari()
    conn = db.baglanti()
    try:
        m = conn.execute("SELECT telefon FROM veli_mesajlari WHERE id = ?", (mesaj_id,)).fetchone()
        if m is None:
            raise HTTPException(status_code=404, detail="Mesaj bulunamadı.")
        tel = m["telefon"]
        if tel in idare:
            raise HTTPException(status_code=409, detail="İdare numarası engellenemez.")
        conn.execute(
            "INSERT OR IGNORE INTO engelli_gonderenler (telefon, neden, zaman) VALUES (?, ?, ?)",
            (tel, neden, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        cur = conn.execute(
            "UPDATE veli_mesajlari SET spam = 1, spam_neden = 'engelli', okundu = 1 WHERE telefon = ?",
            (tel,),
        )
        conn.commit()
        return {"ok": True, "etkilenen": cur.rowcount}
    finally:
        conn.close()


@router.post("/veli-mesajlari/{mesaj_id}/engeli-kaldir", dependencies=[Depends(anahtar_dogrula)])
def engeli_kaldir(mesaj_id: int):
    conn = db.baglanti()
    try:
        m = conn.execute(
            "SELECT telefon, spam, spam_neden FROM veli_mesajlari WHERE id = ?", (mesaj_id,)
        ).fetchone()
        if m is None or not m["spam"]:
            raise HTTPException(status_code=404, detail="Engellenmiş mesaj bulunamadı.")
        if m["spam_neden"] == "engelli":
            conn.execute("DELETE FROM engelli_gonderenler WHERE telefon = ?", (m["telefon"],))
            cur = conn.execute(
                "UPDATE veli_mesajlari SET spam = 0, spam_neden = NULL, okundu = 0 "
                "WHERE telefon = ? AND spam_neden = 'engelli'",
                (m["telefon"],),
            )
        else:  # 'sistem numarası': yalnızca bu mesaj
            cur = conn.execute(
                "UPDATE veli_mesajlari SET spam = 0, spam_neden = NULL, okundu = 0 WHERE id = ?",
                (mesaj_id,),
            )
        conn.commit()
        return {"ok": True, "etkilenen": cur.rowcount}
    finally:
        conn.close()
