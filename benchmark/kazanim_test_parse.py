"""
benchmark/kazanim_test_parse.py — MEB ÖDSGM kazanım testi PDF'lerinin saf
ayrıştırma mantığı. DB/embedding/dosya I/O YOK — `kazanim_test_yukle.py` ve
`kazanim_test_cevap_esle.py` bu modülü import eder, testler ağsız çalışır
(embed_kitap.py'nin kendi hiç test kapsamı olmaması deseniyle tutarlı: bu
modül test edilebilir saf kısmı ayırıyor).

PDF YAPISI (2026-08-30, gerçek dosyalarda pdfplumber ile doğrulandı,
büyük dosyalar OKUNMADI — yalnızca birkaç sayfa örneklendi):

- Her sayfanın üstünde süsleme amaçlı bir kutu var: "12. Sınıf"/"Fizik" gibi
  metinler HER KARAKTERİ İKİŞER KEZ yazılmış hâlde geliyor ("1122.. SSıınnııff"
  -> collapse edilince "12. Sınıf"). Bunun hemen altında kurum adı TERSTEN
  yazılmış ayrı satırlar var ("üğülrüdüM" = "Müdürlüğü" ters) — bunlar saf
  gürültü, İÇERİK DEĞİL, atlanır (tek kelime + boşluksuz olmaları ile
  tanınır, gerçek başlıklar boşluk içerir).
- Konu başlığı (ör. "Çembersel Hareketler – 1") gürültüden sonra, ilk
  sorudan önce gelen, boşluk içeren düz bir satır.
- Sorular `^\d{1,2}\.\s` ile başlar, `A) ... B) ... C) ... D) ... E) ...`
  şıklarıyla biter. Sayfa İKİ SÜTUNLU ama pdfplumber varsayılan okuma
  sırasıyla soru numaraları hâlâ ARTAN sırada çıkıyor (doğrulandı).
"""

import re

_BASLIK_DESENI = re.compile(r"^(\d{1,2})\.\.?\s*[Ss][Iı]{2}[Nn]{2}[Iı]{2}[Ff]{2}$")
_SORU_BASI = re.compile(r"^(\d{1,2})\.(?:\s+(.*))?$")  # "8." tek başına da olabilir (İngilizce)
_ORTAK_METIN = re.compile(r"^For questions?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\b", re.IGNORECASE)
_SIK_DESENI = re.compile(r"([A-E])\)\s*")
_SINIF_SATIRI = re.compile(r"^\d{1,2}\.\s*[Ss]ınıf$")

# Dosya adı öneki -> DB'deki ders adı (başlıktan ders çıkmayan seriler için
# yedek; yalnızca "12sinif_<ders>_" kalıbı — müfredat kitapçıkları ve
# "1.pdf" gibi adlar bilerek eşleşmez).
_DERS_DOSYA_ONEKI = {
    "biyoloji": "Biyoloji", "tarih": "Tarih", "cografya": "Coğrafya",
    "ingilizce": "İngilizce", "kimya": "Kimya", "fizik": "Fizik",
    "matematik": "Matematik",
}
# Başlıkta İngilizce yazan ders adları (Türkçe karşılığına çevrilir).
_DERS_ESLEME = {"English": "İngilizce"}


def ders_dosya_adindan(dosya_adi: str) -> str | None:
    """'12sinif_tarih_1.pdf' -> 'Tarih'. Tanınmazsa None."""
    m = re.match(r"^\d{1,2}sinif_([a-z]+)_", dosya_adi.lower())
    return _DERS_DOSYA_ONEKI.get(m.group(1)) if m else None


def _cift_karakter_coz(satir: str) -> str:
    """'1122.. SSıınnııff' -> '12. Sınıf' — süsleme kutusu her karakteri
    ikişer kez basıyor, ardışık aynı karakterleri teke indirger. YALNIZCA
    başlık satırlarına uygulanır (soru gövdesine değil — orada rastgele
    bir çift harf yanlışlıkla "düzeltilebilir")."""
    return re.sub(r"(.)\1", r"\1", satir)


