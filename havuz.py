"""havuz.py — soru_havuzu veritabanından (yalnızca AGY onaylı) anında soru çeker.

Havuz boş/erişilemezse None döner; çağıran mevcut RAG+Ollama / statik akışa düşer.
Kullanıcı kararı (2026-10-05): AGY denetiminden geçmemiş soru oyunlara GİTMEZ."""

import logging
import random
import re

import turkce

log = logging.getLogger("arena.havuz")
SUTUNLAR = "id, konu, zorluk, soru, kisa_cevap, secenekler, dogru_index, kaynak"
RENKLER = [
    ("from-blue-600 to-indigo-600", "text-blue-400 bg-blue-500/20 border-blue-500/40"),
    (
        "from-emerald-600 to-teal-600",
        "text-emerald-400 bg-emerald-500/20 border-emerald-500/40",
    ),
    (
        "from-amber-600 to-orange-600",
        "text-amber-400 bg-amber-500/20 border-amber-500/40",
    ),
    (
        "from-purple-600 to-pink-600",
        "text-purple-400 bg-purple-500/20 border-purple-500/40",
    ),
]


def _db_sorgu(sql, parametreler):
    import psycopg2

    with psycopg2.connect(
        host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3
    ) as c, c.cursor() as cur:
        cur.execute(sql, parametreler)
        return cur.fetchall()


def sube_normalize(s: str) -> str:
    """Şube adını kanonik '9-A', '10-B' biçimine getirir (örn. '9a', '9/A' -> '9-A')."""
    if not s:
        return ""
    temiz = str(s).strip().upper().replace("/", "-")
    m = re.match(r"^(\d+)\s*[-_]?\s*([A-Za-zÇĞİÖŞÜçğıöşü])$", temiz)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return temiz


def _kullanildi(ids, sorgu, sube: str = "", oyun: str = ""):
    if not ids or sorgu is not None:
        return
    try:
        import psycopg2

        with psycopg2.connect(
            host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3
        ) as c:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE soru SET kullanim_sayisi = kullanim_sayisi + 1 WHERE id = ANY(%s)",
                    (list(ids),),
                )
                temiz_sube = sube_normalize(sube)
                if temiz_sube:
                    cur.executemany(
                        "INSERT INTO soru_kullanim (soru_id, sube, oyun) VALUES (%s, %s, %s)",
                        [(int(sid), temiz_sube, oyun or "") for sid in ids],
                    )
    except Exception as e:  # noqa: BLE001 — sayaç yardımcı
        log.warning("kullanım sayacı yazılamadı: %s", e)


def _cek(ders, sinif, konu, sorgu, limit=400, sube: str = ""):
    temiz_sube = sube_normalize(sube)
    temiz_ders = turkce.kapsam_anahtari(ders) if ders else ""
    if temiz_sube:
        # Aynı sınıfta daha önce sorulmuş sorular en sona (1) atılır, sorulmamışlar önce (0) gelir
        sql = (
            f"SELECT {SUTUNLAR} FROM soru WHERE durum = 'onayli' AND ders = %s AND sinif = %s "
            + ("AND konu ILIKE %s " if konu else "")
            + "ORDER BY CASE WHEN id IN (SELECT soru_id FROM soru_kullanim WHERE sube = %s) THEN 1 ELSE 0 END, "
            + "kullanim_sayisi, random() LIMIT %s"
        )
        p = (temiz_ders, sinif) + ((f"%{konu}%",) if konu else ()) + (temiz_sube, limit)
    else:
        sql = (
            f"SELECT {SUTUNLAR} FROM soru WHERE durum = 'onayli' AND ders = %s AND sinif = %s "
            + ("AND konu ILIKE %s " if konu else "")
            + "ORDER BY kullanim_sayisi, random() LIMIT %s"
        )
        p = (temiz_ders, sinif) + ((f"%{konu}%",) if konu else ()) + (limit,)
    try:
        return (sorgu or _db_sorgu)(sql, p)
    except Exception as e:  # noqa: BLE001 — havuz yardımcı; hata = eski akış
        log.warning("havuz okunamadı: %s", e)
        return None


_DURAK = {
    "bilgi", "bilgileri", "ilgili", "olarak", "ifade", "eder", "eden", "yapar", "açıklar",
    "yorumlar", "ayırt", "örnekler", "sahip", "kavram", "kavramı", "arasındaki", "ilişkiyi",
}


def kazanim_anahtar_kelimeleri(metin: str, adet: int = 3) -> list[str]:
    """Kazanım cümlesinden ILIKE için kısa anahtar kelimeler (en uzundan başlayarak)."""
    kelimeler = re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]{5,}", metin or "")
    gorulen, aday = set(), []
    for k in kelimeler:
        t = k.lower()
        if t in _DURAK or t in gorulen:
            continue
        gorulen.add(t)
        # Türkçe ekleri tolere etmek için kökü kısalt (ILIKE %kök%)
        aday.append(k[: max(5, len(k) - 2)] if len(k) > 7 else k)
    aday.sort(key=len, reverse=True)
    return aday[:adet]


