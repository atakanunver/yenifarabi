"""Anket modülü: yönetici hazırlar, öğrenci / veli / öğretmen kitlesine ayrı ayrı gönderir, sonuçları analiz eder.

Gizlilik (varsayılan, değiştirilemez): yanıtlar ANONİMDİR.
- `anket_katilim` yalnızca "bu kullanıcı bu anketi yanıtladı" der (tek yanıt kuralı, sıra/saat tutulmaz).
- `anket_yanit` + `anket_cevap` yalnızca "ne yanıtlandı"yı tutar; yanıt id'si rastgeledir, kullanıcıya bağ yoktur.
- Yanıtta sınıf/zaman/sıra gibi dolaylı kimlik bilgisi tutulmaz (anket_cevap WITHOUT ROWID).
- Sonuçlar rol bazında verilir; bir rolde ESIK_N'den az yanıt varsa o rolün sonucu (açık uçlu metin dahil) gizlenir.
Yönetici kimin yanıtlamadığını da göremez (yalnızca sayılar).
Anket bir kez bir role gönderilince soruları değiştirilemez (sonuçlar karışmasın).
"""

import json
import secrets
import sqlite3
from datetime import datetime

import zaman

ROLLER = ("ogrenci", "veli", "ogretmen")
ROL_ETIKET = {"ogrenci": "Öğrenciler", "veli": "Veliler", "ogretmen": "Öğretmenler"}
TURLER = {
    "tek": "Tek seçenek",
    "coklu": "Birden çok seçenek",
    "olcek": "1–5 ölçek",
    "metin": "Açık uçlu (yazılı)",
}
OLCEK = (1, 2, 3, 4, 5)
ESIK_N = 5  # bir rolde bundan az yanıt varsa sonuç gösterilmez
MAX_SORU = 30
MAX_SECENEK = 10
MAX_METIN = 1000  # açık uçlu yanıt


class AnketHatasi(Exception):
    pass


def _temiz(s: str | None) -> str:
    return " ".join((s or "").split())


# --- hazırlama (yönetici) ---