def baslik_bilgisi_cikar(ilk_sayfa_metni: str) -> tuple[int | None, str | None]:
    """İlk sayfanın ilk birkaç satırından (sinif, ders) çıkarır — süsleme
    kutusunun çift-karakter kodunu çözerek. Bulunamazsa (None, None) —
    çağıran bunu dosya adı gibi başka bir ipucuyla tamamlayabilir, hiçbir
    soru bu yüzden atlanmaz.

    Ders adı TEK kelime olabilir ("Fizik", her satır kendi başına ikişer kez
    basılı) YA DA birden fazla satıra yayılmış birden fazla kelime olabilir
    ("Din Kültürü ve" + "Ahlak Bilgisi", her parça yine ikişer kez basılı) —
    2026-08-31'de gerçek DKAB/edebiyat dosyalarında bulundu: ilk sürüm yalnızca
    tek-kelimelik dersleri (Fizik/Matematik/Kimya) tanıyordu, çok kelimeli
    dersleri (Din Kültürü ve Ahlak Bilgisi, Türk Dili ve Edebiyatı) ya hiç
    çıkaramıyor ya da yarım çıkarıyordu ("Edebiyatı" gibi). Artık "N. Sınıf"
    satırından sonraki, kurum-adı satırına ("MEB" geçen) kadarki ardışık
    tekrarsız satırlar birleştirilip ders adı yapılıyor."""
    ham_satirlar = [s.strip() for s in ilk_sayfa_metni.splitlines()[:12] if s.strip()]
    sinif = None
    sinif_indeksi = None
    for i, satir in enumerate(ham_satirlar):
        m = re.match(r"^(\d{1,2})\.\s*[Ss]ınıf$", _cift_karakter_coz(satir))
        if not m:
            # İngilizce serisi: "12th Grade"
            m = re.match(r"^(\d{1,2})(?:th|st|nd|rd)\s+Grade$", satir)
        if m:
            sinif = int(m.group(1))
            sinif_indeksi = i
            break
    if sinif is None:
        return None, None

    _DERS_PARCA = re.compile(r"^[A-Za-zÇĞİIÖŞÜçğıiöşü ]+$")
    parcalar: list[str] = []
    onceki = None
    for satir in ham_satirlar[sinif_indeksi + 1:]:
        cozulmus = _cift_karakter_coz(satir)
        if re.match(r"^(\d{1,2})\.\s*[Ss]ınıf$", cozulmus) or re.match(
                r"^(\d{1,2})(?:th|st|nd|rd)\s+Grade$", satir):
            continue  # "12. Sınıf" ikinci kopyası
        if not _DERS_PARCA.match(cozulmus):
            # rakam/formül/soru gövdesi içeren ilk satır — ders adı bitti
            break
        if cozulmus == onceki:
            continue  # aynı parçanın ikinci (çift basım) kopyası
        parcalar.append(cozulmus)
        onceki = cozulmus
    ders = " ".join(p.rstrip() for p in parcalar).strip() or None
    ders = _DERS_ESLEME.get(ders, ders)
    return sinif, ders


def konu_cikar(ilk_sayfa_metni: str) -> str | None:
    """Gürültüden sonra, ilk sorudan önceki son 'gerçek' (boşluklu) satırı
    konu başlığı olarak alır. Tek kelimelik/boşluksuz satırlar (ters yazılmış
    kurum adı gürültüsü) atlanır."""
    aday = None
    for satir in ilk_sayfa_metni.splitlines():
        satir = satir.strip()
        if not satir:
            continue
        if _SORU_BASI.match(satir):
            break
        if " " in satir and not satir.isupper():
            aday = satir
    return aday


def _sayfa_basligini_temizle(tam_metin: str) -> str:
    """Süsleme kutusu HER SAYFADA tekrarlanıyor ("MEB ● Ölçme..." satırı +
    "N. Sınıf"/ders adı çift basılmış hâlde) — 2026-08-31'de bulundu:
    temizlenmeden `sorulari_ayir` "12. Sınıf" gibi satırları soru 12'nin
    başlangıcı sanıp gerçek soruların üstüne yazıyordu. Kurum satırını
    ("MEB" geçen) ve ardışık BİREBİR aynı satır çiftlerini (çift-basım
    artefaktı — ders adı, "N. Sınıf") atar. Konu başlığı (ör. "Çembersel
    Hareketler – 1", sayfa altında TEK kez basılı) burada YAKALANMAZ —
    kasıtlı: hangi sorunun sonuna denk geldiği garanti değil, bilinçli
    olarak son sorunun metnine küçük bir kuyruk gürültü olarak bırakılıyor."""
    satirlar = tam_metin.splitlines()
    temiz: list[str] = []
    i = 0
    while i < len(satirlar):
        satir = satirlar[i]
        if "MEB" in satir:
            i += 1
            continue
        if i + 1 < len(satirlar) and satir.strip() and satir == satirlar[i + 1]:
            i += 2
            continue
        temiz.append(satir)
        i += 1
    return "\n".join(temiz)


