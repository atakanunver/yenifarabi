#!/bin/bash
# server/kitap_dagit.sh — ders kitabı PDF'lerini sunucudan tahtaların
# ~/DERSLER/<DERS>/ klasörlerine rsync ile kopyalar.
#
# 2026-11-25 (Atakan kararı, DECISIONS.md): öğretmen kitabı tahtada ağsız
# açabilsin diye ders kitapları tahtalara kopyalanır ("tahtada içerik deposu
# yok" kuralı bu iş için değişti).
#
# Kaynak: /mnt/farabi-data/farabi/kitaplar (server/main.py'nin kitap dizini).
# Hedef : tahtada /home/<kullanıcı>/DERSLER/<DERS>/ — DOĞRUDAN bu klasöre
#         (<DERS>/<DERS>/ alt klasörüne DEĞİL). DERS adları tahtalarda zaten
#         var olanlardır (aşağıdaki tabloda ve ONAYLI_DERSLER'de); yenisi
#         uydurulmaz. Home sembolik bağlarına (~/FİZİK vb.) dokunulmaz.
#
# Kapsam kuralı:
#   - Şubeli tahta (9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B): düzey derslik
#     adından çıkarılır ("11-A" -> 11) ve YALNIZ o düzeyin kitapları gider.
#   - Şubesiz tahta (fenlab, sporodasi): FİZİK + KİMYA + BİYOLOJİ, 9-12 hepsi.
#   - Başka ad (tahta-NNN vb.): düzey bilinmediği için HATA, gönderilmez.
#   - Dosya adından (ders, düzey) çıkarımı aşağıdaki AÇIK tabloyla yapılır.
#     Tabloda olmayan dosya "eşlenmemiş" diye listelenir ve GÖNDERİLMEZ
#     (tahmin yok). Düzeysiz ayt-kimya-2026.pdf 12. düzey kabul edilir.
#   - Kaynaktaki sembolik bağlar (biyoloji-12.pdf, felsefe-11.pdf) takma addır;
#     atlanır, hedef gerçek dosya (tabloda) gider — aynı kitap iki kez gitmez.
#
# Aktarım: rsync -rt --size-only --partial. YALNIZ eksik veya BOYUTU farklı
#   dosya gider (aynı boyutlu dosya mtime farklı olsa da yeniden gönderilmez).
#   --delete ASLA yok: tahtadaki öğretmen dosyaları silinmez. Hedefte aynı
#   adlı ama boyutu farklı dosya varsa ÜZERİNE YAZILIR (kuru çıktıda "~"
#   ile işaretlenir); aynı adlı aynı boyutlu dosyaya dokunulmaz. rsync dosyayı
#   geçici adla yazıp yer değiştirir; --partial kesilen aktarımı sürdürür
#   (yarım dosya hedef adında kalır, sonraki çalıştırmada boyut farkıyla
#   tamamlanır).
#
# Kullanım:
#   ./kitap_dagit.sh [--kuru] [--zorla] [--bwlimit=KB/s] [tahta ...]
#   tahta verilmezse VARSAYILAN_TAHTALAR (7 şubeli tahta + fenlab +
#   sporodasi). --kuru: rsync -n; her tahtaya gidecek dosyalar,
#   dosya sayısı ve toplam boyut gösterilir, hiçbir şey yazılmaz.
#   --bwlimit varsayılan 20000 KB/s (~160 Mbit/s) — okul ağını doldurmasın.
#
# Ders saati koruması: hafta içi 08:00-17:00 (Europe/Istanbul) GERÇEK kopyalama
#   REDDEDİLİR (yüzlerce MB'lık aktarım ders sırasında tahtayı/ağı yorar).
#   --kuru serbesttir; --zorla ile aşılabilir.
#
# Çıkış kodu: ulaşılamayan tahta / rsync hatası / düzeyi bilinmeyen tahta varsa 1.

set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAYNAK="/mnt/farabi-data/farabi/kitaplar"
KAYIT_DOSYASI="$BASE_DIR/tahtalar.json"
SSH_KEY="$HOME/.ssh/id_ed25519_tahta"
VARSAYILAN_TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab sporodasi)
SUBESIZ_TAHTALAR=(fenlab sporodasi)
SUBESIZ_DERSLER=("FİZİK" "KİMYA" "BİYOLOJİ")
ONAYLI_DERSLER=("ALMANCA" "BİLİŞİM" "BİYOLOJİ" "COĞRAFYA" "DİN KÜLTÜRÜ" "EDEBİYAT" "FELSEFE" "FİZİK" "GÖRSEL SANATLAR" "İNGİLİZCE" "KİMYA" "MATEMATİK" "SAĞLIK BİLGİSİ" "TARİH")

