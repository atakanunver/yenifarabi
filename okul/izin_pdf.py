"""Veli izin dilekçesi PDF'i (fpdf2 + sistem DejaVuSans; dış yazı tipi yok).

fpdf2 ya da yazı tipi yoksa None döner: talep yine oluşur, yalnız PDF eksik kalır.
"""

import logging
from pathlib import Path

log = logging.getLogger("okul.izin_pdf")

FONT_DIZINI = Path("/usr/share/fonts/truetype/dejavu")


def dilekce_metni(a: dict) -> str:
    """a: okul_adi, sinif, okul_no, ogrenci, baslangic, bitis, gun, mazeret, fiil, tarih, veli, telefon, ek_var."""
    return (
        f"Velisi olduğum {a['sinif']} sınıfı {a['okul_no']} numaralı öğrencim {a['ogrenci']}, "
        f"{a['baslangic']} – {a['bitis']} tarihleri arasında {a['gun']} gün süreyle {a['mazeret']} nedeniyle "
        f"okula devam {a['fiil']}. Söz konusu devamsızlığın özürlü devamsızlık olarak değerlendirilmesi "
        "hususunda gereğini bilgilerinize arz ederim."
    )


def uret(a: dict) -> bytes | None:
    try:
        from fpdf import FPDF
    except ImportError:
        log.warning("fpdf2 kurulu değil: izin dilekçesi PDF'i üretilmedi")
        return None
    normal, kalin = FONT_DIZINI / "DejaVuSans.ttf", FONT_DIZINI / "DejaVuSans-Bold.ttf"
    if not normal.exists() or not kalin.exists():
        log.warning("DejaVuSans bulunamadı: izin dilekçesi PDF'i üretilmedi")
        return None
    pdf = FPDF(format="A4")
    pdf.set_margins(25, 30, 25)
    pdf.add_page()
    pdf.add_font("DejaVu", "", str(normal))
    pdf.add_font("DejaVu", "B", str(kalin))
    pdf.set_font("DejaVu", "B", 13)
    baslik = f"{a['okul_adi']} Müdürlüğüne" if a.get("okul_adi") else "Okul Müdürlüğüne"
    pdf.multi_cell(0, 8, baslik, align="C")
    pdf.ln(10)
    pdf.set_font("DejaVu", "", 11)
    pdf.multi_cell(0, 7, "        " + dilekce_metni(a), align="J")
    pdf.ln(12)
    for satir in (a["tarih"], "İmza (elektronik başvuru)", a["veli"]):
        pdf.cell(0, 7, satir, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.cell(0, 7, f"İletişim: {a['telefon'] or '-'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Ekler: " + ("Sağlık raporu / belge (1 adet)" if a.get("ek_var") else "Yok"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
