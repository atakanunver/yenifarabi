"""Görsel modülü (2026-11-10): haftalık ödül birincileri için 16:9 duvar kağıdı.

HİBRİT: yapay zekâ (CLIProxyAPI, gpt-image-2) YALNIZ isimsiz dekoratif zemini üretir; ödül panelleri,
Ad Soyad / sınıf / başarı metni Pillow ile bu sunucuda basılır. Öğrenci adı `ai_arka_plan`'a ASLA geçmez ve loga yazılmaz.
Arşiv (kalıcı): veri/gorseller/<tarih>/<tarih>_<SSDD>_<tür>.png (tür: hafta-kart, kart, arka-plan,
onayli-arka-plan, serbest; dosya adına öğrenci adı yazılmaz). Tahtaya gönderim YALNIZ elle, panelden.
durum: veri/gorsel_durum.json (atomik yazılır).
"""

import base64
import io
import json
import math
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TABAN = Path(__file__).resolve().parent
VERI = TABAN / "veri"
GORSEL_DIZINI = VERI / "gorseller"
DURUM_YOLU = VERI / "gorsel_durum.json"
CLIPROXY_URL = "http://127.0.0.1:8317/v1/images/generations"
CLIPROXY_AYAR = TABAN / "config" / "cliproxy.json"
MODEL = "gpt-image-2"
OKUL_ODUL_URL = "http://127.0.0.1:9090/api/odul/hafta"
FONT_YOLU = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LISTE_FONT_YOLU = "/usr/share/fonts/opentype/urw-base35/URWGothic-Demi.otf"
GUNLUK_SINIR = 10
KART_BOYUT = (1920, 1080)
PROMPT_EKI = (
    "panel, çerçeve, madalya, yazı ve harf yok; sol kenar (yaklaşık %25) sade ve koyu kalsın, ana dekor "
    "(kupa, defne, altın kıvrımlar) orta ve sağ tarafta olsun, merkezde ve sağda büyük sade alan bırak; "
    "lacivert-altın prestij teması"
)
GENEL_PROMPT_EKI = (
    "zengin, gösterişli ve sinematik; yazı, harf, logo ve filigran yok; ışık efektleri, derinlik ve "
    "ayrıntılı süsleme kenar ve köşelerde yoğun; ortası ve sağ-orta isim listesi için daha sakin, "
    "düşük kontrastlı; sol yaklaşık %20 sakin"
)
VARSAYILAN_PROMPT = (
    "Okul haftalık başarı ödülü için 16:9 duvar kağıdı arka planı: koyu lacivert ve altın tonları, "
    "mezuniyet kepi, defne dalları, kupa ve kitaplar, törensel ve zarif"
)
_ISTANBUL = ZoneInfo("Europe/Istanbul")
_kilit = threading.Lock()


class GorselHatasi(Exception):
    """Kullanıcıya gösterilebilir (içinde öğrenci verisi/anahtar yok) hata."""


def bugun() -> str:
    return datetime.now(_ISTANBUL).date().isoformat()


# --------------------------------------------------------------------
# CLIProxyAPI istemcisi
# --------------------------------------------------------------------


def _anahtar() -> str:
    deger = os.environ.get("CLIPROXY_API_KEY", "").strip()
    if deger:
        return deger
    try:
        deger = str(json.loads(CLIPROXY_AYAR.read_text(encoding="utf-8")).get("anahtar", "")).strip()
    except FileNotFoundError:
        raise GorselHatasi(
            "CLIProxyAPI anahtarı yok: CLIPROXY_API_KEY ortam değişkeni ya da "
            "dashboard/config/cliproxy.json ({\"anahtar\": \"...\"}) tanımlanmalı."
        ) from None
    except (OSError, ValueError):
        raise GorselHatasi("config/cliproxy.json okunamadı (geçerli JSON değil).") from None
    if not deger:
        raise GorselHatasi("config/cliproxy.json içinde 'anahtar' boş.")
    return deger