# dosya (KAYNAK'a göre) | DERS | düzey
ESLEME='
11.SINIF MAARIF SORU BANKASI MATEMATİK.pdf|MATEMATİK|11
12. Sınıf T.C. İnkılap Tarihi Ve Atatürkçülük Ders Kitabı-MEB.pdf|TARİH|12
9-sinif-biyoloji-fasikul-anlatim-rehberi.pdf|BİYOLOJİ|9
Biyoloji 12.pdf|BİYOLOJİ|12
Coğrafya 12.pdf|COĞRAFYA|12
ayt-kimya-2026.pdf|KİMYA|12
biyoloji-9.pdf|BİYOLOJİ|9
biyoloji-10.pdf|BİYOLOJİ|10
biyoloji-11.pdf|BİYOLOJİ|11
cagdas-turk-ve-dunya-tarihi-12.pdf|TARİH|12
cografya-9.pdf|COĞRAFYA|9
cografya-10.pdf|COĞRAFYA|10
cografya-11.pdf|COĞRAFYA|11
daf/daf_001_kimya_hayattir.pdf|KİMYA|9
daf/daf_002_atomdan_periyodik_tabloya.pdf|KİMYA|9
daf/daf_003_periyodik_sistem.pdf|KİMYA|9
daf/daf_004_etkilesimler.pdf|KİMYA|9
daf/daf_005_etkilesimden_maddeye.pdf|KİMYA|9
daf/daf_006_katilar_sivilar.pdf|KİMYA|9
daf/daf_007_nanoparçaciklar.pdf|KİMYA|9
din-kulturu-ve-ahlak-bilgisi-9.pdf|DİN KÜLTÜRÜ|9
din-kulturu-ve-ahlak-bilgisi-10.pdf|DİN KÜLTÜRÜ|10
din-10-meb-2025.pdf|DİN KÜLTÜRÜ|10
peygamberimizin-hayati-10.pdf|DİN KÜLTÜRÜ|10
din-kulturu-ve-ahlak-bilgisi-11.pdf|DİN KÜLTÜRÜ|11
din-kulturu-ve-ahlak-bilgisi-12.pdf|DİN KÜLTÜRÜ|12
ens-10-edebiyat-konu.pdf|EDEBİYAT|10
felsefe-10.pdf|FELSEFE|10
felsefe-dersi-11sinif-ders-kitabi_20261003_214213_339.pdf|FELSEFE|11
fizik_9.pdf|FİZİK|9
fizik-10.pdf|FİZİK|10
fizik-11.pdf|FİZİK|11
fizik-12.pdf|FİZİK|12
ingilizce-11.pdf|İNGİLİZCE|11
waymark-year-9-b1.1-ders-kitabi2.pdf|İNGİLİZCE|9
kimya_9.pdf|KİMYA|9
kimya-10.pdf|KİMYA|10
kimya-10-alternatif.pdf|KİMYA|10
kimya-11.pdf|KİMYA|11
maarif-kimya-11.pdf|KİMYA|11
kimya-12.pdf|KİMYA|12
matematik_9.pdf|MATEMATİK|9
matematik_9_2.pdf|MATEMATİK|9
matematik-10.pdf|MATEMATİK|10
matematik-11.pdf|MATEMATİK|11
temel-matematik-11.pdf|MATEMATİK|11
matematik-12.pdf|MATEMATİK|12
matematik-12-yeni-2025.pdf|MATEMATİK|12
temel-matematik-12-destek-2025.pdf|MATEMATİK|12
tarih-9.pdf|TARİH|9
tarih-10.pdf|TARİH|10
tarih-11.pdf|TARİH|11
turk_dili_ve_edebiyati_9.pdf|EDEBİYAT|9
turk-dili-ve-edebiyati-10_2.pdf|EDEBİYAT|10
turk-dili-ve-edebiyati-11.pdf|EDEBİYAT|11
turk-dili-ve-edebiyati-12.pdf|EDEBİYAT|12
'
# Bilerek eşlenmeyenler (kaynakta durur, tabloda yok -> "eşlenmemiş" çıkar):
#   10-mof-cozumsuz.pdf, 11-mof-cozumsuz.pdf  taranmış görüntü, metin yok; ders belirsiz
#   almancaa1.pdf                              Almanca A1.1, kitapta sınıf düzeyi yok
#   piytonbilisim.pdf, robotik.pdf, yapazeka.pdf  seçmeli BİLİŞİM, sınıf düzeyi yok

