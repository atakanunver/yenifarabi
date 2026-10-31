#!/usr/bin/env python3
"""Linux /proc üzerinden ders görsel gözlemci kaynak ölçümü."""

import argparse
import json
import os
import re
import time
from pathlib import Path


def cpu_yuzdesi(tick_farki, gecen_saniye, clk_tck):
    """İşlemci kullanımını bir çekirdeğin yüzdesi olarak hesapla."""
    if gecen_saniye <= 0 or clk_tck <= 0 or tick_farki < 0:
        raise ValueError("Geçersiz CPU ölçüm aralığı")
    return 100.0 * tick_farki / (clk_tck * gecen_saniye)


def rss_parse(status):
    """status metnindeki VmRSS değerini MiB olarak döndür."""
    eslesme = re.search(r"^VmRSS:\s*(\d+)\s+kB\s*$", status, re.MULTILINE)
    if not eslesme:
        raise ValueError("VmRSS bulunamadı")
    return int(eslesme.group(1)) / 1024.0


def log_parse(metin):
    """Logdaki iki p95 değerinin ayrı ayrı en büyüklerini döndür."""
    sonuc = {}
    for anahtar in ("grab_p95", "karsilastirma_p95"):
        sayilar = re.findall(
            rf"(?<![\w]){anahtar}\s*=\s*(\d+(?:\.\d+)?)(?![\w.])",
            metin,
        )
        sonuc[anahtar] = max(map(float, sayilar), default=None)
    return sonuc


def esik_karari(deger, esik):
    """Eksik veri için None, diğer durumlarda eşik sonucunu döndür."""
    return None if deger is None else deger <= esik


def stat_tick(stat):
    """Parantez içindeki komut adında boşluk veya parantez bulunabilir."""
    alanlar = stat[stat.rindex(")") + 2 :].split()
    return int(alanlar[11]) + int(alanlar[12])


def pid_bul(ad, proc=Path('/proc')):
    kendisi = {os.getpid(), os.getppid()}
    for yol in proc.iterdir():
        if yol.name.isdigit() and int(yol.name) not in kendisi:
            try:
                # Argümanın adı tam eşleşmeli; adı komut metninde geçen kabuk eşleşmesin.
                argv = (yol / 'cmdline').read_bytes().split(b'\0')
                if any(Path(a.decode(errors='replace')).name == ad for a in argv if a):
                    return int(yol.name)
            except (OSError, ProcessLookupError):
                continue
    return None


def pozitif(metin):
    try:
        deger = float(metin)
        if not 0 < deger < float('inf'):
            raise ValueError
        return deger
    except ValueError as hata:
        raise argparse.ArgumentTypeError('Pozitif ve sonlu sayı gerekli') from hata


def olc(pid, sure, aralik, proc=Path('/proc')):
    yol = proc / str(pid)
    clk_tck = os.sysconf('SC_CLK_TCK')
    cpu, rss = [], []
    bitti = time.monotonic() + sure
    onceki_tick = onceki_zaman = None
    kesildi = False
    while True:
        try:
            stat = (yol / 'stat').read_text()
            durum = (yol / 'status').read_text()
            zaman = time.monotonic()
            tick = stat_tick(stat)
            rss.append(rss_parse(durum))
            if onceki_tick is not None:
                cpu.append(cpu_yuzdesi(tick - onceki_tick, zaman - onceki_zaman, clk_tck))
            onceki_tick, onceki_zaman = tick, zaman
        except (OSError, ValueError, IndexError):
            kesildi = True
            break
        kalan = bitti - time.monotonic()
        if kalan <= 0:
            break
        time.sleep(min(aralik, kalan))
    return cpu, rss, kesildi


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    grup = parser.add_mutually_exclusive_group(required=True)
    grup.add_argument('--pid', type=int)
    grup.add_argument('--ad')
    parser.add_argument('--sure-dk', type=pozitif, default=10)
    parser.add_argument('--aralik-sn', type=pozitif, default=2)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--cpu-esik', type=float, default=5)
    parser.add_argument('--rss-esik', type=float, default=50)
    parser.add_argument('--grab-esik', type=float, default=40)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.pid is not None and args.pid <= 0:
        parser.error('--pid pozitif olmalı')
    pid = args.pid if args.pid is not None else pid_bul(args.ad)
    cpu, rss, kesildi = olc(pid, args.sure_dk * 60, args.aralik_sn) if pid else ([], [], True)
    log = {'grab_p95': None, 'karsilastirma_p95': None}
    if args.log:
        try:
            log = log_parse(args.log.read_text(encoding='utf-8', errors='replace'))
        except OSError as hata:
            parser.error(f'Log okunamadı: {hata}')
    ort_cpu = sum(cpu) / len(cpu) if cpu else None
    kararlar = {
        'cpu': esik_karari(ort_cpu, args.cpu_esik),
        'rss_artis': esik_karari(max(rss) - rss[0] if rss else None, args.rss_esik),
        'grab': esik_karari(log['grab_p95'], args.grab_esik),
    }
    sonuc = {
        'pid': pid, 'ornek_sayisi': len(rss), 'cpu_ornek_sayisi': len(cpu),
        'cpu_ortalama_yuzde': ort_cpu, 'cpu_en_yuksek_yuzde': max(cpu, default=None),
        'rss_baslangic_mib': rss[0] if rss else None,
        'rss_ortalama_mib': sum(rss) / len(rss) if rss else None,
        'rss_en_yuksek_mib': max(rss, default=None),
        'grab_p95_ms': log['grab_p95'], 'karsilastirma_p95_ms': log['karsilastirma_p95'],
        'esikler': kararlar, 'surec_sona_erdi': kesildi,
        'genel_sonuc': 'SÜREÇ YOK' if kesildi else (
            'AŞTI' if False in kararlar.values() else 'GEÇTİ'),
    }
    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    else:
        def goster(deger):
            return 'veri yok' if deger is None else f'{deger:.2f}'

        print(f"PID: {pid if pid else 'veri yok'} | Örnek sayısı: {len(rss)}")
        print(f"CPU ortalama/en yüksek (%): {goster(ort_cpu)} / {goster(sonuc['cpu_en_yuksek_yuzde'])}")
        print(f"RSS başlangıç/ortalama/en yüksek (MiB): {goster(sonuc['rss_baslangic_mib'])} / "
              f"{goster(sonuc['rss_ortalama_mib'])} / {goster(sonuc['rss_en_yuksek_mib'])}")
        print(f"grab ms p95: {goster(log['grab_p95'])} | karşılaştırma ms p95: "
              f"{goster(log['karsilastirma_p95'])}")
        for ad, karar in kararlar.items():
            print(f"{ad}: {'veri yok' if karar is None else 'GEÇTİ' if karar else 'AŞTI'}")
        print(f"Genel sonuç: {sonuc['genel_sonuc']}")
    return 2 if kesildi else 1 if False in kararlar.values() else 0


if __name__ == '__main__':
    raise SystemExit(main())
