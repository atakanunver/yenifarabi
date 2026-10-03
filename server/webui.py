"""server/webui.py — Open WebUI Farabi modlarının kaynak arama ucu (2026-10-03).

Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.2.
Open WebUI'deki `farabi_kaynak` filtresi her kullanıcı mesajında burayı çağırır;
dönen parçalar sistem mesajına eklenir. LLM'e GİTMEZ (RagMotoru.ara).

- Erişim: 0.0.0.0 (yerel ağ, kullanıcı kararı) + `X-Farabi-WebUI-Key`
  (api_keys.json::webui_key). Tahta anahtarı burada geçmez.
- Loglama: yalnızca `metrik` (sonuc=webui_*, tahta_id NULL); `soru_log`
  tahta sorularına ayrılmış, öğretmen soruları oraya YAZILMAZ.
- Hata: her durumda 200 + durum="hata" — filtre aramasız devam eder,
  Open WebUI asla düşmez.
"""

from __future__ import annotations

import hmac
import logging
import re
import time

import auth
import db
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("webui")

router = APIRouter()

MOTOR = None  # main.py lifespan'da RagMotoru atanır; None = RAG kapalı
SORU_AZAMI = 2000

# kapsam → kitap.ders değerleri (canlı DB'deki yazımla birebir, 2026-10-03)
KAPSAM_DERSLER: dict[str, list[str]] = {
    "kimya": ["Kimya"],
    "fizik": ["Fizik"],
    "biyoloji": ["Biyoloji"],
    "matematik": ["Matematik", "Temel Matematik"],
    "edebiyat": ["Türk Dili ve Edebiyatı"],
    "ingilizce": ["İngilizce"],
    "felsefe": ["Felsefe"],
    "din": ["Din Kültürü ve Ahlak Bilgisi"],
    "tarih": ["Tarih", "İnkılap Tarihi ve Atatürkçülük"],
    "cografya": ["Coğrafya"],
}
KAPSAM_DERSLER["genel"] = sorted({d for liste in KAPSAM_DERSLER.values() for d in liste})
KAPSAMLAR = set(KAPSAM_DERSLER) | {"idari"}

# "10. sınıf", "10.sınıf", "10 sınıf", "10-a" — soru .lower() edilerek aranır
# ("SINIF".lower() == "sinif"). Önünde/arkasında rakam olan sayılar (2010,
# 110) eşleşmez.
_SINIF_RE = re.compile(
    r"(?<!\d)(9|10|11|12)(?:\s*\.\s*|\s+)(?:sınıf|sinif)"
    r"|(?<!\d)(9|10|11|12)-[a-zçğıöşü](?![a-zçğıöşü])"
)


def sinif_cikar(soru: str) -> int | None:
    m = _SINIF_RE.search(soru.lower())
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def webui_anahtari_dogrula(
    x_farabi_webui_key: str | None = Header(default=None, alias=auth.WEBUI_HEADER_ADI),
) -> None:
    beklenen = auth.webui_anahtari()
    if not beklenen or not x_farabi_webui_key or not hmac.compare_digest(beklenen, x_farabi_webui_key):
        log.warning("webui authentication failure")
        raise HTTPException(status_code=401, detail="Geçersiz ya da eksik WebUI anahtarı")


class AraIstek(BaseModel):
    kapsam: str
    soru: str = Field(..., min_length=1)
    sinif: int | None = None


def _kitaplar(conn, dersler: list[str], sinif: int | None) -> dict[int, str]:
    """kitap_id → etiket öneki ("Kimya 10", "Matematik 9 (2. cilt)")."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sinif, ders, dosya_yolu FROM kitap WHERE ders = ANY(%s) ORDER BY id",
            (dersler,),
        )
        satirlar = cur.fetchall()
    if sinif is not None and any(r[1] == sinif for r in satirlar):
        satirlar = [r for r in satirlar if r[1] == sinif]
    # Aynı (sınıf, ders) birden fazla ciltse id sırasıyla "N. cilt" eklenir.
    gruplar: dict[tuple, list[int]] = {}
    for kid, snf, ders, _yol in satirlar:
        gruplar.setdefault((snf, ders), []).append(kid)
    etiketler = {}
    for (snf, ders), idler in gruplar.items():
        for sira, kid in enumerate(sorted(idler), start=1):
            ek = f" ({sira}. cilt)" if len(idler) > 1 else ""
            etiketler[kid] = f"{ders} {snf}{ek}"
    return etiketler


def _idari_belgeler(conn) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ad FROM idari_belge ORDER BY id")
        return {int(r[0]): r[1] for r in cur.fetchall()}


def _metrik_yaz(conn, sonuc: dict, toplam_ms: int) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metrik
                    (tahta_id, retrieval_ms, rerank_ms, llm_toplam_ms,
                     toplam_ms, sonuc, en_yuksek_skor)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (None, sonuc.get("retrieval_ms"), sonuc.get("rerank_ms"), None,
                 toplam_ms, f"webui_{sonuc['durum']}", sonuc.get("en_iyi_skor")),
            )
        conn.commit()
    except Exception:  # noqa: BLE001 — metrik yazılamaması cevabı etkilememeli
        conn.rollback()


@router.post("/api/webui/ara", dependencies=[Depends(webui_anahtari_dogrula)])
def ara(istek: AraIstek):
    if istek.kapsam not in KAPSAMLAR:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen kapsam: {istek.kapsam}")
    t0 = time.perf_counter()
    if MOTOR is None:
        return {"durum": "hata", "parcalar": [], "sure_ms": 0}

    soru = istek.soru[:SORU_AZAMI]
    etiketler: dict[int, str] = {}
    toplam_ms = 0
    try:  # bağlantı alınamazsa (havuz tükenmesi) da 200 + hata dön
        with db.baglanti() as conn:
            try:
                if istek.kapsam == "idari":
                    etiketler = _idari_belgeler(conn)
                    kaynak = "idari"
                else:
                    sinif = istek.sinif if istek.sinif is not None else sinif_cikar(soru)
                    etiketler = _kitaplar(conn, KAPSAM_DERSLER[istek.kapsam], sinif)
                    kaynak = "egitim"
                sonuc = MOTOR.ara(conn, kaynak, list(etiketler), soru)
            except Exception as e:  # noqa: BLE001 — arama hatası 200 + durum="hata"
                conn.rollback()
                log.warning("webui arama hatası: %s: %s", type(e).__name__, e)
                sonuc = {"durum": "hata", "parcalar": []}
            if sonuc["durum"] == "hata":
                # RagMotoru.ara kendi DB hatalarını yakalar ama rollback yapmaz;
                # bağlantı iptal edilmiş işlemde kalırsa metrik INSERT'i sessizce
                # düşerdi.
                conn.rollback()
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            _metrik_yaz(conn, sonuc, toplam_ms)
    except Exception as e:  # noqa: BLE001 — Open WebUI'ye her durumda 200 + durum="hata"
        log.warning("webui bağlantı/işlem hatası: %s: %s", type(e).__name__, e)
        return {"durum": "hata", "parcalar": [], "sure_ms": int((time.perf_counter() - t0) * 1000)}

    parcalar = [
        {"kaynak": f"{etiketler.get(p['kaynak_id'], '?')}, s. {p['sayfa']}",
         "sayfa": p["sayfa"], "metin": p["metin"], "skor": p["skor"]}
        for p in sonuc.get("parcalar", [])
    ]
    return {"durum": sonuc["durum"], "parcalar": parcalar, "sure_ms": toplam_ms}