KURU=0
ZORLA=0
BWLIMIT=20000
TAHTALAR=()
for a in "$@"; do
    case "$a" in
        --kuru) KURU=1 ;;
        --zorla) ZORLA=1 ;;
        --bwlimit=*) BWLIMIT="${a#--bwlimit=}" ;;
        -*) echo "HATA: bilinmeyen seçenek: $a" >&2; exit 2 ;;
        *) TAHTALAR+=("$a") ;;
    esac
done
[[ "$BWLIMIT" =~ ^[0-9]+$ ]] || { echo "HATA: --bwlimit sayı olmalı (KB/s)" >&2; exit 2; }
[ ${#TAHTALAR[@]} -eq 0 ] && TAHTALAR=("${VARSAYILAN_TAHTALAR[@]}")

# Ders saati koruması (yalnız gerçek kopyalama)
if [ "$KURU" -eq 0 ] && [ "$ZORLA" -eq 0 ]; then
    gun=$(TZ=Europe/Istanbul date +%u)
    saat=$(TZ=Europe/Istanbul date +%H)
    if [ "$gun" -le 5 ] && [ "$((10#$saat))" -ge 8 ] && [ "$((10#$saat))" -lt 17 ]; then
        echo "RED: hafta içi 08:00-17:00 (TR) arası gerçek kopyalama yapılmaz. 17:00'den sonra çalıştır, ya da --kuru / --zorla kullan." >&2
        exit 3
    fi
fi

command -v rsync >/dev/null || { echo "HATA: sunucuda rsync yok" >&2; exit 1; }
[ -d "$KAYNAK" ] || { echo "HATA: kaynak yok: $KAYNAK" >&2; exit 1; }

# Tabloyu oku + doğrula
declare -A T_DERS T_DUZEY
TABLO=()
while IFS='|' read -r f ders duzey; do
    [ -z "$f" ] && continue
    ok=0; for d in "${ONAYLI_DERSLER[@]}"; do [ "$d" = "$ders" ] && ok=1; done
    [ "$ok" -eq 1 ] || { echo "HATA: tabloda onaysız ders adı: $ders ($f)" >&2; exit 1; }
    T_DERS["$f"]="$ders"; T_DUZEY["$f"]="$duzey"; TABLO+=("$f")
    [ -f "$KAYNAK/$f" ] || echo "UYARI: tabloda var ama kaynakta yok: $f" >&2
done <<< "$ESLEME"

# Eşlenmemiş / takma ad dosyaları bul
ESLENMEMIS=()
while IFS= read -r -d '' p; do
    rel="${p#"$KAYNAK"/}"
    if [ -L "$p" ]; then
        echo "takma ad atlandı: $rel -> $(readlink "$p")"
    elif [ -z "${T_DERS[$rel]+x}" ]; then
        ESLENMEMIS+=("$rel")
    fi
done < <(find "$KAYNAK" -mindepth 1 \( -type f -o -type l \) -print0 | LC_ALL=C sort -z)
echo "tablo: ${#TABLO[@]} dosya eşlendi; eşlenmemiş (GÖNDERİLMEZ): ${#ESLENMEMIS[@]}"
for e in "${ESLENMEMIS[@]}"; do echo "  eşlenmemiş: $e"; done

# tahtalar.json'dan kullanıcı ve IP (tahta-ssh.sh ile aynı mantık)
tahta_bilgi() {
    python3 -c "
import json, sys
kayit = json.load(open(sys.argv[1])).get(sys.argv[2])
if not kayit:
    sys.exit(1)
print(kayit['kullanici'], kayit['ip'])
" "$KAYIT_DOSYASI" "$1"
}

mb() { awk -v b="$1" 'BEGIN{printf "%.1f MB", b/1048576}'; }

HATA=0
for t in "${TAHTALAR[@]}"; do
    # Düzey / kapsam
    duzey=""; subesiz=0
    if [[ "$t" =~ ^(9|10|11|12)-[A-Z]$ ]]; then
        duzey="${BASH_REMATCH[1]}"
    else
        for s in "${SUBESIZ_TAHTALAR[@]}"; do [ "$s" = "$t" ] && subesiz=1; done
        if [ "$subesiz" -eq 0 ]; then
            echo "== $t: HATA — düzey çıkarılamadı (şubeli ad ya da fenlab/sporodasi değil)"; HATA=1; continue
        fi
    fi

    bilgi=$(tahta_bilgi "$t") || { echo "== $t: HATA — tahtalar.json'da kayıtlı değil"; HATA=1; continue; }
    read -r KULLANICI IP <<< "$bilgi"
    uzak_dizinler=$(timeout 30 "$BASE_DIR/tahta-ssh.sh" "$t" 'ls -1 ~/DERSLER 2>/dev/null || echo __DERSLER_YOK__' 2>/dev/null)
    if [ -z "$uzak_dizinler" ]; then
        echo "== $t: HATA — ulaşılamadı"; HATA=1; continue
    fi
    if [ "$uzak_dizinler" = "__DERSLER_YOK__" ]; then
        echo "== $t: HATA — tahtada ~/DERSLER yok (dizin düzeni farklı), gönderilmedi"; HATA=1; continue
    fi
    if [ "$subesiz" -eq 1 ]; then
        echo "== $t: kapsam FİZİK+KİMYA+BİYOLOJİ, 9-12"
    else
        echo "== $t: kapsam ${duzey}. sınıf kitapları"
    fi

    # Dersleri sıralı topla
    DERS_LISTESI=$(for f in "${TABLO[@]}"; do echo "${T_DERS[$f]}"; done | LC_ALL=C sort -u)
    t_yeni=0; t_guncel=0; t_bayt=0; t_hata=0
    while IFS= read -r ders; do
        [ -z "$ders" ] && continue
        dosyalar=()
        for f in "${TABLO[@]}"; do
            [ "${T_DERS[$f]}" = "$ders" ] || continue
            [ -f "$KAYNAK/$f" ] || continue
            if [ "$subesiz" -eq 1 ]; then
                uygun=0; for d in "${SUBESIZ_DERSLER[@]}"; do [ "$d" = "$ders" ] && uygun=1; done
                [ "$uygun" -eq 1 ] || continue
            else
                [ "${T_DUZEY[$f]}" = "$duzey" ] || continue
            fi
            dosyalar+=("$KAYNAK/$f")
        done
        [ ${#dosyalar[@]} -eq 0 ] && continue

        klasor_var=0
        while IFS= read -r u; do [ "$u" = "$ders" ] && klasor_var=1; done <<< "$uzak_dizinler"
        [ "$klasor_var" -eq 0 ] && echo "   $ders: UYARI — tahtada klasör yok, oluşturulacak"

        rs_secenek=(-rt8 --size-only --partial --no-motd --timeout=120 "--bwlimit=$BWLIMIT" -s
            --out-format='%i|%l|%n'
            -e "ssh -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=5")
        [ "$KURU" -eq 1 ] && rs_secenek+=(-n)
        cikti=$(rsync "${rs_secenek[@]}" "${dosyalar[@]}" "${KULLANICI}@${IP}:/home/${KULLANICI}/DERSLER/${ders}/" 2>&1)
        rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "   $ders: HATA — rsync çıkış kodu $rc"
            echo "$cikti" | grep -v '^<f' | head -5 | sed 's/^/      /'
            t_hata=1
        fi
        while IFS='|' read -r itemize boyut ad; do
            [[ "$itemize" == '<f'* ]] || continue
            t_bayt=$((t_bayt + boyut))
            if [[ "$itemize" == '<f+++++++++' ]]; then
                t_yeni=$((t_yeni + 1)); isaret="+"
            else
                t_guncel=$((t_guncel + 1)); isaret="~"
            fi
            echo "   $isaret $ders/$ad ($(mb "$boyut"))"
        done <<< "$cikti"
    done <<< "$DERS_LISTESI"

    [ "$t_hata" -eq 1 ] && HATA=1
    if [ "$KURU" -eq 1 ]; then
        etiket="gidecek"
    else
        etiket="kopyalandı"
    fi
    echo "== $t: $etiket: $((t_yeni + t_guncel)) dosya ($t_yeni yeni, $t_guncel üzerine yazılan), $(mb "$t_bayt")"
done
[ "$KURU" -eq 1 ] && echo "(kuru çalıştırma — hiçbir dosya değiştirilmedi; + yeni, ~ boyutu farklı olduğu için üzerine yazılır)"
exit $HATA
