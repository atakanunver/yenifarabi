import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Hap, Kart, YAY } from './Kart';
import { haftaGunleri, yoklamaOrani } from '../turet';
import { durumGetir } from '../api';
import type { Satir } from '../tipler';

interface KatilimGrafigiProps {
  tarih: string;
  bugun: string;
  satirlar: Satir[];
  onTarihSec: (t: string) => void;
}

interface GunVerisi {
  iso: string;
  kisa: string;
  oran: number | null;
  gelecek: boolean;
}

const GUN_ADLARI = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum'];

// Haftalık katılım: dikey hap çubuklar; seçili gün camgöbeği→çivit parlar. Gelecek gün çağrılmaz, soluk.
export const KatilimGrafigi: React.FC<KatilimGrafigiProps> = ({ tarih, bugun, satirlar, onTarihSec }) => {
  const gunler = haftaGunleri(tarih);
  const [hafta, setHafta] = useState<GunVerisi[]>(() =>
    gunler.map((g, i) => ({ iso: g, kisa: GUN_ADLARI[i], oran: g === tarih ? yoklamaOrani(satirlar) : null, gelecek: g > bugun }))
  );

  // Diğer günler yalnız tarih değişince çekilir; seçili günün oranı her yoklama yenilemesinde güncellenir.
  useEffect(() => {
    let iptal = false;
    Promise.all(
      haftaGunleri(tarih).map(async (g, i): Promise<GunVerisi> => {
        const taban = { iso: g, kisa: GUN_ADLARI[i], gelecek: g > bugun };
        if (g > bugun || g === tarih) return { ...taban, oran: null };
        try {
          return { ...taban, oran: yoklamaOrani((await durumGetir(g)).satirlar || []) };
        } catch {
          return { ...taban, oran: null };
        }
      })
    ).then((s) => { if (!iptal) setHafta(s); });
    return () => { iptal = true; };
  }, [tarih, bugun]);

  const gorunen = hafta.map((g) => (g.iso === tarih ? { ...g, oran: yoklamaOrani(satirlar) } : g));
  const secili = gorunen.find((g) => g.iso === tarih);
  const oranlar = gorunen.filter((g) => g.oran !== null).map((g) => g.oran as number);
  const ortalama = oranlar.length ? oranlar.reduce((a, b) => a + b, 0) / oranlar.length : null;

  return (
    <Kart baslik="Haftalık katılım" ikon="grafik" vurgu="#6366F1" sira={3}
          sag={<Hap renk="#38BDF8">Ort. {ortalama === null ? '—' : `%${Math.round(ortalama * 100)}`}</Hap>}>
      <p className="text-[40px] font-semibold leading-none tracking-tight text-white">
        {secili?.oran == null ? '—' : `%${Math.round(secili.oran * 100)}`}
      </p>
      <p className="mt-2 text-[13px] text-white/45">{secili ? `${secili.kisa} günü yoklama oranı` : 'Hafta sonu'}</p>
      <ul className="mt-4 flex h-[124px] items-end justify-between gap-2" aria-label="Günlük yoklama oranları">
        {gorunen.map((g, i) => {
          const sec = g.iso === tarih;
          return (
            <li key={g.iso} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
              <button type="button" disabled={g.gelecek} aria-pressed={sec} onClick={() => !sec && onTarihSec(g.iso)}
                      aria-label={`${g.kisa}: ${g.oran === null ? 'veri yok' : `%${Math.round(g.oran * 100)}`}`}
                      title={`${g.kisa}: ${g.oran === null ? 'veri yok' : `%${Math.round(g.oran * 100)}`}`}
                      className="group/cubuk flex h-full w-full items-end justify-center disabled:opacity-30">
                <motion.span
                  className={`block w-full max-w-[26px] rounded-full transition-colors duration-300 ${
                    sec && g.oran !== null ? 'bg-gradient-to-t from-civit to-camgobegi shadow-[0_0_16px_rgba(56,189,248,0.55)]' : 'bg-white/15 group-hover/cubuk:bg-white/25'
                  }`}
                  initial={{ height: 0 }}
                  animate={{ height: `${(g.oran ?? 0.06) * 100}%` }}
                  transition={{ ...YAY, delay: i * 0.04 }}
                />
              </button>
              <span className={`text-[12px] ${sec ? 'text-white' : 'text-white/45'}`}>{g.kisa}</span>
            </li>
          );
        })}
      </ul>
    </Kart>
  );
};
