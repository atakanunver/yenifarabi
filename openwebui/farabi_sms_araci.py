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
        Okul yönetimine (Atakan Ünver ve Arzu Oral) belirtilen gün ve saatte SMS ile hatırlatma gönderilmesini zamanlar. Kullanıcı "hatırlat", "hatırlatma kur", "bana SMS ile hatırlat" dediğinde ONAY SORMADAN çağır. Örnek: "15 Ekim'de kermes var, 14 Ekim'de hatırlat" → tarih 14 Ekim; "17 Ekim'de toplantı var, sabahında hatırlat" → tarih 17 Ekim, saat boş.
        :param metin: Hatırlatma notu; en fazla 120 karakter, kısa ve açık (ör. "Hatırlatma: 15 Ekim Çarşamba okul kermesi var.").
        :param tarih: Hatırlatmanın gönderileceği gün, YYYY-MM-DD biçiminde. Yıl söylenmediyse sistem mesajındaki bugünün tarihine göre gelecekteki ilk tarihi kullan.
        :param saat: Gönderim saati HH:MM (24 saat). Kullanıcı saat söylemediyse BOŞ bırak; varsayılan 10:00.
        :return: Kurulan hatırlatmanın zamanı ve alıcıları ya da hata.
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

    async def sms_hatirlatmalari_listele(self) -> str:
        """
        Bekleyen (henüz gönderilmemiş) SMS hatırlatmalarını listeler. "Hangi hatırlatmalar var", "hatırlatmalarım" dendiğinde çağır.
        :return: Bekleyen hatırlatmaların listesi.
        """
        try:
            kod, y = await self._istek("GET", "/hatirlatmalar")
        except httpx.HTTPError:
            return ULASILAMADI
        if kod != 200:
            return self._hata(kod, y)
        liste = y.get("hatirlatmalar") or []
        if not liste:
            return "Bekleyen hatırlatma yok."
        return "Bekleyen hatırlatmalar:\n" + "\n".join(
            f"- #{h['id']} {_gunlu(h['zaman'])}: {h['metin']}" for h in liste
        )

    async def sms_hatirlatma_iptal(self, hatirlatma_id: int) -> str:
        """
        Bekleyen bir SMS hatırlatmasını iptal eder. Numarayı bilmiyorsan önce sms_hatirlatmalari_listele çağır.
        :param hatirlatma_id: İptal edilecek hatırlatmanın numarası (#).
        :return: İptal sonucu.
        """
        try:
            kod, y = await self._istek(
                "POST", f"/hatirlatma/{int(hatirlatma_id)}/iptal", {}
            )
        except httpx.HTTPError:
            return ULASILAMADI
        return (
            f"Hatırlatma #{hatirlatma_id} iptal edildi."
            if kod == 200
            else self._hata(kod, y)
        )

    async def acil_sms_gonder(self, metin: str) -> str:
        """
        Okul yönetimine (Atakan Ünver ve Arzu Oral) HEMEN SMS gönderir. Kullanıcı acil durum bildirmek ya da yönetime şimdi SMS atmak istediğinde çağır.
        :param metin: SMS metni; kısa ve açık.
        :return: Gönderim sonucu.
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
        Bir sınıfın velilerine (ya da TÜM okulun velilerine) gidecek SMS için TASLAK hazırlar (henüz göndermez). Kullanıcı "9-A velilerine SMS at", "10a velilerine kermesi bildir", "tüm velilere SMS gönder" dediğinde ÖNCE bunu çağır, sonucu kullanıcıya göster ve açıkça onay iste.
        :param sinif: Sınıf adı, ör. "9-A" ("10a", "11 b" de olur); okuldaki tüm veliler için "TÜM".
        :param metin: Velilere gidecek mesaj; en fazla 300 karakter, nazik ve açık.
        :return: Taslak numarası, alıcı sayısı ve mesaj önizlemesi.
        """
        return await self._taslak_hazirla("/veli-taslak", {"sinif": sinif, "metin": metin}, "velileri")

    async def veli_sms_gonder(self, taslak_id: str, alici_sayisi: int = 0) -> str:
        """
        Daha önce hazırlanmış veli SMS taslağını gönderir. YALNIZCA kullanıcı taslağı gördükten sonra açıkça onay verdiyse ("evet", "gönder", "onaylıyorum") çağır.
        :param taslak_id: veli_sms_taslak'ın döndürdüğü taslak numarası.
        :param alici_sayisi: Yalnızca TÜM OKUL taslağında: kullanıcının kendi yazdığı alıcı sayısı. Diğerlerinde verme.
        :return: Gönderim sonucu.
        """
        return await self._taslak_gonder("/veli-gonder", taslak_id, alici_sayisi, "velilerine")

    async def ogrenci_sms_taslak(self, sinif: str, metin: str) -> str:
        """
        Bir sınıfın ÖĞRENCİLERİNE (ya da tüm okulun öğrencilerine) gidecek SMS için TASLAK hazırlar (henüz göndermez). Kullanıcı "11b öğrencilerine SMS gönder", "tüm öğrencilere duyur" dediğinde ÖNCE bunu çağır, sonucu göster ve açıkça onay iste.
        :param sinif: Sınıf adı, ör. "11-B" ("11b" de olur); tüm öğrenciler için "TÜM".
        :param metin: Öğrencilere gidecek mesaj; en fazla 300 karakter.
        :return: Taslak numarası, alıcı sayısı ve mesaj önizlemesi.
        """
        return await self._taslak_hazirla("/ogrenci-taslak", {"sinif": sinif, "metin": metin}, "öğrencileri")

    async def ogrenci_sms_gonder(self, taslak_id: str, alici_sayisi: int = 0) -> str:
        """
        Daha önce hazırlanmış öğrenci SMS taslağını gönderir. YALNIZCA kullanıcı taslağı gördükten sonra açıkça onay verdiyse çağır.
        :param taslak_id: ogrenci_sms_taslak'ın döndürdüğü taslak numarası.
        :param alici_sayisi: Yalnızca TÜM OKUL taslağında: kullanıcının kendi yazdığı alıcı sayısı. Diğerlerinde verme.
        :return: Gönderim sonucu.
        """
        return await self._taslak_gonder("/ogrenci-gonder", taslak_id, alici_sayisi, "öğrencilerine")

    async def personel_sms_taslak(self, metin: str) -> str:
        """
        Okulun öğretmenlerine/personeline (rehberdeki "Personel" kayıtları) gidecek SMS için TASLAK hazırlar (henüz göndermez). Kullanıcı "öğretmenlere SMS gönder" dediğinde ÖNCE bunu çağır, sonucu göster ve açıkça onay iste.
        :param metin: Öğretmenlere gidecek mesaj; en fazla 300 karakter.
        :return: Taslak numarası, alıcı sayısı ve mesaj önizlemesi.
        """
        return await self._taslak_hazirla("/personel-taslak", {"metin": metin}, "personeli")

    async def personel_sms_gonder(self, taslak_id: str) -> str:
        """
        Daha önce hazırlanmış personel/öğretmen SMS taslağını gönderir. YALNIZCA kullanıcı taslağı gördükten sonra açıkça onay verdiyse çağır.
        :param taslak_id: personel_sms_taslak'ın döndürdüğü taslak numarası.
        :return: Gönderim sonucu.
        """
        return await self._taslak_gonder("/personel-gonder", taslak_id, 0, "personeline")
