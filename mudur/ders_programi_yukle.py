#!/usr/bin/env python3
"""
mudur/ders_programi_yukle.py — mudur/siniflar.pdf (aSc k12'nin ürettiği
"Toplu Çarşaf Liste : Sınıflar" çıktısı) içindeki haftalık ders programını
okur, client/core/program.py'nin beklediği şemada (bkz. client/config/
ders_programi.example.json — bu makinede client/ sparse-checkout dışında
olduğu için 11-B'den SSH ile okunup doğrulandı) tek bir JSON + okunabilir
bir markdown üretir, sonra şu an açık VE Farabi client'ı kurulu tahtalara
(2026-09-13 SSH ile tek tek doğrulandı) SSH ile yazar.

Neden
-----
`core/program.py` "hangi derste olduğunu" yalnızca config/ders_programi.json
varsa VE `_ornek` değilse bilir; yoksa Farabi sınıfa sormak zorunda kalır
(bkz. o dosyanın kendi docstring'i — bilerek: uydurma veriyle çalışmak,
veri yokluğundan daha tehlikeli). Okul idaresi programı her dönem aSc k12
ile PDF olarak üretiyor (`mudur/siniflar.pdf` — mudur/ klasörü koda bağlı
değil, gitignore'lu, bkz. kök .gitignore). Bu script o PDF'i makine-okunur
hale çevirip tahtalara dağıtan TEK SEFERLİK (dönem başı, program değiştikçe
elle) bir araçtır — otomatik/periyodik ÇALIŞMAZ, crontab'a eklenmedi.

Kısaltma → tam ders adı eşlemesi
--------------------------------
aSc çıktısındaki kısaltmalar (pdfplumber ile PDF'in kendi vektör tablosundan
okunuyor, OCR/resim değil — `mudur/siniflar.pdf` 0 gömülü resim, 1 gerçek
tablo içeriyor, 2026-09-13'te doğrulandı) KISALTMALAR sözlüğünde elle tam
ada çevriliyor. "S" öneki "seçmeli" demek. "Hedef" (2026-09-13 kullanıcı
onayı) = sınav hazırlık çalışması, normal öğretmenli bir ders gibi ele
alınıyor. TAHMIN_ISARETLI kümesindeki adlar MEB'in yaygın seçmeli ders
adlarından en olası eşleşmeyle dolduruldu — KESİN DEĞİL, script sonunda
ayrıca ekrana basılıyor; idareyle bir kez teyit edilmesi önerilir.

Çalıştırma
----------
server/venv'de pdfplumber zaten kurulu (tahtayoklama'nın da kullandığı
paket, ayrıca kurulum gerekmedi):
    server/venv/bin/python mudur/ders_programi_yukle.py

Yalnızca JSON/markdown üretir, tahtalara YAZMAZ:
    server/venv/bin/python mudur/ders_programi_yukle.py --no-deploy
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pdfplumber

BASE_DIR = Path(__file__).resolve().parent
PDF_YOLU = BASE_DIR / "siniflar.pdf"
JSON_CIKTI = BASE_DIR / "ders_programi.json"
MD_CIKTI = BASE_DIR / "ders_programi.md"

SSH_ANAHTARI = Path.home() / ".ssh" / "id_ed25519_tahta"
TAHTALAR_JSON = BASE_DIR.parent / "server" / "tahtalar.json"
SSH_BAGLANTI_ZAMAN_ASIMI_SN = 5
SSH_KOMUT_ZAMAN_ASIMI_SN = 15

# Kolon sırası PDF'teki gün bloklarıyla birebir (8'er kolon): Pazartesi,
# Salı, Çarşamba, Perşembe, Cuma. Anahtarlar client/core/program.py'nin
# GUN_ANAHTARI listesiyle birebir aynı olmalı.
GUNLER = ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
GUN_BASLIK = {
    "pazartesi": "Pazartesi", "sali": "Salı", "carsamba": "Çarşamba",
    "persembe": "Perşembe", "cuma": "Cuma",
}

# aSc kısaltması -> tam ders adı (client/config/ders_programi.example.json'daki
# stille aynı: küçük harf, tam Türkçe ad).
KISALTMALAR = {
    "Mat": "matematik",
    "Fizik": "fizik",
    "Kimya": "kimya",
    "Biyo": "biyoloji",
    "Tarih": "tarih",
    "TDE": "türk dili ve edebiyatı",
    "Coğ": "coğrafya",
    "Felsefe": "felsefe",
    "İng": "ingilizce",
    "DKAB": "din kültürü ve ahlak bilgisi",
    "Görsel": "görsel sanatlar",
    "Beden": "beden eğitimi",
    "Rehber": "rehberlik",
    "Bilisim": "bilişim teknolojileri ve yazılım",
    "Hedef": "sınav hazırlık çalışması",              # 2026-09-13 kullanıcı onayı
    "SSpor": "spor etkinlikleri",                      # ⚠ tahmin
    "Sağlık": "sağlık bilgisi ve trafik kültürü",      # ⚠ tahmin
    "SDin": "din kültürü ve ahlak bilgisi",
    "SAlm": "almanca",
    "SBiyo": "biyoloji",
    "SCoğ": "coğrafya",
    "SFizik": "fizik",
    "SKimya": "kimya",
    "SMat": "matematik",
    "SMatUyg": "matematik uygulamaları",               # ⚠ tahmin
    "SOTarih": "osmanlı türkçesi",                     # ⚠ tahmin
    "SPeygamber": "peygamberimizin hayatı",            # ⚠ tahmin
    "SPsiko": "psikoloji",
    "STDE": "türk dili ve edebiyatı",                  # ⚠ tahmin
    "STarih": "tarih",
    "SÇağdaş": "çağdaş türk ve dünya tarihi",          # ⚠ tahmin
    "İnk": "inkılap tarihi ve atatürkçülük",
}

# 2026-09-13 DÜZELTME: "S" öneki daha önce "seçmeli X" olarak yazılıyordu
# (ör. "seçmeli fizik") — ama client/actions/ders_icerigi.py::_ders_eslesir
# (kitap_sorusu'nun DB kitap eşleşmesi) sorgudaki HER kelimenin hedefte
# (kitap.ders) alt dize olarak geçmesini istiyor; "seçmeli" kelimesi "Fizik"
# içinde hiç geçmediği için eşleşme SIFIRA düşüyordu — canlı DB'ye karşı
# ölçüldü (12-A'nın yarınki ilk 3 bloğu: seçmeli fizik/kimya/biyoloji, hepsi
# kitap_id=None döndü). Kitabın kendisi seçmeli/zorunlu ayrımı yapmıyor
# (aynı MEB kitabı), o yüzden "seçmeli" öneki RAG eşleşmesi için hiç
# gerekli değil — üstteki tabloda tamamen kaldırıldı, yalnızca ders adı
# kaldı (ör. "seçmeli fizik" -> "fizik").

TAHMIN_ISARETLI = {
    "SSpor", "Sağlık", "SMatUyg", "SOTarih", "SPeygamber", "STDE", "SÇağdaş",
}

# Yalnızca ŞU AN Farabi client'ı kurulu VE açık tahtalar (2026-09-13 SSH ile
# tek tek doğrulandı: 9-B/10-A/11-A/12-B'de ~/farabi/client YOK). 9-A'nın
# kendi klasör yapısı FARKLI — bkz. kök CLAUDE.md "9-A'nın kendi mekanizması"
# notu (repo tam klon, gerçek client repo/client altında).
HEDEF_TAHTALAR = {
    "9-A": "~/farabi/repo/client/config/ders_programi.json",
    "11-B": "~/farabi/client/config/ders_programi.json",
    "12-A": "~/farabi/client/config/ders_programi.json",
}


def tabloyu_oku() -> list[list[str | None]]:
    with pdfplumber.open(PDF_YOLU) as pdf:
        tablolar = pdf.pages[0].extract_tables()
    if not tablolar:
        raise RuntimeError(f"{PDF_YOLU}'da tablo bulunamadı — PDF formatı değişmiş olabilir.")
    return tablolar[0]


def _temizle(hucre: str | None) -> str | None:
    if hucre is None:
        return None
    return hucre.replace("\n", "").strip() or None


def _ders_adi(kisaltma: str) -> str:
    tam = KISALTMALAR.get(kisaltma)
    if tam is None:
        raise ValueError(
            f"Bilinmeyen kısaltma: {kisaltma!r} — mudur/ders_programi_yukle.py'deki "
            "KISALTMALAR sözlüğüne eklenmeden devam edilemez (sessizce atlamak "
            "Farabi'nin yanlış/eksik ders söylemesine yol açar)."
        )
    return tam


def programi_coz(tablo: list[list[str | None]]) -> tuple[dict, set[str]]:
    """Ham pdfplumber tablosunu {sinif: {gun: {saat: ders}}} sözlüğüne çevirir.

    PDF'teki birleştirilmiş (çift saatlik) hücreler pdfplumber'da ikinci
    hücrede None olarak gelir — bir önceki dolu değer o hücreye taşınır.
    """
    siniflar: dict[str, dict[str, dict[str, str]]] = {}
    kullanilan: set[str] = set()

    for satir in tablo[2:]:  # ilk 2 satır başlık: gün adları + saat numaraları
        sinif = satir[0]
        if not sinif:
            continue
        hucreler = [_temizle(h) for h in satir[1:41]]

        son_deger: str | None = None
        doldurulmus: list[str | None] = []
        for h in hucreler:
            if h is not None:
                son_deger = h
            doldurulmus.append(son_deger)

        gunluk: dict[str, dict[str, str]] = {}
        for gun_index, gun in enumerate(GUNLER):
            saatler: dict[str, str] = {}
            for saat_index in range(8):
                kisaltma = doldurulmus[gun_index * 8 + saat_index]
                if not kisaltma:
                    continue
                kullanilan.add(kisaltma)
                saatler[str(saat_index + 1)] = _ders_adi(kisaltma)
            gunluk[gun] = saatler
        siniflar[sinif] = gunluk

    return siniflar, kullanilan


def markdown_uret(siniflar: dict[str, dict[str, dict[str, str]]]) -> str:
    satirlar = ["# Ders Programı", "", "Kaynak: `mudur/siniflar.pdf`", ""]
    for sinif, gunluk in siniflar.items():
        satirlar.append(f"## {sinif}")
        satirlar.append("")
        satirlar.append("| Saat | " + " | ".join(GUN_BASLIK[g] for g in GUNLER) + " |")
        satirlar.append("|" + "---|" * (len(GUNLER) + 1))
        for saat in range(1, 9):
            hucre = [gunluk.get(g, {}).get(str(saat), "") for g in GUNLER]
            satirlar.append(f"| {saat} | " + " | ".join(hucre) + " |")
        satirlar.append("")
    return "\n".join(satirlar)


def _ssh_ile_yaz(ip: str, kullanici: str, uzak_yol: str, icerik: bytes) -> tuple[bool, str]:
    komut = f"cat > {uzak_yol}.tmp && mv {uzak_yol}.tmp {uzak_yol}"
    argumanlar = [
        "ssh", "-i", str(SSH_ANAHTARI),
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={SSH_BAGLANTI_ZAMAN_ASIMI_SN}",
        f"{kullanici}@{ip}", komut,
    ]
    try:
        sonuc = subprocess.run(
            argumanlar, input=icerik, capture_output=True,
            timeout=SSH_KOMUT_ZAMAN_ASIMI_SN,
        )
    except subprocess.TimeoutExpired:
        return False, "SSH zaman aşımına uğradı"
    return sonuc.returncode == 0, sonuc.stderr.decode("utf-8", errors="replace")


def tahtalara_dagit(json_bytes: bytes) -> None:
    tahtalar = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
    for derslik, uzak_yol in HEDEF_TAHTALAR.items():
        kayit = tahtalar.get(derslik)
        if not kayit:
            print(f"  ⚠ {derslik}: server/tahtalar.json'da kayıtlı değil, atlandı.")
            continue
        basarili, hata = _ssh_ile_yaz(kayit["ip"], kayit["kullanici"], uzak_yol, json_bytes)
        if basarili:
            print(f"  ✓ {derslik}: {uzak_yol} yazıldı.")
        else:
            print(f"  ✗ {derslik}: HATA — {hata.strip()[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-deploy", action="store_true",
                         help="Yalnızca JSON/markdown üret, tahtalara yazma.")
    args = parser.parse_args()

    print(f"[1/4] {PDF_YOLU} okunuyor...")
    tablo = tabloyu_oku()

    print("[2/4] Tablo çözülüyor...")
    siniflar, kullanilan = programi_coz(tablo)

    cikti = {
        "_kaynak": "mudur/siniflar.pdf (aSc k12, Ders Planı Oluşturuldu: 12.09.2026)",
        "_uretim_araci": "mudur/ders_programi_yukle.py",
        "siniflar": siniflar,
    }
    JSON_CIKTI.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_CIKTI.write_text(markdown_uret(siniflar), encoding="utf-8")
    print(f"    -> {JSON_CIKTI}")
    print(f"    -> {MD_CIKTI}")

    tahmin_edilenler = kullanilan & TAHMIN_ISARETLI
    if tahmin_edilenler:
        print("\n⚠ Aşağıdaki ders adları TAHMİN edildi, idareyle teyit edilmesi önerilir:")
        for kis in sorted(tahmin_edilenler):
            print(f"    {kis} -> {KISALTMALAR[kis]}")

    if args.no_deploy:
        print("\n[3/4] --no-deploy verildi, tahtalara yazılmadı.")
        return

    print(f"\n[3/4] Tahtalara dağıtılıyor ({', '.join(HEDEF_TAHTALAR)})...")
    # Tahtaya yazılan dosyadaki _kaynak/_uretim_araci gibi ekstra alanlar
    # program.py için zararsız — yalnızca 'siniflar' okunuyor, '_ornek' yoksa
    # dosya geçerli sayılıyor (bkz. core/program.py::cizelge).
    tahtalara_dagit(json.dumps(cikti, ensure_ascii=False, indent=2).encode("utf-8"))

    print("\n[4/4] Bitti.")


if __name__ == "__main__":
    main()