def sorulari_ayir(tam_metin: str) -> list[dict]:
    """Tüm PDF metnini (sayfalar birleştirilmiş) soru listesine ayırır.
    Her öge: {"soru_no": int, "soru_metni": str, "secenekler": dict|None}."""
    satirlar = _sayfa_basligini_temizle(tam_metin).splitlines()
    bloklar: list[tuple[int, list[str]]] = []
    guncel_no, guncel_satirlar = None, []
    son_no = None  # son kabul edilen soru numarası (ardışıklık denetimi)
    # İngilizce: "For questions 8-12, choose…" + ortak metin, sorular arasında
    # durur; önceki sorunun E şıkkına yapışmasın diye ayrı tamponda toplanır
    # ve 8..12. soruların başına eklenir.
    ortak_tampon: list[str] | None = None
    ortaklar: list[tuple[int, int, str]] = []
    ortak_aralik = (0, 0)
    for satir in satirlar:
        # lstrip (rstrip DEĞİL): "N.\t" gibi satırlarda numaranın hemen
        # ardından TEK içerik satır sonuna kadar sarkan bir tab/boşluk
        # geliyor (2026-08-31'de mat_1.pdf'de bulundu) — rstrip/strip bunu
        # silip _SORU_BASI'nin \s+ şartını kırıyor, soru numarası hiç
        # yakalanmıyordu.
        m = _SORU_BASI.match(satir.lstrip())
        # Soru numarası ARDIŞIK olmalı (önceki+1): kimyada şekil etiketleri
        # ("1. kap", "2. kap"), tarihte sayfa altı konu başlığı ("20. Yüzyıl
        # Başlarında…") ve "12. Sınıf" başlığı soru başı sanılıyordu. İlk
        # soru herhangi bir numarayla başlayabilir (eski davranış).
        if m and _SINIF_SATIRI.match(satir.strip()):
            m = None
        if m and son_no is not None and int(m.group(1)) != son_no + 1:
            m = None
        om = None if m else _ORTAK_METIN.match(satir.strip())
        if m:
            if guncel_no is not None:
                bloklar.append((guncel_no, guncel_satirlar))
            if ortak_tampon is not None:
                ortaklar.append((*ortak_aralik, " ".join(t for t in ortak_tampon if t)))
                ortak_tampon = None
            guncel_no = son_no = int(m.group(1))
            guncel_satirlar = [(m.group(2) or "").strip()]
        elif om:
            if guncel_no is not None:
                bloklar.append((guncel_no, guncel_satirlar))
                guncel_no, guncel_satirlar = None, []
            if ortak_tampon is not None:
                ortaklar.append((*ortak_aralik, " ".join(t for t in ortak_tampon if t)))
            ortak_aralik = (int(om.group(1)), int(om.group(2)))
            ortak_tampon = [satir.strip()]
        elif ortak_tampon is not None:
            ortak_tampon.append(satir.strip())
        elif guncel_no is not None:
            guncel_satirlar.append(satir.strip())
    if guncel_no is not None:
        bloklar.append((guncel_no, guncel_satirlar))

    sonuc = []
    for no, satirlar in bloklar:
        blok_metni = " ".join(s for s in satirlar if s)
        ilk_sik = _SIK_DESENI.search(blok_metni)
        if ilk_sik:
            soru_metni = blok_metni[:ilk_sik.start()].strip()
            sik_kismi = blok_metni[ilk_sik.start():]
            parcalar = _SIK_DESENI.split(sik_kismi)[1:]  # [harf, metin, harf, metin, ...]
            secenekler = {}
            for i in range(0, len(parcalar) - 1, 2):
                harf, metin = parcalar[i], parcalar[i + 1].strip()
                if harf in "ABCDE":
                    secenekler[harf] = metin
            secenekler = secenekler or None
        else:
            soru_metni = blok_metni.strip()
            secenekler = None
        for bas, son, ortak_metin in ortaklar:
            if bas <= no <= son and ortak_metin:
                soru_metni = f"{ortak_metin} {soru_metni}".strip()
        if soru_metni:
            sonuc.append({"soru_no": no, "soru_metni": soru_metni, "secenekler": secenekler})
    return sonuc


def cevap_anahtari_ayir(metin: str) -> dict[int, dict[int, str]]:
    """'Test 1  1.B 2.E 3.D ...' satırlarını {test_no: {soru_no: harf}}'e
    çevirir."""
    sonuc: dict[int, dict[int, str]] = {}
    for satir in metin.splitlines():
        m = re.match(r"^\s*Test\s+(\d+)\s+(.*)$", satir.strip())
        if not m:
            continue
        test_no = int(m.group(1))
        cevaplar = {int(no): harf for no, harf in
                    re.findall(r"(\d{1,2})\.\s*([A-E])\b", m.group(2))}
        if cevaplar:
            sonuc[test_no] = cevaplar
    return sonuc
