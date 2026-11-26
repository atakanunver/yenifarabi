"""kazanim_sayfa_haritasi.py — İçindekiler ayrıştırma, kod normalleştirme, offset, aralık,
başlık yoluna düşüş. Gerçek /mnt verisine dokunmaz; küçük sahte metin sözlükleri kullanır."""

import json

import pytest

import kazanim_sayfa_haritasi as ksh

# biyoloji-9 PDF s.8 biçimi: "1.1.\t" + iki satıra bölünmüş başlık + nokta dolgusu + sekme
BIYOLOJI_TOC = (
    "7\n"
    "Güvenlik Sembolleri ....................................\t10\n"
    "1.1.\t\n"
    "BİYOLOJİNİN ÖNEMİ VE BİYOLOJİDEKİ DÖNÜM\n"
    "NOKTALARININ İNSAN HAYATINA KATKILARI ................\t16\n"
    "Biyolojinin Tanımı ve Önemi  .........................\t17\n"
    "1.2.\t\n"
    "BİLİM, BİLİMİN DOĞASI VE BİLİMSEL ARAŞTIRMA\n"
    "SÜREÇLERİ ............................................\t22\n"
    "Bilimsel Yöntem ......................................\t23\n"
    "1.3.\t\n"
    "BİLİMSEL ARAŞTIRMALARIN BİLİM ETİĞİNE\n"
    "UYGUNLUĞU ............................................\t31\n"
    "1. Tema Ölçme ve Değerlendirme Soruları ...............\t 71\n"
    "1. Tema\n1. Tema Yaşam\n14\nİçindekiler\n"
)

# fizik_9 biçimi: sayfa numarası sonraki satırda, sekmeyle
FIZIK_TOC = (
    "7\n"
    "1. ÜNİTE\t\n1. ÜNİTE\t FİZİK BİLİMİ VE KARİYER KEŞFİ\n12\n"
    "1.1.\t FİZİK BİLİMİ  \t\n\t 15\n"
    "1.2.\t FİZİK BİLİMİNİN ALT DALLARI  \t\n\t 23\n"
    "2.3.1.\t Vektörlerin Özellikleri \t\n\t 64\n"
    "3.4.1.\t Kaldırma Kuvveti ile Sıvılardaki \nBasıncı Oluşturan Kuvvet Arasındaki İlişki \t\n\t176\n"
)

# felsefe-10 biçimi: dolgulu satırlar sayfasız, numaralar blok hâlinde sonra
FELSEFE_TOC = (
    "1. ÜNİTE: FELSEFENİN DOĞASI\n12\n"
    "1.1. Felsefenin Anlamı ...................................\n"
    "1.2. Felsefi Düşüncenin Gelişimi .........................\n"
    "1. Ünite Ölçme ve Değerlendirme Soruları .................\n"
    "15\n19\n40\n10\n"
)


def _toc(metin):
    return [(g["no"], g["baslik"], g["sayfa"]) for g in ksh.icindekiler_ayristir(metin)]


