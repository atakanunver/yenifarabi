"""idari_yukle.py — saf fonksiyonlar. Gerçek tesseract/bge-m3/DB'ye gitmez."""

from pathlib import Path

import docx
import fitz
import idari_yukle as iy


def test_bilinen_dosya_adi_esleme():
    assert iy.belge_adi(Path("yazıı ve uygulamalı sınavlar yönergesi.pdf")) == \
        "Yazılı ve Uygulamalı Sınavlar Yönergesi"


def test_bilinmeyen_dosya_adi_dosya_kokunden():
    assert iy.belge_adi(Path("okul_nobet-cizelgesi.pdf")) == "Okul Nobet Cizelgesi"


def test_listeleme_alt_klasor_ve_xlsx_haric(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "b.docx").write_bytes(b"x")
    (tmp_path / "c.jpeg").write_bytes(b"x")
    (tmp_path / "d.xlsx").write_bytes(b"x")
    (tmp_path / "GUVENLIK").mkdir()
    (tmp_path / "GUVENLIK" / "e.pdf").write_bytes(b"x")
    assert [p.name for p in iy.belgeleri_listele(tmp_path)] == ["a.pdf", "b.docx", "c.jpeg"]


def test_haric_dosya_listelenmez(tmp_path):
    (tmp_path / "657DEVLET.pdf").write_bytes(b"x")
    (tmp_path / "657_devlet_memurlari_kanunu.pdf").write_bytes(b"x")
    assert [p.name for p in iy.belgeleri_listele(tmp_path)] == ["657DEVLET.pdf"]


def test_metinli_pdf_ocr_suz(tmp_path):
    yol = tmp_path / "m.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Madde 1 - Bu yonetmelik ortaogretim kurumlarini kapsar. " * 3)
    d.save(yol)
    cagri = []
    sonuc = iy.sayfa_metinleri(yol, ocr=lambda png: cagri.append(1) or "OCR")
    assert sonuc[0][0] == 1 and "Madde 1" in sonuc[0][1] and sonuc[0][2] is False
    assert cagri == []


def test_bos_pdf_sayfasi_ocr_a_gider(tmp_path):
    yol = tmp_path / "t.pdf"
    d = fitz.open()
    d.new_page()
    d.save(yol)
    sonuc = iy.sayfa_metinleri(yol, ocr=lambda png: "taranmış metin")
    assert sonuc == [(1, "taranmış metin", True)]


def test_docx_paragraf_ve_tablo(tmp_path):
    yol = tmp_path / "y.docx"
    belge = docx.Document()
    belge.add_paragraph("Sınıf rehber öğretmeni görevleri")
    t = belge.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Görev"
    t.cell(0, 1).text = "Veli toplantısı"
    belge.save(yol)
    (sayfa, metin, ocr_mu), = iy.sayfa_metinleri(yol)
    assert sayfa == 1 and "rehber" in metin and "Veli toplantısı" in metin and ocr_mu is False


def test_gorsel_dosya_ocr(tmp_path):
    yol = tmp_path / "g.jpeg"
    yol.write_bytes(b"\xff\xd8sahte")
    assert iy.sayfa_metinleri(yol, ocr=lambda b: "norm saat") == [(1, "norm saat", True)]
