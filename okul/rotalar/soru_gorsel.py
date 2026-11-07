"""Öğrencinin erişebildiği arşiv sorusuna ait görsel."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from deps import db_conn, rol
from kaynaklar import KaynakHatasi
from kaynaklar.kazanim import _baglan

router = APIRouter()
KULLANICI = rol("ogrenci", "ogretmen", "yonetici")


def _gorebilir(conn, kullanici_id: int, soru_id: int) -> bool:
    # Henüz gösterilmemiş maraton sorularının görsellerini önceden açtırma.
    return conn.execute("""
        SELECT 1 FROM maraton_soru s JOIN maraton m ON m.id=s.maraton_id
          WHERE m.kullanici_id=? AND s.soru_id=? AND s.gosterim IS NOT NULL
        UNION ALL
        SELECT 1 FROM bilgi_cevap s JOIN bilgi_tur t ON t.id=s.tur_id
          WHERE t.kullanici_id=? AND s.soru_id=? AND s.sira <= COALESCE(
            (SELECT MIN(b.sira) FROM bilgi_cevap b WHERE b.tur_id=t.id AND b.cevap IS NULL), 999999)
        UNION ALL
        SELECT 1 FROM calisma_soru s WHERE s.kullanici_id=? AND s.soru_id=?
        LIMIT 1
    """, (kullanici_id, soru_id, kullanici_id, soru_id, kullanici_id, soru_id)).fetchone() is not None


def _gorsel(soru_id: int):
    with _baglan() as c, c.cursor() as cur:
        cur.execute("SELECT icerik, mime FROM soru_gorsel WHERE soru_id = %s", (soru_id,))
        r = cur.fetchone()
        return (bytes(r[0]), r[1]) if r else None


@router.get("/soru-gorsel/{soru_id}")
def soru_gorsel(soru_id: int, k=Depends(KULLANICI), conn=Depends(db_conn)):
    if soru_id < 1:
        raise HTTPException(404)
    if k["rol"] == "ogrenci":
        yetkili = _gorebilir(conn, k["id"], soru_id)
    elif k["rol"] == "ogretmen":
        yetkili = conn.execute("SELECT 1 FROM soru_inceleme WHERE ogretmen_id=? AND soru_id=? LIMIT 1", (k["id"], soru_id)).fetchone() is not None
    else:
        yetkili = True
    if not yetkili:
        raise HTTPException(404)
    try:
        veri = _gorsel(soru_id)
    except KaynakHatasi:
        raise HTTPException(503, "Soru görseli şu an alınamıyor.") from None
    if veri is None:
        raise HTTPException(404)
    return Response(content=veri[0], media_type=veri[1], headers={"Cache-Control": "private, max-age=300"})
