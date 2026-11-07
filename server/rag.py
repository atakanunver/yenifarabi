"""server/rag.py — Faz 1 RAG çekirdeği: pgvector arama + rerank + eşik + LLM.

benchmark/recall_test.py (retrieval/rerank) ve benchmark/katman_test.py'nin
(eşik + LLM katmanı — 2026-08-10'da ölçülen: C grubu tek başına hiçbir eşikle
ayrıştırılamıyordu, iki katman birlikte %94 doğru) DOĞRULANMIŞ mantığının
canlı servise taşınmış hali. Akış mimari.md §8 ile birebir: rerank → eşik
(ana savunma, LLM'e hiç gitmeyebilir) → LLM (orta savunma, katı prompt +
YETERSIZ_KAYNAK) → sayı kontrolü (ek savunma).

NOT — sistem promptu mimari.md §8'den BİREBİR kopya, benchmark/katman_test.py
ile de aynı. Üç yerde de elle senkron tutulmalı; paylaşılan tek bir prompt
dosyası yok (Faz 1'in ilerleyen bir adımı olabilir).

ESIK_RERANK = 0.5 — benchmark/katman_test.py'de ölçüldü: A/B grubu rerank
skorlarının tabanı (temiz soru setiyle) 0.71, grup C'nin 2/5'i 0.02-0.34
aralığında. 0.5 ikisi arasında güvenli bir boşlukta duruyor ama TEK kitapla
(biyoloji-9) ölçüldü — yeni bir kitap eklendiğinde bu değer yeniden
gözden geçirilmeli, kör kör başka kitaplara uygulanmamalı.

§8 adım 7 "SAYI KONTROLÜ" (2026-08-11 eklendi) — cevaptaki sayısal değerlerin
kaynak metinde geçip geçmediğini kontrol eder. CLAUDE.md'nin "RAG Kuralları"
notuyla aynı: "kelime örtüşme oranı kullanma (doğru parafrazı engeller)" —
bu yüzden kontrol yalnızca SAYILARI karşılaştırıyor, cümlenin geri kalanını
değil. Dar kapsamlı, ek bir savunma — ana savunma eşik+LLM katmanıdır (yukarı
bkz.), bunun yerine geçmez.

LOGLAMA (2026-08-11 eklendi, mimari.md §13 / benchmark/olcum_schema.sql) —
`metrik` HER sorguda yazılır (süre+durum+skor, içerik yok, sınırsız saklanır).
`soru_log` yalnızca CLAUDE.md'nin "Loglama" tablosundaki durumlarda yazılır:
düşük skorlu ok, yetersiz_kaynak, sayi_kontrolu_reddi, hata (iptal bu API'de
henüz üretilemiyor — iptal mekanizması yok). DUSUK_SKOR_ESIGI (0.65) ÖLÇÜLMEDİ,
ESIK_RERANK (0.5, ana savunma) ile A/B'nin ölçülen tabanı (0.71) arasında ilk
tahmin — Kural 10 gereği burada açıkça işaretleniyor.

Yapılmayan (bilinçli sınır, bu turda eklenmedi):
- Kazanım eşleştirme, tahta_id → ders_programi → kitap_id bağlam çözümü —
  şu an kitap_id doğrudan istekte veriliyor, Faz 1'in sonraki bir adımı.
  `sorgula()`'ya tahta_id/sinif/ders parametreleri BU YÜZDEN eklendi (loglama
  şimdiden doğru şemaya yazsın diye) ama çağıran taraf (main.py) şu an
  yalnızca sinif/ders'i kitap_id'den çözüp geçiyor, tahta_id hep None.
"""

import json
import re
import time
import urllib.request

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
TOP_K = 20
TOP_N = 4
ESIK_RERANK = 0.5
DUSUK_SKOR_ESIGI = 0.65

