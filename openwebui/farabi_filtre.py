"""
title: Farabi Kaynak Arama
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Farabi modlarında her kullanıcı mesajı için ders kitabı/mevzuat parçalarını farabi-api'den (/api/webui/ara) getirip sistem mesajına ekler; düşünme varsayılanını moddan ayarlar.
"""

# Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.4
# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Function olarak yüklenir;
# Open WebUI içinde elle düzenlenmez (kur.py her çalıştığında üzerine yazar).

import asyncio
import json
import urllib.request

from pydantic import BaseModel, Field

BLOK_AZAMI_KARAKTER = 7500  # ~2.500 token — 16k bağlamın payı

GIRIS = ("Aşağıdaki kaynak parçaları kullanıcının son mesajı için okulun arama sisteminden geldi. "
         "Yalnızca soruyla ilgiliyse kullan. Kullandığın bilginin sonunda kaynağı köşeli parantezle "
         "belirt, örneğin [Kimya 10, s. 84]. Parçalarda olmayan sayfa numarası uydurma.")
ZAYIF_NOTU = ("Not: Bu mesaj için kitaplarda/mevzuatta yeni bir kaynak parçası bulunamadı. "
              "Önceki cevaplarında kaynak gösterdiysen onlara dayanmaya devam edebilirsin; "
              "yeni bilgi ekliyorsan bunun kitaba/mevzuata dayanmadığını açıkça söyle ve "
              "sayfa numarası uydurma.")


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


def sistem_mesajina_ekle(body: dict, blok: str) -> None:
    mesajlar = body.setdefault("messages", [])
    if mesajlar and mesajlar[0].get("role") == "system" and isinstance(mesajlar[0].get("content"), str):
        mesajlar[0]["content"] = mesajlar[0]["content"].rstrip() + "\n\n" + blok
    else:
        mesajlar.insert(0, {"role": "system", "content": blok})


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(default="http://127.0.0.1:8000/api/webui/ara")
        api_key: str = Field(default="")
        zaman_asimi_sn: float = Field(default=8.0)

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

    async def inlet(self, body: dict, __model__: dict | None = None,
                    __metadata__: dict | None = None) -> dict:
        if (__metadata__ or {}).get("task"):
            return body  # başlık/etiket gibi arka plan görevleri — arama yok

        try:
            return await self._inlet_govde(body, __model__)
        except Exception as e:  # noqa: BLE001 — filtre hatası sohbeti engellememeli, gövde değişmeden gider
            print(f"[farabi_kaynak] inlet hatası: {type(e).__name__}: {e}")
            return body

    async def _inlet_govde(self, body: dict, __model__: dict | None) -> dict:
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
        if not kapsam:
            return body
        soru = son_kullanici_mesaji(body.get("messages"))
        if not soru:
            return body

        sonuc = await asyncio.to_thread(self._ara, kapsam, soru)
        try:
            blok = kaynak_blogu(sonuc) if sonuc else None
            if blok:
                sistem_mesajina_ekle(body, blok)
        except Exception as e:  # noqa: BLE001 — blok eklenemezse sohbet kaynaksız sürer
            print(f"[farabi_kaynak] blok eklenemedi: {type(e).__name__}: {e}")
        return body
