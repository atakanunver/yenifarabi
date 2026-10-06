"""
title: Belge Kalıcı Kayıt
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Sohbete eklenen belgeleri okulun kalıcı belge arşivine (mudur/) kaydeder ve Atos kaynak aramasına (RAG, bge-m3) ekler. Yalnızca İdare.
"""

# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Tool olarak yüklenir; Open WebUI
# içinde elle düzenlenmez. Dosyayı farabi-api'nin /api/webui/belge-kaydet ucuna
# gönderir (server/belge_arsiv.py): mudur/ klasörüne yazılır, idari_yukle.py ile
# RAG'a alınır. Model "kaydettim" demeyi YALNIZCA bu aracın sonucuna dayandırır.

import base64
import hashlib
from pathlib import Path

import httpx
from pydantic import BaseModel

ARSIV = {
    "kaydedildi": "arşive kaydedildi",
    "guncellendi": "arşivdeki eski sürümün yerine kaydedildi",
    "zaten_vardi": "aynı içerik arşivde zaten vardı",
}
RAG = {
    "yuklendi": "kaynak aramasına eklendi",
    "zaten_yuklu": "kaynak aramasında zaten vardı",
}


def _satir(ad: str, y: dict | None) -> str:
    if not isinstance(y, dict):
        return f"- {ad}: sunucuya ulaşılamadı — KAYDEDİLMEDİ"
    if y.get("durum") == "desteklenmiyor":
        return (
            f"- {ad}: desteklenmeyen dosya türü — KAYDEDİLMEDİ ({y.get('mesaj', '')})"
        )
    if y.get("durum") == "hata":
        return f"- {ad}: {y.get('mesaj') or 'hata'} — KAYDEDİLMEDİ"
    arsiv = ARSIV.get(y.get("arsiv"), "arşiv durumu bilinmiyor")
    if y.get("rag") == "hata":
        return (
            f'- {ad}: {arsiv} ("{y.get("ad")}"), ancak kaynak aramasına EKLENEMEDİ; '
            "gece taramasında yeniden denenecek"
        )
    parca = f", {y['parca']} parça" if y.get("parca") else ""
    return f'- {ad}: {arsiv} ("{y.get("ad")}") ve {RAG.get(y.get("rag"), "kaynak aramasında")}{parca}'


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8000/api/webui/belge-kaydet"
        api_key: str = ""
        zaman_asimi_sn: float = 660.0

    def __init__(self):
        self.valves = self.Valves()

    async def _dosyalar(self, files, user: dict, dosya_adi: str) -> list:
        from open_webui.models.files import Files

        bulunan, goruldu = [], set()
        for item in files or []:
            if not isinstance(item, dict) or item.get("type", "file") != "file":
                continue
            fid = item.get("id")
            if not isinstance(fid, str) or not fid or fid in goruldu:
                continue
            goruldu.add(fid)
            f = await Files.get_file_by_id(fid)
            if f is None or not getattr(f, "path", None):
                continue
            if f.user_id != user.get("id") and user.get("role") != "admin":
                continue
            if dosya_adi and dosya_adi.lower() not in (f.filename or "").lower():
                continue
            bulunan.append(f)
        return bulunan

    @staticmethod
    def _oku(yol: str) -> bytes:
        try:
            from open_webui.storage.provider import Storage

            yol = Storage.get_file(yol)
        except Exception:  # noqa: BLE001 — yerel depolamada yol zaten dosyanın kendisi
            pass
        return Path(yol).read_bytes()

    async def belgeyi_kalici_kaydet(
        self,
        dosya_adi: str = "",
        __files__: list | None = None,
        __user__: dict | None = None,
    ) -> str:
        """
        Sohbete eklenmiş belgeleri okulun kalıcı belge arşivine kaydeder ve kaynak aramasına (RAG) ekler; böylece belge sonraki tüm sohbetlerde kullanılabilir. Kullanıcı "kalıcı hafızaya kaydet", "RAG'a ekle", "arşive kaydet", "sisteme yükle" gibi bir istekte bulunduğunda çağır.
        :param dosya_adi: Yalnızca adında bu metin geçen dosyaları kaydet; boş bırakılırsa sohbetteki tüm dosyalar kaydedilir.
        :return: Her dosya için kayıt sonucu.
        """
        user = __user__ if isinstance(__user__, dict) else {}
        try:
            dosyalar = await self._dosyalar(__files__, user, (dosya_adi or "").strip())
        except Exception:  # noqa: BLE001 — Open WebUI iç API'si değişirse sohbet bozulmasın
            dosyalar = []
        if not dosyalar:
            return (
                "Bu sohbette kaydedilecek dosya bulunamadı. Kullanıcıdan belgeyi sohbete ekleyip "
                "tekrar istemesini iste. Belgeyi kaydettiğini SÖYLEME."
            )
        satirlar, hashler = [], set()
        async with httpx.AsyncClient(
            timeout=self.valves.zaman_asimi_sn, trust_env=False
        ) as c:
            for f in dosyalar:
                try:
                    veri = self._oku(f.path)
                except OSError:
                    satirlar.append(f"- {f.filename}: dosya okunamadı — KAYDEDİLMEDİ")
                    continue
                h = hashlib.sha256(veri).hexdigest()
                if h in hashler:
                    satirlar.append(
                        f"- {f.filename}: aynı içerikli dosya bu istekte zaten işlendi (tekrar kaydedilmedi)"
                    )
                    continue
                hashler.add(h)
                try:
                    r = await c.post(
                        self.valves.api_url,
                        headers={"X-Farabi-WebUI-Key": self.valves.api_key},
                        json={
                            "ad": f.filename,
                            "icerik_b64": base64.b64encode(veri).decode(),
                        },
                    )
                    y = r.json() if r.status_code == 200 else None
                except (httpx.HTTPError, ValueError):
                    y = None
                satirlar.append(_satir(f.filename, y))
        return (
            "Belge kayıt sonuçları — kullanıcıya YALNIZCA bunları bildir; KAYDEDİLMEDİ yazan "
            "dosyalar için kaydettim deme:\n" + "\n".join(satirlar)
        )
