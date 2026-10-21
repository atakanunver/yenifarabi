"""
title: Farabi Kaynak Arama
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.2.0
description: Farabi modlarında her mesaja Türkiye saatiyle tarih/saat/ders saati ekler; ders kitabı/mevzuat parçalarını farabi-api'den (/api/webui/ara) getirip son kullanıcı mesajının sonuna <baglam> bloğu olarak ekler; düşünme varsayılanını moddan ayarlar.
"""

# Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.4
# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Function olarak yüklenir;
# Open WebUI içinde elle düzenlenmez (kur.py her çalıştığında üzerine yazar).

import asyncio
import hashlib
import json
import urllib.request
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

BLOK_AZAMI_KARAKTER = 7500  # ~2.500 token — 16k bağlamın payı

# 2026-10-04 (kullanıcı isteği): okul/mevzuat/ders sorularında yerel belgeler
# ÖNCELİKLİ — model eskiden "yalnızca ilgiliyse kullan" deyip genel bilgiyle
# cevap verebiliyordu.
GIRIS = ("Aşağıdaki kaynak parçaları kullanıcının mesajı için okulun resmî belgelerinden "
         "(ders kitapları ve mevzuat) geldi. Karşındaki kullanıcı doğrudan bir öğretmen "
         "veya okul idarecisidir (müdür / müdür yardımcısı). Onlara tam yetkili, saygın "
         "ve yetkin bir meslektaş olarak yardımcı ol. Asla 'okul idaresine sor', 'müdürlüğe git' "
         "gibi yönlendirmeler yapma; doğrudan idari ve pedagojik çözümü sun. Okul, mevzuat, "
         "yönetmelik ve ders sorularında ÖNCE bu parçalara dayan. Sorunun cevabı parçalarda "
         "yoksa bunu tek cümleyle belirtip genel bilginle yetkin biçimde cevap ver; tahmin yürütme, "
         "madde/sayfa/sayı uydurma. Kullandığın bilginin sonunda kaynağı köşeli parantezle belirt, "
         "örneğin [657 Sayılı Devlet Memurları Kanunu, s. 16].")

ZAYIF_NOTU = ("Karşındaki kullanıcı okulumuzun öğretmeni veya okul idarecisidir (müdür / "
              "müdür yardımcısı). Ona tam yetkili, uzman ve çözüm odaklı bir çalışma arkadaşı "
              "olarak doğrudan ve net yardımcı ol. Asla 'okul idaresine sor', 'müdürlüğe başvur', "
              "'idareye dilekçe yaz' gibi yönlendirmeler yapma, çünkü soruyu soran zaten okul "
              "idaresi veya eğitimcidir. Bu mesaj için belgelerden eşleşen parça gelmedi; bunu kullanıcıya "
              "'belgelerde bulamadım / kaynağım yok' diye söylemene gerek yok. Önceki cevaplarında "
              "kaynak gösterdiysen onlara dayanmaya devam edebilirsin; ders konularını, genel mevzuatı "
              "(657 Sayılı DMK, MEB Ortaöğretim Kurumları Yönetmeliği vb.) ve okul işleyişini kendi "
              "bilginle doğrudan, açık ve yetkin biçimde anlat. Kesin belge olmadan hayali madde "
              "numarası veya sayfa numarası uydurma; emin olmadığın mevzuat ayrıntısını kısaca belirt.")


ISTANBUL = ZoneInfo("Europe/Istanbul")
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık"]


def yerel_zaman_metni(an: datetime | None = None) -> str:
    """Okul API'sine ulaşılamazsa (ders saati bilgisi olmadan) kullanılan metin."""
    an = an or datetime.now(ISTANBUL)
    return (f"Şu an (Türkiye saati): {an.day} {AYLAR[an.month - 1]} {an.year} "
            f"{GUNLER[an.isoweekday() - 1]}, saat {an:%H:%M}.")


def son_kullanici_mesaji(messages: list) -> str:
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        icerik = m.get("content")
        if isinstance(icerik, str):
            return icerik.strip()
        if isinstance(icerik, list):
            return " ".join(p.get("text", "") for p in icerik
                            if isinstance(p, dict) and p.get("type") == "text").strip()
        return ""
    return ""


TAKIP_AZAMI_KELIME = 8  # bundan kısa mesajlar takip sorusu sayılır


def arama_sorgusu(messages: list) -> str:
    """RAG'a giden sorgu: son kullanıcı mesajı; kısa bir takip sorusuysa (\"peki babalık
    izninde?\") bağlam kaybolmasın diye önceki kullanıcı mesajı başa eklenir."""
    son = son_kullanici_mesaji(messages)
    if not son or len(son.split()) > TAKIP_AZAMI_KELIME:
        return son
    kullanici = [m for m in (messages or []) if isinstance(m, dict) and m.get("role") == "user"]
    onceki = son_kullanici_mesaji(kullanici[:-1]) if len(kullanici) > 1 else ""
    return f"{onceki[:200]} {son}" if onceki else son


