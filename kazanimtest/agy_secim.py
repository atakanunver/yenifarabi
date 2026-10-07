"""kazanimtest/agy_secim.py — Adaylardan kazanıma uygun N soruyu agy'ye seçtirir.

Çağrı deseni `soruhavuzu/denetci.py::agy_cagir`. agy başarısız / zaman aşımı / bozuk
yanıt → benzerlik sırasıyla ilk N (akış durmaz).
"""

import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("kazanimtest.agy")

AGY = "/home/ata/.local/bin/agy"
SEMA = Path(__file__).with_name("agy_sema.json")
CALISMA_DIZINI = Path("/tmp/kazanimtest-agy")


def istem(kazanimlar: list[str], adaylar: list[dict], n: int) -> str:
    ks = "\n".join(f"- {k}" for k in kazanimlar)
    soru_metni = "\n\n".join(
        f"[id={i}] {a['soru']}\n" + "\n".join(f"  {'ABCD'[j]}) {s}" for j, s in enumerate(a["secenekler"]))
        + f"\n  Doğru: {'ABCD'[a['dogru_index']]}"
        for i, a in enumerate(adaylar)
    )
    return (
        f"Bir lise öğretmeni için bu haftanın kazanımlarını ölçen {n} soruluk çoktan seçmeli test "
        "hazırlıyorsun.\n\nKazanımlar:\n" + ks + "\n\nAday sorular (id sıra numarasıdır):\n\n"
        + soru_metni
        + f"\n\nGörev: Kazanımlara en uygun, doğru cevabı kesin doğru, tek doğru şıklı, birbirini "
        f"tekrarlamayan en fazla {n} soruyu seç (`secilen`: id listesi). Uygun olmayan ya da hatalı "
        "soruları `red` içinde nedeniyle yaz. Yalnızca JSON döndür."
    )


def agy_cagir(metin: str, zaman_asimi_sn: int = 600) -> str:
    CALISMA_DIZINI.mkdir(exist_ok=True)
    r = subprocess.run(
        [
            AGY, "-p", metin, "--output-format", "json", "--json-schema", str(SEMA),
            "--mode", "plan", "--print-timeout", f"{zaman_asimi_sn}s",
        ],
        cwd=CALISMA_DIZINI,
        capture_output=True,
        text=True,
        check=False,
        timeout=zaman_asimi_sn + 30,
    )
    return r.stdout


def yaniti_coz(cikti: str, aday_sayisi: int) -> list[int]:
    try:
        dis = json.loads(cikti)
        yapisal = dis.get("structured_output") if isinstance(dis, dict) else None
        if isinstance(dis, dict) and dis.get("status") == "ERROR":
            log.warning("agy hata: %s", str(dis.get("error", ""))[:200])
            return []
        if isinstance(yapisal, dict) and "secilen" in yapisal:  # denetci.py ile aynı
            ic = yapisal
        elif isinstance(dis, dict) and "secilen" in dis:
            ic = dis
        else:
            govde = dis.get("response", "") if isinstance(dis, dict) else ""
            govde = govde.strip().removeprefix("```json").removeprefix("```").strip()
            ic = json.JSONDecoder().raw_decode(govde)[0]
        ham = ic.get("secilen", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []
    gorulen: list[int] = []
    for x in ham if isinstance(ham, list) else []:
        if isinstance(x, int) and not isinstance(x, bool) and 0 <= x < aday_sayisi and x not in gorulen:
            gorulen.append(x)
    return gorulen


def sec(kazanimlar: list[str], adaylar: list[dict], n: int, cagir=None, zaman_asimi_sn: int = 600) -> list[dict]:
    """Adaylar benzerlik sırasında gelir; geri dönen liste ≤ n soru."""
    if len(adaylar) <= n:
        return list(adaylar)
    secilen: list[int] = []
    cagir = cagir or agy_cagir
    try:
        secilen = yaniti_coz(cagir(istem(kazanimlar, adaylar, n), zaman_asimi_sn), len(adaylar))[:n]
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("agy seçimi başarısız (%s) — benzerlik sırasına düşüldü", e)
    if not secilen:
        log.warning("agy yanıtı boş/bozuk — benzerlik sırasına düşüldü")
    sonuc = [adaylar[i] for i in secilen]
    for i, a in enumerate(adaylar):  # eksik kalanı benzerlik sırasıyla tamamla
        if len(sonuc) >= n:
            break
        if i not in secilen:
            sonuc.append(a)
    return sonuc
