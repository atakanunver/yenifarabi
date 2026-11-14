import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { durumGetir, tahtaBaslat, yenile } from './api';

const yanit = (status: number, govde: unknown = {}) =>
  ({ ok: status >= 200 && status < 300, status, json: async () => govde }) as Response;

describe('api — Review Focus 2: oturum düşünce /giris', () => {
  const assign = vi.fn();
  beforeEach(() => {
    vi.stubGlobal('location', { assign });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    assign.mockReset();
  });

  it('401 → location.assign("/giris"), hata fırlatır', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => yanit(401)));
    await expect(durumGetir('2026-11-13')).rejects.toThrow();
    expect(assign).toHaveBeenCalledWith('/giris');
  });

  it('durumGetir doğru ucu çağırır', async () => {
    const f = vi.fn(async () => yanit(200, { tarih: '2026-11-13', satirlar: [], tahta_acik: {} }));
    vi.stubGlobal('fetch', f);
    const d = await durumGetir('2026-11-13');
    expect(f).toHaveBeenCalledWith('/api/durum?tarih=2026-11-13', expect.anything());
    expect(d.satirlar).toEqual([]);
  });

  it('tahtaBaslat 502 → {basarili:false}, fırlatmaz', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => yanit(502, { basarili: false, detay: 'ssh' })));
    expect(await tahtaBaslat(5)).toEqual({ basarili: false, detay: 'ssh' });
  });

  it('yenile ağ hatasında {basarili:false}', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('ağ'); }));
    const r = await yenile('2026-11-13');
    expect(r.basarili).toBe(false);
  });
});
