"""soruhavuzu/cografya_dunya_ekle.py — Dünya fiziki coğrafyası (kıta, sıradağ, nehir, göl, boğaz, kanal)
sorularını 11 ve 12. sınıf coğrafya havuzuna onaylı olarak ekler (Atakan'ın verdiği soru + doğru cevap;
çeldiriciler aynı türden seçildi). Aynı sınıfta aynı soru metni varsa atlanır; tekrar çalıştırmak güvenlidir."""

import sys

sys.path.insert(0, "/home/ata/farabi")
from soruhavuzu import vt

KONU_DAG = "Dünya: Kıtalar, Okyanuslar ve Sıradağlar"
KONU_SU = "Dünya: Nehirler, Göller, Boğazlar ve Kanallar"
KAYNAK = "Öğretmen girişi: Dünya fiziki coğrafyası"

# (konu, soru, [doğru, çeldirici, çeldirici, çeldirici], zorluk)
SORULAR = [
    (KONU_DAG, "Dünyanın en yüksek noktası olan Everest Tepesi (8.848 m) hangi sıradağlar ve kıta üzerinde yer alır?",
     ["Himalayalar - Asya", "And Dağları - Güney Amerika", "Alp Dağları - Avrupa", "Karakurum Dağları - Afrika"], 1),
    (KONU_DAG, "Güney Amerika kıtasının batı kıyısı boyunca uzanan dünyanın en uzun kara sıradağları hangisidir?",
     ["And Dağları", "Kayalık Dağları", "Appalaş Dağları", "Atlas Dağları"], 1),
    (KONU_DAG, "Kuzey Amerika kıtasının batı kıyıları boyunca uzanan genç kıvrım dağ kuşağı hangisidir?",
     ["Kayalık Dağları (Rocky Mountains)", "Appalaş Dağları", "And Dağları", "Ural Dağları"], 2),
    (KONU_DAG, "Avrupa kıtası ile Asya kıtasını birbirinden ayıran doğal sınır kabul edilen sıradağlar hangisidir?",
     ["Ural Dağları", "Kafkas Dağları", "Alp Dağları", "Karpat Dağları"], 2),
    (KONU_DAG, "Afrika kıtasının doğu fayı hattında yer alan en yüksek bağımsız volkanik kütlesi hangisidir?",
     ["Kilimanjaro Dağı", "Kenya Dağı", "Atlas Dağları", "Etna Yanardağı"], 2),
    (KONU_DAG, "İsviçre, Fransa, İtalya ve Avusturya sınırlarına yayılan Avrupa'nın en büyük kıvrım dağ kuşağı hangisidir?",
     ["Alp Dağları", "Pireneler", "Karpat Dağları", "Apenin Dağları"], 1),
    (KONU_SU, "Afrika kıtasının ortasından doğup Akdeniz'e dökülen dünyanın en uzun nehri hangisidir?",
     ["Nil Nehri", "Kongo Nehri", "Nijer Nehri", "Zambezi Nehri"], 1),
    (KONU_SU, "Taşıdığı su miktarı (debi) ve havza genişliği bakımından dünyanın en büyük akarsuyu olan Amazon Nehri hangi kıtadadır?",
     ["Güney Amerika", "Afrika", "Asya", "Kuzey Amerika"], 1),
    (KONU_SU, "Ekvator çizgisini iki kez kesen ve Afrika'nın en derin akarsuyu olan nehir hangisidir?",
     ["Kongo Nehri", "Nil Nehri", "Nijer Nehri", "Zambezi Nehri"], 3),
    (KONU_SU, "Dünyanın en derin ve en büyük tatlı su hacmine sahip tektonik gölü olan Baykal Gölü hangi ülkededir?",
     ["Rusya", "Kazakistan", "Moğolistan", "Çin"], 2),
    (KONU_SU, "Dünyanın yüz ölçümü bakımından en büyük kapalı su kütlesi (tuzlu gölü) hangisidir?",
     ["Hazar Denizi (Gölü)", "Aral Gölü", "Lut Gölü (Ölü Deniz)", "Victoria Gölü"], 2),
    (KONU_SU, "Akdeniz ile Kızıldeniz'i birbirine bağlayarak Hint Okyanusu yolunu kısaltan yapay kanal hangisidir?",
     ["Süveyş Kanalı", "Panama Kanalı", "Korint Kanalı", "Kiel Kanalı"], 1),
    (KONU_SU, "Atlas Okyanusu ile Büyük Okyanus'u bağlayan ve mühendislik havuz sistemiyle çalışan Orta Amerika kanalı hangisidir?",
     ["Panama Kanalı", "Süveyş Kanalı", "Kiel Kanalı", "Korint Kanalı"], 1),
    (KONU_SU, "Basra Körfezi'ndeki petrol sevkiyatının dünyaya açıldığı tek boğaz hangisidir?",
     ["Hürmüz Boğazı", "Babülmendep Boğazı", "Malakka Boğazı", "Cebelitarık Boğazı"], 2),
    (KONU_SU, "Akdeniz'i Atlas Okyanusu'na bağlayan ve Avrupa ile Afrika kıtalarını ayıran doğal boğaz hangisidir?",
     ["Cebelitarık Boğazı", "Babülmendep Boğazı", "Hürmüz Boğazı", "Manş Denizi"], 1),
    (KONU_SU, "Malezya ile Sumatra Adası arasında yer alan ve dünya deniz ticaretinin en yoğun boğazlarından biri olan geçit hangisidir?",
     ["Malakka Boğazı", "Hürmüz Boğazı", "Bering Boğazı", "Babülmendep Boğazı"], 2),
    (KONU_SU, "Asya kıtası (Sibirya) ile Kuzey Amerika kıtasını (Alaska) birbirinden ayıran en kuzeydeki boğaz hangisidir?",
     ["Bering Boğazı", "Macellan Boğazı", "Malakka Boğazı", "Cebelitarık Boğazı"], 1),
    (KONU_SU, "Afrika kıtasında yer alan Kongo Nehri hangi su kütlesine dökülür?",
     ["Atlas Okyanusu", "Hint Okyanusu", "Akdeniz", "Kızıldeniz"], 2),
    (KONU_SU, "Güney Amerika kıtasında yer alan Amazon Nehri hangi su kütlesine dökülür?",
     ["Atlas Okyanusu", "Büyük Okyanus (Pasifik)", "Karayip Denizi", "Meksika Körfezi"], 1),
    (KONU_SU, "Afrika kıtasında yer alan Nil Nehri hangi su kütlesine dökülür?",
     ["Akdeniz", "Kızıldeniz", "Atlas Okyanusu", "Hint Okyanusu"], 1),
    (KONU_SU, "Asya kıtasında yer alan Mekong Nehri hangi su kütlesine dökülür?",
     ["Güney Çin Denizi", "Bengal Körfezi", "Sarı Deniz", "Arap Denizi"], 2),
    (KONU_SU, "Kuzey Amerika kıtasında yer alan Mississippi Nehri hangi su kütlesine dökülür?",
     ["Meksika Körfezi", "Büyük Okyanus (Pasifik)", "Hudson Körfezi", "Karayip Denizi"], 2),
    (KONU_SU, "Aşağıdaki nehir – döküldüğü su kütlesi eşleştirmelerinden hangisi yanlıştır?",
     ["Mekong Nehri – Hint Okyanusu", "Kongo Nehri – Atlas Okyanusu", "Nil Nehri – Akdeniz",
      "Mississippi Nehri – Meksika Körfezi"], 3),
]

