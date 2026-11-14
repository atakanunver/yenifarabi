import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import type { PanoVeri } from './tipler';

const veri: PanoVeri = {
  tarih: '2026-11-13', bugun: '2026-11-14', siniflar: [{ id: 1, ad: '9-A' }],
  sinif_tahta: { '1': 5 }, ders_saatleri: [{ no: 1, baslangic: '08:10', bitis: '08:50' }],
  ilk_durum: { tarih: '2026-11-13', tahta_acik: { '9-A': true }, satirlar: [
    { sinif: '9-A', ders_no: 1, durum: 'alindi', yok_isimleri: '[]', izinli_isimleri: '[]' },
  ] },
};

describe('App — ortak kabuk içindeki React ders paneli', () => {
  it('KPI, grafik, halka, gerçek tablo ve ders listesi hazır render olur', () => {
    const html = renderToStaticMarkup(<App veri={veri} />);
    for (const baslik of ['Şu an', 'Katılım', 'Haftalık katılım', 'Dersler', '9-A']) expect(html).toContain(baslik);
    expect(html).toContain('<table');
    expect(html).not.toContain('yükleniyor…');
    expect(html).not.toContain('<nav'); // taban.html tek kabuk; ikinci React menüsü yok
    expect(html).toContain('Şimdi yenile');
  });
});