class TestIcindekiler:
    def test_iki_satira_bolunmus_baslik_nokta_dolgusu_sekme(self):
        g = _toc(BIYOLOJI_TOC)
        assert ("1.1", "BİYOLOJİNİN ÖNEMİ VE BİYOLOJİDEKİ DÖNÜM NOKTALARININ İNSAN HAYATINA KATKILARI",
                16) in g
        assert ("1.2", "BİLİM, BİLİMİN DOĞASI VE BİLİMSEL ARAŞTIRMA SÜREÇLERİ", 22) in g
        assert ("1.3", "BİLİMSEL ARAŞTIRMALARIN BİLİM ETİĞİNE UYGUNLUĞU", 31) in g
        assert (None, "1. Tema Ölçme ve Değerlendirme Soruları", 71) in g
        # numarasız alt başlıklar ve basılı sayfa numarası girdi değildir
        assert all(no is None or no.startswith("1.") for no, _b, _s in g)
        assert len([x for x in g if x[0]]) == 3

    def test_sayfa_sonraki_satirda_ve_uc_duzey(self):
        g = _toc(FIZIK_TOC)
        assert ("1.1", "FİZİK BİLİMİ", 15) in g
        assert ("1.2", "FİZİK BİLİMİNİN ALT DALLARI", 23) in g
        assert ("2.3.1", "Vektörlerin Özellikleri", 64) in g
        assert ("3.4.1", "Kaldırma Kuvveti ile Sıvılardaki Basıncı Oluşturan Kuvvet Arasındaki İlişki",
                176) in g

    def test_sutunlu_dizgide_numaralar_sonradan(self):
        g = _toc(FELSEFE_TOC)
        assert g == [("1.1", "Felsefenin Anlamı", 15), ("1.2", "Felsefi Düşüncenin Gelişimi", 19),
                     (None, "1. Ünite Ölçme ve Değerlendirme Soruları", 40)]

    def test_tema_acilisi_bolum_sayilmaz(self):
        g = _toc("1.1. \nTEMA\nTEMA\nTepki\n12\n1.1.\t Farklı Canlıların Tepkileri\n14\n")
        assert g == [("1.1", "Farklı Canlıların Tepkileri", 14)]

    def test_ocr_eki_atlanir(self):
        g = _toc("1.1. Kimya Hayattır ......\t18\n[SAYFADAKİ GÖRSEL/HARİTA METNİ — OCR]\n"
                 "1.2. Bozuk ..... 99\n")
        assert g == [("1.1", "Kimya Hayattır", 18)]

    def test_satir_ici_sayfa_bitisik_numara(self):
        assert _toc("3.1.Yeşil Kimya ....... 237\n") == [("3.1", "Yeşil Kimya", 237)]

    def test_icindekiler_sayfalari_blok(self):
        sayfalar = {"7": {"metin": "6\n"}, "8": {"metin": BIYOLOJI_TOC},
                    "9": {"metin": "8\n1.4.\t\nCANLILAR ......\t34\n"}, "10": {"metin": "9\nKitabın Tanıtımı\n"}}
        assert ksh.icindekiler_sayfalari(sayfalar) == [8, 9]


@pytest.mark.parametrize("kod,beklenen", [
    ("BİY.9.1.2", "1.2"),
    ("MAT.11.1.1", "1.1"),
    ("KİM.10.2.13", "2.13"),
    ("PSK.1.1", "1.1"),
    ("SBTK.1.1", "1.1"),
    ("9.1.1", "1.1"),
    ("12.1.1.1", "1.1"),
    ("12.3.5", "3.5"),
    ("1.1", "1.1"),
    ("TDE2.1", None),
    ("A.2.1", None),
    ("11.1.1.1.1", None),
    ("ENG.8.1.R3", None),
    ("E10.1.L1", None),
    ("9.1", None),
    (None, None),
])
def test_kod_normalle(kod, beklenen):
    assert ksh.kod_normalle(kod) == beklenen


@pytest.mark.parametrize("metin,kod", [
    ("BİY.9.1.2. Bilimsel araştırma", "BİY.9.1.2"),
    ("9.1.1. Gerçek sayıların", "9.1.1"),
    ("TDE2.1. “Sözün İnceliği”", "TDE2.1"),
    ("HÖREN 1. Kann vertraute", None),
    ("1. Din-bilim ilişkisini", None),
    ("Günlük hayat problemleri", None),
])
def test_kazanim_kodu(metin, kod):
    assert ksh.kazanim_kodu(metin) == kod


class TestOffset:
    def test_cogunluk_farki(self):
        sayfalar = {str(p): {"metin": f"{p - 1}\nmetin"} for p in range(10, 30)}
        sayfalar["15"] = {"metin": "3\nbir liste maddesi"}  # gürültü
        sayfalar["16"] = {"metin": "başlık\nmetin\n15"}      # numara son satırda
        fark, oran = ksh.offset_hesapla(sayfalar, 10, 29)
        assert fark == 1
        assert 0.9 < oran < 1.0

    def test_olcum_yok(self):
        assert ksh.offset_hesapla({"10": {"metin": "metin"}}, 10, 10) == (None, 0.0)


