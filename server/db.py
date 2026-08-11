"""server/db.py — PostgreSQL bağlantı havuzu.

benchmark/ortak.py'nin tek-bağlantı deseninin sunucu (çok istek, eşzamanlı)
karşılığı — her istek için yeni bağlantı açmak yerine küçük bir havuzdan
alıp geri veriyoruz.
"""

import psycopg2.pool
from pgvector.psycopg2 import register_vector

_havuz: psycopg2.pool.SimpleConnectionPool | None = None


def baslat(host: str, dbname: str, user: str, min_conn: int = 1, max_conn: int = 5) -> None:
    global _havuz
    _havuz = psycopg2.pool.SimpleConnectionPool(min_conn, max_conn, host=host, dbname=dbname, user=user)


def kapat() -> None:
    global _havuz
    if _havuz:
        _havuz.closeall()
        _havuz = None


class baglanti:
    """`with db.baglanti() as conn:` — havuzdan alır, iş bitince geri verir."""

    def __enter__(self):
        if _havuz is None:
            raise RuntimeError("db.baslat() çağrılmadan bağlantı istendi")
        self.conn = _havuz.getconn()
        register_vector(self.conn)
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        _havuz.putconn(self.conn)
