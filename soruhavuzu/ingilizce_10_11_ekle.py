"""soruhavuzu/ingilizce_10_11_ekle.py — 10 ve 11. sınıf İngilizce sorularını ekler.

MEB 10. Sınıf ve 11. Sınıf İngilizce Öğretim Programı ve Yıllık Planlarındaki temalara uygun olarak:
- 10. Sınıf: School Life, Plans, Legendary Figures, Traditions, Travel, Helpful Tips, Food & Festivals, Digital Era, Modern Heroes, Shopping.
- 11. Sınıf: Future Jobs, Hobbies & Skills, Hard Times, What a Life, Back to the Past, Open Your Heart, Facts About Turkey, Sports, Friends, Values & Norms.

Her tema için 1-4 zorluk derecelerinde, 4 şıklı ve kanonik sıralı sorular oluşturur;
ayrıca 12. sınıf MEB Kazanım havuzundaki uygun kazanım sorularını 10 ve 11. sınıflara bağlayarak
soru_havuzu.soru ve farabi.kazanim_test_soru tablolarına onaylı ('onayli') olarak kaydeder.
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

# 10. SINIF MÜFREDAT SORULARI (10 Tema x 4 Soru = 40 Soru)
SORULAR_10 = [
    # Tema 1: School Life & Routines
    {
        "konu": "School Life & Routines",
        "soru": "Which sentence describes a daily school routine correctly?",
        "secenekler": ["I always arrive at school before eight o'clock.", "I am arriving at school yesterday.", "I will arrive school tomorrow morning.", "I arrived school right now."],
        "cevap": "I always arrive at school before eight o'clock.",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 1: School Life"
    },
    {
        "konu": "School Life & Routines",
        "soru": "'My brother ____ physics at university this semester.' Fill in the blank with the appropriate present tense.",
        "secenekler": ["is studying", "studies", "studied", "study"],
        "cevap": "is studying",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 1: School Life"
    },
    {
        "konu": "School Life & Routines",
        "soru": "Choose the word that describes a person who always finishes homework on time and keeps notes organized.",
        "secenekler": ["disciplined", "impatient", "clumsy", "forgetful"],
        "cevap": "disciplined",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 1: School Life"
    },
    {
        "konu": "School Life & Routines",
        "soru": "In academic schedules, which frequency adverb indicates that an event never fails to take place?",
        "secenekler": ["invariably", "rarely", "seldom", "occasionally"],
        "cevap": "invariably",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 1: School Life"
    },

    # Tema 2: Plans & Predictions
    {
        "konu": "Plans & Predictions",
        "soru": "'Look at those dark clouds! It ____ rain soon.' Which structure is used for predictions based on present evidence?",
        "secenekler": ["is going to", "will", "was going to", "must be"],
        "cevap": "is going to",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 2: Plans"
    },
    {
        "konu": "Plans & Predictions",
        "soru": "'I have already booked the flight ticket. I ____ to London next Monday.' Which form expresses a fixed future arrangement?",
        "secenekler": ["am flying", "will fly", "fly", "flew"],
        "cevap": "am flying",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 2: Plans"
    },
    {
        "konu": "Plans & Predictions",
        "soru": "'Don't worry, I promise I ____ you as soon as I arrive at the station.' Fill in the blank.",
        "secenekler": ["will call", "am calling", "called", "have called"],
        "cevap": "will call",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 2: Plans"
    },
    {
        "konu": "Plans & Predictions",
        "soru": "Which sentence expresses a spontaneous decision made at the moment of speaking?",
        "secenekler": [
            "The phone is ringing; I will answer it.",
            "I am going to study medicine next year.",
            "The train departs at 09:30 tomorrow.",
            "We are meeting the principal on Friday."
        ],
        "cevap": "The phone is ringing; I will answer it.",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 2: Plans"
    },

    # Tema 3: Legendary Figures
    {
        "konu": "Legendary Figures",
        "soru": "'Mustafa Kemal Atatürk ____ born in Thessaloniki in 1881.' Fill in the blank.",
        "secenekler": ["was", "were", "is", "has been"],
        "cevap": "was",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 3: Legendary Figures"
    },
    {
        "konu": "Legendary Figures",
        "soru": "'Marie Curie ____ the Nobel Prize in two different scientific fields.' Which past form is correct?",
        "secenekler": ["won", "winned", "was winning", "wins"],
        "cevap": "won",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 3: Legendary Figures"
    },
    {
        "konu": "Legendary Figures",
        "soru": "Which word describes a person who shows exceptional courage and dedication for the benefit of their nation?",
        "secenekler": ["heroic", "cowardly", "arrogant", "hesitant"],
        "cevap": "heroic",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 3: Legendary Figures"
    },
    {
        "konu": "Legendary Figures",
        "soru": "'Fatih Sultan Mehmet conquered Istanbul in 1453, which ____ an end to the Middle Ages.' Choose the correct verb.",
        "secenekler": ["put", "putted", "has put", "had been put"],
        "cevap": "put",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 3: Legendary Figures"
    },

    # Tema 4: Traditions & Habits
    {
        "konu": "Traditions & Habits",
        "soru": "'My grandfather ____ walk five kilometers every morning when he was young.' Which structure indicates a past habit?",
        "secenekler": ["used to", "is used to", "uses to", "was used to"],
        "cevap": "used to",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 4: Traditions"
    },
    {
        "konu": "Traditions & Habits",
        "soru": "In Turkish hospitality traditions, what do hosts traditionally offer to visitors as a welcoming gesture?",
        "secenekler": ["Turkish delight and tea", "Salt and vinegar", "Bread and butter", "Ice cubes and soda"],
        "cevap": "Turkish delight and tea",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 4: Traditions"
    },
    {
        "konu": "Traditions & Habits",
        "soru": "'We ____ have mobile phones in our childhood, so we played traditional street games.' Fill in the blank.",
        "secenekler": ["didn't use to", "used to not", "aren't used to", "weren't used to"],
        "cevap": "didn't use to",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 4: Traditions"
    },
    {
        "konu": "Traditions & Habits",
        "soru": "Which term refers to cultural practices and customs passed down from generation to generation?",
        "secenekler": ["cultural heritage", "digital transformation", "modern innovation", "commercial trade"],
        "cevap": "cultural heritage",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 4: Traditions"
    },

    # Tema 5: Travel & Experiences
    {
        "konu": "Travel & Experiences",
        "soru": "'____ you ever visited Cappadocia and seen the fairy chimneys?' Choose the correct auxiliary verb.",
        "secenekler": ["Have", "Did", "Were", "Are"],
        "cevap": "Have",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 5: Travel"
    },
    {
        "konu": "Travel & Experiences",
        "soru": "'She has lived in Antalya ____ three years.' Which preposition indicates duration in Present Perfect?",
        "secenekler": ["for", "since", "during", "at"],
        "cevap": "for",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 5: Travel"
    },
    {
        "konu": "Travel & Experiences",
        "soru": "'I visited Pamukkale ____ 2021, and I haven't forgotten its beauty since then.' Fill in the blank.",
        "secenekler": ["in", "since", "for", "ago"],
        "cevap": "in",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 5: Travel"
    },
    {
        "konu": "Travel & Experiences",
        "soru": "What is the difference between 'has gone to Rome' and 'has been to Rome'?",
        "secenekler": [
            "'Has gone' means still there; 'has been' means went and returned.",
            "'Has gone' means returned; 'has been' means never visited.",
            "'Has gone' refers to past; 'has been' refers to future.",
            "There is no difference in meaning."
        ],
        "cevap": "'Has gone' means still there; 'has been' means went and returned.",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 5: Travel"
    },

    # Tema 6: Helpful Tips & Modals
    {
        "konu": "Helpful Tips & Modals",
        "soru": "'You look very pale and tired. You ____ see a doctor.' Which modal gives advice?",
        "secenekler": ["should", "must not", "can't", "would"],
        "cevap": "should",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 6: Helpful Tips"
    },
    {
        "konu": "Helpful Tips & Modals",
        "soru": "'Drivers ____ obey the traffic lights at all times.' Which modal expresses legal obligation?",
        "secenekler": ["must", "might", "may", "could"],
        "cevap": "must",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 6: Helpful Tips"
    },
    {
        "konu": "Helpful Tips & Modals",
        "soru": "'Tomorrow is Sunday, so I ____ get up early.' Which modal expresses lack of obligation?",
        "secenekler": ["don't have to", "must not", "shouldn't", "can't"],
        "cevap": "don't have to",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 6: Helpful Tips"
    },
    {
        "konu": "Helpful Tips & Modals",
        "soru": "'You ____ touch that exposed electrical wire; it is extremely dangerous!' Which modal expresses strict prohibition?",
        "secenekler": ["must not", "don't have to", "needn't", "might not"],
        "cevap": "must not",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 6: Helpful Tips"
    },

    # Tema 7: Food, Festivals & Quantifiers
    {
        "konu": "Food, Festivals & Quantifiers",
        "soru": "'We don't have ____ milk left in the fridge.' Which quantifier is used in negative sentences?",
        "secenekler": ["any", "some", "many", "a few"],
        "cevap": "any",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 7: Food and Festivals"
    },
    {
        "konu": "Food, Festivals & Quantifiers",
        "soru": "'How ____ olive oil do we need for this traditional recipe?' Choose the correct quantifier.",
        "secenekler": ["much", "many", "few", "any"],
        "cevap": "much",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 7: Food and Festivals"
    },
    {
        "konu": "Food, Festivals & Quantifiers",
        "soru": "'There are only ____ apples in the basket, so we cannot make an apple pie.' Fill in the blank.",
        "secenekler": ["a few", "a little", "much", "any"],
        "cevap": "a few",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 7: Food and Festivals"
    },
    {
        "konu": "Food, Festivals & Quantifiers",
        "soru": "Which traditional Turkish culinary preparation involves wrapping spiced rice in vine leaves?",
        "secenekler": ["Sarma (Stuffed vine leaves)", "Baklava", "Künefe", "Ayran"],
        "cevap": "Sarma (Stuffed vine leaves)",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 7: Food and Festivals"
    },

    # Tema 8: Digital Era & Conditionals
    {
        "konu": "Digital Era & Conditionals",
        "soru": "'If you click on suspicious links, your computer ____ get infected with a virus.' Fill in the blank (Type 1 Conditional).",
        "secenekler": ["will", "would", "had", "was"],
        "cevap": "will",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 8: Digital Era"
    },
    {
        "konu": "Digital Era & Conditionals",
        "soru": "Which security measure is recommended to protect online accounts from unauthorized access?",
        "secenekler": ["Using strong passwords and two-factor authentication", "Sharing passwords with close friends", "Clicking on pop-up advertisements", "Using birthdates as PIN codes"],
        "cevap": "Using strong passwords and two-factor authentication",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 8: Digital Era"
    },
    {
        "konu": "Digital Era & Conditionals",
        "soru": "'Unless you back up your files regularly, you ____ lose your important documents.' Choose the correct modal.",
        "secenekler": ["may", "shouldn't", "haven't", "couldn't"],
        "cevap": "may",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 8: Digital Era"
    },
    {
        "konu": "Digital Era & Conditionals",
        "soru": "What does the technological term 'cyberbullying' specifically refer to?",
        "secenekler": [
            "Harassment and intimidation using digital devices and social media",
            "Downloading high-resolution videos from the internet",
            "Writing computer software code for educational games",
            "Repairing broken computer hardware in laboratories"
        ],
        "cevap": "Harassment and intimidation using digital devices and social media",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 8: Digital Era"
    },

    # Tema 9: Modern Heroes & Relative Clauses
    {
        "konu": "Modern Heroes & Relative Clauses",
        "soru": "'Aziz Sancar is the Turkish scientist ____ won the Nobel Prize in Chemistry in 2015.' Which relative pronoun refers to a person?",
        "secenekler": ["who", "which", "where", "whose"],
        "cevap": "who",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 9: Modern Heroes"
    },
    {
        "konu": "Modern Heroes & Relative Clauses",
        "soru": "'This is the innovative medical device ____ saved thousands of lives during the pandemic.' Which pronoun refers to a thing?",
        "secenekler": ["which", "who", "whom", "where"],
        "cevap": "which",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 9: Modern Heroes"
    },
    {
        "konu": "Modern Heroes & Relative Clauses",
        "soru": "'A philanthropist is a person ____ generous donations support educational and charitable causes.' Choose the correct relative pronoun.",
        "secenekler": ["whose", "who", "which", "whom"],
        "cevap": "whose",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 9: Modern Heroes"
    },
    {
        "konu": "Modern Heroes & Relative Clauses",
        "soru": "'The historical library ____ we conducted our research contains ancient manuscripts from the Ottoman era.' Fill in the blank.",
        "secenekler": ["where", "which", "who", "whose"],
        "cevap": "where",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 9: Modern Heroes"
    },

    # Tema 10: Shopping & Comparatives
    {
        "konu": "Shopping & Comparatives",
        "soru": "'Online shopping is often ____ than shopping in crowded malls.' Choose the correct comparative form of 'convenient'.",
        "secenekler": ["more convenient", "convenienter", "most convenient", "as convenient"],
        "cevap": "more convenient",
        "zorluk": 1,
        "kaynak": "MEB English 10, Theme 10: Shopping"
    },
    {
        "konu": "Shopping & Comparatives",
        "soru": "'This organic cotton shirt is ____ expensive than the synthetic one.' Fill in the blank.",
        "secenekler": ["less", "least", "little", "fewer"],
        "cevap": "less",
        "zorluk": 2,
        "kaynak": "MEB English 10, Theme 10: Shopping"
    },
    {
        "konu": "Shopping & Comparatives",
        "soru": "'Can I have a ____ on this jacket because it has a small scratch on the sleeve?' Which shopping term means price reduction?",
        "secenekler": ["discount", "receipt", "warranty", "refund"],
        "cevap": "discount",
        "zorluk": 3,
        "kaynak": "MEB English 10, Theme 10: Shopping"
    },
    {
        "konu": "Shopping & Comparatives",
        "soru": "When a customer returns a defective product and asks for their money back, what do they request?",
        "secenekler": ["A full refund", "A commercial catalog", "An extra payment", "A shopping trolley"],
        "cevap": "A full refund",
        "zorluk": 4,
        "kaynak": "MEB English 10, Theme 10: Shopping"
    },
]

# 11. SINIF MÜFREDAT SORULARI (10 Tema x 4 Soru = 40 Soru)
SORULAR_11 = [
    # Tema 1: Future Jobs & Careers
    {
        "konu": "Future Jobs & Careers",
        "soru": "Which career field is expected to see dramatic growth due to renewable energy transitions?",
        "secenekler": ["Solar energy engineering", "Coal mining", "Steam locomotive operation", "Typing services"],
        "cevap": "Solar energy engineering",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 1: Future Jobs"
    },
    {
        "konu": "Future Jobs & Careers",
        "soru": "'In thirty years, autonomous robotic systems ____ most repetitive industrial tasks.' Choose the future prediction.",
        "secenekler": ["will be performing", "have performed", "performed", "were performing"],
        "cevap": "will be performing",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 1: Future Jobs"
    },
    {
        "konu": "Future Jobs & Careers",
        "soru": "Which skill is considered a critical soft skill for future interdisciplinary collaborative work?",
        "secenekler": ["Effective communication and emotional intelligence", "Memorizing phone books", "Manual data transcription", "Individual isolation"],
        "cevap": "Effective communication and emotional intelligence",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 1: Future Jobs"
    },
    {
        "konu": "Future Jobs & Careers",
        "soru": "'By the year 2040, aerospace engineers ____ commercial hypersonic travel across oceans.' Choose the future perfect form.",
        "secenekler": ["will have developed", "developed", "are developing", "have developed"],
        "cevap": "will have developed",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 1: Future Jobs"
    },

    # Tema 2: Hobbies & Skills
    {
        "konu": "Hobbies & Skills",
        "soru": "'She is capable of ____ three foreign languages fluently.' Which verb form follows prepositions?",
        "secenekler": ["speaking", "speak", "to speak", "spoken"],
        "cevap": "speaking",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 2: Hobbies and Skills"
    },
    {
        "konu": "Hobbies & Skills",
        "soru": "'After six months of intensive training, he was finally able ____ the marathon.' Fill in the blank.",
        "secenekler": ["to complete", "completing", "complete", "completed"],
        "cevap": "to complete",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 2: Hobbies and Skills"
    },
    {
        "konu": "Hobbies & Skills",
        "soru": "Which expression means possessing a natural talent or aptitude for an artistic or musical endeavor?",
        "secenekler": ["to be gifted in", "to be reluctant to", "to be anxious about", "to be oblivious of"],
        "cevap": "to be gifted in",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 2: Hobbies and Skills"
    },
    {
        "konu": "Hobbies & Skills",
        "soru": "What is the grammatical difference between 'remember to post the letter' and 'remember posting the letter'?",
        "secenekler": [
            "'Remember to do' looks forward to a duty; 'remember doing' recalls a past memory.",
            "'Remember to do' indicates an error; 'remember doing' indicates success.",
            "They both describe future intentions identically.",
            "'Remember doing' can only be used with negative sentences."
        ],
        "cevap": "'Remember to do' looks forward to a duty; 'remember doing' recalls a past memory.",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 2: Hobbies and Skills"
    },

    # Tema 3: Hard Times & Past Continuous
    {
        "konu": "Hard Times & Past Continuous",
        "soru": "'While the firefighters ____ the blaze, residents were safely evacuated.' Fill in the blank.",
        "secenekler": ["were extinguishing", "extinguished", "are extinguishing", "extinguish"],
        "cevap": "were extinguishing",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 3: Hard Times"
    },
    {
        "konu": "Hard Times & Past Continuous",
        "soru": "'I was walking home from school when the severe earthquake ____.' Choose the past simple verb.",
        "secenekler": ["struck", "was striking", "strikes", "has struck"],
        "cevap": "struck",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 3: Hard Times"
    },
    {
        "konu": "Hard Times & Past Continuous",
        "soru": "Which psychological term describes the capacity to recover quickly from difficulties and adapt to hardship?",
        "secenekler": ["Resilience", "Pessimism", "Apathy", "Vulnerability"],
        "cevap": "Resilience",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 3: Hard Times"
    },
    {
        "konu": "Hard Times & Past Continuous",
        "soru": "'By the time the rescue team reached the remote alpine shelter, the mountaineers ____ for thirty hours.'",
        "secenekler": ["had been waiting", "waited", "have waited", "were waiting"],
        "cevap": "had been waiting",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 3: Hard Times"
    },

    # Tema 4: What a Life & Milestones
    {
        "konu": "What a Life & Milestones",
        "soru": "'Stephen Hawking published his groundbreaking book 'A Brief History of Time' ____ 1988.' Choose the preposition.",
        "secenekler": ["in", "on", "at", "for"],
        "cevap": "in",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 4: What a Life"
    },
    {
        "konu": "What a Life & Milestones",
        "soru": "Which word signifies an important stage or turning point in a person's life or historical career?",
        "secenekler": ["Milestone", "Obstacle", "Disruption", "Drawback"],
        "cevap": "Milestone",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 4: What a Life"
    },
    {
        "konu": "What a Life & Milestones",
        "soru": "'Before she graduated from medical school with highest honors, she ____ in volunteer clinics abroad.'",
        "secenekler": ["had already worked", "has worked", "was working", "works"],
        "cevap": "had already worked",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 4: What a Life"
    },
    {
        "konu": "What a Life & Milestones",
        "soru": "Which biographical term describes a literary account written by an author about their own life?",
        "secenekler": ["Autobiography", "Biography", "Anthology", "Monograph"],
        "cevap": "Autobiography",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 4: What a Life"
    },

    # Tema 5: Back to the Past & Inventions
    {
        "konu": "Back to the Past & Inventions",
        "soru": "'In ancient times, philosophers in Anatolia ____ gather in the agora to debate truth and justice.' Which modal indicates past repeated action?",
        "secenekler": ["would", "should", "must", "can"],
        "cevap": "would",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 5: Back to the Past"
    },
    {
        "konu": "Back to the Past & Inventions",
        "soru": "Johannes Gutenberg's movable type printing press in the 15th century revolutionized which aspect of human civilization?",
        "secenekler": ["The rapid dissemination of knowledge and books", "Maritime navigation across uncharted oceans", "Steam engine locomotives and railways", "Aviation and supersonic passenger flights"],
        "cevap": "The rapid dissemination of knowledge and books",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 5: Back to the Past"
    },
    {
        "konu": "Back to the Past & Inventions",
        "soru": "'People ____ have electricity in their homes two hundred years ago, so they relied on oil lamps.' Fill in the blank.",
        "secenekler": ["didn't use to", "used not", "aren't used to", "wouldn't"],
        "cevap": "didn't use to",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 5: Back to the Past"
    },
    {
        "konu": "Back to the Past & Inventions",
        "soru": "Which ancient Anatolian site in Şanlıurfa is recognized as the world's oldest known monumental temple complex?",
        "secenekler": ["Göbeklitepe", "Çatalhöyük", "Hattusha", "Ephesus"],
        "cevap": "Göbeklitepe",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 5: Back to the Past"
    },

    # Tema 6: Open Your Heart & Wishes
    {
        "konu": "Open Your Heart & Wishes",
        "soru": "'I have too much homework tonight. I wish I ____ go to the cinema with you.' Which past form expresses a present wish?",
        "secenekler": ["could", "can", "will", "may"],
        "cevap": "could",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 6: Open Your Heart"
    },
    {
        "konu": "Open Your Heart & Wishes",
        "soru": "'If only I ____ his secret feelings earlier; I wouldn't have made that insensitive joke.' Choose the past perfect form.",
        "secenekler": ["had known", "knew", "know", "have known"],
        "cevap": "had known",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 6: Open Your Heart"
    },
    {
        "konu": "Open Your Heart & Wishes",
        "soru": "Which emotion is defined as the ability to genuinely understand and share the feelings of another individual?",
        "secenekler": ["Empathy", "Apathy", "Hostility", "Indifference"],
        "cevap": "Empathy",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 6: Open Your Heart"
    },
    {
        "konu": "Open Your Heart & Wishes",
        "soru": "'I wish you ____ interrupting me whenever I try to explain my perspective!' Which modal expresses irritation about a habit?",
        "secenekler": ["would stop", "stopped", "had stopped", "will stop"],
        "cevap": "would stop",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 6: Open Your Heart"
    },

    # Tema 7: Facts About Turkey & Passive Voice
    {
        "konu": "Facts About Turkey & Passive Voice",
        "soru": "'The historical Topkapı Palace ____ by thousands of international tourists every week.' Choose the present passive form.",
        "secenekler": ["is visited", "was visited", "visits", "has visited"],
        "cevap": "is visited",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 7: Facts About Turkey"
    },
    {
        "konu": "Facts About Turkey & Passive Voice",
        "soru": "'The majestic Blue Mosque (Sultanahmet) ____ constructed during the reign of Sultan Ahmed I.' Choose the past passive form.",
        "secenekler": ["was", "is", "were", "has"],
        "cevap": "was",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 7: Facts About Turkey"
    },
    {
        "konu": "Facts About Turkey & Passive Voice",
        "soru": "'Anatolia ____ as the cradle of many ancient civilizations throughout millennia.' Fill in the blank with passive present perfect.",
        "secenekler": ["has been regarded", "is regarding", "was regarding", "regards"],
        "cevap": "has been regarded",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 7: Facts About Turkey"
    },
    {
        "konu": "Facts About Turkey & Passive Voice",
        "soru": "Convert active to passive: 'Mimar Sinan designed the Selimiye Mosque in Edirne.'",
        "secenekler": [
            "The Selimiye Mosque in Edirne was designed by Mimar Sinan.",
            "The Selimiye Mosque in Edirne is designed by Mimar Sinan.",
            "Mimar Sinan was designed by the Selimiye Mosque.",
            "The Selimiye Mosque had designed Mimar Sinan in Edirne."
        ],
        "cevap": "The Selimiye Mosque in Edirne was designed by Mimar Sinan.",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 7: Facts About Turkey"
    },

    # Tema 8: Sports & Rules
    {
        "konu": "Sports & Rules",
        "soru": "'In football, players ____ touch the ball with their hands, except for the goalkeeper inside the penalty area.'",
        "secenekler": ["must not", "don't have to", "needn't", "might not"],
        "cevap": "must not",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 8: Sports"
    },
    {
        "konu": "Sports & Rules",
        "soru": "Which extreme sport involves leaping from a high cliff or aircraft while wearing a specialized nylon wingsuit?",
        "secenekler": ["Wingsuit flying", "Table tennis", "Archery", "Bowling"],
        "cevap": "Wingsuit flying",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 8: Sports"
    },
    {
        "konu": "Sports & Rules",
        "soru": "'Athletes ____ maintain strict nutritional discipline and regular cardiovascular training to excel at Olympic levels.'",
        "secenekler": ["have to", "must not", "cannot", "needn't"],
        "cevap": "have to",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 8: Sports"
    },
    {
        "konu": "Sports & Rules",
        "soru": "Which concept defines sporting behavior characterized by fair play, mutual respect for opponents, and ethical integrity?",
        "secenekler": ["Sportsmanship", "Chauvinism", "Antagonism", "Partisanship"],
        "cevap": "Sportsmanship",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 8: Sports"
    },

    # Tema 9: Friends & Deductions
    {
        "konu": "Friends & Deductions",
        "soru": "'His lights are off and his car is gone. He ____ be at home.' Choose the modal of negative deduction.",
        "secenekler": ["can't", "must", "should", "will"],
        "cevap": "can't",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 9: My Friends"
    },
    {
        "konu": "Friends & Deductions",
        "soru": "'She received the highest score on the international biology olympiad. She ____ study remarkably hard.'",
        "secenekler": ["must", "can't", "wouldn't", "shouldn't"],
        "cevap": "must",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 9: My Friends"
    },
    {
        "konu": "Friends & Deductions",
        "soru": "Which adjective describes a loyal friend who can always be trusted to keep confidences and stand by you in adversity?",
        "secenekler": ["Trustworthy", "Deceitful", "Hypocritical", "Self-centered"],
        "cevap": "Trustworthy",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 9: My Friends"
    },
    {
        "konu": "Friends & Deductions",
        "soru": "'Look, Sarah is soaking wet! It ____ raining heavily outside.' Choose the continuous deduction modal.",
        "secenekler": ["must be", "can't be", "should have", "would be"],
        "cevap": "must be",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 9: My Friends"
    },

    # Tema 10: Values, Norms & Past Modals
    {
        "konu": "Values, Norms & Past Modals",
        "soru": "'I failed the history exam yesterday. I ____ studied much harder last week.' Choose the past modal of regret.",
        "secenekler": ["should have", "must have", "can have", "will have"],
        "cevap": "should have",
        "zorluk": 1,
        "kaynak": "MEB English 11, Theme 10: Values and Norms"
    },
    {
        "konu": "Values, Norms & Past Modals",
        "soru": "'The ancient stone inscription is completely illegible. Time and weather ____ eroded the surface.'",
        "secenekler": ["must have", "should have", "can't have", "needn't have"],
        "cevap": "must have",
        "zorluk": 2,
        "kaynak": "MEB English 11, Theme 10: Values and Norms"
    },
    {
        "konu": "Values, Norms & Past Modals",
        "soru": "'You ____ lied to your best friend; honesty is the most fundamental pillar of friendship.'",
        "secenekler": ["shouldn't have", "must have", "could have", "needn't have"],
        "cevap": "shouldn't have",
        "zorluk": 3,
        "kaynak": "MEB English 11, Theme 10: Values and Norms"
    },
    {
        "konu": "Values, Norms & Past Modals",
        "soru": "Which ethical principle asserts that one should treat others with dignity, equality, and impartial fairness?",
        "secenekler": ["Universal justice and moral equity", "Egocentrism and self-interest", "Opportunism and deception", "Blind obedience without reflection"],
        "cevap": "Universal justice and moral equity",
        "zorluk": 4,
        "kaynak": "MEB English 11, Theme 10: Values and Norms"
    },
]


def calistir():
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")
    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")

    # 1. kaynak_birim ekle
    with havuz.cursor() as cur:
        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kazanim', 'kazanim:ingilizce:10_mufredat', 'ingilizce', 10,
                    '10. Sınıf İngilizce Müfredat Soruları', 'MEB 10. Sınıf İngilizce Dersi Yıllık Planı ve Müfredat Soruları',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_10_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kazanim', 'kazanim:ingilizce:11_mufredat', 'ingilizce', 11,
                    '11. Sınıf İngilizce Müfredat Soruları', 'MEB 11. Sınıf İngilizce Dersi Yıllık Planı ve Müfredat Soruları',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_11_id = cur.fetchone()[0]

        # Eski müfredat sorularını temizle (10 ve 11. sınıf)
        cur.execute("DELETE FROM soru WHERE ders = 'ingilizce' AND sinif IN (10, 11);")
        logging.info("soru_havuzu: Eski 10 ve 11. sınıf İngilizce kayıtları temizlendi (%d satır).", cur.rowcount)

        eklenen_sayac = {10: 0, 11: 0}

        for sinif_duzey, birim_id, soru_listesi in [(10, birim_10_id, SORULAR_10), (11, birim_11_id, SORULAR_11)]:
            for s in soru_listesi:
                dogru_metin = s["cevap"]
                secim = list(s["secenekler"])
                if dogru_metin not in secim:
                    secim[0] = dogru_metin
                dogru_idx = secim.index(dogru_metin)

                kanonik_sec, yeni_idx = sik.kanonik_sira(s["soru"], secim, dogru_idx)

                cur.execute("""
                    INSERT INTO soru
                    (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
                """, (
                    birim_id,
                    "ingilizce",
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

        # 2. 12. Sınıf MEB Kazanım sorularından uygun olanları 10 ve 11'e köprüle (~50'şer soru)
        cur.execute("""
            SELECT birim_id, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak
            FROM soru
            WHERE ders = 'ingilizce' AND sinif = 12 AND durum = 'onayli'
              AND length(soru) BETWEEN 30 AND 250
            ORDER BY id;
        """)
        aday_sorular = cur.fetchall()
        logging.info("12. sınıftan köprülenebilir aday soru sayısı: %d", len(aday_sorular))

        kopru_10 = aday_sorular[:50]
        kopru_11 = aday_sorular[50:100]

        for s in kopru_10:
            cur.execute("""
                INSERT INTO soru
                (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                VALUES (%s, 'ingilizce', 10, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
            """, (s[0], s[1], s[2], s[3], json.dumps(s[4], ensure_ascii=False) if isinstance(s[4], list) else s[4], s[5], s[6], s[7]))
            eklenen_sayac[10] += 1

        for s in kopru_11:
            cur.execute("""
                INSERT INTO soru
                (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                VALUES (%s, 'ingilizce', 11, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
            """, (s[0], s[1], s[2], s[3], json.dumps(s[4], ensure_ascii=False) if isinstance(s[4], list) else s[4], s[5], s[6], s[7]))
            eklenen_sayac[11] += 1

        havuz.commit()
        logging.info("soru_havuzu: 10. sınıf için toplam %d, 11. sınıf için toplam %d İngilizce sorusu hazırlandı.", eklenen_sayac[10], eklenen_sayac[11])

    # 3. farabi.kazanim_test_soru tablosuna 10 ve 11. sınıf sorularını ekle
    with farabi.cursor() as cur:
        cur.execute("DELETE FROM kazanim_test_soru WHERE ders ILIKE '%%ingilizce%%' AND sinif IN (10, 11);")
        dosyalar_map = {
            10: (Path("/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027/ingilizce/10. SINIF İNGİLİZCE.docx"), SORULAR_10),
            11: (Path("/mnt/farabi-data/farabi/icerik/11.sinif-ingilizce-yillik-plan-2026-2027-indir.xml"), SORULAR_11),
        }
        for sinif_val, (dosya_yolu, soru_listesi) in dosyalar_map.items():
            f_hash = hashlib.sha256(dosya_yolu.read_bytes()).hexdigest()
            no_sayac = 1
            for s in soru_listesi:
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
                    sinif_val,
                    "İngilizce",
                    s["konu"],
                    1,
                    no_sayac,
                    s["soru"],
                    json.dumps(secenek_map, ensure_ascii=False),
                    dogru_harf
                ))
                no_sayac += 1
        farabi.commit()
        logging.info("farabi.kazanim_test_soru: 10 ve 11. sınıf için İngilizce soruları kaydedildi.")

    havuz.close()
    farabi.close()


if __name__ == "__main__":
    calistir()
