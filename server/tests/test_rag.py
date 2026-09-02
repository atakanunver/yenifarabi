"""
server/rag.py — halüsinasyon savunmasının ve statü makinesinin birim testleri.

NEDEN BU DOSYA VAR (docs/TEST_ANALYSIS.md T-01): rag.py, CLAUDE.md'nin "RAG
Kuralları (kritik)" bölümündeki HER savunmayı barındırıyor ama 2026-09-02'ye
kadar hiçbir birim testi yoktu (coverage %19). Mantık yalnızca `benchmark/`
ile doğrulanıyordu — GPU + PostgreSQL + indekslenmiş kitap + ayrı venv
gerektiren, CI'da koşamayan bir yol. Yani rag.py'ye yapılan her düzenleme
fiilen otomatik kontrolsüzdü.

Ve korunacak bir şey VAR: üretim telemetrisi (354 gerçek istek, docs/
RAG_BASELINE.md §4.1) eşiğin gerçekten ayırt ettiğini gösteriyor — `ok`
cevaplarının ortalama rerank skoru 0,972, `yetersiz_kaynak`'ınki 0,596.

KAPSAM SINIRI — bu dosya retrieval KALİTESİNİ ölçmez (Recall@4, MRR: o
`benchmark/recall_test.py`'nin işi ve gerçek veri ister). Burada test edilen
şey KARAR MANTIĞI: hangi girdide hangi statü dönüyor, LLM ne zaman
çağrılmıyor, neyin logu tutuluyor. GPU yok, DB yok, ağ yok.
"""

import pytest
import rag
from conftest import SahteBaglanti, SahteEmbed, SahteReranker


def _metin(id_, sayfa, metin, mesafe=0.1):
    """chunk_egitim satırı — üretim şemasıyla aynı biçim."""
    return (id_, sayfa, metin, mesafe)


def _tablo(id_, sayfa, baslik, ozet, mesafe=0.1):
    """chunk_tablo satırı — üretim şemasıyla aynı biçim."""
    return (id_, sayfa, baslik, ozet, mesafe)


def _llm_sabit(cevap: str, sayac: list | None = None):
    """`_llm_cevap` yerine geçen sahte. `sayac` verilirse her çağrıda
    büyür — "LLM'e HİÇ gidilmedi" iddiasını kanıtlamak için."""
    def _sahte(sistem, soru, timeout=30.0):
        if sayac is not None:
            sayac.append((sistem, soru))
        return cevap
    return _sahte


# ══════════════════════════════════════════════════════════════════════
# 1. EK SAVUNMA — sayı kontrolü (mimari.md §8 adım 7)
# ══════════════════════════════════════════════════════════════════════

class TestSayilarKaynaktaMi:
    """Saf fonksiyon, hiçbir bağımlılığı yok. CLAUDE.md: "cevapta kaynakta
    geçmeyen SAYI varsa gösterme. Kelime örtüşme oranı kullanma (doğru
    parafrazı engeller)" — yani kontrol YALNIZCA sayılara bakmalı."""

    def test_sayisiz_cevap_her_zaman_gecer(self):
        assert rag._sayilar_kaynakta_mi("Mitoz bir bölünme türüdür.", "kaynak")

    def test_kaynakta_gecen_sayi_gecer(self):
        assert rag._sayilar_kaynakta_mi(
            "Sonuçta 2 hücre oluşur.", "Mitoz sonucunda 2 hücre oluşur.")

    def test_kaynakta_olmayan_sayi_reddedilir(self):
        assert not rag._sayilar_kaynakta_mi(
            "Sonuçta 4 hücre oluşur.", "Mitoz sonucunda 2 hücre oluşur.")

    def test_tek_uydurma_sayi_bile_reddeder(self):
        """"Kaynakta olmayan TEK bir sayı bile varsa False" — biri doğru
        biri uydurma olduğunda da reddedilmeli."""
        assert not rag._sayilar_kaynakta_mi(
            "2 hücre, 46 kromozom.", "Mitoz sonucunda 2 hücre oluşur.")

    def test_ondalik_nokta_ve_virgul(self):
        assert rag._sayilar_kaynakta_mi("Değer 3,14'tür.", "pi sayısı 3,14 kadardır")
        assert rag._sayilar_kaynakta_mi("Değer 3.14'tür.", "pi sayısı 3.14 kadardır")

    def test_parafraz_engellenmez(self):
        """Kontrolün DAR kapsamlı olduğunun kanıtı: hiçbir kelimesi
        kaynakta geçmeyen ama sayı içermeyen bir cevap geçer. Kelime
        örtüşmesine kaymadığını garanti eder."""
        assert rag._sayilar_kaynakta_mi(
            "Hücreler ikiye ayrılır.", "Mitoz sonucunda iki yavru oluşur.")


