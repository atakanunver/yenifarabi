import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Ikon } from './Ikon';
import { YAY } from './Kart';
import { haftaGunleri } from '../turet';
import type { AcilDurum } from '../api';

const KISA = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum'];

interface UstSeritProps {
  tarih: string;
  bugun: string;
  sonGuncelleme: string;
  yenileniyor: boolean;
  acil: AcilDurum | null;
  onTarih: (t: string) => void;
  onYenile: () => void;
}

export const UstSerit: React.FC<UstSeritProps> = ({ tarih, bugun, sonGuncelleme, yenileniyor, acil, onTarih, onYenile }) => {
  const gunler = haftaGunleri(tarih);
  const a = acil?.aktif;
  return (
    <>
      <AnimatePresence>
        {a && (
          <motion.a
            key="acil-bant"
            href="/acil"
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.99 }}
            transition={YAY}
            className="mb-5 flex items-center gap-3 rounded-[20px] border border-mercan/50 bg-mercan/20 px-4 py-3 text-[15px] font-semibold text-white no-underline shadow-[0_0_24px_rgba(255,59,92,0.35)]"
          >
            <Ikon ad="uyari" className="h-5 w-5 text-mercan" />
            <span>
              Aktif alarm: {acil?.turler[a.tur]?.baslik || a.tur}{a.tatbikat ? ' (tatbikat)' : ''} — {(a.zaman || '').slice(11, 16)}
              {a.istemci_ip ? ` — ${a.istemci_ip}` : ''} · Yönetmek için tıklayın
            </span>
          </motion.a>
        )}
      </AnimatePresence>
      <h1 className="sr-only">Ders ızgarası</h1>
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <div role="tablist" aria-label="Haftanın günü" className="relative flex rounded-full border border-white/15 bg-white/[0.06] p-1">
            {gunler.map((g, i) => {
              const secili = g === tarih;
              return (
                <motion.button key={g} role="tab" type="button" aria-selected={secili} disabled={g > bugun}
                        whileTap={g <= bugun ? { scale: 0.94 } : undefined}
                        onClick={() => !secili && onTarih(g)} title={g}
                        className={`relative rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-300
                                    ${secili ? 'text-white' : 'text-white/55 hover:text-white'} disabled:opacity-30`}>
                  {secili && (
                    <motion.span layoutId="gun-hap" transition={YAY}
                                 className="absolute inset-0 rounded-full border border-white/20 bg-white/20 shadow-[0_0_15px_rgba(255,255,255,0.3)]" />
                  )}
                  <span className="relative">{KISA[i]}</span>
                </motion.button>
              );
            })}
          </div>
          <label className="flex items-center gap-2 text-[12px] text-white/45">
            <span className="sr-only">Tarih</span>
            <input type="date" value={tarih} max={bugun} onChange={(e) => e.target.value && onTarih(e.target.value)}
                   className="h-9 rounded-full border border-white/15 bg-white/[0.06] px-3 text-[13px] text-white transition-colors duration-200 hover:border-white/30 hover:bg-white/[0.1]" />
          </label>
          <motion.button type="button" onClick={onYenile} disabled={tarih !== bugun || yenileniyor}
                  whileHover={tarih === bugun && !yenileniyor ? { y: -1.5 } : undefined}
                  whileTap={tarih === bugun && !yenileniyor ? { scale: 0.95 } : undefined}
                  transition={YAY}
                  className="inline-flex h-9 items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 text-[13px] font-medium text-white
                             transition-colors duration-300 hover:border-t-white/35 hover:bg-white/[0.11] disabled:opacity-40">
            <Ikon ad="yenile" className={`h-4 w-4 ${yenileniyor ? 'animate-spin' : ''}`} />
            {yenileniyor ? 'Yenileniyor…' : 'Şimdi yenile'}
          </motion.button>
          <span className="w-full text-right text-[12px] text-white/45 sm:w-auto" aria-live="off">
            {sonGuncelleme ? `Son güncelleme: ${sonGuncelleme}` : ''}
          </span>
        </div>
      </header>
    </>
  );
};
