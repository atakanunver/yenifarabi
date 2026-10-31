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


def test_jeopardy_farkli_konu_ayni_kaynak_yedegi():
    # 4 farklı kaynak, her birinde 4 farklı konu adı ama 4 zorluk seviyesi var
    satirlar = []
    idx = 0
    for kid in range(1, 5):
        kaynak_adi = f"Biyoloji 9, s. {kid * 10}"
        for z in (1, 2, 3, 4):
            idx += 1
            satirlar.append((
                idx,
                f"Alt Konu {idx}",  # Her sorunun konusu farklı
                z,
                f"Soru {idx}",
                f"Cevap {idx}",
                ["A", "B", "C", "D"],
                0,
                kaynak_adi
            ))
    s = havuz.jeopardy_seti("biyoloji", 9, sorgu=_sahte(satirlar))
    assert s is not None and len(s) == 4
    assert all(len(k["questions"]) == 4 for k in s)
    assert [q["points"] for q in s[0]["questions"]] == [100, 200, 300, 400]


def test_sube_normalize():
    assert havuz.sube_normalize("9a") == "9-A"
    assert havuz.sube_normalize("9-a") == "9-A"
    assert havuz.sube_normalize("9/A") == "9-A"
    assert havuz.sube_normalize("10B") == "10-B"
    assert havuz.sube_normalize("11-c") == "11-C"
    assert havuz.sube_normalize("") == ""


def test_sube_ile_sorgulama_kullanilmamislari_onceler():
    yakalanan = []

    def sorgu(sql, p):
        yakalanan.append((sql, p))
        return []

    havuz.jeopardy_seti("matematik", 9, sorgu=sorgu, sube="9a")
    assert len(yakalanan) > 0
    sql, p = yakalanan[0]
    assert "soru_kullanim WHERE sube = %s" in sql
    assert "9-A" in p


def test_petek_ve_duello_sube_aktarir():
    yakalanan = []

    def sorgu(sql, p):
        yakalanan.append((sql, p))
        return [_satir("Konu", 1, i) for i in range(25)]

    p = havuz.petek_sorulari("fizik", 9, 19, sorgu=sorgu, sube="9b")
    assert p and len(p) == 19
    sql, params = yakalanan[0]
    assert "soru_kullanim WHERE sube = %s" in sql
    assert "9-B" in params




def test_sorulara_havuz_kimligi_eklenir():
    """'Soru hatalı' bildirimi için tahtaya soru kimliği (sid) gider."""
    ciftler = [(k, z) for k in ("Log", "Türev", "İntegral", "Limit") for z in (1, 2, 3, 4)]
    satirlar = [_satir(k, z, 100 + i) for i, (k, z) in enumerate(ciftler)]
    s = havuz.jeopardy_seti("matematik", 12, sorgu=_sahte(satirlar))
    assert {q["sid"] for k in s for q in k["questions"]} <= {100 + i for i in range(16)}
    assert all(isinstance(q["sid"], int) for k in s for q in k["questions"])
    petek = havuz.petek_sorulari("matematik", 12, 10, sorgu=_sahte(satirlar))
    assert all(isinstance(q["sid"], int) for q in petek)
