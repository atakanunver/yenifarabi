"""
title: SMS ve Hatırlatma
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Okul yönetimine zamanlı SMS hatırlatması ve acil SMS; sınıf velilerine (taslak + onay ile) SMS. Yalnızca İdare.
"""

# Bu dosya Open WebUI'ye (Atos) `openwebui/kur.py` ile Tool olarak yüklenir; Open
# WebUI içinde elle düzenlenmez. SMS sisteminin /api/arac/* ucunu çağırır
# (smssistemi/arac_api.py). Hatırlatma ve acil SMS her zaman okul yönetimine
# (Atakan Ünver, Arzu Oral) gider; hatırlatma onaysız kurulur. Veli SMS'i önce
# taslak, kullanıcı açıkça onaylarsa gönderim (2026-10-05 kullanıcı kararları).

from datetime import datetime

import httpx
from pydantic import BaseModel

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _gunlu(zaman: str) -> str:
    """"2026-10-14 10:00" → "14.10.2026 Çarşamba 10:00" (model günü kendisi hesaplamasın)."""
    try:
        an = datetime.strptime(zaman, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(zaman)
    return f"{an:%d.%m.%Y} {GUNLER[an.weekday()]} {an:%H:%M}"


ULASILAMADI = "SMS sistemine ulaşılamadı — işlem YAPILMADI. Kullanıcıya SMS gönderilmediğini söyle."


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8020/api/arac"
        api_key: str = ""
        zaman_asimi_sn: float = 20.0

    def __init__(self):
        self.valves = self.Valves()

    async def _istek(self, yontem: str, yol: str, govde: dict | None = None):
        async with httpx.AsyncClient(
            timeout=self.valves.zaman_asimi_sn, trust_env=False
        ) as c:
            r = await c.request(
                yontem,
                f"{self.valves.api_url}{yol}",
                json=govde,
                headers={"X-Sms-Arac-Key": self.valves.api_key},
            )
        try:
            veri = r.json()
        except ValueError:
            veri = {}
        return r.status_code, veri

    @staticmethod
    def _hata(kod: int, veri: dict) -> str:
        return f"İşlem YAPILMADI ({kod}): {veri.get('detail') or 'bilinmeyen hata'}"

    async def sms_hatirlatma_kur(self, metin: str, tarih: str, saat: str = "") -> str:
        """
        Yönetime (Atakan Ünver, Arzu Oral) belirtilen gün/saatte SMS hatırlatması zamanlar. "Hatırlat" denince ONAY SORMADAN çağır. Örn. "15 Ekim kermes, 14 Ekim'de hatırlat" → tarih 14 Ekim; "sabahında hatırlat" → saat boş.
        :param metin: Not, en çok 120 karakter.
        :param tarih: YYYY-MM-DD; yıl yoksa bugünden sonraki ilk tarih.
        :param saat: HH:MM; söylenmediyse BOŞ (varsayılan 10:00).
        """
        try:
            kod, y = await self._istek(
                "POST",
                "/hatirlatma",
                {"metin": metin, "tarih": tarih, "saat": saat or None},
            )
        except httpx.HTTPError:
            return ULASILAMADI
        if kod != 200:
            return self._hata(kod, y)
        return (
            f"Hatırlatma kuruldu (#{y['id']}): {_gunlu(y['zaman'])} — alıcılar: {', '.join(y['alicilar'])}. "
            f'Mesaj: "{y["metin"]}"'
        )

    async def acil_sms_gonder(self, metin: str) -> str:
        """
        Okul yönetimine (Atakan Ünver ve Arzu Oral) HEMEN SMS gönderir. Kullanıcı acil durum bildirmek ya da yönetime şimdi SMS atmak istediğinde çağır.
        :param metin: SMS metni; kısa ve açık.
        """
        try:
            kod, y = await self._istek("POST", "/acil", {"metin": metin})
        except httpx.HTTPError:
            return ULASILAMADI
        if kod != 200:
            return self._hata(kod, y)
        return (
            f'SMS gönderime alındı: {", ".join(y["alicilar"])}. Mesaj: "{y["metin"]}"'
        )

    async def _taslak_hazirla(self, yol: str, govde: dict, kime: str) -> str:
        try:
            kod, y = await self._istek("POST", yol, govde)
        except httpx.HTTPError:
            return ULASILAMADI
        if kod != 200:
            return self._hata(kod, y)
        tum = y.get("sinif") == "TÜM OKUL"
        hedef = "tüm okul" if tum else y["sinif"]
        ek = (
            f" ÖNEMLİ: bu TÜM OKUL gönderimi. Göndermeden önce kullanıcıdan alıcı sayısını ({y['alici_sayisi']}) kendisinin "
            f"yazmasını iste; yazdığı sayıyı gönder fonksiyonuna alici_sayisi olarak ver (sayıyı sen uydurma)."
            if tum
            else ""
        )
        return (
            f"TASLAK hazır (henüz GÖNDERİLMEDİ). Taslak no: {y['taslak_id']} — {hedef} {kime}, "
            f'{y["alici_sayisi"]} alıcı. Mesaj: "{y["metin"]}". Kullanıcıya bunu göster ve '
            f"gönderilsin mi diye sor; {y['gecerlilik_dk']} dk içinde açık onay verirse gönder fonksiyonunu çağır.{ek}"
        )

    async def _taslak_gonder(self, yol: str, taslak_id: str, alici_sayisi: int, kime: str) -> str:
        govde = {"taslak_id": taslak_id}
        if alici_sayisi:
            govde["alici_sayisi"] = alici_sayisi
        try:
            kod, y = await self._istek("POST", yol, govde)
        except httpx.HTTPError:
            return ULASILAMADI
        if kod != 200:
            return self._hata(kod, y)
        hedef = "tüm okul" if y["sinif"] == "TÜM OKUL" else y["sinif"]
        return f"{hedef} {kime} SMS gönderime alındı ({y['alici_sayisi']} alıcı)."

    async def veli_sms_taslak(self, sinif: str, metin: str) -> str:
        """
        Bir sınıfın (ya da tüm okulun) velilerine gidecek SMS için TASLAK hazırlar, göndermez. "9-A velilerine SMS at" denince ÖNCE bunu çağır, taslağı göster, açık onay iste.
        :param sinif: "9-A" ("10a" de olur) ya da tüm okul için "TÜM".
        :param metin: Mesaj, en çok 300 karakter.
        """
        return await self._taslak_hazirla("/veli-taslak", {"sinif": sinif, "metin": metin}, "velileri")

    async def veli_sms_gonder(self, taslak_id: str, alici_sayisi: int = 0) -> str:
        """
        Daha önce hazırlanmış veli SMS taslağını gönderir. YALNIZCA kullanıcı taslağı gördükten sonra açıkça onay verdiyse ("evet", "gönder", "onaylıyorum") çağır.
        :param taslak_id: veli_sms_taslak'ın döndürdüğü taslak numarası.
        :param alici_sayisi: Yalnızca TÜM OKUL taslağında: kullanıcının kendi yazdığı alıcı sayısı. Diğerlerinde verme.
        """
        return await self._taslak_gonder("/veli-gonder", taslak_id, alici_sayisi, "velilerine")

    async def ogrenci_sms_taslak(self, sinif: str, metin: str) -> str:
        """
        Bir sınıfın (ya da tüm okulun) ÖĞRENCİLERİNE gidecek SMS için TASLAK hazırlar, göndermez. "11b öğrencilerine SMS" denince ÖNCE bunu çağır, taslağı göster, açık onay iste.
        :param sinif: "11-B" ("11b" de olur) ya da "TÜM".
        :param metin: Mesaj, en çok 300 karakter.
        """
        return await self._taslak_hazirla("/ogrenci-taslak", {"sinif": sinif, "metin": metin}, "öğrencileri")

    async def ogrenci_sms_gonder(self, taslak_id: str, alici_sayisi: int = 0) -> str:
        """
        Daha önce hazırlanmış öğrenci SMS taslağını gönderir. YALNIZCA kullanıcı taslağı gördükten sonra açıkça onay verdiyse çağır.
        :param taslak_id: ogrenci_sms_taslak'ın döndürdüğü taslak numarası.
        :param alici_sayisi: Yalnızca TÜM OKUL taslağında: kullanıcının kendi yazdığı alıcı sayısı. Diğerlerinde verme.
        """
        return await self._taslak_gonder("/ogrenci-gonder", taslak_id, alici_sayisi, "öğrencilerine")
