"""Acil durum: öğretmen/yönetici okul portalından alarm başlatır (2 adımlı onay + şifre) ve birbirine konum gönderir.

Alarmın kendisi (zil, SMS, tahta ekranı) tahtayoklama dashboard'unda çalışır; burası onay akışını, kullanıcı izini
ve diğer personele bildirimi yönetir. Tatbikat/gerçek ayrımı dashboard'daki `tahta_alarm_tatbikat` ayarını izler.
Konum yalnızca öğretmen+yönetici görür, adlı, 24 saat sonra silinir; push'a konum/ad konmaz (sabit şablon).
"""

import hashlib
import hmac
import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta

import db
import push
import yetki
import zaman
from kaynaklar import KaynakHatasi
from kaynaklar import acil as dis

log = logging.getLogger("okul.acil")

ROLLER = ("ogretmen", "yonetici")
JETON_SURESI = 60  # sn: 1. onaydan 2. onaya
AKTIF_SAAT = 12  # bu süreden eski alarm aktif sayılmaz (kapatılmamış olsa bile)
KONUM_SAKLAMA_SAAT = 24
KONUM_DAKIKA_AZAMI = 3
KONUM_PUSH_ARALIK_DK = 3
TEMIZLIK_ARALIK = timedelta(hours=1)
UST_KAT = {"9-A", "9-B", "10-A", "12-B"}  # dashboard acil.UST_KAT ile aynı (okul 2 katlı)
SABIT_YERLER = ("Bahçe / toplanma alanı", "Giriş katı koridor", "Üst kat koridor", "Müdür odası", "Öğretmenler odası")

# anahtarlar dashboard acil.TURLER ile aynı; "sms" ≤160 kr (ad+yer ile birlikte kırpılır)
TURLER = {
    "kilit": {
        "ad": "Kilit-kapı", "alarm": True,
        "etki": "Okul sireni ve anonsu çalar, tahta ekranları kilit-kapı talimatına geçer, personele SMS gider.",
        "sms": "Kilit-kapı başladı. Sınıfta kalın, kapıyı kilitleyin, müdüre durum bildirin.",
    },
    "tahliye": {
        "ad": "Tahliye", "alarm": True,
        "etki": "Okul sireni ve anonsu çalar, tahta ekranları tahliye talimatına geçer, personele SMS gider.",
        "sms": "Tahliye başladı. Öğrencilerle toplanma noktasına gidin, yoklama alıp bildirin.",
    },
    "deprem": {
        "ad": "Deprem", "alarm": True,
        "etki": "Okul sireni ve anonsu çalar, tahta ekranları deprem talimatına geçer, personele SMS gider.",
        "sms": "Deprem. Çök-kapan-tutun; sarsıntı bitince öğrencilerle toplanma alanına çıkın.",
    },
    "yangin": {
        "ad": "Yangın", "alarm": True,
        "etki": "Okul sireni ve anonsu çalar, tahta ekranları yangın talimatına geçer, personele SMS gider.",
        "sms": "Yangın alarmı. Öğrencileri en yakın çıkıştan tahliye edin, toplanma noktasında bildirin.",
    },
    "gecti": {
        "ad": "Tehlike geçti", "alarm": False,
        "etki": "Tahta ekranlarına 'Tehlike geçti' mesajı gider, personele SMS gider; aktif alarm kapanır.",
        "sms": "Tehlike geçti. Yetkililerin yönlendirmesini bekleyin.",
    },
    "yanlis_alarm": {
        "ad": "Yanlış alarm", "alarm": False,
        "etki": "Siren/anons durdurulur, tahta ekranları kapanır, personele 'yanlış alarm' SMS'i gider; aktif alarm kapanır.",
        "sms": "",
    },
}
ALARM_TURLERI = tuple(t for t, v in TURLER.items() if v["alarm"])
KAPATAN_TURLER = ("gecti", "yanlis_alarm")

_son_temizlik: datetime | None = None


class AcilHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


# --- yerler ---


def yerler() -> list[str]:
    try:
        from kaynaklar import program

        siniflar = sorted(program._siniflar())
    except KaynakHatasi:
        siniflar = []
    return [*(f"{s} sınıfı" for s in siniflar), *SABIT_YERLER]


def yer_adi(yer: str) -> str:
    """Listedeki sınıf yerlerine kat bilgisi ekler; listede olmayan değer reddedilir ('' = belirtilmedi)."""
    yer = (yer or "").strip()
    if not yer:
        return ""
    if yer not in yerler():
        raise AcilHatasi("Geçersiz yer.")
    if yer.endswith(" sınıfı"):
        sinif = yer[: -len(" sınıfı")]
        return f"{yer} ({'üst kat' if sinif in UST_KAT else 'giriş katı'})"
    return yer


# --- 2 adımlı onay jetonu ---


def _imza(oturum_token: str, kid: int, tur: str, yer: str, bitis: int) -> str:
    return hmac.new(oturum_token.encode(), f"acil|{kid}|{tur}|{yer}|{bitis}".encode(), hashlib.sha256).hexdigest()[:40]


