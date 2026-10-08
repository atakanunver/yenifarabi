"""kazanim_kapsam.py eşik ayarı için örnek: seçili haftaların kazanımı + en yakın 3 onaylı soru."""
import json
import sys
from pathlib import Path

import numpy as np

from kazanimtest import secici
from soruhavuzu.dersler import ders_anahtari

kz = json.loads(Path("tahtayoklama/data/kazanimlar.json").read_text(encoding="utf-8"))["kazanimlar"]
model = secici.gomme_modeli()
conn = secici.baglan("soru_havuzu")
for hedef in sys.argv[1:]:                      # ör. 9:kimya:5
    duzey, a, h = hedef.split(":")
    metin = "\n".join(m for ad, hs in kz[duzey].items() if ders_anahtari(ad) == a for k, m in hs.items() if k == h and m)
    cur = conn.cursor()
    cur.execute("SELECT soru FROM soru WHERE sinif=%s AND ders=%s AND durum='onayli'", (int(duzey), a))
    sorular = [r[0] for r in cur.fetchall()]
    b = model.encode([metin], normalize_embeddings=True) @ model.encode(sorular, batch_size=64, normalize_embeddings=True).T
    print(f"\n=== {hedef} | KAZANIM: {metin[:230]}")
    for i in np.argsort(b[0])[::-1][:3]:
        print(f"  {b[0][i]:.3f}  {sorular[i][:150]}")