ARALIK_GIRDILERI = [
    {"no": "1.1", "baslik": "A", "sayfa": 16},
    {"no": "1.1.1", "baslik": "A alt", "sayfa": 18},
    {"no": "1.2", "baslik": "B", "sayfa": 22},
    {"no": None, "baslik": "1. Tema Ölçme ve Değerlendirme", "sayfa": 30},
    {"no": "2.1", "baslik": "C", "sayfa": None, "pdf": 40},  # gövde aramasından PDF sayfası
    {"no": "2.2", "baslik": "D", "sayfa": 50},
]


class TestAralik:
    def _bolumler(self, **kw):
        return {b["no"]: (b["ilk_sayfa"], b["son_sayfa"])
                for b in ksh.bolum_araliklari(ARALIK_GIRDILERI, 1, 100, **kw)}

    def test_sonraki_bolum_ve_olcme_siniri(self):
        b = self._bolumler()
        assert b["1.1"] == (17, 22)    # 1.2 PDF 23'te başlar
        assert b["1.1.1"] == (19, 22)  # üç düzey: üst düzeydeki sonraki bölümle biter
        assert b["1.2"] == (23, 30)    # Ölçme ve Değerlendirme PDF 31
        assert b["2.1"] == (40, 50)    # pdf alanı offset'siz kullanılır

    def test_sonuncu_bolum_tema_sonu_ya_da_kitap_sonu(self):
        assert self._bolumler()["2.2"] == (51, 100)
        assert self._bolumler(tema_sonlari={"2": 80})["2.2"] == (51, 80)


def test_govde_ara_liste_sayfasini_atlar():
    sayfalar = {
        "10": {"metin": "1.1. Gerçek Sayılar\n1.2. Sayı Aralıkları\n1.3. Sayı Kümeleri"},  # tema açılışı
        "11": {"metin": "12\nmetin"},
        "12": {"metin": "13\n1.2. Sayı Aralıkları ve\nİşlemleri\nmetin"},
    }
    assert ksh.govde_ara(sayfalar, "1.2", "SAYI ARALIKLARI VE İŞLEMLERİ", 10, 12) == 12
    assert ksh.govde_ara(sayfalar, "1.4", "YOK", 10, 12) is None


KITAP = {"dosya": "kimya_9.pdf", "ders": "kimya", "sinif": 9}
BOLUMLER = {"kimya_9.pdf": [
    {"no": "1.1", "baslik": "Kimya Hayattır", "ilk_sayfa": 18, "son_sayfa": 45},
    {"no": "1.1.4", "baslik": "Kimyasal Maddelerin Kullanımı ve Güvenlik", "ilk_sayfa": 35, "son_sayfa": 45},
    {"no": "1.2", "baslik": "Atomdan Periyodik Tabloya", "ilk_sayfa": 46, "son_sayfa": 89},
    {"no": "1.2.1", "baslik": "Atom Teorileri ve Atomun Yapısı", "ilk_sayfa": 48, "son_sayfa": 55},
]}


class TestKazanimEsle:
    def _esle(self, kazanim, konu):
        return ksh.kazanim_esle("9", "kimya", "3", kazanim, {"konu": konu, "tema": "1. TEMA"},
                                [KITAP], BOLUMLER)

    def test_kod_yolu(self):
        r = self._esle("KİM.9.1.1. Kimya biliminin günlük hayata katkısı", "Kimya Hayattır: Günlük Hayatta")
        assert (r["bolum_no"], r["yontem"], r["ilk_sayfa"], r["son_sayfa"]) == ("1.1", "kod", 18, 45)
        assert r["_supheli"] == []

    def test_kod_tutmazsa_baslik_yolu(self):
        # KİM.9.1.3 → "1.3" kitapta yok; plan konusunun ":" sonrası parçası alt bölüme eşit
        r = self._esle("KİM.9.1.3. Atom teorilerindeki varsayımlar",
                       "Atomdan Periyodik Tabloya: Atom Teorileri (Bohr Atom Teorisi) ve Atomun Yapısı")
        assert (r["bolum_no"], r["yontem"]) == ("1.2.1", "baslik")

    def test_baslik_kodun_bolumunden_iyiyse_kazanir(self):
        # KİM.9.1.2 → "1.2" (Atomdan Periyodik Tabloya) ama konu 1.1.4 başlığına eşit
        r = self._esle("KİM.9.1.2. Kimyasal maddelerin kullanımından kaynaklanan problemler",
                       "Kimyasal Maddelerin Kullanımı ve Güvenlik")
        assert (r["bolum_no"], r["yontem"]) == ("1.1.4", "baslik")

    def test_kodsuz_kazanim_baslik_yolu(self):
        r = self._esle("Günlük hayatta kimyasal maddeler", "Kimyasal Maddelerin Kullanımı ve Güvenlik")
        assert r["kazanim_kodu"] is None and r["yontem"] == "baslik"

    def test_kod_baslik_ortakligi_yoksa_supheli_ama_eslenir(self):
        r = self._esle("KİM.9.1.2. Laboratuvar düzeni", "Laboratuvar")
        assert r["bolum_no"] == "1.2" and r["yontem"] == "kod"
        assert "kod-başlık kelime ortaklığı yok" in r["_supheli"]

    def test_eslenemeyen(self):
        assert self._esle("TDE2.1. Metin okuma", "Şiir Tahlili") is None


