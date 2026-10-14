"""Yıllık planları /mnt/farabi-data/farabi/ klasöründen smual.app sistemine aktarır.

Kullanım:
    python3 scripts/yillik_planlari_aktar.py
"""

import sys
from pathlib import Path

# okul kök dizinini ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import belgeler
import db

BASE = Path("/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027")
MUDUR_DIR = Path("/mnt/farabi-data/farabi/mudur")

PLAN_HARITASI = {
    # 268: Arzu Oral
    (268, "12-A", "ingilizce"): BASE / "ingilizce/26-27 12. sınıf yıllık plan.docx",

    # 269: Ayşe Merve Karakoç
    (269, "9-A", "biyoloji"): BASE / "biyoloji-sağlık/9-sinif-biyoloji-maarif-m-al-yillik-plan.docx",
    (269, "9-B", "biyoloji"): BASE / "biyoloji-sağlık/9-sinif-biyoloji-maarif-m-al-yillik-plan.docx",
    (269, "10-A", "biyoloji"): BASE / "biyoloji-sağlık/10-sinif-biyoloji-maarif-m-al-yillik-plan.docx",
    (269, "11-A", "biyoloji"): BASE / "biyoloji-sağlık/11-sinif-biyoloji-maarif-m-al-yillik-plan-.docx",
    (269, "12-A", "biyoloji"): BASE / "biyoloji-sağlık/12-sinif-biyoloji-al-ayse-merve-karakoc-yillik-plan-.docx",
    (269, "9-A", "sağlık bilgisi ve trafik kültürü"): BASE / "biyoloji-sağlık/9-sinif-saglik-bilg-ve-trafik-kult-maarif-m-yillik-plan.docx",
    (269, "9-B", "sağlık bilgisi ve trafik kültürü"): BASE / "biyoloji-sağlık/9-sinif-saglik-bilg-ve-trafik-kult-maarif-m-yillik-plan.docx",

    # 270: Ayşe Çiçek
    (270, "11-A", "türk dili ve edebiyatı"): BASE / "edebiyat/11.SINIFLAR TDE YILLIK PLANI 2026 - 2027 (1).docx",
    (270, "11-B", "seçmeli türk dili ve edebiyatı"): BASE / "edebiyat/11.SINIFLAR TDE YILLIK PLANI SEÇMELİ.docx",
    (270, "12-B", "seçmeli türk dili ve edebiyatı"): BASE / "edebiyat/12.SINIFLAR TDE YILLIK PLANI SEÇMELİ.docx",
    (270, "9-A", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx",
    (270, "10-A", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/11-sinif-beden-egitimi-ve-spor yıllık plan.docx",
    (270, "11-B", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/11-sinif-beden-egitimi-ve-spor yıllık plan.docx",

    # 271: Elif Yıldız Tutak
    (271, "9-B", "türk dili ve edebiyatı"): BASE / "edebiyat/9.SINIFLAR TDE YILLIK PLANI.docx",
    (271, "11-B", "türk dili ve edebiyatı"): BASE / "edebiyat/11.SINIFLAR TDE YILLIK PLANI 2026 - 2027 (1).docx",
    (271, "12-B", "türk dili ve edebiyatı"): BASE / "edebiyat/12.SINIFLAR TDE YILLIK PLANI.pdf",
    (271, "9-B", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx",
    (271, "10-A", "spor etkinlikleri"): BASE / "beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx",
    (271, "12-A", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/12-sinif-beden-egitimi-ve-spor yıllık plan.docx",
    (271, "9-B", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 283: Fatma Sivrikaya
    (283, "9-A", "matematik"): BASE / "matematik/9-12.xlsx",
    (283, "9-B", "matematik"): BASE / "matematik/9-12.xlsx",
    (283, "12-A", "matematik"): BASE / "matematik/9-12.xlsx",
    (283, "12-B", "matematik"): BASE / "matematik/9-12.xlsx",

    # 273: Feride İmamoğlu
    (273, "9-A", "almanca"): BASE / "almanca/9-sinif-almanca-mit-deutsch-a11-yillik-plan-ogretmenevrak-1788857208.docx",
    (273, "9-B", "almanca"): BASE / "almanca/9-sinif-almanca-mit-deutsch-a11-yillik-plan-ogretmenevrak-1788857208.docx",
    (273, "12-A", "almanca"): BASE / "almanca/12-sinif-almanca-deutsch-a12-yillik-plan-ogretmenevrak-1788857282.docx",
    (273, "12-B", "almanca"): BASE / "almanca/12-sinif-almanca-deutsch-a12-yillik-plan-ogretmenevrak-1788857282.docx",
    (273, "11-A", "görsel sanatlar"): BASE / "görsel sanatlar/11 görsel sanatlar feride.docx",
    (273, "12-A", "spor etkinlikleri"): BASE / "beden eğitimi 10 eksik/12. sınıf beden eğitimi.docx",

    # 274: Gonca Çelik
    (274, "10-A", "felsefe"): BASE / "felsefe-unitelendirilmis-yillik-plan.docx",
    (274, "11-A", "felsefe"): BASE / "11.sinif-felsefe-dersi-yillik-plani.docx",
    (274, "11-B", "felsefe"): BASE / "11.sinif-felsefe-dersi-yillik-plani.docx",
    (274, "11-B", "psikoloji"): BASE / "psikoloji--unitelendirilmis-yillik-plan.docx",
    (274, "11-B", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 275: Gözde Kahriman Gökdoğan
    (275, "9-A", "fizik"): BASE / "fizik/9.sınıf fizik yıllık plan.docx",
    (275, "9-B", "fizik"): BASE / "fizik/9.sınıf fizik yıllık plan.docx",
    (275, "10-A", "fizik"): BASE / "fizik/10.sınıf fizik yıllık plan.docx",
    (275, "11-A", "fizik"): BASE / "fizik/11.sınıf fizik yıllık plan.docx",
    (275, "12-A", "fizik"): BASE / "fizik/hedef-temelli-egitim-fizik-1.docx",
    (275, "9-A", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 276: Melek Yıldırım
    (276, "10-A", "matematik"): BASE / "matematik/2026-2027 10. sınıf yıllık plan matematik.pdf",
    (276, "11-A", "matematik"): BASE / "matematik/2026-2027 11. sınıf yıllık plan matematik.pdf",
    (276, "11-B", "matematik"): BASE / "matematik/2026-2027 11. sınıf yıllık plan matematik.pdf",
    (276, "11-A", "matematik uygulamaları"): BASE / "matematik/2026-2027 11. sınıf yıllık plan matematik.pdf",
    (276, "11-A", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 277: Muharrem Yartaşı
    (277, "9-A", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab9_TYMM  (1).xlsx",
    (277, "9-B", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab9_TYMM  (1).xlsx",
    (277, "10-A", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab10_TYMM (1).xlsx",
    (277, "10-A", "peygamberimizin hayatı"): BASE / "din kültürü/2026-2027peygamberimizinhayati10_TYMM (2).xlsx",
    (277, "11-A", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab11_TYMM 1.xlsx",
    (277, "11-B", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab11_TYMM 1.xlsx",
    (277, "12-A", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab12 (1).xlsx",
    (277, "12-B", "din kültürü ve ahlak bilgisi"): BASE / "din kültürü/2026-2027dkab12 (1).xlsx",

    # 278: Safiye Yılmaz
    (278, "9-A", "ingilizce"): BASE / "ingilizce/9.-Sinif-Ingilizce-Yillik-Plan-2026-2027-by-ingilizceciyiz.com_-1.docx",
    (278, "9-B", "ingilizce"): BASE / "ingilizce/9.-Sinif-Ingilizce-Yillik-Plan-2026-2027-by-ingilizceciyiz.com_-1.docx",
    (278, "10-A", "ingilizce"): BASE / "ingilizce/10. SINIF İNGİLİZCE.docx",
    (278, "11-A", "ingilizce"): BASE / "ingilizce/26-27 11.sınıf yıllık plan.docx",
    (278, "11-B", "ingilizce"): BASE / "ingilizce/26-27 11.sınıf yıllık plan.docx",
    (278, "12-B", "ingilizce"): BASE / "ingilizce/26-27 12. sınıf yıllık plan.docx",
    (278, "10-A", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 279: Sedat Bayar
    (279, "9-A", "tarih"): BASE / "tarih/2026-2027ŞEHİT MURAT USTAOĞLU _9_Sinif_Tarih_Yillik_Plani.docx",
    (279, "9-B", "tarih"): BASE / "tarih/2026-2027ŞEHİT MURAT USTAOĞLU _9_Sinif_Tarih_Yillik_Plani.docx",
    (279, "10-A", "tarih"): BASE / "tarih/2026-2027_ŞEHİT MURAT USTAOĞLU_10_Sinif_Tarih_Yillik_Plani.docx",
    (279, "10-A", "ortak türk tarihi"): BASE / "tarih/ortak-turk-tarihi-unitelendirilmis-yillik-plan.docx",
    (279, "11-A", "tarih"): BASE / "tarih/2026-2027_11_Sinif_Tarih_Yillik_Plani_Farklilastirma_Eklenmis (1).docx",
    (279, "11-B", "tarih"): BASE / "tarih/2026-2027_11_Sinif_Tarih_Yillik_Plani_Farklilastirma_Eklenmis (1).docx",
    (279, "12-A", "inkılap tarihi ve atatürkçülük"): BASE / "tarih/2026-2027_ŞEHİT MURAT USTAOĞLUi_12_Sinif_TC_Inkilap_Tarihi_).docx",
    (279, "12-B", "inkılap tarihi ve atatürkçülük"): BASE / "tarih/2026-2027_ŞEHİT MURAT USTAOĞLUi_12_Sinif_TC_Inkilap_Tarihi_).docx",
    (279, "12-B", "çağdaş türk ve dünya tarihi"): BASE / "tarih/ÇAĞDAŞ .docx",
    (279, "12-B", "rehberlik"): MUDUR_DIR / "Lise_Yıllık_RPDH_Planı.xlsx",

    # 280: Zehra Öztürk
    (280, "9-A", "türk dili ve edebiyatı"): BASE / "edebiyat/9.SINIFLAR TDE YILLIK PLANI.docx",
    (280, "10-A", "türk dili ve edebiyatı"): BASE / "edebiyat/10.sınıflar edebiyat.pdf",
    (280, "12-A", "türk dili ve edebiyatı"): BASE / "edebiyat/12.SINIFLAR TDE YILLIK PLANI.pdf",
    (280, "9-A", "spor etkinlikleri"): BASE / "beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx",
    (280, "9-B", "spor etkinlikleri"): BASE / "beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx",
    (280, "11-A", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/11-sinif-beden-egitimi-ve-spor yıllık plan.docx",
    (280, "12-B", "beden eğitimi"): BASE / "beden eğitimi 10 eksik/12-sinif-beden-egitimi-ve-spor yıllık plan.docx",

    # 281: Çiğdem İnce
    (281, "9-A", "görsel sanatlar"): BASE / "görsel sanatlar/9-sinif-gorsel-sanatlar-maarif-m-yillik-plan-ogretmenevrak-1789636609.docx",
    (281, "9-B", "görsel sanatlar"): BASE / "görsel sanatlar/9-sinif-gorsel-sanatlar-maarif-m-yillik-plan-ogretmenevrak-1789636609.docx",
    (281, "10-A", "görsel sanatlar"): BASE / "görsel sanatlar/10-sinif-gorsel-sanatlar-maarif-m-yillik-plan-ogretmenevrak-1789636695.docx",
    (281, "11-B", "görsel sanatlar"): BASE / "görsel sanatlar/11-sinif-gorsel-sanatlar-cigdem-ince-yillik-plan-ogretmenevrak-1789636733.docx",

    # 282: Özlem Arslan
    (282, "9-A", "coğrafya"): BASE / "coğrafya/9-sinif-cografya-maarif-m-al-yillik-plan-ogretmenevrak-1789111222.docx",
    (282, "9-B", "coğrafya"): BASE / "coğrafya/9-sinif-cografya-maarif-m-al-yillik-plan-ogretmenevrak-1789111222.docx",
    (282, "10-A", "coğrafya"): BASE / "coğrafya/10-sinif-cografya-maarif-m-al-yillik-plan-ogretmenevrak-1789111198.docx",
    (282, "11-B", "coğrafya"): BASE / "coğrafya/11-sinif-cografya-maarif-m-al-4-saatlik-yillik-plan-ogretmenevrak-1789111163.docx",
    (282, "12-B", "coğrafya"): BASE / "coğrafya/12-sinif-cografya-al-4-saatlik-ozlem-arslan-yillik-plan-ogretmenevrak-1789111245.docx",
}


def main():
    conn = db.baglanti()
    try:
        cur = conn.cursor()
        duties = cur.execute("""
            SELECT g.ogretmen_id, k.ad_soyad, g.sinif, g.ders, yp.id as plan_id
            FROM ogretmen_gorev g
            JOIN kullanici k ON g.ogretmen_id = k.id
            LEFT JOIN yillik_plan yp ON yp.ogretmen_id = g.ogretmen_id AND yp.sinif = g.sinif AND yp.ders = g.ders
            ORDER BY k.ad_soyad, g.sinif, g.ders
        """).fetchall()

        print(f"Toplam öğretmen görev sayısı: {len(duties)}")
        yuklenen_sayisi = 0
        zaten_olan_sayisi = 0
        hata_sayisi = 0

        for d in duties:
            ogretmen_id = d["ogretmen_id"]
            ad_soyad = d["ad_soyad"]
            sinif = d["sinif"]
            ders = d["ders"]
            mevcut_plan_id = d["plan_id"]

            if mevcut_plan_id is not None:
                zaten_olan_sayisi += 1
                continue

            anahtar = (ogretmen_id, sinif, ders)
            if anahtar not in PLAN_HARITASI:
                print(f"[UYARI] Haritada yok: {ad_soyad} ({ogretmen_id}) | {sinif} | {ders}")
                hata_sayisi += 1
                continue

            dosya_yolu = PLAN_HARITASI[anahtar]
            if not dosya_yolu.exists():
                print(f"[HATA] Dosya bulunamadı: {dosya_yolu}")
                hata_sayisi += 1
                continue

            k = cur.execute("SELECT * FROM kullanici WHERE id = ?", (ogretmen_id,)).fetchone()
            veri = dosya_yolu.read_bytes()
            dosya_adi = dosya_yolu.name

            try:
                plan_id = belgeler.plan_yukle(conn, k, sinif, ders, dosya_adi, veri)
                print(f"[YÜKLENDİ] ID:{plan_id} -> {ad_soyad} | {sinif} | {ders} | {dosya_adi}")
                yuklenen_sayisi += 1
            except Exception as e:
                print(f"[HATA] {ad_soyad} | {sinif} | {ders} yüklenirken hata: {e}")
                hata_sayisi += 1

        print("=" * 60)
        print(f"İşlem tamamlandı!")
        print(f"Zaten yüklü olanlar: {zaten_olan_sayisi}")
        print(f"Yeni yüklenenler: {yuklenen_sayisi}")
        print(f"Hatalar: {hata_sayisi}")

        # Nihai durum kontrolü
        kalan_eksik = cur.execute("""
            SELECT COUNT(*) FROM ogretmen_gorev g
            LEFT JOIN yillik_plan yp ON yp.ogretmen_id = g.ogretmen_id AND yp.sinif = g.sinif AND yp.ders = g.ders
            WHERE yp.id IS NULL
        """).fetchone()[0]
        toplam_plan = cur.execute("SELECT COUNT(*) FROM yillik_plan").fetchone()[0]
        print(f"Veritabanındaki toplam plan sayısı: {toplam_plan}")
        print(f"Eksik kalan görev sayısı: {kalan_eksik}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