def olustur(conn: sqlite3.Connection, yonetici_id: int, baslik: str, aciklama: str = "") -> int:
    baslik, aciklama = _temiz(baslik), (aciklama or "").strip()
    if not baslik:
        raise AnketHatasi("Anket başlığı boş olamaz.")
    if len(baslik) > 150 or len(aciklama) > 1500:
        raise AnketHatasi("Başlık en çok 150, açıklama en çok 1500 karakter olabilir.")
    cur = conn.execute(
        "INSERT INTO anket (baslik, aciklama, olusturan, olusturma) VALUES (?, ?, ?, ?)",
        (baslik, aciklama, yonetici_id, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def getir(conn: sqlite3.Connection, anket_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM anket WHERE id = ?", (anket_id,)).fetchone()


def hedefler(conn: sqlite3.Connection, anket_id: int) -> dict[str, sqlite3.Row]:
    return {
        r["rol"]: r
        for r in conn.execute("SELECT * FROM anket_hedef WHERE anket_id = ?", (anket_id,))
    }


def taslak_mi(conn: sqlite3.Connection, anket_id: int) -> bool:
    return not hedefler(conn, anket_id)


def sorular(conn: sqlite3.Connection, anket_id: int, rol: str | None = None) -> list[dict]:
    """Sorular (sıralı). rol verilirse yalnızca o role sorulanlar."""
    liste = []
    for r in conn.execute("SELECT * FROM anket_soru WHERE anket_id = ? ORDER BY sira", (anket_id,)):
        d = dict(r)
        d["secenekler"] = json.loads(r["secenekler"])
        d["roller"] = [x for x in r["roller"].split(",") if x]
        if rol is None or rol in d["roller"]:
            liste.append(d)
    return liste


def soru_ekle(
    conn: sqlite3.Connection,
    anket_id: int,
    tur: str,
    metin: str,
    secenekler: list[str],
    zorunlu: bool,
    roller: list[str],
) -> int:
    if not taslak_mi(conn, anket_id):
        raise AnketHatasi("Gönderilmiş anketin soruları değiştirilemez.")
    if tur not in TURLER:
        raise AnketHatasi("Geçersiz soru türü.")
    metin = _temiz(metin)
    if not metin or len(metin) > 500:
        raise AnketHatasi("Soru metni boş olamaz ve en çok 500 karakter olabilir.")
    roller = [r for r in ROLLER if r in roller]
    if not roller:
        raise AnketHatasi("Soru en az bir gruba sorulmalı.")
    if conn.execute("SELECT count(*) FROM anket_soru WHERE anket_id = ?", (anket_id,)).fetchone()[0] >= MAX_SORU:
        raise AnketHatasi(f"Ankette en çok {MAX_SORU} soru olabilir.")
    if tur in ("tek", "coklu"):
        sec = []
        for s in secenekler:
            s = _temiz(s)
            if s and s not in sec:
                sec.append(s)
        if not 2 <= len(sec) <= MAX_SECENEK or any(len(s) > 150 for s in sec):
            raise AnketHatasi(f"Seçenekli soruda 2–{MAX_SECENEK} farklı seçenek olmalı (her biri en çok 150 karakter).")
    else:
        sec = []
    sira = conn.execute("SELECT COALESCE(MAX(sira), 0) + 1 FROM anket_soru WHERE anket_id = ?", (anket_id,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO anket_soru (anket_id, sira, tur, metin, secenekler, zorunlu, roller) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (anket_id, sira, tur, metin, json.dumps(sec, ensure_ascii=False), int(zorunlu), ",".join(roller)),
    )
    conn.commit()
    return cur.lastrowid


def soru_sil(conn: sqlite3.Connection, anket_id: int, soru_id: int) -> None:
    if not taslak_mi(conn, anket_id):
        raise AnketHatasi("Gönderilmiş anketin soruları değiştirilemez.")
    if conn.execute("DELETE FROM anket_soru WHERE id = ? AND anket_id = ?", (soru_id, anket_id)).rowcount != 1:
        conn.rollback()
        raise AnketHatasi("Soru bulunamadı.")
    for i, r in enumerate(conn.execute("SELECT id FROM anket_soru WHERE anket_id = ? ORDER BY sira", (anket_id,)).fetchall(), 1):
        conn.execute("UPDATE anket_soru SET sira = ? WHERE id = ?", (i, r["id"]))
    conn.commit()


def sil(conn: sqlite3.Connection, anket_id: int) -> None:
    """Yalnızca hiç gönderilmemiş taslak silinir (yanıt verisi korunur)."""
    if not taslak_mi(conn, anket_id):
        raise AnketHatasi("Gönderilmiş anket silinemez; kapatabilirsiniz.")
    conn.execute("DELETE FROM anket WHERE id = ?", (anket_id,))
    conn.commit()


def _filtre_listesi(filtre: str) -> list[str]:
    return [t.strip() for t in (filtre or "").replace(";", ",").split(",") if t.strip()]


def siniflar(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]


def _sinif_uyar(sinif: str, jetonlar: list[str]) -> bool:
    return not jetonlar or sinif in jetonlar or sinif.split("-")[0] in jetonlar


def dagit(
    conn: sqlite3.Connection, anket_id: int, rol: str, sinif_filtre: str = "", kapanis: str = ""
) -> None:
    """Anketi bir role (ayrı ayrı) gönderir. Öğrenci/veli için sınıf/düzey süzgeci (ör. '9, 10-A') verilebilir."""
    if getir(conn, anket_id) is None:
        raise AnketHatasi("Anket bulunamadı.")
    if rol not in ROLLER:
        raise AnketHatasi("Geçersiz grup.")
    if rol in hedefler(conn, anket_id):
        raise AnketHatasi(f"{ROL_ETIKET[rol]} için anket zaten gönderilmiş.")
    if not sorular(conn, anket_id, rol):
        raise AnketHatasi(f"{ROL_ETIKET[rol]} için sorulacak soru yok.")
    jetonlar = _filtre_listesi(sinif_filtre) if rol != "ogretmen" else []
    mevcut = siniflar(conn)
    gecerli = set(mevcut) | {s.split("-")[0] for s in mevcut}
    kotu = [t for t in jetonlar if t not in gecerli]
    if kotu:
        raise AnketHatasi("Bilinmeyen sınıf/düzey: " + ", ".join(kotu))
    kapanis = (kapanis or "").strip()
    if kapanis:
        try:
            gun = datetime.strptime(kapanis, "%Y-%m-%d")  # noqa: DTZ007
        except ValueError as e:
            raise AnketHatasi("Kapanış tarihi YYYY-AA-GG olmalı.") from e
        if gun.date() < zaman.simdi().date():
            raise AnketHatasi("Kapanış tarihi geçmişte olamaz.")
    if not hedef_kitle(conn, rol, ",".join(jetonlar)):
        raise AnketHatasi("Bu süzgece uyan kullanıcı yok.")
    conn.execute(
        "INSERT INTO anket_hedef (anket_id, rol, sinif_filtre, acilis, kapanis) VALUES (?, ?, ?, ?, ?)",
        (anket_id, rol, ",".join(jetonlar), zaman.simdi_str(), kapanis or None),
    )
    conn.commit()


def kapat(conn: sqlite3.Connection, anket_id: int, rol: str) -> None:
    if conn.execute(
        "UPDATE anket_hedef SET kapatildi = 1 WHERE anket_id = ? AND rol = ?", (anket_id, rol)
    ).rowcount != 1:
        conn.rollback()
        raise AnketHatasi("Bu grup için gönderilmiş anket yok.")
    conn.commit()


def acik_mi(hedef: sqlite3.Row) -> bool:
    if hedef["kapatildi"]:
        return False
    return not hedef["kapanis"] or hedef["kapanis"] >= zaman.simdi().strftime("%Y-%m-%d")


# --- kitle ---


def hedef_kitle(conn: sqlite3.Connection, rol: str, sinif_filtre: str = "") -> list[int]:
    """Süzgece uyan aktif kullanıcı id'leri (katılım oranının paydası)."""
    jetonlar = _filtre_listesi(sinif_filtre)
    if rol == "ogrenci":
        return [
            r["kullanici_id"]
            for r in conn.execute(
                "SELECT o.kullanici_id, o.sinif FROM ogrenci o JOIN kullanici k ON k.id = o.kullanici_id WHERE k.aktif = 1"
            )
            if _sinif_uyar(r["sinif"], jetonlar)
        ]
    if rol == "veli":
        ids = set()
        for r in conn.execute(
            "SELECT vo.veli_id, o.sinif FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id"
            " JOIN kullanici k ON k.id = vo.veli_id WHERE k.aktif = 1"
        ):
            if _sinif_uyar(r["sinif"], jetonlar):
                ids.add(r["veli_id"])
        return sorted(ids)
    if rol == "ogretmen":
        return [r[0] for r in conn.execute("SELECT id FROM kullanici WHERE rol = 'ogretmen' AND aktif = 1")]
    return []


def _kullanici_siniflari(conn: sqlite3.Connection, k: sqlite3.Row) -> list[str]:
    if k["rol"] == "ogrenci":
        return [r[0] for r in conn.execute("SELECT sinif FROM ogrenci WHERE kullanici_id = ?", (k["id"],))]
    if k["rol"] == "veli":
        return [
            r[0]
            for r in conn.execute(
                "SELECT o.sinif FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id WHERE vo.veli_id = ?",
                (k["id"],),
            )
        ]
    return []


def kapsiyor_mu(conn: sqlite3.Connection, k: sqlite3.Row, hedef: sqlite3.Row) -> bool:
    if k["rol"] != hedef["rol"]:
        return False
    if k["rol"] == "ogretmen":
        return True
    jetonlar = _filtre_listesi(hedef["sinif_filtre"])
    return any(_sinif_uyar(s, jetonlar) for s in _kullanici_siniflari(conn, k))


def yanitladi_mi(conn: sqlite3.Connection, anket_id: int, kid: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM anket_katilim WHERE anket_id = ? AND kullanici_id = ?", (anket_id, kid)
        ).fetchone()
        is not None
    )


def kullanicinin_anketleri(conn: sqlite3.Connection, k: sqlite3.Row) -> dict[str, list[dict]]:
    """{'bekleyen': [...], 'yanitlanan': [...]} — yalnızca açık ve kullanıcıyı kapsayan anketler."""
    sonuc: dict[str, list[dict]] = {"bekleyen": [], "yanitlanan": []}
    if k["rol"] not in ROLLER:
        return sonuc
    for r in conn.execute(
        "SELECT a.id, a.baslik, a.aciklama, h.* FROM anket a JOIN anket_hedef h ON h.anket_id = a.id"
        " WHERE h.rol = ? ORDER BY a.id DESC",
        (k["rol"],),
    ):
        if not kapsiyor_mu(conn, k, r):
            continue
        yanit = yanitladi_mi(conn, r["id"], k["id"])
        if not yanit and not acik_mi(r):
            continue
        satir = {"id": r["id"], "baslik": r["baslik"], "aciklama": r["aciklama"], "kapanis": r["kapanis"]}
        sonuc["yanitlanan" if yanit else "bekleyen"].append(satir)
    return sonuc


def bekleyen_sayisi(conn: sqlite3.Connection, k: sqlite3.Row) -> int:
    return len(kullanicinin_anketleri(conn, k)["bekleyen"])


# --- yanıtlama ---


def yanitla(conn: sqlite3.Connection, k: sqlite3.Row, anket_id: int, girdi: dict[int, list[str]]) -> None:
    """girdi: soru_id -> değer listesi. Tüm doğrulama sunucuda; ya hepsi yazılır ya hiçbiri."""
    hedef = hedefler(conn, anket_id).get(k["rol"])
    if hedef is None or not kapsiyor_mu(conn, k, hedef):
        raise AnketHatasi("Bu ankete erişiminiz yok.")
    if not acik_mi(hedef):
        raise AnketHatasi("Bu anket kapandı.")
    if yanitladi_mi(conn, anket_id, k["id"]):
        raise AnketHatasi("Bu anketi zaten yanıtladınız.")
    satirlar: list[tuple[int, str]] = []
    for s in sorular(conn, anket_id, k["rol"]):
        ham = [v.strip() for v in girdi.get(s["id"], []) if v is not None and v.strip()]
        if not ham:
            if s["zorunlu"]:
                raise AnketHatasi(f"Zorunlu soru boş: {s['metin']}")
            continue
        if s["tur"] == "metin":
            if len(ham[0]) > MAX_METIN:
                raise AnketHatasi(f"Yanıt en çok {MAX_METIN} karakter olabilir.")
            satirlar.append((s["id"], " ".join(ham[0].split())))
        elif s["tur"] == "olcek":
            if len(ham) != 1 or not ham[0].isdigit() or int(ham[0]) not in OLCEK:
                raise AnketHatasi("Geçersiz ölçek değeri.")
            satirlar.append((s["id"], ham[0]))
        else:
            if s["tur"] == "tek" and len(ham) != 1:
                raise AnketHatasi("Bu soruda tek seçenek işaretlenmeli.")
            gecerli = set()
            for v in ham:
                if not v.isdigit() or int(v) >= len(s["secenekler"]):
                    raise AnketHatasi("Geçersiz seçenek.")
                gecerli.add(int(v))
            satirlar += [(s["id"], str(i)) for i in sorted(gecerli)]
    try:
        # katılım kaydı tek yanıt kuralını DB'de zorlar (paralel gönderim ikinciyi reddeder)
        conn.execute(
            "INSERT INTO anket_katilim (anket_id, kullanici_id, rol) VALUES (?, ?, ?)", (anket_id, k["id"], k["rol"])
        )
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise AnketHatasi("Bu anketi zaten yanıtladınız.") from e
    yid = secrets.randbits(62)  # rastgele: katılım sırasıyla eşleştirilemez
    conn.execute("INSERT INTO anket_yanit (id, anket_id, rol) VALUES (?, ?, ?)", (yid, anket_id, k["rol"]))
    conn.executemany(
        "INSERT INTO anket_cevap (yanit_id, soru_id, deger) VALUES (?, ?, ?)", [(yid, sid, d) for sid, d in satirlar]
    )
    conn.commit()


# --- sonuçlar (yönetici) ---


def katilim_ozeti(conn: sqlite3.Connection, anket_id: int) -> list[dict]:
    """Gönderilen her grup için hedef kitle / yanıt sayısı / oran / durum."""
    cikti = []
    for rol, h in hedefler(conn, anket_id).items():
        kitle = len(hedef_kitle(conn, rol, h["sinif_filtre"]))
        n = conn.execute("SELECT count(*) FROM anket_katilim WHERE anket_id = ? AND rol = ?", (anket_id, rol)).fetchone()[0]
        cikti.append({
            "rol": rol, "ad": ROL_ETIKET[rol], "kitle": kitle, "yanit": n,
            "oran": round(100 * n / kitle) if kitle else None,
            "yeterli": n >= ESIK_N, "acik": acik_mi(h), "filtre": h["sinif_filtre"],
            "acilis": h["acilis"], "kapanis": h["kapanis"],
        })
    return cikti


def sonuc(conn: sqlite3.Connection, anket_id: int) -> list[dict]:
    """Soru bazında, rol kırılımlı sonuç. n < ESIK_N olan rol/soru için `gizli=True` ve veri yok."""
    cikti = []
    yanit_sayilari = {
        r["rol"]: r[1]
        for r in conn.execute("SELECT rol, count(*) FROM anket_yanit WHERE anket_id = ? GROUP BY rol", (anket_id,))
    }
    for s in sorular(conn, anket_id):
        roller = []
        for rol in s["roller"]:
            if rol not in hedefler(conn, anket_id):
                continue
            satirlar = conn.execute(
                "SELECT c.yanit_id, c.deger FROM anket_cevap c JOIN anket_yanit y ON y.id = c.yanit_id"
                " WHERE c.soru_id = ? AND y.rol = ?",
                (s["id"], rol),
            ).fetchall()
            cevaplayan = len({r["yanit_id"] for r in satirlar})
            toplam = yanit_sayilari.get(rol, 0)
            d = {"rol": rol, "ad": ROL_ETIKET[rol], "toplam": toplam, "n": cevaplayan, "gizli": False}
            if toplam < ESIK_N or cevaplayan < ESIK_N:
                d["gizli"] = True  # küçük grup: dağılım ve metin gösterilmez
                roller.append(d)
                continue
            if s["tur"] in ("tek", "coklu"):
                sayim = [0] * len(s["secenekler"])
                for r in satirlar:
                    sayim[int(r["deger"])] += 1
                d["secenekler"] = [
                    {"ad": ad, "sayi": sayim[i], "yuzde": round(100 * sayim[i] / cevaplayan)}
                    for i, ad in enumerate(s["secenekler"])
                ]
            elif s["tur"] == "olcek":
                degerler = [int(r["deger"]) for r in satirlar]
                d["ortalama"] = round(sum(degerler) / len(degerler), 2)
                d["dagilim"] = [
                    {"puan": p, "sayi": degerler.count(p), "yuzde": round(100 * degerler.count(p) / cevaplayan)}
                    for p in OLCEK
                ]
            else:
                d["metinler"] = sorted((r["deger"] for r in satirlar), key=lambda t: (len(t), t))
            roller.append(d)
        cikti.append({**s, "roller_sonuc": roller})
    return cikti


def anket_listesi(conn: sqlite3.Connection) -> list[dict]:
    liste = []
    for a in conn.execute("SELECT * FROM anket ORDER BY id DESC"):
        h = hedefler(conn, a["id"])
        liste.append({
            "id": a["id"], "baslik": a["baslik"], "olusturma": a["olusturma"],
            "soru_sayisi": conn.execute("SELECT count(*) FROM anket_soru WHERE anket_id = ?", (a["id"],)).fetchone()[0],
            "taslak": not h,
            "gruplar": [{"ad": ROL_ETIKET[r], "acik": acik_mi(x)} for r, x in h.items()],
            "yanit": conn.execute("SELECT count(*) FROM anket_katilim WHERE anket_id = ?", (a["id"],)).fetchone()[0],
        })
    return liste
