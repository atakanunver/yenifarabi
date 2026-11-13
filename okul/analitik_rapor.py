"""Yönetici kullanım analitiği için yapay zekâ raporu.

Model: yerel Ollama `farabi` takma adı (qwen3.8:27b); bulut YOK. Modele yalnızca toplu sayılar gider (kişi adı, mesaj
metni, IP yok); kutu geri bildirimlerinin yalnızca ilk 100 karakteri kısa alıntı olarak eklenir (yalnız yönetici görür).
Rapor `AYAR.rapor_yolu` JSON dosyasında tutulur (DB göçü yok); panel son raporu gösterir, düğme üretimi arka planda başlatır."""

import json
import re
import sqlite3
import subprocess
import threading
import urllib.request
from collections import Counter
from datetime import date, timedelta

import analitik
import db
import zaman
from ayarlar import AYAR
from kaynaklar import zil

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "farabi"  # takma ad: model değişimi `ollama cp` ile; num_ctx gönderilmez (yeniden yükletir)
LLM_ZAMAN_ASIMI = 300
ROLLER = ("ogrenci", "veli", "ogretmen", "yonetici")
LOG_GUN = 7

SISTEM = (
    "Sen bir okul portalının kullanım verisini yorumlayan analistsin. Kurallar: 1) Yalnızca verilen sayılara dayan; "
    "veride olmayan rakam, neden ya da olay uydurma; bir sayının nedenini bilmiyorsan 'nedeni verilerden anlaşılmıyor' de, "
    "sorunun kaynağını tahmin etme. Yüzdeyi yalnızca veride verilmişse yaz, kendin hesaplama. 2) Kişi adı yazma. 3) Düz Türkçe metin yaz, markdown "
    "(*, #, **) KULLANMA; bölüm başlığı büyük harfli ayrı satır, maddeler satır başında '- ' ile. 4) Bölümler sırayla: "
    "KULLANIM (öğrenci, veli, öğretmen ayrı maddeler), KARŞILAŞTIRMA, GERİ DÖNÜŞ VE BİLDİRİMLER, HATA VE SORUNLAR, "
    "ÖNERİLER (en çok 5, somut). 5) Bot taramalarından kaynaklı 404'leri sorun sayma. 6) Veri yetersizse bunu açıkça söyle. "
    "7) KARŞILAŞTIRMA: 'onceki_rapor' varsa giriş oranı, ödev veren öğretmen, teslim oranı ve bildirim abonesi sayılarını "
    "rol rol 'önceki → şimdi' biçiminde yan yana yaz (ör. 21 → 25), farkı kendin hesaplama; yoksa 'Karşılaştırma için önceki "
    "rapor yok.' yaz. 8) 'kullanilmayan_ozellikler' için 'icerik_sayilari'na bak: içerik 0 ise sorun kullanıcı ilgisi değil, "
    "içeriğin hiç yüklenmemesi ya da öğretmen/yöneticinin hiç başlatmamasıdır; öneriyi o tarafa yönelt. 9) Günlük aktifte "
    "düşüş varsa o günün 'tatil' alanına bak; tatil ya da hafta sonu değilse nedeni bilinmiyor de. 'yaklasan_tatiller' varsa "
    "öğrencilere yönelik tatil önerisi verebilirsin. 10) Teslim tarihi geçmiş ödev varken "
    "'otomatik_hatirlatma_gonderilen_odev' 0 ise otomatik ödev hatırlatmasının çalışmıyor olabileceğini HATA VE SORUNLAR'da yaz."
)
OLCUTLER = ("aralik", "giris_orani_yuzde_rol", "odev", "push_abonelik", "aktif_kullanici")  # sonraki rapor karşılaştırması için saklanır

_calisiyor = threading.Lock()
_son_hata = ""


