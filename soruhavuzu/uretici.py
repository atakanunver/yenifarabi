"""soruhavuzu/uretici.py — bir kaynak biriminden yerel Ollama (`farabi` takma adı) ve/veya AGY (gemini-3.8-flash-low) ile çoktan seçmeli sorular."""

import json
import re
import subprocess
from pathlib import Path

import httpx

MODEL = "farabi"  # Ollama takma adı (şu an qwen3.8:27b); model değişimi: ollama cp <model> farabi
AGY_BIN = "/home/ata/.local/bin/agy"
AGY_MODEL = "gemini-3.8-flash-low"
AGY_SEMA = Path(__file__).with_name("agy_uret_sema.json")
CALISMA_DIZINI = Path("/tmp/soruhavuzu-agy")
DERSLER = {
    "matematik",
    "fizik",
    "kimya",
    "biyoloji",
    "edebiyat",
    "tarih",
    "cografya",
    "din",
    "felsefe",
    "ingilizce",
    "almanca",
}
SEKIL = re.compile(r"şekil|grafik|tablo|görsel|resim(de|deki)", re.IGNORECASE)

SISTEM_MAARIF = (
    "Sen MEB lise öğretmenisin ve MEB 'Bağlam Temelli Çoktan Seçmeli Soru Yazım Kılavuzu' ile "
    "Türkiye Yüzyılı Maarif Modeli ilkelerine tam uygun sorular hazırlıyorsun.\n"
    "YALNIZCA verilen kaynak metne dayan; metinde olmayan bilgiyi soru veya cevap yapma.\n\n"
    "MAARİF MODELİ VE BAĞLAM TEMELLİ SORU KRİTERLERİ (9, 10, 11. Sınıflar):\n"
    "1. BAĞLAM ODAKLI VE GERÇEK HAYAT KURGUSU: Soru; bir günlük yaşam durumu, deneysel bir veri seti, "
    "bilimsel/tarihsel bir olay, problem senaryosu veya gerçekçi bir durum üzerine kurulmalıdır. Bağlamı soru metninin başında açıkça ver.\n"
    "2. BAĞLAMSIZ ÇÖZÜLEMEZ ('BAĞLAMSIZLIK TESTİ'): Öğrenci soruyu yalnızca ezberlediği formülle veya tanımı "
    "hatırlayarak çözememeli; mutlaka verilen senaryodaki veriyi/öncülü okuyup ayıklayarak ve akıl yürüterek çözebilmelidir. "
    "Bağlam kapatıldığında doğrudan çözülebilecek kuru bilgi/tanım soruları YASAKTIR.\n"
    "3. ÖĞRENME ÇIKTISI TEMELLİ: Her soru müfredattaki kazanımın ölçtüğü beceriye (veri yorumlama, analiz, "
    "sebep-sonuç ilişkilendirme, çıkarım yapma) hizmet etmelidir.\n"
    "4. GEREKSİZ DETAYDAN ARINDIRILMIŞ: Metin içi boş hikayelerle şişirilmemeli; ölçülen beceriye doğrudan hizmet eden net ve gerçekçi verilere dayanmalıdır.\n"
    "5. GÜÇLÜ ÇELDİRİCİLER: Seçenekler rastgele konmamalı; öğrencilerin sıklıkla düştüğü tipik kavram yanılgılarına ve mantık hatalarına göre tasarlanmalıdır.\n"
    "6. BAĞIMSIZ VE GÖRSEL ATIFSIZ: Öğrenci soruyu ekrana bakarak çözecektir. 'şekildeki', 'grafiğe göre', 'tabloya göre', 'metne göre' "
    "gibi atıflar YASAKTIR. Gerekli tüm verileri ve durumu doğrudan soru metni içinde aktar.\n"
    "7. BİÇİM: 4 şıktan yalnızca biri doğru olsun. Kısa cevap 1-6 kelime. Zorluk 1 (temel kavrama) ile 4 (üst düzey akıl yürütme) arası dağılsın.\n"
    'Yalnızca JSON döndür: {"sorular": [...]}.'
)

