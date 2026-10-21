"""Yollar ve ayarlar. Testler AYAR alanlarını monkeypatch.setattr ile değiştirir."""

import json
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parent
FARABI = KOK.parent


@dataclass
class Ayarlar:
    db_yolu: Path = KOK / "veri" / "okul.db"
    dosya_dizini: Path = KOK / "veri" / "dosyalar"  # foto/plan — static DEĞİL, yetkili rotalardan sunulur
    pano_db_yolu: Path = field(
        default=FARABI / "tahtayoklama" / "dashboard" / "veri" / "yoklama_pano.db"
    )
    program_yolu: Path = FARABI / "mudur" / "ders_programi.json"
    zil_yolu: Path = FARABI / "tahtayoklama" / "data" / "zil.json"
    takvim_yolu: Path = KOK / "config" / "takvim.json"
    kanallar_yolu: Path = KOK / "config" / "kanallar.json"  # okulun dijital kanalları (alt şerit); dosya yoksa şerit gizli
    kazanim_yolu: Path = field(
        default=FARABI / "tahtayoklama" / "data" / "kazanimlar.json"
    )
    havuz_db: str = "soru_havuzu"
    sms_url: str = "http://127.0.0.1:8020/api/arac/kod-sms"
    sms_anahtar: str = ""
    kazanim_esik: float = 0.7
    # Acil durum: dashboard (:80) makine API'si; anahtar config/gizli.json "acil_makine_anahtar" (boşsa butonlar basılamaz)
    acil_url: str = "http://127.0.0.1"
    acil_anahtar: str = ""
    # Web Push (VAPID): config/gizli.json; boşsa bildirim özelliği kapalı (push.py)
    vapid_ozel: str = ""
    vapid_acik: str = ""
    vapid_konu: str = ""
    # Veli WhatsApp grubu davet bağlantısı: ANAHTAR gibidir (bağlantıyı bilen gruba girer) → yalnızca gizli.json, yalnızca veliye gösterilir
    whatsapp_veli: str = ""
    whatsapp_ogrenci: str = ""
    # soruhavuzu → okul /api/soru-bildirim paylaşılan anahtarı (config/gizli.json "soru_havuzu_anahtar"); boşsa uç kapalı
    soru_anahtar: str = ""
    # EBYS botu (Müdür PC) → /api/duyuru-ekle paylaşılan anahtarı (config/gizli.json "duyuru_anahtar"); boşsa uç kapalı
    duyuru_anahtar: str = ""


def yukle() -> Ayarlar:
    a = Ayarlar()
    gizli = KOK / "config" / "gizli.json"
    if gizli.exists():
        g = json.loads(gizli.read_text(encoding="utf-8"))
        a.sms_anahtar = g.get("sms_arac_anahtar", "")
        a.acil_anahtar = g.get("acil_makine_anahtar", "")
        a.vapid_ozel = g.get("vapid_ozel", "")
        a.vapid_acik = g.get("vapid_acik", "")
        a.vapid_konu = g.get("vapid_konu", "")
        a.whatsapp_veli = g.get("whatsapp_veli", "")
        a.whatsapp_ogrenci = g.get("whatsapp_ogrenci", "")
        a.soru_anahtar = g.get("soru_havuzu_anahtar", "")
        a.duyuru_anahtar = g.get("duyuru_anahtar", "")
    return a


AYAR = yukle()