def _log_ozeti() -> dict | None:
    """Son LOG_GUN günün servis logundan yalnızca sayaçlar (yol/IP/mesaj yok). journalctl yoksa/başarısızsa None."""
    try:
        cikti = subprocess.run(
            ["journalctl", "-u", "farabi-okul.service", "--since", f"{LOG_GUN} days ago", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    kodlar: Counter = Counter()
    giris = Counter()
    for m in re.finditer(r'"([A-Z]+) (\S+) HTTP/[\d.]+" (\d{3})', cikti):
        kodlar[m.group(3)] += 1
        if m.group(1) == "POST" and m.group(2) == "/giris" and m.group(3) in ("401", "429"):
            giris[m.group(3)] += 1
    return {
        "gun": LOG_GUN,
        "durum_kodlari": dict(kodlar.most_common(8)),
        "sunucu_hatasi_5xx": sum(n for k, n in kodlar.items() if k.startswith("5")),
        "beklenmeyen_hata": cikti.count("Beklenmeyen hata"),
        "giris_basarisiz_401": giris["401"],
        "giris_hiz_siniri_429": giris["429"],
    }


def _terk(t: dict) -> dict:
    """Ham anahtarlar modele belirsiz geliyordu; açık adlarla ver."""
    return {
        "giris_yapan_oturum": t["giris"],
        "giristen_sonra_hicbir_islem_yapmayan_oturum": t["giris_bos"],
        "ana_sayfayi_acip_islem_yapmayan_oturum_gunu": t["gun_bos"],
        "ana_sayfayi_acan_oturum_gunu": t["gun"],
    }


def topla(conn: sqlite3.Connection) -> dict:
    """Modele gidecek toplu veri (son 30 gün)."""
    f = analitik.filtre_coz(conn, "", "", None, None, None, ROLLER)
    ozet = analitik.ozet(conn, f)
    gunler = analitik.gunluk(conn, f)
    gunluk = [d["n"] for d in gunler if d["n"] is not None]
    ozl = analitik.ozellikler(conn, f)
    oz = [
        {"ad": o["ad"], "kullanan": o["kullanan"], "oran_yuzde": o["oran"], "egilim": o["egilim"]["durum"]}
        for o in ozl
        if o["kullanan"]
    ]
    giris_yapan = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT k.rol, COUNT(DISTINCT o.kullanici_id) FROM oturum o JOIN kullanici k ON k.id = o.kullanici_id"
            " WHERE k.aktif = 1 GROUP BY k.rol"
        )
    }
    sifresiz = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT rol, SUM(sifre_degismeli) FROM kullanici WHERE aktif = 1 AND sifre_degismeli = 1 GROUP BY rol"
        )
    }
    bildirim = [
        dict(r)
        for r in conn.execute(
            "SELECT tur, kaynak, COUNT(*) AS n, COUNT(DISTINCT soru_id) AS soru FROM soru_bildirim"
            " WHERE iptal = 0 AND kaynak != 'yonetici-toplu' AND substr(zaman, 1, 10) BETWEEN ? AND ?"
            " GROUP BY tur, kaynak",  # 'yonetici-toplu' = yöneticinin toplu karantina işareti, kullanıcı geri bildirimi değil
            (f.bas, f.bit),
        )
    ]
    kutu = [
        {"tur": r["tur"], "durum": r["durum"], "alinti": r["metin"][:100]}
        for r in conn.execute(
            "SELECT tur, durum, metin FROM kutu_kayit WHERE substr(olusturma, 1, 10) BETWEEN ? AND ?"
            " ORDER BY id DESC LIMIT 10",
            (f.bas, f.bit),
        )
    ]
    push = conn.execute("SELECT COUNT(*), COALESCE(SUM(hata_sayisi > 0), 0) FROM push_abonelik").fetchone()
    abone_rol = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT k.rol, COUNT(DISTINCT p.kullanici_id) FROM push_abonelik p JOIN kullanici k ON k.id = p.kullanici_id"
            " WHERE k.aktif = 1 GROUP BY k.rol"
        )
    }
    kayitli = ozet["kayitli"]
    return {
        "aralik": [f.bas, f.bit],
        "kayitli": kayitli,
        "aktif_son_30_gun_rol": ozet["aktif_rol"],
        "aktif_kullanici": {"bugun": ozet["bugun"], "son_7_gun": ozet["hafta"], "son_30_gun": ozet["ay"]},
        "gunluk_aktif_min_maks": [min(gunluk), max(gunluk)] if gunluk else None,
        "gunluk_aktif_son_14_gun": _son_gunler(gunler),
        "yaklasan_tatiller": _yaklasan_tatiller(),
        "oturum_acan_rol": giris_yapan,
        "giris_orani_yuzde_rol": {r: _oran(giris_yapan.get(r, 0), n) for r, n in kayitli.items()},
        "ilk_sifresini_degistirmeyen_rol": sifresiz,
        "ozellikler": oz,
        "kullanilmayan_ozellikler": [o["ad"] for o in ozl if not o["kullanan"]],
        "icerik_sayilari": _icerik(conn, f),
        "odev": _odev(conn, f, kayitli.get("ogretmen", 0)),
        "oturum_terk": _terk(analitik.oturum_terk(conn, f)),
        "soru_bildirimleri": bildirim,
        "kutu_son": kutu,
        "push_abonelik": {
            "toplam_cihaz": push[0],
            "hatali": push[1],
            "abone_kisi_rol": abone_rol,
            "abone_orani_yuzde_rol": {r: _oran(abone_rol.get(r, 0), n) for r, n in kayitli.items()},
        },
        "servis_logu": _log_ozeti(),
    }


