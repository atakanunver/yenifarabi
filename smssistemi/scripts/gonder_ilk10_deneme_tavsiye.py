#!/usr/bin/env python3
"""
scripts/gonder_ilk10_deneme_tavsiye.py
11 ve 12. Sınıf Son Deneme İlk 10 Öğrenci ve Velilerine Teknik Tavsiye SMS Gönderimi.
"""

import sys
import os
import sqlite3
import threading
from pathlib import Path
from datetime import datetime

SMSSISTEMI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SMSSISTEMI_DIR))

import db
import sms_gonderici

DB_YOLU = SMSSISTEMI_DIR / "veri" / "smssistemi.db"

# 12. Sınıf Öğrenci ve Veli Teknik Metinleri
DATA_12 = [
    {
        "no": 132, "ad": "Irmak Nur Uysal",
        "ogr_txt": "Tr yazim kurallari ve paragraf bolmeyi calis. Matta 5 yanlisi kesmek icin islem kontrolu yap, geometride acilar ve ucgende alana calis.",
        "veli_txt": "Evde haftalik cozdugu mat denemelerindeki yanlis sorularin video cozumlerini izleyip izlemedigini ve geometri tekrarini denetleyin."
    },
    {
        "no": 143, "ad": "Zeynep Koca",
        "ogr_txt": "Trde yazim-noktalama calisip 7 yanlisi kes. Matta rasyonel sayi ve mutlak deger tekrarla. Fende biyoloji ekoloji ve hucreyi bitir.",
        "veli_txt": "Haftada 2 gun 40 soruluk kronometreli Turkce denemesi cozdurun, fende biyoloji konu ozetlerini size sesli anlatmasini saglayin."
    },
    {
        "no": 192, "ad": "Alperen Mevlüt Kılıç",
        "ogr_txt": "Fende 17 bos soru var; biyoloji hucre ve kimya periyodik cetvelden 5 kolay soru sec. Matta ilk 10 konudan gunluk 30 temel soru coz.",
        "veli_txt": "Her aksam fen (biyoloji/kimya) konu tekrari ile matematikten gunluk 30 soru cozum cizelgesini imzalayarak kontrol edin."
    },
    {
        "no": 205, "ad": "Meryem Canöz",
        "ogr_txt": "Trde fiilimsi ve sozcuk yapisi calisip 9 yanlisi sifirla. Matta bilmedigin 6 soruyu isaretleme, sadece emin oldugun ilk 12 konuyu coz.",
        "veli_txt": "Denemede yanlis yaptigi sorulari kestirip 'Hata Defteri'ne yapistirtin; pazar gunleri bu sorulari tekrar cozmesini denetleyin."
    },
    {
        "no": 122, "ad": "Fatma Nur İnce",
        "ogr_txt": "Matta 26 soru bos; basamak kavrami, rasyonel ve basit denklemden 8 soru belirle. Trde fiilimsi ve cumle ogeleri tekrari yap.",
        "veli_txt": "Matematik kaygisini kirmak icin en temel TYT fasikulunden her gun 2 test cozdurun ve yapamadigi sorulari hocalarina sormasini saglayin."
    },
    {
        "no": 139, "ad": "Denizay Deveci",
        "ogr_txt": "Matta eksi neti durdur: tahmini isaretleme yapma! Yalnizca rasyonel, uslu ve temel kavramda emin oldugun 5 soruyu cozup birak.",
        "veli_txt": "Denemelerde emin olmadigi sorulari kesinlikle bos birakmasini tembihleyin; evdeki testlerde yanlis sayisini takip edin."
    },
    {
        "no": 131, "ad": "Ela Balcı",
        "ogr_txt": "Sosyalde felsefe kavrami ve cografya harita calis. Matta hic yanlisin yok; sureyi 15 dk artirip yapabilecegin 5 soru daha coz.",
        "veli_txt": "Odasina Turkiye ve dunya dilsiz haritasi asmasini saglayin; her aksam 20 dk felsefe/tarih kavram kartlarini calismasini isteyin."
    },
    {
        "no": 220, "ad": "Aynur Aksoy",
        "ogr_txt": "Matta 12 yanlis cok fazla; sallama/tahmini birak, yalnizca emin oldugun 6 soruyu coz. Trde sozcukte yapi ve noktalama calis.",
        "veli_txt": "Matematikte 12 yanlisi cikmistir. Evde tahmini soru isaretlememe kuralini uygulatip gunluk 20 temel islem testi cozdurun."
    },
    {
        "no": 150, "ad": "Esila İrem Mayda",
        "ogr_txt": "Trde yetismeyen paragraflar icin kronometreli gunluk 25 soru coz. Mat ve geometride formulleri kucuk kagitlara yazip tekrar et.",
        "veli_txt": "Haftada 2 adet sureli Turkce brans denemesi cozdurun; aksamlari telefonunu ayri odaya aldirip gunluk 25 paragrafi denetleyin."
    },
    {
        "no": 119, "ad": "Ecrinsu Yılmaz",
        "ogr_txt": "Fizikte bilmeden soru isaretleme, fende kimya ve biyoloji temel konulara odaklan. Matta ilk 10 konunun video cozumlerini izle.",
        "veli_txt": "Gunde 40'ar dakikalik 3 etut plani uygulatin; fende konu calismadan test cozmemesini, once kavram ozeti cikarip calismasini saglayin."
    }
]

