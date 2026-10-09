"""secici: kazanim_id ile eşleşen onaylı sorular benzerlik aramasından önce gelir (gerçek DB'ye bağlanmaz)."""

from kazanimtest import secici


class SahteImlec:
    def __init__(self, satirlar):
        self.satirlar = satirlar
        self.sorgular = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sorgular.append((sql, params))

    def fetchall(self):
        return self.satirlar


class SahteBaglanti:
    def __init__(self, satirlar):
        self.imlec = SahteImlec(satirlar)

    def cursor(self, **kw):
        return self.imlec


def _satir(i):
    return {"id": i, "konu": "k", "soru": f"S{i}?", "secenekler": ["a", "b", "c", "d"],
            "dogru_index": 2, "kaynak": "Kimya 9, s. 3"}


def _aday(i, kaynak="havuz"):
    return {"kimlik": f"{kaynak}:{i}", "kaynak": kaynak, "db_id": i, "soru": f"S{i}?",
            "secenekler": ["a", "b", "c", "d"], "dogru_index": 0, "etiket": "k", "benzerlik": 0.5}


def test_kazanim_adaylari_metinleri_boler_ve_sekli_korur():
    conn = SahteBaglanti([_satir(3), _satir(4)])
    r = secici.kazanim_adaylari(conn, 9, "kimya", "Hücre\nZar\n", 5)
    sql, params = conn.imlec.sorgular[0]
    assert "kazanim_id" in sql and "durum = 'onayli'" in sql
    assert params[:3] == (9, "kimya", ["Hücre", "Zar"]) and params[3] == 5
    assert [a["kimlik"] for a in r] == ["havuz:3", "havuz:4"]
    assert r[0]["benzerlik"] == 1.0 and r[0]["dogru_index"] == 2 and r[0]["kaynak"] == "havuz"
    assert set(r[0]) >= {"kimlik", "kaynak", "db_id", "soru", "secenekler", "dogru_index", "etiket", "benzerlik"}


def test_kazanim_adaylari_bos_girdi_sorgu_yapmaz():
    conn = SahteBaglanti([])
    assert secici.kazanim_adaylari(conn, 9, "kimya", " \n", 5) == []
    assert secici.kazanim_adaylari(None, 9, "kimya", "x", 5) == []
    assert conn.imlec.sorgular == []


def test_adaylar_kazanim_id_once_sonra_benzerlik_tekrarsiz(monkeypatch):
    monkeypatch.setattr(secici, "vektor", lambda m, model=None: [0.0])
    monkeypatch.setattr(secici, "meb_adaylari", lambda *a: [])
    monkeypatch.setattr(secici, "kazanim_adaylari", lambda c, d, de, km, lim: [_aday(1), _aday(2)])
    monkeypatch.setattr(secici, "havuz_adaylari",
                        lambda c, d, de, v, lim, model=None: [_aday(i) for i in (2, 7, 8, 9, 10)][:lim])
    r = secici.adaylar(None, object(), 9, "kimya", "k", azami=5)
    assert [a["db_id"] for a in r] == [1, 2, 7, 8, 9]
