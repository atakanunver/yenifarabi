"""agy kazanım-soru kartı için girdi paketi: bir (düzey, ders) için her plan haftasının
kazanımı + kapsam ölçümü + o kazanıma en yakın 10 onaylı soru + kitap metni dosyası.

Kullanım (kökten): HF_HUB_OFFLINE=1 server/venv/bin/python -m benchmark.kazanim_agy_paket 9 biyoloji
Çıktı: /mnt/farabi-data/farabi/kazanim_testleri/agy/<duzey>-<ders>/girdi.json
Yalnızca okur (DB'ye yazmaz). İçerik halka açık ders kitabı/soru metni; öğrenci verisi yok.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from kazanimtest import secici
from soruhavuzu.dersler import ders_anahtari

KOK = Path(__file__).resolve().parent.parent
KAZANIM = KOK / "tahtayoklama" / "data" / "kazanimlar.json"
KAPSAM = Path("/mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json")
METIN = Path("/mnt/farabi-data/farabi/icerik/metin")
CIKTI = Path("/mnt/farabi-data/farabi/kazanim_testleri/agy")
# (düzey, ders anahtarı) -> kitap metin dosyası (icerik/metin/)
KITAP = {
    (9, "biyoloji"): "biyoloji-9.json", (10, "biyoloji"): "biyoloji-10.json", (11, "biyoloji"): "biyoloji-11.json", (12, "biyoloji"): "biyoloji-12.json",
    (9, "cografya"): "cografya-9.json", (10, "cografya"): "cografya-10.json", (11, "cografya"): "cografya-11.json", (12, "cografya"): "cografya-12.json",
    (9, "din"): "din-kulturu-ve-ahlak-bilgisi-9.json", (10, "din"): "din-kulturu-ve-ahlak-bilgisi-10.json",
    (11, "din"): "din-kulturu-ve-ahlak-bilgisi-11.json",
    (9, "fizik"): "fizik_9.json", (10, "fizik"): "fizik-10.json", (11, "fizik"): "fizik-11.json",
    (9, "kimya"): "kimya_9.json", (10, "kimya"): "kimya-10.json", (11, "kimya"): "kimya-11.json",
    (9, "matematik"): "matematik_9.json", (10, "matematik"): "matematik-10.json", (12, "matematik"): "matematik-12.json",
    (9, "tarih"): "tarih-9.json", (10, "tarih"): "tarih-10.json", (11, "tarih"): "tarih-11.json",
    (12, "tarih"): "12. Sınıf T.C. İnkılap Tarihi Ve Atatürkçülük Ders Kitabı-MEB.json",
    (9, "edebiyat"): "turk_dili_ve_edebiyati_9.json", (10, "edebiyat"): "turk-dili-ve-edebiyati-10_2.json",
    (11, "edebiyat"): "turk-dili-ve-edebiyati-11.json", (12, "edebiyat"): "turk-dili-ve-edebiyati-12.json",
}


def main(duzey: int, ders: str) -> Path:
    kz = json.loads(KAZANIM.read_text(encoding="utf-8"))["kazanimlar"][str(duzey)]
    haftalar: dict[str, list[tuple[str, str]]] = defaultdict(list)   # hafta -> [(plan ders adı, metin)]
    for ad, hs in kz.items():
        if ders_anahtari(ad) == ders:
            for h, m in hs.items():
                if isinstance(m, str) and m.strip():
                    haftalar[h].append((ad, m.strip()))
    if not haftalar:
        raise SystemExit(f"{duzey}-{ders}: yıllık planda kazanım yok")
    kapsam = json.loads(KAPSAM.read_text(encoding="utf-8"))["sonuc"].get(f"{duzey}-{ders}", {}).get("haftalar", {})

    conn = secici.baglan("soru_havuzu")
    cur = conn.cursor()
    cur.execute("SELECT id, soru, secenekler, dogru_index, kaynak FROM soru "
                "WHERE sinif=%s AND ders=%s AND durum='onayli'", (duzey, ders))
    sorular = cur.fetchall()
    conn.close()
    model = secici.gomme_modeli()
    sv = model.encode([s[1] for s in sorular], batch_size=64, normalize_embeddings=True) if sorular else None

    paket_haftalar = []
    for h in sorted(haftalar, key=int):
        metin = "\n".join(m for _, m in haftalar[h])
        yakin = []
        if sv is not None:
            b = (model.encode([metin], normalize_embeddings=True) @ np.asarray(sv).T)[0]
            for i in np.argsort(b)[::-1][:10]:
                sid, soru, sec, dogru, kaynak = sorular[i]
                sec = sec if isinstance(sec, list) else json.loads(sec)
                yakin.append({"id": sid, "benzerlik": round(float(b[i]), 3), "soru": soru,
                              "secenekler": sec, "dogru": "ABCD"[dogru], "kaynak": kaynak})
        paket_haftalar.append({"hafta": int(h), "plan_dersleri": sorted({a for a, _ in haftalar[h]}),
                               "kazanim": metin, "kapsam": kapsam.get(h), "en_yakin_10": yakin})

    kitap = KITAP.get((duzey, ders))
    yol = CIKTI / f"{duzey}-{ders}"
    yol.mkdir(parents=True, exist_ok=True)
    girdi = yol / "girdi.json"
    girdi.write_text(json.dumps({
        "uretim": datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(timespec="seconds"),
        "duzey": duzey, "ders": ders,
        "kitap_metni": str(METIN / kitap) if kitap else None,
        "onayli_soru_sayisi": len(sorular), "haftalar": paket_haftalar,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("yazıldı:", girdi, "| hafta:", len(paket_haftalar), "| kitap:", kitap)
    return girdi


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
