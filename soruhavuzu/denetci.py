"""soruhavuzu/denetci.py — üretilen soruları AGY (Antigravity CLI) ile kaynak metne karşı denetler.

Kullanıcı kararı (2026-10-05): sorular yerel Ollama'da üretilir, üretim bitince AGY tüm havuzu tek
seferde denetler. Çağrı başına ~12k token sabit AGY maliyeti olduğu için tek çalıştırma içinde
sorular 100'lük paketler hâlinde, kaynak metinleriyle birlikte gönderilir."""

import json
import subprocess
from pathlib import Path

from soruhavuzu import vt

AGY = "/home/ata/.local/bin/agy"
SEMA = Path(__file__).with_name("agy_sema.json")
CALISMA_DIZINI = Path("/tmp/soruhavuzu-agy")
METIN_AZAMI = 2500


def istem(paket: list[dict]) -> str:
    bloklar, goruldu = [], set()
    for s in paket:
        if s["birim_id"] not in goruldu:
            goruldu.add(s["birim_id"])
            bloklar.append(
                f"\n### KAYNAK {s['birim_id']}\n{s['birim_metin'][:METIN_AZAMI]}"
            )
        secenekler = " | ".join(
            f"{'ABCD'[i]}) {x}" for i, x in enumerate(s["secenekler"])
        )
        bloklar.append(
            f"- id={s['id']} (kaynak {s['birim_id']}, {s['ders']} {s['sinif']}. sınıf, "
            f"zorluk {s['zorluk']}): {s['soru']}\n  Şıklar: {secenekler}\n"
            f"  Doğru: {'ABCD'[s['dogru_index']]} / kısa cevap: {s['kisa_cevap']}"
        )
    return (
        "Sen bir MEB lise soru denetçisisin. Aşağıdaki her soruyu ilgili KAYNAK metne göre denetle. "
        "Geçerli sayılması için: işaretli şık ve kısa cevap doğru, tek doğru şık var, soru açık ve "
        "tek başına anlaşılır, kaynak metinle uyumlu, sınıf düzeyine uygun. Ayrıca soru belirtilen "
        "dersin kendi bilgisini/becerisini ölçmeli: ders kitabındaki bir örnek, hikâye ya da problem "
        "bağlamından çıkarılmış ders dışı bilgi soruları (ör. matematik kitabında bir günün tarihi, "
        "bir kişinin adı, bir yerin özelliği) ve saçma, anlamsız ya da cevabı sorudan belli olan "
        "sorular GEÇERSİZDİR — metinde geçse bile reddet. Dosya oluşturma, araç "
        "kullanma; yalnızca her id için bir karar içeren JSON döndür: "
        '{"kararlar": [{"id": 1, "gecerli": true, "neden": "kısa gerekçe"}]}\n'
        + "\n".join(bloklar)
    )


def yaniti_coz(cikti: str, paket_idleri: set[int]) -> dict[int, tuple[bool, str]]:
    try:
        dis = json.loads(cikti)
        yapisal = dis.get("structured_output") if isinstance(dis, dict) else None
        if isinstance(yapisal, dict) and "kararlar" in yapisal:
            kararlar = yapisal["kararlar"]
        else:
            ic = dis.get("response", "") if isinstance(dis, dict) else ""
            ic = ic.strip().removeprefix("```json").removeprefix("```").strip()
            # AGY bazen JSON'u iki kez art arda yazar; yalnızca ilk nesneyi al
            kararlar = json.JSONDecoder().raw_decode(ic)[0].get("kararlar", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}
    sonuc = {}
    for k in kararlar if isinstance(kararlar, list) else []:
        if (
            isinstance(k, dict)
            and k.get("id") in paket_idleri
            and isinstance(k.get("gecerli"), bool)
        ):
            sonuc[k["id"]] = (k["gecerli"], str(k.get("neden", ""))[:500])
    return sonuc


def agy_cagir(istem: str, zaman_asimi_sn: int = 900) -> str:
    CALISMA_DIZINI.mkdir(exist_ok=True)
    r = subprocess.run(
        [
            AGY,
            "-p",
            istem,
            "--output-format",
            "json",
            "--json-schema",
            str(SEMA),
            "--mode",
            "plan",
            "--print-timeout",
            f"{zaman_asimi_sn}s",
        ],
        cwd=CALISMA_DIZINI,
        capture_output=True,
        text=True,
        timeout=zaman_asimi_sn + 30,
    )
    return r.stdout


def paket_denetle(conn, boyut: int = 100, cagir=agy_cagir) -> int:
    paket = vt.denetlenecekler(conn, boyut)
    if not paket:
        return 0
    for s in paket:
        if isinstance(s["secenekler"], str):
            s["secenekler"] = json.loads(s["secenekler"])
    kararlar = yaniti_coz(cagir(istem(paket)), {s["id"] for s in paket})
    for sid, (gecerli, neden) in kararlar.items():
        vt.denetim_yaz(conn, sid, "onayli" if gecerli else "red", f"agy: {neden}")
    return len(kararlar)
