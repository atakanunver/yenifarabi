#!/usr/bin/env python3
"""
tools/mikrofon_test.py — Canlı mikrofon seviye göstergesi.

Kullanım:
    python tools/mikrofon_test.py            # 20 saniye ölç
    python tools/mikrofon_test.py --sure 40
    python tools/mikrofon_test.py --kazanc 3 # yazılımsal 3x kazançla dene

Neden gerekli:
"Farabi beni duymuyor" şikâyetinde sorunun mikrofon seviyesinde mi yoksa
transkripsiyonda mı olduğunu ayırt etmek gerekiyor. Log'a bakarak yapılan
ölçümler işe yaramadı çünkü konuşmanın TAM OLARAK NE ZAMAN olduğu
bilinmiyordu — iki kez yanlış teşhise yol açtı. Bu betik seviyeyi anlık
gösterir: konuşurken çubuğun hareket ettiğini kendi gözünle görürsün.

10 tahtalı dağıtımda da işe yarar: her tahtanın mikrofonunu kurulumda
tek komutla doğrulamak için.

    Yorumlama: --karsilastir kipi tabanı kendisi ölçer, oranı yorumlar.
    Canlı kipteki mutlak eşikler (150/400) yalnızca kaba göstergedir;
    gürültü tabanı kazançla 40 kat değiştiği için karar oranla verilir.
"""

import argparse
import sys
import time

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    sys.exit("gerekli: pip install sounddevice numpy")

ORNEKLEME = 16000          # main.py ile aynı
BLOK      = 1024


def _cubuk(rms: float, genislik: int = 42) -> str:
    """
    Seviye çubuğu — KAREKÖK ölçek.

    İlk sürüm logaritmik ölçek kullanıyordu ve ilgili aralığı sıkıştırıyordu:
    rms 500 -> 29 çubuk, rms 5000 -> 40 çubuk. Yani oda sesi ile konuşma
    görsel olarak ayrışmıyordu ve "seviye hiç değişmiyor" izlenimi verdi —
    yanlış bir teşhise yol açtı. Karekök ölçek 0-3000 aralığını yayar:
    rms 100 -> 8, rms 500 -> 17, rms 2000 -> 34 çubuk.
    """
    dolu = int(min(1.0, (max(rms, 0) / 3000.0) ** 0.5) * genislik)
    return "█" * dolu + "·" * (genislik - dolu)


def _yorum(rms: float, tepe: int) -> str:
    if tepe >= 32767:
        return "KIRPILMA! kazanç çok yüksek"
    if rms >= 400:
        return "KONUŞMA"
    if rms >= 150:
        return "zayıf"
    return "sessiz"


def _olc(sure: float, kazanc: float, aygit) -> tuple[float, int]:
    """Belirtilen süre kadar dinle, (ortalama rms, tepe) döndür."""
    r = sd.rec(int(sure * ORNEKLEME), samplerate=ORNEKLEME, channels=1,
               dtype="int16", device=aygit)
    sd.wait()
    d = np.asarray(r, dtype=np.float64).flatten() * kazanc
    d = np.clip(d, -32768, 32767)
    return float(np.sqrt((d ** 2).mean())), int(np.abs(d).max())


