"""soruhavuzu/sekil.py — kaynak şekil/grafik/tabloya atıf yapan, ama şekli taşımayan soruları tespit eder.

Öğrenci soruyu şekil görmeden çözer; "şekildeki", "grafiğe göre" gibi atıflar cevaplanamaz soru üretir.
Yanlış pozitifleri azaltmak için 'bir şekilde', 'periyodik tablo', 'grafik tasarım' gibi sıradan
kullanımlar atıf sayılmaz."""

import re

_NOTR = re.compile(
    r"fonksiyon\w*\s+grafiğ\w+\s+göre|periyodik\s+tablo\w*|çarpım\s+tablo\w*|doğruluk\s+tablo\w*|değişken\s+tablo\w*|"
    r"grafik\s+(tasarım|sanat|kartı|programı|arayüz)\w*|görsel\s+(sanat|iletişim|tasarım|kültür)\w*|"
    r"(bir|her|aynı|farklı|bu|şu|o|her\s+bir)\s+şekilde|şekilde\s+(ifade|yorum|tanım|adland|kullan|oluş)\w*",
    re.IGNORECASE,
)
_ATIF = re.compile(
    r"\b(şekil|grafik|tablo|çizelge|diyagram|harita|görsel|resim|devre|çizim|şema)\s*[-–]?\s*\d+\b|"
    r"\b(şekil|şekilde|şekillerde)\s+"
    r"(göre|bakarak|bakıldığında|verilmiş|verilen|gösterilen|çizilmiş|görülen|yer\s+alan|belirtilen)\b|"
    r"\b(şekildeki|şekillerdeki|şekle\s+göre|şekle\s+bakarak)\b|"
    r"\b(yukarıdaki|aşağıdaki|yandaki|verilen)\s+"
    r"(şekil|grafik|tablo|çizelge|diyagram|harita|görsel|resim|devre|çizim|şema)\w*|"
    r"\b(grafik|grafiği|grafikte|grafikteki|grafiğe|grafiğine|tabloda|tablodaki|tabloya|çizelgeye|çizelgede|"
    r"çizelgedeki|diyagramda|diyagramdaki|haritada|haritadaki|haritaya|görseldeki|görsele|resimdeki|"
    r"resimde|devrede|devredeki|çizimdeki|şemada|şemadaki)\s+"
    r"(göre|bakarak|bakıldığında|verilmiş|gösterilen|görülen|çizilmiş|belirtilen|inceleyerek|"
    r"yer\s+alan)\b|"
    r"\b(grafiğe|tabloya|haritaya|görsele|diyagrama|çizelgeye|şemaya)\s+göre\b|"
    r"\b(şekilde|grafikte|tabloda|haritada|çizelgede|diyagramda|şemada)\s+(gösterilen|verilen|görülen|"
    r"verilmiş|çizilmiş|belirtilen)\b",
    re.IGNORECASE,
)


def eslesme(soru: str, secenekler: list | None = None) -> str | None:
    metin = " ".join([soru or "", *[str(x) for x in (secenekler or [])]])
    m = _ATIF.search(_NOTR.sub(" ", metin))
    return m.group(0) if m else None


def sekil_atfi(soru: str, secenekler: list | None = None) -> bool:
    """Soru metni ya da şıklarda şekil/grafik/tablo atfı varsa True."""
    return eslesme(soru, secenekler) is not None
