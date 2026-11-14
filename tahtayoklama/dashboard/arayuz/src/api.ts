import type { DurumYaniti } from './tipler';

// Veri uçları pano.html ile aynı (/api/durum, /api/yenile, /api/tahta/{id}/baslat, /api/acil/durum).
// Oturum düşerse (401) giriş sayfasına gidilir; sessiz boş ekran kalmaz.
async function istek(url: string, secenek: RequestInit = {}): Promise<Response> {
  const r = await fetch(url, { credentials: 'same-origin', ...secenek });
  if (r.status === 401) {
    location.assign('/giris');
    throw new Error('oturum yok');
  }
  return r;
}

export async function durumGetir(tarih: string): Promise<DurumYaniti> {
  const r = await istek(`/api/durum?tarih=${tarih}`, {});
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

export interface EylemSonucu {
  basarili: boolean;
  durum?: string;
  detay?: string;
}

async function eylem(url: string): Promise<EylemSonucu> {
  try {
    const r = await istek(url, { method: 'POST' });
    const j = await r.json().catch(() => ({}));
    return r.ok ? { basarili: !!j.basarili, ...j } : { basarili: false, detay: j.detay || String(r.status) };
  } catch (e) {
    return { basarili: false, detay: e instanceof Error ? e.message : 'bağlantı hatası' };
  }
}

export const yenile = (tarih: string) => eylem(`/api/yenile?tarih=${tarih}`);
export const tahtaBaslat = (tahtaId: number) => eylem(`/api/tahta/${tahtaId}/baslat`);

export interface AcilDurum {
  aktif: { tur: string; tatbikat?: boolean; zaman?: string; istemci_ip?: string } | null;
  turler: Record<string, { baslik: string }>;
}

export async function acilDurum(): Promise<AcilDurum | null> {
  try {
    const r = await istek('/api/acil/durum');
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}
