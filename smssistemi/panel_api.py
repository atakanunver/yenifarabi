"""smssistemi/panel_api.py — dashboard'un çektiği veli mesajları API'si.

Kimlik: X-Sms-Panel-Key başlığı = config/panel.json {"anahtar": ...}.
Dosya yoksa/boşsa 503 (fail-closed). Tam telefon numarası yanıta ÇIKMAZ.
"""

from __future__ import annotations

import hmac
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException

import db
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
    }


@router.get("/veli-mesajlari", dependencies=[Depends(anahtar_dogrula)])
def liste(okunmamis: int = 0, limit: int = 100):
    limit = max(1, min(int(limit), 500))
    sorgu = "SELECT * FROM veli_mesajlari"
    if okunmamis:
        sorgu += " WHERE okundu = 0"
    sorgu += " ORDER BY modem_zaman DESC, id DESC LIMIT ?"
    conn = db.baglanti()
    try:
        return {"mesajlar": [_satir(r) for r in conn.execute(sorgu, (limit,)).fetchall()]}
    finally:
        conn.close()


@router.get("/veli-mesajlari/sayac", dependencies=[Depends(anahtar_dogrula)])
def sayac():
    conn = db.baglanti()
    try:
        r = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(cikis_talebi), 0) AS c "
            "FROM veli_mesajlari WHERE okundu = 0"
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