# ── FAZ 1 (2026-09-02): chunk_tablo retrieval'a bağlandı ──────────────────
# `chunk_tablo` 2026-08-30'da dolduruldu (tools/tablo_cikar.py +
# benchmark/embed_tablo.py) ama HİÇBİR sorgu onu okumuyordu — 67 gerçek tablo
# embed edilmiş hâlde boşta duruyordu (plan.md §D.1). "Tablodaki en yüksek
# değer hangisi?" gibi sorular bu yüzden yalnızca düz sayfa metnine
# düşüyordu, hücre/sütun ilişkisi kaybolmuş hâline.
#
# TASARIM — neden AYRI sorgu, tek birleşik sorgu değil:
# İki tabloyu tek `UNION` ile çekip top-20 almak, tablo satırlarının metin
# satırlarını ADAY LİSTESİNDEN DIŞARI İTMESİNE yol açardı; yalnızca-metin
# sorularında bugünkü recall'ı düşürürdü. Bunun yerine her kaynak KENDİ
# top-K'sını getirir, rerank BİRLEŞİM üzerinde çalışır, top-4 oradan seçilir.
# Böylece metin tarafının aday havuzu (TOP_K=20) hiç daralmaz — davranış
# yalnızca "tablo daha iyi eşleşiyorsa üste çıkabilir" yönünde değişir.
#
# ESIK_RERANK (0.5) DEĞİŞTİRİLMEDİ: chunk_egitim düzyazısıyla kalibre
# edilmişti, `metin_ozet`in ("Tablo: X. hücre — hücre") skor dağılımı
# ölçülmedi. Ayrı bir eşik icat etmek yerine aynı kapı kullanılıyor —
# tablo da aynı çıtayı aşmak zorunda.
TOP_K_TABLO = 10
# Rerank ADIMI için tablo metni kırpma sınırı (LLM'e giden metin TAM kalır).
# ÖLÇÜM (2026-09-02): tablo eklenince rerank 893 ms → 3321 ms'ye çıktı —
# 10 aday için +2,4 sn, yani aday başına ~240 ms (metin adaylarında ~45 ms).
# Sebep: CrossEncoder'a `max_length` verilmemiş (server/main.py), model
# 8192 token'a kadar kabul ediyor ve BATCH EN UZUN DİZİYE PADLENİYOR —
# chunk_tablo.metin_ozet en fazla 4571 karakter (chunk_egitim'de 3122),
# tek uzun tablo TÜM partinin maliyetini yükseltiyor. Kırpma yalnızca
# tablo adaylarının rerank görünümüne uygulanır; metin adayları ve LLM'e
# giden kaynak metin AYNEN korunur (Kural 5, mevcut davranışı bozma).
RERANK_TABLO_KARAKTER = 1200
# ── R-4 (2026-09-02): aynı padding cezası METİN adaylarında da var ────────
# Yukarıdaki kırpma yalnızca tablo adaylarına uygulanıyordu, ama batch'i
# padleyen şey adayın TÜRÜ değil UZUNLUĞU. Canlı DB ölçümü: chunk_egitim'de
# 45 chunk 3.122 karakteri, 10'u 6.000'i aşıyor; en uzunu 21.814 karakter
# (Fizik-9 s.169 — yalnızca 184 kelime, gerisi PyMuPDF'in U+FFFD çöpü).
# Böyle bir aday top-20'ye girdiğinde TÜM partinin maliyetini yükseltiyor.
#
# KAPAK NEDEN 4000 — kabul testinin koştuğu kitapta NO-OP olacak şekilde
# seçildi. Kitap bazlı dağılım (canlı DB, 2026-09-02):
#     kitap 19 Fizik-9      p99 9.112   max 21.814   >4000: 10
#     kitap 17 Coğrafya-9   p99 3.938   max  4.673   >4000:  4
#     kitap 18 Din Kült.-9  p99 3.606   max  4.212   >4000:  2
#     kitap 14 Türk Dili-10 p99 2.844   max  4.163   >4000:  1
#  →  kitap  1 BİYOLOJİ-9   p99 2.392   max  3.122   >4000:  0
# Recall@4 yalnızca biyoloji-9'da ölçülüyor ve orada 4000'i aşan TEK BİR
# chunk YOK — yani kapak o kitaba hiç dokunmuyor, kabul testi kendi kendini
# kirletmiyor. Korpus genelinde etkilenen: 8.726 chunk'ın 17'si (%0,19).
# (Korpus geneli p95=1.777'den türetmek YANLIŞ olurdu: padding SORGU-BAŞI
# bir kuyruk özelliği, korpus geneli bir ortalama değil. 2000'lik bir kapak
# biyoloji-9'un 12 chunk'ını kırpıp gate'i kirletirdi.)
#
# TABLO kapağı (1200) DEĞİŞTİRİLMEDİ — o ayrı ölçümle kalibre edildi.
# Kırpma YALNIZCA rerank görünümüne uygulanır; LLM'e giden kaynak metin
# TAM kalır (Kural 5). Bunu server/tests/test_rag.py::
# test_tablo_rerankte_KIRPILIR_metin_KIRPILMAZ garanti eder.
# Geri dönüş: None yap — kırpma tamamen devre dışı kalır.
RERANK_METIN_KARAKTER = 4000
# Tek satırlık geri dönüş anahtarı (plan.md §K): False yapmak sistemi
# FAZ 1 öncesi davranışa döndürür, DB'ye dokunmadan.
TABLO_KAYNAGI = True

