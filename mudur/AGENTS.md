# mudur

Müdür yardımcısının kaynak dosyaları; servis değil. Git'te yalnız `*.py` ve talimat dosyaları izlenir (`.gitignore`: `mudur/*`).
Repo PUBLIC: buraya öğrenci adı/veri yazma. Lint kapsamı dışı.
- ⚠️ `SINIF/` (öğrenci listeleri, doğum tarihi, telefon) ve idari belgeler kişisel veri: içeriğini OKUMA, dosya adı/boyut düzeyinde
  çalış ya da sor. Okuyanlar: `smssistemi/scripts/sinif_bilgi_ice_aktar.py`, Atos SQL (`mudur/SINIF/tcler`, TC). Yolları değiştirme.
- `ders_programi_yukle.py` ve `ders_programi.json`/`.md` ESKİ (2026-10-24): ders programının tek kaynağı `okul_ana`. `siniflar.pdf`
  yalnız ders programıdır, okunabilir.
