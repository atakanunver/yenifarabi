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

// ---- Cam ders ızgarası (2026-11-14): sıralama, halkalar, ders ilerlemesi ----
import { sorunluUste, halkaOranlari, dersIlerlemesi, istanbulSaati } from './turet';

describe('dürüst ders listesi ve saat', () => {
  it('verisiz gün veya ders olmayan gün tamamlandı listesi üretmez', () => {
    const simdi = new Date(2026, 10, 14, 16);
    expect(dersListesi(SAATLER, [], simdi, true, 7)).toEqual([]);
    expect(dersListesi(SAATLER, [{ ...SATIR_TABAN, durum: 'ders_yok_o_gun' }], simdi, true, 7)).toEqual([]);
  });
  it('tarayıcının saat diliminden bağımsız İstanbul saatini üretir', () => {
    const t = istanbulSaati(new Date('2026-11-13T06:15:00Z'));
    expect([t.getHours(), t.getMinutes()]).toEqual([9, 15]);
  });
});

describe('sorunluUste — pano.html ile aynı sıra', () => {
  const siniflar = [{ id: 1, ad: '9-A' }, { id: 2, ad: '9-B' }, { id: 3, ad: '10-A' }, { id: 4, ad: '11-A' }];
  it('alınmadı / ulaşılamaz sınıflar üste, kendi aralarında özgün sırada', () => {
    const satirlar = [
      { ...SATIR_TABAN, sinif: '10-A', durum: 'tahta_ulasilamaz' },
      { ...SATIR_TABAN, sinif: '9-B', durum: 'alinmadi' },
      { ...SATIR_TABAN, sinif: '9-A', durum: 'alindi' },
    ];
    expect(sorunluUste(siniflar, satirlar).map((s) => s.ad)).toEqual(['9-B', '10-A', '9-A', '11-A']);
  });
  it('sorun yoksa sıra değişmez', () => {
    expect(sorunluUste(siniflar, []).map((s) => s.ad)).toEqual(['9-A', '9-B', '10-A', '11-A']);
  });
});

describe('halkaOranlari — payda 0 iken null (NaN halka yok)', () => {
  it('boş gün', () => {
    expect(halkaOranlari([], {})).toEqual({ alinan: null, tam: null, acik: null });
  });
  it('oranlar', () => {
    const satirlar = [
      { ...SATIR_TABAN, durum: 'alindi' },
      { ...SATIR_TABAN, durum: 'alindi', yok_isimleri: '["Ali"]' },
      { ...SATIR_TABAN, durum: 'alinmadi' },
      { ...SATIR_TABAN, durum: 'henuz_baslamadi' },
    ];
    const h = halkaOranlari(satirlar, { '9-A': true, '9-B': false, '10-A': true, '11-A': true });
    expect(h.alinan).toBeCloseTo(2 / 3);
    expect(h.tam).toBeCloseTo(1 / 2);
    expect(h.acik).toBeCloseTo(3 / 4);
  });
});

describe('dersIlerlemesi', () => {
  it('ders ortasında 0.5, ders dışında null', () => {
    const s = { no: 1, baslangic: '08:10', bitis: '08:50' };
    expect(dersIlerlemesi(s, new Date(2026, 10, 13, 8, 30))).toBeCloseTo(0.5);
    expect(dersIlerlemesi(null, new Date(2026, 10, 13, 8, 30))).toBeNull();
  });
});
