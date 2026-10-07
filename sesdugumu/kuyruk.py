"""Uretim sonu "bogulma" kuyrugunu temizler.

2026-10-04: T3 omurgasi EOS'tan once konusma bittikten sonra kisa bir
sessizlik + yuksek seviyeli anlamsiz ses uretebiliyor. Son 12 uretimin
yarisindan fazlasinda olculdu: konusma → -47..-55 dB bosluk → -25..-5 dB
kuyruk, dosya bu kuyrukla (yuksek seviyede) bitiyor. `librosa.effects.trim`
yalnizca KENARDAKI sessizligi kirptigi icin bu kuyrugu hic yakalamiyordu.

Kural: son KUYRUK_ARAMA_SN icinde en az BOSLUK_MIN_SN suren bir bosluk
varsa ve ardindan gelen ses KUYRUK_MAX_SN'den kisaysa, ses boslugun
basindan (+ kucuk bir pay) kesilir. Her durumda sona kisa bir fade-out
uygulanir (ani kesilme / tik sesi olmasin).
"""

import numpy as np

KARE_SN = 0.02
BOSLUK_DB = -40.0  # tepe seviyesine gore
BOSLUK_MIN_SN = 0.2
KUYRUK_MAX_SN = 1.2
KUYRUK_ARAMA_SN = 2.5
KESIM_PAYI_SN = 0.08
FADE_SN = 0.03


def _kare_db(y: np.ndarray, kare: int) -> np.ndarray:
    n = len(y) // kare
    kareler = y[: n * kare].reshape(n, kare)
    rms = np.sqrt(np.mean(kareler.astype(np.float64) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms / max(rms.max(), 1e-9))


def _fade_out(y: np.ndarray, sr: int) -> np.ndarray:
    n = min(len(y), int(FADE_SN * sr))
    if n > 1:
        y = y.copy()
        y[-n:] *= np.linspace(1.0, 0.0, n, dtype=y.dtype)
    return y


def kuyruk_temizle(y: np.ndarray, sr: int) -> tuple[np.ndarray, bool]:
    """(temizlenmis_ses, kuyruk_kesildi_mi) dondurur."""
    kare = int(KARE_SN * sr)
    if len(y) < kare * 4:
        return y, False

    db = _kare_db(y, kare)
    n = len(db)
    arama_bas = max(0, n - int(KUYRUK_ARAMA_SN / KARE_SN))
    min_bosluk = int(BOSLUK_MIN_SN / KARE_SN)

    # Arama penceresindeki SON yeterince uzun bosluğu bul (sondan geriye).
    sessiz = db < BOSLUK_DB
    kesim_kare = None
    i = n - 1
    while i >= arama_bas:
        if sessiz[i]:
            son = i
            while i >= arama_bas and sessiz[i]:
                i -= 1
            bas = i + 1
            if son - bas + 1 >= min_bosluk:
                kuyruk_sn = (n - 1 - son) * KARE_SN
                # Bosluktan sonra ses var mi ve kisa mi?
                if 0 < kuyruk_sn <= KUYRUK_MAX_SN and np.any(db[son + 1 :] > BOSLUK_DB):
                    kesim_kare = bas
                break
        i -= 1

    if kesim_kare is None:
        return _fade_out(y, sr), False

    kesim = min(len(y), kesim_kare * kare + int(KESIM_PAYI_SN * sr))
    return _fade_out(y[:kesim], sr), True