SISTEM_YKS_12 = (
    "Sen MEB lise öğretmenisin ve 12. Sınıf YKS (TYT/AYT) sınavına hazırlanan öğrenciler için çoktan seçmeli sorular hazırlıyorsun.\n"
    "12. Sınıf Maarif Modeli kapsamında olmayıp klasik MEB YKS müfredatına tabidir.\n"
    "YALNIZCA verilen 12. sınıf ders kitabı metnine dayan; metinde olmayan bilgiyi soru veya cevap yapma.\n\n"
    "12. SINIF YKS SORU KRİTERLERİ:\n"
    "1. KAZANIM VE YKS UYUMU: Soru doğrudan 12. sınıf kazanımını ve YKS soru standartlarını ölçmelidir.\n"
    "2. KAVRAMSAL VE ANALİTİK ÖLÇME: Sorular kavramsal bilgiyi, problem çözmeyi ve analitik düşünmeyi ölçsün.\n"
    "3. BAĞIMSIZ VE GÖRSEL ATIFSIZ: 'şekildeki', 'grafiğe göre', 'tabloya göre', 'metne göre' gibi atıflar YASAKTIR. Bilgiyi doğrudan soru metninde ver.\n"
    "4. BİÇİM: 4 şıktan yalnızca biri doğru olsun, çeldiriciler mantıklı ve güçlü olsun. Kısa cevap 1-6 kelime. Zorluk 1 ile 4 arası dağılsın.\n"
    'Yalnızca JSON döndür: {"sorular": [...]}.'
)

SISTEM = SISTEM_MAARIF


def istem(birim: dict) -> list[dict]:
    if birim["tur"] == "kitap":
        gorev = (
            "Bu ders kitabı metninden farklı alt konulara yayılan 4 soru üret "
            "(zorluk 1, 2, 3, 4 birer tane)."
        )
    else:
        gorev = (
            "Bu sayfa hazır test sorusu içeriyor. Cevap anahtarı/çözümü sayfada varsa ya da "
            "doğru cevap metinden kesin çıkıyorsa her soruyu AYNI içerikle yaz (en fazla 6); "
            "cevabı kesin değilse o soruyu ATLA."
        )
    ders_satiri = (
        f"Ders: {birim['ders']}"
        if birim.get("ders")
        else f"Her soruya 'ders' alanı ekle; şunlardan biri: {', '.join(sorted(DERSLER))}"
    )
    sema = (
        '{"sorular": [{"konu": "kısa konu adı", "soru": "...", "kisa_cevap": "...", '
        '"secenekler": ["A", "B", "C", "D"], "dogru_index": 0, "zorluk": 1, "sayfa": 0'
        + (', "ders": "fizik"' if not birim.get("ders") else "")
        + "}]}"
    )
    kullanici = (
        f"{ders_satiri}\nSınıf: {birim['sinif']}\nKaynak: {birim['etiket']}\n"
        f"Görev: {gorev}\n'sayfa' alanına sorunun dayandığı sayfa numarasını yaz.\n"
        f"Biçim: {sema}\n\nKAYNAK METİN:\n{birim['metin']}"
    )
    return [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": kullanici},
    ]


def _gecerli(s: dict) -> bool:
    try:
        return bool(
            isinstance(s.get("soru"), str)
            and s["soru"].strip()
            and isinstance(s.get("kisa_cevap"), str)
            and s["kisa_cevap"].strip().lstrip(":;-–. ").strip()  # temizlenince boş kalan cevap geçersiz
            and isinstance(s.get("secenekler"), list)
            and len(s["secenekler"]) == 4
            and all(isinstance(x, str) and x.strip() for x in s["secenekler"])
            and len({x.strip() for x in s["secenekler"]}) == 4
            and int(s.get("dogru_index")) in range(4)
            and int(s.get("zorluk")) in range(1, 5)
            and not SEKIL.search(s["soru"])
        )
    except (TypeError, ValueError):
        return False


def ayristir(ham: str | dict, birim: dict) -> list[dict]:
    if isinstance(ham, dict):
        veri = ham
    else:
        try:
            veri = json.loads(ham)
        except (json.JSONDecodeError, TypeError):
            return []
    sorular = veri.get("sorular") if isinstance(veri, dict) else None
    cikti = []
    for s in sorular if isinstance(sorular, list) else []:
        if not isinstance(s, dict) or not _gecerli(s):
            continue
        ders = birim.get("ders") or s.get("ders")
        if ders not in DERSLER:
            continue
        etiket = birim["etiket"]
        sayfa = s.get("sayfa")
        # Kitap birimleri birden çok sayfa kapsar; PDF birimlerinde sayfa zaten kesin.
        if (
            birim["tur"] == "kitap"
            and isinstance(sayfa, int)
            and sayfa > 0
            and ", s. " in etiket
        ):
            etiket = etiket.rsplit(", s. ", 1)[0] + f", s. {sayfa}"
        cikti.append(
            {
                "ders": ders,
                "sinif": birim["sinif"],
                "konu": str(s.get("konu") or "Genel").strip()[:80],
                "soru": s["soru"].strip(),
                "kisa_cevap": s["kisa_cevap"].strip().lstrip(":;-–. ").strip(),
                "secenekler": [x.strip() for x in s["secenekler"]],
                "dogru_index": int(s["dogru_index"]),
                "zorluk": int(s["zorluk"]),
                "kaynak": etiket,
            }
        )
    return cikti


