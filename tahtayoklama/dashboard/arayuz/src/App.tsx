import React, { useState } from 'react';
import { Gezinme } from './bilesenler/Gezinme';
import { KatilimGrafigi } from './bilesenler/KatilimGrafigi';
import { Metrikler } from './bilesenler/Metrikler';
import type { PanoVeri, Satir } from './tipler';

interface AppProps {
  veri: PanoVeri;
}

export const App: React.FC<AppProps> = ({ veri }) => {
  const [tarih, setTarih] = useState(veri.tarih);
  const [satirlar] = useState<Satir[]>(veri.ilk_durum.satirlar);
  const [tahtaAcik] = useState(veri.ilk_durum.tahta_acik);

  const bugunMu = tarih === veri.bugun;

  return (
    <div className="relative min-h-screen">
      {/* Koyu lacivert ve degrade ortam — brief gereksinimi */}
      <div
        className="fixed inset-0 -z-10 bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900"
        aria-hidden="true"
      />
      <div
        className="fixed inset-0 -z-10 opacity-40 pointer-events-none"
        style={{
          background:
            'radial-gradient(60vmax 50vmax at 10% 10%, rgba(42, 59, 143, 0.7), transparent 60%), radial-gradient(55vmax 50vmax at 90% 90%, rgba(125, 227, 244, 0.25), transparent 60%)',
        }}
        aria-hidden="true"
      />

      <div className="mx-auto flex max-w-[1440px] items-start gap-6 px-4 pb-28 pt-6 sm:px-6 lg:pb-6">
        <Gezinme menu={veri.menu} acil={veri.acil} />

        <main
          className="min-w-0 flex-1 rounded-[28px] border border-white/10 bg-white/10 p-4 sm:p-6
                     backdrop-blur-xl shadow-[0_30px_80px_-30px_rgba(2,6,23,0.9)]"
        >
          <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-white/60">
                {bugunMu ? 'Bugün' : 'Geçmiş gün'} · {tarih}
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-[-0.025em] text-white sm:text-3xl">
                Ders ızgarası
              </h1>
            </div>
            <a
              href="/"
              className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs font-semibold
                         text-white/80 hover:bg-white/10 hover:text-white transition-all"
            >
              Klasik görünüme dön
            </a>
          </header>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-12">
            <div className="xl:col-span-5">
              <KatilimGrafigi
                tarih={tarih}
                bugun={veri.bugun}
                satirlar={satirlar}
                onTarihSec={(yeni) => setTarih(yeni)}
              />
            </div>
            <div className="xl:col-span-3">
              <Metrikler
                saatler={veri.ders_saatleri}
                satirlar={satirlar}
                tahtaAcik={tahtaAcik}
                sinifSayisi={veri.siniflar.length}
                bugunMu={bugunMu}
              />
            </div>
            <div className="md:col-span-2 xl:col-span-4" id="halka-alani">
              {/* Task 4 KatilimHalkasi buraya gelecek */}
              <div className="flex h-full min-h-[160px] items-center justify-center rounded-[22px] border border-white/[0.08] bg-white/[0.04] p-5 text-xs text-white/40">
                Katılım halkası yükleniyor…
              </div>
            </div>
            <div className="xl:col-span-7" id="ders-listesi-alani">
              {/* Task 4 DersListesi buraya gelecek */}
              <div className="flex h-full min-h-[180px] items-center justify-center rounded-[22px] border border-white/[0.08] bg-white/[0.04] p-5 text-xs text-white/40">
                Ders listesi yükleniyor…
              </div>
            </div>
            <div className="xl:col-span-5" id="izgara-alani">
              {/* Task 5 DersIzgarasi buraya gelecek */}
              <div className="flex h-full min-h-[180px] items-center justify-center rounded-[22px] border border-white/[0.08] bg-white/[0.04] p-5 text-xs text-white/40">
                Yoklama ızgarası yükleniyor…
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
