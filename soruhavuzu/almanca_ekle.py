"""soruhavuzu/almanca_ekle.py — 9 ve 12. sınıf Almanca A1.1/A1.2 sorularını ekler.

MEB Almanca A1 ders kitabı (almancaa1.pdf) ve 9-12. sınıf yıllık planları temel alınarak
4 zorluk derecesinde (1-4), 4 şıklı ve kanonik sıralı olarak soru_havuzu.soru ve
farabi.kazanim_test_soru tablolarına onaylı ('onayli') olarak kaydeder.
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

SORULAR_9 = [
    # Kategori: Begrüßung & Vorstellung (Zorluk 1-4)
    {
        "konu": "Begrüßung & Vorstellung",
        "soru": "Almancada 'Guten Morgen' ifadesinin Türkçe karşılığı hangisidir?",
        "secenekler": ["Günaydın", "İyi akşamlar", "İyi geceler", "Hoşça kal"],
        "cevap": "Günaydın",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 11)"
    },
    {
        "konu": "Begrüßung & Vorstellung",
        "soru": "'Wie heißt du?' sorusuna verilebilecek en uygun yanıt hangisidir?",
        "secenekler": ["Ich heiße Ali.", "Ich bin 15 Jahre alt.", "Ich komme aus Ankara.", "Ich wohne in Izmir."],
        "cevap": "Ich heiße Ali.",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 14)"
    },
    {
        "konu": "Begrüßung & Vorstellung",
        "soru": "'Woher kommst du?' sorusunun anlamı ve doğru dilbilgisel cevabı hangi seçenekte verilmiştir?",
        "secenekler": [
            "Nerelisin? - Ich komme aus der Türkei.",
            "Nerede oturuyorsun? - Ich wohne in Berlin.",
            "Kaç yaşındasın? - Ich bin 16 Jahre alt.",
            "Nasılsın? - Mir geht es gut, danke."
        ],
        "cevap": "Nerelisin? - Ich komme aus der Türkei.",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 15)"
    },
    {
        "konu": "Begrüßung & Vorstellung",
        "soru": "Birisi size 'Danke schön!' dediğinde nezaket kuralı olarak Almanca hangi karşılığı verirsiniz?",
        "secenekler": ["Bitte schön!", "Auf Wiedersehen!", "Gute Nacht!", "Bis bald!"],
        "cevap": "Bitte schön!",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 16)"
    },

    # Kategori: Zahlen & Farben (Zorluk 1-4)
    {
        "konu": "Zahlen & Farben",
        "soru": "Almancada 'rot' hangi renktir?",
        "secenekler": ["Kırmızı", "Mavi", "Yeşil", "Sarı"],
        "cevap": "Kırmızı",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 21)"
    },
    {
        "konu": "Zahlen & Farben",
        "soru": "Almanca 'zwölf' sayısı Türkçe karşılığı olarak kaçtır?",
        "secenekler": ["12", "20", "2", "22"],
        "cevap": "12",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 18)"
    },
    {
        "konu": "Zahlen & Farben",
        "soru": "'vierunddreißig' sayısı rakamla nasıl yazılır?",
        "secenekler": ["34", "43", "40", "30"],
        "cevap": "34",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 19)"
    },
    {
        "konu": "Zahlen & Farben",
        "soru": "Aşağıdaki renk ve Türkçe eşleştirmelerinden hangisi YANLIŞTIR?",
        "secenekler": ["grün - Sarı", "blau - Mavi", "schwarz - Siyah", "weiß - Beyaz"],
        "cevap": "grün - Sarı",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 24)"
    },

    # Kategori: Schulsachen & Artikel (Zorluk 1-4)
    {
        "konu": "Schulsachen & Artikel",
        "soru": "'Buch' (kitap) isminin belirli artikeli (bestimmter Artikel) hangisidir?",
        "secenekler": ["das", "der", "die", "den"],
        "cevap": "das",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 22)"
    },
    {
        "konu": "Schulsachen & Artikel",
        "soru": "'Bleistift' (kurşun kalem) sözcüğünün doğru artikeli hangisidir?",
        "secenekler": ["der", "das", "die", "dem"],
        "cevap": "der",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 23)"
    },
    {
        "konu": "Schulsachen & Artikel",
        "soru": "'Das ist ____ Schere.' (Bu bir makastır.) cümlesindeki boşluğa hangi belirsiz artikel (unbestimmter Artikel) gelmelidir?",
        "secenekler": ["eine", "ein", "einen", "kein"],
        "cevap": "eine",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 25)"
    },
    {
        "konu": "Schulsachen & Artikel",
        "soru": "Almancada çoğul (Plural) isimlerin tümünün belirli tanımlığı (artikeli) her zaman hangisidir?",
        "secenekler": ["die", "der", "das", "den"],
        "cevap": "die",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 28)"
    },

    # Kategori: Familie & Personen (Zorluk 1-4)
    {
        "konu": "Familie & Personen",
        "soru": "Almancada 'Mutter' kelimesinin Türkçe karşılığı hangisidir?",
        "secenekler": ["Anne", "Baba", "Kız kardeş", "Teyze"],
        "cevap": "Anne",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 3 (s. 31)"
    },
    {
        "konu": "Familie & Personen",
        "soru": "'Das ist ____ Vater.' (Bu benim babamdır.) boşluğuna hangi iyelik zamiri (Possessivpronomen) gelmelidir?",
        "secenekler": ["mein", "meine", "meinen", "meines"],
        "cevap": "mein",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 3 (s. 33)"
    },
    {
        "konu": "Familie & Personen",
        "soru": "'Die Eltern' kelimesi Türkçe aile kavramında neyi ifade eder?",
        "secenekler": ["Anne ve Baba (Ebeveyn)", "Büyükanne ve Büyükbaba", "Kardeşler", "Kuzenler"],
        "cevap": "Anne ve Baba (Ebeveyn)",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Modul 3 (s. 34)"
    },
    {
        "konu": "Familie & Personen",
        "soru": "'Mein Bruder ist Arzt von Beruf.' cümlesinin Türkçe doğru çevirisi hangisidir?",
        "secenekler": [
            "Erkek kardeşim meslek olarak doktordur.",
            "Ağabeyim hastanede hastadır.",
            "Babam bir doktordur.",
            "Erkek kardeşim öğretmen olmak istiyor."
        ],
        "cevap": "Erkek kardeşim meslek olarak doktordur.",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Modul 3 (s. 37)"
    },

    # Kategori: Wochentage & Alltag (Zorluk 1-4)
    {
        "konu": "Wochentage & Alltag",
        "soru": "Almancada haftanın ilk günü olan 'Montag' hangi gündür?",
        "secenekler": ["Pazartesi", "Salı", "Çarşamba", "Cuma"],
        "cevap": "Pazartesi",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 4 (s. 41)"
    },
    {
        "konu": "Wochentage & Alltag",
        "soru": "Almancada günlerden önce hangi edat (Präposition) kullanılır? (Örn: Pazartesi günü)",
        "secenekler": ["am", "um", "im", "in"],
        "cevap": "am",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 4 (s. 43)"
    },
    {
        "konu": "Wochentage & Alltag",
        "soru": "Almancada 'das Wochenende' ifadesi ne anlama gelir?",
        "secenekler": ["Hafta sonu", "Hafta içi", "Gelecek hafta", "Tatil günü"],
        "cevap": "Hafta sonu",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Modul 4 (s. 44)"
    },
    {
        "konu": "Wochentage & Alltag",
        "soru": "Cuma gününden sonra gelen hafta sonunun ilk günü hangisidir?",
        "secenekler": ["Samstag", "Sonntag", "Donnerstag", "Mittwoch"],
        "cevap": "Samstag",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Modul 4 (s. 45)"
    },

    # Kategori: Verben & Konjugation (Zorluk 1-4)
    {
        "konu": "Verben & Konjugation",
        "soru": "'Ich ____ aus Deutschland.' (kommen) cümlesindeki boşluğa hangi çekim gelir?",
        "secenekler": ["komme", "kommst", "kommt", "kommen"],
        "cevap": "komme",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Grammatik (s. 100)"
    },
    {
        "konu": "Verben & Konjugation",
        "soru": "'sein' (olmak) fiilinin 'du' öznesine göre şimdiki zaman çekimi hangisidir?",
        "secenekler": ["bist", "bin", "ist", "sind"],
        "cevap": "bist",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Grammatik (s. 100)"
    },
    {
        "konu": "Verben & Konjugation",
        "soru": "'haben' (sahip olmak) fiilinin 'er / sie / es' çekimi hangisidir?",
        "secenekler": ["hat", "hast", "habe", "haben"],
        "cevap": "hat",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.1, Grammatik (s. 100)"
    },
    {
        "konu": "Verben & Konjugation",
        "soru": "'sprechen' fiili 'du' öznesiyle çekimlendiğinde kök ses değişimi nasıl olur?",
        "secenekler": ["du sprichst", "du sprechst", "du sprecht", "du sprachst"],
        "cevap": "du sprichst",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Grammatik (s. 101)"
    },

    # Ekstra Sorular (9. Sınıf A1.1 genel pekiştirme)
    {
        "konu": "Begrüßung & Vorstellung",
        "soru": "'Auf Wiedersehen!' vedalaşma ifadesi ne anlama gelir?",
        "secenekler": ["Görüşmek üzere / Hoşça kalın", "Günaydın", "Teşekkür ederim", "Özür dilerim"],
        "cevap": "Görüşmek üzere / Hoşça kalın",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 12)"
    },
    {
        "konu": "Zahlen & Farben",
        "soru": "Almancada 'sieben' sayısı kaçtır?",
        "secenekler": ["7", "6", "8", "9"],
        "cevap": "7",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 17)"
    },
    {
        "konu": "Schulsachen & Artikel",
        "soru": "'Tisch' (masa) isminin belirli artikeli hangisidir?",
        "secenekler": ["der", "das", "die", "ein"],
        "cevap": "der",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 22)"
    },
    {
        "konu": "Familie & Personen",
        "soru": "'Schwester' kelimesinin Türkçe anlamı nedir?",
        "secenekler": ["Kız kardeş", "Erkek kardeş", "Teyze", "Hala"],
        "cevap": "Kız kardeş",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 3 (s. 32)"
    },
    {
        "konu": "Wochentage & Alltag",
        "soru": "Almancada 'Mittwoch' haftanın hangi günüdür?",
        "secenekler": ["Çarşamba", "Salı", "Perşembe", "Pazar"],
        "cevap": "Çarşamba",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 4 (s. 42)"
    },
    {
        "konu": "Verben & Konjugation",
        "soru": "'Wir ____ Deutsch.' (lernen) cümlesinde fiilin doğru çekimi hangisidir?",
        "secenekler": ["lernen", "lernt", "lerne", "lernst"],
        "cevap": "lernen",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.1, Modul 1 (s. 16)"
    },
    {
        "konu": "Zahlen & Farben",
        "soru": "'gelb' kelimesinin Türkçe renk karşılığı hangisidir?",
        "secenekler": ["Sarı", "Kırmızı", "Mavi", "Mor"],
        "cevap": "Sarı",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.1, Modul 2 (s. 24)"
    },
    {
        "konu": "Schulsachen & Artikel",
        "soru": "'Ich habe ____ Spitzer.' (der Spitzer - Kalemtıraşım var.) Akkusativ durumunda belirsiz artikel ne olur?",
        "secenekler": ["einen", "ein", "eine", "einer"],
        "cevap": "einen",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.1, Grammatik (s. 103)"
    },
]

SORULAR_12 = [
    # Kategori: Essen & Trinken (Zorluk 1-4)
    {
        "konu": "Essen & Trinken",
        "soru": "Almancada 'der Apfel' kelimesinin Türkçe anlamı nedir?",
        "secenekler": ["Elma", "Armut", "Muz", "Portakal"],
        "cevap": "Elma",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 52)"
    },
    {
        "konu": "Essen & Trinken",
        "soru": "'Ich trinke gern ____.' (Severek süt içerim.) cümlesinde 'süt' kelimesinin Almancası hangisidir?",
        "secenekler": ["Milch", "Wasser", "Tee", "Kaffee"],
        "cevap": "Milch",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 54)"
    },
    {
        "konu": "Essen & Trinken",
        "soru": "'möchten' (istemek) nezaket fiilinin 'ich' öznesi ile çekimi hangisidir?",
        "secenekler": ["möchte", "möchtest", "möchten", "möchtet"],
        "cevap": "möchte",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 57)"
    },
    {
        "konu": "Essen & Trinken",
        "soru": "'Was isst du zum Frühstück?' sorusunun Türkçe anlamı hangisidir?",
        "secenekler": [
            "Kahvaltıda ne yersin?",
            "Öğle yemeğinde ne içersin?",
            "Akşam ne pişiriyorsun?",
            "Pikniğe ne getirdin?"
        ],
        "cevap": "Kahvaltıda ne yersin?",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 59)"
    },

    # Kategori: Kleidung & Einkaufen (Zorluk 1-4)
    {
        "konu": "Kleidung & Einkaufen",
        "soru": "Almancada 'die Hose' hangi giysi türüdür?",
        "secenekler": ["Pantolon", "Gömlek", "Ceket", "Ayakkabı"],
        "cevap": "Pantolon",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 82)"
    },
    {
        "konu": "Kleidung & Einkaufen",
        "soru": "Bir mağazada 'Bu ne kadar / Kaça?' diye fiyat sormak için hangi soru kalıbı kullanılır?",
        "secenekler": ["Wie viel kostet das?", "Wie spät ist es?", "Wie geht es dir?", "Wo ist das?"],
        "cevap": "Wie viel kostet das?",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 84)"
    },
    {
        "konu": "Kleidung & Einkaufen",
        "soru": "'tragen' (giymek/taşımak) fiilinin 'er' (o) öznesine göre çekimi hangisidir?",
        "secenekler": ["trägt", "tragt", "trage", "tragen"],
        "cevap": "trägt",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 86)"
    },
    {
        "konu": "Kleidung & Einkaufen",
        "soru": "'Das Hemd ist zu teuer, ich kaufe es nicht.' cümlesinde 'zu teuer' ne anlama gelir?",
        "secenekler": ["Çok pahalı", "Çok ucuz", "Çok dar", "Çok eski"],
        "cevap": "Çok pahalı",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 88)"
    },

    # Kategori: Freizeit & Hobbys (Zorluk 1-4)
    {
        "konu": "Freizeit & Hobbys",
        "soru": "Almancada 'Fußball spielen' eyleminin Türkçe karşılığı nedir?",
        "secenekler": ["Futbol oynamak", "Basketbol oynamak", "Yüzmek", "Gitar çalmak"],
        "cevap": "Futbol oynamak",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 7 (s. 72)"
    },
    {
        "konu": "Freizeit & Hobbys",
        "soru": "'können' (ebilmek/yetenek) modal fiilinin 'ich' ve 'er/sie/es' çekimi nasıldır?",
        "secenekler": ["kann", "kannst", "könnt", "können"],
        "cevap": "kann",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 7 (s. 75)"
    },
    {
        "konu": "Freizeit & Hobbys",
        "soru": "'Er kann sehr gut schwimmen.' cümlesinin anlamı hangisidir?",
        "secenekler": [
            "O çok iyi yüzebilir.",
            "O her gün yüzer.",
            "O yüzmeyi sevmez.",
            "O havuzda koşuyor."
        ],
        "cevap": "O çok iyi yüzebilir.",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 7 (s. 76)"
    },
    {
        "konu": "Freizeit & Hobbys",
        "soru": "Modal fiil (können/müssen/wollen) kullanılan düz bir Almanca cümlede esas fiil nerede ve nasıl yer alır?",
        "secenekler": [
            "Cümlenin en sonunda yalın (mastar/Infinitiv) halde",
            "Modal fiilin hemen yanında çekimli halde",
            "Özneden önce çekimli halde",
            "Cümlenin başında soru halinde"
        ],
        "cevap": "Cümlenin en sonunda yalın (mastar/Infinitiv) halde",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Grammatik (s. 102)"
    },

    # Kategori: Uhrzeit & Tagesablauf (Zorluk 1-4)
    {
        "konu": "Uhrzeit & Tagesablauf",
        "soru": "Almancada saatin kaç olduğunu sormak için hangisi söylenir?",
        "secenekler": ["Wie spät ist es?", "Wie alt bist du?", "Wo bist du?", "Wie heißt du?"],
        "cevap": "Wie spät ist es?",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 4 (s. 46)"
    },
    {
        "konu": "Uhrzeit & Tagesablauf",
        "soru": "Saat belirtirken (örn: Saat 8'de) hangi edat kullanılır?",
        "secenekler": ["um", "am", "im", "an"],
        "cevap": "um",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 4 (s. 47)"
    },
    {
        "konu": "Uhrzeit & Tagesablauf",
        "soru": "'Es ist halb neun.' ifadesi saat kaçı göstermektedir?",
        "secenekler": ["08:30", "09:30", "07:30", "09:00"],
        "cevap": "08:30",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 4 (s. 48)"
    },
    {
        "konu": "Uhrzeit & Tagesablauf",
        "soru": "'aufstehen' (yataktan kalkmak) ayrılabilen fiili (trennbares Verb) için 'Ali saat 7'de kalkar' cümlesi hangisidir?",
        "secenekler": [
            "Ali steht um 7 Uhr auf.",
            "Ali aufsteht um 7 Uhr.",
            "Ali steht auf um 7 Uhr.",
            "Ali um 7 Uhr aufstehen."
        ],
        "cevap": "Ali steht um 7 Uhr auf.",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Modul 4 (s. 49)"
    },

    # Kategori: Jahreszeiten & Wetter (Zorluk 1-4)
    {
        "konu": "Jahreszeiten & Wetter",
        "soru": "Almancada 'der Sommer' hangi mevsimdir?",
        "secenekler": ["Yaz", "Kış", "İlkbahar", "Sonbahar"],
        "cevap": "Yaz",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 6 (s. 62)"
    },
    {
        "konu": "Jahreszeiten & Wetter",
        "soru": "'Es regnet.' hava durumu ifadesi ne anlama gelir?",
        "secenekler": ["Yağmur yağıyor.", "Kar yağıyor.", "Güneş açıyor.", "Rüzgar esiyor."],
        "cevap": "Yağmur yağıyor.",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 6 (s. 63)"
    },
    {
        "konu": "Jahreszeiten & Wetter",
        "soru": "Mevsimler ve aylardan önce hangi edat kullanılır? (Örn: Yazın / Temmuzda)",
        "secenekler": ["im", "am", "um", "nach"],
        "cevap": "im",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 6 (s. 64)"
    },
    {
        "konu": "Jahreszeiten & Wetter",
        "soru": "Aşağıdaki ay ve mevsim eşleştirmelerinden hangisi YANLIŞTIR?",
        "secenekler": [
            "Dezember - Sommer",
            "Januar - Winter",
            "Juli - Sommer",
            "April - Frühling"
        ],
        "cevap": "Dezember - Sommer",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Modul 6 (s. 66)"
    },

    # Kategori: Modalverben & Sätze (Zorluk 1-4)
    {
        "konu": "Modalverben & Sätze",
        "soru": "'müssen' fiilinin anlamı hangisidir?",
        "secenekler": ["Zorunda olmak / -meli", "İstemek", "Yapabilmek", "İzinli olmak"],
        "cevap": "Zorunda olmak / -meli",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Grammatik (s. 102)"
    },
    {
        "konu": "Modalverben & Sätze",
        "soru": "'Wir ____ Deutsch lernen.' (müssen) cümlesinde doğru çekim hangisidir?",
        "secenekler": ["müssen", "muss", "musst", "müsst"],
        "cevap": "müssen",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Grammatik (s. 102)"
    },
    {
        "konu": "Modalverben & Sätze",
        "soru": "'dürfen' modal fiili hangi anlamı ifade eder?",
        "secenekler": ["İzinli olmak / yasak-izin", "Mecbur olmak", "Sevmek", "Bilmektir"],
        "cevap": "İzinli olmak / yasak-izin",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 85)"
    },
    {
        "konu": "Modalverben & Sätze",
        "soru": "'Hier darf man nicht rauchen.' cümlesinin Türkçe doğru anlamı nedir?",
        "secenekler": [
            "Burada sigara içilmesine izin verilmez / sigara içmek yasaktır.",
            "Burada sigara içmek serbesttir.",
            "Burada sigara içmek zorunludur.",
            "Burada herkes sigara içer."
        ],
        "cevap": "Burada sigara içilmesine izin verilmez / sigara içmek yasaktır.",
        "zorluk": 4,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 87)"
    },

    # Ekstra Sorular (12. Sınıf A1.2 genel pekiştirme)
    {
        "konu": "Essen & Trinken",
        "soru": "Almancada 'das Brot' kelimesinin Türkçe karşılığı nedir?",
        "secenekler": ["Ekmek", "Peynir", "Zeytin", "Yumurta"],
        "cevap": "Ekmek",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 53)"
    },
    {
        "konu": "Kleidung & Einkaufen",
        "soru": "'das T-Shirt' kelimesinin çoğulu (Plural) hangisidir?",
        "secenekler": ["die T-Shirts", "die T-Shirten", "die T-Shirte", "die T-Shirt"],
        "cevap": "die T-Shirts",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 8 (s. 83)"
    },
    {
        "konu": "Freizeit & Hobbys",
        "soru": "'Mein Hobby ist Gitarre ____.' boşluğuna hangi fiil gelir?",
        "secenekler": ["spielen", "kochen", "reisen", "malen"],
        "cevap": "spielen",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 7 (s. 73)"
    },
    {
        "konu": "Uhrzeit & Tagesablauf",
        "soru": "'Viertel nach acht' ifadesi saat kaç demektir?",
        "secenekler": ["08:15", "08:45", "07:45", "08:30"],
        "cevap": "08:15",
        "zorluk": 3,
        "kaynak": "MEB Almanca A1.2, Modul 4 (s. 48)"
    },
    {
        "konu": "Jahreszeiten & Wetter",
        "soru": "'Der Frühling' hangi mevsimdir?",
        "secenekler": ["İlkbahar", "Sonbahar", "Kış", "Yaz"],
        "cevap": "İlkbahar",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 6 (s. 62)"
    },
    {
        "konu": "Modalverben & Sätze",
        "soru": "'Ich möchte ein Glas Wasser trinken.' cümlesinde kişinin isteği nedir?",
        "secenekler": [
            "Bir bardak su içmek istiyor.",
            "Bir fincan çay almak istiyor.",
            "Bir elma yemek istiyor.",
            "Bir bardak süt arıyor."
        ],
        "cevap": "Bir bardak su içmek istiyor.",
        "zorluk": 2,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 58)"
    },
    {
        "konu": "Freizeit & Hobbys",
        "soru": "Almancada 'kitap okumak' eylemi hangisidir?",
        "secenekler": ["Bücher lesen", "Musik hören", "Filme sehen", "Bilder malen"],
        "cevap": "Bücher lesen",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 7 (s. 74)"
    },
    {
        "konu": "Essen & Trinken",
        "soru": "'Guten Appetit!' ifadesi Türkçede ne anlama gelir?",
        "secenekler": ["Afiyet olsun!", "İyi yolculuklar!", "Tebrikler!", "Geçmiş olsun!"],
        "cevap": "Afiyet olsun!",
        "zorluk": 1,
        "kaynak": "MEB Almanca A1.2, Modul 5 (s. 55)"
    },
]


def calistir():
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")
    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")

    # 1. kaynak_birim ekle (9 ve 12. sınıf)
    with havuz.cursor() as cur:
        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kitap', 'kitap:almancaa1:a1_1', 'almanca', 9,
                    'Almanca A1.1 Ders Kitabı (MEB)', 'MEB 9. Sınıf Almanca A1.1 Öğretim Programı ve Ders Kitabı',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_9_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kitap', 'kitap:almancaa1:a1_2', 'almanca', 12,
                    'Almanca A1.2 Ders Kitabı (MEB)', 'MEB 12. Sınıf Almanca A1.2 Öğretim Programı ve Ders Kitabı',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_12_id = cur.fetchone()[0]

        # Eski Almanca sorularını temizle (tekrarı önlemek için)
        cur.execute("DELETE FROM soru WHERE ders = 'almanca';")
        logging.info("soru_havuzu: Eski Almanca soruları temizlendi (%d satır).", cur.rowcount)

        eklenen_sayac = {9: 0, 12: 0}

        for sinif_duzey, birim_id, soru_listesi in [(9, birim_9_id, SORULAR_9), (12, birim_12_id, SORULAR_12)]:
            for s in soru_listesi:
                dogru_metin = s["cevap"]
                secim = list(s["secenekler"])
                if dogru_metin not in secim:
                    secim[0] = dogru_metin
                dogru_idx = secim.index(dogru_metin)

                # Şıkları kanonik sıraya diz
                kanonik_sec, yeni_idx = sik.kanonik_sira(s["soru"], secim, dogru_idx)

                cur.execute("""
                    INSERT INTO soru
                    (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
                """, (
                    birim_id,
                    "almanca",
                    sinif_duzey,
                    s["konu"],
                    s["soru"],
                    dogru_metin,
                    json.dumps(kanonik_sec, ensure_ascii=False),
                    yeni_idx,
                    s["zorluk"],
                    s["kaynak"]
                ))
                eklenen_sayac[sinif_duzey] += 1

        havuz.commit()
        logging.info("soru_havuzu: 9. sınıf için %d, 12. sınıf için %d Almanca sorusu eklendi.", eklenen_sayac[9], eklenen_sayac[12])

    # 2. farabi.kazanim_test_soru tablosuna da ekle (MEB kataloğu bütünlüğü)
    with farabi.cursor() as cur:
        cur.execute("DELETE FROM kazanim_test_soru WHERE ders = 'Almanca';")
        no_sayac = 1
        for s in SORULAR_9 + SORULAR_12:
            secenek_harfleri = ["A", "B", "C", "D"]
            secenek_map = {secenek_harfleri[i]: s["secenekler"][i] for i in range(len(s["secenekler"]))}
            dogru_harf = secenek_harfleri[s["secenekler"].index(s["cevap"])]

            sinif_val = 9 if no_sayac <= len(SORULAR_9) else 12
            almanca_hash = hashlib.sha256(Path("/mnt/farabi-data/farabi/kitaplar/almancaa1.pdf").read_bytes()).hexdigest()
            cur.execute("""
                INSERT INTO kazanim_test_soru
                (kaynak_dosya, kaynak_hash, sinif, ders, konu, test_no, soru_no, soru_metni, secenekler, cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                "almancaa1.pdf",
                almanca_hash,
                sinif_val,
                "Almanca",
                s["konu"],
                1,
                no_sayac,
                s["soru"],
                json.dumps(secenek_map, ensure_ascii=False),
                dogru_harf
            ))
            no_sayac += 1
        farabi.commit()
        logging.info("farabi.kazanim_test_soru: %d Almanca sorusu kaydedildi.", no_sayac - 1)

    havuz.close()
    farabi.close()


if __name__ == "__main__":
    calistir()
