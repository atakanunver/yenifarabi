import pymupdf
import pytest

from soruhavuzu import katki

KATKI = {"id": 7, "sinif": 9, "ders": "biyoloji", "baslik": "Hucre testi", "cevap": "BA"}


def _pdf(satirlar_sayfalari, iki_sutun=False):
    """Her sayfa satır listesi; iki_sutun'da ikinci yarı sağ sütuna yazılır."""
    d = pymupdf.open()
    for satirlar in satirlar_sayfalari:
        p = d.new_page()
        p.insert_text((40, 30), "Okul Biyoloji Tarama", fontsize=9)  # her sayfada üst bilgi
        yari = len(satirlar) // 2 if iki_sutun else len(satirlar)
        for i, s in enumerate(satirlar):
            x, y = (40, 80 + 16 * i) if i < yari else (320, 80 + 16 * (i - yari))
            if isinstance(s, tuple):  # yan yana şıklar: [(x, metin), ...]
                for dx, m in s:
                    p.insert_text((x + dx, y), m, fontsize=10)
            else:
                p.insert_text((x, y), s, fontsize=10)
    b = d.tobytes()
    d.close()
    return b


SAYFA = [
    "1. Hucrenin enerji merkezi hangisidir?",
    "A) Ribozom", "B) Mitokondri", "C) Golgi", "D) Lizozom",
    "2. Fotosentez hangi organelde olur?",
    ((0, "A) Kloroplast"), (120, "B) Koful")),
    ((0, "C) Sentrozom"), (120, "D) Cekirdek")),
]


def test_hazirla_metin_sorulari():
    s = katki.hazirla(_pdf([SAYFA]), "BA")
    assert [x["no"] for x in s] == [1, 2]
    assert s[0]["soru"] == "Hucrenin enerji merkezi hangisidir?"
    assert s[0]["secenekler"] == ["Ribozom", "Mitokondri", "Golgi", "Lizozom"] and s[0]["dogru_index"] == 1
    assert s[1]["secenekler"] == ["Kloroplast", "Koful", "Sentrozom", "Cekirdek"]  # yan yana şıklar sıralı
    assert s[1]["kisa_cevap"] == "Kloroplast"
    assert s[0]["gorsel"].startswith(b"\x89PNG") and s[0]["sayfa"] == 1


def test_anahtar_pdf_icinde():
    s = katki.hazirla(_pdf([SAYFA + ["CEVAP ANAHTARI", "1-B 2-A"]]), "")
    assert [x["dogru_index"] for x in s] == [1, 0]
    assert "CEVAP" not in s[1]["secenekler"][-1]  # anahtar son şıkka karışmaz


def test_iki_sutun_ve_sayfa_gecisi():
    sol = ["1. Birinci soru metni burada mi?", "A) a1", "B) b1", "C) c1", "D) d1"]
    sag = ["2. Ikinci soru metni burada mi?", "A) a2", "B) b2", "C) c2", "D) d2"]
    s = katki.hazirla(_pdf([sol + sag, ["3. Ucuncu soru metni burada mi?", "A) a3", "B) b3", "C) c3", "D) d3"]],
                           iki_sutun=True), "ABC")
    assert [x["secenekler"][0] for x in s] == ["a1", "a2", "a3"]


def test_sekil_atifli_soru_yalniz_gorsel():
    sayfa = ["1. Yukaridaki tabloya gore asagidaki ifadelerden hangisi kesinlikle dogrudur?",
             "A) Birinci ifade", "B) Ikinci ifade", "C) Ucuncu ifade", "D) Dorduncu ifade"]
    s = katki.hazirla(_pdf([sayfa]), "C")
    assert s[0]["soru"] == katki.GORSEL_YER and s[0]["secenekler"][0] == "A seçeneği"


@pytest.mark.parametrize(
    "pdf, cevap, mesaj",
    [
        (_pdf([SAYFA]), "BAC", "2 soru bulundu, cevap anahtarında 3"),
        (_pdf([SAYFA]), "", "Cevap anahtarı yok"),
        (_pdf([SAYFA]), "BE", "cevabı E"),
        (_pdf([["1. Sikki olmayan bir soru metni burada yazili.", "Cevabi aciklayiniz ve gerekcelendiriniz lutfen."]]), "A", "şıkları bulunamadı"),
        (_pdf([[]]), "A", "seçilebilir metin yok"),
        (b"bozuk", "A", "açılamadı"),
    ],
)
def test_hazirla_hatalari(pdf, cevap, mesaj):
    with pytest.raises(katki.KatkiHatasi, match=mesaj):
        katki.hazirla(pdf, cevap)


def test_yaz_tek_seferlik(conn):
    s = katki.hazirla(_pdf([SAYFA]), "BA")
    assert katki.yaz(conn, KATKI, "a" * 64, s) == 2
    with conn.cursor() as cur:
        cur.execute("SELECT durum, sinif, ders, konu, secenekler, dogru_index FROM soru ORDER BY id")
        satir = cur.fetchall()
        cur.execute("SELECT count(*) FROM soru_gorsel")
        assert cur.fetchone()[0] == 2
    assert satir[0] == ("onayli", 9, "biyoloji", "Hucre testi", ["Ribozom", "Mitokondri", "Golgi", "Lizozom"], 1)
    with pytest.raises(katki.KatkiHatasi, match="daha önce"):
        katki.yaz(conn, KATKI, "a" * 64, s)


def test_kararlari_uygula_yalniz_askidaki_katki(conn):
    with conn.cursor() as cur:
        for anahtar in ("ogretmen-acik:x:1", "ogretmen-acik:x:2", "kitap:baska"):
            cur.execute("INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin) VALUES"
                        " ('kitap', %s, 'biyoloji', 9, 'e', 'm') RETURNING id", (anahtar,))
            cur.execute("INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index,"
                        " zorluk, kaynak, durum) VALUES (%s, 'biyoloji', 9, 'k', 's', 'c', '[\"a\",\"b\",\"c\",\"d\"]', 0, 1, 'e', 'askida')",
                        (cur.fetchone()[0],))
    conn.commit()
    n = katki.kararlari_uygula(conn, [{"soru_id": 1, "karar": "onay"}, {"soru_id": 2, "karar": "red"},
                                      {"soru_id": 3, "karar": "onay"}, {"soru_id": 99, "karar": "onay"}])
    assert n == 2
    with conn.cursor() as cur:
        cur.execute("SELECT durum FROM soru ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == ["onayli", "red", "askida"]  # başka kaynaktaki askıda soru dokunulmaz
