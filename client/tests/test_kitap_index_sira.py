"""
tools/kitap_index.py — sayfa başlığı çıkarımı fitz'in okuma sırasına bağlı.

Regresyon: `sayfa.get_text()` (sort=False, PDF'in dahili nesne sırası)
kullanıldığında birçok kitapta sayfa numarası (üstbilgi/kenar boşluğu) ünite
başlığından ÖNCE geliyordu — `indexle()` başlığı yalnızca İLK SATIRDAN
okuduğu için bölüm hiç tespit edilemiyordu. Ölçüldü (02.08.2026): gerçek
kitaplıkta 12 kitaptan yalnızca 3'ünde bölüm tespit ediliyordu (biyoloji-9
dahil SIFIR — daha önce çalışan bir kitap `tools/kitap_index.py`'nin
pdfplumber'dan fitz'e taşınmasıyla kırılmıştı). `sort=True` (konum sıralı:
üstten alta, soldan sağa) düzeltti; 9 kitapta iyileşme, hiçbir kitapta
gerileme yok.

Bu test gerçek bir kitaba (kitaplar/ bir DROP DIRECTORY, gitignore'da,
her makinede olmayabilir) bağımlı olmasın diye küçük, sentetik bir PDF
üretir: sayfa numarası nesnesi ÖNCE eklenir (dahili sırada önce gelsin),
başlık nesnesi ondan SONRA ama sayfada ondan daha YUKARIDA/SOLDA çizilir —
tam olarak ölçülen gerçek kitaplardaki düzeni taklit eder.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

fitz = pytest.importorskip("fitz", reason="PyMuPDF kurulu değilse atlanır")

from tools.kitap_index import indexle  # noqa: E402


def _sentetik_pdf(yol: Path) -> None:
    doc = fitz.open()
    sayfa = doc.new_page()
    # ÖNCE eklenen nesne: sayfa numarası, sayfanın ALT kısmında (üstbilgi/
    # kenar boşluğu taklidi) — gerçek kitaplarda ölçülen dahili nesne
    # sırasıyla aynı desen: küçük, konumca sonraki ama nesne sırasınca önceki.
    sayfa.insert_text((500, 750), "7")
    # SONRA eklenen nesne: gerçek başlık, sayfanın ÜST kısmında.
    sayfa.insert_text((50, 60), "1. Tema / Test Ünitesi")
    doc.save(str(yol))
    doc.close()


def test_sayfa_numarasi_basliktan_once_eklenirse_yine_dogru_tespit_edilir(tmp_path):
    pdf_yolu = tmp_path / "sentetik.pdf"
    _sentetik_pdf(pdf_yolu)

    sonuc = indexle(pdf_yolu)

    assert sonuc["bolumler"], (
        "Bölüm tespit edilemedi — sort=True olmadan (ya da bozulursa) "
        "sayfa numarası başlıktan önce okunup regex hiç eşleşmiyor."
    )
    assert sonuc["bolumler"][0]["no"] == 1
    assert "Test Ünitesi" in sonuc["bolumler"][0]["ad"]


def test_get_text_sort_true_ile_cagriliyor():
    """Kaynak kodun kendisi de kontrol edilir — birisi ileride 'sort=True'yı
    'temizlik' diye silerse bu test de, yukarıdaki de kırmızıya döner."""
    kaynak = Path(__file__).resolve().parent.parent / "tools" / "kitap_index.py"
    assert "get_text(sort=True)" in kaynak.read_text(encoding="utf-8")
