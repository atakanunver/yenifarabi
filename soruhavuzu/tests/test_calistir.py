from soruhavuzu import calistir, zaman


def _sahte_saat():
    t = [0.0]

    def simdi():
        return t[0]

    return t, simdi


def test_paket_siniri_durur(monkeypatch, conn):
    monkeypatch.setattr(calistir.vt, "denetlenecekler", lambda c, n: [1])
    cagri = []
    calistir.denetle(conn, azami_paket=3, paket_fn=lambda c: cagri.append(1) or 5)
    assert len(cagri) == 3


def test_sure_siniri_durur(monkeypatch, conn):
    monkeypatch.setattr(calistir.vt, "denetlenecekler", lambda c, n: [1])
    t, simdi = _sahte_saat()

    def paket(c):
        t[0] += 600  # her paket 10 dk
        return 5

    sayac = []
    calistir.denetle(
        conn, azami_dk=25, paket_fn=lambda c: sayac.append(1) or paket(c), simdi=simdi
    )
    assert len(sayac) == 3  # 0,10,20 dk'da başladı; 30 dk >= 25 → dur


def test_ders_saati_baslayinca_durur(monkeypatch, conn):
    monkeypatch.setattr(calistir.vt, "denetlenecekler", lambda c, n: [1])
    durumlar = iter([True, True, False])
    monkeypatch.setattr(zaman, "uretim_serbest", lambda an=None: next(durumlar))
    sayac = []
    calistir.denetle(
        conn, ders_saati_kontrol=True, paket_fn=lambda c: sayac.append(1) or 5
    )
    assert len(sayac) == 2


def test_sinirsiz_denetle_bitince_cikar(monkeypatch, conn):
    monkeypatch.setattr(calistir.vt, "denetlenecekler", lambda c, n: [])
    assert calistir.denetle(conn, paket_fn=lambda c: 0) is None


def test_art_arda_uc_bos_cikar(monkeypatch, conn):
    monkeypatch.setattr(calistir.vt, "denetlenecekler", lambda c, n: [1])
    sayac = []
    calistir.denetle(conn, paket_fn=lambda c: sayac.append(1) or 0)
    assert len(sayac) == 3