# ══════════════════════════════════════════════════════════════════════
# 2. ANA SAVUNMA — rerank eşiği (mimari.md §8 adım 5)
# ══════════════════════════════════════════════════════════════════════

class TestEsikKapisi:
    def test_esik_altinda_yetersiz_kaynak_doner(self, motor):
        motor.reranker = SahteReranker(skorlar=rag.ESIK_RERANK - 0.01)
        conn = SahteBaglanti([_metin(1, 84, "metin")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "yetersiz_kaynak"
        assert s["answer"] is None
        assert s["sources"] == []

    def test_esik_altinda_LLM_E_HIC_GIDILMEZ(self, motor, monkeypatch):
        """ANA SAVUNMANIN ASIL İDDİASI. CLAUDE.md: "skor eşiğin altındaysa
        LLM'e hiç gitme". Sadece statüyü değil, LLM'in ÇAĞRILMADIĞINI
        doğrular — statü doğru ama LLM yine de çağrılsaydı savunma
        (gizlilik + maliyet + gecikme açısından) delinmiş olurdu."""
        cagrilar = []
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("cevap", cagrilar))
        motor.reranker = SahteReranker(skorlar=0.1)
        conn = SahteBaglanti([_metin(1, 84, "metin")])
        assert motor.sorgula(conn, 1, "soru")["status"] == "yetersiz_kaynak"
        assert cagrilar == [], "eşik altında LLM çağrıldı — ana savunma delik"

    def test_esigin_tam_ustunde_LLM_E_GIDILIR(self, motor, monkeypatch):
        """Kapının sınırı: `<` karşılaştırması, eşiğe EŞİT skor geçmeli."""
        cagrilar = []
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap.", cagrilar))
        motor.reranker = SahteReranker(skorlar=rag.ESIK_RERANK)
        conn = SahteBaglanti([_metin(1, 84, "metin")])
        assert motor.sorgula(conn, 1, "soru")["status"] == "ok"
        assert len(cagrilar) == 1

    def test_hic_aday_yoksa_yetersiz_kaynak(self, motor):
        s = motor.sorgula(SahteBaglanti([]), 1, "soru")
        assert s["status"] == "yetersiz_kaynak"


# ══════════════════════════════════════════════════════════════════════
# 3. ORTA SAVUNMA — LLM'in YETERSIZ_KAYNAK çıkışı (§8 adım 6)
# ══════════════════════════════════════════════════════════════════════

class TestYetersizKaynakTespiti:
    @pytest.mark.parametrize("cevap", [
        "YETERSIZ_KAYNAK",
        "yetersiz_kaynak",
        "Bu konuda YETERSIZ_KAYNAK.",
        "YETERSİZ_KAYNAK",          # Türkçe büyük İ — .replace("İ","I") yolu
        "yetersİz_kaynak",
    ])
    def test_tum_yazimlar_yakalanir(self, motor, monkeypatch, cevap):
        """Türkçe `İ`/`I` normalizasyonu kritik: model küçük harfle ya da
        Türkçe noktalı İ ile yazarsa da yakalanmalı, yoksa "YETERSIZ_KAYNAK"
        metni öğrenciye CEVAP diye gösterilirdi."""
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit(cevap))
        conn = SahteBaglanti([_metin(1, 84, "metin")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "yetersiz_kaynak"
        assert s["answer"] is None

    def test_normal_cevap_yetersiz_sanilmaz(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Kaynak yeterlidir."))
        conn = SahteBaglanti([_metin(1, 84, "metin")])
        assert motor.sorgula(conn, 1, "soru")["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════
# 4. Mutlu yol + kaynak gösterimi
# ══════════════════════════════════════════════════════════════════════

class TestMutluYol:
    def test_ok_cevap_ve_kaynaklar(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("  Mitoz bölünmedir.  "))
        conn = SahteBaglanti([_metin(7, 84, "Mitoz konusu"), _metin(8, 85, "Devamı")])
        s = motor.sorgula(conn, 1, "Mitoz nedir?")
        assert s["status"] == "ok"
        assert s["answer"] == "Mitoz bölünmedir."          # strip edilmiş
        assert {"chunk_id": 7, "sayfa": 84, "tur": "metin"} in s["sources"]
        assert isinstance(s["latency_ms"], int)

    def test_en_fazla_TOP_N_kaynak_doner(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        conn = SahteBaglanti([_metin(i, i, f"m{i}") for i in range(1, 11)])
        s = motor.sorgula(conn, 1, "soru")
        assert len(s["sources"]) == rag.TOP_N

    def test_kaynak_metni_rerank_sirasina_gore(self, motor, monkeypatch):
        """Kaynaklar rerank skoruna göre sıralanmalı, DB'den geliş sırasına
        göre değil — `sources[0]` en iyi eşleşme olmalı."""
        gorulen = []
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap.", gorulen))
        motor.reranker = SahteReranker(skorlar=[0.6, 0.99])
        conn = SahteBaglanti([_metin(1, 10, "zayif"), _metin(2, 20, "guclu")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["sources"][0]["chunk_id"] == 2
        assert "guclu" in gorulen[0][0]        # sistem promptunda kaynak metin

    def test_sayi_uydurulursa_reddedilir(self, motor, monkeypatch):
        """Üçüncü savunma uçtan uca: LLM kaynakta olmayan bir sayı
        döndürürse cevap gösterilmez."""
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Tam 4271 tanedir."))
        conn = SahteBaglanti([_metin(1, 84, "Mitoz sonucunda iki hücre oluşur.")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "sayi_kontrolu_reddi"
        assert s["answer"] is None


# ══════════════════════════════════════════════════════════════════════
# 5. chunk_tablo kaynağı (2026-09-02 FAZ 1)
# ══════════════════════════════════════════════════════════════════════

class TestTabloKaynagi:
    def test_tablo_chunk_id_NEGATIF_yazilir(self, motor, monkeypatch):
        """chunk_egitim.id ve chunk_tablo.id AYRI bigserial dizileri — aynı
        sayı iki farklı satır demek olabilir. soru_log.donen_chunk_idler
        (integer[]) şemasını değiştirmeden ayırt edebilmek için tablo
        kaynakları negatif yazılır. Karıştırılırsa bir hata ayıklamada
        YANLIŞ chunk incelenir."""
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        motor.reranker = SahteReranker(skorlar=[0.9, 0.99])   # tablo üstte
        conn = SahteBaglanti([_metin(5, 10, "duz metin")],
                             [_tablo(5, 12, "Hücre", "satır verisi")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["sources"][0] == {"chunk_id": -5, "sayfa": 12, "tur": "tablo"}
        assert s["sources"][1] == {"chunk_id": 5, "sayfa": 10, "tur": "metin"}

    def test_tablo_sorgusu_patlarsa_metin_yolu_ETKILENMEZ(self, motor, monkeypatch):
        """mimari.md §2 "Farabi asla dersi bozmaz" — chunk_tablo yoksa/
        bozuksa RAG'ın metin yolu çalışmaya devam etmeli. FAZ 1'in fiilî
        geri dönüş garantisi."""
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        conn = SahteBaglanti([_metin(1, 84, "duz metin")],
                             tablo_patlat=RuntimeError("chunk_tablo yok"))
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "ok"
        assert s["sources"][0]["tur"] == "metin"
        assert conn.rollback_sayisi >= 1

    def test_bayrak_kapaliyken_tabloya_HIC_SORULMAZ(self, motor, monkeypatch):
        """`TABLO_KAYNAGI = False` tek satırlık geri dönüş anahtarı —
        kapalıyken chunk_tablo sorgusu hiç yapılmamalı."""
        monkeypatch.setattr(rag, "TABLO_KAYNAGI", False)
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        conn = SahteBaglanti([_metin(1, 84, "metin")], [_tablo(9, 1, "b", "o")])
        assert motor.sorgula(conn, 1, "soru")["status"] == "ok"
        assert not [s for s, _ in conn.sorgular if "chunk_tablo" in s]

    def test_tablo_rerankte_KIRPILIR_ama_LLM_E_TAM_GIDER(self, motor, monkeypatch):
        """Ölçülmüş performans kararı: uzun tablo metni rerank batch'ini
        padliyor (893→3321 ms). Kırpma YALNIZCA rerank görünümüne
        uygulanır; LLM'e giden kaynak metin TAM kalır (Kural 5).

        Bu test R-4'ün (metin adaylarını da kırpma) güvenlik ağıdır: aynı
        ayrımın metin tarafında da korunduğunu doğrulayacak."""
        gorulen = []
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap.", gorulen))
        uzun = "X" * (rag.RERANK_TABLO_KARAKTER + 500)
        conn = SahteBaglanti([], [_tablo(1, 5, "Baslik", uzun)])
        motor.sorgula(conn, 1, "soru")
        rerank_metni = motor.reranker.gorulen_ciftler[0][1]
        assert len(rerank_metni) == rag.RERANK_TABLO_KARAKTER
        assert uzun in gorulen[0][0], "LLM'e giden kaynak metin kırpılmış"


# ══════════════════════════════════════════════════════════════════════
# 6. Hata yolu — hiçbir istisna çıplak 500 olmamalı
# ══════════════════════════════════════════════════════════════════════

class TestHataYolu:
    def test_embedding_patlarsa_hata_statusu(self, motor):
        """2026-08-11'de gerçekten yaşandı: çok uzun bir soru reranker'ı
        CUDA OOM'a düşürdü, istisna main.py'ye kadar YAKALANMADAN çıkıp
        çıplak 500 döndürdü VE metriğe hiç yazılmadı."""
        motor.embed_model = SahteEmbed(patlat=RuntimeError("CUDA OOM"))
        conn = SahteBaglanti([_metin(1, 84, "m")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "hata"
        assert "CUDA OOM" in s["hata"]
        assert len(conn.metrik_kayitlari()) == 1

    def test_rerank_patlarsa_hata_statusu(self, motor):
        motor.reranker = SahteReranker(patlat=RuntimeError("CUDA OOM"))
        conn = SahteBaglanti([_metin(1, 84, "m")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "hata"
        assert len(conn.metrik_kayitlari()) == 1

    def test_llm_patlarsa_hata_statusu(self, motor, monkeypatch):
        def _patla(sistem, soru, timeout=30.0):
            raise TimeoutError("ollama yanıt vermedi")
        monkeypatch.setattr(motor, "_llm_cevap", _patla)
        conn = SahteBaglanti([_metin(1, 84, "m")])
        s = motor.sorgula(conn, 1, "soru")
        assert s["status"] == "hata"
        assert "TimeoutError" in s["hata"]

    def test_loglama_patlarsa_CEVAP_ETKILENMEZ(self, motor, monkeypatch):
        """mimari.md §2 — loglama dersi bozmaz. `_logla` içindeki bir hata
        yutulmalı, öğrencinin cevabı yine de dönmeli."""
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        conn = SahteBaglanti([_metin(1, 84, "m")])
        conn.commit = lambda: (_ for _ in ()).throw(RuntimeError("DB düştü"))
        assert motor.sorgula(conn, 1, "soru")["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════
# 7. Loglama sözleşmesi — GİZLİLİK KURALI
# ══════════════════════════════════════════════════════════════════════

class TestLoglamaSozlesmesi:
    """CLAUDE.md "Loglama — iki tablo, karıştırma":
       metrik   → HER sorguda, içerik YOK
       soru_log → yalnızca düşük skorlu ok / yetersiz_kaynak /
                  sayi_kontrolu_reddi / hata
    Bu ayrım bir gizlilik kuralıdır; bozulursa başarılı+yüksek skorlu
    cevapların METNİ süresiz saklanmaya başlar."""

    def test_yuksek_skorlu_ok_ta_soru_log_YAZILMAZ(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        motor.reranker = SahteReranker(skorlar=0.99)   # > DUSUK_SKOR_ESIGI
        conn = SahteBaglanti([_metin(1, 84, "m")])
        motor.sorgula(conn, 1, "soru")
        assert len(conn.metrik_kayitlari()) == 1
        assert conn.soru_log_kayitlari() == [], "yüksek skorlu ok'ta metin saklandı"

    def test_dusuk_skorlu_ok_ta_soru_log_YAZILIR(self, motor, monkeypatch):
        monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit("Cevap."))
        motor.reranker = SahteReranker(skorlar=rag.DUSUK_SKOR_ESIGI - 0.01)
        conn = SahteBaglanti([_metin(1, 84, "m")])
        motor.sorgula(conn, 1, "soru")
        assert len(conn.soru_log_kayitlari()) == 1

    def test_yetersiz_kaynakta_soru_log_YAZILIR(self, motor):
        motor.reranker = SahteReranker(skorlar=0.1)
        conn = SahteBaglanti([_metin(1, 84, "m")])
        motor.sorgula(conn, 1, "soru")
        assert len(conn.soru_log_kayitlari()) == 1

    def test_metrik_HER_statude_yazilir(self, motor, monkeypatch):
        for cevap, beklenen in [("Cevap.", "ok"),
                                ("YETERSIZ_KAYNAK", "yetersiz_kaynak"),
                                ("Tam 4271 tane.", "sayi_kontrolu_reddi")]:
            monkeypatch.setattr(motor, "_llm_cevap", _llm_sabit(cevap))
            conn = SahteBaglanti([_metin(1, 84, "iki hücre oluşur")])
            assert motor.sorgula(conn, 1, "soru")["status"] == beklenen
            assert len(conn.metrik_kayitlari()) == 1, f"{beklenen}: metrik yazılmadı"