def _oran(pay: int, payda: int) -> int | None:
    return round(100 * pay / payda) if payda else None


def _son_gunler(gunluk: list[dict], n: int = 14) -> list[dict]:
    """Son n günün aktif sayısı + okul günü değilse nedeni (hafta sonu/tatil); düşüşler tatille karıştırılmasın."""
    return [
        {"gun": d["gun"], "aktif": d["n"], "tatil": zil.tatil_adi(date.fromisoformat(d["gun"]))}
        for d in gunluk[-n:]
        if d["n"] is not None
    ]


def _yaklasan_tatiller(gun: int = 21) -> list[dict]:
    """Önümüzdeki `gun` gün içindeki tatiller (hafta sonu hariç), ilk günleriyle."""
    bugun, sonuc = zaman.simdi().date(), {}
    for i in range(1, gun + 1):
        g = bugun + timedelta(days=i)
        ad = zil.tatil_adi(g)
        if ad and ad != "Hafta sonu":
            sonuc.setdefault(ad, g.isoformat())
    return [{"ad": ad, "baslangic": g} for ad, g in sonuc.items()]


def _icerik(conn: sqlite3.Connection, f) -> dict:
    """Öğretmen/yöneticinin başlattığı ya da yüklenmesi gereken içerik; 0 = kullanıcı ilgisizliği değil, içerik yok."""
    def say(sql: str, *p) -> int:
        return conn.execute(sql, p).fetchone()[0]

    return {
        "bilmece_havuzu_aktif": say("SELECT COUNT(*) FROM bilmece WHERE aktif = 1"),
        "olusturulan_anket_toplam": say("SELECT COUNT(*) FROM anket"),
        "olusturulan_veli_onay_talebi_toplam": say("SELECT COUNT(*) FROM onay_talep"),
        "ogretmen_tesekkur_karti_toplam": say("SELECT COUNT(*) FROM tesekkur"),
        "duyuru_yazar_rol": {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT k.rol, COUNT(*) FROM duyuru d JOIN kullanici k ON k.id = d.yazar_id"
                " WHERE substr(d.yayin, 1, 10) BETWEEN ? AND ? GROUP BY k.rol",
                (f.bas, f.bit),
            )
        },
    }