def kaynak_blogu(sonuc: dict) -> str | None:
    if not isinstance(sonuc, dict):
        return None
    durum = sonuc.get("durum")
    if durum == "zayif":
        return ZAYIF_NOTU
    parcalar = sonuc.get("parcalar")
    if durum != "ok" or not isinstance(parcalar, list) or not parcalar:
        return None
    gecerli = [p for p in parcalar
               if isinstance(p, dict) and isinstance(p.get("metin"), str)
               and isinstance(p.get("kaynak"), str)]
    if not gecerli:
        return None
    blok = GIRIS
    for i, p in enumerate(gecerli, start=1):
        ek = f"\n\n[{i}] {p['kaynak']}\n{p['metin'].strip()}"
        if len(blok) + len(ek) > BLOK_AZAMI_KARAKTER:
            kalan = BLOK_AZAMI_KARAKTER - len(blok)
            if kalan > 200:
                blok += ek[:kalan]
            break
        blok += ek
    return blok


WIKI_GIRIS = ("Okul wiki'sinin sabit sayfaları (yönetimin kısa kuralları). Eski olabilir; belge ya da araç "
              "sonucuyla çelişirse onlar geçerlidir. Başka bilgi için wiki_ara / wiki_oku kullan.")


def wiki_blogu(sonuc: dict | None) -> str | None:
    """Sabit wiki sayfaları; boşsa None. Bütçe sunucuda (≤1.000 karakter) kırpılır."""
    if not isinstance(sonuc, dict) or sonuc.get("durum") != "ok":
        return None
    satirlar = [f"- [{k['ad']}, {k.get('tarih', '?')}] {k['metin']}" for k in sonuc.get("sayfalar") or []
                if isinstance(k, dict) and isinstance(k.get("ad"), str) and isinstance(k.get("metin"), str)]
    return WIKI_GIRIS + "\n" + "\n".join(satirlar) if satirlar else None


# Dinamik bağlam (saat, wiki, kaynak) SİSTEM mesajına değil kullanıcı mesajının sonuna eklenir ve her
# kullanıcı mesajına bir kez, aynı metinle bağlı kalır (2026-10-21). Neden: Ollama'daki hibrit model yalnızca
# önceki istemin SON ~512 token'ında bir kontrol noktasına geri dönebilir; sistem mesajı her turda değişince
# (dakikayla değişen saat) sabit ~7 bin token'lık sistem+araç öneki ve tüm geçmiş her yeni mesajda baştan
# işleniyordu (ilk cevap 25–35 sn). Geçmişteki mesaj bloğuyla birlikte aynı kaldığında yalnızca yeni mesaj işlenir.
BAGLAM_ONBELLEK: OrderedDict[str, str] = OrderedDict()
BAGLAM_AZAMI_KAYIT = 1000


