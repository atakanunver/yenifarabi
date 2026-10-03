"""Tahta yeniden başlatma (sudo gerekir) — uzaktan_yonetim.py'ye KASITLI
olarak girmez: o modül "hiçbir işlem sudo gerektirmez" ilkesiyle yazıldı.
Reboot, tahtadaki `admin` hesabında YALNIZCA `/usr/bin/systemctl reboot`
komutuna izin veren sudoers kuralıyla çalışır; komut o kuralla birebir aynı
olmalı (ek argüman yok).

Yalnızca ajan_api.py (makine API'si) kullanır. Ham stderr/stdout/IP asla
dönmez.
"""

import time
from datetime import datetime

import ssh_istemci
import zil

BEKLEME_SN = 120
_SSH_BAGLANTI_HATASI = 255
_SUDO_KONTROL_KOMUTU = "sudo -n -l /usr/bin/systemctl reboot"
_REBOOT_KOMUTU = "sudo -n /usr/bin/systemctl reboot"
_UYARILAR = {"9-A": "otomatik giriş yok, açılışta giriş ekranında kalır"}

# {tahta adı: monotonic zaman} — süreç belleğinde; servis yeniden başlarsa sıfırlanır.
_SON_ISTEK: dict[str, float] = {}


def ders_saatinde_mi(simdi: datetime | None = None) -> bool:
    """Okul günü ve saat ilk dersin başlangıcı ile son dersin bitişi arasında
    ise True (teneffüsler ve öğle arası DAHİL — simdiki_ders() teneffüste
    None döndüğü için tek başına yetmez). Karşılaştırma İstanbul saatiyle."""
    simdi = simdi or zil.simdi_istanbul()
    if simdi.tzinfo is None:
        simdi = simdi.replace(tzinfo=zil.ISTANBUL)
    else:
        simdi = simdi.astimezone(zil.ISTANBUL)
    ilk = zil.ilk_ders_saati()
    son = zil.son_ders_bitis_saati()
    if ilk is None or son is None or not zil.okul_gunu_mu(simdi.date()):
        return False
    return ilk <= simdi.time().replace(second=0, microsecond=0) < son


def _sonuc(t: dict, basarili: bool, sebep: str) -> dict:
    sonuc = {"tahta": t["ad"], "basarili": basarili, "sebep": sebep}
    if basarili and t["ad"] in _UYARILAR:
        sonuc["uyari"] = _UYARILAR[t["ad"]]
    return sonuc


async def yeniden_baslat_tek(t: dict) -> dict:
    ad = t["ad"]
    if not t.get("admin"):
        return _sonuc(t, False, "izin_yok")

    # Bekleme kontrolü + işaretleme ATOMİK (arada await yok): aynı tahta için
    # eşzamanlı iki istek de ön kontrolü geçip ikinci reboot göndermesin.
    simdi = time.monotonic()
    son = _SON_ISTEK.get(ad)
    if son is not None and simdi - son < BEKLEME_SN:
        return _sonuc(t, False, "bekleme")
    _SON_ISTEK[ad] = simdi

    # Ön kontrol: sudoers kuralı gerçekten var mı? Reboot komutu ÇAĞRILMAZ.
    kontrol = await ssh_istemci.komut_calistir(t["ip"], t["admin"], _SUDO_KONTROL_KOMUTU, zaman_asimi=8)
    if not kontrol.basarili:
        # Başarısız ön kontrol bekleme süresi başlatmaz.
        _SON_ISTEK.pop(ad, None)
        if kontrol.zaman_asimi:
            return _sonuc(t, False, "zaman_asimi")
        if kontrol.cikis_kodu in (None, _SSH_BAGLANTI_HATASI):
            return _sonuc(t, False, "ulasilamadi")
        return _sonuc(t, False, "izin_yok")

    _SON_ISTEK[ad] = time.monotonic()
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["admin"], _REBOOT_KOMUTU, zaman_asimi=10)
    # Reboot başlayınca SSH oturumu kopar → 255 beklenen bir sonuç.
    if sonuc.basarili or sonuc.cikis_kodu == _SSH_BAGLANTI_HATASI:
        return _sonuc(t, True, "tamam")
    if sonuc.zaman_asimi:
        return _sonuc(t, False, "zaman_asimi")
    return _sonuc(t, False, "hata")
