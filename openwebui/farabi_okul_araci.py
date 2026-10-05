"""
title: Okul Bilgisi
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Sınıfların ders programını (şu anki ders, bugün, belirli gün, haftalık) ve — yalnızca İdare/Öğretmen hesaplarına — öğrenci bilgisini (ad soyad, numara, sınıf) okulun yerel kayıtlarından getirir.
"""

# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Tool olarak yüklenir; Open WebUI
# içinde elle düzenlenmez. Dashboard'un yerel /api/okul/* JSON API'sini çağırır
# (tahtayoklama/dashboard/okul_bilgisi.py). Çıktıya istisna metni, IP ya da
# anahtar ASLA konmaz. Öğrenci verisi yerel Ollama'dan başka yere gitmez.
# Öğrenci erişimi (2026-10-04 kullanıcı kararı): admin + Valves.ogrenci_izinli
# e-postaları (İdare, Öğretmen); tahta hesabı HARİÇ. Sunucu aynı kontrolü yapar.

import httpx
from pydantic import BaseModel

ULASILAMADI = "Okul bilgisi servisine ulaşılamadı."
OGRENCI_RET = (
    "Öğrenci bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
)


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8010/api/okul"
        api_key: str = ""
        ogrenci_izinli: str = ""  # virgüllü e-posta listesi (kur.py yazar)
        zaman_asimi_sn: float = 15.0

    def __init__(self):
        self.valves = self.Valves()

    def _ogrenci_izni(self, user) -> bool:
        if not isinstance(user, dict) or not user.get("email"):
            return False
        if user.get("role") == "admin":
            return True
        izinli = {
            e.strip().lower()
            for e in self.valves.ogrenci_izinli.split(",")
            if e.strip()
        }
        return str(user["email"]).strip().lower() in izinli

    async def _get(self, user, yol: str, params: dict):
        user = user if isinstance(user, dict) else {}
        basliklar = {
            "X-Farabi-Okul-Key": self.valves.api_key,
            "X-Farabi-Kullanici": str(user.get("email", "")),
            "X-Farabi-Rol": str(user.get("role", "")),
        }
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn) as c:
                return await c.get(
                    self.valves.api_url.rstrip("/") + yol,
                    headers=basliklar,
                    params=params,
                )
        except Exception:  # noqa: BLE001 — istisna metni LLM'e gitmemeli
            return None

    @staticmethod
    def _json(yanit):
        try:
            return yanit.json()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _satir(d: dict) -> str:
        isaret = " (şu an)" if d.get("simdi") else ""
        return f"- {d.get('no')}. ders {d.get('baslangic')}–{d.get('bitis')}: {d.get('ders')}{isaret}"

    async def ders_programi(
        self, sinif: str, gun: str = "bugun", __user__: dict | None = None
    ) -> str:
        """
        Bir sınıfın ders programını okulun kayıtlarından getirir. "11-A'nın şu an hangi dersi var?",
        "9-B'nin bugünkü dersleri", "10-A çarşamba programı" gibi sorularda kullan; tahmin etme.
        :param sinif: Sınıf ve şube, örn. "11-A".
        :param gun: "simdi" (o anki ders), "bugun", "hafta" ya da gün adı (Pazartesi..Cuma).
        """
        y = await self._get(__user__, "/ders-programi", {"sinif": sinif, "gun": gun})
        if y is None:
            return ULASILAMADI
        v = self._json(y)
        if y.status_code == 404:
            gecerli = (
                ((v or {}).get("detail") or {}).get("gecerli")
                if isinstance(v, dict)
                else None
            )
            ek = (
                f" Geçerli sınıflar: {', '.join(gecerli)}."
                if isinstance(gecerli, list)
                else ""
            )
            return f"{sinif} sınıfı ders programında bulunamadı.{ek}"
        if y.status_code == 400:
            return "Gün anlaşılamadı: simdi, bugun, hafta ya da Pazartesi–Cuma yazın."
        if y.status_code != 200 or not isinstance(v, dict):
            return ULASILAMADI
        bas = v.get("simdi") or ""
        if "hafta" in v:
            satirlar = [f"{v.get('sinif')} haftalık ders programı:"]
            for gun_adi, dersler in (v.get("hafta") or {}).items():
                satirlar.append(f"{gun_adi}:")
                satirlar += [self._satir(d) for d in dersler]
            return bas + "\n" + "\n".join(satirlar)
        dersler = v.get("dersler") or []
        if not dersler:
            return f"{bas}\n{v.get('sinif')} için {v.get('gun', '')} bu zaman aralığında ders yok."
        satirlar = [f"{v.get('sinif')} — {v.get('gun')}:"] + [
            self._satir(d) for d in dersler
        ]
        return (
            bas
            + "\n"
            + "\n".join(satirlar)
            + "\n(Kaynak: okul ders programı. Öğretmen adı kayıtlı değil.)"
        )

    async def ogrenci_bilgisi(
        self,
        sinif: str = "",
        ad: str = "",
        numara: str = "",
        __user__: dict | None = None,
    ) -> str:
        """
        Okulun sınıf listelerinden öğrenci bilgisi (ad soyad, okul numarası, sınıf) getirir.
        "Ayşe Yılmaz hangi sınıfta?", "11-A'da kimler var?", "123 numaralı öğrenci kim?" gibi
        sorularda kullan. Yalnızca İdare ve Öğretmen hesapları kullanabilir.
        :param sinif: Sınıf ve şube, örn. "11-A" (isteğe bağlı).
        :param ad: Öğrencinin adı ve/veya soyadı (isteğe bağlı).
        :param numara: Okul numarası (isteğe bağlı).
        """
        if not self._ogrenci_izni(__user__):
            return OGRENCI_RET
        if not (str(sinif).strip() or str(ad).strip() or str(numara).strip()):
            return "Aramak için sınıf, ad ya da numara verin."
        y = await self._get(
            __user__, "/ogrenci", {"sinif": sinif, "ad": ad, "no": numara}
        )
        if y is None:
            return ULASILAMADI
        if y.status_code == 403:
            return OGRENCI_RET
        v = self._json(y)
        if y.status_code != 200 or not isinstance(v, dict):
            return ULASILAMADI
        liste = v.get("ogrenciler") or []
        if not liste:
            return "Kayıtlarda eşleşen öğrenci bulunamadı. Başka isim uydurma; kullanıcıya bulunamadığını söyle."
        satirlar = [
            f"- {o.get('ad_soyad')} — no {o.get('no')}, {o.get('sinif')}" for o in liste
        ]
        ek = (
            f"\n(Toplam {v.get('toplam')}, ilk {len(liste)} gösterildi.)"
            if v.get("toplam", 0) > len(liste)
            else ""
        )
        return "Okul kayıtlarındaki öğrenciler:\n" + "\n".join(satirlar) + ek
