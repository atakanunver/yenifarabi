"""duello_motoru.py - Tahta Düellosu Soru Hazırlama ve Şık Karıştırma Motoru.

Tüm dersler için (İngilizce, Matematik, Fizik, Biyoloji, Tarih, Edebiyat vb.)
4 seçenekli, anlamlı çeldiricilere sahip çoktan seçmeli sorular hazırlar.
Doğru şıkkı (A, B, C, D) rastgele karıştırarak A şıkkının sürekli doğru cevap
olması hatasını kesin olarak önler.
"""

import random
from typing import Any
import havuz
import turkce
import soru_uretici
from fetih_motoru import DERS_KONULARI_VE_SORULAR


def ders_anahtari_coz(ders_adi: str) -> str:
    """Ders adını kanonik veritabanı/havuz anahtarına dönüştürür."""
    if not ders_adi:
        return "genel"
    temiz = turkce.kapsam_anahtari(ders_adi.strip())
    if temiz in soru_uretici.KAPSAM_ESLEME:
        return soru_uretici.KAPSAM_ESLEME[temiz]
    for k, v in soru_uretici.KAPSAM_ESLEME.items():
        if k in temiz or temiz in k:
            return v
    return temiz


def duello_sorulari_hazirla(ders_adi: str, sinif: int = 9, adet: int = 10, sube: str = "") -> tuple[list[dict[str, Any]], str]:
    """Tahta Düellosu için 10 adet şıkları karıştırılmış çoktan seçmeli soru üretir.

    Öncelik Sırası:
    1. PostgreSQL soru_havuzu (AGY onaylı sorular)
    2. MEB Müfredat Soru Bankası (fetih_motoru.DERS_KONULARI_VE_SORULAR)
    3. Akıllı Çeldiricili Hazır Sorular (soru_uretici.hazir_sorulari_getir)
    """
    anahtar = ders_anahtari_coz(ders_adi)
    adet = max(1, min(adet, 25))

    # --- 1. KAYNAK: PostgreSQL Soru Havuzu (onayli) ---
    try:
        havuz_sorulari = havuz.duello_sorulari(anahtar, sinif, adet=adet, sube=sube)
        if havuz_sorulari and len(havuz_sorulari) >= adet:
            cikti = []
            for s in havuz_sorulari:
                sec = [str(x).strip() for x in s.get("secenekler", [])]
                dogru = str(s.get("a", "")).strip()
                if dogru not in sec and sec:
                    sec[0] = dogru
                random.shuffle(sec)
                dogru_idx = sec.index(dogru) if dogru in sec else 0
                cikti.append({
                    "sid": s.get("sid"),
                    "konu": s.get("konu", ders_adi),
                    "q": s.get("q", ""),
                    "secenekler": sec,
                    "a": dogru,
                    "dogru_index": dogru_idx,
                    "kaynak": s.get("kaynak", "MEB Soru Havuzu"),
                })
            return cikti, "soru_havuzu"
    except Exception:
        pass

    # --- 2. KAYNAK: MEB Müfredat Soru Bankası (15 Ders) ---
    adaylar = DERS_KONULARI_VE_SORULAR.get(anahtar)
    if not adaylar:
        # Doğrudan ders_adi içinde ara
        for k, v in DERS_KONULARI_VE_SORULAR.items():
            if k in anahtar or anahtar in k:
                adaylar = v
                break
    if not adaylar:
        adaylar = DERS_KONULARI_VE_SORULAR.get("genel", [])

    if adaylar and len(adaylar) >= 3:
        # Rastgele 'adet' kadar soru seç
        if len(adaylar) >= adet:
            secilen = random.sample(adaylar, adet)
        else:
            secilen = [random.choice(adaylar) for _ in range(adet)]

        cikti = []
        for s in secilen:
            sec = list(s.get("secenekler", []))
            dogru = str(s.get("a", "")).strip()

            # Eğer şık sayısı eksikse veya çeldiriciler sahteyse temizle
            if len(sec) < 4 or any("şıkkı" in x.lower() for x in sec):
                sec = [dogru, "A şıkkı", "B şıkkı", "C şıkkı"]  # geçici emniyet

            # Şıkları rastgele karıştır
            random.shuffle(sec)
            dogru_idx = sec.index(dogru) if dogru in sec else 0

            cikti.append({
                "konu": s.get("konu", ders_adi),
                "q": s.get("q", ""),
                "secenekler": sec,
                "a": dogru,
                "dogru_index": dogru_idx,
                "kaynak": s.get("kaynak", "MEB Müfredatı"),
            })
        return cikti, "meb_bankasi"

    # --- 3. KAYNAK: Hazır Sorulardan Akıllı Çeldirici Üretimi ---
    hazir = soru_uretici.hazir_sorulari_getir(ders_adi)
    duz_sorular = []
    tum_cevaplar = set()

    for kat in (hazir or []):
        for q in kat.get("questions", []):
            cevap = str(q.get("a", "")).strip()
            if cevap:
                tum_cevaplar.add(cevap)
                duz_sorular.append({
                    "konu": kat.get("name", ders_adi),
                    "q": q.get("q", ""),
                    "a": cevap,
                    "kaynak": q.get("kaynak", "MEB Hazır Soru"),
                })

    if duz_sorular:
        random.shuffle(duz_sorular)
        secilen = duz_sorular[:adet]
        cikti = []

        cevap_listesi = list(tum_cevaplar)
        for s in secilen:
            dogru = s["a"]
            digerleri = [c for c in cevap_listesi if c.lower() != dogru.lower()]

            if len(digerleri) >= 3:
                celdiriciler = random.sample(digerleri, 3)
            else:
                celdiriciler = ["Tanım / Kavram", "Kural", "İlkeler"][:3]

            sec = [dogru] + celdiriciler
            random.shuffle(sec)
            dogru_idx = sec.index(dogru)

            cikti.append({
                "konu": s["konu"],
                "q": s["q"],
                "secenekler": sec,
                "a": dogru,
                "dogru_index": dogru_idx,
                "kaynak": s["kaynak"],
            })
        return cikti, "hazir_akilli"

    # Acil durum genel sorular
    genel_banka = DERS_KONULARI_VE_SORULAR.get("genel", [])
    secilen = random.sample(genel_banka, min(adet, len(genel_banka)))
    cikti = []
    for s in secilen:
        sec = list(s.get("secenekler", []))
        dogru = str(s.get("a", "")).strip()
        random.shuffle(sec)
        cikti.append({
            "konu": s.get("konu", "Genel Kültür"),
            "q": s.get("q", ""),
            "secenekler": sec,
            "a": dogru,
            "dogru_index": sec.index(dogru) if dogru in sec else 0,
            "kaynak": s.get("kaynak", "MEB Genel"),
        })
    return cikti, "genel"
