"""soruhavuzu/siniflandir.py — kazanıma bağlanamamış onaylı soruları LLM ile sınıflandırır.
Aynı sınıf+ders kazanımlarından gömmeyle en yakın 5 aday seçilir, Ollama "hangisini ölçüyor
(ya da hiçbiri)" diye karar verir. Kaldığı yer = veritabanı (kazanim_siniflandirma_at)."""

import json

import httpx
import numpy as np

from soruhavuzu import zaman
from soruhavuzu.uretici import MODEL

PARTI = 8
ADAY = 5
AZAMI_DENEME = 3

SISTEM = (
    "Sen MEB lise öğretmenisin. Sana test soruları ve her soru için aday kazanımlar verilecek. "
    "Soru hangi kazanımı ÖLÇÜYOR? Yalnızca açıkça ölçüyorsa seç; emin değilsen 0 yaz. "
    'Yalnızca JSON döndür: {"kararlar": [{"no": 1, "secim": 3}, ...]}.'
)


def _istem(parti: list[dict]) -> list[dict]:
    bloklar = []
    for i, p in enumerate(parti, 1):
        adaylar = "\n".join(f"  {j}. {a['metin']}" for j, a in enumerate(p["adaylar"], 1))
        bloklar.append(
            f"SORU {i}: {p['soru']}\nDoğru cevap: {p['dogru']}\nAday kazanımlar:\n{adaylar}"
        )
    kullanici = (
        "\n\n".join(bloklar)
        + "\n\nHer soru için hangi aday kazanımı ölçtüğünü seç (1-5), hiçbiri değilse 0. "
        'Biçim: {"kararlar": [{"no": 1, "secim": 3}]}'
    )
    return [{"role": "system", "content": SISTEM}, {"role": "user", "content": kullanici}]


def ollama_cagir(
    mesajlar: list[dict], ollama_url: str = "http://127.0.0.1:11434", zaman_asimi: float = 180
) -> str:
    govde = {
        "model": MODEL,
        "messages": mesajlar,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 1024},
    }
    with httpx.Client(timeout=zaman_asimi, trust_env=False) as c:
        r = c.post(f"{ollama_url}/api/chat", json=govde)
        if r.status_code == 500:  # Ollama arada sebepsiz 500 dönüyor; tekrarda geçiyor
            r = c.post(f"{ollama_url}/api/chat", json=govde)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")


def _ayristir(ham: str, adet: int) -> dict[int, int] | None:
    """{soru sırası (0 tabanlı): seçim 0-5}; bozuk ya da eksikse None."""
    try:
        veri = json.loads(ham)
        kararlar = veri["kararlar"]
        sonuc = {}
        for k in kararlar:
            no, secim = int(k["no"]), int(k["secim"])
            if not (1 <= no <= adet and 0 <= secim <= ADAY) or (no - 1) in sonuc:
                return None
            sonuc[no - 1] = secim
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return None
    return sonuc if len(sonuc) == adet else None


