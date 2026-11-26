import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from 'framer-motion';
import { KatilimGrafigi } from './bilesenler/KatilimGrafigi';
import { KatilimHalkasi } from './bilesenler/KatilimHalkasi';
import { SuAn } from './bilesenler/Metrikler';
import { DersListesi } from './bilesenler/DersListesi';
import { DersIzgarasi } from './bilesenler/DersIzgarasi';
import { UstSerit } from './bilesenler/UstSerit';
import { YAY } from './bilesenler/Kart';
import { aktifDers, istanbulSaati } from './turet';
import { acilDurum, durumGetir, tahtaBaslat, yenile } from './api';
import type { AcilDurum } from './api';
import type { PanoVeri } from './tipler';

export const App: React.FC<{ veri: PanoVeri }> = ({ veri }) => {
  const [durum, setDurum] = useState(veri.ilk_durum);
  const [simdi, setSimdi] = useState(() => istanbulSaati());
  const [sonGuncelleme, setSonGuncelleme] = useState('');
  const [yenileniyor, setYenileniyor] = useState(false);
  const [hata, setHata] = useState(false);
  const [acil, setAcil] = useState<AcilDurum | null>(null);
  const bekleyen = useRef(false);
  const reduced = useReducedMotion();
  const [animMod, setAnimMod] = useState<string>(() =>
    (typeof document !== 'undefined' ? document.documentElement.dataset.animasyon : undefined) || 'acik'
  );
  useEffect(() => {
    const dinle = (e: Event) => {
      const d = (e as CustomEvent<string>).detail;
      setAnimMod(d || document.documentElement.dataset.animasyon || 'acik');
    };
    window.addEventListener('farabi-animasyon', dinle);
    return () => window.removeEventListener('farabi-animasyon', dinle);
  }, []);
  const motionMod = animMod === 'kapali' ? 'always' : animMod === 'oto' ? 'user' : 'never';
  const motionKapali = animMod === 'kapali' || (animMod === 'oto' && !!reduced);
  const bugunMu = veri.tarih === veri.bugun;
  const satirlar = durum.satirlar;
  const dersVar = satirlar.some((s) => s.durum !== 'ders_yok_o_gun');
  const aktif = aktifDers(veri.ders_saatleri, simdi, bugunMu && dersVar);

  const guncelle = useCallback(async () => {
    if (document.hidden || bekleyen.current) return;
    bekleyen.current = true;
    try {
      const d = await durumGetir(veri.tarih);
      setDurum(d);
      setHata(false);
      setSonGuncelleme(new Date().toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' }));
    } catch {
      setHata(true); // Son iyi veri yerinde kalır, yenileme hatası açıkça görünür.
    } finally {
      bekleyen.current = false;
    }
  }, [veri.tarih]);

  useEffect(() => {
    let kapali = false;
    const alarm = async () => {
      if (document.hidden) return;
      const d = await acilDurum();
      if (!kapali && d) setAcil(d);
    };
    const gorunur = () => {
      if (!document.hidden) { void guncelle(); void alarm(); setSimdi(istanbulSaati()); }
    };
    setSonGuncelleme(new Date().toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' }));
    void alarm();
    const durumTimer = setInterval(() => { void guncelle(); }, 60_000);
    const saatTimer = setInterval(() => setSimdi(istanbulSaati()), 30_000);
    const alarmTimer = setInterval(() => { void alarm(); }, 10_000);
    document.addEventListener('visibilitychange', gorunur);
    return () => {
      kapali = true;
      clearInterval(durumTimer); clearInterval(saatTimer); clearInterval(alarmTimer);
      document.removeEventListener('visibilitychange', gorunur);
    };
  }, [guncelle]);

  const onYenile = async () => {
    if (!bugunMu || yenileniyor) return;
    setYenileniyor(true);
    try {
      const r = await yenile(veri.tarih);
      if (r.basarili) { await guncelle(); window.farabiToast?.('Yenilendi.'); }
      else window.farabiToast?.(`Yenileme başarısız — ${r.detay || 'Bağlantı hatası'}`);
    } finally {
      setYenileniyor(false);
    }
  };
  const onBaslat = async (id: number, sinif: string) => {
    const r = await tahtaBaslat(id);
    window.farabiToast?.(r.basarili
      ? `${sinif}: ${r.durum === 'one_getirildi' ? 'pencere öne getirildi' : 'yoklama ekranı başlatıldı'}.`
      : `${sinif}: başlatılamadı — ${r.detay || 'Bağlantı hatası'}`);
    await guncelle();
  };
  // Tarih değişimi tam sayfa yükler: eski güne ait geç gelen istek yeni günün verisini ezemez.
  const onTarih = (t: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set('tarih', t);
    window.location.assign(url.toString());
  };

  return (
    <MotionConfig reducedMotion={motionMod} transition={motionKapali ? { duration: 0 } : YAY}>
      <UstSerit tarih={veri.tarih} bugun={veri.bugun}
                sonGuncelleme={sonGuncelleme} yenileniyor={yenileniyor} acil={acil}
                onTarih={onTarih} onYenile={() => { void onYenile(); }} />
      <AnimatePresence>
        {hata && (
          <motion.div
            key="hata-bant"
            role="status"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={YAY}
            className="mb-4 flex flex-wrap items-center gap-3 rounded-[20px] border border-white/15 bg-white/[0.06] px-4 py-3 text-[13px] text-white/75"
          >
            Yoklama verisi yenilenemedi; son başarılı kayıt gösteriliyor.
            <button type="button" className="underline transition-opacity hover:opacity-80" onClick={() => { void guncelle(); }}>Tekrar dene</button>
          </motion.div>
        )}
      </AnimatePresence>
      {/* Izgara her genişlikte önce gelir; KPI ve grafikler alt sıradadır. */}
      <div className="flex flex-col gap-4">
        <DersIzgarasi siniflar={veri.siniflar} saatler={veri.ders_saatleri} satirlar={satirlar}
                      sinifTahta={veri.sinif_tahta} tahtaAcik={durum.tahta_acik}
                      aktifDersNo={aktif?.no ?? null} onBaslat={onBaslat} />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <SuAn saatler={veri.ders_saatleri} satirlar={satirlar} tahtaAcik={durum.tahta_acik}
                sinifSayisi={veri.siniflar.length} bugunMu={bugunMu} simdi={simdi} />
          <KatilimHalkasi satirlar={satirlar} tahtaAcik={durum.tahta_acik} />
          <KatilimGrafigi tarih={veri.tarih} bugun={veri.bugun} satirlar={satirlar} onTarihSec={onTarih} />
        </div>
        <DersListesi saatler={veri.ders_saatleri} satirlar={satirlar} simdi={simdi} bugunMu={bugunMu}
                     sinifSayisi={veri.siniflar.length} />
      </div>
    </MotionConfig>
  );
};
