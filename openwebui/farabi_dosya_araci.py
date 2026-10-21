"""
title: Tablo ve Dosya Çıktısı
author: Farabi (Şehit Murat Ustaoğlu Anadolu Lisesi)
version: 0.1.0
description: Sohbete eklenen Excel (xls/xlsx)/CSV/Word tablosundan sütun seçerek, çıkararak, süzerek, sıralayarak ya da doğum gününe göre dizerek yeni tablo üretir; sohbet metnini ve tabloları Word, Excel ya da PDF dosyası yapar. Yalnızca İdare.
"""

# Bu dosya Open WebUI'ye `openwebui/kur.py` ile Tool olarak yüklenir; Open WebUI
# içinde elle düzenlenmez. Tablo dönüştürmeyi kod yapar (satırlar modele okutulmaz);
# model yalnızca hangi sütunların kalacağını söyler. Veri yerelde kalır, hiçbir yere
# gönderilmez. Kütüphaneler (openpyxl, python-docx, fpdf2) Open WebUI venv'inde kurulu;
# içe aktarmalar işlev içinde, böylece bu dosya kütüphanesiz ortamda da yüklenir.

import base64
import csv
import io
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import httpx
from pydantic import BaseModel

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_KALIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MIME = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
_TR = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")


# Öğrenci tablosunda kayıttan doldurulabilen sütunlar: normalize ad (eş anlamlılar) -> (başlık, kayıttan değer).
# Burada olmayan her sütun (Beden, Ayakkabı No…) BOŞ bırakılır, uydurulmaz.
def _yas(dogum: str, bugun: date) -> str:
    try:
        d = datetime.strptime(dogum, "%Y-%m-%d").date()
    except ValueError:
        return ""
    return str(bugun.year - d.year - ((bugun.month, bugun.day) < (d.month, d.day)))


def _tarih_gg(dogum: str) -> str:
    p = (dogum or "").split("-")
    return f"{p[2]}.{p[1]}.{p[0]}" if len(p) == 3 else ""


def _veli(o: dict, rol: str, alan: str) -> str:
    return next((v[alan] for v in o.get("veliler") or [] if rol in (v.get("rol") or "").lower()), "")


_OGRENCI_ALANLARI = {
    ("adsoyad", "ogrenciadsoyad", "ogrenciadi", "adisoyadi", "isim", "ad"): ("Ad Soyad", lambda o, b: o["ad_soyad"]),
    ("okulno", "numara", "numarasi", "no", "ogrencino", "ogrencinumarasi"): ("Okul No", lambda o, b: str(o.get("okul_no") or "")),
    ("sinif", "sinifi"): ("Sınıf", lambda o, b: o["sinif"]),
    ("dogumtarihi", "dogumtarih"): ("Doğum Tarihi", lambda o, b: _tarih_gg(o.get("dogum_tarihi", ""))),
    ("yas",): ("Yaş", lambda o, b: _yas(o.get("dogum_tarihi", ""), b)),
    ("telefon", "ogrencitelefon", "ogrencitelefonu"): ("Öğrenci Telefon", lambda o, b: o.get("ogrenci_telefon", "")),
    ("anneadi", "annead"): ("Anne Adı", lambda o, b: _veli(o, "anne", "ad_soyad")),
    ("annetelefon", "annetelefonu"): ("Anne Telefon", lambda o, b: _veli(o, "anne", "telefon")),
    ("babaadi", "babaad"): ("Baba Adı", lambda o, b: _veli(o, "baba", "ad_soyad")),
    ("babatelefon", "babatelefonu"): ("Baba Telefon", lambda o, b: _veli(o, "baba", "telefon")),
}


def _ogrenci_alani(ad: str):
    k = _norm(ad)
    return next((v for anahtarlar, v in _OGRENCI_ALANLARI.items() if k in anahtarlar), None)


def _norm(s: str) -> str:
    """Sütun adı karşılaştırması: Türkçe harf, büyük/küçük harf ve noktalama farkını yok sayar."""
    return re.sub(r"[^a-z0-9]", "", str(s).translate(_TR).lower())


_TC_RE = re.compile(r"(?<!\d)(\d{3})\d{6}(\d{2})(?!\d)")


def _maskele(metin: str) -> str:
    """Sohbete yazılacak metinde 11 haneli TC'nin ortasını gizler; dosyaya yazılan veri maskelenmez."""
    return _TC_RE.sub(r"\1******\2", metin)


def _sayfa_adlari(veri: bytes, uzanti: str) -> list[str]:
    """Çok sayfalı dosyada tüm sayfa adları (wiki kaydı için); CSV/Word için tek eleman."""
    if uzanti in ("xlsx", "xlsm"):
        from openpyxl import load_workbook

        return list(load_workbook(io.BytesIO(veri), read_only=True).sheetnames)
    if uzanti == "xls":
        import xlrd

        return xlrd.open_workbook(file_contents=veri).sheet_names()
    if uzanti == "docx":
        import docx

        return [str(i + 1) for i in range(len(docx.Document(io.BytesIO(veri)).tables))]
    return [""]