def calistir(
    conn, gomucu, kuru: bool = False, limit: int | None = None,
    ders_saati_kontrol: bool = True, cagir=None,
) -> dict:
    cagir = cagir or ollama_cagir
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (sinif, ders, metin) id, sinif, ders, metin FROM kazanim "
            "ORDER BY sinif, ders, metin, hafta, id"
        )
        kaz = cur.fetchall()
        cur.execute(
            "SELECT id, sinif, ders, soru, secenekler, dogru_index FROM soru "
            "WHERE durum='onayli' AND kazanim_id IS NULL AND kazanim_siniflandirma_at IS NULL "
            "ORDER BY id"
        )
        sorular = cur.fetchall()
    gruplar: dict = {}
    for kid, sinif, ders, metin in kaz:
        gruplar.setdefault((sinif, ders), []).append((kid, metin))
    sorular = [s for s in sorular if (s[1], s[2]) in gruplar]
    if limit is not None:
        sorular = sorular[:limit]
    onbellek: dict = {}  # (sinif, ders) -> kazanım gömmeleri (bir kez)

    def kazanim_vek(anahtar):
        if anahtar not in onbellek:
            v = gomucu.encode([m for _, m in gruplar[anahtar]], normalize_embeddings=True)
            onbellek[anahtar] = np.stack([np.asarray(x) for x in v])
        return onbellek[anahtar]

    toplam = len(sorular)
    islenen = baglanan = hicbiri = bozuk_parti = 0
    ornek = 0
    for bas in range(0, toplam, PARTI):
        if ders_saati_kontrol and not zaman.uretim_serbest():
            print("[siniflandir] ders saati — durduruldu", flush=True)
            break
        parca = sorular[bas : bas + PARTI]
        metinler, dogrular = [], []
        for _, _, _, soru, sec, di in parca:
            dogru = sec[di] if isinstance(sec, list) and 0 <= di < len(sec) else ""
            dogrular.append(dogru)
            metinler.append(f"{soru} {dogru}")
        vler = gomucu.encode(metinler, normalize_embeddings=True)
        parti = []
        for (sid, sinif, ders, soru, _, _), dogru, v in zip(parca, dogrular, vler):
            liste = gruplar[(sinif, ders)]
            skorlar = kazanim_vek((sinif, ders)) @ np.asarray(v)
            sira = np.argsort(-skorlar, kind="stable")[:ADAY]
            parti.append({
                "id": sid, "soru": soru, "dogru": dogru,
                "adaylar": [
                    {"id": liste[j][0], "metin": liste[j][1], "skor": float(skorlar[j])} for j in sira
                ],
            })
        kararlar = None
        for _ in range(AZAMI_DENEME):
            try:
                kararlar = _ayristir(cagir(_istem(parti)), len(parti))
            except httpx.HTTPError as e:
                print(f"[siniflandir] Ollama hatası: {type(e).__name__}: {e}", flush=True)
                kararlar = None
            if kararlar is not None:
                break
        if kararlar is None:
            bozuk_parti += 1
            print(f"[siniflandir] parti bozuk ({AZAMI_DENEME} deneme) — işaretleniyor: "
                  f"{[p['id'] for p in parti]}", flush=True)
            if not kuru:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE soru SET kazanim_siniflandirma_at=now() WHERE id = ANY(%s)",
                        ([p["id"] for p in parti],),
                    )
                conn.commit()
            islenen += len(parti)
            print(f"[siniflandir] {islenen}/{toplam} — bağlanan {baglanan}, hiçbiri {hicbiri}", flush=True)
            continue
        with conn.cursor() as cur:
            for i, p in enumerate(parti):
                secim = kararlar[i]
                if secim:
                    a = p["adaylar"][secim - 1] if secim <= len(p["adaylar"]) else None
                else:
                    a = None
                if a is not None:
                    baglanan += 1
                else:
                    hicbiri += 1
                if kuru:
                    if ornek < 20:
                        print(f"  {p['soru'][:70]} -> {a['metin'][:70] if a else 'hiçbiri'}", flush=True)
                        ornek += 1
                elif a is not None:
                    cur.execute(
                        "UPDATE soru SET kazanim_id=%s, kazanim_skor=%s, kazanim_kaynak='llm', "
                        "kazanim_siniflandirma_at=now() WHERE id=%s",
                        (a["id"], a["skor"], p["id"]),
                    )
                else:
                    cur.execute(
                        "UPDATE soru SET kazanim_siniflandirma_at=now() WHERE id=%s", (p["id"],)
                    )
        if not kuru:
            conn.commit()
        islenen += len(parti)
        print(f"[siniflandir] {islenen}/{toplam} — bağlanan {baglanan}, hiçbiri {hicbiri}", flush=True)
    return {"islenen": islenen, "baglanan": baglanan, "hicbiri": hicbiri, "bozuk_parti": bozuk_parti}
