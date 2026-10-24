"""
Araç kaydı — bildirim ve dağıtım tek kaynaktan gelmeli.

Bu testler eskiden CLAUDE.md'de bir `grep` tek satırıyla elle yapılan
kontrolün yerini alır.
"""

import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from actions import kayit                      # noqa: E402


def test_bildirim_sayisi_kayitla_ayni():
    assert len(kayit.bildirimler()) == len(kayit.ARACLAR)


def test_bildirimler_gemini_semasina_uyar():
    for b in kayit.bildirimler():
        assert b["name"] and b["description"]
        assert b["parameters"]["type"] == "OBJECT"
        for zorunlu in b["parameters"].get("required", []):
            assert zorunlu in b["parameters"]["properties"], \
                f"{b['name']}: required alan properties içinde yok: {zorunlu}"


def test_dagitim_dallari_kayitla_ortusuyor():
    """main.py içindeki `name == "..."` dalları ile kayıt aynı olmalı."""
    kaynak = (KOK / "main.py").read_text(encoding="utf-8")
    dagitim = set(re.findall(r'name == "(\w+)"', kaynak))
    assert dagitim == set(kayit.adlar())


@pytest.mark.parametrize("arac", kayit.ARACLAR, ids=lambda a: a.ad)
def test_agir_araclarin_zaman_asimi_var(arac):
    """
    İş parçacığında çalışan her aracın zaman aşımı OLMAK ZORUNDA.

    Zaman aşımı yokken ölçülen 55,4 saniyelik bir çağrı, alım döngüsünün
    içinde await edildiği için bütün oturumu kilitliyordu.
    """
    if arac.calisma in ("isci", "arkaplan"):
        # "isci": zaman_asimi `_isci`'nin `asyncio.wait_for`'ı tarafından
        # uygulanır. "arkaplan" (2026-09-04, gorsel_uret): ÇAĞRI
        # beklenmediği için `_isci` devrede değil, ama aracın kendi iç
        # çağrısı hâlâ bir üst sınıra ihtiyaç duyar — yoksa yanıt vermeyen
        # bir sağlayıcı çağrısı iş parçacığında süresiz asılı kalır.
        assert arac.zaman_asimi and arac.zaman_asimi > 0
    else:
        # satirici (anında) akışında zaman aşımı uygulanmaz; bunu açıkça
        # belirtmek gerekir.
        assert arac.zaman_asimi is None


@pytest.mark.parametrize("arac", kayit.ARACLAR, ids=lambda a: a.ad)
def test_her_aracin_izni_ve_maliyet_sinifi_var(arac):
    assert arac.izin
    assert arac.maliyet in ("yerel", "dusuk", "yuksek")


def test_kip_kisiti_sorgulanabilir():
    assert kayit.kipte_acik("ders_icerigi", "ogretmenli")
    assert kayit.kipte_acik("ders_icerigi", "ogretmensiz")


def test_shutdown_farabi_aciklamasi_surec_kapaniyor_demiyor():
    """2026-09-01: shutdown_farabi artık süreci öldürmüyor (bkz. _DersBitti)
    — yalnızca dersi bitirip DERSİ BAŞLAT öncesi bekleme durumuna dönüyor.
    Modelin yanlış bir "kapanıyor"/"asistan tamamen kapanıyor" iddiasında
    bulunması, CLAUDE.md'nin web_ac(hedef='kapat') için belgelediği aynı
    sınıftan bir hataydı — açıklama metni bunu artık söylememeli."""
    arac = kayit._HARITA["shutdown_farabi"]
    assert "closes the assistant completely" not in arac.aciklama


def test_yoklama_al_kayitli_ve_normal_derste_acik():
    assert "yoklama_al" in kayit.adlar()
    assert kayit.kipte_acik("yoklama_al", "ogretmenli")
    assert kayit.kipte_acik("yoklama_al", "ogretmensiz")
    assert kayit.kipte_acik("yoklama_al", "talimat")  # 2026-10-24 sade mod: "yoklamayı aç" talimat modunda da açık


SADE_HARIC = ("talimat_modundan_cik", "shutdown_farabi")
SADE_TALIMAT_ARACLARI = {
    "web_ac", "uygulama_ac", "dosya_ac", "pencere_kapat", "pdf_sayfa", "kitap_sorusu", "yks_sorulari", "geogebra",
    "ekran_goruntusu_al", "ekrandaki_soruyu_oku", "icerigi_kapat", "youtube_video", "web_search", "eba", "yoklama_al",
}


def test_sade_modda_talimat_arac_kumesi():
    """2026-10-24 sade mod: talimat kipinde TAM bu 15 araç (çıkış/ders bitirme araçları listeden çıkar)."""
    adlar = {d["name"] for d in kayit.bildirimler("talimat", haric=SADE_HARIC)}
    assert adlar == SADE_TALIMAT_ARACLARI


def test_haric_yalniz_listeden_cikarir_normal_kip_ve_sade_olmayan_talimat_etkilenmez():
    tum = {d["name"] for d in kayit.bildirimler("talimat")}
    assert "talimat_modundan_cik" in tum  # sade olmayan talimat: çıkış aracı duruyor
    assert tum - {d["name"] for d in kayit.bildirimler("talimat", haric=SADE_HARIC)} == {"talimat_modundan_cik"}
    assert "shutdown_farabi" in {d["name"] for d in kayit.bildirimler("ogretmenli")}  # ders kipleri değişmedi
    assert {d["name"] for d in kayit.bildirimler("ogretmenli")} == {d["name"] for d in kayit.bildirimler("ogretmenli", haric=())}


def test_icerigi_kapat_yalniz_talimat_kipinde_ve_aciklamasi_dis_pencere_demiyor():
    assert kayit.kipte_acik("icerigi_kapat", "talimat")
    assert not kayit.kipte_acik("icerigi_kapat", "ogretmenli") and not kayit.kipte_acik("icerigi_kapat", "ogretmensiz")
    arac = kayit.bul("icerigi_kapat")
    assert arac.parametreler["required"] == [] and "pencere_kapat" in arac.aciklama  # dış pencere için pencere_kapat'a yönlendirir


@pytest.mark.parametrize("ad", ["youtube_video", "web_search", "eba", "yoklama_al"])
def test_sade_mod_ek_araclari_hem_derste_hem_talimatta_acik(ad):
    assert kayit.kipte_acik(ad, "talimat") and kayit.kipte_acik(ad, "ogretmenli") and kayit.kipte_acik(ad, "ogretmensiz")
