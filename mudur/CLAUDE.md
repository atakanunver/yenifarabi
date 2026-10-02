# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**`mudur/` — müdür yardımcısının kaynak dosyaları, servis değil.** Git'te
yalnızca `*.py` ve bu dosya izlenir (`.gitignore`: `mudur/*`); PDF/JPEG/
JSON/MD/Excel diskte kalır. Repo PUBLIC — buraya öğrenci adı ya da veri
yazma.

## İçerik ve onu okuyanlar

| Dosya | Ne | Kim okur |
|---|---|---|
| `siniflar.pdf` | aSc k12 "Toplu Çarşaf Liste : Sınıflar" haftalık program | `ders_programi_yukle.py` (bu dizin), `tahtayoklama/dashboard/scripts/ders_programi_yukle.py` |
| `ders_programi.json` / `.md` | yukarıdaki PDF'in çıktısı | `server/config_dagit.sh` → tahtaların `client/config/ders_programi.json`'ı |
| `giris cikis saatleri.jpg` | zil saatleri | elle okunup `tahtayoklama/dashboard/scripts/zil_yukle.py::VARSAYILAN_SAATLER`'e gömüldü |
| `SINIF/` (Excel + PDF) | öğrenci listeleri, doğum tarihleri, telefonlar — **kişisel veri** | `smssistemi/scripts/sinif_bilgi_ice_aktar.py` |
| `IPLER.html`, `vestel akıllı tahtalar.jpg` | tahta envanteri notları | — (kanonik kayıt `server/tahtalar.json`) |

## `ders_programi_yukle.py`

Dönem başında / program değişince elle çalıştırılır (cron yok). PDF'i
`client/core/program.py` şemasında JSON + MD'ye çevirir ve `server/
tahtalar.json`'daki açık tahtalara SSH ile yazar.

```bash
python3 mudur/ders_programi_yukle.py --no-deploy   # yalnızca JSON/MD üret, tahtalara yazma
```

- `KISALTMALAR` sözlüğü `tahtayoklama/dashboard/scripts/
  ders_programi_yukle.py`'dekiyle **elle senkron** tutulmalı — tek kaynak
  yok; sapması geçmişte seçmeli ders adlarının RAG'de eşleşmemesine yol
  açtı. `TAHMIN_ISARETLI` adlar kesin değil, script sonunda raporlanır.
- Program üç kopyada yaşar (kök CLAUDE.md "Ders programı ve zil
  saatleri"); bu script yalnızca client kopyasını günceller.

## Okuma sınırı

`SINIF/` altındaki Excel/PDF'ler ve `ders_programi.*` dışındaki idari
belgeler öğrenci/veli/personel verisi içerir: buluta (Claude dahil)
gönderilmemesi için **içeriklerini okuma**; gerekirse dosya adı/boyut
düzeyinde çalış ya da kullanıcıya sor. `siniflar.pdf` yalnızca ders
programıdır, okunabilir.
