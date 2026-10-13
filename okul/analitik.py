"""Kullanım analitiği: olay kaydı (tamponlu, tekilleştirilmiş) ve yönetici sorguları.

Gizlilik: yalnızca (kullanıcı, tür, nesne no, gün, saat, oturum kısa kodu) tutulur. Form içeriği,
mesaj metni, cevap, parola, token, IP, user-agent KAYDEDİLMEZ. Akademik başarı verisiyle ilgisi yoktur.
Geçmiş veri uydurulmaz: veri_baslangici() ilk gerçek kayıt gününü verir, öncesi "veri yok"tur.
"""

import hashlib
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import db
import zaman

NABIZ_SURESI = 90  # sn: çevrim içi sayılma penceresi
EN_FAZLA_ARALIK = 366
TAMPON_ADET = 25
TAMPON_SURE = 5.0  # sn
AZ_VERI = 10  # öneri/eğilim için asgari olay-günü

# tür -> (görünen ad, ilgili roller, temel işlem mi, kullanılmıyorsa öneri)
OZELLIKLER = {
    "ana_sayfa": ("Ana sayfa", ("ogrenci", "veli", "ogretmen", "yonetici"), False, ""),
    "odev_goruntule": (
        "Ödev görüntüleme", ("ogrenci",), True,
        "Ana sayfadaki bekleyen ödev kartını öne al; ödev ilanında teslim tarihini öğrenciye bildiren duyuru kullan.",
    ),
    "odev_tamamla": (
        "Ödev tamamlama", ("ogrenci",), True,
        "Teslim butonunu ödev sayfasının üstüne taşı; öğretmenlere teslim tarihi vermelerini hatırlat.",
    ),
    "test_basla": (
        "Maraton/test başlatma", ("ogrenci",), True,
        "Maratonu ana sayfada ders adıyla öne çıkar; sınıfta kısa tanıtım yap ve haftalık liderliği duyur.",
    ),
    "test_bitir": (
        "Maraton/test tamamlama", ("ogrenci",), True,
        "Başlatıp bitirmeyenler varsa soru sayısını/süreyi gözden geçir; yarım bırakma nedenini öğrencilere sor.",
    ),
    "kazanim_raporu": (
        "Kazanım raporu", ("ogrenci",), True,
        "Kazanım sayfasına ana sayfadan doğrudan bağlantı ver; öğretmenler dersle birlikte sayfayı göstersin.",
    ),
    "duyuru_goruntule": (
        "Duyuru görüntüleme", ("ogrenci", "veli", "ogretmen", "yonetici"), True,
        "Okunmamış duyuru için ana sayfada belirgin bir kart kullan; kritik duyuruları SMS ile de ilet.",
    ),
    "ogretmen_odev_olustur": (
        "Öğretmen: ödev oluşturma", ("ogretmen",), True,
        "Öğretmenlere ödev verme adımlarını gösteren kısa bir tanıtım yap; ana sayfadaki 'Ödev ver' sekmesini vurgula.",
    ),
    "ogretmen_etkinlik_olustur": (
        "Öğretmen: sınav/etkinlik ekleme", ("ogretmen",), True,
        "Sınav takvimini zümre toplantısında göster; yazılı tarihlerini platforma girmeyi zümre kararı yap.",
    ),
    "veli_gelisim_raporu": (
        "Veli: gelişim raporu", ("veli",), True,
        "Veli ana sayfasına 'Kazanım raporu' bağlantısı ekle; veli toplantısında kısa gösterim yap.",
    ),
}
# Sayısı hesaplanmayan sistem olayları
GIRIS, CIKIS, AKTIF = "giris", "cikis", "aktif"
TEMEL_ISLEMLER = tuple(t for t, v in OZELLIKLER.items() if v[2])

_SAYFALAR = (
    (re.compile(r"^/(ogrenci|veli|ogretmen|yonetici)$"), "ana_sayfa"),
    (re.compile(r"^/ogrenci/odev/\d+$"), "odev_goruntule"),
    (re.compile(r"^/ogrenci/kazanimlar$"), "kazanim_raporu"),
    (re.compile(r"^/veli/kazanim$"), "veli_gelisim_raporu"),
    (re.compile(r"^/duyurular$"), "duyuru_goruntule"),
)


# --- kayıt ---

_kilit = threading.Lock()
_tampon: list[tuple] = []
_ilk_zaman = 0.0
_goruldu: set[tuple] = set()
_goruldu_gun = ""


