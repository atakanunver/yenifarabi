"""soruhavuzu/okul_bildirim.py — smual.app öğrenci "soru bildir" kayıtlarını havuza işler.

Okul havuza yazmaz; soruhavuzu okulun /api/soru-bildirim ucunu (127.0.0.1:9090, X-Soru-Anahtar) okur,
`soru_geri_bildirim` tablosuna yazar ve eşiği aşan (farklı öğrenci sayısı) sorular için durum='askida' yapar.
Anahtar okul/config/gizli.json "soru_havuzu_anahtar" (gitignore'lu); yoksa adım sessizce atlanır."""

import json
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:9090/api/soru-bildirim"
GIZLI = Path("/home/ata/farabi/okul/config/gizli.json")
TUR = {"sekil": "soru_hatali", "cevap": "cevap_yanlis", "anlasilmiyor": "soru_hatali"}


def anahtar() -> str:
    try:
        return json.loads(GIZLI.read_text(encoding="utf-8")).get("soru_havuzu_anahtar", "")
    except (OSError, ValueError):
        return ""


def cek(url: str = URL, anahtar_: str | None = None, zaman_asimi: int = 15) -> dict | None:
    a = anahtar() if anahtar_ is None else anahtar_
    if not a:
        return None
    istek = urllib.request.Request(url, headers={"X-Soru-Anahtar": a})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:  # noqa: S310 — yerel servis
        return json.loads(r.read().decode("utf-8"))


def isle(conn, veri: dict) -> dict:
    """Her soru için geri bildirim satırlarını yeniler (idempotent) ve eşiği aşanı askıya alır."""
    esik = int(veri.get("esik", 2))
    yazilan = askiya = 0
    with conn.cursor() as cur:
        for s in veri.get("sorular", []):
            cur.execute("SELECT durum FROM soru WHERE id = %s", (s["soru_id"],))
            satir = cur.fetchone()
            if satir is None:
                continue
            cur.execute("DELETE FROM soru_geri_bildirim WHERE soru_id = %s AND not_metni LIKE 'okul:%%'", (s["soru_id"],))
            for tur, n in s["turler"].items():
                cur.execute(
                    "INSERT INTO soru_geri_bildirim (soru_id, tur, not_metni) VALUES (%s, %s, %s)",
                    (s["soru_id"], TUR.get(tur, "diger"), f"okul:{tur}:{n} öğrenci"),
                )
                yazilan += 1
            if s["kisi"] >= esik and satir[0] in ("onayli", "uretildi"):
                cur.execute(
                    "UPDATE soru SET durum='askida', denetim_notu=%s, denetim_at=now() WHERE id = %s",
                    (f"ogrenci_bildirimi: {s['kisi']} öğrenci", s["soru_id"]),
                )
                askiya += 1
    conn.commit()
    return {"yazilan": yazilan, "askiya": askiya}


def calistir(conn, cekici=cek) -> dict | None:
    """Okul kapalı/anahtarsızsa None döner; gece turu bundan etkilenmez."""
    try:
        veri = cekici()
    except Exception as e:  # noqa: BLE001 — okul geçici kapalıysa üretim turu aksamasın
        print(f"[geri-bildirim] okul okunamadı: {type(e).__name__}: {e}", flush=True)
        return None
    if veri is None:
        return None
    return isle(conn, veri)
