#!/usr/bin/env python3
"""
scripts/retry_failed_tavsiye.py
Hatalı kalan 17 SMS'i otomatik yeniden bağlanma (re-login) korumasıyla gönderir.
"""

import sys
import time
import sqlite3
from pathlib import Path

SMSSISTEMI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SMSSISTEMI_DIR))

import sms_gonderici
from gonderim import is_ascii
from huawei_lte_api.Client import Client
from huawei_lte_api.enums.sms import TextModeEnum

DB_YOLU = SMSSISTEMI_DIR / "veri" / "smssistemi.db"
GONDERIM_ID = "deneme_tavsiye_20261102_223858"


def gonder_tekrar():
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()

    c.execute(
        "SELECT id, isim, telefon, mesaj FROM gonderimler WHERE gonderim_id = ? AND durum = 'hata' ORDER BY id",
        (GONDERIM_ID,)
    )
    hatalilar = c.fetchall()
    print(f"Yeniden gönderilecek kayıt sayısı: {len(hatalilar)}")

    if not hatalilar:
        print("Hatalı kayıt bulunamadı.")
        return

    ayarlar = sms_gonderici.modem_ayarlarini_yukle()
    basarili = 0
    hata_sayisi = 0

    client = None
    baglanti = None

    def baglan():
        nonlocal client, baglanti
        if baglanti:
            try:
                baglanti.close()
            except Exception:
                pass
        baglanti = sms_gonderici._baglan(ayarlar)
        client = Client(baglanti)

    baglan()

    for row_id, isim, telefon, mesaj in hatalilar:
        mode = TextModeEnum.SEVEN_BIT if is_ascii(mesaj) else TextModeEnum.UCS2
        gonderildi = False

        for deneme in range(3):
            try:
                client.sms.send_sms([telefon], mesaj, text_mode=mode)
                c.execute(
                    "UPDATE gonderimler SET durum = 'gonderildi', hata_metni = NULL, zaman = CURRENT_TIMESTAMP WHERE id = ?",
                    (row_id,)
                )
                conn.commit()
                basarili += 1
                gonderildi = True
                print(f"[OK] {isim} ({telefon[-4:]}): Gönderildi")
                break
            except Exception as exc:
                print(f"[TEKRAR DENENİYOR {deneme+1}/3] {isim}: {exc}")
                time.sleep(2)
                try:
                    baglan()
                except Exception as baglanti_exc:
                    print(f"Yeniden bağlanma hatası: {baglanti_exc}")

        if not gonderildi:
            hata_sayisi += 1
            print(f"[BAŞARISIZ] {isim} ({telefon[-4:]})")

        time.sleep(2.5)

    try:
        sms_gonderici.giden_kutusunu_temizle(client)
    except Exception:
        pass

    print(f"\nTekrar Gönderim Tamamlandı! Başarılı: {basarili}, Hatalı: {hata_sayisi}")


if __name__ == "__main__":
    gonder_tekrar()
