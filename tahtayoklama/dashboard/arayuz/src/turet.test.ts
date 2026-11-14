import { describe, it, expect } from 'vitest';
import {
  hucreDurumu,
  yoklamaOrani,
  dagilim,
  aktifDers,
  dersListesi,
  tiklanabilir,
  haftaGunleri,
} from './turet';
import type { Satir, DersSaati } from './tipler';

const SATIR_TABAN: Satir = {
  sinif: '9-A',
  ders_no: 1,
  durum: 'alindi',
  yok_isimleri: '[]',
  izinli_isimleri: '[]',
};

const SAATLER: DersSaati[] = [
  { no: 1, baslangic: '08:10', bitis: '08:50' },
  { no: 2, baslangic: '09:00', bitis: '09:40' },
  { no: 3, baslangic: '09:50', bitis: '10:30' },
];

describe('yoklamaOrani — Review Focus 1', () => {
  it('boş listede null döner (payda 0, NaN çökmesi yok)', () => {
    expect(yoklamaOrani([])).toBeNull();
  });

  it('yalnız henuz_baslamadi satırlarında null döner', () => {
    const s: Satir[] = [{ ...SATIR_TABAN, durum: 'henuz_baslamadi' }];
    expect(yoklamaOrani(s)).toBeNull();
  });

  it('alindi ve alinmadi oranını doğru hesaplar', () => {
    const s: Satir[] = [
      { ...SATIR_TABAN, durum: 'alindi' },
      { ...SATIR_TABAN, durum: 'alindi' },
      { ...SATIR_TABAN, durum: 'alindi' },
      { ...SATIR_TABAN, durum: 'alinmadi' },
    ];
    expect(yoklamaOrani(s)).toBe(0.75);
  });
});

describe('hucreDurumu — Review Focus 5', () => {
  it('tam: alindi ve yok/izinli boş', () => {
    const h = hucreDurumu(SATIR_TABAN);
    expect(h.tur).toBe('tam');
    expect(h.yok).toEqual([]);
    expect(h.izinli).toEqual([]);
  });

  it('devamsiz: alindi ve yalnız izinli var', () => {
    const h = hucreDurumu({ ...SATIR_TABAN, izinli_isimleri: '["Ayşe"]' });
    expect(h.tur).toBe('devamsiz');
    expect(h.izinli).toEqual(['Ayşe']);
  });

  it('devamsiz: alindi ve devamsız var', () => {
    const h = hucreDurumu({ ...SATIR_TABAN, yok_isimleri: '["Mehmet", "Can"]' });
    expect(h.tur).toBe('devamsiz');
    expect(h.yok).toEqual(['Mehmet', 'Can']);
  });

  it('bozuk JSON boş listeye düşer, çökmez', () => {
    const h = hucreDurumu({ ...SATIR_TABAN, yok_isimleri: 'gecersiz' });
    expect(h.tur).toBe('tam');
    expect(h.yok).toEqual([]);
  });

  it('alinmadi, ulasilamaz ve bos durumları', () => {
    expect(hucreDurumu({ ...SATIR_TABAN, durum: 'alinmadi' }).tur).toBe('alinmadi');
    expect(hucreDurumu({ ...SATIR_TABAN, durum: 'tahta_ulasilamaz' }).tur).toBe('ulasilamaz');
    expect(hucreDurumu({ ...SATIR_TABAN, durum: 'henuz_baslamadi' }).tur).toBe('bos');
    expect(hucreDurumu({ ...SATIR_TABAN, durum: 'ders_yok_o_gun' }).tur).toBe('bos');
  });
});

describe('tiklanabilir — Review Focus 3', () => {
  it('alinmadi ve tahta id varsa true', () => {
    expect(tiklanabilir({ ...SATIR_TABAN, durum: 'alinmadi' }, { '1': 5 }, 1)).toBe(true);
  });

  it('sınıf tahta haritasında yoksa false', () => {
    expect(tiklanabilir({ ...SATIR_TABAN, durum: 'alinmadi' }, {}, 1)).toBe(false);
  });

  it('durum alindi ise false', () => {
    expect(tiklanabilir(SATIR_TABAN, { '1': 5 }, 1)).toBe(false);
  });
});

describe('aktifDers ve dersListesi — Review Focus 4', () => {
  it('bugün değilse aktifDers null, dersListesinde devam yok', () => {
    const simdi = new Date('2026-11-14T09:15:00');
    expect(aktifDers(SAATLER, simdi, false)).toBeNull();

    const satirlar: Satir[] = [
      { ...SATIR_TABAN, ders_no: 1, durum: 'alindi' },
      { ...SATIR_TABAN, ders_no: 2, durum: 'alindi' },
    ];
    const liste = dersListesi(SAATLER, satirlar, simdi, false, 2);
    expect(liste.every((d) => d.durum === 'tamam')).toBe(true);
  });

  it('bugün ise saat aralığındaki ders devam ediyor', () => {
    const simdi = new Date('2026-11-14T09:15:00');
    const a = aktifDers(SAATLER, simdi, true);
    expect(a?.no).toBe(2);

    const satirlar: Satir[] = [
      { ...SATIR_TABAN, ders_no: 1, durum: 'alindi' },
      { ...SATIR_TABAN, ders_no: 2, durum: 'alinmadi' },
    ];
    const liste = dersListesi(SAATLER, satirlar, simdi, true, 2);
    expect(liste.find((d) => d.no === 2)?.durum).toBe('devam');
    expect(liste.find((d) => d.no === 1)?.durum).toBe('tamam');
  });
});

describe('dagilim', () => {
  it('dilim sayılarını doğru gruplar', () => {
    const satirlar: Satir[] = [
      { ...SATIR_TABAN, durum: 'alindi' },
      { ...SATIR_TABAN, durum: 'alindi', yok_isimleri: '["A"]' },
      { ...SATIR_TABAN, durum: 'alinmadi' },
      { ...SATIR_TABAN, durum: 'tahta_ulasilamaz' },
    ];
    expect(dagilim(satirlar)).toEqual({
      tam: 1,
      devamsiz: 1,
      alinmadi: 1,
      ulasilamaz: 1,
    });
  });
});

describe('haftaGunleri', () => {
  it('cumartesi verilince o haftanın Pzt–Cum günlerini döner', () => {
    expect(haftaGunleri('2026-11-14')).toEqual([
      '2026-11-09',
      '2026-11-10',
      '2026-11-11',
      '2026-11-12',
      '2026-11-13',
    ]);
  });
});
