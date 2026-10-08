"""soruhavuzu/etiketle.py — mevcut onaylı soruları en yakın kazanıma bağlar (bir kerelik geri doldurma).
Gömme bilgehan bge-m3 (tekrar._gomucu); eşik kapsam ölçümüyle aynı (0,55)."""

import numpy as np

ESIK = 0.55


def etiketle(conn, gomucu, kuru: bool = False, esik: float = ESIK) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, sinif, ders, metin FROM kazanim WHERE durum = 'aktif'")
        kazanimlar = cur.fetchall()
        cur.execute("SELECT id, sinif, ders, soru, secenekler, dogru_index FROM soru "
                    "WHERE durum = 'onayli' AND kazanim_id IS NULL")
        sorular = cur.fetchall()
    gruplar: dict = {}
    for kid, sinif, ders, metin in kazanimlar:
        gruplar.setdefault((sinif, ders), []).append((kid, metin))
    kvek = {}
    for anahtar, liste in gruplar.items():
        v = gomucu.encode([m for _, m in liste], normalize_embeddings=True)
        kvek[anahtar] = ([k for k, _ in liste], np.stack([np.asarray(x) for x in v]))
    dagilim, yazilacak = {}, []
    for i in range(0, len(sorular), 64):
        parca = sorular[i:i + 64]
        metinler = []
        for _, _, _, soru, sec, di in parca:
            secenekler = sec if isinstance(sec, list) else []
            dogru = secenekler[di] if 0 <= di < len(secenekler) else ""
            metinler.append(f"{soru} {dogru}")
        vler = gomucu.encode(metinler, normalize_embeddings=True)
        for (sid, sinif, ders, *_), v in zip(parca, vler):
            et, top = dagilim.get((sinif, ders), (0, 0))
            hedef = kvek.get((sinif, ders))
            if hedef is None:
                dagilim[(sinif, ders)] = (et, top + 1)
                continue
            skorlar = hedef[1] @ np.asarray(v)
            j = int(np.argmax(skorlar))
            if float(skorlar[j]) >= esik:
                yazilacak.append((hedef[0][j], float(skorlar[j]), sid))
                et += 1
            dagilim[(sinif, ders)] = (et, top + 1)
    if not kuru and yazilacak:
        with conn.cursor() as cur:
            cur.executemany("UPDATE soru SET kazanim_id=%s, kazanim_skor=%s, kazanim_kaynak='etiket' "
                            "WHERE id=%s AND kazanim_id IS NULL", yazilacak)
        conn.commit()
    toplam = sum(t for _, t in dagilim.values())
    return {"etiketlenen": len(yazilacak), "etiketsiz": toplam - len(yazilacak), "dagilim": dagilim}