def uret(
    birim: dict, ollama_url: str = "http://127.0.0.1:11434", zaman_asimi: float = 180
) -> list[dict]:
    govde = {
        "model": MODEL,
        "messages": istem(birim),
        "stream": False,
        "think": False,
        "format": "json",
        # normal yanıt ~600-700 token; tekrar döngüsüne giren model 8k+ üretip zaman aşımına düşüyordu
        "options": {"temperature": 0.4, "num_predict": 2048},
    }
    with httpx.Client(timeout=zaman_asimi, trust_env=False) as c:
        r = c.post(f"{ollama_url}/api/chat", json=govde)
        if r.status_code == 500:  # Ollama arada sebepsiz 500 dönüyor; aynı istek tekrarda geçiyor
            r = c.post(f"{ollama_url}/api/chat", json=govde)
        r.raise_for_status()
        return ayristir(r.json().get("message", {}).get("content", ""), birim)


def istem_kazanim(kazanim: dict, kaynak: dict) -> list[dict]:
    kaynak_metin = re.sub(r"\.{4,}", " ", kaynak["metin"])
    sinif = kazanim.get("sinif")
    if sinif == 12:
        sistem = SISTEM_YKS_12
        gorev = (
            "Görev: Bu kazanımı ölçen 5 çoktan seçmeli YKS (TYT/AYT) tarzı soru üret (zorluk 1-4 dağıt). "
            "Her soru bu kazanımı ölçmeli; 12. sınıf ders kitabı metnine sadık kalarak kavramsal ve analitik düşünmeyi ölçen, "
            "çeldiricileri güçlü sorular hazırla. Harici görsel atıfı ('şekildeki/grafiğe göre') yapma; bilgiyi soru metninde açıkça ver. "
            "Kaynak metinde geçse de kazanımla ilgisiz bilgiyi sorma. 'konu' alanına kazanımın kısa adını yaz.\n"
        )
    else:
        sistem = SISTEM_MAARIF
        gorev = (
            "Görev: Bu kazanımı ölçen 5 çoktan seçmeli soru üret (zorluk 1-4 dağıt). "
            "Her soru bu kazanımı ölçmeli; MEB Bağlam Temelli Soru Yazım Kılavuzu ilkelerine tam uy:\n"
            "- Her soru için gerçek hayat, deney, veri seti, olay veya problem senaryosu kurgula.\n"
            "- Sorular BAĞLAMSIZ ÇÖZÜLEMEZ olsun (Bağlamsızlık Testi: metin/senaryo kapatıldığında ezberle çözülememeli, veriyi analiz ettirmeli).\n"
            "- Gereksiz laf kalabalığından arındırılmış, ölçülen beceriye odaklı net veriler kullan.\n"
            "- Çeldiricileri öğrencilerin sıkça yaptığı mantık hataları ve kavram yanılgılarına göre hazırla.\n"
            "- 'şekildeki/grafikteki/tabloya göre' gibi harici görsele atıf yapma, gereken tüm veriyi soru metninde açıkça ver.\n"
            "Kaynak metinde geçse de kazanımla ilgisiz bilgiyi sorma. 'konu' alanına kazanımın kısa adını yaz.\n"
        )
    kullanici = (
        f"Ders: {kazanim['ders']}\nSınıf: {kazanim['sinif']}\nKaynak: {kaynak['etiket']}\n"
        f"KAZANIM: {kazanim['metin']}\n"
        f"{gorev}"
        'Biçim: {"sorular": [{"konu": "...", "soru": "...", "kisa_cevap": "...", '
        '"secenekler": ["A", "B", "C", "D"], "dogru_index": 0, "zorluk": 1, "sayfa": 0}]}\n\n'
        f"KAYNAK METİN:\n{kaynak_metin}"
    )
    return [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}]


