"""server/atos_wiki.py — Atos (Open WebUI) wiki: kayıtlı dosyalar + Atos'un yazdığı not sayfaları (LLM wiki, 2026-10-21).

İdare, sohbete eklediği Excel/Word/PDF tablolarını `wiki_kaydet` ile buraya alır; sonra aranır,
okunur ve `tablo_uret(wiki_id)` ile yeni tablo/PDF/Excel/Word türetilir (dönüştürme araç tarafında).
Her kayıt iki dosya: `<id>.json` (gerçek veri, TC dahil — kullanıcı kararı 2026-10-21) ve `<id>.md`
(okunur sayfa; TC maskeli). `index.md` her yazımda yeniden üretilir. Veri yalnızca yerelde, yalnızca
İdare'ye açık araçtan erişilir. İçerik loga YAZILMAZ, yalnızca id.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

import belge_arsiv
from webui import webui_anahtari_dogrula

log = logging.getLogger("farabi.atos_wiki")
router = APIRouter(prefix="/api/webui/wiki", dependencies=[Depends(webui_anahtari_dogrula)])

DIZIN = Path("/mnt/farabi-data/farabi/atos_wiki")
AZAMI_SATIR = 20000  # kayıt başına toplam satır
AYRIK_ADLAR = {"index", "log"}  # index.md / log.md'nin üzerine yazılmasın
AZAMI_NOT = 20000  # Atos'un yazdığı not sayfasının en çok karakteri
AZAMI_SABIT = 500  # "sabit" (her mesajda hatırlatılan) sayfanın en çok karakteri
SABIT_TOPLAM = 1000  # sabit sayfaların birlikte en çok karakteri (bağlama giren)
_LINK_RE = re.compile(r"\[\[([^\]\n|]{1,80})(?:\|[^\]\n]*)?\]\]")
AZAMI_PDF_BAYT = 40 * 1024 * 1024
ISTANBUL = ZoneInfo("Europe/Istanbul")
_TR = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
_TC_RE = re.compile(r"(?<!\d)(\d{3})\d{6}(\d{2})(?!\d)")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).translate(_TR).lower())


def _kelimeler(s: str) -> list[str]:
    return [k for k in re.split(r"[^a-z0-9]+", str(s).translate(_TR).lower()) if k]


def _slug(ad: str) -> str:
    return "-".join(_kelimeler(ad))[:60] or "sayfa"


def maskele(metin: str) -> str:
    """11 haneli TC kimlik numarasının ortasını gizler (123******01)."""
    return _TC_RE.sub(r"\1******\2", metin)


AZAMI_METIN = 300_000


class Sayfa(BaseModel):
    """Tablo sayfası (baslik + satirlar) ya da metin sayfası (metin); ikisi birlikte de olabilir."""

    ad: str = Field("Sayfa", max_length=60)
    baslik: list[str] = Field(default_factory=list, max_length=200)
    satirlar: list[list[str]] = Field(default_factory=list)
    metin: str = Field("", max_length=AZAMI_METIN)

    @model_validator(mode="after")
    def _bos_olmasin(self):
        if not self.metin.strip() and not (self.baslik and self.satirlar):
            raise ValueError("sayfada tablo ya da metin olmalı")
        return self


class KaydetIstek(BaseModel):
    ad: str = Field(..., min_length=1, max_length=80)
    kaynak: str = Field("", max_length=200)
    sayfalar: list[Sayfa] = Field(..., min_length=1, max_length=40)


class YazIstek(BaseModel):
    ad: str = Field(..., min_length=1, max_length=80)
    icerik: str = Field(..., min_length=1, max_length=AZAMI_NOT)
    sabit: bool = False


class AraIstek(BaseModel):
    sorgu: str = Field("", max_length=300)
    limit: int = Field(5, ge=1, le=20)


class GetirIstek(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    maskele: bool = True


class PdfIstek(BaseModel):
    ad: str = Field(..., min_length=1, max_length=200)
    icerik_b64: str = Field(..., min_length=1)


def _yaz(yol: Path, metin: str) -> None:
    gecici = yol.with_suffix(yol.suffix + ".tmp")
    gecici.write_text(metin, encoding="utf-8")
    os.replace(gecici, yol)


def _hucre_md(v: str) -> str:
    return maskele(str(v)).replace("|", "\\|").replace("\n", " ")


def _md(kayit: dict) -> str:
    satir = [
        "---",
        f"ad: {kayit['ad']}",
        f"kaynak: {kayit['kaynak']}",
        f"tarih: {kayit['tarih']}",
        "---",
        f"# {kayit['ad']}",
        "",
        "_TC kimlik numaraları bu sayfada maskelidir; gerçek veri `.json` dosyasındadır._",
    ]
    for s in kayit["sayfalar"]:
        if s.get("metin"):
            satir += ["", f"## {s['ad']} (metin)", "", maskele(s["metin"])]
        if s["baslik"]:
            satir += ["", f"## {s['ad']} ({len(s['satirlar'])} satır)", ""]
            satir.append("| " + " | ".join(_hucre_md(h) for h in s["baslik"]) + " |")
            satir.append("|" + "---|" * len(s["baslik"]))
            satir += ["| " + " | ".join(_hucre_md(v) for v in r) + " |" for r in s["satirlar"]]
    return "\n".join(satir) + "\n"


def _kayitlar() -> list[dict]:
    sonuc = []
    for yol in sorted(DIZIN.glob("*.json")):
        try:
            sonuc.append(json.loads(yol.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            log.warning("wiki kaydı okunamadı: %s", yol.name)
    return sonuc


def _indeks_yaz() -> None:
    satir = ["# Atos Wiki", "", "| Sayfa | Tür | Kaynak | Tarih | Sayfa/satır |", "|---|---|---|---|---|"]
    for k in _kayitlar():
        toplam = sum(len(s["satirlar"]) for s in k["sayfalar"])
        tur = "not (sabit)" if k.get("sabit") else k.get("tur", "dosya")
        satir.append(f"| [{k['ad']}]({k['id']}.md) | {tur} | {k['kaynak']} | {k['tarih']} | {len(k['sayfalar'])}/{toplam} |")
    _yaz(DIZIN / "index.md", "\n".join(satir) + "\n")


def _simdi() -> str:
    return datetime.now(ISTANBUL).strftime("%Y-%m-%d %H:%M")


def _log_yaz(olay: str, kid: str, ad: str) -> None:
    """log.md: değiştirilemez günlük (yalnız sona eklenir)."""
    yol = DIZIN / "log.md"
    onceki = yol.read_text(encoding="utf-8") if yol.exists() else "# Atos Wiki günlüğü\n\n"
    _yaz(yol, onceki + f"- {_simdi()} | {olay} | [[{ad}]] (`{kid}`)\n")


def _baglantilar(metin: str) -> list[str]:
    """Metindeki [[Sayfa Adı]] bağlantılarının kimlikleri (sıra korunur, tekrarsız)."""
    return list(dict.fromkeys(_slug(m) for m in _LINK_RE.findall(metin)))


def _gelenler(kid: str) -> list[str]:
    return [k["id"] for k in _kayitlar() if k["id"] != kid and kid in _baglantilar(" ".join(s.get("metin", "") for s in k["sayfalar"]))]


def _ozet(k: dict) -> dict:
    return {
        "id": k["id"],
        "ad": k["ad"],
        "kaynak": k["kaynak"],
        "tarih": k["tarih"],
        "tur": k.get("tur", "dosya"),
        "sayfalar": [
            {"ad": s["ad"], "sutunlar": s["baslik"], "satir": len(s["satirlar"]), "metin": len(s.get("metin", ""))}
            for s in k["sayfalar"]
        ],
    }


@router.post("/kaydet")
def kaydet(istek: KaydetIstek):
    toplam = sum(len(s.satirlar) for s in istek.sayfalar)
    if toplam > AZAMI_SATIR:
        return {"durum": "hata", "mesaj": f"En çok {AZAMI_SATIR} satır kaydedilebilir (bu dosyada {toplam})."}
    sayfalar = []
    for s in istek.sayfalar:
        n = len(s.baslik)
        sayfalar.append(
            {
                "ad": s.ad,
                "baslik": s.baslik,
                "satirlar": [(list(map(str, r)) + [""] * n)[:n] for r in s.satirlar],
                "metin": s.metin.strip(),
            }
        )
    govde = json.dumps(sayfalar, ensure_ascii=False, sort_keys=True)
    ozet = hashlib.sha256(govde.encode()).hexdigest()
    kid = _slug(istek.ad)
    if kid in AYRIK_ADLAR:
        return {"durum": "hata", "mesaj": "Bu sayfa adı ayrılmış; başka bir ad seç."}
    DIZIN.mkdir(parents=True, exist_ok=True)
    yol = DIZIN / f"{kid}.json"
    onceki = None
    if yol.exists():
        try:
            onceki = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            onceki = None
    if onceki and onceki.get("tur") == "not":
        return {"durum": "hata", "mesaj": "Bu ad Atos'un yazdığı bir not sayfasına ait; başka bir ad seç."}
    if onceki and onceki.get("hash") == ozet:
        return {"durum": "zaten_vardi", "id": kid, "satir": toplam}
    kayit = {
        "id": kid,
        "ad": istek.ad.strip(),
        "kaynak": istek.kaynak.strip(),
        "tarih": datetime.now(ISTANBUL).strftime("%Y-%m-%d %H:%M"),
        "hash": ozet,
        "sayfalar": sayfalar,
    }
    _yaz(yol, json.dumps(kayit, ensure_ascii=False))
    _yaz(DIZIN / f"{kid}.md", _md(kayit))
    _indeks_yaz()
    _log_yaz("güncellendi" if onceki else "dosyadan kaydedildi", kid, kayit["ad"])
    log.info("wiki kaydedildi: %s (%d sayfa, %d satır)", kid, len(sayfalar), toplam)
    return {"durum": "guncellendi" if onceki else "kaydedildi", "id": kid, "sayfa": len(sayfalar), "satir": toplam}


@router.post("/liste")
def liste():
    return {"durum": "ok", "kayitlar": [_ozet(k) for k in _kayitlar()]}


@router.post("/ara")
def ara(istek: AraIstek):
    belirtecler = _kelimeler(istek.sorgu)
    kayitlar = _kayitlar()
    if not belirtecler:
        return {"durum": "ok", "sonuclar": [_ozet(k) for k in kayitlar[: istek.limit]]}
    puanli = []
    for k in kayitlar:
        baslik_metni = " ".join(_kelimeler(k["ad"] + " " + k["kaynak"] + " " + " ".join(s["ad"] for s in k["sayfalar"])))
        puan = sum(3 for b in belirtecler if b in baslik_metni)
        eslesen = []
        for s in k["sayfalar"]:
            sutun_metni = " ".join(_kelimeler(" ".join(s["baslik"])))
            puan += sum(2 for b in belirtecler if b in sutun_metni)
            for r in s["satirlar"]:
                metin = " ".join(_kelimeler(" ".join(r)))
                n = sum(1 for b in belirtecler if b in metin)
                if n:
                    puan += n
                    eslesen.append((n, s["ad"], s["baslik"], r))
            for par in re.split(r"\n+", s.get("metin", "")):
                n = sum(1 for b in belirtecler if b in " ".join(_kelimeler(par)))
                if n:
                    puan += n
                    eslesen.append((n, s["ad"], ["metin"], [par.strip()[:300]]))
        if puan:
            eslesen.sort(key=lambda x: -x[0])
            puanli.append((puan, k, eslesen[:5]))
    puanli.sort(key=lambda x: -x[0])
    sonuc = []
    for _p, k, eslesen in puanli[: istek.limit]:
        o = _ozet(k)
        o["eslesen_satirlar"] = [
            {"sayfa": ad, "satir": {h: maskele(str(v)) for h, v in zip(baslik, r, strict=True)}} for _n, ad, baslik, r in eslesen
        ]
        sonuc.append(o)
    return {"durum": "ok", "sonuclar": sonuc}


@router.post("/getir")
def getir(istek: GetirIstek):
    if _slug(istek.id) != istek.id:
        return {"durum": "yok", "mesaj": "Böyle bir wiki sayfası yok."}
    yol = DIZIN / f"{istek.id}.json"
    try:
        kayit = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"durum": "yok", "mesaj": "Böyle bir wiki sayfası yok."}
    if istek.maskele:
        for s in kayit["sayfalar"]:
            s["satirlar"] = [[maskele(v) for v in r] for r in s["satirlar"]]
            s["metin"] = maskele(s.get("metin", ""))
    kayit.pop("hash", None)
    metin = " ".join(s.get("metin", "") for s in kayit["sayfalar"])
    kayit["baglantilar"] = [{"id": b, "var": (DIZIN / f"{b}.json").exists()} for b in _baglantilar(metin)]
    kayit["gelen"] = _gelenler(istek.id)
    return {"durum": "ok", "kayit": kayit}


@router.post("/yaz")
def yaz(istek: YazIstek):
    """Atos'un yazdığı not sayfası (markdown, [[bağlantı]]); güncellemede eski sürüm .gecmis/ altına arşivlenir. Silme yok."""
    icerik = istek.icerik.strip()
    if istek.sabit and len(icerik) > AZAMI_SABIT:
        return {"durum": "hata", "mesaj": f"Sabit sayfa en çok {AZAMI_SABIT} karakter olabilir (bu {len(icerik)})."}
    kid = _slug(istek.ad)
    if kid in AYRIK_ADLAR:
        return {"durum": "hata", "mesaj": "Bu sayfa adı ayrılmış; başka bir ad seç."}
    DIZIN.mkdir(parents=True, exist_ok=True)
    yol = DIZIN / f"{kid}.json"
    onceki = None
    if yol.exists():
        try:
            onceki = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            onceki = None
        if onceki and onceki.get("tur") != "not":
            return {"durum": "hata", "mesaj": "Bu ad dosyadan kaydedilmiş bir sayfaya ait; başka bir ad seç."}
    ozet = hashlib.sha256((icerik + str(istek.sabit)).encode()).hexdigest()
    if onceki and onceki.get("hash") == ozet:
        return {"durum": "zaten_vardi", "id": kid}
    if onceki:
        gecmis = DIZIN / ".gecmis" / kid
        gecmis.mkdir(parents=True, exist_ok=True)
        _yaz(gecmis / (datetime.now(ISTANBUL).strftime("%Y%m%d-%H%M%S") + ".json"), json.dumps(onceki, ensure_ascii=False))
    kayit = {
        "id": kid,
        "ad": istek.ad.strip(),
        "kaynak": "Atos notu",
        "tarih": _simdi(),
        "hash": ozet,
        "tur": "not",
        "sabit": istek.sabit,
        "sayfalar": [{"ad": "Not", "baslik": [], "satirlar": [], "metin": icerik}],
    }
    _yaz(yol, json.dumps(kayit, ensure_ascii=False))
    _yaz(DIZIN / f"{kid}.md", _md(kayit))
    _indeks_yaz()
    _log_yaz("güncellendi" if onceki else "yazıldı", kid, kayit["ad"])
    eksik = [b for b in _baglantilar(icerik) if not (DIZIN / f"{b}.json").exists() and b != kid]
    log.info("wiki notu yazıldı: %s (%d karakter)", kid, len(icerik))
    return {"durum": "guncellendi" if onceki else "yazildi", "id": kid, "eksik_baglantilar": eksik}


