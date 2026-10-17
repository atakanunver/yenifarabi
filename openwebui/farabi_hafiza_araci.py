"""
title: Atos Hafıza
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Okulun ortak kalıcı hafızası: bilgi/karar/belge özeti kaydet (onayla), ara, unut. Yalnızca yönetici.
"""

# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Tool olarak yüklenir (yalnızca İdare grubu).
# Sunucu ucu: farabi-api server/hafiza.py. Kayıt iki adımlı: önce taslak, kullanıcı onaylayınca
# onaylandi=True. Model "kaydettim/unuttum" demeyi YALNIZCA bu aracın sonucuna dayandırır.
# Bağlam bütçesi (16k): açıklamalar bilerek kısa tutulur.

import re

import httpx
from pydantic import BaseModel

ULASILAMADI = "Hafıza servisine ulaşılamadı."
YONETICI_RET = "Hafızaya yalnızca yönetici hesabı erişebilir."
TARIH = re.compile(r"\d{4}-\d{2}-\d{2}")


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8000/api/webui/hafiza"
        api_key: str = ""
        zaman_asimi_sn: float = 20.0

    def __init__(self):
        self.valves = self.Valves()

    @staticmethod
    def _yonetici(user) -> bool:
        return isinstance(user, dict) and user.get("role") == "admin"

    async def _post(self, yol: str, govde: dict):
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn, trust_env=False) as c:
                r = await c.post(
                    self.valves.api_url.rstrip("/") + yol,
                    headers={"X-Farabi-WebUI-Key": self.valves.api_key},
                    json=govde,
                )
            return r.json() if r.status_code == 200 else None
        except Exception:  # noqa: BLE001 — istisna metni modele gitmesin
            return None

    @staticmethod
    def _satir(k: dict) -> str:
        son = f", son geçerlilik {k['son_gecerlilik']}" if k.get("son_gecerlilik") else ""
        return f"#{k['id']} [{k['tur']}{', sabit' if k.get('sabit') else ''}] {k['baslik']}: {k['icerik']} ({k['tarih']}{son})"

    async def hafizaya_kaydet(
        self,
        baslik: str,
        icerik: str,
        tur: str = "bilgi",
        kaynak: str = "",
        son_gecerlilik: str = "",
        sabit: bool = False,
        onaylandi: bool = False,
        __user__: dict | None = None,
    ) -> str:
        """
        Kalıcı okul hafızasına bilgi yazar ("hatırla", "kaydet", belge özeti). Önce onaylandi=False ile çağır, taslağı
        kullanıcıya göster; kullanıcı AÇIKÇA onaylayınca aynı alanlarla onaylandi=True çağır. Çıkarım/tahmin kaydetme.
        :param baslik: En çok 80 karakter.
        :param icerik: En çok 600 karakter; kısa, kesin bilgi.
        :param tur: bilgi | karar | tercih | belge.
        :param kaynak: Belge adı/yazı sayısı (isteğe bağlı).
        :param son_gecerlilik: YYYY-AA-GG; süresizse boş.
        :param sabit: True ise her mesajda hatırlatılan çekirdek not (çok az kullan).
        :param onaylandi: Kullanıcı onayı varsa True.
        """
        if not self._yonetici(__user__):
            return YONETICI_RET
        son = (son_gecerlilik or "").strip()
        if son and not TARIH.fullmatch(son):
            return "son_gecerlilik YYYY-AA-GG biçiminde olmalı; kaydedilmedi."
        y = await self._post("/kaydet", {
            "baslik": baslik, "icerik": icerik, "tur": tur, "kaynak": kaynak,
            "son_gecerlilik": son or None, "sabit": bool(sabit), "onaylandi": bool(onaylandi),
        })
        if not isinstance(y, dict):
            return ULASILAMADI + " KAYDEDİLMEDİ."
        d = y.get("durum")
        if d == "taslak":
            o = y["onizleme"]
            benzer = "; ".join(f"#{b['id']} {b['baslik']}" for b in y.get("benzer") or [])
            return (
                f"TASLAK (henüz KAYDEDİLMEDİ): [{o['tur']}] {o['baslik']}: {o['icerik']}"
                + (f" (son geçerlilik {o['son_gecerlilik']})" if o.get("son_gecerlilik") else "")
                + (f". Benzer kayıtlar: {benzer}" if benzer else "")
                + ". Taslağı kullanıcıya göster, açık onay iste; onay gelince onaylandi=True ile tekrar çağır."
            )
        if d == "kaydedildi":
            return f"Kaydedildi (#{y['id']})." + ("" if y.get("embedding") else " Not: anlamsal arama kapalıydı, tam-metin aramasıyla bulunur.")
        if d == "guncellendi":
            return f"Benzer kayıt vardı, güncellendi (#{y['id']})."
        if d == "dolu":
            return f"KAYDEDİLMEDİ: {y.get('neden', 'hafıza dolu')}"
        return "KAYDEDİLMEDİ: beklenmeyen sunucu yanıtı."

    async def hafizada_ara(self, sorgu: str = "", __user__: dict | None = None) -> str:
        """
        Hafızada arar; sorgu boşsa en yeni kayıtları listeler. "Ne biliyorsun?", "şunu hatırlıyor musun?" için.
        :param sorgu: Aranacak konu (boş = son kayıtlar).
        """
        if not self._yonetici(__user__):
            return YONETICI_RET
        y = await self._post("/ara", {"sorgu": sorgu or "", "limit": 8})
        if not isinstance(y, dict):
            return ULASILAMADI
        k = y.get("kayitlar") or []
        if not k:
            return "Hafızada eşleşen kayıt yok. Bilmediğin şeyi uydurma."
        return "Hafıza kayıtları (eski olabilir):\n" + "\n".join(self._satir(x) for x in k)

    async def hafizayi_unut(self, id: int, __user__: dict | None = None) -> str:
        """
        Bir hafıza kaydını arşivler ("bunu unut"). Önce hafizada_ara ile id'yi bul, kullanıcıya hangisi olduğunu doğrulat.
        :param id: Kayıt numarası.
        """
        if not self._yonetici(__user__):
            return YONETICI_RET
        y = await self._post("/unut", {"id": int(id)})
        if not isinstance(y, dict):
            return ULASILAMADI + " UNUTULMADI."
        return f"Unutuldu (#{y['id']})." if y.get("durum") == "unutuldu" else f"#{y.get('id')} bulunamadı; unutulmadı."