def istem_kazanim_agy(kazanim: dict, kaynak: dict) -> str:
    kaynak_metin = re.sub(r"\.{4,}", " ", kaynak.get("metin", ""))
    sinif = kazanim.get("sinif")
    if sinif == 12:
        sistem = SISTEM_YKS_12
        gorev = (
            "Görev: Bu kazanımı ölçen 5 çoktan seçmeli YKS (TYT/AYT) tarzı soru üret (zorluk 1-4 dağıt). "
            "Her soru bu kazanımı ölçmeli; 12. sınıf ders kitabı metnine sadık kalarak kavramsal ve analitik düşünmeyi ölçen, "
            "çeldiricileri güçlü sorular hazırla. Harici görsel atıfı ('şekildeki/grafiğe göre') yapma; bilgiyi soru metninde açıkça ver. "
            "Kaynak metinde geçse de kazanımla ilgisiz bilgiyi sorma. 'konu' alanına kazanımın kısa adını yaz.\n\n"
        )
    else:
        sistem = SISTEM_MAARIF
        gorev = (
            "Görev: Bu kazanımı ölçen 5 çoktan seçmeli soru üret (zorluk 1-4 dağıt). "
            "Her soru bu kazanımı ölçmeli; MEB Bağlam Temelli Soru Yazım Kılavuzu ilkelerine tam uy:\n"
            "- Her soru için gerçek hayat, deney, veri seti, olay veya problem senaryosu kurgula.\n"
            "- Sorular BAĞLAMSIZ ÇÖZÜLEMEZ olsun (Bağlamsızlık Testi: metin/senaryo kapatıldığında ezberle çözülememeli, veriyi analiz ettirmeli).\n"
            "- Gereksiz laf kalabalığından arındırılmış, ölçülen beceriye odaklı net veriler kullan.\n"
            "- Çeldiricileri öğrencilerin sıkça yaptığı mantık hataları ve kavram yanılgılarına göre hazırla.\n"
            "- 'şekildeki/grafikteki/tabloya göre' gibi harici görsele atıf yapma, gereken tüm veriyi soru metninde açıkça ver.\n"
            "Kaynak metinde geçse de kazanımla ilgisiz bilgiyi sorma. 'konu' alanına kazanımın kısa adını yaz.\n\n"
        )
    return (
        f"{sistem}\n\n"
        f"Ders: {kazanim['ders']}\nSınıf: {kazanim['sinif']}\nKaynak: {kaynak['etiket']}\n"
        f"KAZANIM: {kazanim['metin']}\n"
        f"{gorev}"
        f"KAYNAK METİN:\n{kaynak_metin[:30000]}"
    )


def uret_kazanim_agy(
    kazanim: dict,
    kaynak: dict,
    model: str = AGY_MODEL,
    zaman_asimi: int = 120,
) -> list[dict]:
    """AGY (Antigravity CLI) ile hızlı ve ucuz model (gemini-3.8-flash-low) kullanarak 5 soru üretir."""
    birim = {
        "tur": "kitap",
        "ders": kazanim["ders"],
        "sinif": kazanim["sinif"],
        "etiket": kaynak["etiket"],
        "metin": kaynak["metin"],
    }
    if not Path(AGY_BIN).exists():
        return []
    CALISMA_DIZINI.mkdir(exist_ok=True)
    istem_metni = istem_kazanim_agy(kazanim, kaynak)
    try:
        r = subprocess.run(
            [
                AGY_BIN,
                "-p",
                istem_metni,
                "--model",
                model,
                "--mode",
                "plan",
                "--output-format",
                "json",
                "--json-schema",
                str(AGY_SEMA),
                "--print-timeout",
                f"{zaman_asimi}s",
            ],
            cwd=CALISMA_DIZINI,
            capture_output=True,
            text=True,
            timeout=zaman_asimi + 30,
        )
        if r.returncode != 0:
            return []
        dis = json.loads(r.stdout)
        veri = dis.get("structured_output") if isinstance(dis, dict) else None
        if not veri:
            ic = dis.get("response", "") if isinstance(dis, dict) else ""
            if isinstance(ic, str):
                ic = ic.strip().removeprefix("```json").removeprefix("```").strip()
            veri = ic
        return ayristir(veri, birim)
    except Exception:
        return []


def uret_kazanim(
    kazanim: dict,
    kaynak: dict,
    ollama_url: str = "http://127.0.0.1:11434",
    zaman_asimi: float = 180,
    motor: str = "hibrit",
    agy_model: str = AGY_MODEL,
) -> list[dict]:
    if motor == "agy":
        return uret_kazanim_agy(kazanim, kaynak, model=agy_model)

    birim = {
        "tur": "kitap",
        "ders": kazanim["ders"],
        "sinif": kazanim["sinif"],
        "etiket": kaynak["etiket"],
        "metin": kaynak["metin"],
    }
    govde = {
        "model": MODEL,
        "messages": istem_kazanim(kazanim, kaynak),
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.4, "num_predict": 2048},
    }
    sorular = []
    ollama_hatasi = None
    try:
        with httpx.Client(timeout=zaman_asimi, trust_env=False) as c:
            r = c.post(f"{ollama_url}/api/chat", json=govde)
            if r.status_code == 500:
                r = c.post(f"{ollama_url}/api/chat", json=govde)
            r.raise_for_status()
            sorular = ayristir(r.json().get("message", {}).get("content", ""), birim)
    except Exception as e:
        ollama_hatasi = e
        sorular = []

    if motor == "hibrit" and not sorular:
        sorular = uret_kazanim_agy(kazanim, kaynak, model=agy_model)
    elif motor == "ollama" and ollama_hatasi is not None:
        raise ollama_hatasi

    return sorular
