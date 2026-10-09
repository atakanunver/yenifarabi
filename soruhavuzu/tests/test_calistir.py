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


def test_uret_kazanim_dongusu_kaydeder_ve_kaynak_yok_isaretler(conn, monkeypatch):
    from datetime import date
    from soruhavuzu import calistir, kazanimlar, tekrar, vt
    a = vt.kazanim_upsert(conn, {"sinif": 10, "ders": "matematik", "hafta": 5, "kod": None, "metin": "alan"})
    b = vt.kazanim_upsert(conn, {"sinif": 10, "ders": "matematik", "hafta": 5, "kod": None, "metin": "kaynaksız"})
    monkeypatch.setattr(kazanimlar, "haftalar", lambda *_: {5: date(2026, 10, 12)})
    monkeypatch.setattr(tekrar, "_gomucu", lambda: None)
    monkeypatch.setattr(tekrar.Eleyici, "yukle", lambda self, c: None)
    monkeypatch.setattr(tekrar.Eleyici, "kopya_mi", lambda self, d, s, q: False)
    monkeypatch.setattr(calistir, "denetle", lambda *a, **k: None)
    bulucu = lambda fc, g, sinif, ders, metin: None if metin == "kaynaksız" else {
        "etiket": "Matematik 10, s. 5", "metin": "M", "chunk_idler": [1], "skor": 0.8}
    sorular = [{"ders": "matematik", "sinif": 10, "konu": "alan", "soru": f"q{i}", "kisa_cevap": "x",
                "secenekler": ["a", "b", "c", "d"], "dogru_index": 0, "zorluk": 1,
                "kaynak": "Matematik 10, s. 5"} for i in range(5)]
    cagri = {"n": 0}

    def ureten(k, kay):
        cagri["n"] += 1
        return [dict(s, soru=f"{s['soru']}-{cagri['n']}") for s in sorular]
    calistir.uret(conn, ders_saati_kontrol=False, farabi_conn=object(), bulucu=bulucu, ureten=ureten,
                  bugun=date(2026, 10, 13))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru WHERE kazanim_id=%s AND kazanim_kaynak='uretim'", (a,))
        assert cur.fetchone()[0] >= 10
        cur.execute("SELECT durum FROM kazanim WHERE id=%s", (b,))
        assert cur.fetchone()[0] == "kaynak_yok"


def test_uret_bulucu_hatasinda_farabi_baglantisi_rollback_edilir(conn, monkeypatch):
    """farabi DB sorgusu hata verirse bağlantı 'aborted' kalıp sonraki kazanımları da bozmasın."""
    from datetime import date

    from soruhavuzu import calistir, kazanimlar, tekrar, vt

    vt.kazanim_upsert(conn, {"sinif": 10, "ders": "matematik", "hafta": 5, "kod": None, "metin": "alan"})
    monkeypatch.setattr(kazanimlar, "haftalar", lambda *_: {5: date(2026, 10, 12)})
    monkeypatch.setattr(tekrar, "_gomucu", lambda: None)
    monkeypatch.setattr(tekrar.Eleyici, "yukle", lambda self, c: None)
    monkeypatch.setattr(calistir, "denetle", lambda *a, **k: None)

    class FarabiConn:
        rollback_sayisi = 0

        def rollback(self):
            FarabiConn.rollback_sayisi += 1

    def bulucu(*a, **k):
        raise RuntimeError("farabi DB koptu")

    calistir.uret(conn, ders_saati_kontrol=False, farabi_conn=FarabiConn(), bulucu=bulucu,
                  ureten=lambda k, kay: [], bugun=date(2026, 10, 13))
    assert FarabiConn.rollback_sayisi >= 1


def test_isaretle_son_kazanimi_yazar(tmp_path, monkeypatch):
    import json

    hedef = tmp_path / "uret_durum.json"
    monkeypatch.setattr(calistir, "DURUM_DOSYASI", hedef)
    calistir._isaretle({"id": 42, "sinif": 10, "ders": "matematik", "hafta": 3}, "uretim", 5)
    veri = json.loads(hedef.read_text(encoding="utf-8"))
    assert veri["son_kazanim_id"] == 42
    assert veri["son_durum"] == "uretim"
    assert veri["son_eklenen"] == 5


def test_isaretle_yazilamazsa_uretimi_durdurmaz(tmp_path, monkeypatch):
    engel = tmp_path / "dosya"
    engel.write_text("x", encoding="utf-8")  # üst dizin bir dosya: mkdir başarısız olur
    monkeypatch.setattr(calistir, "DURUM_DOSYASI", engel / "uret_durum.json")
    calistir._isaretle({"id": 1, "sinif": 9, "ders": "fizik", "hafta": 1}, "kaynak_yok", 0)
