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
import io
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_KALIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OKUL_BASLIK = ("T.C.", "ŞEHİT MURAT USTAOĞLU ANADOLU LİSESİ MÜDÜRLÜĞÜ")


class Tools:
    class Valves(BaseModel):
        api_url: str = "http://127.0.0.1:8000/api/webui/belge-kaydet"
        oku_url: str = "http://127.0.0.1:8000/api/webui/belge-oku"  # kaydetmeden OCR/metin çıkarma
        durum_url: str = "http://127.0.0.1:8000/api/webui/ogrenci-durum/getir"  # Öğrenci Bilgi Formu Detay tablosu
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


    async def belgeyi_oku(
        self,
        dosya_adi: str = "",
        __files__: list | None = None,
        __user__: dict | None = None,
    ) -> str:
        """
        Sohbetteki yazı/PDF/fotoğraf/docx/xlsx'i KAYDETMEDEN okur (taranmış sayfalar yerel OCR). "Yazıyı oku/özetle", "OCR yap", "cevap hazırla" için önce bunu çağır. Excel/CSV/Word TABLOSUNU yeni tabloya, PDF'e ya da Excel'e çevirmek için bunu değil tablo_bilgisi/tablo_uret kullan.
        :param dosya_adi: Adında bu metin geçen dosya; boşsa sohbetteki dosyalar (en çok 3).
        """
        user = __user__ if isinstance(__user__, dict) else {}
        try:
            dosyalar = await self._dosyalar(__files__, user, (dosya_adi or "").strip())
        except Exception:  # noqa: BLE001
            dosyalar = []
        if not dosyalar:
            return (
                "Bu sohbette okunacak dosya bulunamadı. Kullanıcıdan belgeyi sohbete ekleyip "
                "tekrar istemesini iste. Belge içeriğini uydurma."
            )
        satirlar = []
        async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn, trust_env=False) as c:
            for f in dosyalar[:3]:
                try:
                    veri = self._oku(f.path)
                    r = await c.post(
                        self.valves.oku_url,
                        headers={"X-Farabi-WebUI-Key": self.valves.api_key},
                        json={"ad": f.filename, "icerik_b64": base64.b64encode(veri).decode()},
                    )
                    y = r.json() if r.status_code == 200 else None
                except (OSError, httpx.HTTPError, ValueError):
                    y = None
                if not isinstance(y, dict) or y.get("durum") not in ("ok", "bos"):
                    msg = (y or {}).get("mesaj") if isinstance(y, dict) else None
                    satirlar.append(f"### {f.filename}\nOKUNAMADI: {msg or 'sunucuya ulaşılamadı'}")
                    continue
                if y["durum"] == "bos":
                    satirlar.append(f"### {f.filename}\nBelgede okunabilir metin bulunamadı (boş ya da çok bulanık).")
                    continue
                ek = " (metin kısaltıldı)" if y.get("kisaltildi") else ""
                satirlar.append(
                    f"### {f.filename} — {y['sayfa']} sayfa, {y['ocr_sayfa']} sayfa OCR ile okundu{ek}\n{y['metin']}"
                )
        return (
            "Belge metni (OCR hatası olabilir; okunamayan/şüpheli yerleri [okunamadı] diye işaretle, tahmin ederek "
            "doldurma; sayı, tarih, tutar ve isimleri aynen aktar):\n\n" + "\n\n".join(satirlar)
        )


    async def ogrenci_ozel_durum(
        self,
        tur: str = "ana_baba",
        sinif: str = "",
        __user__: dict | None = None,
    ) -> str:
        """
        "Öğrenci Bilgi Formu Detay" kayıtlarından liste: anne-babası ayrı/ölü, maddi yetersizlik, hastalık. "Anne babası ayrı
        öğrenciler", "maddi desteğe ihtiyacı olanlar", "hasta öğrenciler" için çağır; tahmin etme.
        :param tur: ana_baba | maddi | hastalik | hepsi.
        :param sinif: İsteğe bağlı, örn. "9-A".
        """
        if not isinstance(__user__, dict) or __user__.get("role") != "admin":
            return "Bu kayıtlara yalnızca yönetici hesabı erişebilir."
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn, trust_env=False) as c:
                r = await c.post(
                    self.valves.durum_url,
                    headers={"X-Farabi-WebUI-Key": self.valves.api_key},
                    json={"tur": tur, "sinif": sinif},
                )
            y = r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            y = None
        if not isinstance(y, dict) or y.get("durum") not in ("ok", "yok"):
            return "Öğrenci bilgi formu servisine ulaşılamadı."
        if y["durum"] == "yok":
            return y.get("mesaj", "Öğrenci Bilgi Formu Detay belgesi bulunamadı.")
        liste = y.get("ogrenciler") or []
        if not liste:
            return f"Kayıtta bu ölçüte uyan öğrenci yok ({y['toplam_kayit']} kayıt tarandı, kaynak: {y['kaynak']})."
        satirlar = []
        for o in liste:
            ayr = [f"{ad}: {o[k]}" for k, ad in (("ana_baba", "ana-baba"), ("maddi", "maddi"), ("hastalik", "hastalık"))
                   if o[k].strip() not in ("", "-", "--")]
            satirlar.append(f"- {o['ad_soyad']} — {o['sinif']}, no {o['okul_no']}; " + "; ".join(ayr))
        return (f"Öğrenci Bilgi Formu Detay ({y['kaynak']}, {y['toplam_kayit']} kayıttan {len(liste)} eşleşme):\n"
                + "\n".join(satirlar))

    async def resmi_yazi_pdf(
        self,
        konu: str,
        metin: str,
        makam: str = "",
        sayi: str = "",
        ilgi: str = "",
        imza_ad: str = "",
        imza_unvan: str = "Okul Müdürü",
        __user__: dict | None = None,
    ) -> str:
        """
        Onaylanan resmî yazıyı okul başlıklı PDF yapar, bağlantı verir; bağlantıyı AYNEN ver. Boş alanlar [Sayı] gibi yer tutucu kalır (uydurma).
        :param konu: Tek satır konu.
        :param metin: Gövde; paragraflar boş satırla ayrılır (başlık/makam/imza yazma).
        :param makam: Örn. "... KAYMAKAMLIĞINA".
        :param sayi: Evrak sayısı.
        :param ilgi: İlgi satırı.
        :param imza_ad: İmzalayan adı.
        :param imza_unvan: İmzalayan unvanı.
        """
        if not metin.strip() or not konu.strip():
            return "Konu ve metin boş olamaz; PDF üretilmedi."
        user = __user__ if isinstance(__user__, dict) else {}
        if not user.get("id"):
            return "Kullanıcı bilgisi yok; PDF üretilmedi."
        try:
            veri = self._yazi_pdf(konu, metin, makam, sayi, ilgi, imza_ad, imza_unvan)
            fid, ad = await self._pdf_kaydet(veri, "Resmi_Yazi_" + konu[:40], user)
        except Exception:  # noqa: BLE001
            return "PDF üretilemedi (sunucu hatası)."
        return (
            f"PDF hazır: [{ad}](/api/v1/files/{fid}/content?attachment=true) — bağlantıyı kullanıcıya aynen ver; "
            "yalnızca bu hesap açabilir. Yer tutucuları ([Sayı], [Ad Soyad]...) imzadan önce doldurması gerektiğini hatırlat."
        )

    @staticmethod
    def _yazi_pdf(konu, metin, makam, sayi, ilgi, imza_ad, imza_unvan) -> bytes:
        from fpdf import FPDF

        pdf = FPDF(format="A4")
        pdf.add_font("DejaVu", "", FONT)
        pdf.add_font("DejaVu", "B", FONT_KALIN)
        pdf.set_margins(25, 20, 25)
        pdf.set_auto_page_break(True, 20)
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 11)
        for satir in OKUL_BASLIK:
            pdf.cell(0, 6, satir, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        bugun = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y")
        pdf.set_font("DejaVu", "", 10.5)
        pdf.cell(120, 6, f"Sayı   : {sayi.strip() or '[Sayı]'}")
        pdf.cell(0, 6, bugun, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.multi_cell(0, 6, f"Konu : {konu.strip()}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        pdf.set_font("DejaVu", "B", 11)
        pdf.multi_cell(0, 6, (makam.strip() or "[MAKAM]").upper(), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        pdf.set_font("DejaVu", "", 10.5)
        if ilgi.strip():
            pdf.multi_cell(0, 6, f"İlgi : {ilgi.strip()}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        for paragraf in [p.strip() for p in metin.replace("\r", "").split("\n\n") if p.strip()]:
            pdf.multi_cell(0, 6, "        " + " ".join(paragraf.split()), align="J", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        pdf.ln(12)
        pdf.set_x(pdf.w - pdf.r_margin - 70)
        pdf.set_font("DejaVu", "B", 10.5)
        pdf.cell(70, 6, imza_ad.strip() or "[Ad Soyad]", align="C", new_x="LEFT", new_y="NEXT")
        pdf.set_font("DejaVu", "", 10.5)
        pdf.cell(70, 6, imza_unvan.strip() or "Okul Müdürü", align="C", new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    @staticmethod
    async def _pdf_kaydet(veri: bytes, baslik: str, user: dict):
        from open_webui.models.files import FileForm, Files
        from open_webui.storage.provider import Storage

        fid = str(uuid.uuid4())
        guvenli = "".join(c if c.isalnum() or c in " -_" else "_" for c in baslik).strip().replace(" ", "_") or "yazi"
        ad = f"{guvenli}.pdf"
        _, yol = Storage.upload_file(io.BytesIO(veri), f"{fid}_{ad}", {"OpenWebUI-File-Id": fid})
        await Files.insert_new_file(
            user["id"],
            FileForm(id=fid, filename=ad, path=yol,
                     meta={"name": ad, "content_type": "application/pdf", "size": len(veri)}),
        )
        return fid, ad
