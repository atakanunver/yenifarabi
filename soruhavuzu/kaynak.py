"""soruhavuzu/kaynak.py — bir kazanım için ders kitabından veya kazanım testlerinden en ilgili parçaları bulur (farabi DB, pgvector).
Gömme bilgehan bge-m3; RAG ile aynı `embedding <=> vektör` kalıbı (server/rag.py::_ilk_k_getir)."""

from soruhavuzu import dersler

ESIK = 0.45


def kitap_idleri(farabi_conn, sinif: int, ders: str) -> list[int]:
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT id, ders FROM kitap WHERE sinif = %s", (sinif,))
        return [kid for kid, ad in cur.fetchall() if dersler.ders_anahtari(ad) == ders]


def bul(farabi_conn, gomucu, sinif: int, ders: str, kazanim_metin: str, k: int = 3) -> dict | None:
    idler = kitap_idleri(farabi_conn, sinif, ders)
    v = list(map(float, gomucu.encode([kazanim_metin], normalize_embeddings=True)[0]))
    vektor = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    if idler:
        with farabi_conn.cursor() as cur:
            cur.execute("SELECT id, sayfa_no, metin, embedding <=> %s::vector AS mesafe FROM chunk_egitim "
                        "WHERE kitap_id = ANY(%s) ORDER BY mesafe LIMIT %s", (vektor, idler, k))
            parcalar = cur.fetchall()
        if parcalar and 1 - float(parcalar[0][3]) >= ESIK:
            sayfalar = sorted({p[1] for p in parcalar})
            ad = ders.capitalize() if ders != "cografya" else "Coğrafya"
            aralik = f"{sayfalar[0]}" if len(sayfalar) == 1 else f"{sayfalar[0]}-{sayfalar[-1]}"
            return {"etiket": f"{ad} {sinif}, s. {aralik}", "metin": "\n\n".join(p[2] for p in parcalar),
                    "chunk_idler": [p[0] for p in parcalar], "skor": 1 - float(parcalar[0][3])}
    try:
        with farabi_conn.cursor() as cur:
            cur.execute("SELECT DISTINCT ders FROM kazanim_test_soru WHERE sinif = %s", (sinif,))
            adlar = [r[0] for r in cur.fetchall() if dersler.ders_anahtari(r[0] or "") == ders]
            if adlar:
                cur.execute(
                    "SELECT id, soru_no, soru_metni, secenekler, kaynak_dosya, "
                    "embedding <=> %s::vector AS mesafe FROM kazanim_test_soru "
                    "WHERE sinif = %s AND ders = ANY(%s) AND embedding IS NOT NULL "
                    "ORDER BY mesafe LIMIT %s",
                    (vektor, sinif, adlar, k),
                )
                kt_parcalar = cur.fetchall()
                if kt_parcalar and 1 - float(kt_parcalar[0][5]) >= ESIK:
                    soru_metinleri = [f"Örnek Soru {row[1]}: {row[2]}" for row in kt_parcalar]
                    ad = ders.capitalize() if ders != "cografya" else "Coğrafya"
                    dosya = kt_parcalar[0][4]
                    return {
                        "etiket": f"Kazanım Testi {ad} {sinif} ({dosya})",
                        "metin": "\n\n".join(soru_metinleri),
                        "chunk_idler": [p[0] for p in kt_parcalar],
                        "skor": 1 - float(kt_parcalar[0][5]),
                    }
    except Exception:
        pass
    return None
