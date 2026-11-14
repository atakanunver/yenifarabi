import type { Satir, DersSaati, Sinif } from './tipler';

function jsonDizi(ham: string | null | undefined): string[] {
  if (!ham) return [];
  try {
    const d = JSON.parse(ham);
    return Array.isArray(d) ? d.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export type HucreTuru =
  | 'tam'
  | 'devamsiz'
  | 'alinmadi'
  | 'ulasilamaz'
  | 'atanmamis'
  | 'bos';

export interface HucreSonucu {
  tur: HucreTuru;
  yok: string[];
  izinli: string[];
}

export function hucreDurumu(satir: Satir): HucreSonucu {
  const yok = jsonDizi(satir.yok_isimleri);
  const izinli = jsonDizi(satir.izinli_isimleri);

  if (satir.durum === 'alindi') {
    return {
      tur: yok.length || izinli.length ? 'devamsiz' : 'tam',
      yok,
      izinli,
    };
  }
  if (satir.durum === 'alinmadi') return { tur: 'alinmadi', yok, izinli };
  if (satir.durum === 'tahta_ulasilamaz') return { tur: 'ulasilamaz', yok, izinli };
  if (satir.durum === 'tahta_atanmamis') return { tur: 'atanmamis', yok, izinli };
  return { tur: 'bos', yok, izinli };
}

export function yoklamaOrani(satirlar: Satir[]): number | null {
  let alindi = 0;
  let alinmadi = 0;
  for (const s of satirlar) {
    if (s.durum === 'alindi') alindi++;
    else if (s.durum === 'alinmadi') alinmadi++;
  }
  const toplam = alindi + alinmadi;
  if (toplam === 0) return null;
  return alindi / toplam;
}

export interface Dagilim {
  tam: number;
  devamsiz: number;
  alinmadi: number;
  ulasilamaz: number;
}

export function dagilim(satirlar: Satir[]): Dagilim {
  const d: Dagilim = { tam: 0, devamsiz: 0, alinmadi: 0, ulasilamaz: 0 };
  for (const s of satirlar) {
    const h = hucreDurumu(s);
    if (h.tur === 'tam') d.tam++;
    else if (h.tur === 'devamsiz') d.devamsiz++;
    else if (h.tur === 'alinmadi') d.alinmadi++;
    else if (h.tur === 'ulasilamaz') d.ulasilamaz++;
  }
  return d;
}

/** Zil programı İstanbul saatidir; tarayıcı başka saat diliminde olsa da aynı dersi vurgular. */
export function istanbulSaati(simdi = new Date()): Date {
  const parcalar = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(simdi);
  const deger = (ad: string) => Number(parcalar.find((p) => p.type === ad)?.value);
  return new Date(deger('year'), deger('month') - 1, deger('day'), deger('hour'), deger('minute'), deger('second'));
}

function saatDk(ssDk: string): number {
  const [s, d] = ssDk.split(':').map((x) => parseInt(x, 10));
  return (s || 0) * 60 + (d || 0);
}

export function aktifDers(
  saatler: DersSaati[],
  simdi: Date,
  bugunMu: boolean
): DersSaati | null {
  if (!bugunMu) return null;
  const dk = simdi.getHours() * 60 + simdi.getMinutes();
  for (const s of saatler) {
    if (dk >= saatDk(s.baslangic) && dk <= saatDk(s.bitis)) return s;
  }
  return null;
}

export interface DersOzeti {
  no: number;
  baslangic: string;
  bitis: string;
  durum: 'devam' | 'tamam';
  alinan: number;
  beklenen: number;
}

export function dersListesi(
  saatler: DersSaati[],
  satirlar: Satir[],
  simdi: Date,
  bugunMu: boolean,
  sinifSayisi: number
): DersOzeti[] {
  const aktif = aktifDers(saatler, simdi, bugunMu);
  const simdiDk = simdi.getHours() * 60 + simdi.getMinutes();

  return saatler
    .filter((s) => (!bugunMu || simdiDk >= saatDk(s.baslangic))
      && satirlar.some((r) => r.ders_no === s.no && r.durum !== 'ders_yok_o_gun'))
    .map((s) => {
      const buDers = satirlar.filter((r) => r.ders_no === s.no);
      const alinan = buDers.filter((r) => r.durum === 'alindi').length;
      const devamMi = bugunMu && aktif?.no === s.no;
      return {
        no: s.no,
        baslangic: s.baslangic,
        bitis: s.bitis,
        durum: devamMi ? ('devam' as const) : ('tamam' as const),
        alinan,
        beklenen: sinifSayisi,
      };
    });
}

export function tiklanabilir(
  satir: Satir,
  sinifTahta: Record<string, number>,
  sinifId: number
): boolean {
  if (satir.durum !== 'alinmadi') return false;
  return String(sinifId) in sinifTahta;
}

export function haftaGunleri(tarihIso: string): string[] {
  // Verilen günün ait olduğu haftanın Pzt..Cum günleri
  const [y, m, d] = tarihIso.split('-').map((x) => parseInt(x, 10));
  const t = new Date(y, m - 1, d);
  // JS getDay: 0 Pazar, 1 Pzt.. 6 Cts -> Pzt'yi 0 yap
  const gun = (t.getDay() + 6) % 7;
  const pzt = new Date(t);
  pzt.setDate(t.getDate() - gun);

  const sonuclar: string[] = [];
  for (let i = 0; i < 5; i++) {
    const k = new Date(pzt);
    k.setDate(pzt.getDate() + i);
    const ky = k.getFullYear();
    const km = String(k.getMonth() + 1).padStart(2, '0');
    const kd = String(k.getDate()).padStart(2, '0');
    sonuclar.push(`${ky}-${km}-${kd}`);
  }
  return sonuclar;
}

// ---- Cam ders ızgarası (2026-11-14) ----

/** pano.html sorunluSatirlariUsteAl ile aynı: alınmadı/ulaşılamaz sınıflar üstte, kendi aralarında özgün sırada. */
export function sorunluUste(siniflar: Sinif[], satirlar: Satir[]): Sinif[] {
  const sorunlu = new Set(
    satirlar.filter((s) => s.durum === 'alinmadi' || s.durum === 'tahta_ulasilamaz').map((s) => s.sinif)
  );
  return [...siniflar.filter((s) => sorunlu.has(s.ad)), ...siniflar.filter((s) => !sorunlu.has(s.ad))];
}

const GUNLER = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
const AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

/** "Bugün · Cumartesi 14 Kasım" / geçmiş gün "Pazartesi 12 Ekim" (pano.html h1 ile aynı). */
export function baslikMetni(tarihIso: string, bugunIso: string): string {
  const [y, m, d] = tarihIso.split('-').map((x) => parseInt(x, 10));
  const t = new Date(y, m - 1, d);
  const metin = `${GUNLER[t.getDay()]} ${d} ${AYLAR[m - 1]}`;
  return tarihIso === bugunIso ? `Bugün · ${metin}` : metin;
}

export interface HalkaOranlari {
  alinan: number | null; // alındı / (alındı + alınmadı)
  tam: number | null;    // tam katılımlı / alındı
  acik: number | null;   // açık tahta / bilinen tahta
}

export function halkaOranlari(satirlar: Satir[], tahtaAcik: Record<string, boolean>): HalkaOranlari {
  const d = dagilim(satirlar);
  const alindi = d.tam + d.devamsiz;
  const tahtalar = Object.values(tahtaAcik);
  return {
    alinan: yoklamaOrani(satirlar),
    tam: alindi ? d.tam / alindi : null,
    acik: tahtalar.length ? tahtalar.filter(Boolean).length / tahtalar.length : null,
  };
}

/** Etkin dersin geçen süre oranı (0–1); ders yoksa null. */
export function dersIlerlemesi(ders: DersSaati | null, simdi: Date): number | null {
  if (!ders) return null;
  const bas = saatDk(ders.baslangic);
  const bit = saatDk(ders.bitis);
  if (bit <= bas) return null;
  const dk = simdi.getHours() * 60 + simdi.getMinutes() + simdi.getSeconds() / 60;
  return Math.min(1, Math.max(0, (dk - bas) / (bit - bas)));
}
