"""osym_analiz.py — osym veri tabanı için tutarsızlık (tutarlılık) kontrolleri ve temel veri analizi.

    osym/venv/bin/python osym_analiz.py            # rapor stdout'a; yalnızca SELECT
Çıktıda her kontrol: [TAMAM] / [UYARI] / [HATA] satırı. Kişisel veri (TC, ad) basılmaz; yalnızca sayılar.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

import psycopg
from osym_yukle import dsn

_SONUCLAR = Counter()
PUAN_ESLEME = {"SAY": "SAYISAL", "EA": "EŞİT AĞIRLIK", "SÖZ": "SÖZEL", "TYT": "TYT", "DİL": "YABANCI DİL"}


def rapor(durum: str, mesaj: str):
    _SONUCLAR[durum] += 1
    print(f"  [{durum}] {mesaj}")


def baslik(t: str):
    print(f"\n== {t}")


def tc_gecerli(s: str) -> bool:
    """T.C. kimlik numarası sağlama basamakları."""
    if not (s and len(s) == 11 and s.isdigit() and s[0] != "0"):
        return False
    d = [int(x) for x in s]
    return d[9] == ((sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10) and d[10] == sum(d[:10]) % 10


def sorgu(c, q, *p):
    return c.execute(q, p).fetchall()


def kapsam(c):
    baslik("1. Kapsam (yıl × rapor)")
    yillar = range(2022, 2027)
    raporlar = ["yerlestirme", "yerlestirme_puani", "ham_puan", "dogru_yanlis_tyt", "dogru_yanlis_ayt"]
    var = {(y, r): n for y, r, n in sorgu(c, "SELECT yil, rapor, count(*) FROM yukleme GROUP BY 1,2")}
    for y in yillar:
        eksik = [r for r in raporlar if (y, r) not in var]
        if eksik:
            rapor("UYARI", f"{y}: eksik rapor -> {', '.join(eksik)}")
        else:
            rapor("TAMAM", f"{y}: 5 rapor da var")


def tc_kontrol(c):
    baslik("2. T.C. kimlik no sağlama (guncel görünümler)")
    for tablo in ("yerlestirme_guncel", "yks_puan_guncel", "dogru_yanlis_guncel"):
        tcler = {r[0] for r in sorgu(c, f"SELECT DISTINCT tc_kimlik FROM {tablo}")}
        gecersiz = sum(1 for t in tcler if not tc_gecerli(t))
        rapor("TAMAM" if not gecersiz else "HATA", f"{tablo}: {len(tcler)} farklı TC, geçersiz {gecersiz}")


def tekrar_kontrol(c):
    baslik("3. Yinelenen kayıtlar")
    n = sorgu(c, "SELECT count(*) FROM (SELECT yil, tc_kimlik FROM yerlestirme_guncel GROUP BY 1,2 HAVING count(*)>1) x")[0][0]
    rapor("TAMAM" if n == 0 else "UYARI", f"yerlestirme_guncel: aynı yıl+TC birden fazla satır: {n}")
    n = sorgu(c, "SELECT count(*) FROM (SELECT yil, rapor, tc_kimlik, puan_turu FROM yks_puan_guncel GROUP BY 1,2,3,4 HAVING count(*)>1) x")[0][0]
    rapor("TAMAM" if n == 0 else "UYARI", f"yks_puan_guncel: aynı yıl+rapor+TC+tür birden fazla satır: {n}")
    ayni, farkli = sorgu(c, """SELECT count(*) FILTER (WHERE d = 1), count(*) FILTER (WHERE d > 1) FROM (
            SELECT count(DISTINCT (dogru, yanlis, bos, ham)) d FROM dogru_yanlis_guncel GROUP BY yil, sinav, test, tc_kimlik HAVING count(*) > 1) x""")[0]
    rapor("TAMAM" if farkli == 0 else "HATA", f"dogru_yanlis_guncel: iki dosyada kesişen test+öğrenci: aynı değerli {ayni}, FARKLI değerli {farkli}")
    n = sorgu(c, "SELECT count(*) FROM (SELECT 1 FROM yerlestirme_guncel GROUP BY yil, tc_kimlik, donem, program_kodu, puan_turu, puan HAVING count(*)>1) x")[0][0]
    rapor("TAMAM" if n == 0 else "UYARI", f"yerlestirme_guncel: birebir aynı satır iki kez geçen kayıt: {n}")
    n = sorgu(c, "SELECT count(*) FROM (SELECT tc_kimlik FROM yerlestirme_guncel GROUP BY 1 HAVING count(DISTINCT yil)>1) x")[0][0]
    rapor("TAMAM" if n == 0 else "UYARI", f"yerlestirme_guncel: birden fazla yılda yerleşen aynı kişi: {n}")


def eksik_alan_kontrol(c):
    baslik("4. Boş kritik alanlar (yerlestirme_guncel)")
    for alan in ("program_adi", "universite", "puan_turu", "puan", "obp", "tercih_sirasi"):
        n, top = sorgu(c, f"SELECT count(*) FILTER (WHERE {alan} IS NULL), count(*) FROM yerlestirme_guncel")[0]
        rapor("TAMAM" if n == 0 else "UYARI", f"{alan}: {n}/{top} boş")


def surum_kontrol(c):
    baslik("5. Aynı yıl+rapor için birden fazla dosya sürümü")
    for y, r in sorgu(c, "SELECT yil, rapor FROM yukleme GROUP BY 1,2 HAVING count(*)>1 ORDER BY 1,2"):
        kume = defaultdict(set)
        tablo = {"yerlestirme": "yerlestirme", "yerlestirme_puani": "yks_puan", "ham_puan": "yks_puan"}.get(r, "dogru_yanlis")
        for yid, tcx in sorgu(c, f"SELECT yukleme_id, tc_kimlik FROM {tablo} WHERE yil=%s AND yukleme_id IN (SELECT id FROM yukleme WHERE yil=%s AND rapor=%s)", y, y, r):
            kume[yid].add(tcx)
        dosyalar = sorgu(c, "SELECT id, dosya, satir, birincil FROM yukleme WHERE yil=%s AND rapor=%s ORDER BY dosya_zamani", y, r)
        farkli = {frozenset(v) for v in kume.values()}
        if len(farkli) == 1:
            rapor("TAMAM", f"{y} {r}: {len(dosyalar)} sürüm, kişi kümesi aynı (satır {sorted({d[2] for d in dosyalar})})")
        else:
            ayrinti = "; ".join(f"id{d[0]}:{len(kume[d[0]])} kişi{'*' if d[3] else ''}" for d in dosyalar)
            rapor("UYARI", f"{y} {r}: sürümler farklı kişi kümesi içeriyor ({ayrinti}; *=birincil)")


def capraz_kontrol(c):
    baslik("6. Raporlar arası tutarlılık")
    for y, in sorgu(c, "SELECT DISTINCT yil FROM yerlestirme_guncel ORDER BY 1"):
        yer = {r[0] for r in sorgu(c, "SELECT tc_kimlik FROM yerlestirme_guncel WHERE yil=%s", y)}
        yp = {r[0] for r in sorgu(c, "SELECT tc_kimlik FROM yks_puan_guncel WHERE yil=%s AND rapor='yerlestirme_puani'", y)}
        hp = {r[0] for r in sorgu(c, "SELECT tc_kimlik FROM yks_puan_guncel WHERE yil=%s AND rapor='ham_puan'", y)}
        dy = {r[0] for r in sorgu(c, "SELECT tc_kimlik FROM dogru_yanlis_guncel WHERE yil=%s", y)}
        if not yp:
            rapor("UYARI", f"{y}: puan raporları yok, yerleşen {len(yer)} kişi çapraz kontrol edilemedi")
            continue
        for ad, kume in (("yerlestirme_puani", yp), ("ham_puan", hp), ("dogru_yanlis", dy)):
            eksik = len(yer - kume)
            rapor("TAMAM" if eksik == 0 else "UYARI", f"{y}: yerleşen {len(yer)} kişiden {eksik} kişi {ad} raporunda yok")
        fazla = len(dy - hp)
        rapor("TAMAM" if fazla == 0 else "UYARI", f"{y}: doğru-yanlış raporunda olup ham puan raporunda olmayan öğrenci: {fazla}")
        rapor("TAMAM" if yp == hp else "UYARI", f"{y}: yerlestirme_puani ({len(yp)}) ve ham_puan ({len(hp)}) kişi kümeleri {'aynı' if yp == hp else 'farklı'}")
        # yerleştirme puanı = ham puan + OBP katkısı → ham puan, yerleştirme puanından büyük olamaz
        bozuk = sorgu(c, """SELECT count(*) FROM yks_puan_guncel a JOIN yks_puan_guncel b
            ON a.yil=b.yil AND a.tc_kimlik=b.tc_kimlik AND a.puan_turu=b.puan_turu
            WHERE a.yil=%s AND a.rapor='ham_puan' AND b.rapor='yerlestirme_puani' AND a.puan > b.puan + 0.001""", y)[0][0]
        rapor("TAMAM" if bozuk == 0 else "HATA", f"{y}: ham puanı yerleştirme puanından büyük olan kayıt: {bozuk}")
        # yerlestirme.puan, yks_puan (yerlestirme_puani) ile aynı mı
        fark = tut = 0
        for tcx, tur, puan in sorgu(c, "SELECT tc_kimlik, puan_turu, puan FROM yerlestirme_guncel WHERE yil=%s AND puan IS NOT NULL", y):
            eslesen = sorgu(c, "SELECT puan FROM yks_puan_guncel WHERE yil=%s AND rapor='yerlestirme_puani' AND tc_kimlik=%s AND puan_turu=%s", y, tcx, PUAN_ESLEME.get(tur, tur))
            if eslesen and eslesen[0][0] is not None:
                tut += 1
                fark += abs(float(eslesen[0][0]) - float(puan)) > 0.01
        if tut:
            rapor("TAMAM" if fark == 0 else "UYARI", f"{y}: yerleştiği puan türündeki puan, puan raporuyla {tut} kayıtta karşılaştırıldı, farklı {fark}")


def net_kontrol(c):
    baslik("7. Doğru-yanlış iç tutarlılığı")
    # net = doğru - yanlış/4 ; HAM sütunu net olmalı
    for sinav in ("TYT", "AYT"):
        n, bozuk = sorgu(c, "SELECT count(*), count(*) FILTER (WHERE abs((dogru - yanlis/4.0) - ham) > 0.011) FROM dogru_yanlis_guncel WHERE ham IS NOT NULL AND sinav=%s", sinav)[0]
        rapor("TAMAM" if bozuk == 0 else "UYARI", f"{sinav}: HAM = D - Y/4 kuralı: {n} kayıttan {bozuk} sapma")
    for y, test, k, mn, mx in sorgu(c, """SELECT yil, left(test,32), count(*), round(min((dogru-yanlis/4.0)-ham),2), round(max((dogru-yanlis/4.0)-ham),2)
            FROM dogru_yanlis_guncel WHERE ham IS NOT NULL AND abs((dogru-yanlis/4.0)-ham)>0.011 GROUP BY 1,2 ORDER BY 1,2"""):
        print(f"      sapma: {y} '{test}' {k} kayıt, D-Y/4 - HAM = {mn}..{mx}")
    # D+Y+B her testte sabit (soru sayısı) olmalı
    for y, sinav, test, adet, mn, mx in sorgu(c, """SELECT yil, sinav, test, count(*), min(dogru+yanlis+coalesce(bos,0)), max(dogru+yanlis+coalesce(bos,0))
            FROM dogru_yanlis_guncel GROUP BY 1,2,3 HAVING min(dogru+yanlis+coalesce(bos,0)) <> max(dogru+yanlis+coalesce(bos,0)) ORDER BY 1,2,3"""):
        rapor("UYARI", f"{y} {sinav} '{test}': D+Y+B sabit değil ({mn}..{mx}, {adet} kayıt)")
    n = sorgu(c, "SELECT count(*) FROM dogru_yanlis_guncel WHERE dogru < 0 OR yanlis < 0 OR dogru > 120")[0][0]
    rapor("TAMAM" if n == 0 else "HATA", f"negatif/aşırı doğru-yanlış değeri: {n}")
    n = sorgu(c, "SELECT count(*) FROM yks_puan_guncel WHERE puan < 100 OR puan > 600 OR basari_sirasi <= 0")[0][0]
    rapor("TAMAM" if n == 0 else "UYARI", f"aralık dışı puan (100..600) ya da başarı sırası <= 0: {n}")


def istatistik_kontrol(c):
    baslik("8. Word genel istatistik ↔ Excel verisi")
    for r in sorgu(c, "SELECT yil, son_sinif, basvuran, kazanan, tercih_yapan, lisans, onlisans_sinavsiz, onlisans_sinavli, aof, toplam_yerlesen FROM genel_istatistik ORDER BY yil"):
        y, son, bas, kaz, terc, lis, ons, onl, aof, top = r
        parca = sum(x or 0 for x in (lis, ons, onl, aof))
        if top is not None and parca != top:
            rapor("UYARI", f"{y}: lisans+önlisans+AÖF = {parca}, toplam yerleşen = {top}")
        for ad, kucuk, buyuk in (("başvuran>son sınıf", bas, son), ("kazanan>başvuran", kaz, bas), ("tercih yapan>kazanan", terc, kaz), ("yerleşen>tercih yapan", top, terc)):
            if kucuk is not None and buyuk is not None and kucuk > buyuk:
                rapor("UYARI", f"{y}: {ad} ({kucuk} > {buyuk})")
    for y, ist in sorgu(c, "SELECT yil, toplam_yerlesen FROM genel_istatistik WHERE yil BETWEEN 2022 AND 2026 ORDER BY yil"):
        say = sorgu(c, "SELECT count(DISTINCT tc_kimlik) FROM yerlestirme_guncel WHERE yil=%s", y)[0][0]
        if say == 0:
            rapor("UYARI", f"{y}: Excel'de yerleştirme verisi yok (Word: {ist})")
        else:
            rapor("TAMAM" if say == ist else "UYARI", f"{y}: Word toplam yerleşen {ist}, Excel (birincil dosya) {say} kişi")
    for y, mez, giren, yer, oran, son, bas, top in sorgu(c, """SELECT o.yil, o.mezun, o.sinava_giren, o.yerlesen, o.oran, g.son_sinif, g.basvuran, g.toplam_yerlesen
            FROM ozet_son5 o LEFT JOIN genel_istatistik g USING (yil) ORDER BY 1"""):
        if son is None:
            rapor("UYARI", f"{y}: ozet_son5 var, genel_istatistik (Word) yok")
            continue
        for ad, a, b in (("mezun/son sınıf", mez, son), ("sınava giren/başvuran", giren, bas), ("yerleşen/toplam yerleşen", yer, top)):
            rapor("TAMAM" if a == b else "UYARI", f"{y}: özet Excel ↔ Word {ad}: {a} ↔ {b}")
        if mez and yer is not None and oran is not None and abs(float(oran) - yer / mez) > 0.001:
            rapor("UYARI", f"{y}: özet oranı {float(oran):.3f}, yerleşen/mezun {yer / mez:.3f}")
    yillar = [r[0] for r in sorgu(c, "SELECT yil FROM genel_istatistik ORDER BY yil")]
    atlanan = [y for y in range(yillar[0], yillar[-1] + 1) if y not in yillar]
    rapor("TAMAM" if not atlanan else "UYARI", f"Word yıl serisi {yillar[0]}-{yillar[-1]}: eksik yıl {atlanan or 'yok'}")


def analiz(c):
    baslik("9. Analiz (son 5 yıl, birincil dosyalar)")
    print("  Yıl | Yerleşen | Ort.puan | Ort.OBP | Lisans | Önlisans(MYO) | En çok puan türü")
    for y, n, ort, obp in sorgu(c, "SELECT yil, count(DISTINCT tc_kimlik), round(avg(puan),1), round(avg(obp),1) FROM yerlestirme_guncel GROUP BY 1 ORDER BY 1"):
        myo = sorgu(c, "SELECT count(*) FROM yerlestirme_guncel WHERE yil=%s AND (fakulte ILIKE '%%meslek%%' OR fakulte ILIKE '%%myo%%' OR fakulte ILIKE '%%yüksekokul%%')", y)[0][0]
        tur = sorgu(c, "SELECT puan_turu, count(*) FROM yerlestirme_guncel WHERE yil=%s GROUP BY 1 ORDER BY 2 DESC LIMIT 1", y)[0]
        print(f"  {y} | {n:8} | {ort or '-':>8} | {obp or '-':>7} | {n - myo:6} | {myo:13} | {tur[0]} ({tur[1]})")
    print("\n  Yerleşme oranı (Word özet): yıl, son sınıf, başvuran, yerleşen, yerleşen/son sınıf %")
    for y, son, bas, top in sorgu(c, "SELECT yil, son_sinif, basvuran, toplam_yerlesen FROM genel_istatistik ORDER BY yil"):
        oran = f"{100 * top / son:.0f}%" if son and top is not None else "-"
        print(f"  {y}: son sınıf {son}, başvuran {bas}, yerleşen {top} -> {oran}")
    print("\n  TYT net ortalaması (HAM) yıl bazında:")
    for y, test, ort, adet in sorgu(c, "SELECT yil, test, round(avg(ham),1), count(*) FROM dogru_yanlis_guncel WHERE sinav='TYT' AND ham IS NOT NULL GROUP BY 1,2 ORDER BY 1, 3 DESC"):
        print(f"  {y} {test[:28]:28} ort net {ort} ({adet} öğrenci)")
    print("\n  TYT puan/başarı sırası (ham_puan): yıl, öğrenci, ort puan, medyan sıra")
    for y, n, ort, med in sorgu(c, "SELECT yil, count(*), round(avg(puan),1), percentile_cont(0.5) WITHIN GROUP (ORDER BY basari_sirasi)::int FROM yks_puan_guncel WHERE rapor='ham_puan' AND puan_turu='TYT' GROUP BY 1 ORDER BY 1"):
        print(f"  {y}: {n} öğrenci, ort {ort}, medyan başarı sırası {med}")
    print("\n  En çok tercih edilen üniversiteler (5 yıl):")
    for u, n in sorgu(c, "SELECT universite, count(*) FROM yerlestirme_guncel GROUP BY 1 ORDER BY 2 DESC LIMIT 5"):
        print(f"  {n:3} {u}")


def main() -> int:
    with psycopg.connect(dsn()) as c:
        for f in (kapsam, tc_kontrol, tekrar_kontrol, eksik_alan_kontrol, surum_kontrol, capraz_kontrol, net_kontrol, istatistik_kontrol, analiz):
            f(c)
    print(f"\nÖzet: {dict(_SONUCLAR)}")
    return 1 if _SONUCLAR["HATA"] else 0


if __name__ == "__main__":
    sys.exit(main())
