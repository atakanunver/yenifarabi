"""soruhavuzu/kaynak.py — bir kazanım için ders kitabından en ilgili parçaları bulur (farabi DB, pgvector).
Gömme bilgehan bge-m3; RAG ile aynı `embedding <=> vektör` kalıbı (server/rag.py::_ilk_k_getir)."""

import json
from pathlib import Path

from soruhavuzu import dersler

ESIK = 0.45
# Kaynağı yalnızca "okuma metni" parçalarına kısıtlanan kitaplar: {"<kitap_id>": [chunk_id, ...]}.
# İngilizce 9'un alıştırma/yönerge sayfaları soru üretmeye uygun değil (2026-10-14: %9-16 onay).
# Dosya yoksa ya da kitap listede değilse kısıtlama yok. Etiketler yerel modelle üretildi (DECISIONS.md).
OKUMA_DOSYASI = Path("/mnt/farabi-data/farabi/soru_havuzu/okuma_parcalari.json")


def _okuma_izinli() -> dict[int, list[int]]:
    try:
        return {int(k): [int(i) for i in v] for k, v in json.loads(OKUMA_DOSYASI.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def kitap_idleri(farabi_conn, sinif: int, ders: str) -> list[int]:
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT id, ders FROM kitap WHERE sinif = %s", (sinif,))
        return [kid for kid, ad in cur.fetchall() if dersler.ders_anahtari(ad) == ders]


def bul(
    farabi_conn,
    gomucu,
    sinif: int,
    ders: str,
    kazanim_metin: str,
    k: int = 3,
    haric_chunklar: set[int] | None = None,
    offset: int = 0,
) -> dict | None:
    idler = kitap_idleri(farabi_conn, sinif, ders)
    if not idler:
        return None
    v = list(map(float, gomucu.encode([kazanim_metin], normalize_embeddings=True)[0]))
    vektor = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    izinli = _okuma_izinli()
    kisitli = [kid for kid in idler if kid in izinli]
    haric = list(haric_chunklar or [])
    haric_filtre = " AND NOT (id = ANY(%s))" if haric else ""
    sorgu = (
        "SELECT id, sayfa_no, metin, embedding <=> %s::vector AS mesafe FROM chunk_egitim "
        f"WHERE ((kitap_id = ANY(%s) AND NOT (kitap_id = ANY(%s))) OR id = ANY(%s)){haric_filtre} "
        "ORDER BY mesafe LIMIT %s OFFSET %s"
    )
    param = (
        [vektor, idler, kisitli, [i for kid in kisitli for i in izinli[kid]], haric, k, offset]
        if haric
        else [vektor, idler, kisitli, [i for kid in kisitli for i in izinli[kid]], k, offset]
    )
    with farabi_conn.cursor() as cur:
        cur.execute(sorgu, param)
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