def sifirla() -> None:
    """Testler için: bellek içi tampon ve tekilleştirme önbelleğini boşalt."""
    global _ilk_zaman, _goruldu_gun
    with _kilit:
        _tampon.clear()
        _goruldu.clear()
        _ilk_zaman, _goruldu_gun = 0.0, ""


def oturum_kodu(token: str | None) -> str:
    """Token'dan tek yönlü kısa kod (oturum başına sayım için); token geri çıkarılamaz."""
    if not token:
        return ""
    return hashlib.sha256(("analitik:" + token).encode()).hexdigest()[:12]


def sayfa_olayi(yol: str) -> str | None:
    for kalip, tur in _SAYFALAR:
        if kalip.match(yol):
            return tur
    return None


def kaydet(kullanici_id: int, rol: str, tur: str, nesne: str = "", token: str | None = None) -> None:
    """Olayı tampona ekler. Aynı (kullanıcı, tür, nesne, gün, oturum) bu süreçte bir kez yazılır;
    DB'de de UNIQUE + INSERT OR IGNORE olduğundan istemcinin tekrar göndermesi sayıyı artırmaz."""
    global _ilk_zaman, _goruldu_gun
    simdi = zaman.simdi()
    gun = simdi.strftime("%Y-%m-%d")
    oturum = oturum_kodu(token)
    anahtar = (kullanici_id, tur, nesne, oturum)
    with _kilit:
        if gun != _goruldu_gun:
            _goruldu.clear()
            _goruldu_gun = gun
        if anahtar in _goruldu:
            return
        _goruldu.add(anahtar)
        if not _tampon:
            _ilk_zaman = time.monotonic()
        _tampon.append((kullanici_id, rol, tur, nesne, gun, simdi.hour, oturum))
        hazir = len(_tampon) >= TAMPON_ADET or time.monotonic() - _ilk_zaman >= TAMPON_SURE
    if hazir:
        bosalt()


def bosalt() -> None:
    """Tamponu tek işlemde yazar. Analitik hatası uygulamayı asla düşürmez."""
    with _kilit:
        if not _tampon:
            return
        parti = list(_tampon)
        _tampon.clear()
    try:
        conn = db.baglanti()
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO olay (kullanici_id, rol, tur, nesne, gun, saat, oturum_k)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                parti,
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass  # sayaç kaybı kabul; sayfa servisi etkilenmez


def istekten(request, tur: str, nesne: str = "") -> None:
    """Rota içinden: başarılı işlemden sonra çağrılır (kullanıcı/token request.state'ten)."""
    k = getattr(request.state, "kullanici", None)
    if k is not None:
        kaydet(k["id"], k["rol"], tur, nesne, getattr(request.state, "token", None))


def sayfa_goruntulendi(request, durum: int) -> None:
    """Orta katmandan: yalnızca başarılı (200) GET sayfa görüntülemeleri + sayfa açıkken 'aktif' saati."""
    if durum != 200 or request.url.path.startswith("/static"):
        return
    k = getattr(request.state, "kullanici", None)
    if k is None or k["sifre_degismeli"]:
        return
    token = getattr(request.state, "token", None)
    if request.method == "GET":
        tur = sayfa_olayi(request.url.path)
        if tur:
            kaydet(k["id"], k["rol"], tur, "" if tur != "odev_goruntule" else request.url.path.rsplit("/", 1)[1], token)
    kaydet(k["id"], k["rol"], AKTIF, str(zaman.simdi().hour), token)


def nabiz(conn: sqlite3.Connection, token_hash: str) -> None:
    conn.execute(
        "UPDATE oturum SET son_nabiz = ? WHERE token_hash = ?", (zaman.simdi_str(), token_hash)
    )
    conn.commit()


# --- filtre ---


@dataclass
class Filtre:
    bas: str
    bit: str
    rol: str | None = None
    sinif: str | None = None
    duzey: str | None = None


def _gun(s: str | None) -> date | None:
    try:
        return datetime.strptime(s or "", "%Y-%m-%d").date()
    except ValueError:
        return None


def siniflar(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]


def duzeyler(conn: sqlite3.Connection) -> list[str]:
    return sorted({m.group() for s in siniflar(conn) if (m := re.match(r"\d+", s))}, key=int)


def filtre_coz(conn: sqlite3.Connection, bas, bit, rol, sinif, duzey, roller) -> Filtre:
    """Sorgu parametrelerini beyaz listeyle doğrular; geçersiz/yabancı değer yok sayılır."""
    bugun = zaman.simdi().date()
    b, e = _gun(bas), _gun(bit)
    if e is None or e > bugun:
        e = bugun
    if b is None or b > e or (e - b).days >= EN_FAZLA_ARALIK:
        b = e - timedelta(days=29)
    sn = siniflar(conn)
    return Filtre(
        b.isoformat(),
        e.isoformat(),
        rol if rol in roller else None,
        sinif if sinif in sn else None,
        duzey if duzey in duzeyler(conn) else None,
    )


