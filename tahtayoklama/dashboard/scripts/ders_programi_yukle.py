#!/usr/bin/env python3
"""dashboard/scripts/ders_programi_yukle.py — mudur/siniflar.pdf (aSc k12'nin
ürettiği "Toplu Çarşaf Liste : Sınıflar" çıktısı) içindeki haftalık ders
programını okuyup tahtayoklama/data/ders_programi.json'u (dashboard/
ders_programi.py'nin okuduğu şema) üretir.

mudur/ders_programi_yukle.py'deki PDF-çözme mantığının BİREBİR aynısının
tahtayoklama'ya taşınmış hâli — ama farklı iş yapıyor: mudur'unki ürettiği
JSON'u Farabi client'ına (RAG/ders içeriği için gerekli) SSH ile dağıtıyor,
bu script bunu YAPMAZ. tahtayoklama/data/ders_programi.json yalnızca
dashboard sunucusu (`dashboard/ders_programi.py`) kendi diskinden okuyor —
pano hücrelerindeki ders kısa adı etiketi için (bkz. CLAUDE.md "Ders kısa
adı etiketi"), tahtalara hiç gönderilmiyor; yoklama.py'nin bundan haberi
yok ve olması gerekmiyor.

mudur/siniflar.pdf'e cross-project salt-okunur erişim, scripts/
ilk_yukleme.py'nin server/tahtalar.json okumasıyla aynı desen — mudur/
klasörü koda bağlı değil (kök .gitignore'da), bu yalnızca tek seferlik
(dönem başı, program değiştikçe elle) bir okuma.

Kısaltma → tam ders adı eşlemesi (aşağıdaki KISALTMALAR) mudur/
ders_programi_yukle.py'dekiyle senkron tutulmalı — biri güncellenirse
diğeri de güncellenmeli (iki ayrı script, TEK doğru eşleme yok, bkz. o
dosyanın kendi docstring'i). Bu, `dashboard/ders_programi.py`'deki
KISALTMALAR sözlüğüyle KARIŞTIRILMAMALI — o TAM ders adını pano etiketi
kısaltmasına çevirir (matematik -> MAT), bu ise PDF kısaltmasını TAM ders
adına çevirir (Mat -> matematik). Ters yönler, ayrı dosyalar.

Çalıştırma (dashboard/ dizininden)
------------------------------------
pdfplumber dashboard'un ana venv'inde YOK (yalnızca bu script kullanıyor,
uygulamanın geri kalanı ihtiyaç duymuyor) — önce:
    venv/bin/pip install -r scripts/requirements-ekstra.txt

Sonra:
    venv/bin/python scripts/ders_programi_yukle.py
    venv/bin/python scripts/ders_programi_yukle.py --pdf /baska/yol.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pdfplumber

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
TAHTAYOKLAMA_DIR = DASHBOARD_DIR.parent
VARSAYILAN_PDF_YOLU = TAHTAYOKLAMA_DIR.parent / "mudur" / "siniflar.pdf"
JSON_CIKTI = TAHTAYOKLAMA_DIR / "data" / "ders_programi.json"
MD_CIKTI = TAHTAYOKLAMA_DIR / "data" / "ders_programi.md"

# Kolon sırası PDF'teki gün bloklarıyla birebir (8'er kolon): Pazartesi,
# Salı, Çarşamba, Perşembe, Cuma — dashboard/ders_programi.py'nin
# _GUN_ADLARI'ndeki isoweekday eşlemesiyle aynı sırada olmalı.
GUNLER = ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
GUN_BASLIK = {
    "pazartesi": "Pazartesi", "sali": "Salı", "carsamba": "Çarşamba",
    "persembe": "Perşembe", "cuma": "Cuma",
}

# aSc kısaltması -> tam ders adı. mudur/ders_programi_yukle.py'nin
# KISALTMALAR sözlüğüyle SENKRON tutulmalı (bkz. yukarıdaki docstring notu).
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
    "Hedef": "sınav hazırlık çalışması",
    "SSpor": "spor etkinlikleri",
    "Sağlık": "sağlık bilgisi ve trafik kültürü",
    "SDin": "din kültürü ve ahlak bilgisi",
    "SAlm": "almanca",
    "SBiyo": "biyoloji",
    "SCoğ": "coğrafya",
    "SFizik": "fizik",
    "SKimya": "kimya",
    "SMat": "matematik",
    "SMatUyg": "matematik uygulamaları",
    "SOTarih": "osmanlı türkçesi",
    "SPeygamber": "peygamberimizin hayatı",
    "SPsiko": "psikoloji",
    "STDE": "türk dili ve edebiyatı",
    "STarih": "tarih",
    "SÇağdaş": "çağdaş türk ve dünya tarihi",
    "İnk": "inkılap tarihi ve atatürkçülük",
}

TAHMIN_ISARETLI = {
    "SSpor", "Sağlık", "SMatUyg", "SOTarih", "SPeygamber", "STDE", "SÇağdaş",
}


def tabloyu_oku(pdf_yolu: Path) -> list[list[str | None]]:
    with pdfplumber.open(pdf_yolu) as pdf:
        tablolar = pdf.pages[0].extract_tables()
    if not tablolar:
        raise RuntimeError(f"{pdf_yolu}'da tablo bulunamadı — PDF formatı değişmiş olabilir.")
    return tablolar[0]


def _temizle(hucre: str | None) -> str | None:
    if hucre is None:
        return None
    return hucre.replace("\n", "").strip() or None


def _ders_adi(kisaltma: str) -> str:
    tam = KISALTMALAR.get(kisaltma)
    if tam is None:
        raise ValueError(
            f"Bilinmeyen kısaltma: {kisaltma!r} — bu script'teki KISALTMALAR "
            "sözlüğüne (ve mudur/ders_programi_yukle.py'dekine) eklenmeden "
            "devam edilemez (sessizce atlamak pano'nun yanlış/eksik ders "
            "göstermesine yol açar)."
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", type=Path, default=VARSAYILAN_PDF_YOLU, help=f"Kaynak PDF (varsayılan: {VARSAYILAN_PDF_YOLU})")
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"HATA: {args.pdf} bulunamadı.")

    print(f"[1/3] {args.pdf} okunuyor...")
    tablo = tabloyu_oku(args.pdf)

    print("[2/3] Tablo çözülüyor...")
    siniflar, kullanilan = programi_coz(tablo)

    cikti = {
        "_kaynak": f"{args.pdf.name} (aSc k12)",
        "_uretim_araci": "tahtayoklama/dashboard/scripts/ders_programi_yukle.py",
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

    print("\n[3/3] Bitti. (Tahtalara dağıtım YOK — bu dosya yalnızca dashboard'un kendisi tarafından okunuyor.)")


if __name__ == "__main__":
    main()
