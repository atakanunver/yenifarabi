"""Tahtaya dosya gönderimi: imza, yetki ve kuyruk."""

import zipfile
from datetime import timedelta

import pytest
import tahta_dosya
from ayarlar import AYAR
from test_web_belge_sinav import giris, istemci, lan_istemci, veli_giris  # noqa: F401

PDF = b'%PDF-1.4\n' + b'x' * 100


def _ogretmen(conn, ornek):
    return conn.execute('SELECT * FROM kullanici WHERE id=?', (ornek['ogretmen'],)).fetchone()


def test_imza_ve_yedek(conn, ornek, tmp_path, saat):
    yol = tmp_path / 'girdi'
    yol.write_bytes(PDF)
    k = _ogretmen(conn, ornek)
    ids = tahta_dosya.kaydet(conn, k, yol, 'Şıklar.pdf', ['9-A', '9-B'], {'9-A', '9-B'})
    assert len(ids) == 2
    satirlar = conn.execute('SELECT * FROM tahta_dosya ORDER BY id').fetchall()
    assert satirlar[0]['yedek_yol'] == satirlar[1]['yedek_yol']
    assert satirlar[0]['dosya_adi'] == 'Siklar.pdf'
    assert 'Hoca_Hanim_2026-10-12_1000_Siklar.pdf' in satirlar[0]['yedek_yol']
    assert AYAR.tahta_dosya_yedek.joinpath('Hoca_Hanim_2026-10-12_1000_Siklar.pdf').read_bytes() == PDF
    tahta_dosya.kaydet(conn, k, yol, 'Şıklar.pdf', ['9-A'], {'9-A'})
    assert (AYAR.tahta_dosya_yedek / 'Hoca_Hanim_2026-10-12_1000_Siklar_2.pdf').exists()
    yol.write_bytes(b'MZ' + b'x' * 100)
    with pytest.raises(tahta_dosya.DosyaHatasi):
        tahta_dosya.kaydet(conn, k, yol, 'sahte.pdf', ['9-A'], {'9-A'})
    with yol.open('wb') as f:
        f.truncate(tahta_dosya.AZAMI + 1)
    with pytest.raises(tahta_dosya.DosyaHatasi, match='95 MB'):
        tahta_dosya.kaydet(conn, k, yol, 'buyuk.pdf', ['9-A'], {'9-A'})


@pytest.mark.parametrize('parca,tur', [('wordprocessingml.document.main+xml', 'docx'),
                                       ('presentationml.presentation.main+xml', 'pptx'),
                                       ('spreadsheetml.sheet.main+xml', 'xlsx')])
def test_ofis_zip_imzasi(tmp_path, parca, tur):
    yol = tmp_path / 'ofis.zip'
    with zipfile.ZipFile(yol, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types>' + parca + '</Types>')
    assert tahta_dosya.tur_bul(yol) == tur


def test_kuyruk_ve_sure(conn, ornek, tmp_path, saat):
    yol = tmp_path / 'f'; yol.write_bytes(PDF)
    ids = tahta_dosya.kaydet(conn, _ogretmen(conn, ornek), yol, 'f.pdf', ['9-A', '9-B'], {'9-A', '9-B'})
    assert [r['id'] for r in tahta_dosya.bekleyenler(conn)] == ids
    assert tahta_dosya.sonuc(conn, ids[0], 'gonderildi')
    assert not tahta_dosya.sonuc(conn, ids[0], 'gonderildi')
    saat['an'] += timedelta(hours=24, seconds=1)
    assert tahta_dosya.bekleyenler(conn) == []
    assert conn.execute('SELECT durum FROM tahta_dosya WHERE id=?', (ids[1],)).fetchone()[0] == 'suresi_doldu'


def test_web_yetki_csrf_ve_akis(istemci, conn, ornek, monkeypatch):  # noqa: F811
    import rotalar.tahta_dosya as rota
    monkeypatch.setattr(rota, '_tahtalar', lambda: [{'ad': '9-A', 'sinif': '9-A'}, {'ad': '9-B', 'sinif': '9-B'}])
    giris(istemci, '101', 'ali-sifre')
    assert istemci.get('/ogretmen/tahtaya-gonder').status_code == 404
    giris(istemci, 'hoca', 'hoca-sifre')
    assert 'en fazla 95 MB' in istemci.get('/ogretmen/tahtaya-gonder').text
    assert istemci.post('/ogretmen/tahtaya-gonder', files={'dosya': ('a.pdf', PDF)}, data={'tahta': '9-A'}).status_code == 400
    csrf = giris(istemci, 'hoca', 'hoca-sifre')
    assert istemci.post('/ogretmen/tahtaya-gonder', data={'csrf': csrf, 'tahta': '9-A'},
                        files={'dosya': ('sahte.pdf', b'MZ' + b'x' * 20)}).status_code == 422
    r = istemci.post('/ogretmen/tahtaya-gonder', data={'csrf': csrf, 'tahta': ['9-A', '9-B']},
                     files={'dosya': ('ders.pdf', PDF)}, follow_redirects=False)
    assert r.status_code == 303, r.text[r.text.find('<p class="hata" role="alert"'):r.text.find('<p class="hata" role="alert"')+200]
    assert conn.execute('SELECT COUNT(*) FROM tahta_dosya').fetchone()[0] == 2
    assert 'Sırada' in istemci.get('/ogretmen/tahtaya-gonder').text
    giris(istemci, 'mudur', 'mudur-sifre')
    assert istemci.get('/ogretmen/tahtaya-gonder').status_code == 200
    veli_giris(istemci, conn, ornek['veli1'])
    assert istemci.get('/ogretmen/tahtaya-gonder').status_code == 404


def test_lan_anahtar_ve_sonuc(lan_istemci, conn, ornek, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(AYAR, 'tahta_dosya_anahtar', 'test-anahtari')
    yol = tmp_path / 'f'; yol.write_bytes(PDF)
    id_ = tahta_dosya.kaydet(conn, _ogretmen(conn, ornek), yol, 'f.pdf', ['9-A'], {'9-A'})[0]
    api = '/api/tahta-dosya'
    assert lan_istemci.get(api + '/bekleyen').status_code == 404
    h = {'X-Tahta-Dosya-Key': 'test-anahtari'}
    assert lan_istemci.get(api + '/bekleyen', headers={'X-Tahta-Dosya-Key': 'yanlis'}).status_code == 404
    assert lan_istemci.get(api + '/bekleyen', headers={**h, 'Cf-Ray': 'x'}).status_code == 404
    assert [x['id'] for x in lan_istemci.get(api + '/bekleyen', headers=h).json()['dosyalar']] == [id_]
    assert lan_istemci.get(f'{api}/{id_}/dosya', headers=h).content == PDF
    assert lan_istemci.post(f'{api}/{id_}/sonuc', headers=h, json={'durum': 'gonderildi'}).status_code == 200
    assert lan_istemci.get(api + '/bekleyen', headers=h).json()['dosyalar'] == []
