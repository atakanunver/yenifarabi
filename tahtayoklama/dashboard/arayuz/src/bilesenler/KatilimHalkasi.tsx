import React from 'react';
import { motion } from 'framer-motion';
import { Kart } from './Kart';
import { halkaOranlari } from '../turet';
import type { Satir } from '../tipler';

const yuzde = (o: number | null) => (o === null ? '—' : `%${Math.round(o * 100)}`);

// İç içe halkalar (yuvarlak uçlu, parlak): alınan yoklama, tam katılım, açık tahta. Payda 0 → boş halka + "—".
export const KatilimHalkasi: React.FC<{ satirlar: Satir[]; tahtaAcik: Record<string, boolean> }> = ({ satirlar, tahtaAcik }) => {
  const o = halkaOranlari(satirlar, tahtaAcik);
  const halkalar = [
    { ad: 'Alınan yoklama', r: 58, renk: '#32D74B', oran: o.alinan },
    { ad: 'Tam katılım', r: 44, renk: '#38BDF8', oran: o.tam },
    { ad: 'Açık tahta', r: 30, renk: '#BF5AF2', oran: o.acik },
  ];
  return (
    <Kart baslik="Katılım" ikon="hedef" vurgu="#32D74B" sira={1}>
      <p className="text-[40px] font-semibold leading-none tracking-tight text-white">{yuzde(o.alinan)}</p>
      <p className="mt-2 text-[13px] text-white/45">Başlamış derslerde alınan yoklama</p>
      <div className="mt-4 flex items-center gap-5">
        <svg viewBox="0 0 140 140" className="h-[132px] w-[132px] shrink-0" role="img"
             aria-label={halkalar.map((h) => `${h.ad} ${yuzde(h.oran)}`).join(', ')}>
          {halkalar.map((h) => (
            <g key={h.ad}>
              <circle cx={70} cy={70} r={h.r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={10} />
              <motion.circle cx={70} cy={70} r={h.r} fill="none" stroke={h.renk} strokeWidth={10} strokeLinecap="round"
                             transform="rotate(-90 70 70)" style={{ filter: `drop-shadow(0 0 6px ${h.renk})` }}
                             initial={{ pathLength: 0, opacity: 0 }}
                             animate={{ pathLength: h.oran ?? 0, opacity: h.oran ? 1 : 0 }}
                             transition={{ duration: 0.9, ease: 'easeOut' }} />
            </g>
          ))}
        </svg>
        <ul className="flex min-w-0 flex-1 flex-col gap-2.5">
          {halkalar.map((h) => (
            <li key={h.ad} className="flex items-center gap-2.5">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: h.renk, boxShadow: `0 0 8px ${h.renk}` }} />
              <div className="min-w-0 leading-tight">
                <p className="text-[12px] text-white/45">{h.ad}</p>
                <p className="text-[14px] font-medium text-white">{yuzde(h.oran)}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Kart>
  );
};