def ai_arka_plan(prompt: str, boyut: str = "1536x1024", *, haftalik: bool = True) -> bytes:
    """İsimsiz arka plan PNG'si üretir (~22 sn). Öğrenci adı bu fonksiyona geçirilmez."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise GorselHatasi("Prompt boş.")
    if len(prompt) > 2000:
        raise GorselHatasi("Prompt en çok 2000 karakter olabilir.")
    ek = PROMPT_EKI if haftalik else GENEL_PROMPT_EKI
    govde = {"model": MODEL, "prompt": f"{prompt}. {ek}", "size": boyut, "n": 1}
    istek = urllib.request.Request(
        CLIPROXY_URL,
        data=json.dumps(govde).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_anahtar()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(istek, timeout=150) as yanit:
            veri = json.load(yanit)
        png = base64.b64decode(veri["data"][0]["b64_json"])
        Image.open(io.BytesIO(png)).verify()
    except urllib.error.HTTPError as e:
        raise GorselHatasi(f"Görsel servisi reddetti (HTTP {e.code}).") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        raise GorselHatasi(f"Görsel servisine ulaşılamadı ya da yanıt geçersiz ({type(e).__name__}).") from None
    return png


OLLAMA_SOHBET_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "farabi"  # takma ad: başka adla istek ikinci modeli yükletir
ZENGINLESTIR_SISTEM = (
    "Kullanıcının kısa görsel fikrini, görsel üretim modeli için ayrıntılı tek paragraflık Türkçe bir "
    "prompta dönüştür: konu, kompozisyon, renk paleti, ışık, tarz ve atmosfer. Kullanıcının fikrine "
    "sadık kal, yeni konu ekleme. İstenmedikçe görsele yazı, harf, logo veya kişi adı ekleme. "
    "Yalnızca prompt metnini yaz; açıklama, başlık veya tırnak ekleme. En çok 800 karakter."
)


def prompt_zenginlestir(metin: str) -> str:
    """Kısa fikri yerel LLM ile ayrıntılı prompta çevirir (bulut yok; öğrenci verisi geçirilmez)."""
    metin = (metin or "").strip()
    if not metin:
        raise GorselHatasi("Önce kısa bir fikir yaz.")
    if len(metin) > 1000:
        raise GorselHatasi("Zenginleştirmek için metin en çok 1000 karakter olabilir.")
    govde = {
        "model": OLLAMA_MODEL, "stream": False, "think": False,
        "messages": [{"role": "system", "content": ZENGINLESTIR_SISTEM}, {"role": "user", "content": metin}],
    }
    istek = urllib.request.Request(
        OLLAMA_SOHBET_URL, data=json.dumps(govde).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(istek, timeout=90) as yanit:
            sonuc = json.load(yanit)["message"]["content"]
    except urllib.error.HTTPError as e:
        raise GorselHatasi(f"Yerel yapay zekâ reddetti (HTTP {e.code}).") from None
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise GorselHatasi(f"Yerel yapay zekâya ulaşılamadı ({type(e).__name__}).") from None
    sonuc = re.sub(r"<think>.*?</think>", "", sonuc, flags=re.DOTALL).strip().strip('"“”')
    if not sonuc:
        raise GorselHatasi("Yapay zekâ boş yanıt verdi, tekrar dene.")
    return sonuc[:2000]


# --------------------------------------------------------------------
# Okul ucundan kazananlar
# --------------------------------------------------------------------


def hafta_kazananlari(hb: str | None = None, gecici: bool = True) -> dict:
    """Okul /api/odul/hafta: {"hafta","kesin","kategoriler":{"maraton":[...],"etkinlik":[...]}}."""
    sorgu = {"gecici": "1" if gecici else "0"}
    if hb:
        sorgu["hb"] = hb
    url = OKUL_ODUL_URL + "?" + urllib.parse.urlencode(sorgu)
    try:
        with urllib.request.urlopen(url, timeout=10) as yanit:
            veri = json.load(yanit)
        if not isinstance(veri.get("kategoriler"), dict):
            raise TypeError("kategoriler yok")
    except urllib.error.HTTPError as e:
        raise GorselHatasi(f"Okul servisi kazananları vermedi (HTTP {e.code}).") from None
    except (OSError, ValueError, AttributeError, TypeError) as e:
        raise GorselHatasi(f"Okul servisine ulaşılamadı ({type(e).__name__}).") from None
    return veri


# --------------------------------------------------------------------
# Kart (Pillow)
# --------------------------------------------------------------------

# Paneller Pillow ile çizilir (konum deterministik). Sol x<420 şeridi masaüstü ikonları için boş kalır.
_PANELLER = {"maraton": (470, 1130), "etkinlik": (1180, 1840)}
_SAG_PANEL = _PANELLER["etkinlik"]  # tek dolu kategori sağ panelde
_PANEL_Y = (170, 900)
_MADALYA_R = 46
_BASLIK = {"maraton": "Soru Maratonu Birincisi", "etkinlik": "En Çok Etkinlik"}
_ALTIN = (246, 215, 138, 255)
_BEYAZ = (255, 255, 255, 255)
_ACIK = (200, 215, 240, 255)
_LACIVERT = (10, 22, 56, 200)
_ALTIN_KOYU = (150, 115, 30, 255)
_ALTIN_PARLAK = (243, 215, 122, 255)
_ALTIN_CERCEVE = (212, 175, 55, 255)
_MAKS_AD = 3


def _font(boyut: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_YOLU, boyut)
    except OSError:
        raise GorselHatasi(f"Yazı tipi bulunamadı: {FONT_YOLU}") from None


def _liste_font(boyut: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(LISTE_FONT_YOLU, boyut)
    except OSError:
        raise GorselHatasi(f"Yazı tipi bulunamadı: {LISTE_FONT_YOLU}") from None


def _genislik(font, metin: str) -> float:
    return font.getlength(metin)


def _sar(metin: str, font, genislik: int) -> list[str] | None:
    """Kelime (ve tire) sınırında sarar; tek parça sığmıyorsa None."""
    parcalar = []  # (metin, sonrasında boşluk var mı)
    for kelime in metin.split():
        alt = kelime.split("-")
        parcalar += [(a + "-", False) for a in alt[:-1]] + [(alt[-1], True)]
    satirlar, mevcut = [], ""
    for p, bosluk in parcalar:
        if _genislik(font, p) > genislik:
            return None
        if mevcut and _genislik(font, mevcut + p) > genislik:
            satirlar.append(mevcut.rstrip())
            mevcut = ""
        mevcut += p + (" " if bosluk else "")
    if mevcut.strip():
        satirlar.append(mevcut.rstrip())
    return satirlar


def _adim(font, ad: bool) -> int:
    """Satır yüksekliği; ad satırlarında Ü/İ noktaları üst satıra değmesin diye daha geniş."""
    return round(font.size * (1.2 if ad else 1.3))


def _blok(kayit: dict, genislik: int, yukseklik: int) -> dict:
    """Bir kazanan bloğu: ad (sığan en büyük punto), sınıf, ayrıntı."""
    ad = str(kayit.get("ad_soyad") or "").strip()
    sinif = str(kayit.get("sinif") or "").strip()
    ayrinti = str(kayit.get("ayrinti") or "").strip()
    kucuk = max(18, min(30, yukseklik // 9))
    f_sinif, f_ayr = _font(kucuk), _font(max(16, kucuk - 4))
    alt_satirlar = [(f"Sınıf {sinif}" if sinif else "", f_sinif, _ALTIN)]
    ayr = _sar(ayrinti, f_ayr, genislik) if ayrinti else []
    while ayr is None and len(ayrinti) > 4:  # ayrıntı tek kelimede bile sığmazsa kırp
        ayrinti = ayrinti[:-2]
        ayr = _sar(ayrinti + "…", f_ayr, genislik)
    alt_satirlar += [(s, f_ayr, _ACIK) for s in (ayr or [])[:2]]
    alt_h = 10 + sum(_adim(f, False) for s, f, _ in alt_satirlar if s)
    for boyut in range(64, 15, -2):
        f = _font(boyut)
        satirlar = _sar(ad, f, genislik)
        if satirlar is None or len(satirlar) > 3:
            continue
        if len(satirlar) * _adim(f, True) + alt_h <= yukseklik:
            break
    else:
        f = _font(16)
        satirlar = _sar(ad, f, genislik)
        if satirlar is None:  # tek kelime 16 puntoda bile sığmıyor: harf kırp
            satirlar = [ad[: max(1, int(genislik / (_genislik(f, "M") or 1)) - 1)] + "…"]
    ad_satirlari = [(s, f, _BEYAZ) for s in satirlar]
    tum = ad_satirlari + [x for x in alt_satirlar if x[0]]
    return {"satirlar": tum, "yukseklik": 10 + sum(_adim(fo, i < len(ad_satirlari)) for i, (_, fo, _) in enumerate(tum))}


def _golge_yaz(
    cizim: ImageDraw.ImageDraw,
    orta_x: float,
    y: float,
    metin: str,
    font,
    renk,
    *,
    anchor: str = "ma",
    stroke_width: int = 0,
    stroke_fill=None,
    golge_cizim: ImageDraw.ImageDraw | None = None,
    golge_dx: int = 5,
    golge_dy: int = 6,
) -> None:
    if golge_cizim is not None:
        golge_cizim.text(
            (orta_x + golge_dx, y + golge_dy),
            metin,
            font=font,
            fill=(0, 0, 0, 170),
            anchor=anchor,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 200),
        )
        cizim.text(
            (orta_x, y),
            metin,
            font=font,
            fill=renk,
            anchor=anchor,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
    else:
        for dx, dy, a in ((3, 3, 150), (2, 2, 200)):
            cizim.text((orta_x + dx, y + dy), metin, font=font, fill=(0, 0, 0, a), anchor=anchor)
        cizim.text((orta_x, y), metin, font=font, fill=renk, anchor=anchor)


def _panel_zemin(kart: Image.Image, x0: int, x1: int, y0: int, y1: int) -> Image.Image:
    """Gölge + yarı saydam lacivert panel + iki katmanlı altın çerçeve + madalya (kart üzerine birleştirir)."""
    golge = Image.new("RGBA", kart.size, (0, 0, 0, 0))
    ImageDraw.Draw(golge).rounded_rectangle((x0 + 4, y0 + 8, x1 + 4, y1 + 8), 34, fill=(0, 0, 0, 150))
    kart = Image.alpha_composite(kart, golge.filter(ImageFilter.GaussianBlur(10)))
    kat = Image.new("RGBA", kart.size, (0, 0, 0, 0))
    c = ImageDraw.Draw(kat)
    c.rounded_rectangle((x0, y0, x1, y1), 34, fill=_LACIVERT, outline=_ALTIN_CERCEVE, width=6)
    c.rounded_rectangle((x0 + 14, y0 + 14, x1 - 14, y1 - 14), 24, outline=_ALTIN_PARLAK, width=2)
    cx, r = (x0 + x1) // 2, _MADALYA_R
    for yon in (-1, 1):  # şerit uçları (madalyanın arkasından yukarı)
        c.polygon([(cx + yon * 8, y0 - 6), (cx + yon * 36, y0 - 6), (cx + yon * 58, y0 - 70),
                   (cx + yon * 30, y0 - 70)], fill=(150, 25, 45, 255), outline=_ALTIN_KOYU)
    c.ellipse((cx - r, y0 - r, cx + r, y0 + r), fill=_ALTIN_CERCEVE, outline=_ALTIN_KOYU, width=3)
    c.ellipse((cx - r + 9, y0 - r + 9, cx + r - 9, y0 + r - 9), fill=_ALTIN_PARLAK, outline=_ALTIN_KOYU, width=3)
    c.ellipse((cx - r + 18, y0 - r + 18, cx + r - 18, y0 + r - 18), fill=_ALTIN_CERCEVE)
    yildiz = [(cx + (r - 22) * (1 if i % 2 == 0 else 0.45) * math.sin(i * math.pi / 5),
               y0 - (r - 22) * (1 if i % 2 == 0 else 0.45) * math.cos(i * math.pi / 5)) for i in range(10)]
    c.polygon(yildiz, fill=(255, 240, 190, 255))
    return Image.alpha_composite(kart, kat)


def _panel_ciz(cizim, kayitlar: list[dict], baslik: str, x0: int, x1: int, y0: int, y1: int) -> None:
    """Panel içeriği (başlık + en çok 3 blok); y0/y1 panelin dış sınırları."""
    genislik = x1 - x0 - 80
    orta = (x0 + x1) / 2
    ic_ust, ic_alt = y0 + _MADALYA_R + 24, y1 - 40
    f_baslik = _font(34)
    while _genislik(f_baslik, baslik) > genislik and f_baslik.size > 18:
        f_baslik = _font(f_baslik.size - 2)
    ust = ic_ust + f_baslik.size + 22
    kayitlar = kayitlar[:_MAKS_AD]
    ayrilan = (ic_alt - ust) // len(kayitlar)
    bloklar = [_blok(k, genislik, ayrilan) for k in kayitlar]
    toplam = sum(b["yukseklik"] for b in bloklar)
    artan = max(0, ic_alt - ust - toplam)
    aralik = min(36, artan // len(bloklar)) if len(bloklar) > 1 else 0  # bloklar arası ek boşluk
    kayma = (artan - aralik * (len(bloklar) - 1)) // 2  # başlık + bloklar tek grup, dikey ortalı
    _golge_yaz(cizim, orta, ic_ust + kayma, baslik, f_baslik, _ALTIN)
    y = ust + kayma
    for i, b in enumerate(bloklar):
        for metin, font, renk in b["satirlar"]:
            _golge_yaz(cizim, orta, y, metin, font, renk)
            y += _adim(font, renk == _BEYAZ)
        if i < len(bloklar) - 1:
            cizim.line((orta - 90, y + 3 + aralik // 2, orta + 90, y + 3 + aralik // 2), fill=_ALTIN_KOYU, width=2)
            y += aralik
        y += 10


def ogrencileri_ayristir(metin: str) -> list[dict]:
    if len(metin) > 8000:
        raise GorselHatasi("Girdi 8000 karakter sınırını aşıyor.")
    kayitlar = []
    for no, satir in enumerate(metin.splitlines(), 1):
        if not satir.strip():
            continue
        if satir.count(";") + satir.count("\t") != 1:
            raise GorselHatasi(f"{no}. satır: geçersiz ayırıcı.")
        ayirac = ";" if ";" in satir else "\t"
        ad, sinif = (alan.strip() for alan in satir.split(ayirac))
        if not ad or not sinif:
            raise GorselHatasi(f"{no}. satır: eksik alan.")
        if len(kayitlar) == 24:
            raise GorselHatasi(f"{no}. satır: 24 kayıt sınırı aşıldı.")
        kayitlar.append({"ad_soyad": ad, "sinif": sinif})
    return kayitlar


def liste_karti(arka_plan_png: bytes, kayitlar: list[dict], baslik: str = "") -> bytes:
    if len(kayitlar) > 24:
        raise GorselHatasi("Liste 24 kayıt sınırını aşıyor.")
    baslik = (baslik or "").strip()
    if len(baslik) > 60:
        raise GorselHatasi("Başlık en çok 60 karakter olabilir.")
    try:
        arka = Image.open(io.BytesIO(arka_plan_png)).convert("RGB")
    except (OSError, ValueError):
        raise GorselHatasi("Arka plan geçerli bir görsel değil.") from None
    en, boy = KART_BOYUT
    oran = max(en / arka.width, boy / arka.height)
    arka = arka.resize((round(arka.width * oran), round(arka.height * oran)), Image.LANCZOS)
    sol, ust = (arka.width - en) // 2, (arka.height - boy) // 2
    kart = arka.crop((sol, ust, sol + en, ust + boy)).convert("RGBA")
    if not kayitlar:
        cikti = io.BytesIO()
        kart.convert("RGB").save(cikti, "PNG")
        return cikti.getvalue()

    for k in kayitlar:
        ad = str(k.get("ad_soyad") or "").strip()
        sinif = str(k.get("sinif") or "").strip()
        if not ad or not sinif:
            raise GorselHatasi("Listede eksik alan var.")

    x_min = 460
    x_max = 1840
    y_min = 40
    y_max = 1040
    w_avail = x_max - x_min
    h_avail = y_max - y_min

    aday_sutunlar = [1] if len(kayitlar) == 1 else [1, 2]
    sonuclar = {}

    for sutun in aday_sutunlar:
        col_gap = 60 if sutun == 2 else 0
        col_width = (w_avail - col_gap) // sutun
        rows_count = math.ceil(len(kayitlar) / sutun)
        for boyut in range(80, 27, -1):
            f_ad = _liste_font(boyut)
            f_sinif = _liste_font(max(16, round(boyut * 0.65)))
            f_bas_size = round(boyut * 1.3)
            if baslik:
                while f_bas_size > 20:
                    fb = _liste_font(f_bas_size)
                    if fb.getlength(baslik) <= w_avail - 40:
                        break
                    f_bas_size -= 2
                f_bas = _liste_font(f_bas_size)
                baslik_h = f_bas.size * 1.15 + 24
            else:
                f_bas = None
                baslik_h = 0
            h_rec = h_avail - baslik_h
            adim_ad = round(boyut * 1.12)
            adim_sinif = round(f_sinif.size * 1.12)

            parsed_cols = []
            possible = True
            for c in range(sutun):
                c_items = kayitlar[c * rows_count : (c + 1) * rows_count]
                c_parsed = []
                c_h = 0
                for item in c_items:
                    ad = str(item.get("ad_soyad") or "").strip()
                    sinif = str(item.get("sinif") or "").strip()
                    ad_lines = _sar(ad, f_ad, col_width)
                    if ad_lines is None:
                        possible = False
                        break
                    sinif_lines = _sar(sinif, f_sinif, col_width)
                    if sinif_lines is None:
                        possible = False
                        break
                    item_h = len(ad_lines) * adim_ad + len(sinif_lines) * adim_sinif + 4
                    c_h += item_h
                    c_parsed.append((ad_lines, sinif_lines, item_h))
                if not possible:
                    break
                parsed_cols.append((c_parsed, c_h))
            if not possible:
                continue
            max_col_h = max((ch for _, ch in parsed_cols), default=0)
            if max_col_h <= h_rec:
                sonuclar[sutun] = (boyut, f_bas_size, parsed_cols, baslik_h, col_width, col_gap, rows_count)
                break

    if not sonuclar:
        raise GorselHatasi("Liste içeriği ayrılan alana sığmıyor.")

    if len(sonuclar) == 1:
        secilen_sutun = next(iter(sonuclar))
    else:
        b1 = sonuclar[1][0]
        b2 = sonuclar[2][0]
        if b2 > b1:
            secilen_sutun = 2
        elif b1 > b2:
            secilen_sutun = 1
        else:
            secilen_sutun = 1 if len(kayitlar) <= 4 else 2

    boyut, f_bas_size, parsed_cols, baslik_h, col_width, col_gap, rows_count = sonuclar[secilen_sutun]
    f_ad = _liste_font(boyut)
    f_sinif = _liste_font(max(16, round(boyut * 0.65)))
    f_bas = _liste_font(f_bas_size) if baslik else None
    adim_ad = round(boyut * 1.12)
    adim_sinif = round(f_sinif.size * 1.12)

    max_col_h = max(ch for _, ch in parsed_cols)
    artan_h = max(0, (h_avail - baslik_h) - max_col_h)
    row_gap = min(36, artan_h // (rows_count - 1)) if rows_count > 1 else 0
    total_h = baslik_h + max_col_h + (rows_count - 1) * row_gap
    top_y = y_min + (h_avail - total_h) // 2

    title_y = top_y
    columns_y = top_y + baslik_h

    col_widths = []
    for c_parsed, _ in parsed_cols:
        cw = 0.0
        for ad_lines, sinif_lines, _ in c_parsed:
            for line in ad_lines:
                cw = max(cw, f_ad.getlength(line))
            for line in sinif_lines:
                cw = max(cw, f_sinif.getlength(line))
        col_widths.append(cw)

    if secilen_sutun == 1:
        total_block_w = col_widths[0]
        block_left = max(float(x_min), (x_min + x_max - total_block_w) / 2)
        col_xs = [round(block_left)]
    else:
        col_gap_actual = 90
        total_block_w = col_widths[0] + col_gap_actual + col_widths[1]
        block_left = (x_min + x_max - total_block_w) / 2
        col_x0 = round(block_left)
        col_x1 = round(col_x0 + col_widths[0] + col_gap_actual)
        col_xs = [col_x0, col_x1]

    title_x = (col_xs[0] + (col_xs[-1] + col_widths[-1])) / 2

    metin_kutulari = []
    if f_bas:
        bw = f_bas.getlength(baslik)
        metin_kutulari.append((title_x - bw / 2, title_y, title_x + bw / 2, title_y + f_bas.size * 1.15))

    for c, (c_parsed, _) in enumerate(parsed_cols):
        cx = col_xs[c]
        cy = columns_y
        for ad_lines, sinif_lines, _ in c_parsed:
            for line in ad_lines:
                lw = f_ad.getlength(line)
                metin_kutulari.append((cx, cy, cx + lw, cy + adim_ad))
                cy += adim_ad
            for line in sinif_lines:
                lw = f_sinif.getlength(line)
                metin_kutulari.append((cx, cy, cx + lw, cy + adim_sinif))
                cy += adim_sinif
            cy += 4 + row_gap

    min_x = min(k[0] for k in metin_kutulari)
    min_y = min(k[1] for k in metin_kutulari)
    max_x = max(k[2] for k in metin_kutulari)
    max_y = max(k[3] for k in metin_kutulari)

    pad_x = 50
    pad_y = 35
    hx0 = max(450, round(min_x - pad_x))
    hx1 = min(1890, round(max_x + pad_x))
    hy0 = max(20, round(min_y - pad_y))
    hy1 = min(1060, round(max_y + pad_y))
    hradius = min(50, (hy1 - hy0) // 4)

    hale = Image.new("RGBA", KART_BOYUT, (0, 0, 0, 0))
    ImageDraw.Draw(hale).rounded_rectangle((hx0, hy0, hx1, hy1), radius=hradius, fill=(5, 10, 30, 120))
    hale = hale.filter(ImageFilter.GaussianBlur(25))
    hale.paste((0, 0, 0, 0), (0, 0, 420, 1080))

    golge_katman = Image.new("RGBA", KART_BOYUT, (0, 0, 0, 0))
    yazi_katman = Image.new("RGBA", KART_BOYUT, (0, 0, 0, 0))
    golge_cizim = ImageDraw.Draw(golge_katman)
    yazi_cizim = ImageDraw.Draw(yazi_katman)

    if f_bas:
        _golge_yaz(
            yazi_cizim,
            title_x,
            title_y,
            baslik,
            f_bas,
            _ALTIN,
            anchor="ma",
            stroke_width=3,
            stroke_fill=(60, 40, 0),
            golge_cizim=golge_cizim,
            golge_dx=5,
            golge_dy=6,
        )

    for c, (c_parsed, _) in enumerate(parsed_cols):
        cx = col_xs[c]
        cy = columns_y
        for ad_lines, sinif_lines, _ in c_parsed:
            for line in ad_lines:
                _golge_yaz(
                    yazi_cizim,
                    cx,
                    cy,
                    line,
                    f_ad,
                    _BEYAZ,
                    anchor="la",
                    stroke_width=4,
                    stroke_fill=(10, 20, 50),
                    golge_cizim=golge_cizim,
                    golge_dx=5,
                    golge_dy=6,
                )
                cy += adim_ad
            for line in sinif_lines:
                _golge_yaz(
                    yazi_cizim,
                    cx,
                    cy,
                    line,
                    f_sinif,
                    _ALTIN,
                    anchor="la",
                    stroke_width=2,
                    stroke_fill=(10, 20, 50),
                    golge_cizim=golge_cizim,
                    golge_dx=4,
                    golge_dy=5,
                )
                cy += adim_sinif
            cy += 4 + row_gap

    golge_katman = golge_katman.filter(ImageFilter.GaussianBlur(6))
    golge_katman.paste((0, 0, 0, 0), (0, 0, 420, 1080))
    yazi_katman.paste((0, 0, 0, 0), (0, 0, 420, 1080))

    kart = Image.alpha_composite(kart, hale)
    kart = Image.alpha_composite(kart, golge_katman)
    kart = Image.alpha_composite(kart, yazi_katman)
    cikti = io.BytesIO()
    kart.convert("RGB").save(cikti, "PNG")
    return cikti.getvalue()


def hafta_karti(arka_plan_png: bytes, kazananlar: dict) -> bytes:
    """1920x1080 PNG: arka plan (cover-kırp) + Pillow ile çizilen ödül panelleri (sol x<420 boş)."""
    dolu = {k: v for k, v in ((k, kazananlar.get(k) or []) for k in _BASLIK) if v}
    if not dolu:
        raise ValueError("Her iki kategori de boş: kart üretilemez.")
    try:
        arka = Image.open(io.BytesIO(arka_plan_png)).convert("RGB")
    except OSError:
        raise GorselHatasi("Arka plan geçerli bir görsel değil.") from None
    en, boy = KART_BOYUT
    oran = max(en / arka.width, boy / arka.height)
    arka = arka.resize((round(arka.width * oran), round(arka.height * oran)), Image.LANCZOS)
    sol, ust = (arka.width - en) // 2, (arka.height - boy) // 2
    kart = arka.crop((sol, ust, sol + en, ust + boy)).convert("RGBA")
    y0, y1 = _PANEL_Y
    yerler = {k: (_PANELLER[k] if len(dolu) == 2 else _SAG_PANEL) for k in dolu}
    for x0, x1 in yerler.values():
        kart = _panel_zemin(kart, x0, x1, y0, y1)
    katman = Image.new("RGBA", KART_BOYUT, (0, 0, 0, 0))
    cizim = ImageDraw.Draw(katman)
    for kategori, kayitlar in dolu.items():
        _panel_ciz(cizim, kayitlar, _BASLIK[kategori], *yerler[kategori], y0, y1)
    cikti = io.BytesIO()
    Image.alpha_composite(kart, katman).convert("RGB").save(cikti, "PNG")
    return cikti.getvalue()


# --------------------------------------------------------------------
# Arşiv ve durum
# --------------------------------------------------------------------


def durum_oku() -> dict:
    varsayilan = {
        "onayli_arka_plan": None, "aday_arka_plan": None, "hafta": None, "onay_zamani": None,
        "uretim": {"tarih": None, "sayi": 0}, "gonderim_gunlugu": [], "hafta_kartlari": {},
    }
    try:
        return {**varsayilan, **json.loads(DURUM_YOLU.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return varsayilan


def durum_guncelle(**alanlar) -> dict:
    """Okuyup birleştirir, atomik yazar (tmp + os.replace)."""
    with _kilit:
        durum = {**durum_oku(), **alanlar}
        DURUM_YOLU.parent.mkdir(parents=True, exist_ok=True)
        gecici = DURUM_YOLU.with_suffix(".json.tmp")
        gecici.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(gecici, DURUM_YOLU)
        return durum


def uretim_hakki_al() -> bool:
    """Günlük sınırın altındaysa sayacı artırıp True döner."""
    with _kilit:
        durum = durum_oku()
    sayac = durum["uretim"]
    sayi = sayac["sayi"] if sayac.get("tarih") == bugun() else 0
    if sayi >= GUNLUK_SINIR:
        return False
    durum_guncelle(uretim={"tarih": bugun(), "sayi": sayi + 1})
    return True


def kalan_hak() -> int:
    sayac = durum_oku()["uretim"]
    return GUNLUK_SINIR - (sayac["sayi"] if sayac.get("tarih") == bugun() else 0)


_AD_DESENI = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_([a-z]+(?:-[a-z]+)*?)(?:-\d+)?\.png$")


def arsivle(tur: str, icerik: bytes) -> Path:
    simdi = datetime.now(_ISTANBUL)
    dizin = GORSEL_DIZINI / simdi.date().isoformat()
    dizin.mkdir(parents=True, exist_ok=True)
    taban = f"{simdi:%Y-%m-%d_%H%M}_{tur}"
    yol, n = dizin / f"{taban}.png", 1
    while yol.exists():
        n += 1
        yol = dizin / f"{taban}-{n}.png"
    yol.write_bytes(icerik)
    return yol


def arsiv_listele() -> list[dict]:
    """veri/gorseller/*/ altındaki geçerli adlı PNG'ler, en yeni üstte: [{ad, tarih, saat, tur}]."""
    sonuc = []
    if GORSEL_DIZINI.is_dir():
        for yol in GORSEL_DIZINI.glob("*/*.png"):
            m = _AD_DESENI.match(yol.name)
            if m and yol.parent.name == m.group(1) and yol.is_file():
                sonuc.append({"ad": yol.name, "tarih": m.group(1), "saat": f"{m.group(2)[:2]}:{m.group(2)[2:]}",
                              "tur": m.group(3)})
    return sorted(sonuc, key=lambda x: x["ad"], reverse=True)


