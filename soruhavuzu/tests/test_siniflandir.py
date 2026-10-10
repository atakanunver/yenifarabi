import json
from datetime import date

import numpy as np

from soruhavuzu import calistir, kazanimlar, siniflandir, tekrar, vt, zaman
from soruhavuzu.tests.conftest import ORNEK_SORU


class SahteGomucu:
    """'alan' -> [1,0], 'açı' -> [0,1], diğer -> [0.6,0.6] normalize."""

    def encode(self, metinler, normalize_embeddings=True):
        cikti = []
        for m in metinler:
            v = (
                np.array([1.0, 0.0]) if "alan" in m
                else np.array([0.0, 1.0]) if "açı" in m
                else np.array([0.6, 0.6])
            )
            cikti.append(v / np.linalg.norm(v))
        return cikti


def _hazirla(conn, sorular=("Üçgenin alanı?", "Dış açı kaç derece?")):
    ka = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 1, "kod": None, "metin": "alan hesabı"})
    kb = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 2, "kod": None, "metin": "Dış açı"})
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "m")
    ids = [vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": q}) for q in sorular]
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli'")
    conn.commit()
    return ka, kb, ids


def _satirlar(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, kazanim_id, kazanim_kaynak, kazanim_skor, kazanim_siniflandirma_at "
            "FROM soru ORDER BY id"
        )
        return cur.fetchall()


def _cagir(yanit, sayac=None):
    def f(mesajlar):
        if sayac is not None:
            sayac.append(mesajlar)
        return yanit if isinstance(yanit, str) else json.dumps(yanit)
    return f


def test_secim_yazilir_kaynak_llm(conn):
    ka, kb, ids = _hazirla(conn)
    s = siniflandir.calistir(
        conn, SahteGomucu(), ders_saati_kontrol=False,
        cagir=_cagir({"kararlar": [{"no": 1, "secim": 1}, {"no": 2, "secim": 1}]}),
    )
    assert s["baglanan"] == 2 and s["hicbiri"] == 0 and s["islenen"] == 2
    r = _satirlar(conn)
    assert (r[0][1], r[0][2]) == (ka, "llm") and r[0][3] == 1.0 and r[0][4] is not None
    assert (r[1][1], r[1][2]) == (kb, "llm")


def test_sifir_yalnizca_isaret(conn):
    _hazirla(conn)
    s = siniflandir.calistir(
        conn, SahteGomucu(), ders_saati_kontrol=False,
        cagir=_cagir({"kararlar": [{"no": 1, "secim": 0}, {"no": 2, "secim": 0}]}),
    )
    assert s["hicbiri"] == 2 and s["baglanan"] == 0
    for r in _satirlar(conn):
        assert r[1] is None and r[2] is None and r[4] is not None


def test_bozuk_yanit_dokunmaz_uc_bozukta_isaretler(conn):
    _hazirla(conn)
    sayac = []
    s = siniflandir.calistir(conn, SahteGomucu(), ders_saati_kontrol=False, cagir=_cagir("bozuk{", sayac))
    assert len(sayac) == 3 and s["bozuk_parti"] == 1 and s["baglanan"] == 0
    for r in _satirlar(conn):
        assert r[1] is None and r[4] is not None


def test_eksik_yanit_bozuk_sayilir_ve_dokunulmaz(conn):
    _hazirla(conn)
    sayac = []
    # ilk deneme eksik (2. soru yok), ikinci bozuk, üçüncüde düzgün: işaretlenmeden yazılmalı
    tam = {"kararlar": [{"no": 1, "secim": 1}, {"no": 2, "secim": 0}]}
    yanitlar = iter([{"kararlar": [{"no": 1, "secim": 1}]}, "x", tam])
    s = siniflandir.calistir(
        conn, SahteGomucu(), ders_saati_kontrol=False,
        cagir=lambda m: sayac.append(1) or (lambda y: y if isinstance(y, str) else json.dumps(y))(next(yanitlar)),
    )
    assert len(sayac) == 3 and s["bozuk_parti"] == 0 and s["baglanan"] == 1 and s["hicbiri"] == 1


def test_kuru_yazmaz(conn, capsys):
    _hazirla(conn)
    siniflandir.calistir(
        conn, SahteGomucu(), kuru=True, ders_saati_kontrol=False,
        cagir=_cagir({"kararlar": [{"no": 1, "secim": 1}, {"no": 2, "secim": 2}]}),
    )
    for r in _satirlar(conn):
        assert r[1] is None and r[2] is None and r[4] is None
    assert "Üçgenin alanı?" in capsys.readouterr().out


def test_ders_saati_kapaliysa_hemen_doner(conn, monkeypatch, capsys):
    _hazirla(conn)
    monkeypatch.setattr(zaman, "uretim_serbest", lambda an=None: False)
    sayac = []
    s = siniflandir.calistir(conn, SahteGomucu(), cagir=_cagir({"kararlar": []}, sayac))
    assert sayac == [] and s["islenen"] == 0
    assert "ders saati — durduruldu" in capsys.readouterr().out


def test_kazanimsiz_ders_ve_islenmis_atlanir(conn):
    ka, kb, ids = _hazirla(conn)
    bid = vt.birim_ekle(conn, "kitap", "k:2", "fizik", 12, "E", "m")
    vt.soru_ekle(conn, bid, {**ORNEK_SORU, "ders": "fizik", "soru": "Hız?"})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli'")
        cur.execute("UPDATE soru SET kazanim_siniflandirma_at=now() WHERE id=%s", (ids[1],))
    conn.commit()
    sayac = []
    s = siniflandir.calistir(
        conn, SahteGomucu(), ders_saati_kontrol=False,
        cagir=_cagir({"kararlar": [{"no": 1, "secim": 1}]}, sayac),
    )
    assert s["islenen"] == 1 and s["baglanan"] == 1


def test_uret_bitince_siniflandir_cagrilir(conn, monkeypatch):
    monkeypatch.setattr(kazanimlar, "haftalar", lambda *_: {5: date(2026, 10, 12)})
    monkeypatch.setattr(tekrar, "_gomucu", lambda: "G")
    monkeypatch.setattr(tekrar.Eleyici, "yukle", lambda self, c: None)
    monkeypatch.setattr(calistir, "denetle", lambda *a, **k: None)
    cagrilar = []
    monkeypatch.setattr(calistir.siniflandir, "calistir", lambda *a, **k: cagrilar.append((a, k)))
    calistir.uret(conn, ders_saati_kontrol=False, farabi_conn=object(), bulucu=lambda *a: None,
                  ureten=lambda *a: [], bugun=date(2026, 10, 13), denetim=False)
    assert len(cagrilar) == 1 and cagrilar[0][0][1] == "G"
    assert cagrilar[0][1]["ders_saati_kontrol"] is False
