import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { DersSaati, Satir, Sinif } from '../tipler';
import { hucreDurumu, sorunluUste, tiklanabilir } from '../turet';
import { Kart, YAY } from './Kart';

interface DersIzgarasiProps {
  siniflar: Sinif[];
  saatler: DersSaati[];
  satirlar: Satir[];
  sinifTahta: Record<string, number>;
  tahtaAcik: Record<string, boolean>;
  aktifDersNo: number | null;
  onBaslat: (tahtaId: number, sinif: string) => Promise<void>;
  yukleniyor?: boolean;
}

export function DersIzgarasi({ siniflar, saatler, satirlar, sinifTahta, tahtaAcik, aktifDersNo, onBaslat, yukleniyor = false }: DersIzgarasiProps) {
  const bekleyen = useRef(new Set<number>());
  const [bekleyenler, setBekleyenler] = useState<Set<number>>(new Set());
  const satirHaritasi = new Map(satirlar.map((satir) => [`${satir.sinif}\u0000${satir.ders_no}`, satir]));

  async function baslat(tahtaId: number, sinif: string) {
    if (bekleyen.current.has(tahtaId)) return;
    bekleyen.current.add(tahtaId);
    setBekleyenler(new Set(bekleyen.current));
    try {
      await onBaslat(tahtaId, sinif);
    } catch {
      // Hata bildirimi onBaslat çağırıcısının sorumluluğundadır.
    } finally {
      bekleyen.current.delete(tahtaId);
      setBekleyenler(new Set(bekleyen.current));
    }
  }

  return (
    <Kart baslik="Ders ızgarası" ikon="takvim" vurgu="#38BDF8" sira={0} className="w-full min-w-0">
      {siniflar.length === 0 ? (
        <p className="text-sm text-white/70">Panoda gösterilecek aktif sınıf yok.</p>
      ) : (
        <div className="w-full min-w-0 overflow-x-auto" tabIndex={0} aria-label="Sınıf ve ders saatine göre yoklama durumu">
          <table className="w-full min-w-[900px] table-fixed border-separate border-spacing-0 text-left text-sm">
            <caption className="sr-only">Sınıf ve ders saatine göre yoklama durumu</caption>
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 z-20 w-28 border-b border-white/15 bg-[rgba(20,25,44,0.92)] px-3 py-3 text-white">Sınıf</th>
                {saatler.map((ders) => (
                  <th key={ders.no} scope="col" className={`border-b border-white/15 px-3 py-3 text-white/75 ${aktifDersNo === ders.no ? 'bg-white/10' : ''}`}>
                    <span>{ders.no}. ders{aktifDersNo === ders.no ? ' · şimdi' : ''}</span>
                    <span className="block text-xs text-white/50">{ders.baslangic}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorunluUste(siniflar, satirlar).map((sinif, satirIndeks) => {
                const tahtaDurumu = tahtaAcik[sinif.ad];
                const tahtaMetni = tahtaDurumu === undefined ? 'Tahta durumu bilinmiyor' : tahtaDurumu ? 'Tahta açık' : 'Tahta kapalı';
                return (
                  <motion.tr
                    key={sinif.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ ...YAY, delay: Math.min(satirIndeks * 0.03, 0.24) }}
                    className="transition-colors duration-200 hover:bg-white/[0.035]"
                  >
                    <th scope="row" className="sticky left-0 z-10 border-b border-white/10 bg-[rgba(20,25,44,0.92)] px-3 py-3 text-white">
                      <span role="img" aria-label={tahtaMetni} title={tahtaMetni} className={`mr-2 inline-block h-2 w-2 rounded-full transition-shadow duration-300 ${tahtaDurumu === undefined ? 'bg-gray-400' : tahtaDurumu ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.65)]' : 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.5)]'}`} />
                      {sinif.ad}
                    </th>
                    {saatler.map((ders) => {
                      const anahtar = `${sinif.ad}\u0000${ders.no}`;
                      const satir = satirHaritasi.get(anahtar);
                      const hucre = satir ? hucreDurumu(satir) : null;
                      const tahtaId = sinifTahta[String(sinif.id)];
                      const etkin = !!satir && tiklanabilir(satir, sinifTahta, sinif.id) && typeof tahtaId === 'number';
                      const bekliyor = bekleyenler.has(tahtaId);
                      const icerik = !hucre ? null : hucre.tur === 'devamsiz' ? (
                        <>
                          {hucre.yok.length > 0 && <span className="block break-words text-white/85"><span className="sr-only">Devamsız: </span>{hucre.yok.join(', ')}</span>}
                          {hucre.izinli.length > 0 && <span className="block break-words text-sky-200">İzinli: {hucre.izinli.join(', ')}</span>}
                        </>
                      ) : hucre.tur === 'bos' ? (satir && !['henuz_baslamadi', 'ders_yok_o_gun'].includes(satir.durum) ? satir.durum : null) : (
                        <span className={`inline-block rounded-full px-2 py-1 text-xs transition-transform duration-200 group-hover/hucre:scale-105 ${hucre.tur === 'tam' ? 'bg-emerald-400/20 text-emerald-200' : hucre.tur === 'alinmadi' ? 'bg-amber-400/20 text-amber-200' : 'bg-white/10 text-white/75'}`}>
                          {hucre.tur === 'tam' ? 'Tam' : hucre.tur === 'alinmadi' ? 'Alınmadı' : hucre.tur === 'ulasilamaz' ? 'Tahta ulaşılamaz' : 'Tahta atanmadı'}
                        </span>
                      );
                      return (
                        <td key={ders.no} className={`group/hucre border-b border-white/10 px-3 py-3 align-top text-white/75 transition-all duration-200 ${aktifDersNo === ders.no ? 'bg-white/10' : ''} ${etkin ? 'cursor-pointer hover:bg-amber-400/10 active:scale-[0.97] focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-300' : ''}`}
                          role={etkin ? 'button' : undefined} tabIndex={etkin ? 0 : undefined}
                          aria-label={etkin ? `${sinif.ad}, ${ders.no}. ders: yoklama alınmadı. Tahtada yoklama ekranını başlat` : undefined}
                          aria-disabled={etkin && bekliyor ? true : undefined} aria-busy={bekliyor || undefined}
                          title={etkin ? 'Tahtada yoklama ekranını başlat' : undefined}
                          onClick={etkin ? () => { void baslat(tahtaId, sinif.ad); } : undefined}
                          onKeyDown={etkin ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); void baslat(tahtaId, sinif.ad); } } : undefined}>
                          {yukleniyor && !satir ? <span className="block h-4 w-16 animate-pulse rounded bg-white/10" aria-label="Yükleniyor" /> : icerik}
                          {satir?.ders_kisa_adi && <span className="mt-1 block break-words text-xs text-white/50" title={satir.ogretmen || undefined}>{satir.ders_kisa_adi}{satir.ogretmen_kisa ? `-${satir.ogretmen_kisa}` : ''}</span>}
                        </td>
                      );
                    })}
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Kart>
  );
}