@router.post("/sabit")
def sabit():
    """Her mesajda modele hatırlatılan kısa sayfalar (toplam SABIT_TOPLAM karakter bütçesi)."""
    sonuc, kalan = [], SABIT_TOPLAM
    for k in sorted((k for k in _kayitlar() if k.get("sabit")), key=lambda k: k["tarih"]):
        metin = maskele(" ".join(s.get("metin", "") for s in k["sayfalar"]).strip())
        if len(metin) > kalan:
            break
        kalan -= len(metin)
        sonuc.append({"ad": k["ad"], "tarih": k["tarih"], "metin": metin})
    return {"durum": "ok", "sayfalar": sonuc}


@router.post("/pdf-tablo")
def pdf_tablo(istek: PdfIstek):
    """PDF'teki tabloları ham satır listesi olarak döndürür (başlık seçimi araç tarafında). Saklanmaz."""
    try:
        veri = base64.b64decode(istek.icerik_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="icerik_b64 geçersiz") from None
    if not veri or len(veri) > AZAMI_PDF_BAYT:
        return {"durum": "hata", "mesaj": "Dosya boş ya da 40 MB'tan büyük."}
    try:
        import pymupdf

        belge = pymupdf.open(stream=veri, filetype="pdf")
        tablolar = []
        for sayfa in belge:
            for i, t in enumerate(sayfa.find_tables().tables, 1):
                satirlar = [[("" if h is None else str(h).replace("\n", " ").strip()) for h in r] for r in t.extract()]
                if len(satirlar) >= 2:
                    tablolar.append({"ad": f"Sayfa {sayfa.number + 1} Tablo {i}", "satirlar": satirlar})
    except Exception:
        log.warning("wiki pdf-tablo okunamadı", exc_info=True)
        return {"durum": "hata", "mesaj": "PDF okunamadı (bozuk ya da desteklenmeyen içerik)."}
    if not tablolar:
        return {"durum": "yok", "mesaj": "PDF'te tablo bulunamadı (taranmış/görüntü PDF olabilir)."}
    return {"durum": "ok", "tablolar": tablolar}


@router.post("/metin")
def metin(istek: PdfIstek):
    """PDF/görsel/docx metni (taranmışsa yerel OCR; en çok 40 sayfa / 30000 karakter). Saklanmaz."""
    y = belge_arsiv.belge_oku(belge_arsiv.BelgeIstek(ad=istek.ad, icerik_b64=istek.icerik_b64))
    return {k: y.get(k) for k in ("durum", "mesaj", "metin", "kisaltildi") if k in y}