def karsilastir(kazanc: float, aygit) -> None:
    """
    İki fazlı ölçüm: önce sessizlik (gürültü tabanı), sonra konuşma.
    Sonucu MUTLAK eşikle değil, tabanla KARŞILAŞTIRARAK yorumlar — böylece
    hangi mikrofon, hangi kazanç olduğu fark etmez ve yoruma gerek kalmaz.
    """
    print("\n1. AŞAMA — SESSİZ KALIN (5 saniye, gürültü tabanı ölçülüyor)")
    for i in (3, 2, 1):
        print(f"   {i}...", flush=True); time.sleep(1)
    taban, taban_tepe = _olc(5, kazanc, aygit)
    print(f"   gürültü tabanı: rms={int(taban)}  tepe={taban_tepe}")

    print("\n2. AŞAMA — ŞİMDİ NORMAL SESLE KONUŞUN (6 saniye)")
    for i in (3, 2, 1):
        print(f"   {i}...", flush=True); time.sleep(1)
    print("   >>> KONUŞ <<<", flush=True)
    ses, ses_tepe = _olc(6, kazanc, aygit)
    print(f"   konuşma      : rms={int(ses)}  tepe={ses_tepe}")

    oran = ses / taban if taban > 0 else float("inf")
    print("\n" + "=" * 58)
    print(f"GÜRÜLTÜ TABANI : rms {int(taban):6d}   tepe {taban_tepe:6d}")
    print(f"KONUŞMA        : rms {int(ses):6d}   tepe {ses_tepe:6d}")
    print(f"ORAN           : {oran:.1f}x")
    print("=" * 58)

    if ses_tepe >= 32000:
        print("SONUC: KIRPILMA. Kazanc cok yuksek, sinyal bozuluyor.")
        print("       pactl set-source-volume @DEFAULT_SOURCE@ 60%")
    elif oran >= 3.0:
        print("SONUC: MIKROFON IYI. Sesiniz ortam gurultusunden net ayrisiyor.")
        print("       Farabi hala duymuyorsa sorun SES KATMANINDA DEGIL,")
        print("       transkripsiyon tarafindadir.")
    elif oran >= 1.6:
        print("SONUC: SINIRDA. Ses ayrisiyor ama zayif; transkripsiyon")
        print("       guvenilmez olur. Mikrofona yaklasin ya da kazanci")
        print("       dusurup tekrar deneyin (taban duser, oran artar):")
        print("       pactl set-source-volume @DEFAULT_SOURCE@ 70%")
    else:
        print("SONUC: SESINIZ MIKROFONA ULASMIYOR. Konusma, ortam")
        print("       gurultusunden ayrismiyor. Kontrol listesi:")
        print("       1) Donanim mikrofon kapatma tusu/anahtari acik mi")
        print("       2) Mikrofon delikleri kapali mi (kilif, el, toz)")
        print("       3) pactl list short sources -> baska kaynak denenmeli")
        print("       4) Harici/USB mikrofon varsa onu deneyin")


