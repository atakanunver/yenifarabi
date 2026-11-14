import React from 'react';
import { Ikon } from './Ikon';
import { aktifDers } from '../turet';
import type { DersSaati, Satir } from '../tipler';

interface MetriklerProps {
  saatler: DersSaati[];
  satirlar: Satir[];
  tahtaAcik: Record<string, boolean>;
  sinifSayisi: number;
  bugunMu: boolean;
  simdi?: Date;
}

interface KartProps {
  ikon: string;
  baslik: string;
  deger: string;
  alt: string;
  vurgu: string;
}

const Kart: React.FC<KartProps> = ({ ikon, baslik, deger, alt, vurgu }) => (
  <li className="flex items-center gap-4 rounded-[18px] border border-white/[0.07] bg-white/[0.04] p-4">
    <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${vurgu}`}>
      <Ikon ad={ikon} className="h-5 w-5" />
    </span>
    <div className="min-w-0 flex-1">
      <p className="text-xs font-medium text-white/60">{baslik}</p>
      <p className="mt-0.5 text-xl font-bold tracking-[-0.02em] tabular-nums text-white truncate">
        {deger}
      </p>
      <p className="text-[11px] text-white/50 truncate">{alt}</p>
    </div>
  </li>
);

export const Metrikler: React.FC<MetriklerProps> = ({
  saatler,
  satirlar,
  tahtaAcik,
  sinifSayisi,
  bugunMu,
  simdi = new Date(),
}) => {
  const aktif = aktifDers(saatler, simdi, bugunMu);
  const acikSayi = Object.values(tahtaAcik).filter(Boolean).length;
  const toplamTahta = Object.keys(tahtaAcik).length || sinifSayisi;

  const alinanToplam = satirlar.filter((s) => s.durum === 'alindi').length;
  const beklenenToplam = saatler.length * sinifSayisi;

  const dersMetni = aktif
    ? `${aktif.no}. ders`
    : bugunMu
    ? 'Teneffüs / Ders yok'
    : 'Geçmiş gün';
  const dersAlt = aktif ? `${aktif.baslangic} – ${aktif.bitis}` : 'Zil programına göre';

  return (
    <section aria-labelledby="b-metrikler" className="flex h-full flex-col">
      <h2 id="b-metrikler" className="sr-only">
        Hızlı metrikler
      </h2>
      <ul className="flex flex-1 flex-col justify-between gap-3">
        <Kart
          ikon="saat"
          baslik="Şu an"
          deger={dersMetni}
          alt={dersAlt}
          vurgu="bg-buz/15 text-buz"
        />
        <Kart
          ikon="tahta"
          baslik="Açık tahta"
          deger={`${acikSayi} / ${toplamTahta}`}
          alt={`%${toplamTahta ? Math.round((acikSayi / toplamTahta) * 100) : 0} çevrimiçi`}
          vurgu="bg-lila/15 text-lila"
        />
        <Kart
          ikon="onay"
          baslik="Alınan yoklama"
          deger={`${alinanToplam}`}
          alt={`Toplam ${beklenenToplam} dersten`}
          vurgu="bg-zumrut/15 text-emerald-300"
        />
      </ul>
    </section>
  );
};
