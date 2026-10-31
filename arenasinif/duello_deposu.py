"""duello_deposu.py - Tahta Düellosu öğrenci skorlarını ve maç geçmişini JSON dosyalarında saklar.

Veriler yerel 'veri/duello_skorlar.json' ve sınıf bazında 'veri/duello_skorlar_<sinif>.json'
dosyalarına yazılır. Öğrencilerin kümülatif puanları, oynadıkları maç sayısı,
galibiyet/mağlubiyet/beraberlik sayıları, mevcut ve en yüksek galibiyet serileri
kalıcı olarak tutulur.
"""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("arena.duello_deposu")
BASE_DIR = Path(__file__).resolve().parent
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
_LOCK = threading.Lock()


def veri_dizini() -> Path:
    dizin = Path(os.environ.get("ARENA_VERI_DIZINI") or (BASE_DIR / "veri"))
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


def ana_dosya_yolu() -> Path:
    return veri_dizini() / "duello_skorlar.json"


def sinif_dosya_yolu(sinif: str) -> Path:
    temiz = "".join(c for c in (sinif or "genel") if c.isalnum() or c in "-_")
    return veri_dizini() / f"duello_skorlar_{temiz}.json"


def _guvenli_dosya_yaz(hedef_yol: Path, veri: dict[str, Any]) -> None:
    """Atomik olarak JSON dosyasını diske yazar (.tmp üzerinden)."""
    tmp_yol = hedef_yol.with_suffix(".tmp")
    try:
        with open(tmp_yol, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        os.replace(tmp_yol, hedef_yol)
    except Exception as e:
        if tmp_yol.exists():
            try:
                tmp_yol.unlink()
            except OSError:
                pass
        log.error("JSON skor dosyası yazılamadı (%s): %s", hedef_yol, e)
        raise


def _tum_veriyi_oku() -> dict[str, Any]:
    """Ana JSON dosyasını okur veya boş şablon döner."""
    yol = ana_dosya_yolu()
    if not yol.exists():
        return {"guncelleme": datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds"), "siniflar": {}}
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("JSON skor dosyası okunamadı, sıfırlanıyor: %s", e)
        return {"guncelleme": datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds"), "siniflar": {}}


def skor_kaydet(
    sinif: str,
    ders: str,
    sol_oyuncu: str,
    sol_puan: int,
    sag_oyuncu: str,
    sag_puan: int,
    kazanan: str | None = None,
    seri: int = 0,
    simdi: datetime | None = None,
) -> dict[str, Any]:
    """Bir düello maçının sonucunu JSON dosyalarına işler ve güncel liderlik durumunu döner."""
    if not sol_oyuncu or not sag_oyuncu:
        raise ValueError("Oyuncu isimleri boş olamaz")

    simdi = simdi or datetime.now(ISTANBUL_TZ)
    zaman_damgasi = simdi.isoformat(timespec="seconds")
    sinif_anahtari = (sinif or "9-A").strip()

    # Kazananı belirle
    if kazanan is None:
        if sol_puan > sag_puan:
            kazanan = sol_oyuncu
        elif sag_puan > sol_puan:
            kazanan = sag_oyuncu
        else:
            kazanan = "berabere"

    with _LOCK:
        veri = _tum_veriyi_oku()
        siniflar = veri.setdefault("siniflar", {})
        sinif_verisi = siniflar.setdefault(sinif_anahtari, {"ogrenciler": {}, "mac_gecmisi": []})
        ogrenciler = sinif_verisi.setdefault("ogrenciler", {})
        mac_gecmisi = sinif_verisi.setdefault("mac_gecmisi", [])

        # 1. Sol Oyuncuyu Güncelle
        sol_stats = ogrenciler.setdefault(
            sol_oyuncu,
            {
                "ad": sol_oyuncu,
                "sinif": sinif_anahtari,
                "toplam_puan": 0,
                "oyun_sayisi": 0,
                "galibiyet": 0,
                "maglubiyet": 0,
                "beraberlik": 0,
                "mevcut_seri": 0,
                "en_iyi_seri": 0,
                "dogru_sayisi": 0,
                "son_oyun": zaman_damgasi,
            },
        )
        sol_stats["toplam_puan"] += int(sol_puan)
        sol_stats["oyun_sayisi"] += 1
        sol_stats["dogru_sayisi"] += max(0, int(sol_puan) // 10)
        sol_stats["son_oyun"] = zaman_damgasi

        if kazanan == sol_oyuncu:
            sol_stats["galibiyet"] += 1
            sol_stats["mevcut_seri"] = seri if seri > 0 else (sol_stats.get("mevcut_seri", 0) + 1)
            sol_stats["en_iyi_seri"] = max(sol_stats["en_iyi_seri"], sol_stats["mevcut_seri"])
        elif kazanan == "berabere":
            sol_stats["beraberlik"] += 1
        else:
            sol_stats["maglubiyet"] += 1
            sol_stats["mevcut_seri"] = 0

        # 2. Sağ Oyuncuyu Güncelle
        sag_stats = ogrenciler.setdefault(
            sag_oyuncu,
            {
                "ad": sag_oyuncu,
                "sinif": sinif_anahtari,
                "toplam_puan": 0,
                "oyun_sayisi": 0,
                "galibiyet": 0,
                "maglubiyet": 0,
                "beraberlik": 0,
                "mevcut_seri": 0,
                "en_iyi_seri": 0,
                "dogru_sayisi": 0,
                "son_oyun": zaman_damgasi,
            },
        )
        sag_stats["toplam_puan"] += int(sag_puan)
        sag_stats["oyun_sayisi"] += 1
        sag_stats["dogru_sayisi"] += max(0, int(sag_puan) // 10)
        sag_stats["son_oyun"] = zaman_damgasi

        if kazanan == sag_oyuncu:
            sag_stats["galibiyet"] += 1
            sag_stats["mevcut_seri"] = seri if seri > 0 else (sag_stats.get("mevcut_seri", 0) + 1)
            sag_stats["en_iyi_seri"] = max(sag_stats["en_iyi_seri"], sag_stats["mevcut_seri"])
        elif kazanan == "berabere":
            sag_stats["beraberlik"] += 1
        else:
            sag_stats["maglubiyet"] += 1
            sag_stats["mevcut_seri"] = 0

        # 3. Maç Geçmişine Ekle (son 100 maç saklanır)
        mac_kaydi = {
            "tarih": zaman_damgasi,
            "sinif": sinif_anahtari,
            "ders": ders or "Genel",
            "sol_oyuncu": sol_oyuncu,
            "sol_puan": int(sol_puan),
            "sag_oyuncu": sag_oyuncu,
            "sag_puan": int(sag_puan),
            "kazanan": kazanan,
            "seri": seri,
        }
        mac_gecmisi.insert(0, mac_kaydi)
        if len(mac_gecmisi) > 100:
            mac_gecmisi.pop()

        veri["guncelleme"] = zaman_damgasi

        # 4. JSON Dosyalarını Diske Yaz
        _guvenli_dosya_yaz(ana_dosya_yolu(), veri)

        # Sınıf bazlı özel JSON dosyasını da hazırla
        sinif_liderlik = sorted(
            ogrenciler.values(),
            key=lambda o: (-o["toplam_puan"], -o["galibiyet"], -o["en_iyi_seri"], o["ad"]),
        )
        for i, o in enumerate(sinif_liderlik, 1):
            o["sira"] = i

        sinif_ozel_veri = {
            "sinif": sinif_anahtari,
            "guncelleme": zaman_damgasi,
            "toplam_oyuncu": len(ogrenciler),
            "toplam_mac": len(mac_gecmisi),
            "ogrenciler": sinif_liderlik,
            "son_maclar": mac_gecmisi[:20],
        }
        _guvenli_dosya_yaz(sinif_dosya_yolu(sinif_anahtari), sinif_ozel_veri)

        return {
            "durum": "ok",
            "sinif": sinif_anahtari,
            "sol_oyuncu": sol_stats,
            "sag_oyuncu": sag_stats,
            "kazanan": kazanan,
            "liderlik": sinif_liderlik,
            "son_maclar": mac_gecmisi[:10],
        }


def skorlari_getir(sinif: str | None = None) -> dict[str, Any]:
    """Belirtilen sınıfın (veya tüm sınıfların) skor ve liderlik tablosunu döner."""
    with _LOCK:
        veri = _tum_veriyi_oku()
        siniflar = veri.get("siniflar", {})

        if sinif and sinif in siniflar:
            sinif_verisi = siniflar[sinif]
            ogrenciler = list(sinif_verisi.get("ogrenciler", {}).values())
            liderlik = sorted(
                ogrenciler,
                key=lambda o: (-o.get("toplam_puan", 0), -o.get("galibiyet", 0), -o.get("en_iyi_seri", 0), o["ad"]),
            )
            for i, o in enumerate(liderlik, 1):
                o["sira"] = i
            return {
                "durum": "ok",
                "sinif": sinif,
                "toplam_oyuncu": len(liderlik),
                "liderlik": liderlik,
                "son_maclar": sinif_verisi.get("mac_gecmisi", [])[:15],
            }

        # Sınıf belirtilmemişse veya genel özet
        tum_ogrenciler = []
        for s_ad, s_veri in siniflar.items():
            for o in s_veri.get("ogrenciler", {}).values():
                tum_ogrenciler.append(o)

        genel_liderlik = sorted(
            tum_ogrenciler,
            key=lambda o: (-o.get("toplam_puan", 0), -o.get("galibiyet", 0), -o.get("en_iyi_seri", 0), o["ad"]),
        )
        for i, o in enumerate(genel_liderlik, 1):
            o["sira"] = i

        return {
            "durum": "ok",
            "sinif": sinif or "Tümü",
            "toplam_oyuncu": len(genel_liderlik),
            "liderlik": genel_liderlik[:50],
            "siniflar": list(siniflar.keys()),
        }


def ogrenci_istatistigi(ad: str, sinif: str) -> dict[str, Any] | None:
    """Belirli bir öğrencinin istatistiklerini döner."""
    with _LOCK:
        veri = _tum_veriyi_oku()
        sinif_verisi = veri.get("siniflar", {}).get(sinif or "", {})
        return sinif_verisi.get("ogrenciler", {}).get(ad)


def skorlari_sifirla(sinif: str | None = None) -> bool:
    """İsteğe bağlı olarak belirli bir sınıfın veya tüm sınıfların skorlarını sıfırlar."""
    with _LOCK:
        if sinif:
            veri = _tum_veriyi_oku()
            if sinif in veri.get("siniflar", {}):
                del veri["siniflar"][sinif]
                veri["guncelleme"] = datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds")
                _guvenli_dosya_yaz(ana_dosya_yolu(), veri)
                ozel = sinif_dosya_yolu(sinif)
                if ozel.exists():
                    try:
                        ozel.unlink()
                    except OSError:
                        pass
                return True
            return False

        # Tümü sıfırlanıyor
        veri = {"guncelleme": datetime.now(ISTANBUL_TZ).isoformat(timespec="seconds"), "siniflar": {}}
        _guvenli_dosya_yaz(ana_dosya_yolu(), veri)
        return True
