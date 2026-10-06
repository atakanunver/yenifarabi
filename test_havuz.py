import havuz


def _sahte(satirlar):
    return lambda sql, p: satirlar


def _satir(konu, zorluk, i):
    # id, konu, zorluk, soru, kisa_cevap, secenekler, dogru_index, kaynak
    return (
        i,
        konu,
        zorluk,
        f"S{i}",
        f"C{i}",
        ["a", "b", "c", "d"],
        2,
        "Matematik 12, s. 5",
    )


def test_jeopardy_dort_konu_dort_zorluk():
    ciftler = [
        (k, z)
        for k in ("Log", "Türev", "İntegral", "Limit", "Fazla")
        for z in (1, 2, 3, 4)
    ]
    satirlar = [_satir(k, z, i) for i, (k, z) in enumerate(ciftler)]
    s = havuz.jeopardy_seti("matematik", 12, sorgu=_sahte(satirlar))
    assert len(s) == 4 and all(len(k["questions"]) == 4 for k in s)
    assert [q["points"] for q in s[0]["questions"]] == [100, 200, 300, 400]
    assert s[0]["questions"][0]["answered"] is False


def test_jeopardy_yetersizse_none():
    assert (
        havuz.jeopardy_seti("matematik", 12, sorgu=_sahte([_satir("Log", 1, 1)]))
        is None
    )


def test_petekler_benzersiz_ve_dogru_sik_metni():
    satirlar = [_satir("Log", 1 + i % 4, i) for i in range(25)]
    p = havuz.petek_sorulari("matematik", 12, 19, sorgu=_sahte(satirlar))
    assert len(p) == 19 and len({x["q"] for x in p}) == 19 and p[0]["a"] == "c"


def test_petek_yetersizse_none():
    assert (
        havuz.petek_sorulari("matematik", 12, 19, sorgu=_sahte([_satir("Log", 1, 1)]))
        is None
    )


def test_db_hatasinda_none():
    def patla(sql, p):
        raise RuntimeError("db yok")

    assert havuz.jeopardy_seti("matematik", 12, sorgu=patla) is None


def test_yalnizca_onayli_sorgulanir():
    yakalanan = []

    def kaydet(sql, p):
        yakalanan.append(sql)
        return []

    havuz.jeopardy_seti("matematik", 12, sorgu=kaydet)
    assert "durum = 'onayli'" in yakalanan[0]