def jeton_uret(oturum_token: str, kid: int, tur: str, yer: str) -> str:
    bitis = int(zaman.simdi().timestamp()) + JETON_SURESI
    return f"{bitis}.{_imza(oturum_token, kid, tur, yer, bitis)}"


def jeton_gecerli(jeton: str, oturum_token: str, kid: int, tur: str, yer: str) -> bool:
    try:
        bitis_s, imza = jeton.split(".", 1)
        bitis = int(bitis_s)
    except ValueError:
        return False
    if bitis < int(zaman.simdi().timestamp()):
        return False
    return hmac.compare_digest(imza, _imza(oturum_token, kid, tur, yer, bitis))


# --- alarm ---


def aktif(conn: sqlite3.Connection) -> dict | None:
    """Kapatılmamış, başarılı, son AKTIF_SAAT içindeki en son alarm (yoksa None)."""
    sinir = (zaman.simdi() - timedelta(hours=AKTIF_SAAT)).strftime(zaman.BICIM)
    yer = ",".join("?" * len(ALARM_TURLERI))
    r = conn.execute(
        f"SELECT o.id, o.tur, o.yer, o.tatbikat, o.olusturma, u.ad_soyad FROM acil_olay o"
        f" JOIN kullanici u ON u.id = o.kullanici_id"
        f" WHERE o.tur IN ({yer}) AND o.basarili = 1 AND o.kapanis IS NULL AND o.olusturma >= ?"
        f" ORDER BY o.id DESC LIMIT 1",
        (*ALARM_TURLERI, sinir),
    ).fetchone()
    if r is None:
        return None
    return {
        "id": r["id"], "tur": r["tur"], "tur_ad": TURLER[r["tur"]]["ad"], "yer": r["yer"] or "",
        "tatbikat": bool(r["tatbikat"]), "ad": r["ad_soyad"], "saat": r["olusturma"][11:16],
    }


def _sms_metni(k: sqlite3.Row, tur: str, yer: str) -> str:
    kim = f"{k['ad_soyad']}{f' ({yer})' if yer else ''}"
    return f"ACİL: {kim} bildirdi. {TURLER[tur]['sms']}"[:160]


