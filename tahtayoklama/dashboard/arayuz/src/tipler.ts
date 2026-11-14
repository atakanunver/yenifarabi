export type HamDurum =
  | 'alindi'
  | 'alinmadi'
  | 'henuz_baslamadi'
  | 'ders_yok_o_gun'
  | 'tahta_ulasilamaz'
  | 'tahta_atanmamis';

export interface Satir {
  sinif: string;
  ders_no: number;
  durum: HamDurum | string;
  yok_isimleri: string | null;
  izinli_isimleri: string | null;
  kaynak_tahta?: string | null;
  kaydedilme_saati?: string | null;
  guncelleme_zamani?: string | null;
  ders_kisa_adi?: string | null;
  ogretmen?: string | null;
  ogretmen_kisa?: string | null;
}

export interface Sinif {
  id: number;
  ad: string;
}

export interface DersSaati {
  no: number;
  baslangic: string; // "08:10"
  bitis: string;     // "08:50"
}

/** /api/durum yanıtı (pano.html ile aynı uç) */
export interface DurumYaniti {
  tarih: string;
  satirlar: Satir[];
  tahta_acik: Record<string, boolean>;
}

export interface PanoVeri {
  tarih: string; // YYYY-MM-DD
  bugun: string;
  siniflar: Sinif[];
  sinif_tahta: Record<string, number>;
  ders_saatleri: DersSaati[];
  ilk_durum: DurumYaniti;
}

declare global {
  interface Window {
    PANO_VERI?: PanoVeri;
    farabiToast?: (metin: string) => void; // static/menu.js (taban.html kabuğu)
  }
}