# 11. Sınıf Öğrenci ve Veli Teknik Metinleri
DATA_11 = [
    {
        "no": 162, "ad": "Ayşe Nur Teke",
        "ogr_txt": "Trde zamir ve coklu paragraflari tara. Matta 4 yanlisi kesmek icin fonksiyon ve trigonometri temel testlerini coz, soru analizini yap.",
        "veli_txt": "Matematikte yanlis yaptigi 4 sorunun cozum videosunu izletin; aksamlari 40 dakika sessiz etutte Turkce dil bilgisi tekrarini denetleyin."
    },
    {
        "no": 168, "ad": "Zeliha Tuğçe Çetiner",
        "ogr_txt": "Fizikte 4 yanlisin var; vektor ve bagil hareketi bastan calis. Matta islem hatasi yapmamak icin sorulari adim adim yazarak coz.",
        "veli_txt": "Fizik dersinden anlamadigi konulari belirleyip okulda ogretmenine sormasini ve gunluk 2 test fizik cozmesini evde takip edin."
    },
    {
        "no": 120, "ad": "İlayda Uysal",
        "ogr_txt": "Trde ses olaylari ve soz varligini tekrar et. Matta 20 bos birakma; analitik geometri ve parabolden kolay 5 soru daha coz.",
        "veli_txt": "Matematikte bos biraktigi 20 konuyu tespit edip fasikulden gunluk 25 soru cozmesini ve haftalik soru cizelgesini denetleyin."
    },
    {
        "no": 142, "ad": "İdil Çağla Ünver",
        "ogr_txt": "Fizige hic dokunmamissin; temel kavramlardan 3 kolay soru belirle. Trde paragrafa cumle yerlestirme ve iki cumleyi birlestirme calis.",
        "veli_txt": "Fizik testini bos birakma aliskanligini kirmak icin evde en temel seviye fizik ozetlerini okutun ve 10 temel soru cozdurun."
    },
    {
        "no": 156, "ad": "Defne Ebrar Dereli",
        "ogr_txt": "Trde zamir ve genel dil bilgisinden soru kacirma. Matta 4 yanlisi kesmek icin denklem cozme ve oran-orantiyi iyice pekistir.",
        "veli_txt": "Turkce dil bilgisi konu tarama testlerini haftada 2 kez cozdurun; matematikte yapamadigi sorulari hocalarina sormasini denetleyin."
    },
    {
        "no": 183, "ad": "Elanur Aygenoğlu",
        "ogr_txt": "Geometrin cok iyi; bu gucu cebirde kullan: rasyonel ve uslu sayilardan soru kacirma. Trde paragraf cozum sureti 40 dknin altina indir.",
        "veli_txt": "Geometrideki basarisini matematikte de gostermesi icin her gun 30 temel matematik sorusu cozmesini ve kronometre tutmasini saglayin."
    },
    {
        "no": 105, "ad": "Gaffar Okan Çetin",
        "ogr_txt": "Fende 12 bos soru var; kimya periyodik sistem ile biyolojiye calis. Trde eylem (fiil) konusunu bastan tekrar et, yanlisi kes.",
        "veli_txt": "Turkcesi mukemmel ancak fene bakmiyor; evde her gun 20 dakika fen konu ozeti cikarmasini ve 15 temel soru cozmesini saglayin."
    },
    {
        "no": 106, "ad": "Menekşe Rana Cengiz",
        "ogr_txt": "Fizikte 4 yanlisin var; emin olmadan isaretleme yapma. Trde 7 yanlisi azaltmak icin noktalama ve sozcukte anlam testleri coz.",
        "veli_txt": "Fizik dersindeki 4 yanlisi icin konu eksigini gidermesini saglayin; evde tahmini soru isaretlememe kuralini kesin olarak hatirlatin."
    },
    {
        "no": 207, "ad": "Deniz Çağrı Ateş",
        "ogr_txt": "Trde 8 bos paragrafin var; hizlanmak icin her sabah sureli 20 paragraf coz. Fende kimya ve biyolojiden kavram sorularini topla.",
        "veli_txt": "Her sabah okula gitmeden once kronometreyle 20 paragraf sorusu cozmesini saglayin; aksamlari calisirken telefonunu ayri odaya alin."
    },
    {
        "no": 157, "ad": "Tuğçe Onsun",
        "ogr_txt": "Trde 10, matta 9, fizikte 5 yanlis cok fazla! Tahminle isaretlemeyi birak, emin olmadigini bos birakirsan netin hemen 55e firlar.",
        "veli_txt": "Denemede toplam 31 yanlisi cikmistir; tahmini isaretleme huyu vardir. Evdeki testlerde bilmedigini bos birakma kuralini denetleyin."
    }
]


