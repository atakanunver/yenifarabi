"""
title: Farabi Yönetim
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: YALNIZCA YÖNETİCİ. Akıllı tahtaların durumunu sorgular, uzaktan eylem (yoklama, web sayfası, ekran karartma, Chrome kapatma) ve yeniden başlatma yapar; değiştiren her işlem onay penceresinden geçer.
"""

# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Tool olarak yüklenir; Open WebUI
# içinde elle düzenlenmez. Dashboard'un yerel /api/ajan/* JSON API'sini çağırır.
# Çıktıya ham yanıt gövdesi, istisna metni, IP ya da anahtar ASLA konmaz.

import re
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

HEPSI = {"hepsi", "tümü", "tumu", "tum", "all"}
EYLEM_ADLARI = {
    "yoklama_ac": "Yoklamayı aç",
    "yoklama_kapat": "Yoklamayı kapat",
    "web_ac": "Web sayfası aç",
    "chrome_kapat": "Chrome'u kapat",
    "ekran_karart": "Ekranı karart",
    "ekran_kaldir": "Ekran karartmayı kaldır",
}
SEBEPLER = {
    "tamam": "tamam",
    "ulasilamadi": "ulaşılamadı",
    "zaman_asimi": "zaman aşımı",
    "oturum_yok": "masaüstü oturumu yok",
    "izin_yok": "izin yok",
    "hata": "hata",
    "bekleme": "bekleme süresi dolmadı, biraz sonra tekrar deneyin",
}
RET_ROL = "Bu araç yalnızca yönetici içindir."
ERISIM_YOK = "Yönetim API'sine erişilemedi (anahtar/yapılandırma)."
AG_HATASI = "Yönetim API'sine ulaşılamadı (ağ hatası ya da zaman aşımı)."


def _anahtar(ad: str) -> str:
    return re.sub(r"[\s/\-_]", "", str(ad)).lower()


def tahtalari_coz(istenen: list[str], kayit: list[str]) -> tuple[list[str], list[str]]:
    """İstenen adları kayıttaki yazıma çevirir. (çözülenler, bilinmeyenler) döner.
    'hepsi'/'tümü'/'tum'/'all' kayıttaki tüm adlara açılır; çıktı sırası kayıt sırasıdır."""
    if any(str(a).strip().lower() in HEPSI for a in istenen):
        return list(kayit), []
    harita = {_anahtar(k): k for k in kayit}
    secili, bilinmeyen = set(), []
    for a in istenen:
        k = harita.get(_anahtar(a))
        if k is None:
            bilinmeyen.append(str(a))
        else:
            secili.add(k)
    return [k for k in kayit if k in secili], bilinmeyen


POST_BELIRSIZ = ("Sonuç alınamadı; işlem yapılmış olabilir. "
                 "Tekrar denemeden önce `tahta_durumu` ile kontrol edin.")

URL_MAKS = 2000
_URL_YASAK = re.compile(r"[\s\x00-\x1f\x7f\[\]()<>`]")


def url_gecerli_mi(url) -> bool:
    """http(s) mutlak adres; boşluk/kontrol karakteri ve Markdown/HTML'de anlamlı [ ] ( ) < > ` yok
    (onay penceresi mesajı Markdown olarak işlenir). Bu karakterler gerekiyorsa %-kodlanmalıdır."""
    # ASCII dışı yok: bidi/sıfır genişlik/C1 karakterleri onay penceresinde yanıltıcı görünebilir;
    # IDN alan adları punycode (xn--) ile yazılmalı.
    if (not isinstance(url, str) or not url or len(url) > URL_MAKS or not url.isascii()
            or _URL_YASAK.search(url)):
        return False
    try:
        parca = urlsplit(url)
    except ValueError:
        return False
    return parca.scheme in ("http", "https") and bool(parca.netloc)


def _kod(metin: str) -> str:
    """Markdown satır içi kod aralığı (ters tırnaklar atılır)."""
    return "`" + str(metin).replace("`", "") + "`"


