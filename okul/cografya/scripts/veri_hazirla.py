import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS = Path('/home/ata/farabi/tahtaatlasfarabi')
BOLGELER = {'Africa': 'Afrika', 'Asia': 'Asya', 'Europe': 'Avrupa',
            'Oceania': 'Okyanusya', 'Polar': 'Kutup'}
ALT_BOLGELER = {
    '': '', 'Polar': 'Kutup', 'Eastern Africa': 'Doğu Afrika',
    'Middle Africa': 'Orta Afrika', 'Northern Africa': 'Kuzey Afrika',
    'Southern Africa': 'Güney Afrika', 'Western Africa': 'Batı Afrika',
    'Caribbean': 'Karayipler', 'Central America': 'Orta Amerika',
    'Northern America': 'Kuzey Amerika', 'South America': 'Güney Amerika',
    'Central Asia': 'Orta Asya', 'Eastern Asia': 'Doğu Asya',
    'South-Eastern Asia': 'Güneydoğu Asya', 'Southern Asia': 'Güney Asya',
    'Western Asia': 'Batı Asya', 'Eastern Europe': 'Doğu Avrupa',
    'Northern Europe': 'Kuzey Avrupa', 'Southern Europe': 'Güney Avrupa',
    'Western Europe': 'Batı Avrupa', 'Australia and New Zealand': 'Avustralya ve Yeni Zelanda',
    'Melanesia': 'Melanezya', 'Micronesia': 'Mikronezya', 'Polynesia': 'Polinezya',
}
ALTERNATIFLER = {'USA': ['ABD', 'Amerika Birleşik Devletleri'],
                 'GBR': ['Birleşik Krallık', 'İngiltere'], 'NLD': ['Hollanda'],
                 'KOR': ['Güney Kore']}
BASKENT_ALTERNATIFLERI = {'USA': ['Washington D.C.']}


def oku(yol):
    return json.loads(yol.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cikti', type=Path, default=ROOT / 'static/res/data')
    args = parser.parse_args()
    ulkeler = oku(ROOT / 'ham/kaynak/countryInfo.json')
    takma = oku(ROOT / 'ham/kaynak/countryAliases.json')
    duzeltmeler = oku(ROOT / 'ham/duzeltmeler.json')
    world = oku(ATLAS / 'data/source/world.json')
    adlar = {}
    for feature in world['features']:
        p = feature['properties']
        kod = p['ISO_A3'] if p['ISO_A3'] != '-99' else p['ADM0_A3']
        if p.get('NAME_TR'):
            adlar[kod] = p['NAME_TR']
    baskent_adlari = oku(ATLAS / 'data/source/capitals-tr.json')
    katalog = oku(ATLAS / 'public/data/catalog.json')
    baskentler = {}
    for feature in katalog['features']:
        kimlik = str(feature.get('id', ''))
        p = feature['properties']
        ne_id = kimlik.removeprefix('CAPITAL-')
        if kimlik.startswith('CAPITAL-') and ne_id in baskent_adlari and p.get('countryId'):
            baskentler[p['countryId'].removeprefix('COUNTRY-')] = baskent_adlari[ne_id]
    for kod, ulke in ulkeler.items():
        ingilizce_ad = ulke['name']
        ingilizce_baskent = ulke.get('capital', '')
        ulke['name'] = adlar.get(kod, ulke['name'])
        if kod in baskentler and ulke.get('capital'):
            ulke['capital'] = baskentler[kod]
        region, subregion = ulke['region'], ulke['subregion']
        ulke['region'] = ('Güney Amerika' if subregion == 'South America' else 'Kuzey Amerika') if region == 'Americas' else BOLGELER[region]
        ulke['subregion'] = ALT_BOLGELER[subregion]
        ulke.update(duzeltmeler.get(kod, {}))
        ulke['capitalAliases'] = []
        for ad in [ingilizce_baskent] + BASKENT_ALTERNATIFLERI.get(kod, []):
            if ad and ad.casefold() != ulke.get('capital', '').casefold() and ad.casefold() not in {
                a.casefold() for a in ulke['capitalAliases']
            }:
                ulke['capitalAliases'].append(ad)
        mevcut = takma.setdefault(kod, [])
        gorulen = {girdi[0].casefold() for girdi in mevcut}
        for ad, etiket in [(ingilizce_ad, 'ingilizce ad')] + [
            (ad, 'türkçe alternatif') for ad in ALTERNATIFLER.get(kod, [])
        ]:
            if ad and ad.casefold() not in gorulen:
                mevcut.append([ad, etiket])
                gorulen.add(ad.casefold())
    args.cikti.mkdir(parents=True, exist_ok=True)
    for dosya, veri in [('countryInfo.json', ulkeler), ('countryAliases.json', takma)]:
        with (args.cikti / dosya).open('w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


if __name__ == '__main__':
    main()
