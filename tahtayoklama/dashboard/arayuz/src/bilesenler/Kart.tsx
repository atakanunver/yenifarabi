import React from 'react';
import { motion } from 'framer-motion';
import { Ikon } from './Ikon';

export const YAY = { type: 'spring', stiffness: 260, damping: 24 } as const;

interface KartProps {
  baslik: string;
  ikon: string;
  vurgu: string;   // ikon rozeti ve arka ışık rengi (#RRGGBB)
  sag?: React.ReactNode;
  sira?: number;   // giriş gecikmesi sırası
  className?: string;
  children: React.ReactNode;
}

// Bento kart: nötr cam; üzerine gelince hafif kalkar, üst kenarı parlar, vurgu renginde arka ışık verir.
export const Kart: React.FC<KartProps> = ({ baslik, ikon, vurgu, sag, sira = 0, className = '', children }) => (
  <motion.section
    initial={{ opacity: 0, y: 14, scale: 0.98 }}
    animate={{ opacity: 1, y: 0, scale: 1 }}
    transition={{ ...YAY, delay: sira * 0.05 }}
    className={`group relative min-w-0 ${className}`}
    aria-label={baslik}
  >
    <div aria-hidden="true"
         className="pointer-events-none absolute inset-x-10 -bottom-4 h-16 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-60"
         style={{ background: `${vurgu}59` }} />
    <div className="relative flex h-full flex-col rounded-[24px] border border-white/15 bg-white/[0.04] p-5
                    shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] transition-all duration-300
                    group-hover:-translate-y-0.5 group-hover:border-t-white/35 group-hover:bg-white/[0.08]">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full"
                style={{ background: `${vurgu}26`, color: vurgu, boxShadow: `0 0 14px ${vurgu}40` }}>
            <Ikon ad={ikon} className="h-4 w-4" />
          </span>
          <h2 className="truncate text-[15px] font-medium text-white/75">{baslik}</h2>
        </div>
        {sag}
      </header>
      {children}
    </div>
  </motion.section>
);

export const Hap: React.FC<{ renk?: string; children: React.ReactNode }> = ({ renk, children }) => (
  <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[12px] font-medium text-white/75">
    {renk && <span className="h-1.5 w-1.5 rounded-full" style={{ background: renk, boxShadow: `0 0 8px ${renk}` }} />}
    {children}
  </span>
);

export const Kapsul: React.FC<{ oran: number | null; renk: string; etiket: string }> = ({ oran, renk, etiket }) => (
  <div className="h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-label={etiket}
       aria-valuemin={0} aria-valuemax={100} aria-valuenow={oran === null ? undefined : Math.round(oran * 100)}>
    <motion.div className="h-full rounded-full" style={{ background: renk, boxShadow: `0 0 8px ${renk}` }}
                initial={{ width: 0 }} animate={{ width: `${(oran ?? 0) * 100}%` }} transition={YAY} />
  </div>
);