def test_harita_uret_sema(tmp_path):
    plan = {"kazanimlar": {"9": {"kimya": {"1": "KİM.9.1.1. Kimya biliminin katkısı",
                                           "2": "TDE2.1. Eşlenmez"}}},
            "konular": {"9": {"kimya": {"1": {"tema": "1. TEMA: ETKİLEŞİM", "konu": "Kimya Hayattır"}}}}}
    kayitlar, oran, eslenemeyen, _sup, alinmayan = ksh.harita_uret(plan, [KITAP], BOLUMLER)
    assert alinmayan == []
    assert len(kayitlar) == 1 and len(eslenemeyen) == 1
    assert oran[("9", "kimya")][:2] == [1, 2]
    k = kayitlar[0]
    assert set(k) == {"sinif", "ders", "hafta", "kazanim_kodu", "kazanim", "plan_konu", "plan_tema",
                      "kitap", "bolum_no", "baslik", "ilk_sayfa", "son_sayfa", "yontem"}
    assert (k["sinif"], k["hafta"], k["kitap"], k["kazanim_kodu"]) == ("9", "1", "kimya_9.pdf", "KİM.9.1.1")
    assert "bolumler" not in json.dumps(kayitlar)


def test_ortaklik_yok_tabloya_alinmaz_diger_supheliler_kalir():
    # KİM.9.1.2 → "1.2" (ortak kelime yok, başlık yolu da bulamaz) → tabloya girmez;
    # KİM.9.1.1 → "1.1" uzun aralık (45 sayfa) → tabloda kalır, şüpheli olarak işaretli
    bolumler = {"kimya_9.pdf": [
        {"no": "1.1", "baslik": "Kimya Hayattır", "ilk_sayfa": 18, "son_sayfa": 62},
        {"no": "1.2", "baslik": "Atomdan Periyodik Tabloya", "ilk_sayfa": 63, "son_sayfa": 89},
    ]}
    plan = {"kazanimlar": {"9": {"kimya": {"1": "KİM.9.1.1. Kimya biliminin katkısı",
                                           "2": "KİM.9.1.2. Laboratuvar düzeni"}}},
            "konular": {"9": {"kimya": {"1": {"konu": "Kimya Hayattır"}, "2": {"konu": "Laboratuvar"}}}}}
    kayitlar, oran, eslenemeyen, supheli, alinmayan = ksh.harita_uret(plan, [KITAP], bolumler)
    assert [k["kazanim_kodu"] for k in kayitlar] == ["KİM.9.1.1"]
    assert len(alinmayan) == 1 and "KİM.9.1.2" in alinmayan[0] and ksh._ORTAKLIK_YOK in alinmayan[0]
    assert len(supheli) == 1 and "aralık 45 sayfa" in supheli[0]
    assert eslenemeyen == [] and oran[("9", "kimya")][:2] == [1, 2]


