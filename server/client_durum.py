"""server/client_durum.py — 10 tahtaya ölçekleme: merkezi tahta durum takibi
(analiz raporu §5/§6, kullanıcı onayı 2026-08-18).

Her tahta periyodik olarak hafif bir heartbeat gönderir — derslik, kendi git
commit kısa hash'i, hostname, IP. Bu modül main.py'nin Live oturumuna/ses
döngüsüne HİÇ dokunmaz ve tahtadan bağımsız, ayrı bir cron/systemd timer'dan
çağrılır (client'ın kendi kodunda DEĞİL) — "Farabi asla dersi bozmaz" (CLAUDE.md
Kural 2): heartbeat'in gecikmesi/başarısızlığı dersi hiçbir şekilde etkilemez.

DURUM burada yalnızca "tahta ağda göründü ve heartbeat gönderdi" anlamına
gelir, "Farabi (main.py) o an çalışıyor" anlamına GELMEZ — bunlar ayrı
sinyallerdir (main.py'nin kendisi bu uca hiç dokunmuyor, bu yüzden
uygulama kapalıyken de son bilinen heartbeat DB'de kalır).
"""

from fastapi import APIRouter
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

import db

router = APIRouter()


class Heartbeat(BaseModel):
    derslik: str = Field(..., max_length=50)
    commit: str = Field("", max_length=40)
    hostname: str = Field("", max_length=100)
    ip: str = Field("", max_length=45)


@router.post("/api/client/heartbeat")
def heartbeat(istek: Heartbeat):
    """Loglama gibi: hata olursa yut, dersi/tahtayı hiçbir şekilde etkileme
    (rag.py::_logla ile aynı ilke — bkz. modül docstring'i)."""
    try:
        with db.baglanti() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tahta_durum (derslik, commit_hash, hostname, ip, son_heartbeat)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (derslik) DO UPDATE SET
                        commit_hash = EXCLUDED.commit_hash,
                        hostname = EXCLUDED.hostname,
                        ip = EXCLUDED.ip,
                        son_heartbeat = now()
                    """,
                    (istek.derslik, istek.commit, istek.hostname, istek.ip),
                )
            conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "hata", "detay": f"{type(e).__name__}"}


@router.get("/api/client/durum")
def durum_listesi():
    """Tüm tahtaların son bilinen durumu — farabi-status CLI'sının okuyacağı uç."""
    with db.baglanti() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT derslik, commit_hash, hostname, ip, son_heartbeat "
                "FROM tahta_durum ORDER BY derslik"
            )
            return cur.fetchall()