def ana():
    conn = sqlite3.connect(DB_YOLU)
    c = conn.cursor()

    gonderilecekler = []

    def ekle_grup(liste, sinif_etiket):
        for item in liste:
            no = item["no"]
            ad = item["ad"]
            # Öğrenci telefonu
            c.execute("SELECT id, telefon FROM kisiler WHERE okul_no = ? AND tur = 'ogrenci'", (no,))
            ogr = c.fetchone()
            ogr_id = ogr[0] if ogr else None
            ogr_tel = ogr[1] if ogr else None

            # Veli telefonu
            veli_tel = None
            veli_ad = None
            if ogr_id:
                c.execute("SELECT ad_soyad, telefon, veli_rol FROM kisiler WHERE ogrenci_kisi_id = ? AND tur = 'veli'", (ogr_id,))
                veliler = c.fetchall()
                for v in veliler:
                    if v[1]:
                        veli_tel = v[1]
                        veli_ad = f"{v[0]} ({v[2]})" if v[2] else v[0]
                        break

            # Öğrenci SMS kaydı
            if ogr_tel:
                gonderilecekler.append((f"{ad} ({sinif_etiket})", ogr_tel, item["ogr_txt"]))
            elif veli_tel:
                # Öğrencinin telefonu yoksa veliye öğrenci tavsiyesini de ekle
                gonderilecekler.append((f"{ad} Öğrenci Tavsiyesi -> {veli_ad}", veli_tel, f"{ad.split()[0]}: {item['ogr_txt']}"))

            # Veli SMS kaydı
            if veli_tel:
                gonderilecekler.append((f"{veli_ad} (Veli - {ad})", veli_tel, item["veli_txt"]))

    ekle_grup(DATA_12, "12. Sınıf")
    ekle_grup(DATA_11, "11. Sınıf")

    print(f"Toplam hazırlanmış alıcı sayısı: {len(gonderilecekler)}")

    gonderim_id = f"deneme_tavsiye_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Gonderim ID: {gonderim_id}")

    basarili = 0
    hatali = 0

    def _kaydet(isim, telefon, mesaj, durum, hata):
        nonlocal basarili, hatali
        if durum == "gonderildi":
            basarili += 1
            print(f"[OK] {isim} ({telefon[-4:]}): Gonderildi")
        else:
            hatali += 1
            print(f"[HATA] {isim} ({telefon[-4:]}): {hata}")
        db.gonderim_kaydet(conn, gonderim_id, isim, telefon, mesaj, durum, hata)

    ayarlar = sms_gonderici.modem_ayarlarini_yukle()
    durdur_bayragi = threading.Event()

    print("\nModem üzerinden SMS gönderimi başlıyor (her mesaj arası 2.5 sn bekleme)...\n")
    sms_gonderici.toplu_gonder(
        ayarlar=ayarlar,
        kisiler=gonderilecekler,
        sonuc_callback=_kaydet,
        durdur_bayragi=durdur_bayragi,
        bekleme_sn=2.5
    )

    print(f"\nTamamlandı! Başarılı: {basarili}, Hatalı: {hatali}")


if __name__ == "__main__":
    ana()