def _sinif_listesi(conn, f: Filtre) -> list[str] | None:
    if f.sinif:
        return [f.sinif]
    if f.duzey:
        return [s for s in siniflar(conn) if re.match(rf"{f.duzey}(?!\d)", s)]
    return None


def _kullanici_kosulu(conn, f: Filtre, alan: str = "e.kullanici_id") -> tuple[str, list]:
    """Rol ve sınıf/düzey filtresi. Sınıf seçiliyse: o sınıfın öğrencisi, velisi ve görevli öğretmeni
    (yönetici dahil değil). Güncel sınıf atamasına göre; geçmiş atamalar tutulmaz."""
    kos, par = [], []
    if f.rol:
        kos.append("e.rol = ?")
        par.append(f.rol)
    sl = _sinif_listesi(conn, f)
    if sl is not None:
        if not sl:
            return "0", []
        yer = ",".join("?" * len(sl))
        kos.append(
            f"{alan} IN (SELECT kullanici_id FROM ogrenci WHERE sinif IN ({yer}) AND kullanici_id IS NOT NULL"
            f" UNION SELECT vo.veli_id FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id WHERE o.sinif IN ({yer})"
            f" UNION SELECT ogretmen_id FROM ogretmen_gorev WHERE sinif IN ({yer}))"
        )
        par += sl * 3
    return (" AND ".join(kos) or "1"), par


# --- sorgular ---


def veri_baslangici(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MIN(gun) FROM olay").fetchone()[0]


def cevrimici(conn: sqlite3.Connection, f: Filtre) -> int:
    """Son 90 sn'de nabız gönderen geçerli (silinmemiş) oturumların FARKLI kullanıcıları."""
    esik = (zaman.simdi() - timedelta(seconds=NABIZ_SURESI)).strftime(zaman.BICIM)
    kos, par = [], []
    if f.rol:
        kos.append("k.rol = ?")
        par.append(f.rol)
    ks, kp = _kullanici_kosulu(conn, Filtre(f.bas, f.bit, None, f.sinif, f.duzey), "k.id")
    return conn.execute(
        "SELECT COUNT(DISTINCT k.id) FROM oturum o JOIN kullanici k ON k.id = o.kullanici_id"
        f" WHERE k.aktif = 1 AND o.son_nabiz >= ? AND {' AND '.join(kos + [ks.replace('e.rol', 'k.rol')])}",
        [esik, *par, *kp],
    ).fetchone()[0]


def _aktif(conn, f: Filtre, bas: str, bit: str) -> int:
    ks, kp = _kullanici_kosulu(conn, f)
    return conn.execute(
        f"SELECT COUNT(DISTINCT e.kullanici_id) FROM olay e WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks}",
        [bas, bit, *kp],
    ).fetchone()[0]


def ozet(conn: sqlite3.Connection, f: Filtre) -> dict:
    bugun = zaman.simdi().date()
    def iso(n: int) -> str:
        return (bugun - timedelta(days=n)).isoformat()

    kayit = {
        r[0]: r[1]
        for r in conn.execute("SELECT rol, COUNT(*) FROM kullanici WHERE aktif = 1 GROUP BY rol")
    }
    ks, kp = _kullanici_kosulu(conn, f)
    aktif_rol = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT e.rol, COUNT(DISTINCT e.kullanici_id) FROM olay e"
            f" WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks} GROUP BY e.rol",
            [f.bas, f.bit, *kp],
        )
    }
    return {
        "cevrimici": cevrimici(conn, f),
        "bugun": _aktif(conn, f, iso(0), iso(0)),
        "hafta": _aktif(conn, f, iso(6), iso(0)),
        "ay": _aktif(conn, f, iso(29), iso(0)),
        "kayitli": kayit,
        "aktif_rol": aktif_rol,
    }


