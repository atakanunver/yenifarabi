import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DersIzgarasi } from './DersIzgarasi';
import type { Satir } from '../tipler';

const saatler = Array.from({ length: 8 }, (_, i) => ({ no: i + 1, baslangic: '08:00', bitis: '08:40' }));
const satir = (sinif: string, durum: string, yok: string[] = [], izinli: string[] = []): Satir => ({
  sinif, ders_no: 1, durum, yok_isimleri: JSON.stringify(yok), izinli_isimleri: JSON.stringify(izinli),
});

function render(satirlar: Satir[], sinifTahta: Record<string, number> = { '2': 10 }) {
  return renderToStaticMarkup(<DersIzgarasi siniflar={[{ id: 1, ad: '9-A' }, { id: 2, ad: '9-B' }]}
    saatler={saatler} satirlar={satirlar} sinifTahta={sinifTahta} tahtaAcik={{ '9-B': true }}
    aktifDersNo={1} onBaslat={vi.fn()} />);
}

describe('DersIzgarasi', () => {
  it('sorunlu sınıfı üste alır, tahtayı ve etkin dersi gösterir', () => {
    const html = render([satir('9-B', 'alinmadi')]);
    expect(html.indexOf('9-B')).toBeLessThan(html.indexOf('9-A'));
    expect(html).toContain('Tahta açık');
    expect(html).toContain('şimdi');
    expect(html).toContain('8. ders');
    expect(html).toContain('role="button"');
    expect(html).toContain('tabindex="0"');
    expect(html).toContain('overflow-x-auto');
  });

  it('atanmamış tahtada başlatma sunmaz; boş kayıt tam değildir', () => {
    const html = render([satir('9-B', 'alinmadi')], {});
    expect(html).not.toContain('role="button"');
    expect(render([])).not.toContain('>Tam<');
  });

  it('isimleri güvenli gösterir, izinliyi tam saymaz ve bilinmeyen durumu gösterir', () => {
    const html = render([satir('9-A', 'alindi', ['<b>Ad</b>'], ['İsim']), satir('9-B', 'yeni_durum')]);
    expect(html).toContain('&lt;b&gt;Ad&lt;/b&gt;');
    expect(html).toContain('İzinli: İsim');
    expect(html).toContain('yeni_durum');
    expect(html).not.toContain('>Tam<');
  });
});
