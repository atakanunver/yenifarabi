import React, { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Ikon } from './Ikon';
import { haftaGunleri, yoklamaOrani } from '../turet';
import type { Satir } from '../tipler';

interface KatilimGrafigiProps {
  tarih: string;
  bugun: string;
  satirlar: Satir[];
  onTarihSec?: (t: string) => void;
}

interface GunVerisi {
  iso: string;
  kisa: string;
  oran: number | null;
  gelecek: boolean;
}

const GUN_ADLARI = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum'];

export const KatilimGrafigi: React.FC<KatilimGrafigiProps> = ({
  tarih,
  bugun,
  satirlar,
  onTarihSec,
}) => {
  const reduced = useReducedMotion();
  const gunler = haftaGunleri(tarih);
  const [hafta, setHafta] = useState<GunVerisi[]>(() =>
    gunler.map((g, i) => ({
      iso: g,
      kisa: GUN_ADLARI[i],
      oran: g === tarih ? yoklamaOrani(satirlar) : null,
      gelecek: g > bugun,
    }))
  );

  useEffect(() => {
    let iptal = false;
    async function yukle() {
      const sonuclar = await Promise.all(
        gunler.map(async (g, i) => {
          if (g > bugun) return { iso: g, kisa: GUN_ADLARI[i], oran: null, gelecek: true };
          if (g === tarih) {
            return { iso: g, kisa: GUN_ADLARI[i], oran: yoklamaOrani(satirlar), gelecek: false };
          }
          try {
            const r = await fetch(`/api/durum?tarih=${g}`);
            if (!r.ok) return { iso: g, kisa: GUN_ADLARI[i], oran: null, gelecek: false };
            const j = await r.json();
            return {
              iso: g,
              kisa: GUN_ADLARI[i],
              oran: yoklamaOrani(j.satirlar || []),
              gelecek: false,
            };
          } catch {
            return { iso: g, kisa: GUN_ADLARI[i], oran: null, gelecek: false };
          }
        })
      );
      if (!iptal) setHafta(sonuclar);
    }
    yukle();
    return () => {
      iptal = true;
    };
  }, [tarih, bugun, satirlar]);

  const seciliGun = hafta.find((g) => g.iso === tarih) || hafta[0];
  const yuzdeMetni =
    seciliGun?.oran !== null && seciliGun?.oran !== undefined
      ? `%${Math.round(seciliGun.oran * 100)}`
      : '—';

  return (
    <section
      aria-labelledby="b-katilim"
      className="flex h-full flex-col rounded-[22px] border border-white/[0.08] bg-white/[0.04] p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 id="b-katilim" className="flex items-center gap-2 text-[15px] font-semibold tracking-[-0.01em]">
          <Ikon ad="grafik" className="h-4 w-4 text-buz" />
          Haftalık katılım
        </h2>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/60">
          Bu hafta
        </span>
      </div>

      <div className="mt-3">
        <p className="text-[34px] font-bold leading-none tracking-[-0.03em] tabular-nums">
          {yuzdeMetni}
        </p>
        <p className="mt-1.5 text-sm text-white/60">
          {seciliGun ? `${seciliGun.kisa} günü yoklama oranı` : 'Seçili gün'}
        </p>
      </div>

      <ul className="mt-6 flex h-40 items-end justify-between gap-2.5" aria-label="Günlük katılım oranları">
        {hafta.map((g, i) => {
          const secili = g.iso === tarih;
          const oran = g.oran ?? 0;
          return (
            <li key={g.iso} className="flex h-full flex-1 flex-col items-center gap-2">
              <button
                type="button"
                disabled={g.gelecek}
                onClick={() => onTarihSec?.(g.iso)}
                aria-label={`${g.kisa}: ${g.oran !== null ? `%${Math.round(g.oran * 100)}` : 'veri yok'}`}
                aria-pressed={secili}
                className={`relative flex w-full max-w-[36px] flex-1 items-end overflow-hidden rounded-full
                            bg-white/[0.06] transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buz
                            ${g.gelecek ? 'opacity-30 cursor-not-allowed' : 'hover:bg-white/[0.12] cursor-pointer'}`}
              >
                <motion.span
                  className={`block w-full rounded-full ${
                    secili ? 'bg-gradient-to-t from-buz to-white' : 'bg-white/30'
                  }`}
                  initial={reduced ? false : { scaleY: 0 }}
                  animate={{ scaleY: oran }}
                  transition={{ duration: 0.6, delay: i * 0.05, ease: [0.2, 0.8, 0.2, 1] }}
                  style={{ height: '100%', originY: 1 }}
                />
              </button>
              <span className={`text-xs ${secili ? 'font-semibold text-white' : 'text-white/50'}`}>
                {g.kisa}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
};
