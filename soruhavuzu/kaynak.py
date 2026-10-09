"""soruhavuzu/kaynak.py — bir kazanım için ders kitabından en ilgili parçaları bulur (farabi DB, pgvector).
Gömme bilgehan bge-m3; RAG ile aynı `embedding <=> vektör` kalıbı (server/rag.py::_ilk_k_getir)."""

from soruhavuzu import dersler

ESIK = 0.45


def kitap_idleri(farabi_conn, sinif: int, ders: str) -> list[int]:
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT id, ders FROM kitap WHERE sinif = %s", (sinif,))
        return [kid for kid, ad in cur.fetchall() if dersler.ders_anahtari(ad) == ders]


def bul(farabi_conn, gomucu, sinif: int, ders: str, kazanim_metin: str, k: int = 3) -> dict | None:
    idler = kitap_idleri(farabi_conn, sinif, ders)
    if not idler:
        return None
    v = list(map(float, gomucu.encode([kazanim_metin], normalize_embeddings=True)[0]))
    vektor = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    with farabi_conn.cursor() as cur:
        cur.execute(
            "SELECT id, sayfa_no, metin, embedding <=> %s::vector AS mesafe FROM chunk_egitim "
            "WHERE kitap_id = ANY(%s) ORDER BY mesafe LIMIT %s",
            (vektor, idler, k),
        )
        parcalar = cur.fetchall()
    if not parcalar or 1 - float(parcalar[0][3]) < ESIK:
        return None
    sayfalar = sorted({p[1] for p in parcalar})
    ad = ders.capitalize() if ders != "cografya" else "Coğrafya"
    aralik = f"{sayfalar[0]}" if len(sayfalar) == 1 else f"{sayfalar[0]}-{sayfalar[-1]}"
    return {
        "etiket": f"{ad} {sinif}, s. {aralik}",
        "metin": "\n\n".join(p[2] for p in parcalar),
        "chunk_idler": [p[0] for p in parcalar],
        "skor": 1 - float(parcalar[0][3]),
    }