# ── Open WebUI arama yolu (2026-10-03) ────────────────────────────────────
# Yeniden sıralama YOK (kullanıcı kararı C): CPU'da 20 adayın rerank'i
# medyan 9,9 sn sürdü; vektör-only recall@4 28/35 (rerank'li 32/35),
# biyoloji-9 40 soru — DECISIONS.md 2026-10-03.
# kaynak → (chunk tablosu, kaynak kolonu). SQL'e yalnızca bu beyaz
# listeden isim girer (enjeksiyon yok).
_ARAMA_TABLOLARI = {
    "egitim": ("chunk_egitim", "kitap_id"),
    "idari": ("chunk_idari", "belge_id"),
}
# Kosinüs benzerliği (1 - mesafe) eşiği — altındaysa "zayif": filtre modele
# "kaynakta bulunamadı" notu düşer (cevap yine verilir). Değer
# benchmark/recall_test.py --esik 0.55 ölçümünden (2026-08-11, %90 doğru
# tespit, biyoloji-9). Yeni kitaplarda yeniden gözden geçirilmeli.
ESIK_BENZERLIK = 0.55

_SAYI_RE = re.compile(r"\d+(?:[.,]\d+)?")
_DURAK_KELIMELER = {
    "icin", "olan", "veya", "gibi", "kadar", "nedir", "nelerdir", "nasil",
    "buna", "gore", "olur", "diye", "yapan", "eder", "biri", "için",
    "nasıl", "göre", "hakkında", "ile", "ve", "bir", "bu", "şu", "ne",
    "sayılı", "sayili", "kanun", "kanuna", "kanunu", "madde", "maddesi",
    "yönetmelik", "yönetmeliği", "hangi", "kac", "kaç", "olarak", "tür",
    "şeklinde", "olanlar"
}

SISTEM_SABLON = """Sen Farabi'sin; lise düzeyindeki öğretmen ve öğrencilere akıllı tahta üzerinden yardımcı olan MEB müfredatına hakim bir ders asistanısın.
SADECE aşağıdaki KAYNAK METİN'e dayanarak, sorulan soruyu doğrudan ve Türkçe olarak cevapla.

DÜŞÜNME VE CEVAPLAMA KURALLARI:
- DİL VE ANLATIM: Düşünce ve yanıt sürecini duru, akıcı ve kurallı bir Türkçe ile yürüt. Yabancı dilden tercüme hissi veren yapay ifadeler kullanma.
- PEDAGOJİK SEVİYE: MEB müfredatına ve lise seviyesine uygun, öğretici, sade ve net bir üslup benimse.
- KAYNAK SADAKATİ: Yalnızca KAYNAK METİN'de açıkça yer alan bilgileri kullan. Kaynakta geçmeyen hiçbir bilgiyi, formülü veya tarihi ekleme; genel kültürünle tamamlama yapma.
- YETERSİZ BİLGİ: Cevap kaynak metinde doğrudan yoksa veya yetersizse başka hiçbir açıklama yapmadan SADECE şunu yaz: YETERSIZ_KAYNAK
- EN FAZLA 3 CÜMLE: Cevabın en fazla 3 cümle olsun. Giriş, nezaket veya selamlama cümleleri kurmadan doğrudan bilgiye odaklan.
- Yorum, tahmin veya örnek uydurma kesinlikle yasaktır.

KAYNAK METİN:
{kaynak}"""


def _sayilar_kaynakta_mi(cevap: str, kaynak_metin: str) -> bool:
    """Cevaptaki her sayının kaynak metinde birebir geçip geçmediğini kontrol
    eder. Kaynakta olmayan TEK bir sayı bile varsa False döner — mimari.md §8
    adım 7'nin "ek, dar kapsamlı" savunması, kelime örtüşmesi DEĞİL."""
    cevap_sayilari = _SAYI_RE.findall(cevap)
    if not cevap_sayilari:
        return True
    return all(sayi in kaynak_metin for sayi in cevap_sayilari)