def test_kitap_bolumleri_uctan_uca(tmp_path):
    sayfalar = {"8": {"metin": "7\nİçindekiler\n1.1. Kimya Hayattır ......\t17\n"
                               "1.2. Atomdan Periyodik Tabloya ......\t30\n"
                               "1. Tema Ölçme ve Değerlendirme ......\t40\n"}}
    for p in range(9, 61):
        sayfalar[str(p)] = {"metin": f"{p - 1}\nmetin"}
    (tmp_path / "kimya_9.json").write_text(json.dumps({"sayfalar": sayfalar}), encoding="utf-8")
    kb = ksh.kitap_bolumleri({"dosya": "kimya_9.pdf", "sayfa_sayisi": 60}, metin_dizini=tmp_path)
    assert kb["toc"] == [8] and kb["offset"] == 1
    assert [(b["no"], b["ilk_sayfa"], b["son_sayfa"]) for b in kb["bolumler"]] == [
        ("1.1", 18, 30), ("1.2", 31, 40)]


def test_metin_yoksa_bos(tmp_path):
    kb = ksh.kitap_bolumleri({"dosya": "yok.pdf"}, metin_dizini=tmp_path)
    assert kb["bolumler"] == [] and kb["hata"] == "metin yok"


# ---------------------------------------------------------------- TDE (metin adı yolu)
# turk_dili_ve_edebiyati_9 PDF s.8 biçimi: sayfa sonraki satırda, iki satırlık ad, tekrar, tire
TDE9_TOC = (
    "7\nİçindekiler\nTEMA1.\nSözün İnceliği\n12\n"
    "OKUMA: ŞİİR \n15\nOkuma Öncesi \n16\nOkuma Sırası: “San’at”\n17\nOkuma Sonrası \n18\n"
    "OKUMA: DENEME \n38\nOkuma Sırası: “Picasso’nun Hatları\nPicasso’nun Hatları”\n40\n"
    "EDEBİYAT ATÖLYESİ: YAZMA \n51\nYazma Sırası: “Duygularımı Betimli\xad\nyorum”\n52\n"
    "Tema Ölçme ve Değerlendirme\n67\n"
    "TEMA2.2. Anlam Arayışı\n72\nOKUMA: HİKÂYE\n75\nOkuma Sırası: “San’at”\n77\n"
)
# turk-dili-ve-edebiyati-11 biçimi: satır içi nokta dolgusu, tırnaksız adlar
TDE11_TOC = (
    "1. TEMA: BİR DİYECEĞİM VAR!..............12\n"
    "Metin Tahlili-1 (Anlama): Okuma..........15\nKaragöz Oyunu (Yazıcı)...........18\n"
    "Metin Tahlili-2 (Anlama): Okuma..........36\nMektup (Âli’ye Mektuplar) ........37\n"
    "Sözlü İletişim Engellerini Konu Alan Bir Drama Sergileyebilme.......53\n"
    "Edebiyat Atölyesi-2 (Anlatma): Yazma.....74\n"
    "1. Tema Ölçme ve Değerlendirme Soruları.....79\n"
)
TDE_TEMALAR = [{"no": 1, "ad": "Sözün İnceliği", "ilk_sayfa": 8, "son_sayfa": 73},
               {"no": 2, "ad": "Anlam Arayışı", "ilk_sayfa": 74, "son_sayfa": 150}]
TDE_KITAP = {"dosya": "turk_dili_ve_edebiyati_9.pdf", "ders": "turk dili ve edebiyati", "sinif": 9}


def _tde_yapi():
    return {"bolumler": ksh.tde_bolumleri(ksh.tde_icindekiler(TDE9_TOC), 1, 150, TDE_TEMALAR),
            "temalar": TDE_TEMALAR}


