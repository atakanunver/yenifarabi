import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ATLAS = Path('/home/ata/farabi/tahtaatlasfarabi')


@pytest.fixture
def uretilen(tmp_path):
    gerekli = ['data/source/world.json', 'data/source/capitals-tr.json', 'public/data/catalog.json']
    if not all((ATLAS / yol).is_file() for yol in gerekli):
        pytest.skip('Atlas kaynakları bulunamadı')
    komut = [sys.executable, str(ROOT / 'cografya/scripts/veri_hazirla.py'), '--cikti', str(tmp_path)]
    subprocess.run(komut, check=True)
    return tmp_path, komut


def test_anahtar_kumesi(uretilen):
    dizin, _ = uretilen
    info = json.loads((dizin / 'countryInfo.json').read_text(encoding='utf-8'))
    kaynak = json.loads((ROOT / 'cografya/ham/kaynak/countryInfo.json').read_text(encoding='utf-8'))
    assert set(info) == set(kaynak)
    assert all(ulke['name'] for ulke in info.values())


def test_turkce_baskentler(uretilen):
    dizin, _ = uretilen
    info = json.loads((dizin / 'countryInfo.json').read_text(encoding='utf-8'))
    assert info['PAK']['capital'] == 'İslamabad'
    assert info['TKM']['capital'] == 'Aşkabat'
    assert info['MKD']['capital'] == 'Üsküp'
    assert info['TUR']['name'] == 'Türkiye'
    assert info['TUR']['capital'] == 'Ankara'


def test_kitalar(uretilen):
    dizin, _ = uretilen
    info = json.loads((dizin / 'countryInfo.json').read_text(encoding='utf-8'))
    assert {ulke['region'] for ulke in info.values()} <= {
        'Afrika', 'Asya', 'Avrupa', 'Kuzey Amerika', 'Güney Amerika', 'Okyanusya', 'Kutup'}


def test_takma_adlar(uretilen):
    dizin, _ = uretilen
    aliases = json.loads((dizin / 'countryAliases.json').read_text(encoding='utf-8'))
    info = json.loads((dizin / 'countryInfo.json').read_text(encoding='utf-8'))
    kaynak = json.loads((ROOT / 'cografya/ham/kaynak/countryInfo.json').read_text(encoding='utf-8'))
    kaynak_aliases = json.loads(
        (ROOT / 'cografya/ham/kaynak/countryAliases.json').read_text(encoding='utf-8'))
    assert 'ABD' in [ad for ad, _ in aliases['USA']]
    assert {'United Kingdom', 'İngiltere'} <= {ad for ad, _ in aliases['GBR']}
    assert 'Islamabad' in info['PAK']['capitalAliases']
    assert all(isinstance(ulke['capitalAliases'], list) for ulke in info.values())
    baskentler = {ulke.get('capital', '').casefold()
                  for ulke in [*info.values(), *kaynak.values()] if ulke.get('capital')}
    for kod, girdiler in aliases.items():
        for ad, etiket in girdiler:
            assert etiket != 'alternatif ad'
            # Bazı ülke adları kendi başkentiyle aynıdır; kaynak girdileri de korunur.
            assert (ad.casefold() not in baskentler or ad == kaynak[kod]['name']
                    or [ad, etiket] in kaynak_aliases.get(kod, []))


def test_belirleyicilik(uretilen):
    dizin, komut = uretilen
    yollar = [dizin / 'countryInfo.json', dizin / 'countryAliases.json']
    ilk = [yol.read_bytes() for yol in yollar]
    subprocess.run(komut, check=True)
    assert ilk == [yol.read_bytes() for yol in yollar]