class RagMotoru:
    def __init__(self, embed_model, reranker, ollama_host: str = "127.0.0.1:11434",
                 model: str = "farabi"):
        self.embed_model = embed_model
        self.reranker = reranker
        self.ollama_host = ollama_host
        self.model = model

    def _ilk_k_getir(self, conn, kitap_id: int, vektor, k: int,
                     kazanim_kod: str | None = None):
        with conn.cursor() as cur:
            if kazanim_kod:
                cur.execute(
                    """
                    SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe
                    FROM chunk_egitim
                    WHERE kitap_id = %s AND kazanim_kod = %s
                    ORDER BY mesafe
                    LIMIT %s
                    """,
                    (vektor, kitap_id, kazanim_kod, k),
                )
            else:
                cur.execute(
                    """
                    SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe
                    FROM chunk_egitim
                    WHERE kitap_id = %s
                    ORDER BY mesafe
                    LIMIT %s
                    """,
                    (vektor, kitap_id, k),
                )
            return cur.fetchall()  # [(id, sayfa_no, metin, mesafe), ...]

    # ── Kazanım Katmanı (Hedef → Kanıt → Araç, mimari.md §12.1) ───────────

    def hedef_getir(self, conn, *, sinif: int | None = None, ders: str | None = None,
                    kazanim_kod: str | None = None, unite: str | None = None,
                    arama: str | None = None, limit: int = 50) -> list[dict]:
        """Hedef (kazanim tablosu) filtreleme sorgusu — mimari.md §12.1.
        MEB öğretim programı kazanımlarını (kod, sınıf, ders, ünite, metin)
        filtreler. Ders anlatımının çerçevesini belirler.
        """
        kosullar = []
        parametreler = []
        if sinif is not None:
            kosullar.append("sinif = %s")
            parametreler.append(sinif)
        if ders:
            kosullar.append("ders ILIKE %s")
            parametreler.append(ders)
        if kazanim_kod:
            kosullar.append("kod = %s")
            parametreler.append(kazanim_kod)
        if unite:
            kosullar.append("unite ILIKE %s")
            parametreler.append(f"%{unite}%")
        if arama:
            kosullar.append("metin ILIKE %s")
            parametreler.append(f"%{arama}%")

        where = ("WHERE " + " AND ".join(kosullar)) if kosullar else ""
        sql = f"""
            SELECT kod, sinif, ders, unite, metin
            FROM kazanim
            {where}
            ORDER BY kod
            LIMIT %s
        """
        parametreler.append(limit)
        with conn.cursor() as cur:
            cur.execute(sql, tuple(parametreler))
            satirlar = cur.fetchall()

        return [
            {
                "kod": r[0],
                "sinif": r[1],
                "ders": r[2],
                "unite": r[3],
                "metin": r[4],
                "tur": "hedef",
            }
            for r in satirlar
        ]

    def kanit_getir(self, conn, soru_veya_vektor: str | list[float] | None = None, *,
                    sinif: int | None = None, ders: str | None = None,
                    konu: str | None = None, test_no: int | None = None,
                    soru_no: int | None = None, sadece_cevapli: bool = False,
                    k: int = TOP_N, esik: float | None = None) -> list[dict]:
        """Kanıt (kazanim_test_soru tablosu) filtreleme ve benzerlik sorgusu — mimari.md §12.1.
        Öğrencinin kazanımı edindiğini gösterecek MEB ÖDSGM test sorularını
        vektör benzerliği ve/veya filtreler (sınıf, ders, konu vb.) ile getirir.
        """
        vektor = None
        if soru_veya_vektor is not None:
            if isinstance(soru_veya_vektor, str):
                soru_temiz = soru_veya_vektor.replace("\xad", "").strip()
                vektor = self.embed_model.encode(soru_temiz, normalize_embeddings=True)
            else:
                vektor = soru_veya_vektor

        kosullar = []
        parametreler = []

        if vektor is not None:
            kosullar.append("embedding IS NOT NULL")
        if sinif is not None:
            kosullar.append("sinif = %s")
            parametreler.append(sinif)
        if ders:
            kosullar.append("ders ILIKE %s")
            parametreler.append(ders)
        if konu:
            kosullar.append("konu ILIKE %s")
            parametreler.append(f"%{konu}%")
        if test_no is not None:
            kosullar.append("test_no = %s")
            parametreler.append(test_no)
        if soru_no is not None:
            kosullar.append("soru_no = %s")
            parametreler.append(soru_no)
        if sadece_cevapli:
            kosullar.append("cevap IS NOT NULL AND btrim(cevap) != ''")

        where = ("WHERE " + " AND ".join(kosullar)) if kosullar else ""

        if vektor is not None:
            sql = f"""
                SELECT id, kaynak_dosya, sinif, ders, konu, test_no, soru_no,
                       soru_metni, secenekler, cevap, embedding <=> %s AS mesafe
                FROM kazanim_test_soru
                {where}
                ORDER BY mesafe
                LIMIT %s
            """
            sorgu_parametreleri = [vektor] + parametreler + [k]
        else:
            sql = f"""
                SELECT id, kaynak_dosya, sinif, ders, konu, test_no, soru_no,
                       soru_metni, secenekler, cevap, NULL AS mesafe
                FROM kazanim_test_soru
                {where}
                ORDER BY test_no, soru_no, id
                LIMIT %s
            """
            sorgu_parametreleri = parametreler + [k]

        with conn.cursor() as cur:
            cur.execute(sql, tuple(sorgu_parametreleri))
            satirlar = cur.fetchall()

        sonuclar = []
        for r in satirlar:
            mesafe = r[10]
            skor = round(1 - float(mesafe), 4) if mesafe is not None else None
            if esik is not None and skor is not None and skor < esik:
                continue
            sec = r[8]
            if isinstance(sec, str):
                try:
                    sec = json.loads(sec)
                except (ValueError, TypeError):
                    pass
            sonuclar.append({
                "id": r[0],
                "kaynak_dosya": r[1],
                "sinif": r[2],
                "ders": r[3],
                "konu": r[4],
                "test_no": r[5],
                "soru_no": r[6],
                "soru_metni": r[7],
                "secenekler": sec,
                "cevap": r[9],
                "skor": skor,
                "tur": "kanit",
            })
        return sonuclar

    def arac_getir(self, conn, kitap_id: int, soru_veya_vektor: str | list[float], *,
                   k: int = TOP_K, kazanim_kod: str | None = None,
                   tablo_dahil: bool = True) -> list[dict]:
        """Araç (chunk_egitim ve chunk_tablo) filtreleme sorgusu — mimari.md §12.1.
        Hedefe ulaşmak ve Kanıt'ı çözebilecek yetkinliği kazandırmak için
        kullanılan ders kitabı içeriklerini ve tablolarını filtreler.
        """
        if isinstance(soru_veya_vektor, str):
            soru_temiz = soru_veya_vektor.replace("\xad", "").strip()
            vektor = self.embed_model.encode(soru_temiz, normalize_embeddings=True)
        else:
            vektor = soru_veya_vektor

        metin_adaylar = self._ilk_k_getir(conn, kitap_id, vektor, k, kazanim_kod=kazanim_kod)
        sonuclar = []
        for c in metin_adaylar:
            mesafe = c[3]
            skor = round(1 - float(mesafe), 4) if mesafe is not None else None
            sonuclar.append({
                "id": c[0],
                "sayfa": c[1],
                "metin": c[2],
                "mesafe": mesafe,
                "skor": skor,
                "tur": "metin",
                "kazanim_kod": kazanim_kod,
            })

        if tablo_dahil and TABLO_KAYNAGI and kazanim_kod is None:
            try:
                tablo_adaylar = self._tablo_getir(conn, kitap_id, vektor, TOP_K_TABLO)
                for c in tablo_adaylar:
                    mesafe = c[3]
                    skor = round(1 - float(mesafe), 4) if mesafe is not None else None
                    sonuclar.append({
                        "id": c[0],
                        "sayfa": c[1],
                        "metin": c[2],
                        "mesafe": mesafe,
                        "skor": skor,
                        "tur": "tablo",
                        "kazanim_kod": None,
                    })
            except Exception:  # noqa: BLE001
                conn.rollback()

        sonuclar.sort(key=lambda x: x["mesafe"] if x["mesafe"] is not None else 999.0)
        return sonuclar[:k]

    def uclu_sorgula(self, conn, soru: str, *,
                     sinif: int | None = None, ders: str | None = None,
                     kitap_id: int | None = None, kazanim_kod: str | None = None,
                     k_hedef: int = 5, k_kanit: int = 3, k_arac: int = TOP_N) -> dict:
        """Üçlü tasarım (Hedef, Kanıt, Araç) entegre filtreleme sorgusu — mimari.md §12.1.

        1. Hedef (kazanim): Öğrencinin edineceği beceri/kazanım çerçevesi.
        2. Kanıt (kazanim_test_soru): Kazanımın edinildiğini gösteren değerlendirme soruları.
        3. Araç (chunk_egitim/chunk_tablo): Öğrenmeyi sağlayan ders kitabı kaynakları.
        """
        # 1. Hedef
        hedefler = self.hedef_getir(
            conn, sinif=sinif, ders=ders, kazanim_kod=kazanim_kod, arama=soru, limit=k_hedef
        )
        if not hedefler and kazanim_kod:
            hedefler = self.hedef_getir(
                conn, sinif=sinif, ders=ders, kazanim_kod=kazanim_kod, limit=k_hedef
            )

        # 2. Kanıt
        kanitlar = self.kanit_getir(
            conn, soru, sinif=sinif, ders=ders, k=k_kanit
        )

        # 3. Araç
        araclar = []
        if kitap_id is not None:
            araclar = self.arac_getir(
                conn, kitap_id, soru, k=k_arac, kazanim_kod=kazanim_kod
            )

        return {
            "hedef": hedefler,
            "kanit": kanitlar,
            "arac": araclar,
        }

    def _tablo_getir(self, conn, kitap_id: int, vektor, k: int):
        """chunk_tablo'dan ilk-K aday. `_ilk_k_getir` ile AYNI şekle
        (id, sayfa_no, metin, mesafe) normalize edilir ki rerank/eşik/LLM
        yolu tablo ile metni ayırt etmek zorunda kalmasın."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sayfa_no, baslik, metin_ozet, embedding <=> %s AS mesafe
                FROM chunk_tablo
                WHERE kitap_id = %s
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, kitap_id, k),
            )
            satirlar = cur.fetchall()
        normal = []
        for _id, sayfa, baslik, ozet, mesafe in satirlar:
            bas = (baslik or "").strip()
            metin = (f"Tablo: {bas}. {ozet}" if bas else f"Tablo. {ozet}")
            normal.append((_id, sayfa, metin, mesafe))
        return normal

    def _aday_getir(self, conn, kaynak: str, kaynak_idler: list[int], vektor, k: int):
        tablo, kolon = _ARAMA_TABLOLARI[kaynak]
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe, {kolon}
                FROM {tablo}
                WHERE {kolon} = ANY(%s)
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, list(kaynak_idler), k),
            )
            return cur.fetchall()  # [(id, sayfa_no, metin, mesafe, kaynak_id), ...]

    def _tablo_aday_getir(self, conn, kitap_idler: list[int], vektor, k: int):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sayfa_no, baslik, metin_ozet, embedding <=> %s AS mesafe, kitap_id
                FROM chunk_tablo
                WHERE kitap_id = ANY(%s)
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, list(kitap_idler), k),
            )
            satirlar = cur.fetchall()
        sonuc = []
        for _id, sayfa, baslik, ozet, mesafe, kitap_id in satirlar:
            bas = (baslik or "").strip()
            sonuc.append((_id, sayfa, f"Tablo: {bas}. {ozet}" if bas else f"Tablo. {ozet}",
                          mesafe, kitap_id))
        return sonuc

    def ara(self, conn, kaynak: str, kaynak_idler: list[int], soru: str,
            k: int = TOP_N, esik: float = ESIK_BENZERLIK) -> dict:
        """Yalnızca vektör araması — LLM ve reranker YOK (Open WebUI filtresi,
        webui.py). Hiçbir tabloya YAZMAZ; loglamayı çağıran yapar. Tahta yolu
        (`sorgula`) bunu KULLANMAZ (Kural 5)."""
        if kaynak not in _ARAMA_TABLOLARI:
            raise ValueError(f"bilinmeyen kaynak: {kaynak!r}")
        bos = {"parcalar": [], "retrieval_ms": None, "rerank_ms": None, "en_iyi_skor": None}
        if not kaynak_idler:
            return {"durum": "zayif", **bos}

        soru = soru.replace("\xad", "").strip()
        t0 = time.perf_counter()
        try:
            vektor = self.embed_model.encode(soru, normalize_embeddings=True)
            aday_sozluk: dict[int, tuple] = {}
            for c in self._aday_getir(conn, kaynak, kaynak_idler, vektor, k):
                aday_sozluk[c[0]] = (c[0], c[1], c[2], c[3], "metin", c[4])
            if kaynak == "egitim" and TABLO_KAYNAGI:
                try:
                    for c in self._tablo_aday_getir(conn, kaynak_idler, vektor, k):
                        if c[0] not in aday_sozluk or c[3] < aday_sozluk[c[0]][3]:
                            aday_sozluk[c[0]] = (c[0], c[1], c[2], c[3], "tablo", c[4])
                except Exception:  # noqa: BLE001 — tablo araması yardımcı kaynak; hata olursa yalnızca metinle devam
                    conn.rollback()

            # Hibrit arama: k > TOP_N ise soru içindeki kanun/madde no veya anahtar kelimeleri de tara
            if k > TOP_N:
                tablo, kolon = _ARAMA_TABLOLARI[kaynak]
                sayilar = re.findall(r"\b\d+\b", soru)
                kelimeler = [w for w in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,}", soru)
                             if w.lower() not in _DURAK_KELIMELER]
                terimler = (sayilar + sorted(kelimeler, key=len, reverse=True))[:4]
                for term in terimler:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                f"""
                                SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe, {kolon}
                                FROM {tablo}
                                WHERE {kolon} = ANY(%s) AND metin ILIKE %s
                                LIMIT 4
                                """,
                                (vektor, list(kaynak_idler), f"%{term}%"),
                            )
                            for c in cur.fetchall():
                                if c[0] not in aday_sozluk:
                                    aday_sozluk[c[0]] = (c[0], c[1], c[2], c[3], "metin", c[4])
                    except Exception:  # noqa: BLE001
                        conn.rollback()

            adaylar = list(aday_sozluk.values())
        except Exception as e:  # noqa: BLE001 — arama hatası durum="hata" olarak döner
            return {"durum": "hata", **bos, "hata": f"{type(e).__name__}: {e}"}
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        if not adaylar:
            return {"durum": "zayif", **bos, "retrieval_ms": retrieval_ms}

        secilen = sorted(adaylar, key=lambda c: c[3])[:k]
        en_iyi = round(1 - float(secilen[0][3]), 4)
        ortak = {"retrieval_ms": retrieval_ms, "rerank_ms": None, "en_iyi_skor": en_iyi}
        if en_iyi < esik:
            return {"durum": "zayif", "parcalar": [], **ortak}
        parcalar = [{"kaynak_id": int(c[5]), "sayfa": int(c[1]), "metin": c[2],
                     "skor": round(1 - float(c[3]), 4), "tur": c[4]} for c in secilen]
        return {"durum": "ok", "parcalar": parcalar, **ortak}

    def _llm_cevap(self, sistem: str, soru: str, timeout: float = 30.0) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            # Gemma/qwen3.x varsayılan olarak düşünür; 30 sn zaman aşımını ve "≤3
            # cümle" kuralını korumak için kapalı (2026-10-02).
            "think": False,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": sistem},
                {"role": "user", "content": soru},
            ],
        }
        req = urllib.request.Request(
            f"http://{self.ollama_host}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        return d["message"]["content"]

    def _logla(self, conn, *, tahta_id, sinif, ders, soru, sonuc, ham_cevap,
               toplam_ms, retrieval_ms, rerank_ms, llm_ms, en_iyi_skor,
               chunk_idler, skorlar) -> None:
        """metrik HER ZAMAN yazılır (içerik yok). soru_log yalnızca
        CLAUDE.md'nin "Loglama" tablosundaki durumlarda — mimari.md §13."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO metrik
                        (tahta_id, retrieval_ms, rerank_ms, llm_toplam_ms,
                         toplam_ms, sonuc, en_yuksek_skor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tahta_id, retrieval_ms, rerank_ms, llm_ms, toplam_ms,
                     sonuc, en_iyi_skor),
                )

            dusuk_skorlu_ok = sonuc == "ok" and en_iyi_skor is not None and en_iyi_skor < DUSUK_SKOR_ESIGI
            metin_saklanmali = sonuc != "ok" or dusuk_skorlu_ok
            if metin_saklanmali:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO soru_log
                            (tahta_id, sinif, ders, soru_metni, donen_chunk_idler,
                             skorlar, cevap_metni, sonuc)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (tahta_id, sinif, ders, soru, chunk_idler or None,
                         skorlar or None, ham_cevap, sonuc),
                    )
            conn.commit()
        except Exception:
            # Loglama dersi bozmaz (mimari.md §2) — hata olursa yut, cevabı etkileme.
            conn.rollback()

    def sorgula(self, conn, kitap_id: int, soru: str, *,
                sinif: int | None = None, ders: str | None = None,
                tahta_id: int | None = None,
                kazanim_kod: str | None = None) -> dict:
        """Dönen dict: status, answer, sources ([{chunk_id, sayfa}]), latency_ms."""
        t0 = time.perf_counter()

        # ── Embedding + ilk-K arama + rerank — hiçbiri sarmalanmamıştı ──
        # (2026-08-11 bulundu): çok uzun bir `soru` (~6000 karakter, tekrarlı
        # metin) reranker'ı (cuda:0, qwen2.5:14b ile aynı kart) CUDA OOM'a
        # düşürdü — istisna buradan main.py'ye kadar YAKALANMADAN çıkıp çıplak
        # 500 döndürdü VE `metrik`e hiç yazılmadı ("HER ZAMAN yazılır" iddiası
        # bu yüzden yanlıştı). LLM adımı zaten aynı desenle sarmalıydı
        # (aşağıda) — burası da aynı desene alındı: `hata` durumu + loglama.
        try:
            vektor = self.embed_model.encode(soru, normalize_embeddings=True)
            # (id, sayfa, metin, mesafe, tur) — `tur` yalnızca kaynak
            # etiketlemesi/loglama için; rerank ve eşik ikisine de aynı
            # şekilde uygulanır.
            # 6. eleman = rerank'e giden metin görünümü (metin adaylarında
            # tam metnin kendisi, tablo adaylarında kırpılmışı).
            adaylar = [(*c[:4], "metin",
                        c[2][:RERANK_METIN_KARAKTER] if RERANK_METIN_KARAKTER else c[2])
                       for c in self._ilk_k_getir(conn, kitap_id, vektor, TOP_K, kazanim_kod=kazanim_kod)]
            if TABLO_KAYNAGI and kazanim_kod is None:
                # Tablo tarafı BAĞIMSIZ sarmalı: chunk_tablo yoksa/boşsa/
                # sorgu patlarsa RAG'ın metin yolu HİÇ etkilenmemeli
                # (mimari.md §2 — "Farabi asla dersi bozmaz"). Bu, aynı
                # zamanda FAZ 1'in fiilî geri dönüş garantisi.
                try:
                    adaylar += [(*c, "tablo", c[2][:RERANK_TABLO_KARAKTER])
                                for c in self._tablo_getir(conn, kitap_id, vektor, TOP_K_TABLO)]
                except Exception:
                    conn.rollback()
            retrieval_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="hata", ham_cevap=f"{type(e).__name__}: {e}", toplam_ms=toplam_ms,
                        retrieval_ms=None, rerank_ms=None, llm_ms=None,
                        en_iyi_skor=None, chunk_idler=[], skorlar=[])
            return {"status": "hata", "answer": None, "sources": [], "latency_ms": toplam_ms,
                    "hata": f"{type(e).__name__}: {e}"}

        if not adaylar:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=None, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=None, llm_ms=None,
                        en_iyi_skor=None, chunk_idler=[], skorlar=[])
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        t1 = time.perf_counter()
        try:
            ciftler = [(soru, c[5]) for c in adaylar]
            skorlar_ham = self.reranker.predict(ciftler)
        except Exception as e:
            rerank_ms = int((time.perf_counter() - t1) * 1000)
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="hata", ham_cevap=f"{type(e).__name__}: {e}", toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=None,
                        en_iyi_skor=None, chunk_idler=[], skorlar=[])
            return {"status": "hata", "answer": None, "sources": [], "latency_ms": toplam_ms,
                    "hata": f"{type(e).__name__}: {e}"}
        siralanmis = sorted(zip(adaylar, skorlar_ham), key=lambda x: x[1], reverse=True)
        rerank_ms = int((time.perf_counter() - t1) * 1000)
        top_n = siralanmis[:TOP_N]
        en_iyi_skor = float(top_n[0][1])
        # chunk_egitim.id ve chunk_tablo.id AYRI bigserial dizileri — aynı
        # sayı iki farklı satır demek olabilir. `soru_log.donen_chunk_idler`
        # (integer[]) şemasını değiştirmeden ayırt edebilmek için tablo
        # kaynakları NEGATİF yazılır: -12 = chunk_tablo.id 12.
        chunk_idler = [(-int(c[0]) if c[4] == "tablo" else int(c[0])) for c, _ in top_n]
        skor_listesi = [round(float(s), 4) for _, s in top_n]

        # ── ANA savunma (mimari.md §8 adım 5) — eşiğin altındaysa LLM'e hiç gitme ──
        if en_iyi_skor < ESIK_RERANK:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=None, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=None,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        kaynaklar = [{"chunk_id": (-int(c[0]) if c[4] == "tablo" else int(c[0])),
                      "sayfa": c[1], "tur": c[4]} for c, _ in top_n]
        kaynak_metin = "\n\n".join(
            f"[{'tablo' if c[4] == 'tablo' else 'chunk'}] (s. {c[1]}) {c[2]}" for c, _ in top_n)
        sistem = SISTEM_SABLON.format(kaynak=kaynak_metin)

        # ── ORTA savunma (mimari.md §8 adım 6) — katı prompt + YETERSIZ_KAYNAK ──
        t2 = time.perf_counter()
        try:
            cevap = self._llm_cevap(sistem, soru)
        except Exception as e:
            llm_ms = int((time.perf_counter() - t2) * 1000)
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="hata", ham_cevap=f"{type(e).__name__}: {e}", toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "hata", "answer": None, "sources": [], "latency_ms": toplam_ms,
                    "hata": f"{type(e).__name__}: {e}"}
        llm_ms = int((time.perf_counter() - t2) * 1000)

        yetersiz = "YETERSIZ_KAYNAK" in cevap.upper().replace("İ", "I")
        if yetersiz:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=cevap, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        # ── EK savunma (mimari.md §8 adım 7) — cevaptaki sayılar kaynakta yoksa reddet ──
        if not _sayilar_kaynakta_mi(cevap, kaynak_metin):
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="sayi_kontrolu_reddi", ham_cevap=cevap, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "sayi_kontrolu_reddi", "answer": None, "sources": [], "latency_ms": toplam_ms}

        toplam_ms = int((time.perf_counter() - t0) * 1000)
        self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                    sonuc="ok", ham_cevap=cevap, toplam_ms=toplam_ms,
                    retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                    en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
        return {"status": "ok", "answer": cevap.strip(), "sources": kaynaklar, "latency_ms": toplam_ms}
