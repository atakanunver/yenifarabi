import React from 'react';
import { Hap, Kapsul, Kart } from './Kart';
import { aktifDers, dersIlerlemesi } from '../turet';
import type { DersSaati, Satir } from '../tipler';

interface SuAnProps {
  saatler: DersSaati[];
  satirlar: Satir[];
  tahtaAcik: Record<string, boolean>;
  sinifSayisi: number;
  bugunMu: boolean;
  simdi: Date;
}

// "Şu an": etkin ders (büyük), dersin geçen süresi kapsülü, altta açık tahta ve alınan yoklama.
export const SuAn: React.FC<SuAnProps> = ({ saatler, satirlar, tahtaAcik, sinifSayisi, bugunMu, simdi }) => {
  const dersVar = satirlar.some((s) => s.durum !== 'ders_yok_o_gun');
  const aktif = aktifDers(saatler, simdi, bugunMu && dersVar);
  const ilerleme = dersIlerlemesi(aktif, simdi);
  const tahtalar = Object.values(tahtaAcik);
  const acik = tahtalar.filter(Boolean).length;
  const alinan = satirlar.filter((s) => s.durum === 'alindi').length;
  const baslamis = satirlar.filter((s) => s.durum === 'alindi' || s.durum === 'alinmadi').length;
  const buyuk = aktif ? `${aktif.no}. ders` : bugunMu ? (dersVar ? 'Teneffüs' : 'Ders yok') : 'Geçmiş gün';
  const alt = aktif ? `${aktif.baslangic} – ${aktif.bitis}` : bugunMu ? 'Şu an ders yok' : 'Gün sonu durumu';

  return (
    <Kart baslik="Şu an" ikon="saat" vurgu="#38BDF8" sira={0}
          sag={<Hap renk={aktif ? '#32D74B' : 'rgba(255,255,255,0.45)'}>{aktif ? 'Devam ediyor' : bugunMu ? 'Ders dışı' : 'Kapandı'}</Hap>}>
      <p className="text-[40px] font-semibold leading-none tracking-tight text-white">{buyuk}</p>
      <p className="mt-2 text-[13px] text-white/45">{alt}</p>
      <div className="mt-4">
        <Kapsul oran={ilerleme} renk="#38BDF8" etiket="Dersin geçen süresi" />
      </div>
      <dl className="mt-auto grid grid-cols-2 gap-3 border-t border-white/10 pt-4">
        <div>
          <dt className="text-[12px] text-white/45">Açık tahta</dt>
          <dd className="m-0 text-[20px] font-semibold tracking-tight text-white">
            {acik}<span className="text-[13px] font-normal text-white/45"> / {tahtalar.length || sinifSayisi}</span>
          </dd>
        </div>
        <div>
          <dt className="text-[12px] text-white/45">Alınan yoklama</dt>
          <dd className="m-0 text-[20px] font-semibold tracking-tight text-white">
            {alinan}<span className="text-[13px] font-normal text-white/45"> / {baslamis}</span>
          </dd>
        </div>
      </dl>
    </Kart>
  );
};
