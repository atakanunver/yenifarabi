"""Kalıp cümleler — servis açılışında bir kez sentezlenip önbelleğe alınır.

Anahtarlar istemcide (client/core/yerel_oturum.py) aynen kullanılır; metin
değişirse ikisi birlikte değişir (istemci metni gönderir, eşleşme metinle).
"""

KALIPLAR: dict[str, str] = {
    "bakiyorum": "Hemen bakıyorum hocam.",
    "kitap": "Bir saniye, kitaba bakıyorum.",
    "ekran": "Ekrana bakıyorum.",
    "hazirliyorum": "Hemen hazırlıyorum.",
    "aciyorum": "Hemen açıyorum.",
    "tamam": "Tamam.",
    "peki": "Peki hocam.",
    "anlamadim": "Sizi tam anlayamadım hocam, tekrar söyler misiniz?",
    "duyamadim": "Sizi duyamadım hocam, tekrar söyler misiniz?",
    "yogunum": "Şu an biraz yoğunum, birazdan tekrar sorar mısınız?",
    "hata": "Bir sorun çıktı hocam, tekrar dener misiniz?",
    "servis_kapali": "Ses servisine ulaşamıyorum hocam.",
    "iptal": "Tamam, vazgeçtim.",
    "onay_yoklama": "Yoklama alayım mı hocam?",
    "onay_video": "Videoyu açayım mı hocam?",
    "onay_kapat": "Farabi'yi kapatayım mı hocam?",
    "onay_bekliyorum": "Onaylamak için düğmeye basıp evet deyin hocam.",
    "harika_soru": "Harika bir soru!",
    "dusunelim": "Güzel, birlikte düşünelim.",
    "gunaydin": "Günaydın çocuklar!",
    "merhaba": "Merhaba çocuklar!",
    "tesekkur": "Rica ederim hocam.",
    "devam": "Devam ediyorum.",
    "durdum": "Durdum hocam.",
    "dinliyorum": "Dinliyorum hocam.",
}
