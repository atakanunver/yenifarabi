"""benchmark/ortak.py — recall_test.py ve soru_taslak.py'nin paylaştığı küçük
DB yardımcıları. Ayrı bir modül olmasının nedeni: iki betik de aynı bağlantı/
kitap-çözme mantığını birebir tekrarlıyordu."""

import psycopg2
from pgvector.psycopg2 import register_vector


def baglan(host: str, dbname: str, user: str):
    conn = psycopg2.connect(host=host, dbname=dbname, user=user)
    register_vector(conn)
    return conn


def kitap_idyi_coz(conn, kitap_id: int | None) -> int:
    with conn.cursor() as cur:
        if kitap_id is not None:
            cur.execute("SELECT id FROM kitap WHERE id = %s", (kitap_id,))
            r = cur.fetchone()
            if not r:
                raise SystemExit(f"kitap_id={kitap_id} bulunamadı.")
            return r[0]
        cur.execute("SELECT id, dosya_yolu FROM kitap")
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0][0]
        if not rows:
            raise SystemExit("kitap tablosu boş — önce embed_kitap.py çalıştırılmalı.")
        raise SystemExit(
            f"Birden fazla kitap var ({len(rows)}), --kitap-id ile seç: "
            + ", ".join(f"{i}={p}" for i, p in rows)
        )