class TestTdeIcindekiler:
    def test_sonraki_satir_sayfa_iki_satirlik_ad_tekrar_tire(self):
        g = [(x["metin"], x["sayfa"]) for x in ksh.tde_icindekiler(TDE9_TOC)]
        assert ("OKUMA: ŞİİR", 15) in g
        assert ("Okuma Sırası: “San’at”", 17) in g
        assert ("Okuma Sırası: “Picasso’nun Hatları", 40) in g  # tekrar eden ikinci satır atıldı
        assert ("Yazma Sırası: “Duygularımı Betimliyorum”", 52) in g   # tire birleşti

    def test_satir_ici_dolgu_ve_etkinlik_adi_baslik_degil(self):
        b = ksh.tde_bolumleri(ksh.tde_icindekiler(TDE11_TOC), 1, 84, [
            {"no": 1, "ad": "Bir Diyeceğim Var!", "ilk_sayfa": 13, "son_sayfa": 84}])
        assert [(x["tur"], x["ilk_sayfa"], x["son_sayfa"]) for x in b] == [
            ("okuma", 16, 36), ("okuma", 37, 74), ("yazma", 75, 79), ("olcme", 80, 84)]
        assert b[1]["adlar"] == ["Mektup (Âli’ye Mektuplar)",
                                 "Sözlü İletişim Engellerini Konu Alan Bir Drama Sergileyebilme"]

    def test_aralik_ve_tema(self):
        b = {(x["tema"], x["etiket"]): (x["ilk_sayfa"], x["son_sayfa"], x["adlar"])
             for x in _tde_yapi()["bolumler"]}
        assert b[(1, "OKUMA: ŞİİR")] == (16, 38, ["Okuma Öncesi", "San’at", "Okuma Sonrası"])
        assert b[(1, "OKUMA: DENEME")][:2] == (39, 51)
        assert b[(1, "Tema Ölçme ve Değerlendirme")][:2] == (68, 73)  # tema sonunu aşmaz
        assert b[(2, "OKUMA: HİKÂYE")][:2] == (76, 150)


class TestTdeEsle:
    def _esle(self, konu, tema_no, kazanim="TDE2.1. okuma"):
        r = ksh.tde_esle(konu, kazanim, tema_no, _tde_yapi())
        return (r[0]["etiket"], r[1], r[0]["ilk_sayfa"], r[0]["son_sayfa"], r[2]) if r else None

    def test_tirnakli_ad(self):
        assert self._esle("Metin Tahlili Okuma: 📖 Deneme • bir deneme “Picasso’nun Hatları”", 1) == (
            "OKUMA: DENEME", "Picasso’nun Hatları", 39, 51, "tirnak")

    def test_tema_kisiti_ayni_adli_metin_diger_temada(self):
        # “San’at” 2. temada da var (OKUMA: HİKÂYE); 1. tema planı oraya gitmez
        assert self._esle("Okuma: 📖 Şiir “San’at”", 1)[:3] == ("OKUMA: ŞİİR", "San’at", 16)
        assert self._esle("Okuma: 📖 Şiir “San’at”", 2)[:3] == ("OKUMA: HİKÂYE", "San’at", 76)

    def test_tirnaksiz_ad(self):
        b = ksh.tde_bolumleri(ksh.tde_icindekiler(TDE11_TOC), 1, 84, [
            {"no": 1, "ad": "Bir Diyeceğim Var!", "ilk_sayfa": 13, "son_sayfa": 84}])
        r = ksh.tde_esle("Metin Tahlili Okuma: 📖 KARAGÖZ • Tema içeriğine uygun bir Karagöz oyunu",
                         "TDE2.1. x", 1, {"bolumler": b})
        assert (r[0]["ilk_sayfa"], r[1], r[2]) == (16, "Karagöz Oyunu (Yazıcı)", "ad")

    def test_ad_yoksa_tur_bolumu_ve_birlesik_aralik(self):
        assert self._esle("Edebiyat Atölyesi : YAZMA • bir etkinlik", 1)[::4] == (
            "EDEBİYAT ATÖLYESİ: YAZMA", "tur")
        # konu yok → beceri kodu TDE2 = okuma; 1. temada iki okuma bölümü → birleşik aralık
        assert self._esle("", 1)[2:] == (16, 51, "tur")
        assert self._esle("Tema Ölçme ve Değerlendirme", 1)[0] == "Tema Ölçme ve Değerlendirme"

    def test_tema_yoksa_eslenmez(self):
        assert self._esle("Okuma: “San’at”", None) is None


