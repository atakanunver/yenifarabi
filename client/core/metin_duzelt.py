"""Seslendirme öncesi metin düzeltme: biçimlendirme temizliği + Türkçe sıra sayıları.

Chatterbox'un kendi metin düzelticisi "12. sınıf"ı "on iki. sınıf" okuyor
(2026-10-07 ölçümü); yıl/sayı/ek okumasını ise doğru yapıyor — bu yüzden
burada YALNIZCA sıra sayısı + biçim temizliği var.
"""
import re

_BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SIRA = {
    "bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci",
    "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu",
    "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı",
    "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
    "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü",
}
# "12. sınıf" — sayı + nokta + boşluk + KÜÇÜK harf. Büyük harfle devam eden
# ("x eşittir 5. Kontrol edelim") cümle sonudur; yalnızca bilinen büyük harfli
# sıra sayısı adları ("2. Dünya Savaşı") istisna. cumle_bolucu da bunu kullanır.
SIRA_ONCESI_BUYUK = frozenset({
    "Dünya", "Cumhuriyet", "Meşrutiyet", "Haçlı", "Viyana", "Balkan", "İnönü",
    "Ordu", "Murat", "Mehmet", "Selim", "Mahmut", "Bayezid", "Abdülhamit", "Ahmet",
})
_SIRA_RE = re.compile(r"\b([1-9]\d?|100)\.(?=\s+([^\W\d_]\w*))")


def sira_sayisi_mi(sonraki_kelime: str) -> bool:
    """"N." sonrasındaki kelimeye bakarak N.'nin sıra sayısı olup olmadığı."""
    return bool(sonraki_kelime) and (sonraki_kelime[0].islower()
                                     or sonraki_kelime in SIRA_ONCESI_BUYUK)
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def _sira(n: int) -> str:
    if n == 100:
        return _SIRA["yüz"]
    on, bir = divmod(n, 10)
    kelimeler = [k for k in (_ONLAR[on], _BIRLER[bir]) if k]
    kelimeler[-1] = _SIRA[kelimeler[-1]]
    return " ".join(kelimeler)


def seslendirme_icin(metin: str) -> str:
    m = re.sub(r"\*\*|__|`", "", metin)
    m = re.sub(r"^\s*#+\s*", "", m, flags=re.MULTILINE)       # başlık
    m = re.sub(r"^\s*[-*•]\s+", "", m, flags=re.MULTILINE)    # madde imi
    m = re.sub(r"(?:^|\s)\d+\)\s*", "\n", m)                  # "1) a 2) b" → satırlar
    m = _EMOJI_RE.sub("", m)
    m = _SIRA_RE.sub(lambda e: _sira(int(e.group(1))) if sira_sayisi_mi(e.group(2))
                     else e.group(0), m)
    satirlar = [" ".join(s.split()) for s in m.splitlines()]
    return ", ".join(s for s in satirlar if s)
