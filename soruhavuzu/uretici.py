"""soruhavuzu/uretici.py — bir kaynak biriminden yerel Ollama (qwen3.8:27b) ile çoktan seçmeli sorular."""

import json
import re

import httpx

MODEL = "qwen3.8:27b"
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

SISTEM = (
    "Sen MEB lise öğretmenisin ve sınıf içi yarışma oyunları için soru hazırlıyorsun. "
    "YALNIZCA verilen kaynak metne dayan; metinde olmayan bilgiyi soru veya cevap yapma. "
    "Soruyu öğrenci kaynak metni GÖRMEDEN çözecek: 'tabloya göre', 'metne göre', 'şekildeki' "
    "gibi atıflar YASAK; tablodaki bilgiyi kullanacaksan bilgiyi doğrudan sor. "
    "Her soru tek başına anlaşılır olsun. "
    "Sorular KONU BİLGİSİNİ ölçsün; kitabın yapısı, bölüm/ünite adları, kazanım veya "
    "öğrenme alanı hakkında soru YASAK. Etkinlik, alıştırma veya kontrol noktası sayfalarındaki "
    "bilgiler de (tanım, olgu, kural, tarih, sayısal veri) soru kaynağıdır. "
    "Yalnızca içindekiler, ön söz, kaynakça gibi hiç konu bilgisi olmayan sayfalarda daha az "
    "soru üretebilirsin. "
    "4 şıktan yalnızca biri doğru olsun, çeldiriciler makul olsun. Kısa cevap 1-6 kelime. "
    "Zorluk 1 (hatırlama) ile 4 (çok adımlı akıl yürütme) arası. "
    'Yalnızca JSON döndür: {"sorular": [...]}.'
)


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
            and s["kisa_cevap"].strip()
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


def ayristir(ham: str, birim: dict) -> list[dict]:
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
