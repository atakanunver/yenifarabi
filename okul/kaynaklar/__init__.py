"""Dış, salt-okunur veri kaynakları (pano DB, Postgres, ders programı, SMS servisi)."""


class KaynakHatasi(Exception):
    """Dış kaynağa ulaşılamadı; arayüz ilgili kartta 'şu an alınamıyor' gösterir."""
