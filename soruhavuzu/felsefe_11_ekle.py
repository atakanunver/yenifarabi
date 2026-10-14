"""soruhavuzu/felsefe_11_ekle.py — 11. sınıf Felsefe ve Psikoloji sorularını ekler.

MEB 11. Sınıf Felsefe Öğretim Programı ve Yıllık Planlarındaki temalara uygun olarak:
- Çevre Sorunları ve Çevre Etiği (Hans Jonas, Antroposantrizm / Biyosantrizm)
- Teknoloji ve Hayat (Yapay Zeka Etiği, Transhümanizm, Bilişim Etiği)
- Akıl ve İnanç (Teizm, Deizm, Agnostisizm, Akıl-İman İlişkisi, Farabi & Gazali)
- Edebiyat ve Felsefe (Varoluşçuluk, Albert Camus, Sartre, Felsefi Roman)
- Hayatın Anlamı ve Hukuk Felsefesi (Doğal Hukuk, Pozitif Hukuk, Adalet Teorileri)
- Psikoloji Temelleri (11-B için: Duyum, Algı, Bellek, Koşullanma, Savunma Mekanizmaları)
- İlk Çağ ve Orta Çağ Felsefesi (Sokrates, Platon, Aristoteles, Patristik ve Skolastik Dönem)
- Modern Felsefe ve Aydınlanma (Descartes, Locke, Kant, Hegel)

Her tema için 1-4 zorluk derecelerinde, 4 şıklı ve kanonik sıralı sorular oluşturur;
ayrıca soru_havuzu'nda 12. sınıfta duran 169 adet orijinal MEB/ÖSYM Felsefe & Psikoloji sorusunu
11. sınıfa köprüleyerek kaydeder.
"""

import hashlib
import json
import logging
import sys
from pathlib import Path
import psycopg2