def test_tde_plan_temasi_ve_turu():
    assert ksh.tde_plan_temasi("2. TEMA: ANLAM ARAYIŞI", "", TDE_TEMALAR) == 2
    assert ksh.tde_plan_temasi("", "TDE2.1. “Sözün İnceliği” temasında …", TDE_TEMALAR) == 1
    assert ksh.tde_plan_temasi("", "TDE3.1. Belirli bir tema", TDE_TEMALAR) is None
    assert ksh.tde_plan_turu("Metin Tahlili Dinleme/İzleme: Mülakat", "TDE2.1.") == "dinleme"
    assert ksh.tde_plan_turu("", "TDE4.2. Yazısını") == "yazma"


def test_harita_uret_tde_tema_tasinir_ve_sema():
    plan = {"kazanimlar": {"9": {"türk dili ve edebiyatı": {
                "1": "TDE2.1. “Sözün İnceliği” temasında okuma",
                "2": "TDE4.1. Paragraf yazma"}}},  # tema yok → 1. hafta teması taşınır
            "konular": {}}
    kayitlar, oran, eslenemeyen, _s, _a = ksh.harita_uret(
        plan, [TDE_KITAP], {}, {"turk_dili_ve_edebiyati_9.pdf": _tde_yapi()})
    assert oran[("9", "türk dili ve edebiyatı")][:2] == [2, 2] and eslenemeyen == []
    assert [(k["bolum_no"], k["ilk_sayfa"], k["yontem"]) for k in kayitlar] == [
        ("TEMA1/OKUMA:ŞİİR(+1bölüm)", 16, "metin_adi"), ("TEMA1/EDEBİYATATÖLYESİ:YAZMA", 52, "metin_adi")]
    assert set(kayitlar[0]) == {"sinif", "ders", "hafta", "kazanim_kodu", "kazanim", "plan_konu",
                                "plan_tema", "kitap", "bolum_no", "baslik", "ilk_sayfa", "son_sayfa",
                                "yontem"}


# ---------------------------------------------------------------- numarasız ünite İçindekiler (felsefe-11)
FEL_TOC7 = (
    "İÇİNDEKİLER\nKEZABLN” ANDILAR neimiş RAK 9\n"
    "1. ÜNİTE: ÇEVRE SORUNLARI VE FELSEFE 13\nGİRİŞ 14\nHATIRLAMA 14\nÖN DEĞERLENDİRME 14\n"
    "DÜŞÜNME KÖPRÜSÜ 15\nNDE ALIN AN LL a inse 1\nÇEVRE ETİĞİ 25\n"
    "1. ÜNİTE ÖLÇME VE DEĞERLENDİRME 41\n"
    "2. ÜNİTE: TEKNOLOJİ VE HAYAT 45\nGİRİŞ 46\nDÜŞÜNME KÖPRÜSÜ 47\n"
    "TEKNOLOJİ VE İNSAN HAYATI........ 48\nTEKNOLOJİ BAĞLAMINDA ONTOLOJİK PROBLEMLER smear mrs 58\n"
    "2. ÜNİTE ÖLÇME VE DEĞERLENDİRME 73\n"
)
FEL_TOC8 = ("105\n106\n107\n"  # 3. ünite satırları OCR'da kayıp, yalnız numaralar
            "4. ÜNİTE: HUKUK VE FELSEFE 89\nGİRİŞ 90\nDÜŞÜNME KÖPRÜSÜ 91\nHUKUK VE İNSAN 92\n"
            "Hukukun Kaynağı 94\n4. ÜNİTE ÖLÇME VE DEĞERLENDİRME 98\nSÖZLÜK 102\n")


def _fel_sayfalar():
    s = {str(p): {"metin": f"{p}\nmetin"} for p in range(9, 111)}
    s["7"], s["8"] = {"metin": FEL_TOC7}, {"metin": FEL_TOC8}
    s["13"] = {"metin": "1. ÜNİTE\nANAHTAR ÜNİTE KONULARI\nÇEVRE VE İNSAN İLİŞKİSİ\nÇEVRE ETİĞİ"}  # kapak
    s["16"] = {"metin": "ÇEVRE VE İNSAN\nİLİŞKİSİ\nÇevre, insanı kuşatan…"}  # iki satıra bölünmüş başlık
    s["76"] = {"metin": "GİRİŞ"}
    s["77"] = {"metin": "DÜŞÜNME KÖPRÜSÜ"}
    s["84"] = {"metin": "AKIL VE İNANÇ PROBLEMLERİ\nmetin"}
    return s