def arsiv_yolu(ad: str) -> Path | None:
    """Ad doğrulaması (yol geçişine karşı): yalnız desene uyan, GORSEL_DIZINI altındaki mevcut PNG."""
    m = _AD_DESENI.match(ad or "")
    if not m:
        return None
    yol = GORSEL_DIZINI / m.group(1) / ad
    kok = GORSEL_DIZINI.resolve()
    if not yol.is_file() or kok not in yol.resolve().parents:
        return None
    return yol


def arsivden_sil(ad: str) -> None:
    """Arşivden tek görsel siler. Aday/onaylı arka plan (kart ve Pazartesi zamanlayıcısı kullanır) silinmez."""
    yol = arsiv_yolu(ad)
    if yol is None:
        raise GorselHatasi("Görsel arşivde yok.")
    durum = durum_oku()
    for anahtar in ("aday_arka_plan", "onayli_arka_plan"):
        if durum.get(anahtar) and Path(durum[anahtar]).resolve() == yol.resolve():
            raise GorselHatasi("Bu görsel şu an arka plan olarak kullanılıyor; silinemez.")
    yol.unlink()
    try:
        yol.parent.rmdir()  # gün klasörü boşaldıysa kaldır
    except OSError:
        pass


def aday_kaydet(png: bytes) -> Path:
    yol = arsivle("arka-plan", png)
    durum_guncelle(aday_arka_plan=str(yol))
    return yol