def _hucre(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


# --- Okuma: her biçim (baslik_listesi, satirlar) döndürür; tüm hücreler metin (TC/okul no başındaki 0 korunur) ---

def _tablo_xlsx(veri: bytes, sayfa: str) -> tuple[list[str], list[list[str]]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    ws = wb[sayfa] if sayfa and sayfa in wb.sheetnames else wb.worksheets[0]
    satirlar = [[_hucre(v) for v in r] for r in ws.iter_rows(values_only=True)]
    return _baslik_ayir(satirlar)


def _tablo_xls(veri: bytes, sayfa: str) -> tuple[list[str], list[list[str]]]:
    """Eski Excel (.xls, ör. EKD çizelgesi): xlrd 2.x yalnızca bu biçimi okur."""
    import xlrd

    kitap = xlrd.open_workbook(file_contents=veri)
    ws = kitap.sheet_by_name(sayfa) if sayfa in kitap.sheet_names() else kitap.sheet_by_index(0)
    satirlar = []
    for i in range(ws.nrows):
        satir = []
        for h in ws.row(i):
            if h.ctype == xlrd.XL_CELL_DATE:
                satir.append(_hucre(xlrd.xldate_as_datetime(h.value, kitap.datemode)))
            else:
                satir.append(_hucre(h.value))
        satirlar.append(satir)
    return _baslik_ayir(satirlar)


def _tablo_csv(veri: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        metin = veri.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin = veri.decode("cp1254", errors="replace")
    ayirac = ";" if metin.count(";") > metin.count(",") else ","
    return _baslik_ayir([[h.strip() for h in r] for r in csv.reader(io.StringIO(metin), delimiter=ayirac)])


def _tablo_docx(veri: bytes, sayfa: str) -> tuple[list[str], list[list[str]]]:
    import docx

    tablolar = docx.Document(io.BytesIO(veri)).tables
    if not tablolar:
        return [], []
    sira = int(sayfa) - 1 if sayfa.isdigit() and 0 < int(sayfa) <= len(tablolar) else 0
    return _baslik_ayir([[c.text.strip() for c in r.cells] for r in tablolar[sira].rows])


def _baslik_ayir(satirlar: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Başlık: ilk 15 dolu satırın en dolusu (resmî çizelgelerde üstte başlık/il/tarih satırları olur);
    öncesi atılır. Tamamen boş satır/sütun atılır; çok sütunlu tabloda tek hücreli alt bilgi satırları atılır."""
    satirlar = [r for r in satirlar if any(h.strip() for h in r)]
    if not satirlar:
        return [], []
    dolu = [sum(1 for h in r if h.strip()) for r in satirlar[:15]]
    ham = satirlar[dolu.index(max(dolu))]
    n = len(ham)
    govde = [(r + [""] * n)[:n] for r in satirlar[dolu.index(max(dolu)) + 1:]]
    if n >= 5:
        govde = [r for r in govde if sum(1 for h in r if h.strip()) > 1]
    tut = [j for j in range(n) if ham[j].strip() or any(r[j].strip() for r in govde)]
    baslik = [ham[j].strip() or f"Sütun {j + 1}" for j in tut]
    return baslik, [[r[j] for j in tut] for r in govde]


def _sutun_bul(baslik: list[str], ad: str) -> int:
    """Tam eşleşme, yoksa tek bir sütunda 'içerir' eşleşmesi; bulunamazsa ya da belirsizse ValueError."""
    k = _norm(ad)
    if not k:
        raise ValueError("boş sütun adı")
    tam = [i for i, h in enumerate(baslik) if _norm(h) == k]
    if len(tam) == 1:
        return tam[0]
    kismi = [i for i, h in enumerate(baslik) if k in _norm(h)]
    if len(kismi) == 1:
        return kismi[0]
    if not tam and not kismi:
        raise ValueError(f"'{ad}' sütunu yok")
    raise ValueError(f"'{ad}' birden fazla sütunla eşleşiyor: " + ", ".join(baslik[i] for i in (tam or kismi)))


def _tarih(s: str) -> date | None:
    for bicim in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip()[:10], bicim).date()
        except ValueError:
            continue
    return None


def _liste(s: str) -> list[str]:
    return [p.strip() for p in (s or "").replace(";", ",").split(",") if p.strip()]


def donustur(
    baslik: list[str],
    satirlar: list[list[str]],
    sutunlar: str = "",
    cikar: str = "",
    filtre_sutun: str = "",
    filtre_deger: str = "",
    sirala: str = "",
    azalan: bool = False,
    dogum_gunune_gore: bool = False,
    bos_sutunlar: str = "",
) -> tuple[list[str], list[list[str]]]:
    """Seçilen sütunları tutar/çıkarır, süzer, sıralar; boş sütun ekler; hata durumunda ValueError(Türkçe mesaj)."""
    satirlar = [list(r) for r in satirlar]
    for yeni in _liste(bos_sutunlar):  # elle doldurulacak boş sütunlar (Beden, Ayakkabı No…); `sutunlar` ile yerleri belirlenebilir
        baslik = [*baslik, yeni]
        satirlar = [[*r, ""] for r in satirlar]
    if filtre_sutun:
        i = _sutun_bul(baslik, filtre_sutun)
        k = _norm(filtre_deger)
        satirlar = [r for r in satirlar if k in _norm(r[i])]
    if dogum_gunune_gore:
        i = _sutun_bul(baslik, "doğum tarihi" if any("dogumtarihi" in _norm(h) for h in baslik) else "doğum")
        anahtarli = []
        for r in satirlar:
            t = _tarih(r[i])
            anahtarli.append(((t.month, t.day) if t else (13, 0), r, t))
        anahtarli.sort(key=lambda x: x[0])
        satirlar = []
        for _k, r, t in anahtarli:
            r = list(r)
            r[i] = t.strftime("%d.%m") if t else r[i]  # yıl atılır: doğum günü tablosunda yıl gerekmez
            satirlar.append(r)
        baslik = [("Doğum Günü" if j == i else h) for j, h in enumerate(baslik)]
    elif sirala:
        i = _sutun_bul(baslik, sirala)
        sayisal = all(re.fullmatch(r"\d+([.,]\d+)?", r[i].strip()) for r in satirlar if r[i].strip())
        satirlar.sort(
            key=(lambda r: float(r[i].replace(",", ".") or 0)) if sayisal else (lambda r: _norm(r[i])),
            reverse=azalan,
        )
    if sutunlar:
        secili = [_sutun_bul(baslik, a) for a in _liste(sutunlar)]
    else:
        secili = list(range(len(baslik)))
    if cikar:
        atilacak = {_sutun_bul(baslik, a) for a in _liste(cikar)}
        secili = [i for i in secili if i not in atilacak]
    if not secili:
        raise ValueError("Tüm sütunlar çıkarıldı; en az bir sütun kalmalı")
    return [baslik[i] for i in secili], [[r[i] for i in secili] for r in satirlar]


# --- Yazma ---

def _xlsx(bloklar: list[tuple[str, list[str], list[list[str]]]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    for ad, baslik, satirlar in bloklar:
        ws = wb.create_sheet(re.sub(r"[\[\]:*?/\\]", "_", ad)[:31] or "Sayfa")
        ws.append(baslik)
        for r in satirlar:
            ws.append(r)  # hepsi metin: TC / okul no başındaki 0 ve uzun sayılar bozulmaz
        for h in ws[1]:
            h.font = Font(bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for j, h in enumerate(baslik, 1):
            en_uzun = max([len(h)] + [len(r[j - 1]) for r in satirlar[:200]])
            ws.column_dimensions[get_column_letter(j)].width = min(max(en_uzun + 2, 8), 50)
    ara = io.BytesIO()
    wb.save(ara)
    return ara.getvalue()


def _docx(baslik_metni: str, bloklar: list[tuple]) -> bytes:
    """bloklar: ("h", düzey, metin) | ("p", metin) | ("t", başlık, satırlar)."""
    import docx
    from docx.enum.section import WD_ORIENT
    from docx.shared import Pt

    d = docx.Document()
    en_genis = max([len(b[1]) for b in bloklar if b[0] == "t"] or [0])
    if en_genis > 6:
        s = d.sections[0]
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = s.page_height, s.page_width
    if baslik_metni:
        d.add_heading(baslik_metni, 0)
    for b in bloklar:
        if b[0] == "h":
            d.add_heading(b[2], min(max(b[1], 1), 4))
        elif b[0] == "p":
            d.add_paragraph(b[1])
        else:
            t = d.add_table(rows=1, cols=len(b[1]), style="Table Grid")
            for c, h in zip(t.rows[0].cells, b[1], strict=True):
                c.text = ""
                c.paragraphs[0].add_run(h).bold = True
            for r in b[2]:
                for c, v in zip(t.add_row().cells, r, strict=True):
                    c.text = v
            for satir in t.rows:
                for c in satir.cells:
                    for p in c.paragraphs:
                        for run in p.runs:
                            run.font.size = Pt(9 if en_genis > 6 else 10)
            d.add_paragraph()
    ara = io.BytesIO()
    d.save(ara)
    return ara.getvalue()


def _pdf(baslik_metni: str, bloklar: list[tuple]) -> bytes:
    from fpdf import FPDF

    en_genis = max([len(b[1]) for b in bloklar if b[0] == "t"] or [0])
    pdf = FPDF(format="A4", orientation="L" if en_genis > 6 else "P")
    pdf.add_font("DejaVu", "", FONT)
    pdf.add_font("DejaVu", "B", FONT_KALIN)
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    if baslik_metni:
        pdf.set_font("DejaVu", "B", 14)
        pdf.multi_cell(0, 8, baslik_metni, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    for b in bloklar:
        if b[0] == "h":
            pdf.set_font("DejaVu", "B", max(16 - 2 * b[1], 10))
            pdf.multi_cell(0, 7, b[2], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif b[0] == "p":
            pdf.set_font("DejaVu", "", 10.5)
            pdf.multi_cell(0, 6, b[1], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        else:
            pdf.set_font("DejaVu", "", 9 if len(b[1]) > 6 else 10)
            with pdf.table(text_align="LEFT") as t:
                satir = t.row()
                pdf.set_font("DejaVu", "B", 9 if len(b[1]) > 6 else 10)
                for h in b[1]:
                    satir.cell(h)
                pdf.set_font("DejaVu", "", 9 if len(b[1]) > 6 else 10)
                for r in b[2]:
                    satir = t.row()
                    for v in r:
                        satir.cell(v)
            pdf.ln(3)
    return bytes(pdf.output())


def _markdown_bloklari(metin: str) -> list[tuple]:
    """Sohbet metnini başlık / paragraf / tablo bloklarına ayırır (| a | b | satırları tablodur)."""
    bloklar, tablo, par = [], [], []

    def tabloyu_kapat():
        if tablo:
            baslik, satirlar = _baslik_ayir(tablo)
            if baslik:
                bloklar.append(("t", baslik, satirlar))
            tablo.clear()

    def paragrafi_kapat():
        if par:
            bloklar.append(("p", " ".join(par)))
            par.clear()

    for ham in metin.splitlines():
        s = ham.strip()
        if s.startswith("|") and s.count("|") >= 2:
            paragrafi_kapat()
            hucreler = [h.strip().replace("**", "") for h in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", h) for h in hucreler if h):
                continue  # ayırıcı satır |---|---|
            tablo.append(hucreler)
            continue
        tabloyu_kapat()
        if not s:
            paragrafi_kapat()
        elif s.startswith("#"):
            paragrafi_kapat()
            duzey = len(s) - len(s.lstrip("#"))
            bloklar.append(("h", duzey, s.lstrip("#").strip().replace("**", "")))
        else:
            par.append(re.sub(r"^[-*]\s+", "• ", s).replace("**", ""))
            if re.match(r"^[-*]\s+|^\d+[.)]\s+", s):
                paragrafi_kapat()  # madde işaretli satır tek başına paragraf
    tabloyu_kapat()
    paragrafi_kapat()
    return bloklar


def _dosya_adi(baslik: str, varsayilan: str) -> str:
    g = "".join(c if c.isalnum() or c in " -_" else "_" for c in baslik).strip().replace(" ", "_")
    return g[:60] or varsayilan


class Tools:
    class Valves(BaseModel):
        wiki_url: str = "http://127.0.0.1:8000/api/webui/wiki"  # farabi-api atos_wiki.py
        api_key: str = ""
        sms_api_url: str = "http://127.0.0.1:8020/api/arac"  # öğrenci kaydı (salt okunur, ogrenci-iletisim)
        sms_api_key: str = ""
        zaman_asimi_sn: float = 120.0

    def __init__(self):
        self.valves = self.Valves()

    # --- Open WebUI dosya deposu (farabi_belge_araci.py ile aynı kalıp; araçlar tek dosya yüklendiği için ayrı kopya) ---

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

    @staticmethod
    async def _kaydet(veri: bytes, ad: str, mime: str, user: dict):
        from open_webui.models.files import FileForm, Files
        from open_webui.storage.provider import Storage

        fid = str(uuid.uuid4())
        _, yol = Storage.upload_file(io.BytesIO(veri), f"{fid}_{ad}", {"OpenWebUI-File-Id": fid})
        await Files.insert_new_file(
            user["id"],
            FileForm(id=fid, filename=ad, path=yol, meta={"name": ad, "content_type": mime, "size": len(veri)}),
        )
        return fid

    async def _sunucu(self, yol: str, govde: dict) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn, trust_env=False) as c:
                r = await c.post(
                    f"{self.valves.wiki_url}/{yol}", headers={"X-Farabi-WebUI-Key": self.valves.api_key}, json=govde
                )
            y = r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None
        return y if isinstance(y, dict) else None

    async def _tablo_oku(self, f, sayfa: str) -> tuple[list[str], list[list[str]]]:
        uzanti = (f.filename or "").rsplit(".", 1)[-1].lower()
        veri = self._oku(f.path)
        if uzanti in ("xlsx", "xlsm"):
            return _tablo_xlsx(veri, sayfa)
        if uzanti == "xls":
            return _tablo_xls(veri, sayfa)
        if uzanti in ("csv", "txt"):
            return _tablo_csv(veri)
        if uzanti == "docx":
            return _tablo_docx(veri, sayfa)
        if uzanti == "pdf":
            tablolar = await self._pdf_tablolari(f.filename, veri)
            sira = int(sayfa) - 1 if sayfa.isdigit() and 0 < int(sayfa) <= len(tablolar) else 0
            return _baslik_ayir(tablolar[sira][1])
        raise ValueError(f"{uzanti or 'bu'} dosya türü desteklenmiyor (xls, xlsx, csv, docx, pdf)")

    async def _pdf_tablolari(self, ad: str, veri: bytes) -> list[tuple[str, list[list[str]]]]:
        y = await self._sunucu("pdf-tablo", {"ad": ad, "icerik_b64": base64.b64encode(veri).decode()})
        if y is None:
            raise ValueError("PDF tablo servisine ulaşılamadı")
        if y.get("durum") != "ok":
            raise ValueError(y.get("mesaj") or "PDF'ten tablo okunamadı")
        return [(t["ad"], t["satirlar"]) for t in y["tablolar"]]

    async def _tek_tablo(self, dosya_adi, sayfa, files, user):
        dosyalar = await self._dosyalar(files, user, (dosya_adi or "").strip())
        if not dosyalar:
            raise ValueError("Bu sohbette tablo dosyası bulunamadı; kullanıcıdan Excel/CSV/Word dosyasını eklemesini iste")
        f = dosyalar[0]
        baslik, satirlar = await self._tablo_oku(f, (sayfa or "").strip())
        if not baslik:
            raise ValueError(f"{f.filename}: tablo bulunamadı ya da boş")
        return f, baslik, satirlar

    async def _bagla(self, bloklar_xlsx, bloklar_belge, baslik, bicimler, user, varsayilan):
        """İstenen biçimlerde dosyaları yazar; (bağlantı satırları, hatalar) döndürür."""
        satirlar, hatalar = [], []
        gecerli = [b for b in dict.fromkeys(x.lower().lstrip(".") for x in _liste(bicimler) or ["xlsx"]) if b in MIME]
        if not gecerli:
            return [], ["Biçim xlsx, docx ya da pdf olmalı"]
        ad = _dosya_adi(baslik, varsayilan)
        for b in gecerli:
            try:
                veri = (
                    _xlsx(bloklar_xlsx) if b == "xlsx" else _docx(baslik, bloklar_belge) if b == "docx" else _pdf(baslik, bloklar_belge)
                )
                fid = await self._kaydet(veri, f"{ad}.{b}", MIME[b], user)
                satirlar.append(f"- {b.upper()}: [{ad}.{b}](/api/v1/files/{fid}/content?attachment=true)")
            except Exception:  # noqa: BLE001 — bir biçim bozulsa diğerleri verilsin
                hatalar.append(f"{b.upper()} üretilemedi (sunucu hatası)")
        return satirlar, hatalar

    @staticmethod
    def _yanit(satirlar: list[str], hatalar: list[str], ozet: str) -> str:
        if not satirlar:
            return "Dosya üretilemedi: " + "; ".join(hatalar) + ". Dosya hazır dediğini SÖYLEME."
        return (
            f"{ozet}\nİndirme bağlantıları — bağlantıları kullanıcıya AYNEN ver:\n" + "\n".join(satirlar)
            + ("\nÜretilemeyenler: " + "; ".join(hatalar) if hatalar else "")
        )

    # --- Modelin çağırdığı araçlar ---

    async def tablo_bilgisi(
        self,
        dosya_adi: str = "",
        sayfa: str = "",
        __files__: list | None = None,
        __user__: dict | None = None,
    ) -> str:
        """
        Sohbetteki Excel/CSV/Word/PDF tablosunun sütunlarını, satır sayısını ve ilk 3 satırını verir (TC maskeli). Dosya üretmeden önce çağır; sütun adı uydurma.
        :param dosya_adi: Dosya adında geçen metin; boşsa ilk dosya.
        :param sayfa: Excel sayfa adı / Word-PDF kaçıncı tablo; boşsa ilk.
        """
        user = __user__ if isinstance(__user__, dict) else {}
        try:
            f, baslik, satirlar = await self._tek_tablo(dosya_adi, sayfa, __files__, user)
        except ValueError as e:
            return f"{e}."
        except Exception:  # noqa: BLE001 — Open WebUI iç API'si/okuma hatası sohbeti bozmasın
            return "Dosya okunamadı."
        ornek = _maskele("\n".join("| " + " | ".join(r) + " |" for r in satirlar[:3]))
        return (
            f"{f.filename}: {len(satirlar)} satır, {len(baslik)} sütun.\n"
            f"Sütunlar: {', '.join(baslik)}\nİlk satırlar (TC maskeli; kişisel veri içerebilir, sohbette tekrar etme):\n{ornek}"
        )

    async def tablo_uret(
        self,
        dosya_adi: str = "",
        wiki_id: str = "",
        sutunlar: str = "",
        cikar: str = "",
        filtre_sutun: str = "",
        filtre_deger: str = "",
        sirala: str = "",
        azalan: bool = False,
        dogum_gunune_gore: bool = False,
        bos_sutunlar: str = "",
        bicim: str = "xlsx",
        baslik: str = "",
        sayfa: str = "",
        __files__: list | None = None,
        __user__: dict | None = None,
    ) -> str:
        """
        Tablodan yeni tablo üretip Excel/Word/PDF yapar (TC'siz, seçili sütunlar, süzme, sıralama, doğum günü listesi, boş sütun). Kaynak: sohbet dosyası ya da wiki sayfası (wiki_id). Önce tablo_bilgisi / wiki_oku ile sütunları gör.
        :param dosya_adi: Kaynak sohbet dosyası (adında geçen metin); boşsa ilk.
        :param wiki_id: Doluysa kaynak wiki sayfasıdır (wiki_ara verir).
        :param sutunlar: Tutulacak sütunlar, virgüllü ve sıralı; boşsa hepsi.
        :param cikar: Çıkarılacak sütunlar (örn. "TC").
        :param filtre_sutun: Süzülecek sütun.
        :param filtre_deger: Bu metni içeren satırlar kalır.
        :param sirala: Sıralanacak sütun.
        :param azalan: true: büyükten küçüğe.
        :param dogum_gunune_gore: true: "Doğum Günü" (GG.AA) listesi.
        :param bos_sutunlar: Eklenecek boş sütunlar, virgüllü (örn. "Beden, Ayakkabı No"); yerleri sutunlar sırasıyla belirlenir.
        :param bicim: xlsx, docx, pdf (virgülle birden fazla).
        :param baslik: Belge başlığı / dosya adı.
        :param sayfa: Excel sayfa adı, kaçıncı tablo ya da wiki sekmesi; boşsa ilk.
        """
        user = __user__ if isinstance(__user__, dict) else {}
        try:
            if (wiki_id or "").strip():
                y = await self._sunucu("getir", {"id": wiki_id.strip(), "maskele": False})
                if y is None:
                    return self._WIKI_HATA + " Dosya hazır dediğini SÖYLEME."
                if y.get("durum") != "ok":
                    return y.get("mesaj", "Wiki sayfası bulunamadı.") + " Dosya üretilmedi."
                k = y["kayit"]
                sec = [t for t in k["sayfalar"] if t["baslik"] and (not sayfa or _norm(sayfa) in _norm(t["ad"]))]
                if not sec:
                    return "Böyle bir sayfa/sekme yok: " + ", ".join(t["ad"] for t in k["sayfalar"]) + ". Dosya üretilmedi."
                baslik_l, satirlar, varsayilan = sec[0]["baslik"], sec[0]["satirlar"], f"{k['ad']} {sec[0]['ad']}"
            else:
                f, baslik_l, satirlar = await self._tek_tablo(dosya_adi, sayfa, __files__, user)
                varsayilan = f.filename.rsplit(".", 1)[0] + "_yeni"
            b2, s2 = donustur(
                baslik_l, satirlar, sutunlar, cikar, filtre_sutun, filtre_deger, sirala, azalan, dogum_gunune_gore, bos_sutunlar
            )
        except ValueError as e:
            return f"Tablo üretilemedi: {e}. Sütunlar için tablo_bilgisi / wiki_oku'yu çağır; dosya hazır dediğini SÖYLEME."
        except Exception:  # noqa: BLE001
            return "Dosya okunamadı; tablo üretilmedi."
        return await self._yeni_dosya(b2, s2, (baslik or "").strip() or varsayilan, bicim, user)

    async def _yeni_dosya(self, b2, s2, ad, bicim, user) -> str:
        if not s2:
            return "Süzme sonucunda hiç satır kalmadı; dosya üretilmedi. Filtre değerini kontrol et."
        satir_l, hatalar = await self._bagla([(ad, b2, s2)], [("t", b2, s2)], ad, bicim, user, "Tablo")
        return self._yanit(satir_l, hatalar, f"{len(s2)} satır, {len(b2)} sütunlu tablo hazır (sütunlar: {', '.join(b2)}).")

    async def sohbeti_dosyaya_cevir(
        self,
        metin: str,
        baslik: str = "",
        bicim: str = "pdf",
        __user__: dict | None = None,
    ) -> str:
        """
        Verilen metni/Markdown tabloyu Word, Excel ya da PDF yapar ("bunu PDF yap"). Excel'de her tablo ayrı sayfa olur.
        :param metin: Dosyaya konacak tam metin (Markdown); içerik uydurma.
        :param baslik: Başlık / dosya adı.
        :param bicim: xlsx, docx, pdf (virgülle birden fazla).
        """
        user = __user__ if isinstance(__user__, dict) else {}
        if not user.get("id"):
            return "Kullanıcı bilgisi yok; dosya üretilmedi."
        if not (metin or "").strip():
            return "Metin boş; dosya üretilmedi."
        bloklar = _markdown_bloklari(metin)
        tablolar = [(f"Tablo {i}", b[1], b[2]) for i, b in enumerate((x for x in bloklar if x[0] == "t"), 1)]
        if not tablolar:  # Excel için tablosuz metin: tek sütun
            tablolar = [("Metin", ["Metin"], [[b[1] if b[0] == "p" else b[2]] for b in bloklar if b[0] in ("p", "h")])]
        satir_l, hatalar = await self._bagla(tablolar, bloklar, (baslik or "").strip(), bicim, user, "Cikti")
        return self._yanit(satir_l, hatalar, "Dosya hazır.")

    # --- Atos wiki: kayıtlı tablolar (sunucu: server/atos_wiki.py) ---

    _WIKI_HATA = "Wiki servisine ulaşılamadı."

    async def _wiki_sayfalari(self, dosya_ad: str, veri: bytes) -> list[dict]:
        """Dosyadaki tüm tabloları ve metni wiki sayfalarına çevirir (PDF/görsel: tablo + yerel OCR metni)."""
        uzanti = (dosya_ad or "").rsplit(".", 1)[-1].lower()
        sayfalar = []

        def tablo(ad, b, sat):
            if b and sat:
                sayfalar.append({"ad": ad, "baslik": b, "satirlar": sat})

        async def metin(ad):
            y = await self._sunucu("metin", {"ad": dosya_ad, "icerik_b64": base64.b64encode(veri).decode()})
            if y and y.get("durum") == "ok" and (y.get("metin") or "").strip():
                ek = "\n\n[Metin kısaltıldı: ilk 40 sayfa / 30000 karakter]" if y.get("kisaltildi") else ""
                sayfalar.append({"ad": ad, "metin": y["metin"].strip() + ek})

        if uzanti == "pdf":
            try:
                for tad, ham in await self._pdf_tablolari(dosya_ad, veri):
                    tablo(tad, *_baslik_ayir(ham))
            except ValueError:
                pass  # tablosuz PDF: yalnızca metin kaydedilir
            await metin("Metin")
        elif uzanti in ("jpg", "jpeg", "png"):
            await metin("Metin")
        elif uzanti == "txt":
            sayfalar.append({"ad": "Metin", "metin": veri.decode("utf-8", errors="replace").strip()})
        else:
            for sad in _sayfa_adlari(veri, uzanti):
                b, sat = self._tablo_veriden(uzanti, veri, sad)
                tablo(f"Tablo {sad}" if sad.isdigit() else (sad or "Tablo"), b, sat)
            if uzanti == "docx":
                import docx

                govde = "\n".join(p.text for p in docx.Document(io.BytesIO(veri)).paragraphs if p.text.strip())
                if govde:
                    sayfalar.append({"ad": "Metin", "metin": govde})
        return [x for x in sayfalar if x.get("metin") or (x.get("baslik") and x.get("satirlar"))]

    @staticmethod
    def _tablo_veriden(uzanti: str, veri: bytes, sayfa: str) -> tuple[list[str], list[list[str]]]:
        if uzanti in ("xlsx", "xlsm"):
            return _tablo_xlsx(veri, sayfa)
        if uzanti == "xls":
            return _tablo_xls(veri, sayfa)
        if uzanti == "docx":
            return _tablo_docx(veri, sayfa)
        return _tablo_csv(veri)

    async def wiki_kaydet(
        self,
        ad: str,
        dosya_adi: str = "",
        __files__: list | None = None,
        __user__: dict | None = None,
    ) -> str:
        """
        Sohbetteki Excel/CSV/Word/PDF/görsel/txt dosyasını (tüm sayfaları) Atos wiki'ye kaydeder ("hafızana al", "wikiye kaydet"); aynı ad güncellenir.
        :param ad: Wiki sayfası adı.
        :param dosya_adi: Dosya adında geçen metin; boşsa ilk.
        """
        user = __user__ if isinstance(__user__, dict) else {}
        try:
            dosyalar = await self._dosyalar(__files__, user, (dosya_adi or "").strip())
            if not dosyalar:
                return "Bu sohbette kaydedilecek dosya bulunamadı; kullanıcıdan dosyayı eklemesini iste. Kaydettim deme."
            f = dosyalar[0]
            sayfalar = await self._wiki_sayfalari(f.filename, self._oku(f.path))
        except ValueError as e:
            return f"Kaydedilemedi: {e}. Kaydettim deme."
        except Exception:  # noqa: BLE001 — dosya okuma/iç API hatası sohbeti bozmasın
            return "Dosya okunamadı; wiki'ye kaydedilmedi. Kaydettim deme."
        if not sayfalar:
            return f"{f.filename}: kaydedilecek tablo ya da metin bulunamadı. Kaydettim deme."
        y = await self._sunucu("kaydet", {"ad": ad, "kaynak": f.filename, "sayfalar": sayfalar})
        if y is None:
            return self._WIKI_HATA + " Kaydettim deme."
        if y.get("durum") == "hata":
            return f"Kaydedilemedi: {y.get('mesaj', '')} Kaydettim deme."
        etiket = {"kaydedildi": "wiki'ye kaydedildi", "guncellendi": "wiki'de güncellendi", "zaten_vardi": "wiki'de aynı içerikle zaten vardı"}
        return (
            f"{f.filename} {etiket.get(y['durum'], 'işlendi')}: sayfa kimliği `{y['id']}` "
            f"({len(sayfalar)} sayfa, {sum(len(x['satirlar']) for x in sayfalar)} satır, {sum(len(x.get('metin', '')) for x in sayfalar)} karakter metin). "
            "Sonra wiki_ara / wiki_oku / tablo_uret(wiki_id) ile kullanılır."
        )

    async def wiki_yaz(self, ad: str, icerik: str, sabit: bool = False, __user__: dict | None = None) -> str:
        """
        Atos wiki'ye bilgi sayfası yazar/günceller ("hatırla", "not al", "kaydet", belge/konu özeti). Önce wiki_ara ile var mı bak; varsa wiki_oku ile oku ve TÜM sayfayı güncelleyerek yaz, yinelenen sayfa açma. Markdown yaz; ilgili sayfalara [[Sayfa Adı]] ile bağ ver. Eski sürüm saklanır. Yalnız kullanıcının söylediği ya da belgedeki bilgiyi yaz, tahmin ekleme.
        :param ad: Sayfa adı.
        :param icerik: Markdown gövde (en çok 20000 karakter).
        :param sabit: True: her mesajda hatırlatılan kısa kural sayfası (en çok 500 karakter; çok az kullan).
        """
        y = await self._sunucu("yaz", {"ad": ad, "icerik": icerik, "sabit": bool(sabit)})
        if y is None:
            return self._WIKI_HATA + " Kaydettim deme."
        if y.get("durum") == "hata":
            return f"Yazılamadı: {y.get('mesaj', '')} Kaydettim deme."
        etiket = {"yazildi": "wiki'ye yazıldı", "guncellendi": "wiki'de güncellendi (eski sürüm saklandı)", "zaten_vardi": "wiki'de aynı içerikle zaten vardı"}
        eksik = f" Henüz olmayan bağlantılar: {', '.join(y['eksik_baglantilar'])} (gerekirse bu sayfaları da yaz)." if y.get("eksik_baglantilar") else ""
        return f"`{y['id']}` {etiket.get(y['durum'], 'işlendi')}.{eksik}"

    async def wiki_ara(self, sorgu: str = "", __user__: dict | None = None) -> str:
        """
        Atos wiki'deki sayfalarda (dosyadan kaydedilen tablo/metinler ve yazılmış notlar) arar; boş sorgu tüm sayfaları listeler. Sonucu uydurma.
        :param sorgu: Aranacak kelimeler.
        """
        y = await self._sunucu("ara", {"sorgu": sorgu or "", "limit": 5})
        if y is None or y.get("durum") != "ok":
            return self._WIKI_HATA
        sonuc = y.get("sonuclar") or []
        if not sonuc:
            return "Wiki'de eşleşen kayıt yok." if sorgu else "Wiki boş; kaydetmek için wiki_kaydet kullanılır."
        satirlar = []
        for k in sonuc:
            sayfalar = "; ".join(
                (f"{s['ad']} ({s['satir']} satır: {', '.join(s['sutunlar'][:8])})" if s["sutunlar"] else f"{s['ad']} (metin)")
                for s in k["sayfalar"]
            )
            tur = "not" if k.get("tur") == "not" else f"kaynak {k['kaynak']}"
            satirlar.append(f"- `{k['id']}` — {k['ad']} ({tur}, {k['tarih']}): {sayfalar}")
            for e in k.get("eslesen_satirlar", []):
                satirlar.append("    • " + e["sayfa"] + ": " + "; ".join(f"{h}={v}" for h, v in e["satir"].items() if v))
        return "Wiki sonuçları (TC maskeli; yalnızca bunları aktar):\n" + "\n".join(satirlar)

    async def wiki_oku(self, id: str, sayfa: str = "", __user__: dict | None = None) -> str:
        """
        Wiki sayfasını açar (sütunlar, ilk 25 satır, metin, bağlantılar; TC maskeli).
        :param id: wiki_ara'nın verdiği kimlik.
        :param sayfa: Sekme adı; boşsa tümü.
        """
        y = await self._sunucu("getir", {"id": (id or "").strip(), "maskele": True})
        if y is None:
            return self._WIKI_HATA
        if y.get("durum") != "ok":
            return y.get("mesaj", "Wiki sayfası bulunamadı.")
        k = y["kayit"]
        bolumler = [f"{k['ad']} (kaynak {k['kaynak']}, {k['tarih']})"]
        for s in k["sayfalar"]:
            if sayfa and _norm(sayfa) not in _norm(s["ad"]):
                continue
            if s.get("metin"):
                kisa = " [metin kısaltıldı, tamamı wiki_ara ile aranır]" if len(s["metin"]) > 4000 else ""
                bolumler.append(f"## {s['ad']} — metin ({len(s['metin'])} karakter)\n{s['metin'][:4000]}{kisa}")
            if s["baslik"]:
                govde = "\n".join("| " + " | ".join(r) + " |" for r in s["satirlar"][:25])
                bolumler.append(f"## {s['ad']} — {len(s['satirlar'])} satır\nSütunlar: {', '.join(s['baslik'])}\n{govde}")
        if k.get("baglantilar"):
            bolumler.append("Bağlantılar: " + ", ".join(b["id"] + ("" if b["var"] else " (henüz yok)") for b in k["baglantilar"]))
        if k.get("gelen"):
            bolumler.append("Bu sayfaya bağlananlar: " + ", ".join(k["gelen"]))
        return "\n\n".join(bolumler)

    # --- Okul verisinden öğrenci tablosu: satırlar modele okutulmaz, bilinmeyen sütun boş kalır ---

    async def ogrenci_tablosu(
        self,
        sutunlar: str,
        sinif: str = "",
        ad: str = "",
        dogum_yili: str = "",
        bicim: str = "xlsx",
        baslik: str = "",
        __user__: dict | None = None,
    ) -> str:
        """
        Okul kayıtlarından öğrenci tablosu üretip Excel/Word/PDF yapar. Kayıttaki sütunlar dolar (Ad Soyad, Okul No, Sınıf, Doğum Tarihi, Yaş, Öğrenci/Anne/Baba Telefon, Anne/Baba Adı); kayıtta olmayanlar (Beden, Ayakkabı No…) BOŞ kalır. Öğrenci listesini kendin yazma.
        :param sutunlar: İstenen sütunlar, virgüllü ve sıralı.
        :param sinif: Sınıf ya da virgüllü sınıflar ("9-A, 9-B"); ad/doğum yılı yoksa zorunlu.
        :param ad: İsteğe bağlı ad süzmesi.
        :param dogum_yili: İsteğe bağlı 4 haneli yıl.
        :param bicim: xlsx, docx, pdf.
        :param baslik: Başlık / dosya adı.
        """
        user = __user__ if isinstance(__user__, dict) else {}
        if user.get("role") != "admin":
            return "Öğrenci tablosu yalnızca yönetici hesabına açıktır. Dosya üretilmedi."
        istenen = _liste(sutunlar)
        if not istenen:
            return "Sütun listesi boş; hangi sütunlar istendiğini belirt. Dosya üretilmedi."
        siniflar = _liste(sinif) or [""]
        if siniflar == [""] and not ad.strip() and not dogum_yili.strip():
            return "Sınıf (örn. 9-A), ad ya da doğum yılı belirtilmeli. Dosya üretilmedi."
        ogrenciler = []
        try:
            async with httpx.AsyncClient(timeout=self.valves.zaman_asimi_sn, trust_env=False) as c:
                for sn in siniflar:
                    r = await c.get(
                        self.valves.sms_api_url.rstrip("/") + "/ogrenci-iletisim",
                        headers={"X-Sms-Arac-Key": self.valves.sms_api_key},
                        params={"ad": ad, "sinif": sn, "dogum_yili": dogum_yili, "limit": 500},
                    )
                    if r.status_code != 200:
                        return "Öğrenci kaydı servisine ulaşılamadı (ya da arama geçersiz). Dosya üretilmedi."
                    ogrenciler += r.json().get("ogrenciler") or []
        except (httpx.HTTPError, ValueError):
            return "Öğrenci kaydı servisine ulaşılamadı. Dosya üretilmedi."
        if not ogrenciler:
            return "Kayıtlarda eşleşen öğrenci yok. Dosya üretilmedi; öğrenci uydurma."
        bugun = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        alanlar = [_ogrenci_alani(x) for x in istenen]
        basliklar = [(a[0] if a else x) for a, x in zip(alanlar, istenen, strict=True)]
        satirlar = [[(a[1](o, bugun) if a else "") for a in alanlar] for o in ogrenciler]
        dolu = [b for a, b in zip(alanlar, basliklar, strict=True) if a]
        bos = [b for a, b in zip(alanlar, basliklar, strict=True) if not a]
        ad_belge = (baslik or "").strip() or "Öğrenci Tablosu"
        sonuc = await self._yeni_dosya(basliklar, satirlar, ad_belge, bicim, user)
        if "AYNEN" not in sonuc:
            return sonuc
        return (
            sonuc + f"\nKayıttan doldurulan: {', '.join(dolu) or '—'}. "
            f"BOŞ bırakılan (kayıtta yok, elle doldurulacak): {', '.join(bos) or '—'}. Kullanıcıya bunu söyle."
        )
