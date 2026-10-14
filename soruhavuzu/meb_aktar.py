"""soruhavuzu/meb_aktar.py — farabi.kazanim_test_soru tablosundaki resmi MEB sorularını
soru_havuzu veritabanına aktarır (Tahta Düellosu, Sınıf Arenası ve smual.app için).
"""

import json
import logging
import psycopg2

from soruhavuzu import dersler, sik

log = logging.getLogger("soruhavuzu.meb_aktar")


def meb_sorulari_aktar(kuru: bool = False) -> dict:
    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")

    with farabi.cursor() as cur:
        cur.execute("""
            SELECT id, kaynak_dosya, sinif, ders, konu, test_no, soru_no,
                   soru_metni, secenekler, cevap
            FROM kazanim_test_soru
            WHERE cevap IS NOT NULL AND trim(cevap) != ''
            ORDER BY ders, kaynak_dosya, soru_no;
        """)
        satirlar = cur.fetchall()

    print(f"[meb_aktar] farabi DB'sinden {len(satirlar)} adet cevaplı MEB sorusu okundu.")

    # soru_havuzu'nda mevcut olan kaynakları al (tekrar eklememek için)
    with havuz.cursor() as cur:
        cur.execute("SELECT kaynak FROM soru WHERE kaynak LIKE 'MEB Kazanım Testi:%';")
        mevcut_kaynaklar = {r[0] for r in cur.fetchall()}

    aktarilan = 0
    atlanan = 0
    hatali = 0
    ders_sayac = {}

    birim_cache = {}

    for sid, dosya, sinif, ham_ders, konu, test_no, soru_no, soru_metni, secenekler, cevap in satirlar:
        ders_key = dersler.ders_anahtari(ham_ders) or "genel"
        kaynak_str = f"MEB Kazanım Testi: {dosya} (Test {test_no or 1}, Soru {soru_no})"

        if kaynak_str in mevcut_kaynaklar:
            atlanan += 1
            continue

        if not isinstance(secenekler, dict) or cevap not in secenekler:
            hatali += 1
            continue

        dogru_metin = secenekler[cevap].strip()
        if not dogru_metin:
            hatali += 1
            continue

        # 5 şıkkı (A-E) 4 şıkka indirgeme
        if cevap in ["A", "B", "C", "D"]:
            secim = [secenekler.get(k, "").strip() for k in ["A", "B", "C", "D"] if secenekler.get(k)]
            if len(secim) < 4 and "E" in secenekler:
                secim.append(secenekler["E"].strip())
        else:  # cevap == 'E'
            secim = [dogru_metin]
            for k in ["A", "B", "C", "D"]:
                val = secenekler.get(k, "").strip()
                if val and val != dogru_metin and len(secim) < 4:
                    secim.append(val)

        if len(secim) < 4 or dogru_metin not in secim:
            hatali += 1
            continue

        secim = secim[:4]
        try:
            dogru_idx = secim.index(dogru_metin)
        except ValueError:
            hatali += 1
            continue

        # Kanonik sıralama (şık dengesi için hash tabanlı)
        kanonik_secenekler, yeni_dogru_idx = sik.kanonik_sira(soru_metni, secim, dogru_idx)

        konu_str = konu or f"{ham_ders} Test {test_no or 1}"
        birim_anahtar = f"kazanim:{dosya}:{test_no or 1}"

        zorluk = ((soru_no - 1) % 4) + 1 if soru_no else 2

        if not kuru:
            # kaynak_birim bul veya oluştur
            if birim_anahtar not in birim_cache:
                with havuz.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'islendi', now())
                        ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
                        RETURNING id;
                        """,
                        (
                            "kazanim",
                            birim_anahtar,
                            ders_key,
                            sinif or 12,
                            f"Kazanım Testi: {ham_ders} {sinif or 12}, Test {test_no or 1}",
                            f"{ham_ders} {sinif or 12}. Sınıf MEB ÖDSGM Kazanım Kavrama Testi ({dosya})",
                        ),
                    )
                    birim_id = cur.fetchone()[0]
                    birim_cache[birim_anahtar] = birim_id
            else:
                birim_id = birim_cache[birim_anahtar]

            with havuz.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO soru (
                        birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler,
                        dogru_index, zorluk, kaynak, durum, denetim_notu, olusturma, denetim_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s::jsonb,
                        %s, %s, %s, 'onayli', %s, now(), now()
                    );
                    """,
                    (
                        birim_id,
                        ders_key,
                        sinif or 12,
                        konu_str,
                        soru_metni,
                        dogru_metin,
                        json.dumps(kanonik_secenekler, ensure_ascii=False),
                        yeni_dogru_idx,
                        zorluk,
                        kaynak_str,
                        "MEB ÖDSGM Resmi Kazanım Kavrama Testi (Cevap Anahtarlı)",
                    ),
                )

        aktarilan += 1
        ders_sayac[ders_key] = ders_sayac.get(ders_key, 0) + 1

    if not kuru:
        havuz.commit()

    farabi.close()
    havuz.close()

    return {
        "toplam": len(satirlar),
        "aktarilan": aktarilan,
        "atlanan": atlanan,
        "hatali": hatali,
        "ders_dagilimi": ders_sayac,
    }


if __name__ == "__main__":
    import sys
    kuru = "--kuru" in sys.argv
    sonuc = meb_sorulari_aktar(kuru=kuru)
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))