sys.path.insert(0, "/home/ata/farabi")
from soruhavuzu import sik

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SORULAR_11_MÜFREDAT = [
    # Tema 1: Çevre Sorunları ve Çevre Etiği (Zorluk 1-4)
    {
        "konu": "Çevre Sorunları ve Çevre Etiği",
        "soru": "İnsanı doğanın efendisi ve merkezine koyan, diğer tüm canlıları insanın yararı için bir araç gören felsefi çevre yaklaşımı hangisidir?",
        "secenekler": ["İnsan merkezcilik (Antroposantrizm)", "Canlı merkezcilik (Biyosantrizm)", "Eko-merkezcilik (Ekosantrizm)", "Derin Ekoloji"],
        "cevap": "İnsan merkezcilik (Antroposantrizm)",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 1. Ünite: Çevre Sorunları"
    },
    {
        "konu": "Çevre Sorunları ve Çevre Etiği",
        "soru": "Gelecek kuşaklara yaşanabilir bir dünya bırakmayı ahlaki bir ödev sayan ve 'Sorumluluk İlkesi'ni ortaya koyan 20. yüzyıl filozofu kimdir?",
        "secenekler": ["Hans Jonas", "Immanuel Kant", "René Descartes", "John Locke"],
        "cevap": "Hans Jonas",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, 1. Ünite: Çevre Sorunları"
    },
    {
        "konu": "Çevre Sorunları ve Çevre Etiği",
        "soru": "Doğadaki tüm canlıların insanlar gibi 'özsel bir değere' sahip olduğunu savunan çevre etiği yaklaşımı hangisidir?",
        "secenekler": ["Biyosantrizm (Canlı merkezcilik)", "Teknomerkezcilik", "Faydacılık (Pragmatizm)", "Mekanik doğa anlayışı"],
        "cevap": "Biyosantrizm (Canlı merkezcilik)",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, 1. Ünite: Çevre Sorunları"
    },
    {
        "konu": "Çevre Sorunları ve Çevre Etiği",
        "soru": "Sanayi Devrimi sonrasında doğanın sınırsız bir hammadde deposu olarak görülmesi, hangi felsefi doğa anlayışının bir sonucudur?",
        "secenekler": [
            "Kartezyen mekanik ve araçsalcı doğa anlayışı",
            "Aristotelesçi ereksel (teleolojik) doğa anlayışı",
            "Spinoza'nın panteist doğa anlayışı",
            "Stoacı doğayla uyum felsefesi"
        ],
        "cevap": "Kartezyen mekanik ve araçsalcı doğa anlayışı",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 1. Ünite: Çevre Sorunları"
    },

    # Tema 2: Teknoloji ve Hayat (Zorluk 1-4)
    {
        "konu": "Teknoloji ve Hayat",
        "soru": "İnsan zihninin ve bedeninin biyoteknoloji ve yapay zeka yoluyla geliştirilerek insanüstü bir aşamaya evrilmesini savunan düşünce akımı hangisidir?",
        "secenekler": ["Transhümanizm", "Hümanizm", "Egzistansiyalizm", "Stoacılık"],
        "cevap": "Transhümanizm",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 2. Ünite: Teknoloji ve Hayat"
    },
    {
        "konu": "Teknoloji ve Hayat",
        "soru": "Otonom araçların kaza anında yapacağı seçimleri araştıran meşhur etik ikilem senaryosu hangisidir?",
        "secenekler": ["Tramvay Problemi (Trolley Problem)", "Mahkûm İkilemi", "Theseus'un Gemisi", "Mağara Alegorisi"],
        "cevap": "Tramvay Problemi (Trolley Problem)",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, 2. Ünite: Teknoloji ve Hayat"
    },
    {
        "konu": "Teknoloji ve Hayat",
        "soru": "Yapay zekanın insan düzeyinde bilince ve ahlaki sorumluluğa sahip olup olamayacağını tartışan felsefe dalı hangisidir?",
        "secenekler": ["Zihin Felsefesi ve Yapay Zeka Etiği", "Estetik", "Siyaset Felsefesi", "Mantık"],
        "cevap": "Zihin Felsefesi ve Yapay Zeka Etiği",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, 2. Ünite: Teknoloji ve Hayat"
    },
    {
        "konu": "Teknoloji ve Hayat",
        "soru": "Teknolojinin yalnızca insan amaçlarına hizmet eden nötr bir araç olmadığını, insan düşüncesini ve toplumsal yapıyı kaçınılmaz biçimde biçimlendirdiğini savunan görüş hangisidir?",
        "secenekler": [
            "Teknolojik Determinizm",
            "Teknolojik İyimserlik",
            "Araçsalcı Teknoloji Kuramı",
            "Kültürel Görelilik"
        ],
        "cevap": "Teknolojik Determinizm",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 2. Ünite: Teknoloji ve Hayat"
    },

    # Tema 3: Akıl ve İnanç (Zorluk 1-4)
    {
        "konu": "Akıl ve İnanç",
        "soru": "Tanrı'nın varlığını kabul eden, evreni yarattığına ve evrene sürekli müdahale ettiğine inanan felsefi görüş hangisidir?",
        "secenekler": ["Teizm", "Deizm", "Agnostisizm", "Ateizm"],
        "cevap": "Teizm",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 3. Ünite: Akıl ve İnanç"
    },
    {
        "konu": "Akıl ve İnanç",
        "soru": "Tanrı'nın evreni yarattıktan sonra kendi doğa yasalarına bıraktığını ve mucizeler veya vahiy yoluyla müdahale etmediğini savunan görüş hangisidir?",
        "secenekler": ["Deizm", "Teizm", "Panteizm", "Politeizm"],
        "cevap": "Deizm",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, 3. Ünite: Akıl ve İnanç"
    },
    {
        "konu": "Akıl ve İnanç",
        "soru": "İslam felsefesinde aklı ve mantığı felsefenin merkezine koyan, 'Muallim-i Sani' (İkinci Öğretmen) olarak bilinen ünlü filozof kimdir?",
        "secenekler": ["Fârâbî", "Gazâlî", "İbn Haldun", "Mevlânâ"],
        "cevap": "Fârâbî",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, 3. Ünite: Akıl ve İnanç"
    },
    {
        "konu": "Akıl ve İnanç",
        "soru": "Gazâlî, 'Tehâfütü'l-Felâsife' (Filozofların Tutarsızlığı) adlı eserinde meşşâî filozofların özellikle hangi alandaki akıl yürütmelerinin yetersiz olduğunu savunmuştur?",
        "secenekler": [
            "Metafizik ve nedensellik (illiyet) teorisi",
            "Matematik ve geometri ilkeleri",
            "Mantık kıyas kuralları",
            "Arap dili ve grameri"
        ],
        "cevap": "Metafizik ve nedensellik (illiyet) teorisi",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 3. Ünite: Akıl ve İnanç"
    },

    # Tema 4: Edebiyat ve Felsefe (Zorluk 1-4)
    {
        "konu": "Edebiyat ve Felsefe",
        "soru": "'Yabancı' ve 'Veba' romanlarıyla insanın anlamsız dünyadaki varoluşsal çabasını ve 'Absürd' (Saçma) kavramını işleyen düşünür-yazar kimdir?",
        "secenekler": ["Albert Camus", "Jean-Paul Sartre", "Franz Kafka", "Fyodor Dostoyevski"],
        "cevap": "Albert Camus",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 4. Ünite: Edebiyat ve Felsefe"
    },
    {
        "konu": "Edebiyat ve Felsefe",
        "soru": "'Varoluş özden önce gelir' ilkesini 'Bulantı' romanında edebiyat yoluyla somutlaştıran varoluşçu filozof kimdir?",
        "secenekler": ["Jean-Paul Sartre", "Friedrich Nietzsche", "Arthur Schopenhauer", "Martin Heidegger"],
        "cevap": "Jean-Paul Sartre",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, 4. Ünite: Edebiyat ve Felsefe"
    },
    {
        "konu": "Edebiyat ve Felsefe",
        "soru": "Felsefe ile edebiyatın kesişim noktasında yer alan felsefi romanların temel işlevi hangisidir?",
        "secenekler": [
            "Soyut felsefi problemleri insan deneyimi ve karakterler üzerinden somutlaştırıp sorgulatmak",
            "Yalnızca gramer kurallarını ve kafiye yapısını öğretmek",
            "Tarihi olayları kronolojik olarak belgelendirmek",
            "Doğa bilimlerinin deney sonuçlarını raporlamak"
        ],
        "cevap": "Soyut felsefi problemleri insan deneyimi ve karakterler üzerinden somutlaştırıp sorgulatmak",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, 4. Ünite: Edebiyat ve Felsefe"
    },
    {
        "konu": "Edebiyat ve Felsefe",
        "soru": "Franz Kafka'nın 'Dönüşüm' adlı eserinde Gregor Samsa'nın bir böceğe dönüşmesi hangi varoluşsal durumu simgeler?",
        "secenekler": [
            "Modern insanın ailesine, işine ve topluma yabancılaşması (alienation)",
            "Doğa sevgisi ve entomoloji ilgisi",
            "Biyolojik evrim teorisinin aşamaları",
            "Rönesans resim sanatının canlandırılması"
        ],
        "cevap": "Modern insanın ailesine, işine ve topluma yabancılaşması (alienation)",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 4. Ünite: Edebiyat ve Felsefe"
    },

    # Tema 5: Hukuk Felsefesi ve Adalet (Zorluk 1-4)
    {
        "konu": "Hukuk Felsefesi ve Adalet",
        "soru": "İnsan doğasından kaynaklanan, yazılı kurallardan bağımsız, evrensel ve değişmez ahlaki hakları savunan hukuk anlayışı hangisidir?",
        "secenekler": ["Doğal Hukuk", "Pozitif Hukuk (Yazılı Hukuk)", "Tarihsel Hukuk", "Sosyalist Hukuk"],
        "cevap": "Doğal Hukuk",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 5. Ünite: Hukuk Felsefesi"
    },
    {
        "konu": "Hukuk Felsefesi ve Adalet",
        "soru": "Yalnızca yetkili devlet organları tarafından usulüne uygun olarak konulmuş ve yürürlükte olan yazılı yasalara ne ad verilir?",
        "secenekler": ["Pozitif Hukuk (Müspet Hukuk)", "Doğal Hukuk", "İdeal Hukuk", "Ahlak Yasası"],
        "cevap": "Pozitif Hukuk (Müspet Hukuk)",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, 5. Ünite: Hukuk Felsefesi"
    },
    {
        "konu": "Hukuk Felsefesi ve Adalet",
        "soru": "'Bir Adalet Teorisi' adlı eserinde adaleti 'hakkaniyet olarak adalet' şeklinde tanımlayan ve 'bilinmezlik peçesi' düşünce deneyini geliştiren düşünür kimdir?",
        "secenekler": ["John Rawls", "Thomas Hobbes", "Niccolò Machiavelli", "Montesquieu"],
        "cevap": "John Rawls",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, 5. Ünite: Hukuk Felsefesi"
    },
    {
        "konu": "Hukuk Felsefesi ve Adalet",
        "soru": "Hukukun meşruiyetini adalet ideali ve insan onuruna bağlayan hukuk anlayışının pozitif hukuktan temel farkı nedir?",
        "secenekler": [
            "Yasanın yalnızca iktidar emri olmasını yetersiz bulup ahlaki doğruluğu şart koşması",
            "Mahkemelerin ve yargıçların varlığını tamamen reddetmesi",
            "Yazılı yasaların hiçbir koşulda değiştirilemeyeceğini savunması",
            "Cezalandırmayı tek amaç haline getirmesi"
        ],
        "cevap": "Yasanın yalnızca iktidar emri olmasını yetersiz bulup ahlaki doğruluğu şart koşması",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 5. Ünite: Hukuk Felsefesi"
    },

    # Tema 6: Psikoloji Temelleri (11-B için) (Zorluk 1-4)
    {
        "konu": "Psikoloji Temelleri",
        "soru": "Bir canlının iç veya dış çevreden gelen uyarıcıları duyu organları aracılığıyla sinirsel enerjiye dönüştürüp almasına ne ad verilir?",
        "secenekler": ["Duyum", "Algı", "Öğrenme", "Düşünme"],
        "cevap": "Duyum",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Psikoloji, Duyum ve Algı"
    },
    {
        "konu": "Psikoloji Temelleri",
        "soru": "Duyu organlarına ulaşan bilgilerin beyinde organize edilip anlamlandırılması sürecine ne ad verilir?",
        "secenekler": ["Algı", "Duyum", "Refleks", "Güdü"],
        "cevap": "Algı",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Psikoloji, Duyum ve Algı"
    },
    {
        "konu": "Psikoloji Temelleri",
        "soru": "Fiziksel olarak var olan bir uyarıcının duyu organlarınca yanlış değerlendirilmesine ne denir? (Örn: Gece yerdeki ipi yılan sanmak)",
        "secenekler": ["İllüzyon (Yanılsama)", "Halüsinasyon (Sanrı)", "Duyusal uyum", "Yetersiz uyarılma"],
        "cevap": "İllüzyon (Yanılsama)",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Psikoloji, Duyum ve Algı"
    },
    {
        "konu": "Psikoloji Temelleri",
        "soru": "Ivan Pavlov'un köpekler üzerinde yaptığı deneylerle kanıtladığı ve zil sesi ile salya salgılanmasını eşleştirdiği öğrenme türü hangisidir?",
        "secenekler": [
            "Klasik Koşullanma (Tepkisel Koşullanma)",
            "Edimsel Koşullanma (Operant)",
            "Model Alarak Öğrenme (Sosyal Öğrenme)",
            "Kavrayış Yoluyla Öğrenme (İçgörü)"
        ],
        "cevap": "Klasik Koşullanma (Tepkisel Koşullanma)",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Psikoloji, Öğrenme Psikolojisi"
    },

    # Tema 7: İlk Çağ Felsefesi (Zorluk 1-4)
    {
        "konu": "İlk Çağ Doğa ve İnsan Felsefesi",
        "soru": "Felsefe tarihinin ilk filozofu kabul edilen ve evrenin ana maddesini (arkhe) 'Su' olarak belirleyen düşünür kimdir?",
        "secenekler": ["Thales", "Anaksimandros", "Herakleitos", "Parmenides"],
        "cevap": "Thales",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe Tarihi, MÖ 6. Yüzyıl"
    },
    {
        "konu": "İlk Çağ Doğa ve İnsan Felsefesi",
        "soru": "'Değişmeyen tek şey değişimin kendisidir' ve 'Aynı ırmakta iki kez yıkanılmaz' sözleriyle bilinen filozof kimdir?",
        "secenekler": ["Herakleitos", "Parmenides", "Demokritos", "Empedokles"],
        "cevap": "Herakleitos",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe Tarihi, MÖ 6. Yüzyıl"
    },
    {
        "konu": "İlk Çağ Doğa ve İnsan Felsefesi",
        "soru": "Sokrates'in karşısındaki kişinin zihninde doğuştan var olan doğruları açığa çıkarmak için kullandığı yönteme ne ad verilir?",
        "secenekler": ["Maiotik (Doğurtma Yöntemi / Sokratik Diyalog)", "Tümevarım", "Şüphecilik (Septisizm)", "Fenomenolojik İndirgeme"],
        "cevap": "Maiotik (Doğurtma Yöntemi / Sokratik Diyalog)",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe Tarihi, Sokrates"
    },
    {
        "konu": "İlk Çağ Doğa ve İnsan Felsefesi",
        "soru": "Platon'un ontolojisinde (varlık felsefesinde) duyularla algılanan değişken dünyanın ötesinde yer alan ebedi ve kusursuz asıllar dünyasına ne ad verilir?",
        "secenekler": ["İdealar Dünyası", "Nesneler Dünyası", "Atomlar Alemi", "Görünüşler Dünyası"],
        "cevap": "İdealar Dünyası",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe Tarihi, Platon"
    },

    # Tema 8: Modern Felsefe ve Akıl (Zorluk 1-4)
    {
        "konu": "Modern Felsefe ve Akıl",
        "soru": "'Düşünüyorum, öyleyse varım' (Cogito ergo sum) önermesiyle metodik şüpheyi kesin bilginin temeli yapan Fransız düşünür kimdir?",
        "secenekler": ["René Descartes", "Francis Bacon", "Baruch Spinoza", "Gottfried Leibniz"],
        "cevap": "René Descartes",
        "zorluk": 1,
        "kaynak": "MEB 11. Sınıf Felsefe, 17. Yüzyıl Felsefesi"
    },
    {
        "konu": "Modern Felsefe ve Akıl",
        "soru": "İnsan zihninin doğuştan boş bir levha (Tabula Rasa) olduğunu ve tüm bilgilerin deneyim yoluyla kazanıldığını savunan empirist filozof kimdir?",
        "secenekler": ["John Locke", "Immanuel Kant", "David Hume", "Platon"],
        "cevap": "John Locke",
        "zorluk": 2,
        "kaynak": "MEB 11. Sınıf Felsefe, Aydınlanma Felsefesi"
    },
    {
        "konu": "Modern Felsefe ve Akıl",
        "soru": "Rasyonalizm ile Empirizmi uzlaştırarak 'Görüsüz kavramlar boş, kavramsız görüler kördür' diyen Kritisizmin kurucusu kimdir?",
        "secenekler": ["Immanuel Kant", "G.W.F. Hegel", "Arthur Schopenhauer", "Friedrich Nietzsche"],
        "cevap": "Immanuel Kant",
        "zorluk": 3,
        "kaynak": "MEB 11. Sınıf Felsefe, Aydınlanma Felsefesi"
    },
    {
        "konu": "Modern Felsefe ve Akıl",
        "soru": "Hegel'in felsefesinde evrensel aklın (Geist) kendini gerçekleştirmek için izlediği üç aşamalı diyalektik süreç sırasıyla hangisidir?",
        "secenekler": [
            "Tez - Antitez - Sentez",
            "Gözlem - Hipotez - Teori",
            "Kuşku - İnanç - Eylem",
            "Duyum - Algı - Kavram"
        ],
        "cevap": "Tez - Antitez - Sentez",
        "zorluk": 4,
        "kaynak": "MEB 11. Sınıf Felsefe, 19. Yüzyıl Felsefesi"
    },
]