def onayla(hafta: str | None = None) -> Path:
    """Aday arka planı onaylı olarak kopyalar ve durum dosyasına yazar."""
    aday = durum_oku()["aday_arka_plan"]
    if not aday or not Path(aday).is_file():
        raise GorselHatasi("Onaylanacak arka plan yok: önce arka plan üret.")
    hedef = arsivle("onayli-arka-plan", Path(aday).read_bytes())
    durum_guncelle(
        onayli_arka_plan=str(hedef), hafta=hafta,
        onay_zamani=datetime.now(_ISTANBUL).isoformat(timespec="seconds"),
    )
    return hedef


def kullanilacak_arka_plan() -> Path:
    """Kart için: aday varsa o, yoksa onaylı."""
    durum = durum_oku()
    for anahtar in ("aday_arka_plan", "onayli_arka_plan"):
        yol = durum.get(anahtar)
        if yol and Path(yol).is_file():
            return Path(yol)
    raise GorselHatasi("Arka plan yok: önce arka plan üret.")


def gonderim_kaydet(sonuclar: list[dict]) -> None:
    zaman = datetime.now(_ISTANBUL).isoformat(timespec="seconds")
    gunluk = durum_oku()["gonderim_gunlugu"] + [
        {"tahta": r.get("tahta"), "zaman": zaman, "ok": bool(r.get("basarili"))} for r in sonuclar
    ]
    durum_guncelle(gonderim_gunlugu=gunluk[-50:])


def kart_uret_ve_arsivle(kazananlar: dict, tur: str = "kart", arka_plan: Path | None = None) -> Path:
    arka = (arka_plan or kullanilacak_arka_plan()).read_bytes()
    return arsivle(tur, hafta_karti(arka, kazananlar))

