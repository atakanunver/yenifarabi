"""Günün Bilmecesi havuzuna JSON'dan toplu bilmece ekler (havuzda aynı soru varsa atlanır).

    venv/bin/python scripts/bilmece_yukle.py [config/bilmeceler.json]

JSON: [{"soru", "secenekler": [2-4 metin], "dogru": 0'dan başlayan sıra, "aciklama"}]. Sıra korunur: hiç sorulmamışlar
en küçük id'den başlayarak sorulduğu için dosyadaki sıra gün sırasıdır.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bilmece
import db

VARSAYILAN = Path(__file__).resolve().parent.parent / "config" / "bilmeceler.json"


def yukle(yol: Path) -> tuple[int, int]:
    liste = json.loads(yol.read_text(encoding="utf-8"))
    for b in liste:  # önce hepsi doğrulanır: yarıda kalıp havuzu yarım bırakmasın
        try:
            bilmece.dogrula(b["soru"], b["secenekler"], int(b["dogru"]), b.get("aciklama", ""))
        except bilmece.BilmeceHatasi as e:
            raise SystemExit(f"Geçersiz bilmece: {b['soru'][:60]!r}: {e.mesaj}") from None
    db.sema_kur()
    conn = db.baglanti()
    eklenen = atlanan = 0
    try:
        for b in liste:
            try:
                bilmece.ekle(conn, b["soru"], b["secenekler"], int(b["dogru"]), b.get("aciklama", ""))
                eklenen += 1
            except bilmece.BilmeceHatasi:  # yalnızca 409: aynı soru zaten var
                atlanan += 1
    finally:
        conn.close()
    return eklenen, atlanan


if __name__ == "__main__":
    e, a = yukle(Path(sys.argv[1]) if len(sys.argv) > 1 else VARSAYILAN)
    print(f"{e} bilmece eklendi, {a} zaten vardı.")
