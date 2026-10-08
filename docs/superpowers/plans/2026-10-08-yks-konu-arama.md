# YKS çıkmış soru araması — konu eşleşmesi + kapak/uydurma hatası (2026-10-08)

## Olay (11-A 10:10, 11-B 09:32)
Öğretmen "dörtgenlerde açı ile ilgili soru" istedi. Gemini `yks_sorulari(ders='matematik',
konu='DÖRTGENLERDE AÇI')` çağırdı. Sunucu `AYT_EA_1 s.113` döndü = AYT-EA **Matematik kapak
sayfası** (görsel doğrulandı). Kapağın metninde soru yok → 11-B'de model "[Soru metni ekranda]"
dedi, 11-A'da **"ABCD dörtgeninde m(DAB)=80°…" sorusunu uydurdu** (sayfada yok). "Sonraki" →
s.117 (eşitsizlik), yeniden arama → s.118 (çokgen sembolü) — ikisi de konu dışı.

## Kök nedenler (yks.py)
1. `ders` kelimesi ("matematik") puana katılıyor; her matematik sayfasının başlığında geçtiği için
   tüm sayfalar 0,5 alıyor, eşitlikte dosya/sayfa sırası kazanıyor → ilk sayfa = kapak.
2. Sayfanın soru içerip içermediği kontrol edilmiyor (kapak, TOPLAM tabloları, cevap anahtarı,
   `TYT_Yıllara_Gore_Soru_Dagılımı` aday olabiliyor).
3. Kelime eşleşmesi ek kırpmıyor ("dörtgenlerde" ≠ "dörtgen"), `len>3` "açı"yı atıyor.
4. Alaka eşiği yok → konu dışı sayfa yine "eşleşen soru" diye sunuluyor.
5. Sunum metni "metinde soru yoksa uydurma" demiyor.

## Değişiklikler (yalnızca server, client'a dokunulmaz)
1. **`server/yks_konu_haritasi.py`** (yeni, tek seferlik/yeniden çalıştırılabilir script):
   PDF yer imleri (TOC) + sayfadaki beyaz kalın konu bantları birleşik → sayfa→konu haritası,
   konu bir sonraki etikete kadar ileri taşınır; TOPLAM/yıl/SAYFA/ÜNİTE/KONU gürültüsü atılır,
   cevap anahtarı sayfalarında durur. Çıktı `/mnt/farabi-data/farabi/icerik/eslemeler/yks_konu.json`.
2. **`yks.py`**:
   - Haritayı tembel yükle; dosya yoksa eski davranış (fail-open).
   - Soru sayfası filtresi: şık (`A)`…`E)`) ve/veya `20xx-TYT/AYT` etiketi yoksa sayfa aday olmaz.
   - Puan yalnızca `konu`dan; `ders` yalnız filtre. Kök/önek eşleşmesi (≥4 harf ortak kök;
     "aci" gibi 3 harfliler yalnızca tam kelime), durak kelimeleri (ile, ilgili, soru, sorusu…).
     `metin_araclari` DEĞİŞMEZ (icerik.py de kullanıyor), eşleştirme yks.py içinde.
   - Konu etiketi eşleşmesi güçlü puan; yalnız gövde eşleşmesi zayıf. Eşik altı → `bos`
     ("bulamadım" konu dışı sayfadan iyidir).
   - Farklı dosyalarda aynı sayfa (EA_1 s.181 = SAY s.79) tekilleştirilir.
   - `_sunum_metni`ne: "Bu sayfada birden çok soru olabilir; YALNIZCA aşağıdaki metinde geçen
     soruyu oku. Metinde soru/şık okunamıyorsa soru UYDURMA, 'soru ekranda' de." + sayfanın konusu.
3. **Testler** (`tests/test_yks.py`): dörtgenlerde açı → dörtgen etiketli sayfa; kapak/şıksız sayfa
   asla dönmez; yalnız ders kelimesiyle eşleşme → `bos`; mevcut başlık-filtresi testleri geçer.
4. Gerçek veride elle doğrulama: dörtgenlerde açı, üçgende açı, olasılık, millî mücadele,
   divan edebiyatı.
5. `sudo systemctl restart farabi-api.service`, DECISIONS.md kaydı. Son kabul: tahtada Atakan.

## Kapsam dışı (ayrı karar)
- "10 soru oluştur" — üretme aracı yok (soruhavuzu bağlanabilir, ayrı özellik).
- Kitap RAG'ı (`/api/egitim/question`) reranker kapalı olduğu için bilinçli olarak `hata` döner.
