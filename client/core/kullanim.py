"""
Gemini Live token tüketimi — ayrıştırma ve toplama (saf Python, SDK/ağ yok).

Neden: Gemini tüketimi daha önce hiçbir yerde ölçülmüyordu (2026-10-02
kararı); kota/maliyet boyutlandırması tahminle yapılıyordu. Live oturumunun
her sunucu mesajı `usage_metadata` taşıyabilir; burada o alanlar okunur,
toplanır ve tek satırlık özet olarak loglanır.

DOĞRULANMADI: Live'ın tur başına TEK mi yoksa BİRDEN ÇOK usage mesajı
gönderdiği bilinmiyor. Bu yüzden her mesaj olduğu gibi toplanır (tekilleştirme
yok), mesaj sayısı ayrıca tutulur ve her mesaj ham olarak loglanır. `girdi`
her istekte tüm bağlamı kapsadığı için toplamları "faturalanan" değil
"gözlenen" değer olarak oku; gerçek eğilim `en_buyuk_girdi`'dedir.

Bu modül hiçbir koşulda dersi bozmamalı: eksik/None alan 0 sayılır.
"""

_ALANLAR = ("girdi", "girdi_ses", "girdi_metin", "yanit", "yanit_ses",
            "yanit_metin", "arac", "dusunce", "onbellek", "toplam")


def _bin(n) -> str:
    """12345 -> '12.345' (Türkçe binlik ayracı)."""
    return f"{int(n):,}".replace(",", ".")


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _modalite_adi(m) -> str:
    """Enum ya da düz metin modaliteyi 'AUDIO'/'TEXT' biçimine indirger."""
    ad = getattr(m, "name", None) or str(m)
    ad = str(ad).upper()
    for onek in ("MEDIAMODALITY.", "MODALITY."):
        ad = ad.removeprefix(onek)
    return ad


def _modalite_topla(detaylar) -> tuple[int, int]:
    """(ses, metin) token toplamı; liste yoksa (0, 0)."""
    ses = metin = 0
    for d in detaylar or []:
        ad = _modalite_adi(getattr(d, "modality", None))
        n = _int(getattr(d, "token_count", 0))
        if ad == "AUDIO":
            ses += n
        elif ad == "TEXT":
            metin += n
    return ses, metin


def ayristir(usage) -> dict:
    """`UsageMetadata`'yı düz int sözlüğüne çevirir; eksik alan 0."""
    g_ses, g_metin = _modalite_topla(getattr(usage, "prompt_tokens_details", None))
    y_ses, y_metin = _modalite_topla(getattr(usage, "response_tokens_details", None))
    return {
        "girdi": _int(getattr(usage, "prompt_token_count", 0)),
        "girdi_ses": g_ses,
        "girdi_metin": g_metin,
        "yanit": _int(getattr(usage, "response_token_count", 0)),
        "yanit_ses": y_ses,
        "yanit_metin": y_metin,
        "arac": _int(getattr(usage, "tool_use_prompt_token_count", 0)),
        "dusunce": _int(getattr(usage, "thoughts_token_count", 0)),
        "onbellek": _int(getattr(usage, "cached_content_token_count", 0)),
        "toplam": _int(getattr(usage, "total_token_count", 0)),
    }


def satir(d: dict) -> str:
    """Tek mesajlık özet satırı."""
    return (f"girdi={_bin(d['girdi'])} (ses {_bin(d['girdi_ses'])} / "
            f"metin {_bin(d['girdi_metin'])}) yanit={_bin(d['yanit'])} "
            f"arac={_bin(d['arac'])} toplam={_bin(d['toplam'])}")


class Sayac:
    """Mesajları olduğu gibi toplayan sayaç (bağlantı ya da ders başına)."""

    def __init__(self):
        self.sifirla()

    def sifirla(self) -> None:
        self.mesaj = 0
        self.en_buyuk_girdi = 0
        self.toplam = {k: 0 for k in _ALANLAR}

    @property
    def bos(self) -> bool:
        return self.mesaj == 0

    def ekle(self, usage) -> dict:
        d = ayristir(usage)
        for k in _ALANLAR:
            self.toplam[k] += d[k]
        self.mesaj += 1
        self.en_buyuk_girdi = max(self.en_buyuk_girdi, d["girdi"])
        return d

    def ozet(self) -> str:
        t = self.toplam
        return (f"mesaj={self.mesaj} girdi={_bin(t['girdi'])} "
                f"(ses {_bin(t['girdi_ses'])} / metin {_bin(t['girdi_metin'])}) "
                f"yanit={_bin(t['yanit'])} arac={_bin(t['arac'])} "
                f"toplam={_bin(t['toplam'])} "
                f"en_buyuk_baglam={_bin(self.en_buyuk_girdi)}")
