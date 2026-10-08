"""Kazanım kapsamı ölçümü: yıllık plandaki her (düzey, ders, hafta) kazanımı için
soru havuzunda (durum='onayli') yeterince benzer soru var mı?

Kullanım (kökten): HF_HUB_OFFLINE=1 server/venv/bin/python -m benchmark.kazanim_kapsam
Çıktı: /mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json + özet tablo.
Benzerlik: bge-m3 kosinüs (kazanimtest/secici.py ile aynı model), eşik ESIK.
Yalnızca okur; DB'ye yazmaz.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from kazanimtest import secici
from soruhavuzu.dersler import ders_anahtari

KAZANIM = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data" / "kazanimlar.json"
CIKTI = Path("/mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json")
BRANSLAR = ["matematik", "edebiyat", "fizik", "kimya", "biyoloji", "tarih", "cografya", "din"]
ESIK = 0.55          # server RAG'ın Open WebUI kosinüs eşiğiyle aynı
YETERLI = 10         # bir test = 10 soru


def main() -> None:
    kz = json.loads(KAZANIM.read_text(encoding="utf-8"))["kazanimlar"]
    # (düzey, anahtar) -> {hafta: metin}; aynı anahtara inen birden çok ders adı birleşir
    plan: dict[tuple[int, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    adlar: dict[tuple[int, str], set[str]] = defaultdict(set)
    for duzey, dersler in kz.items():
        for ad, haftalar in dersler.items():
            a = ders_anahtari(ad)
            if a not in BRANSLAR:
                continue
            adlar[(int(duzey), a)].add(ad)
            for h, metin in haftalar.items():
                if isinstance(metin, str) and metin.strip():
                    plan[(int(duzey), a)][h].append(metin.strip())

    model = secici.gomme_modeli()
    conn = secici.baglan("soru_havuzu")
    sonuc, satirlar = {}, []
    for duzey in (9, 10, 11, 12):
        for a in BRANSLAR:
            haftalar = plan.get((duzey, a), {})
            cur = conn.cursor()
            cur.execute("SELECT soru FROM soru WHERE sinif=%s AND ders=%s AND durum='onayli'", (duzey, a))
            sorular = [r[0] for r in cur.fetchall()]
            hafta_ozet = {}
            if haftalar and sorular:
                sv = model.encode(sorular, batch_size=64, normalize_embeddings=True)
                hs = sorted(haftalar, key=int)
                kv = model.encode(["\n".join(haftalar[h]) for h in hs], normalize_embeddings=True)
                benz = np.asarray(kv) @ np.asarray(sv).T
                for h, satir in zip(hs, benz):
                    ust = np.sort(satir)[::-1]
                    hafta_ozet[h] = {"esik_ustu": int((satir >= ESIK).sum()),
                                     "ilk10_ort": round(float(ust[:YETERLI].mean()), 3)}
            yeterli = sum(1 for v in hafta_ozet.values() if v["esik_ustu"] >= YETERLI)
            zayif = sum(1 for v in hafta_ozet.values() if 0 < v["esik_ustu"] < YETERLI)
            bos = len(haftalar) - yeterli - zayif
            sonuc[f"{duzey}-{a}"] = {"plan_adlari": sorted(adlar.get((duzey, a), [])),
                                     "onayli_soru": len(sorular), "plan_haftasi": len(haftalar),
                                     "yeterli": yeterli, "zayif": zayif, "bos": bos,
                                     "haftalar": hafta_ozet}
            satirlar.append((duzey, a, len(sorular), len(haftalar), yeterli, zayif, bos))
            print(f"{duzey:>2} {a:<10} onaylı {len(sorular):>4} | plan haftası {len(haftalar):>2} | "
                  f"yeterli {yeterli:>2} zayıf {zayif:>2} boş {bos:>2}", flush=True)
    conn.close()
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    CIKTI.write_text(json.dumps({"uretim": datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(timespec="seconds"),
                                 "esik": ESIK, "yeterli_soru": YETERLI, "sonuc": sonuc},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print("yazıldı:", CIKTI)


if __name__ == "__main__":
    main()
