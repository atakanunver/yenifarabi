"""soruhavuzu/tekrar.py — aynı ders+sınıfta neredeyse aynı soruları eler (bilgehan bge-m3)."""

import fcntl
import sys
from pathlib import Path

import numpy as np

ESIK = 0.92


ONBELLEK_YOLU = Path("/mnt/farabi-data/farabi/soru_havuzu/eleyici_vektorler.npz")
KILIT_YOLU = Path("/mnt/farabi-data/farabi/soru_havuzu/eleyici_vektorler.lock")


class Eleyici:
    def __init__(self, gomucu):
        self.gomucu = gomucu
        self.vektorler: dict[tuple[str, int], list[np.ndarray]] = {}

    def _ekle(self, ders: str, sinif: int, v: np.ndarray) -> None:
        self.vektorler.setdefault((ders, sinif), []).append(v)

    def yukle(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ders, sinif, soru FROM soru WHERE durum IN ('uretildi','onayli') ORDER BY id"
            )
            satirlar = cur.fetchall()

        mevcut_idler = {s[0] for s in satirlar}
        onbellek_dict: dict[int, tuple[str, int, np.ndarray]] = {}

        KILIT_YOLU.parent.mkdir(parents=True, exist_ok=True)
        with open(KILIT_YOLU, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if ONBELLEK_YOLU.exists():
                    try:
                        npz = np.load(ONBELLEK_YOLU, allow_pickle=True)
                        c_ids = npz["ids"]
                        c_ders = npz["ders"]
                        c_sinif = npz["sinif"]
                        c_veks = npz["vektorler"]
                        for sid, d, sn, v in zip(c_ids, c_ders, c_sinif, c_veks):
                            sid = int(sid)
                            if sid in mevcut_idler:
                                onbellek_dict[sid] = (str(d), int(sn), v)
                                self._ekle(str(d), int(sn), v)
                    except Exception as e:
                        print(f"[tekrar] önbellek okunamadı ({e}), sıfırdan yüklenecek", flush=True)
                        self.vektorler.clear()
                        onbellek_dict.clear()

                yeni_satirlar = [s for s in satirlar if s[0] not in onbellek_dict]
                if yeni_satirlar:
                    print(f"[tekrar] {len(onbellek_dict)} soru önbellekten yüklendi, {len(yeni_satirlar)} yeni soru gömülüyor...", flush=True)
                    for i in range(0, len(yeni_satirlar), 64):
                        parca = yeni_satirlar[i : i + 64]
                        vler = self.gomucu.encode([s[3] for s in parca], normalize_embeddings=True)
                        for (sid, ders, sinif, _), v in zip(parca, vler):
                            arr = np.asarray(v, dtype=np.float32)
                            self._ekle(ders, sinif, arr)
                            onbellek_dict[sid] = (ders, sinif, arr)

                    # Güncellenmiş önbelleği diske yaz
                    try:
                        ONBELLEK_YOLU.parent.mkdir(parents=True, exist_ok=True)
                        siralı_idler = sorted(onbellek_dict.keys())
                        np.savez_compressed(
                            ONBELLEK_YOLU,
                            ids=np.array(siralı_idler, dtype=np.int64),
                            ders=np.array([onbellek_dict[k][0] for k in siralı_idler]),
                            sinif=np.array([onbellek_dict[k][1] for k in siralı_idler], dtype=np.int32),
                            vektorler=np.stack([onbellek_dict[k][2] for k in siralı_idler]),
                        )
                    except Exception as e:
                        print(f"[tekrar] önbellek yazılamadı: {e}", flush=True)
                else:
                    print(f"[tekrar] {len(onbellek_dict)} sorunun tamamı önbellekten yüklendi (0 yeni)", flush=True)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def kopya_mi(self, ders: str, sinif: int, soru: str) -> bool:
        v = np.asarray(self.gomucu.encode([soru], normalize_embeddings=True)[0])
        onceki = self.vektorler.get((ders, sinif), [])
        if onceki and float(np.max(np.stack(onceki) @ v)) >= ESIK:
            return True
        self._ekle(ders, sinif, v)
        return False


# Aynı ders+sınıfta aynı soru metni VE aynı şık kümesi = birebir kopya (içe aktarma betikleri Eleyici'yi
# atlıyor). Yalnızca metin aynı, şıklar farklıysa kopya sayılmaz (ortak yönergeli ayrı sorular).
_KOPYA_SQL = """
WITH anahtarli AS (
  SELECT id, durum,
         row_number() OVER (
           PARTITION BY ders, sinif,
                        lower(regexp_replace(soru, '\\s+', ' ', 'g')),
                        (SELECT string_agg(lower(btrim(v)), '|' ORDER BY lower(btrim(v)))
                           FROM jsonb_array_elements_text(secenekler) v)
           ORDER BY (durum = 'onayli') DESC, id) AS sira
  FROM soru
  WHERE durum IN ('onayli', 'uretildi') AND NOT (sinif = ANY(%s))
)
SELECT id FROM anahtarli WHERE sira > 1
"""


def kopyalari_isaretle(conn, kuru: bool = False) -> int:
    """Birebir kopyalardan ilkini (onaylı öncelikli, sonra en düşük id) bırakıp gerisini 'kopya' yapar."""
    from soruhavuzu import vt

    with conn.cursor() as cur:
        cur.execute(_KOPYA_SQL, (list(vt.DONDURULMUS_SINIFLAR),))
        idler = [r[0] for r in cur.fetchall()]
        if idler and not kuru:
            cur.execute(
                "UPDATE soru SET durum='kopya', denetim_notu=COALESCE(denetim_notu||' | ','')||'birebir kopya' "
                "WHERE id = ANY(%s)", (idler,))
            conn.commit()
    return len(idler)


def _gomucu():
    """farabi-api'nin kullandığı bilgehan gömme istemcisi (server/uzak_model.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
    import uzak_model

    embed, _reranker = uzak_model.olustur(*uzak_model.ayar_oku(), zaman_asimi=30.0)
    return embed