def _mesaj_metni(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(p.get("text") or "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _baglam_anahtari(sohbet: str, sira: int, m: dict) -> str:
    return f"{sohbet}|{sira}|{hashlib.sha1(_mesaj_metni(m).encode('utf-8')).hexdigest()[:16]}"


def _baglami_ilistir(m: dict, blok: str) -> None:
    ek = f"\n\n<baglam>\n{blok}\n</baglam>"
    if isinstance(m.get("content"), str):
        m["content"] += ek
    elif isinstance(m.get("content"), list):
        m["content"].append({"type": "text", "text": ek.strip()})


def baglam_uygula(body: dict, blok: str | None, sohbet: str = "") -> None:
    """Son kullanıcı mesajına yeni bloğu ekler (ve saklar); önceki kullanıcı mesajlarına kendi eski bloklarını geri koyar."""
    mesajlar = body.setdefault("messages", [])
    kullanicilar = [m for m in mesajlar if isinstance(m, dict) and m.get("role") == "user"]
    for sira, m in enumerate(kullanicilar):
        anahtar = _baglam_anahtari(sohbet, sira, m)
        if sira == len(kullanicilar) - 1:
            if blok:
                BAGLAM_ONBELLEK[anahtar] = blok
                BAGLAM_ONBELLEK.move_to_end(anahtar)
                while len(BAGLAM_ONBELLEK) > BAGLAM_AZAMI_KAYIT:
                    BAGLAM_ONBELLEK.popitem(last=False)
                _baglami_ilistir(m, blok)
        elif anahtar in BAGLAM_ONBELLEK:
            _baglami_ilistir(m, BAGLAM_ONBELLEK[anahtar])


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(default="http://127.0.0.1:8000/api/webui/ara")
        api_key: str = Field(default="")
        zaman_asimi_sn: float = Field(default=8.0)
        # Dashboard /api/okul (tarih + ders saati); yalnızca localhost + anahtar.
        okul_url: str = Field(default="http://127.0.0.1/api/okul")
        okul_key: str = Field(default="")
        # Atos wiki'sinin sabit sayfaları (farabi-api /api/webui/wiki/sabit); yalnızca meta.farabi_hafiza=true modeller + admin.
        wiki_sabit_url: str = Field(default="http://127.0.0.1:8000/api/webui/wiki/sabit")

    def __init__(self):
        self.valves = self.Valves()

    def _ara(self, kapsam: str, soru: str) -> dict | None:
        """Bloklayan HTTP çağrısı — inlet bunu asyncio.to_thread ile çağırır
        (Open WebUI'nin olay döngüsü farabi-api yavaşken donmasın)."""
        try:
            istek = urllib.request.Request(
                self.valves.api_url,
                data=json.dumps({"kapsam": kapsam, "soru": soru}).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "X-Farabi-WebUI-Key": self.valves.api_key},
            )
            # Ortam proxy değişkenleri 127.0.0.1 çağrısını proxy'ye yönlendirmesin.
            acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with acici.open(istek, timeout=self.valves.zaman_asimi_sn) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — arama hatası sohbeti bozmamalı, kaynaksız devam
            print(f"[farabi_kaynak] arama başarısız: {type(e).__name__}: {e}")
            return None

    def _wiki_sabit(self) -> dict | None:
        """Wiki'nin sabit sayfaları. Bloklayan çağrı (to_thread); hata → None."""
        try:
            istek = urllib.request.Request(
                self.valves.wiki_sabit_url,
                data=b"{}",
                headers={"Content-Type": "application/json", "X-Farabi-WebUI-Key": self.valves.api_key},
            )
            acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with acici.open(istek, timeout=4.0) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — wiki sohbeti engellememeli
            print(f"[farabi_kaynak] wiki sabit sayfaları alınamadı: {type(e).__name__}")
            return None

    def _zaman(self) -> str:
        """Tarih/saat + o anki ders saati. Bloklayan çağrı (to_thread ile).
        Okul API'si yoksa yerel saat (ders bilgisi olmadan) — asla istisna atmaz."""
        try:
            istek = urllib.request.Request(self.valves.okul_url.rstrip("/") + "/simdi",
                                           headers={"X-Farabi-Okul-Key": self.valves.okul_key})
            acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with acici.open(istek, timeout=2.0) as r:
                metin = json.load(r).get("metin")
            if isinstance(metin, str) and metin.startswith("Şu an"):
                return metin
        except Exception:  # noqa: BLE001 — zaman bilgisi yardımcı; yerel saate düş
            pass
        return yerel_zaman_metni()

    async def inlet(self, body: dict, __model__: dict | None = None,
                    __metadata__: dict | None = None, __user__: dict | None = None) -> dict:
        if (__metadata__ or {}).get("task"):
            return body  # başlık/etiket gibi arka plan görevleri — arama yok

        try:
            return await self._inlet_govde(body, __model__, __user__, (__metadata__ or {}).get("chat_id") or "")
        except Exception as e:  # noqa: BLE001 — filtre hatası sohbeti engellememeli, gövde değişmeden gider
            print(f"[farabi_kaynak] inlet hatası: {type(e).__name__}: {e}")
            return body

    async def _inlet_govde(self, body: dict, __model__: dict | None, __user__: dict | None = None,
                           sohbet: str = "") -> dict:
        meta = (((__model__ or {}).get("info") or {}).get("meta")) or {}
        # Open WebUI, filtrelerden ÖNCE params'ı body["options"]'a taşır ve Ollama'ya
        # giderken yalnızca options["think"]'i köke alır; üst düzey body["think"] atılır.
        secenekler = body.get("options") if isinstance(body.get("options"), dict) else {}
        kullanici_secti = (body.get("think") is not None
                           or (body.get("params") or {}).get("think") is not None
                           or secenekler.get("think") is not None)
        if not kullanici_secti and "farabi_think" in meta:
            body["think"] = bool(meta["farabi_think"])
            body["options"] = {**secenekler, "think": bool(meta["farabi_think"])}

        kapsam = meta.get("farabi_kapsam")
        soru = arama_sorgusu(body.get("messages"))

        async def _zaman_guvenli():
            try:
                return await asyncio.to_thread(self._zaman)
            except Exception:  # noqa: BLE001 — test/yama kaynaklı istisna bile sohbeti bozmasın
                return None

        async def _hic():
            return None

        wiki_acik = bool(meta.get("farabi_hafiza")) and (__user__ or {}).get("role") == "admin"

        # Zaman, kaynak araması ve wiki sabit sayfaları paralel — toplam gecikme üçünün en uzunu.
        zaman, sonuc, wiki = await asyncio.gather(
            _zaman_guvenli(),
            asyncio.to_thread(self._ara, kapsam, soru) if (kapsam and soru) else _hic(),
            asyncio.to_thread(self._wiki_sabit) if wiki_acik else _hic())
        bloklar = [zaman] if zaman else []
        try:
            wblok = wiki_blogu(wiki)
            if wblok:
                bloklar.append(wblok)
        except Exception as e:  # noqa: BLE001
            print(f"[farabi_kaynak] wiki bloğu eklenemedi: {type(e).__name__}")
        try:
            blok = kaynak_blogu(sonuc) if sonuc else None
            if blok:
                bloklar.append(blok)
        except Exception as e:  # noqa: BLE001 — blok eklenemezse sohbet kaynaksız sürer
            print(f"[farabi_kaynak] blok eklenemedi: {type(e).__name__}: {e}")
        baglam_uygula(body, "\n\n".join(bloklar) or None, sohbet)
        return body