def _odev(conn: sqlite3.Connection, f, ogretmen_sayisi: int) -> dict:
    """Aralıkta verilen ödev + veren öğretmen; teslim oranı yalnız teslim tarihi aralıkta geçmiş ödevlerden."""
    verilen, veren = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT ogretmen_id) FROM odev WHERE substr(olusturma, 1, 10) BETWEEN ? AND ?",
        (f.bas, f.bit),
    ).fetchone()
    suresi_dolan, beklenen, teslim = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM((SELECT COUNT(*) FROM ogrenci g WHERE g.sinif = o.sinif)), 0),"
        " COALESCE(SUM((SELECT COUNT(*) FROM odev_teslim t WHERE t.odev_id = o.id)), 0)"
        " FROM odev o WHERE substr(o.teslim, 1, 10) BETWEEN ? AND ? AND substr(o.teslim, 1, 10) < ?",
        (f.bas, f.bit, zaman.simdi().date().isoformat()),
    ).fetchone()
    return {
        "verilen_odev": verilen,
        "odev_veren_ogretmen": veren,
        "kayitli_ogretmen": ogretmen_sayisi,
        "teslim_tarihi_gecmis_odev": suresi_dolan,
        "beklenen_teslim_sinif_mevcudu_toplami": beklenen,
        "yapilan_teslim": teslim,
        "teslim_orani_yuzde": _oran(teslim, beklenen),
        "otomatik_hatirlatma_gonderilen_odev": conn.execute(  # odev_uyari.py (saatlik timer); 0 = timer çalışmıyor olabilir
            "SELECT COUNT(*) FROM odev_uyari WHERE substr(zaman, 1, 10) BETWEEN ? AND ?", (f.bas, f.bit)
        ).fetchone()[0],
        "ogretmen_elle_hatirlatma": conn.execute(
            "SELECT COUNT(*) FROM odev_hatirlatma WHERE substr(gun, 1, 10) BETWEEN ? AND ?", (f.bas, f.bit)
        ).fetchone()[0],
    }


def istem(veri: dict) -> str:
    return "Aşağıdaki JSON okul portalının kullanım verisidir. Kurallara uyarak rapor yaz.\n\n" + json.dumps(
        veri, ensure_ascii=False, indent=1
    )


def _llm(sistem: str, kullanici: str) -> str:
    govde = json.dumps(
        {
            "model": MODEL,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}],
        }
    ).encode()
    istek = urllib.request.Request(OLLAMA_URL, govde, {"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=LLM_ZAMAN_ASIMI) as y:
        return json.loads(y.read())["message"]["content"].strip()


def uret(conn: sqlite3.Connection) -> dict:
    veri = topla(conn)
    onceki = oku()
    if onceki and onceki.get("olcutler"):
        veri["onceki_rapor"] = {"zaman": onceki["zaman"], "olcutler": onceki["olcutler"]}
    metin = _llm(SISTEM, istem(veri))
    if not metin:
        raise ValueError("Model boş yanıt döndürdü")
    return {
        "zaman": zaman.simdi_str(),
        "aralik": veri["aralik"],
        "model": MODEL,
        "metin": metin,
        "olcutler": {k: veri[k] for k in OLCUTLER},
    }


def oku() -> dict | None:
    try:
        return json.loads(AYAR.rapor_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _yaz(rapor: dict) -> None:
    AYAR.rapor_yolu.parent.mkdir(parents=True, exist_ok=True)
    gecici = AYAR.rapor_yolu.with_name(AYAR.rapor_yolu.name + ".tmp")
    gecici.write_text(json.dumps(rapor, ensure_ascii=False), encoding="utf-8")
    gecici.replace(AYAR.rapor_yolu)


def calisiyor() -> bool:
    return _calisiyor.locked()


def son_hata() -> str:
    return _son_hata


def uret_ve_kaydet() -> bool:
    """Arka plan görevi: kendi DB bağlantısıyla üretir, hatada eski raporu korur. Zaten çalışıyorsa False."""
    global _son_hata
    if not _calisiyor.acquire(blocking=False):
        return False
    try:
        conn = db.baglanti()
        try:
            analitik.bosalt()
            _yaz(uret(conn))
            _son_hata = ""
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — arka plan görevi; hata panelde kısa metin olarak gösterilir
        _son_hata = f"{type(e).__name__}: {e}"[:200]
    finally:
        _calisiyor.release()
    return True
