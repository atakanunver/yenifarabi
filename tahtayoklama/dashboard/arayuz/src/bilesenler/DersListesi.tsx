import React from 'react';
import { Hap, Kapsul, Kart } from './Kart';
import { dersListesi } from '../turet';
import type { DersSaati, Satir } from '../tipler';

interface DersListesiProps {
  saatler: DersSaati[];
  satirlar: Satir[];
  simdi: Date;
  bugunMu: boolean;
  sinifSayisi: number;
}

// Başlamış dersler: saat, durum hapı, alınan/beklenen kapsülü. Geçmiş tarihte hepsi "Tamamlandı".
export const DersListesi: React.FC<DersListesiProps> = ({ saatler, satirlar, simdi, bugunMu, sinifSayisi }) => {
  const dersler = dersListesi(saatler, satirlar, simdi, bugunMu, sinifSayisi);
  return (
    <Kart baslik="Dersler" ikon="takvim" vurgu="#BF5AF2" sira={4} sag={<Hap>{dersler.length} / {saatler.length}</Hap>}>
      {dersler.length === 0 ? (
        <p className="text-[13px] text-white/45">Bu tarih için başlamış ders kaydı bulunmuyor.</p>
      ) : (
        <ul className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
          {dersler.map((d) => (
            <li key={d.no} className="rounded-[18px] border border-white/10 bg-white/[0.04] px-3.5 py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[14px] font-medium text-white">
                  {d.no}. ders <span className="font-normal text-white/45">{d.baslangic}–{d.bitis}</span>
                </p>
                <Hap renk={d.durum === 'devam' ? '#32D74B' : 'rgba(255,255,255,0.45)'}>{d.durum === 'devam' ? 'Devam ediyor' : 'Tamamlandı'}</Hap>
              </div>
              <div className="mt-2.5 flex items-center gap-3">
                <div className="flex-1">
                  <Kapsul oran={d.beklenen ? d.alinan / d.beklenen : null} renk={d.alinan >= d.beklenen ? '#32D74B' : '#38BDF8'}
                          etiket={`${d.no}. ders alınan yoklama`} />
                </div>
                <span className="text-[12px] text-white/45">{d.alinan}/{d.beklenen}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Kart>
  );
};
