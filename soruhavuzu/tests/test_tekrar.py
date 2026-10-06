import numpy as np

from soruhavuzu import tekrar


class SahteGomucu:
    def encode(self, metinler, normalize_embeddings=True):
        tablo = {
            "log2(8) kaçtır?": [1, 0],
            "log2 8 kaçtır?": [0.99, 0.14],
            "Fotosentez nedir?": [0, 1],
        }
        v = np.array([tablo[m] for m in metinler], dtype=float)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_benzer_soru_kopya_sayilir_farkli_ders_sayilmaz():
    e = tekrar.Eleyici(SahteGomucu())
    assert e.kopya_mi("matematik", 12, "log2(8) kaçtır?") is False
    assert e.kopya_mi("matematik", 12, "log2 8 kaçtır?") is True
    assert e.kopya_mi("biyoloji", 10, "log2 8 kaçtır?") is False
    assert e.kopya_mi("matematik", 12, "Fotosentez nedir?") is False