def test_uniteli_icindekiler_kalip_ve_bozuk_satir():
    g = ksh.uniteli_icindekiler(FEL_TOC7)
    assert [(x["tur"], x["baslik"], x["sayfa"]) for x in g if x["tur"] != "kalip"] == [
        ("unite", "ÇEVRE SORUNLARI VE FELSEFE", 13), ("baslik", "ÇEVRE ETİĞİ", 25),
        ("unite", "TEKNOLOJİ VE HAYAT", 45), ("baslik", "TEKNOLOJİ VE İNSAN HAYATI", 48),
        ("baslik", "TEKNOLOJİ BAĞLAMINDA ONTOLOJİK PROBLEMLER", 58)]  # OCR çöpü atıldı, s.1 satırı yok
    assert {x["baslik"] for x in g if x["tur"] == "kalip"} >= {
        "GİRİŞ", "HATIRLAMA", "ÖN DEĞERLENDİRME", "DÜŞÜNME KÖPRÜSÜ", "1. ÜNİTE ÖLÇME VE DEĞERLENDİRME"}
    # küçük harfli alt-alt başlık ne bölüm ne sınır
    assert all(x["baslik"] != "Hukukun Kaynağı" for x in ksh.uniteli_icindekiler(FEL_TOC8))


def test_uniteli_bolumler_iki_sayfa_govde_aramasi_ve_acilis_cikarimi():
    aranacak = [(1, "ÇEVRE VE İNSAN İLİŞKİSİ"), (1, "ÇEVRE ETİĞİ"), (2, "TEKNOLOJİ VE İNSAN HAYATI"),
                (3, "AKIL VE İNANÇ İLİŞKİSİ"), (3, "AKIL VE İNANÇ PROBLEMLERİ"), (4, "HUKUK VE İNSAN")]
    b = {x["no"]: (x["baslik"], x["ilk_sayfa"], x["son_sayfa"])
         for x in ksh.uniteli_bolumler(_fel_sayfalar(), 7, 110, 0, aranacak)}
    assert b["1.1"] == ("ÇEVRE VE İNSAN İLİŞKİSİ", 16, 24)   # bozuk satır → gövde, kapak (s.13) atlandı
    assert b["1.2"] == ("ÇEVRE ETİĞİ", 25, 40)               # ölçme sınırı 41
    assert b["2.1"] == ("TEKNOLOJİ VE İNSAN HAYATI", 48, 57)
    assert b["2.2"][1:] == (58, 72)
    # 3. ünite İçindekiler'de yok: açılış sayfaları gövdeden (s.76-77), ilk konu s.78'de başlar
    assert b["3.1"] == ("AKIL VE İNANÇ İLİŞKİSİ", 78, 83)
    assert b["3.2"] == ("AKIL VE İNANÇ PROBLEMLERİ", 84, 88)  # s.8'e taşan 4. ünite s.89
    assert b["4.1"] == ("HUKUK VE İNSAN", 92, 97)


def test_uniteli_yol_yalniz_numarali_bolum_yoksa(tmp_path):
    s = _fel_sayfalar()
    (tmp_path / "fel.json").write_text(json.dumps({"sayfalar": s}), encoding="utf-8")
    kb = ksh.kitap_bolumleri({"dosya": "fel.pdf", "sayfa_sayisi": 110}, metin_dizini=tmp_path,
                             aranacak=[(1, "ÇEVRE ETİĞİ")])
    assert [b["baslik"] for b in kb["bolumler"]][:2] == ["ÇEVRE ETİĞİ", "TEKNOLOJİ VE İNSAN HAYATI"]
    s["7"] = {"metin": "İçindekiler\n1.1. Kimya Hayattır ......\t17\n1.2. Atom ......\t30\n"}
    (tmp_path / "fel.json").write_text(json.dumps({"sayfalar": s}), encoding="utf-8")
    kb = ksh.kitap_bolumleri({"dosya": "fel.pdf", "sayfa_sayisi": 110}, metin_dizini=tmp_path)
    assert [b["no"] for b in kb["bolumler"]] == ["1.1", "1.2"]
