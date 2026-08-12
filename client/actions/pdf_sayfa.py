"""
actions/pdf_sayfa.py — Kitabın belirli bir SAYFA NUMARASINI ekrana görüntü
olarak yansıtır (PyMuPDF/fitz ile rasterize edilir — PDF bütünlüğü korunur,
sayfa metne dönüştürülmez, şekil/tablo/formül olduğu gibi görünür).

`ders_icerigi` ile farkı: ders_icerigi bir KONUYU anlatmak için bölüm/tema
eşleştirip metin getirir (çok sayfa, düz metin). Bu araç öğretmenin/
öğrencinin somut bir SAYFA NUMARASI istediği durum için — "9. sayfayı
göster/yansıt". Konu/tema eşleştirmesi YAPILMAZ, doğrudan sayfa numarasına
gidilir; iskelet, `kitap_sorusu.py`'nin `_kitap_id_bul`'uyla aynı disiplinde
`ders` zorunlu — boş bırakılırsa aynı sınıf düzeyindeki YANLIŞ kitaptan
sayfa gösterme riski olurdu (bkz. kitap_sorusu.py'deki 2026-08-11 bulgusu).

Neden görüntü, metin değil: sayfadaki şekil/tablo/formül PDF'te olduğu gibi
kalmalı — metne çevirmek (tools/kitap_metin.py'nin yaptığı gibi) bunları
kaybeder ya da bozar. PyMuPDF zaten kurulu bir bağımlılık (tools/kitap_metin.py,
kitap_index.py) — yeni bağımlılık eklenmedi.

`render_pdf_sayfa()` bilerek genel/paylaşılabilir yazıldı: `yks_sorulari.py`
(2026-08-12) YKS PDF'lerinden bir soru sayfasını göstermek için aynı
fonksiyonu import eder — render mantığı iki yerde kopyalanmasın diye.
"""

from pathlib import Path

import fitz  # PyMuPDF — requirements.txt'te zaten var

from actions.ders_icerigi import KITAP_PATH, _json_oku, _ders_eslesir

BASE_DIR = Path(__file__).resolve().parent.parent
ONBELLEK_DIR = BASE_DIR / "icerik" / "onbellek" / "pdf_sayfa"

# Board'da okunabilir çözünürlük için zoom faktörü — A4 sayfa ~595x842pt,
# 2x zoom ~1190x1684px, bir akıllı tahtada net okunur.
ZOOM = 2.0


def render_pdf_sayfa(pdf_yolu: Path, sayfa: int, onbellek_dir: Path) -> Path:
    """Bir PDF'in TEK sayfasını PNG'ye render eder (varsa önbellekten döner).

    Hatada Exception fırlatır (dosya yok, sayfa aralık dışı, fitz hatası) —
    çağıran karşılar ve kendi sınıf-dostu mesajını üretir; burada sınıfa
    okunacak bir metin ÜRETİLMEZ, bu fonksiyon salt render katmanıdır.
    """
    onbellek_dir.mkdir(parents=True, exist_ok=True)
    onbellek_yolu = onbellek_dir / f"{pdf_yolu.stem}_s{sayfa}.png"
    if onbellek_yolu.exists():
        return onbellek_yolu
    with fitz.open(str(pdf_yolu)) as pdf:
        if sayfa > len(pdf):
            raise ValueError(f"{pdf_yolu.name} yalnızca {len(pdf)} sayfa — {sayfa}. sayfa yok.")
        sayfa_nesnesi = pdf[sayfa - 1]  # fitz 0-indeksli
        pix = sayfa_nesnesi.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        pix.save(str(onbellek_yolu))
    return onbellek_yolu


def _kitap_bul(ders: str | None, sinif: str | None) -> dict | None:
    """`ders` verilmeden EŞLEŞME YAPILMAZ — aynı sınıf düzeyindeki İLK kitabı
    seçip yanlış kitaptan sayfa göstermek, kitap_sorusu.py'de bulunan
    hatanın aynısı olurdu (bkz. modül dokümanı)."""
    if not ders:
        return None
    kitaplar = _json_oku(KITAP_PATH)
    if not kitaplar:
        return None
    for k in kitaplar.get("kitaplar", []):
        if sinif and k.get("sinif") is not None and str(k["sinif"]) != str(sinif).strip():
            continue
        if not _ders_eslesir(ders, k.get("ders", "")):
            continue
        return k
    return None


def pdf_sayfa(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    try:
        sayfa = int(p.get("sayfa"))
    except (TypeError, ValueError):
        return "Sayfa numarası belirtilmedi ya da geçersiz. 'sayfa' parametresiyle bir tam sayı ver."
    if sayfa < 1:
        return "Sayfa numarası 1'den küçük olamaz."

    ders = (p.get("ders") or "").strip() or None
    sinif = (p.get("sinif") or "").strip() or None
    if not sinif:
        try:
            from core import tahta
            sinif = tahta.sinif_duzeyi() or None
        except Exception:
            pass

    if not ders:
        log("[PDF Sayfa] ders verilmedi, eşleme yapılmadı")
        return "Ders belirtilmedi. 'ders' parametresiyle ver — aksi hâlde yanlış kitaptan sayfa gösterme riski var."

    kitap = _kitap_bul(ders, sinif)
    if not kitap:
        log(f"[PDF Sayfa] eşleşen kitap bulunamadı (ders={ders!r}, sinif={sinif!r})")
        return "Bu ders/sınıf için indekslenmiş kitap bulunamadı."

    pdf_yolu = Path(kitap["yol"])
    if not pdf_yolu.is_absolute():
        pdf_yolu = BASE_DIR / pdf_yolu
    if not pdf_yolu.exists():
        return f"Kitap dosyası bulunamadı: {pdf_yolu.name}."

    try:
        onbellek_yolu = render_pdf_sayfa(pdf_yolu, sayfa, ONBELLEK_DIR)
    except ValueError as e:
        return str(e)
    except Exception as e:
        log(f"[PDF Sayfa] render hatası: {type(e).__name__}: {e}")
        return f"Sayfa render edilemedi ({type(e).__name__}: {e})."

    log(f"[PDF Sayfa] {kitap['dosya']} · s.{sayfa} gösteriliyor")
    if player is not None and hasattr(player, "show_image"):
        player.show_image(f"{kitap.get('ders','KİTAP').upper()} — s.{sayfa}", str(onbellek_yolu))

    return f"{kitap.get('ders','Kitap')} kitabının {sayfa}. sayfası ekranda gösteriliyor."
