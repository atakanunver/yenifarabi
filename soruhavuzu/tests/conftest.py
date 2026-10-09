import pytest

from soruhavuzu import vt


@pytest.fixture
def conn():
    c = vt.baglan("soru_havuzu_test")
    vt.sema_kur(c)
    with c.cursor() as cur:
        cur.execute("TRUNCATE soru, kaynak_birim, kazanim RESTART IDENTITY CASCADE")
    c.commit()
    yield c
    c.close()


ORNEK_SORU = {
    "ders": "matematik",
    "sinif": 12,
    "konu": "Logaritma",
    "soru": "log2(8) kaçtır?",
    "kisa_cevap": "3",
    "secenekler": ["2", "3", "4", "8"],
    "dogru_index": 1,
    "zorluk": 1,
    "kaynak": "Matematik 12, s. 40",
}