def _yonetici_mi(user) -> bool:
    return isinstance(user, dict) and user.get("role") == "admin"


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8010/api/ajan"
        api_key: str = ""
        zaman_asimi_sn: float = 60.0

    def __init__(self):
        self.valves = self.Valves()

    # ---- yardımcılar -------------------------------------------------

    def _basliklar(self, user: dict) -> dict:
        return {"X-Farabi-Ajan-Key": self.valves.api_key,
                "X-Farabi-Kaynak": f"openwebui:{user.get('email', '')}"}

    async def _durum(self, emitter, metin: str, bitti: bool) -> None:
        if emitter:
            await emitter({"type": "status", "data": {"description": metin, "done": bitti}})

    async def _istek(self, user: dict, yontem: str, yol: str, **kw):
        """(yanıt | None) döner; ağ hatasında None (istisna metni dışarı çıkmaz)."""
        url = self.valves.api_url.rstrip("/") + yol
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn) as c:
                if yontem == "GET":
                    return await c.get(url, headers=self._basliklar(user), **kw)
                return await c.post(url, headers=self._basliklar(user), **kw)
        except Exception:  # noqa: BLE001 — hiçbir istisna metni LLM'e gitmemeli
            return None

    @staticmethod
    def _json(yanit):
        try:
            return yanit.json()
        except Exception:  # noqa: BLE001
            return None

    async def _kayit(self, user: dict) -> list[str] | None:
        y = await self._istek(user, "GET", "/tahtalar", params={"canli": 0})
        if y is None or y.status_code != 200:
            return None
        v = self._json(y)
        try:
            return [t["ad"] for t in v["tahtalar"]]
        except (TypeError, KeyError):
            return None

    async def _oku(self, user, yol, **kw):
        """Okuma uçları için: (veri, hata_metni)."""
        y = await self._istek(user, "GET", yol, **kw)
        if y is None:
            return None, AG_HATASI
        if y.status_code == 400:
            return None, "İstek geçersiz (tarih YYYY-MM-DD, sınıf adı geçerli olmalı)."
        if y.status_code != 200:
            return None, ERISIM_YOK
        v = self._json(y)
        if v is None:
            return None, AG_HATASI
        return v, None

    @staticmethod
    def _sonuc_metni(sonuclar) -> str:
        satirlar = []
        for s in sonuclar or []:
            ad = s.get("tahta", "?")
            if s.get("basarili"):
                satir = f"✓ {ad}"
                if s.get("uyari"):
                    satir += f" ({s['uyari']})"
            else:
                satir = f"✗ {ad} ({SEBEPLER.get(s.get('sebep'), 'hata')})"
            satirlar.append(satir)
        return "\n".join(satirlar) or "Sonuç dönmedi."

    def _yanit_yorumla(self, y) -> str:
        """Onaydan SONRA yapılan POST yanıtı: ağ hatası/bozuk gövde = sonuç belirsiz (işlem yapılmış olabilir)."""
        if y is None:
            return POST_BELIRSIZ
        if y.status_code == 200:
            v = self._json(y)
            if isinstance(v, dict):
                return self._sonuc_metni(v.get("sonuclar"))
            return POST_BELIRSIZ
        if y.status_code == 409:
            return "Şu an okul saati; yeniden başlatma reddedildi."
        if y.status_code == 400:
            v = self._json(y)
            d = v.get("detail") if isinstance(v, dict) else None
            if isinstance(d, dict) and isinstance(d.get("bilinmeyen"), list):
                return "Sunucu şu tahta adlarını tanımadı: " + ", ".join(str(a) for a in d["bilinmeyen"])
            return "İstek sunucu tarafından geçersiz bulundu."
        if y.status_code in (401, 403, 503):
            return ERISIM_YOK
        return "Yönetim API'si beklenmeyen bir yanıt verdi."

    async def _onayli(self, user, emitter, event_call, *, baslik, ozet, mesaj, yol, govde) -> str:
        if event_call is None:
            return "İşlem yapılmadı: onay penceresi yok (bu sohbet onay isteğini göstermiyor)."
        onay = await event_call({"type": "confirmation", "data": {"title": baslik, "message": mesaj}})
        if onay is not True:
            return "İptal edildi."
        await self._durum(emitter, ozet, False)
        y = await self._istek(user, "POST", yol, json=govde)
        metin = self._yanit_yorumla(y)
        await self._durum(emitter, ozet, True)
        return metin

    async def _hedefler(self, user, tahtalar) -> tuple[list[str] | None, str | None]:
        if not isinstance(tahtalar, list) or not tahtalar:
            return None, "Tahta listesi boş. Hangi tahta(lar)? Örn. 9-A, fenlab ya da hepsi."
        kayit = await self._kayit(user)
        if kayit is None:
            return None, "Tahta listesi alınamadı; " + ERISIM_YOK
        secili, bilinmeyen = tahtalari_coz(tahtalar, kayit)
        if bilinmeyen:
            return None, ("Bilinmeyen tahta adı: " + ", ".join(bilinmeyen)
                          + ". Geçerli tahtalar: " + ", ".join(kayit) + ". Hiçbir işlem yapılmadı.")
        return secili, None

    # ---- okuma araçları ---------------------------------------------

    async def tahta_durumu(self, __user__: dict | None = None, __event_emitter__=None) -> str:
        """
        Tüm akıllı tahtaların anlık durumunu listeler (açık/kapalı, masaüstü oturumu, yoklama, Chrome, ekran karartma).
        Yalnızca yöneticiler kullanabilir.
        """
        if not _yonetici_mi(__user__):
            return RET_ROL
        await self._durum(__event_emitter__, "Tahtalar sorgulanıyor...", False)
        v, hata = await self._oku(__user__, "/tahtalar", params={"canli": 1})
        await self._durum(__event_emitter__, "Tahtalar sorgulandı.", True)
        if hata:
            return hata
        satirlar = []
        for t in (v.get("tahtalar") or []) if isinstance(v, dict) else []:
            if not t.get("ulasilabilir"):
                satirlar.append(f"{t.get('ad')}: kapalı/ulaşılamıyor")
                continue
            satirlar.append(
                f"{t.get('ad')}: açık, oturum {'var' if t.get('oturum') else 'yok'}, "
                f"yoklama {'açık' if t.get('yoklama') else 'kapalı'}, "
                f"chrome {'açık' if t.get('chrome') else 'kapalı'}"
                + (", ekran karartılmış" if t.get("karartildi") else ""))
        return "\n".join(satirlar) or "Kayıtlı tahta yok."

    async def sunucu_durumu(self, __user__: dict | None = None, __event_emitter__=None) -> str:
        """
        Farabi sunucusunun kısa durum özetini verir (CPU, bellek, disk, GPU ve servis durumları).
        Yalnızca yöneticiler kullanabilir.
        """
        if not _yonetici_mi(__user__):
            return RET_ROL
        await self._durum(__event_emitter__, "Sunucu durumu alınıyor...", False)
        v, hata = await self._oku(__user__, "/sistem")
        await self._durum(__event_emitter__, "Sunucu durumu alındı.", True)
        if hata:
            return hata
        if not isinstance(v, dict):
            return AG_HATASI
        satirlar = [(f"CPU %{v.get('cpu_yuzde')} ({v.get('cpu_sicaklik_c')} °C), bellek %{v.get('bellek_yuzde')}, "
                     f"disk %{v.get('disk_yuzde')}")]
        for i, g in enumerate(v.get("gpu") or [], 1):
            satirlar.append(f"GPU{i}: %{g.get('kullanim_yuzde')} kullanım, bellek %{g.get('bellek_yuzde')}, "
                            f"{g.get('sicaklik_c')} °C")
        servisler = v.get("servisler") or []
        if servisler:
            satirlar.append("Servisler: " + ", ".join(f"{s.get('ad')} {s.get('durum')}" for s in servisler))
        return "\n".join(satirlar)

    async def yoklama_sorgula(self, tarih: str = "", sinif: str = "", __user__: dict | None = None,
                              __event_emitter__=None) -> str:
        """
        Belirli bir gün için yoklama kayıtlarını getirir. Yalnızca yöneticiler kullanabilir.
        :param tarih: YYYY-MM-DD biçiminde tarih; boş bırakılırsa bugün.
        :param sinif: İsteğe bağlı sınıf adı, örn. 9-A; boşsa tüm sınıflar.
        """
        if not _yonetici_mi(__user__):
            return RET_ROL
        params = {}
        if tarih:
            params["tarih"] = tarih
        if sinif:
            params["sinif"] = sinif
        await self._durum(__event_emitter__, "Yoklama sorgulanıyor...", False)
        v, hata = await self._oku(__user__, "/yoklama", params=params)
        await self._durum(__event_emitter__, "Yoklama sorgulandı.", True)
        if hata:
            return hata
        satirlar = v.get("satirlar") if isinstance(v, dict) else None
        if not satirlar:
            return "Bu tarih için yoklama kaydı yok."
        cikti = [f"Yoklama {v.get('tarih')}:"]
        for s in satirlar:
            cikti.append("- " + ", ".join(f"{k}: {s[k]}" for k in s))
        return "\n".join(cikti)

    # ---- değiştiren araçlar (onaylı) --------------------------------

    async def tahta_eylemi(self, eylem: Literal[
                               "yoklama_ac", "yoklama_kapat", "web_ac", "chrome_kapat", "ekran_karart", "ekran_kaldir"],
                           tahtalar: list[str], url: str = "", __user__: dict | None = None,
                           __event_emitter__=None, __event_call__=None) -> str:
        """
        Seçilen tahtalarda uzaktan eylem yapar. Çalışmadan önce yöneticiden onay penceresiyle onay alınır.
        Yalnızca kullanıcı açıkça isterse çağır.
        :param eylem: yoklama_ac, yoklama_kapat, web_ac, chrome_kapat, ekran_karart ya da ekran_kaldir.
        :param tahtalar: Tahta adları, örn. ["9-A", "fenlab"]; tüm tahtalar için ["hepsi"].
        :param url: Yalnızca web_ac için: açılacak adres (http:// ya da https:// ile başlamalı).
        """
        if not _yonetici_mi(__user__):
            return RET_ROL
        if eylem not in EYLEM_ADLARI:
            return "Geçersiz eylem. Geçerli eylemler: " + ", ".join(EYLEM_ADLARI) + ". Hiçbir işlem yapılmadı."
        secili, hata = await self._hedefler(__user__, tahtalar)
        if hata:
            return hata
        if eylem == "web_ac" and not url_gecerli_mi(url):
            return ("web_ac için geçerli bir http:// ya da https:// adresi gerekli (boşluk, satır sonu ve "
                    "[ ] ( ) < > ` karakterleri olmamalı; gerekirse %-kodlayın). Hiçbir işlem yapılmadı.")
        mesaj = f"Eylem: {_kod(EYLEM_ADLARI[eylem])}\nTahtalar: {_kod(', '.join(secili))}"
        govde = {"eylem": eylem, "tahtalar": secili}
        if eylem == "web_ac":
            mesaj += f"\nAdres: {_kod(url)}"
            govde["url"] = url
        return await self._onayli(
            __user__, __event_emitter__, __event_call__,
            baslik=f"Tahta eylemi: {EYLEM_ADLARI[eylem]}", ozet=f"{EYLEM_ADLARI[eylem]}: {', '.join(secili)}",
            mesaj=mesaj, yol="/eylem", govde=govde)

    async def tahtalari_yeniden_baslat(self, tahtalar: list[str], __user__: dict | None = None,
                                       __event_emitter__=None, __event_call__=None) -> str:
        """
        Seçilen tahtaları yeniden başlatır (reboot). Onay penceresiyle yöneticiden onay alınır; okul saatinde
        sunucu reddeder. Yalnızca kullanıcı açıkça isterse çağır.
        :param tahtalar: Tahta adları, örn. ["9-A", "fenlab"]; tüm tahtalar için ["hepsi"].
        """
        if not _yonetici_mi(__user__):
            return RET_ROL
        secili, hata = await self._hedefler(__user__, tahtalar)
        if hata:
            return hata
        mesaj = (f"Eylem: `Tahtaları yeniden başlat`\nTahtalar: {_kod(', '.join(secili))}\n"
                 "Okul saatinde (ders günü ilk dersten son derse kadar) sunucu reddeder.")
        if "9-A" in secili:
            mesaj += "\n9-A açılışta giriş ekranında kalır (otomatik giriş yok)."
        return await self._onayli(
            __user__, __event_emitter__, __event_call__,
            baslik="Tahtaları yeniden başlat", ozet=f"Yeniden başlatılıyor: {', '.join(secili)}",
            mesaj=mesaj, yol="/yeniden-baslat", govde={"tahtalar": secili})
