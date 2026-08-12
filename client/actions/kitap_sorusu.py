"""
actions/kitap_sorusu.py — Kitaba dayalı somut bir soruyu sunucudaki RAG
motoruna sorar (server/rag.py, docs/mimari.md §9).

`ders_icerigi` ile farkı: `ders_icerigi` bir KONUYU anlatmak için ham kitap
sayfası getirir (öğretmen tetikler, anlatım modelin işidir). Bu araç
öğrenci/öğretmenin somut bir SORUSUNU yanıtlar — cevabı sunucu üretir:
retrieval + rerank + eşik + LLM + sayı-kontrolü zincirinden geçmiş, kaynaklı
bir metin döner. Model bu metni ayrıştırmaz, olduğu gibi okur (CLAUDE.md
"API Prensibi": Brain karar verir, Client görüntüler).

Neden ayrı bir sunucu çağrısı, `ders_icerigi`'nin kelime-örtüşme aramasıyla
değil: CLAUDE.md "RAG Kuralları" — cevap yalnızca retrieval sonucundan
üretilir, serbest üretim yok, skor eşiğin altındaysa LLM'e hiç gidilmez. Bu
disiplin ancak sunucuda (embedding + cross-encoder + eşik) uygulanabilir;
client'ta tekrarlamak "Client ince kalmalı" kuralını (CLAUDE.md Kural 1)
çiğner.

Sunucu çökerse/ulaşılamazsa ya da eşleşen kitap yoksa SESSİZCE devam
edilir (mimari.md §2: "Farabi asla dersi bozmaz") — main.py'nin genel
`speak_error` alarmı burada TETİKLENMEZ (hiç exception fırlatılmaz);
`ders_icerigi`'nin `_SINIRLI_DEVAM`'ıyla aynı ruhta bir kısıt metni döner.
"""

import requests

from actions.ders_icerigi import _ders_eslesir
from core.tahta import sunucu_url as _sunucu_url

ZAMAN_ASIMI_GET  = 5.0            # kitap listesi küçük, hızlı
ZAMAN_ASIMI_POST = 10.0           # ölçüm: soru başına 1-5sn, en kötü 5,3sn görüldü — pay bırakıldı

_SINIRLI_DEVAM = (
    "KISIT: Kitap sorusu sunucusuna ulaşılamadı ya da eşleşen kitap "
    "bulunamadı. Kaynak gösteremeyeceğin bir cevabı UYDURMA — bunun yerine "
    "kazanım metnine sadık kalarak `ders_icerigi` ya da `web_search` ile "
    "devam et. Sınıfa teknik sorun anlatma."
)

# Sunucudaki kitap listesi süreç ömrü boyunca bellekte tutulur — aynı
# `_METIN_ONBELLEK` deseni (ders_icerigi.py): kitap kataloğu ders sırasında
# değişmez, her soruda yeniden çekmek gereksiz bir HTTP çağrısı demek.
_KITAP_ONBELLEK: list[dict] | None = None


def _kitap_listesi() -> list[dict] | None:
    global _KITAP_ONBELLEK
    if _KITAP_ONBELLEK is not None:
        return _KITAP_ONBELLEK
    try:
        r = requests.get(f"{_sunucu_url()}/api/egitim/kitaplar", timeout=ZAMAN_ASIMI_GET)
        r.raise_for_status()
        _KITAP_ONBELLEK = r.json()
        return _KITAP_ONBELLEK
    except Exception:
        return None


def _kitap_id_bul(ders: str | None, sinif: str | None) -> int | None:
    """
    `ders` verilmeden EŞLEŞME YAPILMAZ. `_ders_eslesir(None, ...)` sorgu boşken
    her kitabı kabul eder (ders_icerigi.py'de bilinçli bir tasarım — orada
    "hangi kitaplar var" kataloğunu daraltmak için kullanılıyor). Burada aynı
    boşluk, sınıf düzeyi tutan İLK kitabı seçip fizik sorusunu biyoloji
    kitabından kaynaklı gibi yanıtlamak anlamına gelirdi — sessiz bir
    halüsinasyon. "Yanlış temayı anlatmaktansa hiç anlatma" (ders_icerigi.py).
    """
    if not ders:
        return None
    kitaplar = _kitap_listesi()
    if not kitaplar:
        return None
    for k in kitaplar:
        if sinif and str(k.get("sinif")) != str(sinif).strip():
            continue
        if not _ders_eslesir(ders, k.get("ders", "")):
            continue
        return k.get("id")
    return None


def kitap_sorusu(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    soru = (p.get("soru") or "").strip()
    if not soru:
        return "Soru belirtilmedi. Öğrencinin/öğretmenin sorusunu 'soru' parametresiyle ver."

    ders  = (p.get("ders")  or "").strip() or None
    sinif = (p.get("sinif") or "").strip() or None
    # Sınıf belirtilmediyse tahtanın bulunduğu derslikten çıkar — ders_icerigi
    # ile aynı varsayım (bkz. core/tahta.py).
    if not sinif:
        try:
            from core import tahta
            sinif = tahta.sinif_duzeyi() or None
        except Exception:
            pass

    kitap_id = _kitap_id_bul(ders, sinif)
    if kitap_id is None:
        log("[Kitap Sorusu] eşleşen kitap bulunamadı ya da sunucuya ulaşılamadı, sessiz devam")
        return _SINIRLI_DEVAM

    try:
        r = requests.post(
            f"{_sunucu_url()}/api/egitim/question",
            json={"kitap_id": kitap_id, "soru": soru},
            timeout=ZAMAN_ASIMI_POST,
        )
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        log(f"[Kitap Sorusu] sunucu hatası: {type(e).__name__}: {e}")
        return _SINIRLI_DEVAM

    durum = veri.get("status")

    if durum == "ok":
        kaynaklar = veri.get("sources") or []
        kaynak_metni = ""
        if kaynaklar:
            sayfalar_sirali = dict.fromkeys(str(k["page"]) for k in kaynaklar)  # tekrarsız, sıra korunur
            kitap_adi = kaynaklar[0].get("book", "")
            kaynak_metni = f"\n\nKaynak: {kitap_adi}, s. {', '.join(sayfalar_sirali)}"
        log(f"[Kitap Sorusu] ok · {veri.get('latency_ms')}ms")
        sonuc = (veri.get("answer") or "").strip() + kaynak_metni
        if player is not None and hasattr(player, "show_content"):
            player.show_content("KİTAP SORUSU", sonuc)
        return sonuc

    if durum in ("yetersiz_kaynak", "sayi_kontrolu_reddi"):
        log(f"[Kitap Sorusu] {durum}")
        return "Bu bilgi ders kitabında bu haliyle bulunmuyor."

    if durum == "hata":
        # Belgelenmiş bir durum (mimari.md §9 status enum'u) — sunucu (ör.
        # Ollama kapalı) kendi hatasını YAKALAYIP temiz JSON'la bildirdi,
        # bağlantı/format hatası değil. "beklenmeyen" demek yanıltıcıydı.
        # Ham hata metni bilerek API'ye hiç çıkmıyor (server/main.py
        # SoruYanit'te `hata` alanı yok) — sunucu tarafında soru_log'a
        # yazılıyor, "Brain karar verir, Client görüntüler" ilkesi gereği.
        log("[Kitap Sorusu] sunucu 'hata' durumu bildirdi (ayrıntı soru_log'da)")
        return _SINIRLI_DEVAM

    log(f"[Kitap Sorusu] beklenmeyen durum: {durum}")
    return _SINIRLI_DEVAM