def gunluk(conn: sqlite3.Connection, f: Filtre) -> list[dict]:
    """Seçili aralığın her günü için farklı aktif kullanıcı; veri başlangıcından önceki günler None."""
    ilk = veri_baslangici(conn)
    ks, kp = _kullanici_kosulu(conn, f)
    sayilar: dict[tuple[str, str], int] = {}
    for gun, rol, n in conn.execute(
        "SELECT e.gun, e.rol, COUNT(DISTINCT e.kullanici_id) FROM olay e"
        f" WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks} GROUP BY e.gun, e.rol",
        [f.bas, f.bit, *kp],
    ):
        sayilar[(gun, rol)] = n
    toplam = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT e.gun, COUNT(DISTINCT e.kullanici_id) FROM olay e"
            f" WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks} GROUP BY e.gun",
            [f.bas, f.bit, *kp],
        )
    }
    cikti, g, son = [], _gun(f.bas), _gun(f.bit)
    while g <= son:
        s = g.isoformat()
        veri = ilk is not None and s >= ilk
        cikti.append(
            {
                "gun": s,
                "n": toplam.get(s, 0) if veri else None,
                "roller": {r: sayilar.get((s, r), 0) for r in ("ogrenci", "ogretmen", "veli", "yonetici")} if veri else None,
            }
        )
        g += timedelta(days=1)
    return cikti


def haftanin_gunu(gunluk_liste: list[dict]) -> list[dict]:
    """Verisi olan günlerde, haftanın her günü için ortalama günlük aktif kullanıcı."""
    adlar = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    topla = [[0, 0] for _ in range(7)]
    for d in gunluk_liste:
        if d["n"] is None:
            continue
        w = _gun(d["gun"]).weekday()
        topla[w][0] += d["n"]
        topla[w][1] += 1
    return [{"ad": adlar[i], "ort": (t[0] / t[1]) if t[1] else None, "gun_sayisi": t[1]} for i, t in enumerate(topla)]


def saat_dagilimi(conn: sqlite3.Connection, f: Filtre) -> list[int]:
    """Her saat dilimi için farklı (kullanıcı, gün, saat) sayısı."""
    ks, kp = _kullanici_kosulu(conn, f)
    saatler = [0] * 24
    for saat, n in conn.execute(
        "SELECT saat, COUNT(*) FROM (SELECT DISTINCT e.kullanici_id, e.gun, e.saat FROM olay e"
        f" WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks}) GROUP BY saat",
        [f.bas, f.bit, *kp],
    ):
        saatler[saat] = n
    return saatler


def _kullanici_gunu(conn, f: Filtre, tur: str, bas: str, bit: str) -> int:
    ks, kp = _kullanici_kosulu(conn, f)
    return conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT e.kullanici_id, e.gun FROM olay e"
        f" WHERE e.tur = ? AND e.gun BETWEEN ? AND ? AND {ks})",
        [tur, bas, bit, *kp],
    ).fetchone()[0]


def _egilim(conn, f: Filtre, tur: str, ilk: str | None) -> dict:
    """Son 14 gün ile ondan önceki 14 günün kullanıcı-günü karşılaştırması."""
    bit = _gun(f.bit)
    s_bas, o_bit, o_bas = bit - timedelta(days=13), bit - timedelta(days=14), bit - timedelta(days=27)
    if ilk is None or ilk > o_bas.isoformat():
        return {"durum": "yetersiz", "mesaj": "28 günlük veri birikmedi"}
    son = _kullanici_gunu(conn, f, tur, s_bas.isoformat(), bit.isoformat())
    onc = _kullanici_gunu(conn, f, tur, o_bas.isoformat(), o_bit.isoformat())
    if son + onc < AZ_VERI:
        return {"durum": "yetersiz", "mesaj": "olay sayısı çok az", "son": son, "onceki": onc}
    if onc == 0:
        return {"durum": "artiyor", "yuzde": None, "son": son, "onceki": onc}
    yuzde = round(100 * (son - onc) / onc)
    durum = "artiyor" if yuzde >= 20 else "azaliyor" if yuzde <= -20 else "sabit"
    return {"durum": durum, "yuzde": yuzde, "son": son, "onceki": onc}


