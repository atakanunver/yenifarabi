import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { Kart } from './bilesenler/Kart';
import type { PanoVeri } from './tipler';

const veri: PanoVeri = {
  tarih: '2026-11-13', bugun: '2026-11-14', siniflar: [{ id: 1, ad: '9-A' }],
  sinif_tahta: { '1': 5 }, ders_saatleri: [{ no: 1, baslangic: '08:10', bitis: '08:50' }],
  ilk_durum: { tarih: '2026-11-13', tahta_acik: { '9-A': true }, satirlar: [
    { sinif: '9-A', ders_no: 1, durum: 'alindi', yok_isimleri: '[]', izinli_isimleri: '[]' },
  ] },
};

describe('App — ortak kabuk içindeki React ders paneli', () => {
  it('ders ızgarası KPI ve grafiklerden önce gelir', () => {
    const html = renderToStaticMarkup(<App veri={veri} />);
    expect(html.indexOf('<table')).toBeLessThan(html.indexOf('aria-label="Şu an"'));
  });

  it('büyük tarih başlığı yerine yalnız erişilebilir sayfa adı bulunur', () => {
    const html = renderToStaticMarkup(<App veri={veri} />);
    expect(html).toContain('<h1 class="sr-only">Ders ızgarası</h1>');
    expect(html).not.toContain('Bugün ·');
    expect(html).not.toContain('13 Kasım');
  });

  it('kart zemini arka planı daha görünür bırakır', () => {
    const html = renderToStaticMarkup(<Kart baslik="Örnek" ikon="ev" vurgu="#38BDF8">İçerik</Kart>);
    expect(html).toContain('bg-white/[0.04]');
    expect(html).toContain('group-hover:bg-white/[0.08]');
  });

  it('KPI, grafik, halka, gerçek tablo ve ders listesi hazır render olur', () => {
    const html = renderToStaticMarkup(<App veri={veri} />);
    for (const baslik of ['Şu an', 'Katılım', 'Haftalık katılım', 'Dersler', '9-A']) expect(html).toContain(baslik);
    expect(html).toContain('<table');
    expect(html).not.toContain('yükleniyor…');
    expect(html).not.toContain('<nav'); // taban.html tek kabuk; ikinci React menüsü yok
    expect(html).toContain('Şimdi yenile');
  });
});
