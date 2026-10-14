"""soruhavuzu/bilisim_yapazeka_ekle.py — Bilişim Teknolojileri ve Yazılım (Yapay Zekâ) sorularını ekler.

Kaynak: /mnt/farabi-data/farabi/kitaplar/yapazeka.pdf
T.C. Millî Eğitim Bakanlığı Ortaöğretim Bilişim Teknolojileri ve Yazılım Ders Kitabı:
Yapay Zekâ Uygulamaları (345 Sayfa).

12 Kategori x 4 Zorluk (1-4) = 48 Onaylı Soru.
9, 10, 11 ve 12. sınıfların tamamı için soru_havuzu.soru ve farabi.kazanim_test_soru tablolarına
onaylı ('onayli') olarak kaydeder.
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

PDF_YOLU = Path("/mnt/farabi-data/farabi/kitaplar/yapazeka.pdf")

SORULAR_BILISIM = [
    # 1. Kategori: Veri Bilimi ve Python Temelleri (Zorluk 1-4)
    {
        "konu": "Veri Bilimi ve Python Temelleri",
        "soru": "Ham hâlde bulunan verilerden anlamlı ve faydalı bilgiler çıkarmak için verileri toplama, işleme ve analiz etme sürecine ne ad verilir?",
        "secenekler": ["Veri bilimi", "Veritabanı yöneticiliği", "Donanım mimarisi", "Ağ protokolü"],
        "cevap": "Veri bilimi",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 1. Ünite (s. 16)"
    },
    {
        "konu": "Veri Bilimi ve Python Temelleri",
        "soru": "NumPy kütüphanesinde oluşturulan çok boyutlu bir dizinin boyut sayısını ve şeklini öğrenmek için sırasıyla hangi nitelikler kullanılır?",
        "secenekler": ["ndim ve shape", "size ve length", "dim ve count", "rows ve cols"],
        "cevap": "ndim ve shape",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 1. Ünite (s. 40)"
    },
    {
        "konu": "Veri Bilimi ve Python Temelleri",
        "soru": "Veri bilimcilerin kod yazmanın yanı sıra interaktif açıklamalar, grafikler ve notlar eklemek için yaygın olarak kullandığı çalışma ortamı hangisidir?",
        "secenekler": ["Jupyter Notebook", "Notepad++", "Paint", "Excel Macro"],
        "cevap": "Jupyter Notebook",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 1. Ünite (s. 28)"
    },
    {
        "konu": "Veri Bilimi ve Python Temelleri",
        "soru": "Bir veri kümesinde sayılarla ifade edilemeyen, sınıf ve kategori belirten verilere (örn: kan grubu, şehir adı) ne ad verilir?",
        "secenekler": ["Nitel (Kategorik) veri", "Nicel (Sayısal) veri", "Sürekli veri", "Oransal veri"],
        "cevap": "Nitel (Kategorik) veri",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 1. Ünite (s. 24)"
    },

    # 2. Kategori: Pandas ve Veri Çerçeveleri (Zorluk 1-4)
    {
        "konu": "Pandas ve Veri Çerçeveleri",
        "soru": "Bilgisayarda kayıtlı olan 'veriler.csv' isimli bir dosyayı Pandas veri çerçevesine aktarmak için hangi kod satırı kullanılır?",
        "secenekler": ["pd.read_csv('veriler.csv')", "pd.open_csv('veriler.csv')", "pd.load('veriler.csv')", "pd.import_csv('veriler.csv')"],
        "cevap": "pd.read_csv('veriler.csv')",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 3. Ünite (s. 116)"
    },
    {
        "konu": "Pandas ve Veri Çerçeveleri",
        "soru": "Bir Pandas veri çerçevesinin ilk beş satırını hızlıca görüntülemek için hangi fonksiyon kullanılır?",
        "secenekler": ["head()", "tail()", "info()", "show()"],
        "cevap": "head()",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 4. Ünite (s. 147)"
    },
    {
        "konu": "Pandas ve Veri Çerçeveleri",
        "soru": "Pandas'ta drop() fonksiyonu 'axis=1' parametresi ile çalıştırıldığında veri çerçevesinde ne gerçekleşir?",
        "secenekler": ["Belirli bir sütun silinir", "Belirli bir satır silinir", "Tüm indeksler sıfırlanır", "Tüm veri çerçevesi silinir"],
        "cevap": "Belirli bir sütun silinir",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 3. Ünite (s. 116)"
    },
    {
        "konu": "Pandas ve Veri Çerçeveleri",
        "soru": "Pandas veri çerçevelerinde yapılan silme veya değiştirme işlemlerinin orijinal veri üzerinde kalıcı olması için hangi parametre True yapılmalıdır?",
        "secenekler": ["inplace", "ignore_index", "axis", "copy"],
        "cevap": "inplace",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 3. Ünite (s. 117)"
    },

    # 3. Kategori: Veri Temizleme ve Ön İşleme (Zorluk 1-4)
    {
        "konu": "Veri Temizleme ve Ön İşleme",
        "soru": "Aşağıdakilerden hangisi bir veri setinin güvenilir şekilde işlenebilmesi için gereken kalite şartlarından biri DEĞİLDİR?",
        "secenekler": ["Çokluk", "Doğruluk", "Geçerlik", "Tamlık"],
        "cevap": "Çokluk",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 6. Ünite (s. 199)"
    },
    {
        "konu": "Veri Temizleme ve Ön İşleme",
        "soru": "Bir veri çerçevesindeki eksik (NaN) değerleri çıkarmak ve satırları silmek için hangi Pandas fonksiyonu kullanılır?",
        "secenekler": ["dropna()", "fillna()", "drop_duplicates()", "replace()"],
        "cevap": "dropna()",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 6. Ünite (s. 200)"
    },
    {
        "konu": "Veri Temizleme ve Ön İşleme",
        "soru": "Veri setindeki eksik değerlerin yerine kendisinden bir sonraki geçerli değeri yazmak için fillna() içinde hangi yöntem (method) kullanılır?",
        "secenekler": ["bfill (backward fill)", "ffill (forward fill)", "afill", "mfill"],
        "cevap": "bfill (backward fill)",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 6. Ünite (s. 199)"
    },
    {
        "konu": "Veri Temizleme ve Ön İşleme",
        "soru": "Farklı ölçeklerdeki sayısal değişkenleri ortalaması 0 ve standart sapması 1 olacak şekilde dönüştürme işlemine ne ad verilir?",
        "secenekler": ["StandardScaler (Z-skoru standardizasyonu)", "One-Hot Encoding", "Etiket Kodlama", "Kategorileştirme"],
        "cevap": "StandardScaler (Z-skoru standardizasyonu)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 6. Ünite (s. 200)"
    },

    # 4. Kategori: Veri Görselleştirme (Matplotlib) (Zorluk 1-4)
    {
        "konu": "Veri Görselleştirme (Matplotlib)",
        "soru": "matplotlib.pyplot modülünde çizilen bir grafiğe ana başlık eklemek için hangi komut kullanılır?",
        "secenekler": ["title()", "xlabel()", "ylabel()", "legend()"],
        "cevap": "title()",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 4. Ünite (s. 147)"
    },
    {
        "konu": "Veri Görselleştirme (Matplotlib)",
        "soru": "Bir grafikte oluşturulan çizgi veya veri etiketlerini (açıklama kutusunu) görünür yapmak için hangi komut kullanılır?",
        "secenekler": ["legend()", "subplots()", "grid()", "show()"],
        "cevap": "legend()",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 4. Ünite (s. 148)"
    },
    {
        "konu": "Veri Görselleştirme (Matplotlib)",
        "soru": "Bir veri çerçevesine ait birden fazla alt grafiği tek bir pencerede satır ve sütunlar halinde düzenlemek için hangi fonksiyon kullanılır?",
        "secenekler": ["subplots()", "plots()", "axis()", "figure()"],
        "cevap": "subplots()",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 4. Ünite (s. 147)"
    },
    {
        "konu": "Veri Görselleştirme (Matplotlib)",
        "soru": "Histogram grafiklerinde verilerin gruplandırılacağı aralık (kutu) sayısını belirleyen parametre hangisidir?",
        "secenekler": ["bins", "nrows", "ncols", "linestyle"],
        "cevap": "bins",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 4. Ünite (s. 148)"
    },

    # 5. Kategori: İstatistik ve Korelasyon (Zorluk 1-4)
    {
        "konu": "İstatistik ve Korelasyon",
        "soru": "Bir veri setinde en çok tekrar eden (en yüksek frekansa sahip) değere ne ad verilir?",
        "secenekler": ["Mod (Tepe Değer)", "Medyan (Ortanca)", "Aritmetik Ortalama", "Standart Sapma"],
        "cevap": "Mod (Tepe Değer)",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 2. Ünite (s. 91)"
    },
    {
        "konu": "İstatistik ve Korelasyon",
        "soru": "Küçükten büyüğe sıralanmış bir sayı dizisinin tam ortasında yer alan değere ne ad verilir?",
        "secenekler": ["Medyan (Ortanca)", "Mod", "Varyans", "Açıklık"],
        "cevap": "Medyan (Ortanca)",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 2. Ünite (s. 91)"
    },
    {
        "konu": "İstatistik ve Korelasyon",
        "soru": "İki değişken arasındaki doğrusal ilişkinin yönünü ve gücünü gösteren korelasyon katsayısı hangi değer aralığındadır?",
        "secenekler": ["-1 ile +1 arasında", "0 ile 100 arasında", "0 ile sonsuz arasında", "-10 ile +10 arasında"],
        "cevap": "-1 ile +1 arasında",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 5. Ünite (s. 164)"
    },
    {
        "konu": "İstatistik ve Korelasyon",
        "soru": "Aşağıdakilerden hangisi bir merkezî yayılım (dağılım) ölçüsü DEĞİLDİR?",
        "secenekler": ["Aritmetik Ortalama", "Varyans", "Standart Sapma", "Çeyrekler Arası Açıklık"],
        "cevap": "Aritmetik Ortalama",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 2. Ünite (s. 91)"
    },

    # 6. Kategori: Yapay Zekâ ve Makine Öğrenmesi (Zorluk 1-4)
    {
        "konu": "Yapay Zekâ ve Makine Öğrenmesi",
        "soru": "Yapay zekâ sistemleri hakkında aşağıdaki ifadelerden hangisi doğrudur?",
        "secenekler": [
            "Yapay zekâ, eğitime ve algoritmaya bağlı olarak işlemler gerçekleştirir.",
            "Yapay zekâ veri olmadan da öğrenme yapabilir.",
            "Yapay zekâ tüm insan duygularına doğuştan sahiptir.",
            "Yapay zekâ hiçbir donanıma ihtiyaç duymaz."
        ],
        "cevap": "Yapay zekâ, eğitime ve algoritmaya bağlı olarak işlemler gerçekleştirir.",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 276)"
    },
    {
        "konu": "Yapay Zekâ ve Makine Öğrenmesi",
        "soru": "Bilgisayarların verilerden ve geçmiş deneyimlerden yola çıkarak açıkça programlanmadan öğrenmesini sağlayan alan hangisidir?",
        "secenekler": ["Makine öğrenmesi (Machine Learning)", "Web tasarımı", "Veritabanı sorgulama", "İşletim sistemi çekirdeği"],
        "cevap": "Makine öğrenmesi (Machine Learning)",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 276)"
    },
    {
        "konu": "Yapay Zekâ ve Makine Öğrenmesi",
        "soru": "Makine öğrenmesinde bir modelin başarısını tarafsız ölçebilmek için veri seti genellikle hangi iki ana gruba ayrılır?",
        "secenekler": ["Eğitim (Train) ve Test verisi", "Girdi ve Çıktı verisi", "Doğru ve Yanlış verisi", "Sayısal ve Metin verisi"],
        "cevap": "Eğitim (Train) ve Test verisi",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 227)"
    },
    {
        "konu": "Yapay Zekâ ve Makine Öğrenmesi",
        "soru": "Bir modelin eğitim verisini ezberleyerek yeni ve görülmemiş test verilerinde yüksek hata vermesi durumuna ne ad verilir?",
        "secenekler": ["Aşırı Öğrenme (Overfitting)", "Eksik Öğrenme (Underfitting)", "Genelleme", "Normalizasyon"],
        "cevap": "Aşırı Öğrenme (Overfitting)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 228)"
    },

    # 7. Kategori: Regresyon ve Tahmin Modelleri (Zorluk 1-4)
    {
        "konu": "Regresyon ve Tahmin Modelleri",
        "soru": "Sürekli sayısal değerleri (örn: ev fiyatı, sıcaklık, hisse senedi) tahmin etmek için kullanılan model türü hangisidir?",
        "secenekler": ["Regresyon modelleri", "Sınıflandırma modelleri", "Kümeleme modelleri", "Arama ağaçları"],
        "cevap": "Regresyon modelleri",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 215)"
    },
    {
        "konu": "Regresyon ve Tahmin Modelleri",
        "soru": "Doğrusal regresyonda kullanılan 'y = mx + n' denkleminde 'm' parametresi neyi ifade eder?",
        "secenekler": ["Doğrunun eğim katsayısını", "Doğrunun y eksenini kestiği noktayı", "Hata terimini", "Örneklem sayısını"],
        "cevap": "Doğrunun eğim katsayısını",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 5. Ünite (s. 164)"
    },
    {
        "konu": "Regresyon ve Tahmin Modelleri",
        "soru": "Doğrusal regresyon modelinde veri noktalarına en uygun doğruyu bulmak için kullanılan matematiksel optimizasyon yöntemi hangisidir?",
        "secenekler": ["En küçük kareler yöntemi (OLS)", "En büyük kökler yöntemi", "Rastgele arama", "Matris tersi"],
        "cevap": "En küçük kareler yöntemi (OLS)",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 5. Ünite (s. 164)"
    },
    {
        "konu": "Regresyon ve Tahmin Modelleri",
        "soru": "Scikit-Learn kütüphanesinde oluşturulan bir regresyon modelini eğitim verileriyle eğitmek için hangi fonksiyon kullanılır?",
        "secenekler": ["fit()", "predict()", "score()", "transform()"],
        "cevap": "fit()",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 5. Ünite (s. 164)"
    },

    # 8. Kategori: Sınıflandırma Algoritmaları (Zorluk 1-4)
    {
        "konu": "Sınıflandırma Algoritmaları",
        "soru": "Verilerin belirli kategorilere veya etiketlere (örn: spam / güvenli) ayrılmasını sağlayan modelleme türü hangisidir?",
        "secenekler": ["Sınıflandırma (Classification)", "Boyut İndirgeme", "Optimizasyon", "Derleme"],
        "cevap": "Sınıflandırma (Classification)",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 241)"
    },
    {
        "konu": "Sınıflandırma Algoritmaları",
        "soru": "K-En Yakın Komşu (KNN) algoritmasında yeni bir noktanın sınıfı belirlenirken temel alınan kriter nedir?",
        "secenekler": ["En yakın k komşunun çoğunluk oyu", "Ağaçların derinliği", "Korelasyon katsayısı", "Ters matris değeri"],
        "cevap": "En yakın k komşunun çoğunluk oyu",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 252)"
    },
    {
        "konu": "Sınıflandırma Algoritmaları",
        "soru": "Rastgele Orman (Random Forest) sınıflandırma modelini oluştururken kullanılacak karar ağacı sayısını belirleyen parametre hangisidir?",
        "secenekler": ["n_estimators", "max_depth", "n_neighbors", "random_state"],
        "cevap": "n_estimators",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 276)"
    },
    {
        "konu": "Sınıflandırma Algoritmaları",
        "soru": "İki sınıfı birbirinden en geniş sınır aralığıyla (marjinle) ayıran en uygun hiper-düzlemi belirleyen model hangisidir?",
        "secenekler": ["Destek Vektör Makinesi (SVM)", "Lojistik Regresyon", "Naive Bayes", "K-Means"],
        "cevap": "Destek Vektör Makinesi (SVM)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 277)"
    },

    # 9. Kategori: Güdümsüz Öğrenme ve Kümeleme (Zorluk 1-4)
    {
        "konu": "Güdümsüz Öğrenme ve Kümeleme",
        "soru": "Hedef etiketi (çıktısı) bulunmayan verileri kendi içlerindeki benzerlik ve örüntülere göre gruplama yaklaşımına ne ad verilir?",
        "secenekler": ["Güdümsüz (Denetimsiz) Öğrenme", "Güdümlü Öğrenme", "Pekiştirmeli Öğrenme", "Doğrulama"],
        "cevap": "Güdümsüz (Denetimsiz) Öğrenme",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 266)"
    },
    {
        "konu": "Güdümsüz Öğrenme ve Kümeleme",
        "soru": "K-Ortalama (K-Means) kümeleme algoritmasının çalışma prensibinde İLK adım hangisidir?",
        "secenekler": ["Başlangıç küme merkezlerinin belirlenmesi", "Noktaların ağırlıklarının toplanması", "Ağaç budama işlemi", "Korelasyon hesabı"],
        "cevap": "Başlangıç küme merkezlerinin belirlenmesi",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 276)"
    },
    {
        "konu": "Güdümsüz Öğrenme ve Kümeleme",
        "soru": "Dijital görüntülerde pikselleri temsil eden RGB renk modeli hangi temel üç rengi içerir?",
        "secenekler": ["Kırmızı, Yeşil, Mavi", "Kırmızı, Sarı, Mavi", "Sarı, Yeşil, Mavi", "Kırmızı, Beyaz, Siyah"],
        "cevap": "Kırmızı, Yeşil, Mavi",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 277)"
    },
    {
        "konu": "Güdümsüz Öğrenme ve Kümeleme",
        "soru": "Kullanıcıların geçmiş izleme ve satın alma davranışlarını inceleyerek benzer ilgi alanlarına sahip kişilere öneri sunan sistemlere ne ad verilir?",
        "secenekler": ["Tavsiye Sistemleri (Recommendation Systems)", "Karar Ağaçları", "Sıralama Algoritmaları", "Arama Motoru Önbelleği"],
        "cevap": "Tavsiye Sistemleri (Recommendation Systems)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 270)"
    },

    # 10. Kategori: Oyunlarda Yapay Zekâ ve Algoritmalar (Zorluk 1-4)
    {
        "konu": "Oyunlarda Yapay Zekâ ve Algoritmalar",
        "soru": "Dijital oyunlarda gerçek bir oyuncu tarafından kontrol edilmeyen yapay zekâ karakterlerine ne ad verilir?",
        "secenekler": ["NPC (Non-Player Character)", "Avatar", "Boss", "Host"],
        "cevap": "NPC (Non-Player Character)",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 332)"
    },
    {
        "konu": "Oyunlarda Yapay Zekâ ve Algoritmalar",
        "soru": "Oyun karakterlerinin belirli durumlar (örn: devriye, saldırı, kaçma) arasında kurallara göre geçiş yapmasını sağlayan modelleme yapısı hangisidir?",
        "secenekler": ["Sonlu Durum Makinesi (FSM)", "Doğrusal Regresyon", "Destek Vektörü", "K-Means"],
        "cevap": "Sonlu Durum Makinesi (FSM)",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 332)"
    },
    {
        "konu": "Oyunlarda Yapay Zekâ ve Algoritmalar",
        "soru": "İki oyunculu sıfır toplamlı oyunlarda (örn: Tic Tac Toe, Satranç) potansiyel kayıpları en aza, kazançları en üst düzeye çıkaran algoritma hangisidir?",
        "secenekler": ["Minimaks (Minimax) algoritması", "Genetik algoritma", "Dijkstra algoritması", "İkili arama algoritması"],
        "cevap": "Minimaks (Minimax) algoritması",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 332)"
    },
    {
        "konu": "Oyunlarda Yapay Zekâ ve Algoritmalar",
        "soru": "Minimaks algoritmasında oyun ağacının gereksiz derinlikteki dallarını incelemeyerek hesaplama süresini ciddi oranda azaltan yöntem hangisidir?",
        "secenekler": ["Alfa-Beta Budama (Alpha-Beta Pruning)", "Aşırı Öğrenme", "Geri Yayılım (Backpropagation)", "Doğrusal İnterpolasyon"],
        "cevap": "Alfa-Beta Budama (Alpha-Beta Pruning)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 302)"
    },

    # 11. Kategori: Doğal Dil İşleme ve Sohbet Robotları (Zorluk 1-4)
    {
        "konu": "Doğal Dil İşleme ve Sohbet Robotları",
        "soru": "İnsan dilinin (metin veya konuşma) bilgisayarlar tarafından analiz edilmesini ve anlamlandırılmasını sağlayan yapay zekâ alanı hangisidir?",
        "secenekler": ["Doğal Dil İşleme (NLP)", "Bilgisayarla Görme", "Biyometrik Tanıma", "Robotik Kodlama"],
        "cevap": "Doğal Dil İşleme (NLP)",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 333)"
    },
    {
        "konu": "Doğal Dil İşleme ve Sohbet Robotları",
        "soru": "Bir metindeki ifadelerin olumlu, olumsuz veya tarafsız duygusal tonunu belirlemek amacıyla yapılan işleme ne ad verilir?",
        "secenekler": ["Duygu Analizi (Sentiment Analysis)", "Yüz Tanıma", "Nesne Tespiti", "Veri Tabanı İndeksleme"],
        "cevap": "Duygu Analizi (Sentiment Analysis)",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 321)"
    },
    {
        "konu": "Doğal Dil İşleme ve Sohbet Robotları",
        "soru": "Yalnızca önceden tanımlanmış anahtar kelimelere ve 'eğer-ise' kalıplarına göre cevap üreten diyalog sistemlerine ne ad verilir?",
        "secenekler": ["Kural tabanlı sohbet robotu (Rule-based Chatbot)", "Büyük dil modeli", "Derin üretken ağ", "Dönüştürücü (Transformer)"],
        "cevap": "Kural tabanlı sohbet robotu (Rule-based Chatbot)",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 311)"
    },
    {
        "konu": "Doğal Dil İşleme ve Sohbet Robotları",
        "soru": "NLP metin ön işleme sürecinde bir cümlenin en küçük anlamlı parçalarına (kelime, noktalama) ayrılması işlemine ne ad verilir?",
        "secenekler": ["Tokenizasyon (Tokenization)", "Vektörizasyon", "Normalizasyon", "Budama"],
        "cevap": "Tokenizasyon (Tokenization)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 9. Ünite (s. 317)"
    },

    # 12. Kategori: Model Başarımı ve Veri Etiği (Zorluk 1-4)
    {
        "konu": "Model Başarımı ve Veri Etiği",
        "soru": "Sınıflandırma modellerinin gerçek sınıflar ile tahmin edilen sınıflar arasındaki performansını gösteren tabloya ne ad verilir?",
        "secenekler": ["Karmaşıklık Matrisi (Confusion Matrix)", "Korelasyon Tablosu", "Varyans Çizelgesi", "Frekans Histogramı"],
        "cevap": "Karmaşıklık Matrisi (Confusion Matrix)",
        "zorluk": 1,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 261)"
    },
    {
        "konu": "Model Başarımı ve Veri Etiği",
        "soru": "Karmaşıklık matrisinde 'modelin pozitif olarak tahmin ettiği durumların gerçekte ne kadarının pozitif olduğunu' gösteren başarı metriği hangisidir?",
        "secenekler": ["Kesinlik (Precision)", "Doğruluk (Accuracy)", "Eğilim (Bias)", "Kayıp (Loss)"],
        "cevap": "Kesinlik (Precision)",
        "zorluk": 2,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 262)"
    },
    {
        "konu": "Model Başarımı ve Veri Etiği",
        "soru": "Yapay zekâ algoritmalarının eğitim verisindeki adaletsiz veya tek taraflı tercihler nedeniyle belirli gruplara ayrımcılık yapması durumuna ne ad verilir?",
        "secenekler": ["Algoritmik Önyargı (Algorithmic Bias)", "Veri Sıkıştırma", "Aşırı Dengeleme", "Hiperparametre Uyumu"],
        "cevap": "Algoritmik Önyargı (Algorithmic Bias)",
        "zorluk": 3,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 1. Ünite (s. 24)"
    },
    {
        "konu": "Model Başarımı ve Veri Etiği",
        "soru": "Yapay zekâ modellerinin aldıkları kararların ve yaptıkları tahminlerin gerekçelerinin insanlar tarafından anlaşılabilir ve denetlenebilir olmasını savunan yaklaşım hangisidir?",
        "secenekler": [
            "Açıklanabilir Yapay Zekâ (XAI - Explainable AI)",
            "Kara Kutu Modeli",
            "Gizli Katman Ağları",
            "Kapalı Kaynak Yazılım"
        ],
        "cevap": "Açıklanabilir Yapay Zekâ (XAI - Explainable AI)",
        "zorluk": 4,
        "kaynak": "MEB Yapay Zekâ Uygulamaları, 8. Ünite (s. 278)"
    },
]


def calistir():
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")
    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")

    pdf_hash = hashlib.sha256(PDF_YOLU.read_bytes()).hexdigest()

    # 1. soru_havuzu kaynak_birim ekle
    with havuz.cursor() as cur:
        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kitap', 'kitap:yapazeka:meb', 'bilisim', 9,
                    'MEB Yapay Zekâ Uygulamaları Ders Kitabı', 'MEB Ortaöğretim Bilişim Teknolojileri ve Yazılım: Yapay Zekâ Uygulamaları (yapazeka.pdf)',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_id = cur.fetchone()[0]

        # Eski bilisim sorularını temizle
        cur.execute("DELETE FROM soru WHERE ders = 'bilisim';")
        logging.info("soru_havuzu: Eski Bilişim kayıtları temizlendi (%d satır).", cur.rowcount)

        # 9, 10, 11, 12. sınıfların tamamı için ekle (seçmeli ve bilişim dersleri her kademede oynanabilsin)
        toplam_eklenen = 0
        for sinif_duzey in [9, 10, 11, 12]:
            for s in SORULAR_BILISIM:
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
                    "bilisim",
                    sinif_duzey,
                    s["konu"],
                    s["soru"],
                    dogru_metin,
                    json.dumps(kanonik_sec, ensure_ascii=False),
                    yeni_idx,
                    s["zorluk"],
                    s["kaynak"]
                ))
                toplam_eklenen += 1

        havuz.commit()
        logging.info("soru_havuzu: 9, 10, 11, 12. sınıflar için toplam %d onaylı Bilişim sorusu kaydedildi.", toplam_eklenen)

    # 2. farabi.kazanim_test_soru tablosuna ekle
    with farabi.cursor() as cur:
        cur.execute("DELETE FROM kazanim_test_soru WHERE ders = 'Bilişim';")
        no_sayac = 1
        for s in SORULAR_BILISIM:
            secenek_harfleri = ["A", "B", "C", "D"]
            secenek_map = {secenek_harfleri[i]: s["secenekler"][i] for i in range(len(s["secenekler"]))}
            dogru_harf = secenek_harfleri[s["secenekler"].index(s["cevap"])]

            cur.execute("""
                INSERT INTO kazanim_test_soru
                (kaynak_dosya, kaynak_hash, sinif, ders, konu, test_no, soru_no, soru_metni, secenekler, cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                PDF_YOLU.name,
                pdf_hash,
                9,
                "Bilişim",
                s["konu"],
                1,
                no_sayac,
                s["soru"],
                json.dumps(secenek_map, ensure_ascii=False),
                dogru_harf
            ))
            no_sayac += 1
        farabi.commit()
        logging.info("farabi.kazanim_test_soru: %d Bilişim sorusu kaydedildi.", no_sayac - 1)

    havuz.close()
    farabi.close()


if __name__ == "__main__":
    calistir()
