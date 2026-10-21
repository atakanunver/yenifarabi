"""
title: Okul Bilgisi
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Sınıfların ders programını (şu anki ders, bugün, belirli gün, haftalık) ve — yalnızca İdare/Öğretmen hesaplarına — öğrenci bilgisini (ad soyad, numara, sınıf) ve öğretmen listesini (ad soyad, verdiği dersler, sınıflar) okulun yerel kayıtlarından getirir. 2026-10-16: öğretmenin anlık dersi, bugün okulda kimler var (yoklama), ve YALNIZCA yöneticiye öğrenci/veli telefonu.
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
YONETICI_RET = "Telefon ve doğum bilgisine yalnızca yönetici hesabı erişebilir."
OGRENCI_RET = (
    "Öğrenci bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
)


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1/api/okul"
        api_key: str = ""
        ogrenci_izinli: str = ""  # virgüllü e-posta listesi (kur.py yazar)
        sms_api_url: str = "http://127.0.0.1:8020/api/arac"  # öğrenci/veli telefon sorgusu (salt okunur)
        sms_api_key: str = ""
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
            + "\n(Kaynak: okul ders programı. Öğretmen adı için ogretmen_bilgisi aracını kullan.)"
        )

    async def ogrenci_bilgisi(
        self,
        sinif: str = "",
        ad: str = "",
        numara: str = "",
        iletisim: bool = False,
        dogum_yili: str = "",
        __user__: dict | None = None,
    ) -> str:
        """
        Öğrenci bilgisi: ad, okul no, sınıf ("Ayşe hangi sınıfta?", "11-A'da kimler var?", "123 numaralı kim?"). iletisim=True ise doğum tarihi ve öğrenci/veli telefonu da gelir (yalnızca yönetici; "Çağla'nın velisinin telefonu?", "2010 doğumlular?"). Aynı ada birden çok kişi çıkarsa hepsini göster; kayıtta olmayanı uydurma. Anne-baba ayrı/maddi/hastalık için ogrenci_ozel_durum.
        :param sinif: "11-A".
        :param ad: Ad ve/veya soyad.
        :param numara: Okul numarası.
        :param iletisim: True: telefon ve doğum tarihi de (yalnızca yönetici).
        :param dogum_yili: 4 haneli yıl (iletisim ile).
        """
        if iletisim or str(dogum_yili).strip():
            return await self._iletisim_metni(ad, sinif, dogum_yili, __user__)
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

    async def ogretmen_bilgisi(self, ad: str = "", __user__: dict | None = None) -> str:
        """
        Okulun öğretmen listesinden ad soyad, verdiği dersler ve girdiği sınıfları getirir.
        "Okulda hangi öğretmenler var?", "Fizik öğretmeni kim?", "Safiye Yılmaz hangi sınıflara giriyor?"
        gibi sorularda kullan; tahmin etme. Ad boşsa tüm liste gelir. Yalnızca İdare ve Öğretmen hesapları kullanabilir.
        :param ad: Öğretmenin adı ve/veya soyadı (isteğe bağlı).
        """
        if not self._ogrenci_izni(__user__):
            return "Öğretmen bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
        y = await self._get(__user__, "/ogretmen", {"ad": ad})
        if y is None:
            return ULASILAMADI
        if y.status_code == 403:
            return "Öğretmen bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
        v = self._json(y)
        if y.status_code != 200 or not isinstance(v, dict):
            return ULASILAMADI
        liste = v.get("ogretmenler") or []
        if not liste:
            return "Kayıtlarda eşleşen öğretmen bulunamadı. İsim uydurma; kullanıcıya bulunamadığını söyle."
        satirlar = [
            f"- {o.get('ad_soyad')} — dersler: {', '.join(o.get('dersler') or []) or '?'}; "
            f"sınıflar: {', '.join(o.get('siniflar') or []) or '?'}"
            for o in liste
        ]
        return (
            "Okul öğretmen listesi (kaynak: ders programı; dersler kısaltmadır, branş yazmaz):\n"
            + "\n".join(satirlar)
        )


    # --- 2026-10-16: Atos senaryoları ---------------------------------------

    @staticmethod
    def _yonetici(user) -> bool:
        return isinstance(user, dict) and user.get("role") == "admin"

    async def _sms_get(self, yol: str, params: dict):
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn) as c:
                return await c.get(
                    self.valves.sms_api_url.rstrip("/") + yol,
                    headers={"X-Sms-Arac-Key": self.valves.sms_api_key},
                    params=params,
                )
        except Exception:  # noqa: BLE001 — istisna metni LLM'e gitmemeli
            return None

    async def okulda_kimler_var(
        self, tarih: str = "", __user__: dict | None = None
    ) -> str:
        """
        "Bugün okulda kimler var?", "kimler devamsız?": sınıf sınıf yoklama (mevcut/yok/izinli) + şu an dersi olan öğretmenler.
        Yoklaması alınmamış sınıfı mevcut sayma. Öğretmen giriş-çıkış kaydı yok; yalnızca ders programına göre.
        :param tarih: YYYY-AA-GG; boşsa bugün.
        """
        if not self._ogrenci_izni(__user__):
            return OGRENCI_RET
        y = await self._get(__user__, "/okulda", {"tarih": tarih})
        if y is None:
            return ULASILAMADI
        if y.status_code == 403:
            return OGRENCI_RET
        v = self._json(y)
        if y.status_code != 200 or not isinstance(v, dict):
            return ULASILAMADI
        satirlar = [f"{v.get('simdi')}", f"Tarih: {v.get('tarih')}", "Öğrenci yoklaması:"]
        for s in v.get("siniflar") or []:
            if s.get("yoklama") != "alindi":
                satirlar.append(f"- {s['sinif']}: yoklama alınmadı ({s['toplam']} öğrenci kayıtlı)")
                continue
            ek = f"; izinli: {', '.join(s['izinli'])}" if s.get("izinli") else ""
            yok = f"; yok: {', '.join(s['yok'])}" if s.get("yok") else "; devamsız yok"
            satirlar.append(
                f"- {s['sinif']}: {s['mevcut']}/{s['toplam']} mevcut ({s['ders_no']}. ders yoklaması){yok}{ek}"
            )
        ogr = v.get("dersi_olan_ogretmenler") or []
        satirlar.append(
            "Şu an dersi olan öğretmenler: "
            + (", ".join(f"{o['ad_soyad']} ({o['sinif']})" for o in ogr) if ogr else "yok (ders saati dışı olabilir)")
        )
        satirlar.append(f"({v.get('not', '')})")
        return "\n".join(satirlar)

    async def ogretmen_simdi(self, ad: str, __user__: dict | None = None) -> str:
        """
        "Ayşe öğretmenin şu an dersi var mı?", "Sedat hoca bugün hangi sınıflara giriyor?" sorularında kullan.
        Aynı ada sahip birden çok öğretmen olabilir: HEPSİNİ listele, birini seçme; gerekirse kullanıcıya hangisi olduğunu sor.
        :param ad: Öğretmenin adı ve/veya soyadı.
        """
        if not self._ogrenci_izni(__user__):
            return "Öğretmen bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
        y = await self._get(__user__, "/ogretmen-simdi", {"ad": ad})
        if y is None:
            return ULASILAMADI
        if y.status_code == 403:
            return "Öğretmen bilgisine bu hesapla erişilemez (yalnızca İdare ve Öğretmen hesapları)."
        v = self._json(y)
        if y.status_code != 200 or not isinstance(v, dict):
            return ULASILAMADI
        liste = v.get("ogretmenler") or []
        if not liste:
            return "Kayıtlarda eşleşen öğretmen bulunamadı. İsim uydurma; kullanıcıya bulunamadığını söyle."
        satirlar = [v.get("simdi", "")]
        for o in liste:
            s = o.get("simdi_ders")
            durum = f"ŞU AN {s['no']}. derste {s['sinif']} sınıfında" if s else "şu an dersi yok"
            bugun = ", ".join(f"{d['no']}. ders {d['baslangic']}–{d['bitis']} {d['sinif']}" for d in o.get("bugun") or [])
            satirlar.append(
                f"- {o['ad_soyad']} ({', '.join(o.get('dersler') or []) or '?'}): {durum}. "
                f"Bugünkü dersleri: {bugun or 'yok'}"
            )
        return "\n".join(satirlar)

    @staticmethod
    def _tarih(d: str) -> str:
        p = (d or "").split("-")
        return f"{p[2]}.{p[1]}.{p[0]}" if len(p) == 3 else (d or "—")

    async def _iletisim(self, ad: str, sinif: str, dogum_yili: str, limit: int):
        y = await self._sms_get(
            "/ogrenci-iletisim",
            {"ad": ad, "sinif": sinif, "dogum_yili": dogum_yili, "limit": limit},
        )
        if y is None:
            return None, ULASILAMADI
        v = self._json(y)
        if y.status_code == 400:
            return None, "Arama için ad, sınıf ya da doğum yılı (4 haneli) verin."
        if y.status_code != 200 or not isinstance(v, dict):
            return None, ULASILAMADI
        return v, ""

    async def _iletisim_metni(self, ad: str, sinif: str, dogum_yili: str, __user__: dict | None) -> str:
        if not self._yonetici(__user__):
            return YONETICI_RET
        v, hata = await self._iletisim(ad, sinif, dogum_yili, 60)
        if v is None:
            return hata
        liste = v.get("ogrenciler") or []
        if not liste:
            return "Kayıtlarda eşleşen öğrenci bulunamadı. İsim ya da numara uydurma."
        satirlar = []
        for o in liste:
            veliler = "; ".join(f"{x['rol']} {x['ad_soyad']}: {x['telefon'] or 'kayıtlı değil'}" for x in o["veliler"]) or "veli kaydı yok"
            satirlar.append(
                f"- {o['ad_soyad']} — {o['sinif']}, no {o['okul_no']}, doğum {self._tarih(o['dogum_tarihi'])}; "
                f"öğrenci tel: {o['ogrenci_telefon'] or 'kayıtlı değil'}; veliler: {veliler}"
            )
        ek = f"\n(Toplam {v['toplam']}, ilk {len(liste)} gösterildi.)" if v["toplam"] > len(liste) else ""
        return "Okul rehberi kayıtları:\n" + "\n".join(satirlar) + ek
