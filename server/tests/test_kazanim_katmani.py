"""
server/tests/test_kazanim_katmani.py — Kazanım Katmanı (Hedef → Kanıt → Araç)
RAG sorgu ve filtreleme birim testleri (mimari.md §12.1).
"""

from conftest import SahteBaglanti, SahteReranker


def _hedef_satiri(kod="DKAB.9.1.1", sinif=9, ders="Din Kültürü Ve Ahlak Bilgisi",
                  unite="ALLAH-İNSAN İLİŞKİSİ", metin="İnsanın yaratılışını sorgulayabilme"):
    return (kod, sinif, ders, unite, metin)


def _kanit_satiri(id_=101, dosya="test1.pdf", sinif=9, ders="Fizik", konu="Kuvvet",
                  test_no=1, soru_no=1, soru="Bir cisim serbest bırakılıyor...",
                  secenekler='{"A": "10", "B": "20", "C": "30", "D": "40"}',
                  cevap="B", mesafe=0.15):
    return (id_, dosya, sinif, ders, konu, test_no, soru_no, soru, secenekler, cevap, mesafe)


def _arac_metin(id_=1, sayfa=10, metin="Ders kitabı metni...", mesafe=0.12):
    return (id_, sayfa, metin, mesafe)


def _arac_tablo(id_=2, sayfa=12, baslik="Tablo 1", ozet="Özet veri...", mesafe=0.20):
    return (id_, sayfa, baslik, ozet, mesafe)


# ══════════════════════════════════════════════════════════════════════
# 1. HEDEF FİLTRELEME TESTLERİ (kazanim tablosu)
# ══════════════════════════════════════════════════════════════════════

class TestHedefGetir:
    def test_hedef_sinif_ve_ders_filtresi(self, motor):
        satir = _hedef_satiri(kod="FİZ.9.1.1", sinif=9, ders="Fizik")
        conn = SahteBaglanti(hedef_satirlari=[satir])

        sonuc = motor.hedef_getir(conn, sinif=9, ders="Fizik")

        assert len(sonuc) == 1
        assert sonuc[0]["kod"] == "FİZ.9.1.1"
        assert sonuc[0]["sinif"] == 9
        assert sonuc[0]["ders"] == "Fizik"
        assert sonuc[0]["tur"] == "hedef"

        # SQL doğrulaması
        sql, params = next(q for q in conn.sorgular if "FROM kazanim" in q[0])
        assert "sinif = %s" in sql
        assert "ders ILIKE %s" in sql
        assert 9 in params
        assert "Fizik" in params

    def test_hedef_kod_filtresi(self, motor):
        satir = _hedef_satiri(kod="DKAB.9.1.1")
        conn = SahteBaglanti(hedef_satirlari=[satir])

        sonuc = motor.hedef_getir(conn, kazanim_kod="DKAB.9.1.1")
        assert len(sonuc) == 1
        assert sonuc[0]["kod"] == "DKAB.9.1.1"

        sql, params = next(q for q in conn.sorgular if "FROM kazanim" in q[0])
        assert "kod = %s" in sql
        assert "DKAB.9.1.1" in params

    def test_hedef_metin_arama_filtresi(self, motor):
        satir = _hedef_satiri(metin="Kuvvet ve hareket ilişkisi")
        conn = SahteBaglanti(hedef_satirlari=[satir])

        sonuc = motor.hedef_getir(conn, arama="hareket")
        assert len(sonuc) == 1

        sql, params = next(q for q in conn.sorgular if "FROM kazanim" in q[0])
        assert "metin ILIKE %s" in sql
        assert "%hareket%" in params


# ══════════════════════════════════════════════════════════════════════
# 2. KANIT FİLTRELEME TESTLERİ (kazanim_test_soru tablosu)
# ══════════════════════════════════════════════════════════════════════

class TestKanitGetir:
    def test_kanit_vektorlu_arama(self, motor):
        satir = _kanit_satiri(id_=50, mesafe=0.10)
        conn = SahteBaglanti(kanit_satirlari=[satir])

        sonuc = motor.kanit_getir(conn, "Yerçekimi ivmesi nedir?", sinif=9, ders="Fizik", k=3)

        assert len(sonuc) == 1
        assert sonuc[0]["id"] == 50
        assert sonuc[0]["tur"] == "kanit"
        assert sonuc[0]["skor"] == 0.9  # 1 - 0.10
        assert isinstance(sonuc[0]["secenekler"], dict)
        assert sonuc[0]["cevap"] == "B"

        sql, params = next(q for q in conn.sorgular if "FROM kazanim_test_soru" in q[0])
        assert "embedding <=> %s AS mesafe" in sql
        assert "sinif = %s" in sql
        assert "ders ILIKE %s" in sql
        assert 9 in params
        assert "Fizik" in params

    def test_kanit_vektorsuz_filtreleme(self, motor):
        satir = _kanit_satiri(id_=60, mesafe=None)
        conn = SahteBaglanti(kanit_satirlari=[satir])

        sonuc = motor.kanit_getir(conn, soru_veya_vektor=None, sinif=12, ders="Kimya", konu="Asitler")

        assert len(sonuc) == 1
        assert sonuc[0]["skor"] is None

        sql, _ = next(q for q in conn.sorgular if "FROM kazanim_test_soru" in q[0])
        assert "NULL AS mesafe" in sql
        assert "konu ILIKE %s" in sql

    def test_kanit_sadece_cevapli_filtresi(self, motor):
        conn = SahteBaglanti(kanit_satirlari=[])
        motor.kanit_getir(conn, "test", sadece_cevapli=True)

        sql, _ = next(q for q in conn.sorgular if "FROM kazanim_test_soru" in q[0])
        assert "cevap IS NOT NULL" in sql

    def test_kanit_esik_altini_eler(self, motor):
        # mesafe=0.60 -> skor = 0.40; esik=0.55 verilirse elenmeli
        satir = _kanit_satiri(id_=70, mesafe=0.60)
        conn = SahteBaglanti(kanit_satirlari=[satir])

        sonuc = motor.kanit_getir(conn, "test", esik=0.55)
        assert len(sonuc) == 0


