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
    if arac.calisma == "isci":
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