def jeopardy_seti(
    ders: str, sinif: int, konu: str = "", sorgu=None, kazanim: bool = False, sube: str = ""
) -> list[dict] | None:
    """4 konu × 4 zorluk (100–400 puan); ollama_soru_uret ile aynı biçim.

    kazanim=True: konu bir kazanım cümlesidir; anahtar kelimelerle aranır, hiçbiri tam
    bir set vermezse filtresiz sorguya düşülür (kazanım yüzünden asla sıfır soru dönmez)."""
    if kazanim and konu:
        for kw in kazanim_anahtar_kelimeleri(konu):
            sonuc = _jeopardy_kur(_cek(ders, sinif, kw, sorgu, sube=sube), sorgu, sube=sube, oyun="sinif_arena")
            if sonuc:
                return sonuc
        return _jeopardy_kur(_cek(ders, sinif, "", sorgu, sube=sube), sorgu, sube=sube, oyun="sinif_arena")
    return _jeopardy_kur(_cek(ders, sinif, konu, sorgu, sube=sube), sorgu, sube=sube, oyun="sinif_arena")


def _jeopardy_kur(satirlar, sorgu=None, sube: str = "", oyun: str = "sinif_arena") -> list[dict] | None:
    if not satirlar:
        return None
    konular: dict[str, dict[int, tuple]] = {}
    for s in satirlar:
        konular.setdefault(s[1], {}).setdefault(s[2], s)
    tam = [k for k, z in konular.items() if len(z) == 4]

    kategoriler: list[tuple[str, dict[int, tuple]]] = []
    if len(tam) >= 4:
        random.shuffle(tam)
        for k in tam[:4]:
            kategoriler.append((k, konular[k]))
    else:
        # Aynı kaynak/üniteden gelen 4 zorluklu setler (konu adları hafif farklı olsa da)
        kaynak_gruplar: dict[str, dict[int, tuple]] = {}
        for s in satirlar:
            kaynak_gruplar.setdefault(s[7], {}).setdefault(s[2], s)
        tam_kaynak = [k for k, z in kaynak_gruplar.items() if len(z) == 4]
        if len(tam_kaynak) < 4:
            return None
        random.shuffle(tam_kaynak)
        for k in tam_kaynak[:4]:
            z_sozluk = kaynak_gruplar[k]
            kat_adi = z_sozluk[1][1] if 1 in z_sozluk else list(z_sozluk.values())[0][1]
            kategoriler.append((kat_adi, z_sozluk))

    cikti, ids = [], []
    for i, (kat_adi, z_sozluk) in enumerate(kategoriler):
        renk, rozet = RENKLER[i]
        sorular = []
        for z in (1, 2, 3, 4):
            s = z_sozluk[z]
            ids.append(s[0])
            sorular.append(
                {
                    "points": z * 100,
                    "sid": s[0],
                    "q": s[3],
                    "a": s[4],
                    "kaynak": s[7],
                    "answered": False,
                }
            )
        cikti.append(
            {
                "id": f"havuz_kat_{i + 1}",
                "name": kat_adi,
                "color": renk,
                "badgeColor": rozet,
                "questions": sorular,
            }
        )
    _kullanildi(ids, sorgu, sube=sube, oyun=oyun)
    return cikti


def petek_sorulari(
    ders: str, sinif: int, adet: int, sorgu=None, sube: str = "", oyun: str = "hexafetih"
) -> list[dict] | None:
    """HexaFetih: her petek için FARKLI bir çoktan seçmeli soru."""
    satirlar = _cek(ders, sinif, "", sorgu, sube=sube)
    if not satirlar or len(satirlar) < min(adet, 10):
        return None
    secilen = [satirlar[i % len(satirlar)] for i in range(adet)]
    _kullanildi([s[0] for s in secilen], sorgu, sube=sube, oyun=oyun)
    return [
        {
            "sid": s[0],
            "konu": s[1],
            "q": s[3],
            "secenekler": list(s[5]),
            "a": s[5][s[6]],
            "kaynak": s[7],
        }
        for s in secilen
    ]


def duello_sorulari(
    ders: str, sinif: int, adet: int = 10, sorgu=None, sube: str = ""
) -> list[dict] | None:
    """Tahta Düellosu: 10 adet çoktan seçmeli yarışma sorusu."""
    return petek_sorulari(ders, sinif, adet, sorgu, sube=sube, oyun="duello")


def sube_soru_istatistikleri(sube: str, ders: str = "", sinif: int = 0) -> dict:
    """Belirli bir şube için (örn. '9-A') toplam onaylı, sorulmuş ve kalan taze soru sayılarını döner."""
    temiz_sube = sube_normalize(sube)
    temiz_ders = turkce.kapsam_anahtari(ders) if ders else ""
    try:
        import psycopg2

        with psycopg2.connect(
            host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3
        ) as c, c.cursor() as cur:
            kosullar = ["s.durum = 'onayli'"]
            param = []
            if temiz_ders:
                kosullar.append("s.ders = %s")
                param.append(temiz_ders)
            if sinif:
                kosullar.append("s.sinif = %s")
                param.append(sinif)

            where_str = " AND ".join(kosullar)
            sql = f"""
                SELECT 
                    count(DISTINCT s.id) as toplam,
                    count(DISTINCT CASE WHEN sk.id IS NOT NULL THEN s.id END) as sorulan,
                    count(DISTINCT CASE WHEN sk.id IS NULL THEN s.id END) as kalan
                FROM soru s
                LEFT JOIN soru_kullanim sk ON sk.soru_id = s.id AND sk.sube = %s
                WHERE {where_str}
            """
            cur.execute(sql, [temiz_sube] + param)
            r = cur.fetchone()
            return {
                "sube": temiz_sube,
                "toplam_onayli": r[0] or 0,
                "sorulan": r[1] or 0,
                "kalan_taze": r[2] or 0,
            }
    except Exception as e:
        log.warning("sube istatistiği alınamadı: %s", e)
        return {"sube": temiz_sube, "hata": str(e)}