def ozellikler(conn: sqlite3.Connection, f: Filtre) -> list[dict]:
    """Özellik başına: kullanıcı sayısı, ilgili roldeki aktif kullanıcılara oranı, ilk kayıt, eğilim."""
    ilk = veri_baslangici(conn)
    ks, kp = _kullanici_kosulu(conn, f)
    aktif_rol = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT e.rol, COUNT(DISTINCT e.kullanici_id) FROM olay e"
            f" WHERE e.tur = 'aktif' AND e.gun BETWEEN ? AND ? AND {ks} GROUP BY e.rol",
            [f.bas, f.bit, *kp],
        )
    }
    sonuc = []
    for tur, (ad, roller, temel, _oneri) in OZELLIKLER.items():
        kullanan = conn.execute(
            f"SELECT COUNT(DISTINCT e.kullanici_id) FROM olay e WHERE e.tur = ? AND e.gun BETWEEN ? AND ? AND {ks}",
            [tur, f.bas, f.bit, *kp],
        ).fetchone()[0]
        olay_gunu = _kullanici_gunu(conn, f, tur, f.bas, f.bit)
        payda = sum(aktif_rol.get(r, 0) for r in roller)
        ilk_tarih = conn.execute("SELECT MIN(gun) FROM olay WHERE tur = ?", (tur,)).fetchone()[0]
        yeni = conn.execute(
            "SELECT COUNT(*) FROM (SELECT e.kullanici_id, MIN(e.gun) AS g FROM olay e"
            f" WHERE e.tur = ? AND {ks} GROUP BY e.kullanici_id) WHERE g BETWEEN ? AND ?",
            [tur, *kp, f.bas, f.bit],
        ).fetchone()[0]
        sonuc.append(
            {
                "tur": tur,
                "ad": ad,
                "temel": temel,
                "kullanan": kullanan,
                "olay_gunu": olay_gunu,
                "payda": payda,
                "oran": round(100 * min(kullanan, payda) / payda) if payda else None,
                "ilk_tarih": ilk_tarih,
                "yeni_kullanici": yeni,
                "egilim": _egilim(conn, f, tur, ilk),
            }
        )
    return sonuc


def oturum_terk(conn: sqlite3.Connection, f: Filtre) -> dict:
    """Aralıkta giriş yapan oturumlardan, giriş sonrası hiç temel işlem kaydı olmayanların oranı;
    ayrıca ana sayfayı açıp temel işlem yapmayan oturum-günü oranı. Oturum = giriş yapılan cihaz oturumu."""
    ks, kp = _kullanici_kosulu(conn, f)
    yer = ",".join("?" * len(TEMEL_ISLEMLER))
    giris = conn.execute(
        f"SELECT COUNT(*), SUM(NOT EXISTS (SELECT 1 FROM olay t WHERE t.oturum_k = e.oturum_k"
        f" AND t.tur IN ({yer}))) FROM olay e WHERE e.tur = 'giris' AND e.oturum_k != ''"
        f" AND e.gun BETWEEN ? AND ? AND {ks}",
        [*TEMEL_ISLEMLER, f.bas, f.bit, *kp],
    ).fetchone()
    gunler = conn.execute(
        f"SELECT COUNT(*), SUM(NOT EXISTS (SELECT 1 FROM olay t WHERE t.oturum_k = e.oturum_k AND t.gun = e.gun"
        f" AND t.tur IN ({yer}))) FROM (SELECT DISTINCT kullanici_id, rol, oturum_k, gun FROM olay"
        f" WHERE tur = 'ana_sayfa' AND oturum_k != '') e WHERE e.gun BETWEEN ? AND ? AND {ks}",
        [*TEMEL_ISLEMLER, f.bas, f.bit, *kp],
    ).fetchone()

    def oran(n, bos):
        return None if not n or n < AZ_VERI else round(100 * (bos or 0) / n)

    return {
        "giris": giris[0],
        "giris_bos": giris[1] or 0,
        "giris_oran": oran(giris[0], giris[1]),
        "gun": gunler[0],
        "gun_bos": gunler[1] or 0,
        "gun_oran": oran(gunler[0], gunler[1]),
    }


def oneriler(ozet_: dict, liste: list[dict], terk: dict) -> list[str]:
    """Kural tabanlı öneriler. Yeterli veri yoksa üretilmez; kesin hüküm değil, yön gösterir."""
    cikti = []
    for o in liste:
        if o["payda"] < AZ_VERI:
            continue
        mesaj = OZELLIKLER[o["tur"]][3]
        if mesaj and o["oran"] is not None and o["oran"] < 20:
            cikti.append(f"{o['ad']} yalnızca %{o['oran']} oranında kullanılıyor. {mesaj}")
        elif mesaj and o["egilim"]["durum"] == "azaliyor":
            cikti.append(f"{o['ad']} kullanımı son 14 günde %{abs(o['egilim']['yuzde'])} azaldı. {mesaj}")
    if terk["giris_oran"] is not None and terk["giris_oran"] >= 40:
        cikti.append(
            f"Giriş yapan oturumların %{terk['giris_oran']}'i hiçbir temel işlem yapmadı: "
            "ana sayfada 'şimdi yap' kısayollarını (bekleyen ödev, maraton) öne çıkar."
        )
    return cikti