def main() -> None:
    ap = argparse.ArgumentParser(description="Canlı mikrofon seviye göstergesi")
    ap.add_argument("--karsilastir", action="store_true",
                    help="iki fazlı ölçüm: sessizlik + konuşma, kendi kendini kalibre eder")
    ap.add_argument("--sure", type=int, default=20, help="ölçüm süresi (saniye)")
    ap.add_argument("--aygit", default=None, help="ses aygıtı (varsayılan: sistem)")
    ap.add_argument("--kazanc", type=float, default=1.0,
                    help="yazılımsal kazanç çarpanı (örn. 3)")
    a = ap.parse_args()

    aygit = a.aygit
    try:
        bilgi = sd.query_devices(aygit if aygit is not None else sd.default.device[0])
        print(f"Aygıt : {bilgi['name']}")
    except Exception as e:
        print(f"Aygıt bilgisi alınamadı: {e}")

    if a.karsilastir:
        karsilastir(a.kazanc, aygit)
        return

    print(f"Süre  : {a.sure} sn      Kazanç: {a.kazanc}x")
    print("\n>>> KONUŞMAYA BAŞLA — çubuğun hareket ettiğini görmelisin <<<\n")

    # Akış açılırken bir "pop" oluşuyor ve tepe 32768'e vuruyor. İlk sürüm
    # tüm koşunun global maksimumuna bakıp KIRPILMA sanıyor ve kazancı
    # DÜŞÜRMEYİ öneriyordu — gerçekte kazanç YÜKSELTİLMESİ gerekiyordu.
    # Çözüm: ilk blokları at, kırpılmayı tek tepeye değil kırpılan örnek
    # ORANINA göre karar ver.
    ATLA_BLOK = 8                  # ~0.5 sn başlangıç geçici rejimi
    en_yuksek_rms = 0.0
    en_yuksek_tepe = 0
    konusma_sayisi = 0
    olcum_sayisi = 0
    kirpik_ornek = 0
    toplam_ornek = 0
    rms_listesi: list[float] = []

    def geri(indata, frames, zaman, durum):
        nonlocal en_yuksek_rms, en_yuksek_tepe, konusma_sayisi, olcum_sayisi
        nonlocal kirpik_ornek, toplam_ornek
        olcum_sayisi += 1
        if olcum_sayisi <= ATLA_BLOK:
            return                      # başlangıç geçici rejimi
        d = np.asarray(indata, dtype=np.float64).flatten() * a.kazanc
        d = np.clip(d, -32768, 32767)
        rms = float(np.sqrt((d ** 2).mean()))
        tepe = int(np.abs(d).max())
        rms_listesi.append(rms)
        kirpik_ornek += int((np.abs(d) >= 32700).sum())
        toplam_ornek += d.size
        if rms > en_yuksek_rms:
            en_yuksek_rms = rms
        if tepe > en_yuksek_tepe:
            en_yuksek_tepe = tepe
        if rms >= 400:
            konusma_sayisi += 1
        # her ~5 blokta bir yaz (saniyede ~3 satır)
        # Satır satır yaz (\r değil): çıktı kopyalanıp paylaşılabilsin.
        if olcum_sayisi % 8 == 0:
            print(f"  {_cubuk(rms)}  rms={int(rms):5d} tepe={tepe:5d}  "
                  f"{_yorum(rms, tepe)}", flush=True)

    try:
        with sd.InputStream(samplerate=ORNEKLEME, channels=1, dtype="int16",
                            blocksize=BLOK, device=aygit, callback=geri):
            time.sleep(a.sure)
    except Exception as e:
        sys.exit(f"\nMikrofon açılamadı: {type(e).__name__}: {e}")

    if not rms_listesi:
        sys.exit("Ölçüm alınamadı.")
    dizi  = np.array(rms_listesi)
    taban = float(np.percentile(dizi, 10))    # sessiz anlar
    tepe_rms = float(np.percentile(dizi, 95)) # en gürültülü %5 (konuşma)
    kirpik_oran = (kirpik_ornek / toplam_ornek * 100) if toplam_ornek else 0.0
    oran = tepe_rms / taban if taban > 0 else float("inf")

    print("\n" + "─" * 60)
    print(f"Gürültü tabanı (%10)  : rms {int(taban)}")
    print(f"En yüksek seviye (%95): rms {int(tepe_rms)}")
    print(f"Oran                  : {oran:.1f}x")
    print(f"Kırpılan örnek        : %{kirpik_oran:.2f}")
    print("─" * 60)

    # Kırpılma kararı tek tepeye değil ORANA bakar: akış açılışındaki tek
    # "pop" bütün koşuyu yanlış etiketliyordu.
    if kirpik_oran > 0.1:
        print("SONUC: KIRPILMA (orneklerin %.2f%%'i tavanda). Kazanci DUSUR:" % kirpik_oran)
        print("        pactl set-source-volume @DEFAULT_SOURCE@ 70%")
    elif tepe_rms >= 1500:
        print("SONUC: MIKROFON IYI. Konusma yeterli seviyede geliyor.")
        print("        Farabi hala duymuyorsa sorun SES KATMANINDA DEGIL,")
        print("        transkripsiyon tarafindadir.")
    elif oran >= 5:
        print("SONUC: Sesin YAKALANIYOR ama SEVIYE COK DUSUK.")
        print(f"       Konusma rms {int(tepe_rms)}; saglikli aralik 1500-8000.")
        print("       Mikrofon bozuk degil, KAZANC YETERSIZ. Sirayla dene:")
        print("        pactl set-source-volume @DEFAULT_SOURCE@ 200%")
        print("        (yetmezse 300%; sonra bu testi tekrar calistir)")
    else:
        print("SONUC: Konusma ortam sesinden ayrismiyor. Kontrol listesi:")
        print("        1) pactl get-source-mute @DEFAULT_SOURCE@")
        print("        2) Donanim mikrofon kapatma tusu / anahtari")
        print("        3) pactl list short sources -> dogru kaynak secili mi")
        print("        4) Mikrofona 20 cm mesafeden konusarak tekrar dene")


if __name__ == "__main__":
    main()