def baslat(conn: sqlite3.Connection, k: sqlite3.Row, tur: str, yer: str, jeton: str) -> dict:
    """Jeton ve şifre rotada doğrulanmıştır. Jeton hash'i önce yazılır (UNIQUE): çift tıklama/tekrar oynatma ikinci alarm üretmez."""
    if tur not in TURLER:
        raise AcilHatasi("Geçersiz tür.")
    simdi = zaman.simdi_str()
    try:
        cur = conn.execute(
            "INSERT INTO acil_olay (kullanici_id, tur, yer, jeton, olusturma) VALUES (?, ?, ?, ?, ?)",
            (k["id"], tur, yer or None, hashlib.sha256(jeton.encode()).hexdigest(), simdi),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise AcilHatasi("Bu onay daha önce kullanılmış.") from e
    olay_id = cur.lastrowid
    kaynak = f"okul:{k['id']}:{k['ad_soyad']}"[:40]
    try:
        sonuc = (
            dis.yanlis_alarm(kaynak) if tur == "yanlis_alarm" else dis.tetikle(tur, kaynak, _sms_metni(k, tur, yer))
        )
    except KaynakHatasi as e:
        conn.execute("UPDATE acil_olay SET sonuc_json = ? WHERE id = ?", (json.dumps({"hata": str(e)}, ensure_ascii=False), olay_id))
        conn.commit()
        raise AcilHatasi(str(e), 502) from e
    conn.execute(
        "UPDATE acil_olay SET basarili = 1, tatbikat = ?, sonuc_json = ? WHERE id = ?",
        (1 if sonuc.get("tatbikat") else 0, json.dumps(_ozet(sonuc), ensure_ascii=False), olay_id),
    )
    if tur in KAPATAN_TURLER:
        conn.execute(
            f"UPDATE acil_olay SET kapanis = ? WHERE kapanis IS NULL AND tur IN ({','.join('?' * len(ALARM_TURLERI))}) AND id != ?",
            (simdi, *ALARM_TURLERI, olay_id),
        )
    conn.commit()
    yetki.erisim_kaydet(conn, k, f"acil:{tur}", None, None)
    return {"olay_id": olay_id, "tatbikat": bool(sonuc.get("tatbikat")), "kanallar": sonuc.get("kanallar", [])}


def _ozet(sonuc: dict) -> dict:
    return {
        "tatbikat": bool(sonuc.get("tatbikat")),
        "kanallar": [{"kanal": c.get("kanal"), "basarili": bool(c.get("basarili"))} for c in sonuc.get("kanallar", [])],
        "tahtalar": [{"tahta": t.get("tahta"), "basarili": bool(t.get("basarili"))} for t in sonuc.get("tahtalar", [])],
    }


# --- konum ---


def _temizle_gerekirse(conn: sqlite3.Connection) -> None:
    global _son_temizlik
    simdi = zaman.simdi()
    if _son_temizlik is None or simdi - _son_temizlik >= TEMIZLIK_ARALIK:
        _son_temizlik = simdi
        temizle(conn)


def _konum_esigi() -> str:
    return (zaman.simdi() - timedelta(hours=KONUM_SAKLAMA_SAAT)).strftime(zaman.BICIM)


def temizle(conn: sqlite3.Connection) -> int:
    n = conn.execute("DELETE FROM acil_konum WHERE olusturma < ?", (_konum_esigi(),)).rowcount
    conn.commit()
    return n


def baslangic_temizligi() -> None:
    try:
        conn = db.baglanti()
        try:
            temizle(conn)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("acil konum temizliği yapılamadı: %s", type(e).__name__)


def _sayi(deger, alt: float, ust: float, ad: str) -> float | None:
    if deger in (None, ""):
        return None
    try:
        f = float(str(deger).replace(",", "."))
    except ValueError as e:
        raise AcilHatasi(f"Geçersiz {ad}.") from e
    if math.isnan(f) or not (alt <= f <= ust):
        raise AcilHatasi(f"Geçersiz {ad}.")
    return f


def konum_ekle(
    conn: sqlite3.Connection, k: sqlite3.Row, yer: str, enlem="", boylam="", dogruluk=""
) -> tuple[int, bool]:
    """(kayıt id, push gitmeli mi). Yer zorunlu; GPS isteğe bağlı ama enlem+boylam birlikte."""
    ad = yer_adi(yer)
    if not ad:
        raise AcilHatasi("Yerini seç.")
    e, b, d = _sayi(enlem, -90, 90, "enlem"), _sayi(boylam, -180, 180, "boylam"), _sayi(dogruluk, 0, 5000, "doğruluk")
    if (e is None) != (b is None):
        raise AcilHatasi("Enlem ve boylam birlikte gönderilmeli.")
    if e is None:
        d = None
    dk = (zaman.simdi() - timedelta(minutes=1)).strftime(zaman.BICIM)
    if conn.execute("SELECT COUNT(*) FROM acil_konum WHERE kullanici_id = ? AND olusturma >= ?", (k["id"], dk)).fetchone()[0] >= KONUM_DAKIKA_AZAMI:
        raise AcilHatasi("Çok sık konum gönderiyorsun; biraz bekle.", 429)
    push_aralik = (zaman.simdi() - timedelta(minutes=KONUM_PUSH_ARALIK_DK)).strftime(zaman.BICIM)
    bildir = (
        conn.execute("SELECT COUNT(*) FROM acil_konum WHERE kullanici_id = ? AND olusturma >= ?", (k["id"], push_aralik)).fetchone()[0] == 0
    )
    cur = conn.execute(
        "INSERT INTO acil_konum (kullanici_id, yer, enlem, boylam, dogruluk_m, olusturma) VALUES (?, ?, ?, ?, ?, ?)",
        (k["id"], ad, e, b, d, zaman.simdi_str()),
    )
    conn.commit()
    _temizle_gerekirse(conn)
    return cur.lastrowid, bildir


def konumlar(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Son 24 saatin konumları, her kullanıcının yalnızca en yenisi (en yeni önce). Süresi dolan hiç dönmez."""
    sonuc = []
    for r in conn.execute(
        "SELECT c.*, u.ad_soyad, u.rol FROM acil_konum c JOIN kullanici u ON u.id = c.kullanici_id"
        " WHERE c.olusturma >= ? AND c.id = (SELECT MAX(id) FROM acil_konum WHERE kullanici_id = c.kullanici_id)"
        " ORDER BY c.id DESC LIMIT ?",
        (_konum_esigi(), limit),
    ):
        d = {k: r[k] for k in ("id", "yer", "enlem", "boylam", "dogruluk_m", "ad_soyad", "rol")}
        d["zaman"] = r["olusturma"][11:16]
        d["harita"] = f"https://www.google.com/maps?q={r['enlem']},{r['boylam']}" if r["enlem"] is not None else ""
        sonuc.append(d)
    return sonuc


# --- bildirim (push, sabit şablon) ---


def bildirim_alicilari(conn: sqlite3.Connection, haric_id: int) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT u.id FROM kullanici u JOIN push_abonelik p ON p.kullanici_id = u.id"
            " WHERE u.aktif = 1 AND u.rol IN ('ogretmen', 'yonetici') AND u.id != ?",
            (haric_id,),
        )
    ]


def bildir(haric_id: int) -> None:
    """Arka plan görevi: kendi bağlantısını açar, asla istisna fırlatmaz."""
    if not push.etkin_mi():
        return
    try:
        conn = db.baglanti()
        try:
            push.gonder(conn, bildirim_alicilari(conn, haric_id), "acil")
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("acil bildirimi hatası: %s", type(e).__name__)