# ══════════════════════════════════════════════════════════════════════
# 3. ARAÇ FİLTRELEME TESTLERİ (chunk_egitim + chunk_tablo)
# ══════════════════════════════════════════════════════════════════════

class TestAracGetir:
    def test_arac_kazanim_kod_filtresi(self, motor):
        satir = _arac_metin(id_=10, sayfa=5, metin="Kazanım içeriği", mesafe=0.1)
        conn = SahteBaglanti(metin_satirlari=[satir])

        sonuc = motor.arac_getir(conn, kitap_id=1, soru_veya_vektor="Soru",
                                 kazanim_kod="FİZ.9.1.1", k=5)

        assert len(sonuc) == 1
        assert sonuc[0]["id"] == 10
        assert sonuc[0]["kazanim_kod"] == "FİZ.9.1.1"

        sql, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert "kazanim_kod = %s" in sql
        assert "FİZ.9.1.1" in params

    def test_arac_kazanim_kodsuz_tablo_dahil(self, motor):
        metin = _arac_metin(id_=1, mesafe=0.2)
        tablo = _arac_tablo(id_=2, mesafe=0.1)
        conn = SahteBaglanti(metin_satirlari=[metin], tablo_satirlari=[tablo])

        sonuc = motor.arac_getir(conn, kitap_id=1, soru_veya_vektor="Soru", k=5)

        assert len(sonuc) == 2
        turler = [s["tur"] for s in sonuc]
        assert "metin" in turler
        assert "tablo" in turler


# ══════════════════════════════════════════════════════════════════════
# 4. ÜÇLÜ ENTEGRE SORGU TESTLERİ (Hedef + Kanıt + Araç)
# ══════════════════════════════════════════════════════════════════════

class TestUcluSorgula:
    def test_uclu_sorgula_tum_katmanlari_birlestirir(self, motor):
        hedef = _hedef_satiri(kod="FİZ.9.1.1")
        kanit = _kanit_satiri(id_=101)
        arac = _arac_metin(id_=1)

        conn = SahteBaglanti(
            hedef_satirlari=[hedef],
            kanit_satirlari=[kanit],
            metin_satirlari=[arac],
        )

        sonuc = motor.uclu_sorgula(
            conn,
            soru="Kuvvet nedir?",
            sinif=9,
            ders="Fizik",
            kitap_id=19,
            kazanim_kod="FİZ.9.1.1",
        )

        assert "hedef" in sonuc
        assert "kanit" in sonuc
        assert "arac" in sonuc

        assert len(sonuc["hedef"]) >= 1
        assert len(sonuc["kanit"]) == 1
        assert len(sonuc["arac"]) == 1
        assert sonuc["hedef"][0]["kod"] == "FİZ.9.1.1"
        assert sonuc["kanit"][0]["tur"] == "kanit"
        assert sonuc["arac"][0]["tur"] == "metin"


# ══════════════════════════════════════════════════════════════════════
# 5. SORGULA KAZANIM_KOD TESTLERİ
# ══════════════════════════════════════════════════════════════════════

class TestSorgulaKazanimKod:
    def test_sorgula_kazanim_kod_aktarir(self, motor, monkeypatch):
        motor.reranker = SahteReranker(skorlar=0.85)
        monkeypatch.setattr(motor, "_llm_cevap", lambda s, q: "Cevap metni.")

        conn = SahteBaglanti(metin_satirlari=[_arac_metin(id_=1, mesafe=0.1)])

        yanit = motor.sorgula(
            conn,
            kitap_id=1,
            soru="Mitoz nedir?",
            sinif=9,
            ders="Biyoloji",
            kazanim_kod="BİY.9.1.1",
        )

        assert yanit["status"] == "ok"
        sql, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert "kazanim_kod = %s" in sql
        assert "BİY.9.1.1" in params