SINIFLAR = (11, 12)


def calistir() -> None:
    conn = vt.baglan()
    eklenen = atlanan = 0
    for sinif in SINIFLAR:
        anahtar = f"elle:cografya:{sinif}:dunya_fiziki"
        # Birim üretici kuyruğuna ('bekliyor') hiç düşmesin: ekleme ve 'islendi' aynı işlemde
        birim_id = vt.birim_ekle(conn, "kazanim", anahtar, "cografya", sinif,
                                 f"{sinif}. Sınıf Coğrafya: Dünya Fiziki Coğrafyası (öğretmen girişi)", "",
                                 oto_commit=False)
        if birim_id is None:
            birim_id = vt.birim_bul(conn, anahtar)
        with conn.cursor() as cur:
            cur.execute("UPDATE kaynak_birim SET durum = 'islendi', islendi_at = now() WHERE id = %s", (birim_id,))
        conn.commit()
        for konu, soru, secenekler, zorluk in SORULAR:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM soru WHERE ders = 'cografya' AND sinif = %s AND soru = %s", (sinif, soru))
                if cur.fetchone():
                    atlanan += 1
                    continue
            sid = vt.soru_ekle(conn, birim_id, {
                "ders": "cografya", "sinif": sinif, "konu": konu, "soru": soru,
                "kisa_cevap": secenekler[0], "secenekler": list(secenekler), "dogru_index": 0,
                "zorluk": zorluk, "kaynak": KAYNAK,
            })
            with conn.cursor() as cur:
                cur.execute("UPDATE soru SET durum = 'onayli', denetim_at = now(), "
                            "denetim_notu = 'öğretmen girişi' WHERE id = %s", (sid,))
            conn.commit()
            eklenen += 1
    conn.close()
    print(f"eklenen={eklenen} atlanan={atlanan}")


if __name__ == "__main__":
    calistir()
