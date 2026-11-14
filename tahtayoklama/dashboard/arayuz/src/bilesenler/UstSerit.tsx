import React from 'react';
import { motion } from 'framer-motion';
import { Ikon } from './Ikon';
import { YAY } from './Kart';
import { baslikMetni, haftaGunleri } from '../turet';
import type { AcilDurum } from '../api';

const KISA = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum'];

interface UstSeritProps {
  tarih: string;
  bugun: string;
  aktifDersNo: number | null;
  sonGuncelleme: string;
  yenileniyor: boolean;
  acil: AcilDurum | null;
  onTarih: (t: string) => void;
  onYenile: () => void;
}

export const UstSerit: React.FC<UstSeritProps> = ({ tarih, bugun, aktifDersNo, sonGuncelleme, yenileniyor, acil, onTarih, onYenile }) => {
  const gunler = haftaGunleri(tarih);
  const a = acil?.aktif;
  return (
    <>
      {a && (
        <a href="/acil" className="mb-5 flex items-center gap-3 rounded-[20px] border border-mercan/50 bg-mercan/20 px-4 py-3 text-[15px] font-semibold text-white no-underline shadow-[0_0_24px_rgba(255,59,92,0.35)]">
          <Ikon ad="uyari" className="h-5 w-5 text-mercan" />
          <span>
            Aktif alarm: {acil?.turler[a.tur]?.baslik || a.tur}{a.tatbikat ? ' (tatbikat)' : ''} — {(a.zaman || '').slice(11, 16)}
            {a.istemci_ip ? ` — ${a.istemci_ip}` : ''} · Yönetmek için tıklayın
          </span>
        </a>
      )}
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-white/45">Yoklama › Ders ızgarası</p>
          <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight text-white sm:text-[32px]">
            {baslikMetni(tarih, bugun)}
            {aktifDersNo ? <span className="text-white/45"> · {aktifDersNo}. ders</span> : null}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div role="tablist" aria-label="Haftanın günü" className="relative flex rounded-full border border-white/15 bg-white/[0.06] p-1">
            {gunler.map((g, i) => {
              const secili = g === tarih;
              return (
                <button key={g} role="tab" type="button" aria-selected={secili} disabled={g > bugun}
                        onClick={() => !secili && onTarih(g)} title={g}
                        className={`relative rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-300
                                    ${secili ? 'text-white' : 'text-white/55 hover:text-white'} disabled:opacity-30`}>
                  {secili && (
                    <motion.span layoutId="gun-hap" transition={YAY}
                                 className="absolute inset-0 rounded-full border border-white/20 bg-white/20 shadow-[0_0_15px_rgba(255,255,255,0.3)]" />
                  )}
                  <span className="relative">{KISA[i]}</span>
                </button>
              );
            })}
          </div>
          <label className="flex items-center gap-2 text-[12px] text-white/45">
            <span className="sr-only">Tarih</span>
            <input type="date" value={tarih} max={bugun} onChange={(e) => e.target.value && onTarih(e.target.value)}
                   className="h-9 rounded-full border border-white/15 bg-white/[0.06] px-3 text-[13px] text-white" />
          </label>
          <button type="button" onClick={onYenile} disabled={tarih !== bugun || yenileniyor}
                  className="inline-flex h-9 items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 text-[13px] font-medium text-white
                             transition-all duration-300 hover:-translate-y-0.5 hover:border-t-white/35 hover:bg-white/[0.11] disabled:opacity-40 disabled:hover:translate-y-0">
            <Ikon ad="yenile" className={`h-4 w-4 ${yenileniyor ? 'animate-spin' : ''}`} />
            {yenileniyor ? 'Yenileniyor…' : 'Şimdi yenile'}
          </button>
          <span className="w-full text-right text-[12px] text-white/45 sm:w-auto" aria-live="off">
            {sonGuncelleme ? `Son güncelleme: ${sonGuncelleme}` : ''}
          </span>
        </div>
      </header>
    </>
  );
};
