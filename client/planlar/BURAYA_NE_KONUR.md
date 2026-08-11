# planlar/ — MEB yıllık planları (Excel)

> ⚠️ **ARŞİV — hiçbir kod yolu tarafından okunmuyor (2026-08-09 itibarıyla
> doğrulandı).** Yıllık-plan hattı (`tools/plan_parse.py`, `icerik/plan.json`)
> **tamamen kaldırıldı**, yalnız bu dizindeki dosyalar kaldı; `client/CLAUDE.md`,
> "Project layout" bölümüne bakın. Aşağıdaki `plan_parse.py` komutu artık
> ÇALIŞMAZ — dosya yok. Konu/kazanım yalnızca öğretmenden gelir, plandan asla
> otomatik çıkarılmaz; bu davranışı geri getirmeyin.

Buraya **yıllık plan `.xlsx` dosyaları** konur. Başka bir şey konmaz — öğretmenin
kaynak materyali olarak depoda duruyor, hiçbir aracın girdisi değil.

~~Yeni plan eklendiğinde (ders anında değil, **bir kez, ders dışında**):~~

```bash
# ARTIK ÇALIŞMIYOR — plan_parse.py silindi, yalnızca tarihsel referans:
python tools/plan_parse.py planlar/ --json icerik/plan.json
python tools/dogrula.py                      # doğrulama kapısı
```

~~`plan_parse.py` bütün Maarif Modeli sütunlarını korur: kazanım kodları, süreç
bileşenleri, ölçme, sosyal-duygusal beceriler, değerler, okuryazarlık. Birleşik
hücreleri, Türkçe ay adlarını ve tatil satırlarını da işler.~~

## Bilinmesi gerekenler

- **Dosya adı önemlidir.** Bazı planların sayfa adı ders adı taşımıyor
  (`10. Sınıf`, `11.SINIF 2 SAAT` gibi); o durumda ders adı DOSYA ADINDAN
  çıkarılır. `Anadolu Liseleri Felsefe Yıllık Plan.xlsx` → FELSEFE.
- **Tarih hatası düzeltilmez, bildirilir.** MEB kaynağında `31 Kasım`,
  `6-110 Ekim` gibi yazım hataları var; bunlar tarihlenemez ve `dogrula.py`
  sayısını raporlar. Tarih uydurmak, sınıfa yanlış dersi anlatmak demektir.
- Bu klasördeki 29 dosya test verisi olarak depoda duruyor; okulun kendi
  planları da aynı klasöre konur.
