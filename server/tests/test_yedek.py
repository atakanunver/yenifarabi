import importlib.util
import stat
import tarfile
from pathlib import Path

import pytest

_YOL = Path(__file__).resolve().parents[1] / "yedek" / "farabi_yedek.py"
_spec = importlib.util.spec_from_file_location("farabi_yedek", _YOL)
yedek = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yedek)


def _home(tmp_path):
    home = tmp_path / "home"
    for yol, icerik in {
        "farabi/okul/config/gizli.json": "{}",
        "farabi/okul/config/takvim.json": "{}",
        "farabi/tahtayoklama/dashboard/config/kulupler.json": "[]",
        "farabi/tahtayoklama/dashboard/veri/yoklama_pano.db": "x",  # config değil: girmemeli
        ".config/okul-ana/baglanti": "dsn",
        ".pgpass": "pg",
    }.items():
        p = home / yol
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(icerik)
    return home


def test_yapilandirma_kalibina_uyanlar_girer_digerleri_girmez(tmp_path):
    home, hedef = _home(tmp_path), tmp_path / "hedef"
    hedef.mkdir()
    n = yedek.yapilandirma_yedekle(hedef, home)
    with tarfile.open(hedef / "yapilandirma.tar.gz") as t:
        adlar = set(t.getnames())
    assert n == 5
    assert adlar == {
        "farabi/okul/config/gizli.json",
        "farabi/okul/config/takvim.json",
        "farabi/tahtayoklama/dashboard/config/kulupler.json",
        ".config/okul-ana/baglanti",
        ".pgpass",
    }


def test_arsiv_yalniz_sahibi_okuyabilir(tmp_path):
    home, hedef = _home(tmp_path), tmp_path / "hedef"
    hedef.mkdir()
    yedek.yapilandirma_yedekle(hedef, home)
    assert stat.S_IMODE((hedef / "yapilandirma.tar.gz").stat().st_mode) == 0o600


def test_hic_dosya_yoksa_hata_verir_sessizce_bos_yedek_almaz(tmp_path):
    hedef = tmp_path / "hedef"
    hedef.mkdir()
    with pytest.raises(RuntimeError):
        yedek.yapilandirma_yedekle(hedef, tmp_path / "bos-home")


def test_manifest_arsivi_de_kapsar(tmp_path):
    home, hedef = _home(tmp_path), tmp_path / "hedef"
    hedef.mkdir()
    yedek.yapilandirma_yedekle(hedef, home)
    yedek.manifest(hedef)
    assert "yapilandirma.tar.gz" in (hedef / "SHA256SUMS").read_text()
