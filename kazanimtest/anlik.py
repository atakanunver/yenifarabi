"""kazanimtest/anlik.py — form_testi.sorular anlık görüntüsü (soru, şıklar, doğru, kaynak, kazanım satırı)."""

import json
import logging

import psycopg2.extras

from . import secici

log = logging.getLogger("kazanimtest")


def kazanim_satirlari(kazanim: str | list[str]) -> list[str]:
    """form_testi.kazanim ("\\n" ayraçlı) ya da hedef.kazanimlar listesi → boş olmayan satırlar."""
    parca = kazanim.split("\n") if isinstance(kazanim, str) else list(kazanim)
    return [p.strip() for p in parca if p and p.strip()]


def en_yakin_satirlar(sorular: list[dict], satirlar: list[str], model=None) -> list[str | None]:
    """Her soru için bge-m3 kosinüsü en yüksek kazanım satırı. Tek satır → model yüklenmez."""
    if not satirlar:
        return [None] * len(sorular)
    if len(satirlar) == 1:
        return [satirlar[0]] * len(sorular)
    m = model or secici.gomme_modeli()
    sv = [[float(x) for x in v] for v in m.encode(satirlar, normalize_embeddings=True)]
    sonuc = []
    for s in sorular:
        qv = [float(x) for x in m.encode(s["soru"], normalize_embeddings=True)]
        skor = [secici._kosinus(qv, v) for v in sv]
        sonuc.append(satirlar[skor.index(max(skor))])
    return sonuc


def olustur(sorular: list[dict], kazanim: str | list[str], model=None) -> list[dict]:
    satirlar = kazanim_satirlari(kazanim)
    ks = en_yakin_satirlar(sorular, satirlar, model)
    return [
        {
            "kimlik": s["kimlik"],
            "soru": s["soru"],
            "secenekler": list(s["secenekler"]),
            "dogru_index": int(s["dogru_index"]),
            "etiket": s.get("etiket"),
            "kazanim_satiri": k,
        }
        for s, k in zip(sorular, ks)
    ]


def soru_oku(kimlik: str, farabi_conn, havuz_conn) -> dict | None:
    """'havuz:<id>' / 'meb:<id>' → seçici adayı biçiminde soru; bulunamazsa None."""
    tur, _, sid = kimlik.partition(":")
    if not sid.isdigit():
        return None
    with (havuz_conn if tur == "havuz" else farabi_conn).cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if tur == "havuz":
            cur.execute("SELECT id, soru, secenekler, dogru_index, kaynak FROM soru WHERE id=%s", (int(sid),))
            r = cur.fetchone()
            if not r:
                return None
            sec = r["secenekler"]
            sec = json.loads(sec) if isinstance(sec, str) else sec
            return {"kimlik": kimlik, "soru": r["soru"], "secenekler": [str(x) for x in sec],
                    "dogru_index": int(r["dogru_index"]), "etiket": r["kaynak"]}
        if tur == "meb":
            cur.execute("SELECT soru_metni, secenekler, cevap, kaynak_dosya, soru_no FROM kazanim_test_soru WHERE id=%s", (int(sid),))
            r = cur.fetchone()
            if not r or not r["cevap"] or r["cevap"].strip().upper() not in list("ABCD"):
                return None
            sec = r["secenekler"]
            sec = json.loads(sec) if isinstance(sec, str) else sec
            return {"kimlik": kimlik, "soru": r["soru_metni"], "secenekler": [str(sec[h]) for h in "ABCD"],
                    "dogru_index": "ABCD".index(r["cevap"].strip().upper()),
                    "etiket": f"MEB kazanım testi ({r['kaynak_dosya']}, soru {r['soru_no']})"}
    return None


def doldur(farabi_conn, havuz_conn, kayit_modulu, model=None) -> tuple[int, int]:
    """Anlık görüntüsü olmayan form_testi kayıtlarını doldurur. (doldurulan, atlanan)"""
    ok = atlanan = 0
    for k in kayit_modulu.anliksiz_kayitlar(havuz_conn):
        idler = k["soru_idler"] if isinstance(k["soru_idler"], list) else json.loads(k["soru_idler"])
        sorular = [soru_oku(i, farabi_conn, havuz_conn) for i in idler]
        if not sorular or any(s is None for s in sorular):
            log.warning("form_testi %s: soru(lar) DB'de bulunamadı — anlık görüntü yazılmadı", k["id"])
            atlanan += 1
            continue
        kayit_modulu.anlik_yaz(havuz_conn, k["id"], olustur(sorular, k["kazanim"], model))
        ok += 1
    return ok, atlanan