def calistir():
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")
    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")

    # 1. kaynak_birim ekle (11. sınıf Felsefe müfredatı)
    with havuz.cursor() as cur:
        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kazanim', 'kazanim:felsefe:11_mufredat', 'felsefe', 11,
                    '11. Sınıf Felsefe ve Psikoloji Müfredat Soruları', 'MEB 11. Sınıf Felsefe ve Psikoloji Yıllık Planı ve Müfredat Soruları',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_11_id = cur.fetchone()[0]

        # Eski 11. sınıf Felsefe sorularını temizle
        cur.execute("DELETE FROM soru WHERE ders = 'felsefe' AND sinif = 11;")
        logging.info("soru_havuzu: Eski 11. sınıf Felsefe kayıtları temizlendi (%d satır).", cur.rowcount)

        toplam_eklenen = 0

        # Yeni müfredat sorularını ekle (32 soru)
        for s in SORULAR_11_MÜFREDAT:
            dogru_metin = s["cevap"]
            secim = list(s["secenekler"])
            if dogru_metin not in secim:
                secim[0] = dogru_metin
            dogru_idx = secim.index(dogru_metin)

            kanonik_sec, yeni_idx = sik.kanonik_sira(s["soru"], secim, dogru_idx)

            cur.execute("""
                INSERT INTO soru
                (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                VALUES (%s, %s, 11, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
            """, (
                birim_11_id,
                "felsefe",
                s["konu"],
                s["soru"],
                dogru_metin,
                json.dumps(kanonik_sec, ensure_ascii=False),
                yeni_idx,
                s["zorluk"],
                s["kaynak"]
            ))
            toplam_eklenen += 1

        # 2. 12. sınıfta duran 169 adet onaylı YKS Felsefe/Mantık/Psikoloji sorusunu 11. sınıfa kopyala
        cur.execute("""
            SELECT birim_id, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak
            FROM soru
            WHERE ders = 'felsefe' AND sinif = 12 AND durum = 'onayli';
        """)
        yks_sorulari = cur.fetchall()
        logging.info("12. sınıftan köprülenecek onaylı YKS Felsefe soru sayısı: %d", len(yks_sorulari))

        for s in yks_sorulari:
            cur.execute("""
                INSERT INTO soru
                (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                VALUES (%s, 'felsefe', 11, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
            """, (
                s[0], s[1], s[2], s[3],
                json.dumps(s[4], ensure_ascii=False) if isinstance(s[4], list) else s[4],
                s[5], s[6], s[7]
            ))
            toplam_eklenen += 1

        havuz.commit()
        logging.info("soru_havuzu: 11. sınıf Felsefe için toplam %d onaylı soru kaydedildi.", toplam_eklenen)

    # 3. farabi.kazanim_test_soru tablosuna 11. sınıf Felsefe sorularını ekle
    with farabi.cursor() as cur:
        cur.execute("DELETE FROM kazanim_test_soru WHERE ders ILIKE '%%felsefe%%' AND sinif = 11;")
        dosya_yolu = Path("/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027/11.sinif-felsefe-dersi-yillik-plani.docx")
        f_hash = hashlib.sha256(dosya_yolu.read_bytes()).hexdigest()
        no_sayac = 1
        for s in SORULAR_11_MÜFREDAT:
            secenek_harfleri = ["A", "B", "C", "D"]
            secenek_map = {secenek_harfleri[i]: s["secenekler"][i] for i in range(len(s["secenekler"]))}
            dogru_harf = secenek_harfleri[s["secenekler"].index(s["cevap"])]

            cur.execute("""
                INSERT INTO kazanim_test_soru
                (kaynak_dosya, kaynak_hash, sinif, ders, konu, test_no, soru_no, soru_metni, secenekler, cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                dosya_yolu.name,
                f_hash,
                11,
                "Felsefe",
                s["konu"],
                1,
                no_sayac,
                s["soru"],
                json.dumps(secenek_map, ensure_ascii=False),
                dogru_harf
            ))
            no_sayac += 1
        farabi.commit()
        logging.info("farabi.kazanim_test_soru: 11. sınıf için %d Felsefe sorusu kaydedildi.", no_sayac - 1)

    havuz.close()
    farabi.close()


if __name__ == "__main__":
    calistir()
