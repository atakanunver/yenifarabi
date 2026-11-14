import React from 'react';
import { Ikon } from './Ikon';
import type { MenuOgesi } from '../tipler';

interface GezinmeProps {
  menu: MenuOgesi[];
  acil: { ad: string; href: string };
}

// Brief: Yüzen izole dikey şerit (desktop) / alt şerit (mobil).
// İkonlar text-white/60 hover:text-white transition-all.
export const Gezinme: React.FC<GezinmeProps> = ({ menu, acil }) => {
  return (
    <nav
      aria-label="Ana gezinme"
      className="fixed bottom-3 left-1/2 z-30 flex -translate-x-1/2 items-center gap-1.5
                 rounded-[24px] border border-white/10 bg-white/[0.08] px-3 py-2 backdrop-blur-xl
                 shadow-[0_20px_60px_-20px_rgba(2,6,23,0.9)]
                 lg:sticky lg:top-6 lg:bottom-auto lg:left-auto lg:translate-x-0
                 lg:h-[calc(100vh-3rem)] lg:flex-col lg:justify-between lg:px-2.5 lg:py-5"
    >
      <div className="hidden h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-buz to-lila text-slate-950 font-bold text-xs lg:grid"
           title="Farabi Ders Izgarası">
        <Ikon ad="ev" className="h-5 w-5" />
        <span className="sr-only">Farabi</span>
      </div>

      <ul className="flex items-center gap-1 lg:flex-col lg:gap-2">
        {menu.map((m) => {
          const aktif = !!m.aktif;
          return (
            <li key={m.ad}>
              <a
                href={m.href}
                title={m.ad}
                aria-label={m.ad}
                aria-current={aktif ? 'page' : undefined}
                target={m.yeni_sekme ? '_blank' : undefined}
                rel={m.yeni_sekme ? 'noopener' : undefined}
                className={`grid h-11 w-11 place-items-center rounded-2xl transition-all duration-150
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buz
                            ${aktif ? 'bg-white text-slate-950 shadow-md' : 'text-white/60 hover:bg-white/10 hover:text-white'}`}
              >
                <Ikon ad={m.ikon} className="h-5 w-5" />
              </a>
            </li>
          );
        })}
      </ul>

      <div className="flex items-center gap-1 lg:flex-col lg:gap-2">
        <a
          href={acil.href}
          title={acil.ad}
          aria-label={acil.ad}
          className="grid h-11 w-11 place-items-center rounded-2xl text-rose-300 hover:bg-rose-500/20 hover:text-rose-100 transition-all duration-150
                     focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
        >
          <Ikon ad="uyari" className="h-5 w-5" />
        </a>
      </div>
    </nav>
  );
};
