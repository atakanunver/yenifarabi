"""Bilgi Arenası şablonları (Aşama 2): yalnızca render sözleşmesi. Rota/iş kuralı henüz yok."""

from types import SimpleNamespace

import pytest

from deps import TEMPLATES

K = {"id": 1, "rol": "ogrenci", "ad_soyad": "Test", "foto": None, "sifre_degismeli": 0}
SEV = {"no": 3, "xp": 235, "bu_baslangic": 200, "sonraki": 350}
KAZ = [{"kod": "BİY.9.1.1", "metin": "Örnek kazanım", "dogru": 1, "toplam": 2}]


def _render(ad, **ctx):
    ctx.update(k=K, csrf="c", bugun_gun="Sal", request=SimpleNamespace(url=SimpleNamespace(path="/ogrenci/arena")))
    return TEMPLATES.get_template(ad).render(ctx)


def _hub(gorev, **kw):
    return _render(
        "ogrenci/arena.html", seviye=SEV, gorev=gorev, hizli={"kilit": None, "seri": 0},
        son=kw.get("son"), tekrar=kw.get("tekrar"), hafta=None,
    )


@pytest.mark.parametrize(
    "gorev,metin",
    [
        ({"durum": "hazir", "soru_sayisi": 5, "dk": 4}, "Arena'ya Gir"),
        ({"durum": "devam", "soru_sayisi": 5, "cevaplanan": 2, "tur_id": 1}, "Devam et"),
        ({"durum": "tamam", "soru_sayisi": 5, "dogru": 4, "xp": 60, "tur_id": 1}, "Bugün tamamlandı"),
        ({"durum": "kilit", "kilit_bit": "10:30"}, "10:30"),
        ({"durum": "yetersiz"}, "yeterli soru bulunamadı"),
        ({"durum": "kaynak_yok"}, "ulaşılamıyor"),
    ],
)
def test_hub_her_durumu_render_eder(gorev, metin):
    assert metin in _hub(gorev)


def test_hub_veri_yokken_uydurma_gostermez():
    h = _hub({"durum": "hazir", "soru_sayisi": 5, "dk": 4})
    assert "Henüz tamamlanmış görev yok" in h and "Henüz tekrar önerisi yok" in h
    assert "kesin bir değerlendirme değildir" not in h  # kazanım yokken uyarı da yok


def test_hub_xp_cubugu_erisilebilir_ve_dogru_yuzde():
    h = _hub({"durum": "hazir", "soru_sayisi": 5, "dk": 4})
    assert 'role="progressbar"' in h and 'aria-valuenow="23"' in h  # (235-200)/150


def test_soru_ekrani_cevap_vermeden_dogru_sikki_sizdirmaz():
    soru = {"sira": 2, "soru": "S?", "secenekler": ["a", "b", "c", "d"], "konu": "K", "pas_kalan": 1}
    h = _render("ogrenci/arena_soru.html", tur={"id": 1, "soru_sayisi": 5}, soru=soru, kareler=["dogru", "bos", "bos", "bos", "bos"], geri=None)
    assert "doğru cevap" not in h.lower() and "disabled" not in h and h.count('name="sec"') == 4


def test_soru_ekrani_cevap_sonrasi_geri_bildirim_ve_kilit():
    soru = {"sira": 5, "soru": "S?", "secenekler": ["a", "b"], "konu": None}
    geri = {"dogru": False, "dogru_index": 1, "secilen": 0, "sonraki": "/ogrenci/arena/1/sonuc"}
    h = _render("ogrenci/arena_soru.html", tur={"id": 1, "soru_sayisi": 5}, soru=soru, kareler=["dogru"] * 4 + ["yanlis"], geri=geri)
    assert "birlikte gözden geçirelim" in h and "(doğru cevap)" in h and "Sonucu gör" in h and h.count("disabled") == 2


def test_sonuc_ve_ilerleme_render():
    sat = [{"sira": 1, "soru": "S?", "secenekler": ["a", "b"], "dogru_index": 1, "cevap": 0, "konu": None}]
    h = _render("ogrenci/arena_sonuc.html", tur={"dogru": 0, "soru_sayisi": 1, "xp": 0, "ders_ad": "Biyoloji"}, satirlar=sat,
                kazanim_ozet=KAZ, yeni_rozetler=[], seviye_atladi=None, seviye=SEV)
    assert "tahminidir" in h and "(senin cevabın)" in h
    roz = [{"kod": "a", "ad": "R", "aciklama": "x", "kazanildi": False, "tarih": None}]
    i = _render("ogrenci/arena_ilerleme.html", seviye=SEV, gunler=[{"ad": "Sal", "tamam": False, "bugun": True}], hafta=None, rozetler=roz, kazanimlar=None)
    assert "Henüz kazanılmadı" in i and "Henüz yeterli veri yok" in i
