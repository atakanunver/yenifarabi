# Ekran özeti (`ekrani_ozetle`) — tasarım

Tarih: 2026-10-03 · Durum: onaylandı (sohbette, bölüm bölüm) · Kapsam: ilk alt proje

## Amaç

Öğretmen tahtada kendi PDF okuyucusunda / EBA'da / tarayıcıda bir ders kitabı
sayfası açar ve Farabi'ye "bu sayfayı özetle" ya da "anlat" der. Farabi o an
ekranda görüneni okur, sınıf düzeyine uygun bir özet (ya da ders anlatımı)
hazırlar, panelde gösterir ve sesli anlatır. Ders bu sırada beklemez.

Bağlam: RAG 2026-10-03'te kapatıldı (`RAG_AKTIF = False`), iki GPU yerel
`farabi-qwen3.8:27b`'ye ayrıldı (DECISIONS.md 2026-10-03). Kitap metni buluta
gidebilir (2026-09-29 kararı).

## Kararlar (kullanıcı)

- Sayfa kaynağı: öğretmenin kendi PDF/EBA/tarayıcısı — Farabi hangi kitap /
  sayfa olduğunu **bilmez**, bu yüzden ekran görüntüsü + OCR şart.
- Çıktı: özet panelde gösterilir **ve** Farabi ona dayanarak sesli anlatır.
- Çok sayfa: yalnızca o an **görünen** içerik (1–2 sayfa). 3 sayfa için
  öğretmen ikinci kez ister. Sayfa toplama / otomatik kaydırma yok.
- Kapsam: yalnızca anında ekran özeti. Kitapların önceden sayfa sayfa
  özetlenmesi ve OCR metninin kitap sayfasıyla eşleştirilmesi **sonraki ayrı
  iş** (bu spec'te yok).
- Yaklaşım A: sunucuda iki adımlı hat — bulut OCR (ücretsiz katman) → yerel
  Ollama özeti (bulut metin yedeği). Gemini Live'ın kendisinin özetlemesi (B)
  ve yerel tesseract (C) reddedildi.

## Akış

```
öğretmen: "bu sayfayı özetle / anlat"
  └─ Gemini Live → ekrani_ozetle(mod)        [client, calisma="arkaplan"]
       ├─ hemen: model "Sayfayı okuyorum" der (araç sonucu beklenmez)
       ├─ _screenshot_sig → ekran PNG (gizlilik filtresi: yoklama/e-Okul/MEBBİS → yakalama yok)
       └─ POST /api/egitim/ekran_ozet (multipart: resim, mod)     [server]
            ├─ 1) OCR: saglayicilar.gorsel_uret("gorsel", OCR istemi, resim)
            │        pixtral-12b → mistral-medium → nvidia llama-3.2-11b-vision
            ├─    metin < 80 karakter → status="okunamadi"
            ├─ 2) özet: saglayicilar zinciri "ekran_ozet"
            │        ollama/farabi-qwen3.8:27b → deepseek → groq
            └─ {status, answer, latency_ms, request_id}
       ├─ ok   → player.show_content("ÖZET", answer) + speak("[ÖZET] …")
       └─ diğer → speak(tek kısa cümle), panel açılmaz
```

## Bileşenler

### Sunucu — `server/ekran_ozet.py` (yeni router)

- `POST /api/egitim/ekran_ozet`, `dependencies=[Depends(auth.dogrula_tahta)]`;
  `main.py`'de diğer router'lar gibi `include_router`. `durum["hazir"]`'a
  bağlı değil (RAG modeli gerektirmez).
- Girdi: `resim` (UploadFile, PNG/JPEG, üst sınır 8 MB) + `mod`
  (`"ozet"` | `"anlat"`, varsayılan `"ozet"`). Sınıf düzeyi tahtanın kimliğinden:
  `TahtaKimligi.derslik` → baştaki sayı (`"10-A"` → 10); çözülemezse
  (`"fenlab"`, auth kapalı modda `None`) düzey verilmez.
- **OCR adımı:** `saglayicilar.gorsel_uret("gorsel", OCR_ISTEMI, bytes, mime)`.
  `OCR_ISTEMI`: sayfadaki metni okuma sırasıyla, olduğu gibi çıkar; başlıkları
  ve formülleri koru; yorum/özet ekleme; yalnızca metni döndür. Görsel zincir
  değişmez (mevcut `gorsel` görevi). Boş/kısa sonuç (`< OKUNAMADI_ESIK = 80`
  karakter, boşluklar hariç) → `okunamadi`.
- **Özet adımı:** yeni görev zinciri `GOREV_ZINCIRLERI["ekran_ozet"] =
  [("ollama", "farabi-qwen3.8:27b"), ("deepseek", "deepseek-v4-flash"),
  ("groq", "openai/gpt-oss-120b")]`, `GOREV_ZAMAN_ASIMI_SN["ekran_ozet"] = 60`.
  Ollama çağrısı mevcut yoldan: sıcaklık 0,2, `reasoning_effort="none"`.
  `saglayicilar.metin_uret("ekran_ozet", istem, sistem=SISTEM[mod])` — kendi
  sistem mesajı gönderildiği için modelin gömülü Farabi promptu bu çağrıda
  devre dışı (bilerek: görev dar).
  - `ozet` sistemi: verilen sayfa metnini `<düzey>. sınıf` öğrencisine uygun,
    5–8 maddelik kısa özete çevir; yalnızca bu metne dayan, metinde olmayan
    bilgi/sayı ekleme; Türkçe.
  - `anlat` sistemi: aynı kurallar, ~250–400 kelimelik, ders anlatımı tonunda,
    akıcı metin (madde değil).
- **Eşzamanlılık:** aynı `derslik`'ten süren bir istek varken gelen ikinci
  istek → `status="mesgul"` (modül seviyesi `derslik` anahtarlı küme —
  server/CLAUDE.md "derslik anahtarlı durum" kuralı).
- **Yanıt:** `{status, answer, latency_ms, request_id}`; `status ∈ {ok,
  okunamadi, mesgul, hata}`. Ham OCR metni ve hata ayrıntısı dönmez; ayrıntı
  yalnızca journal'a (`log.warning`). İçerik kalıcı saklanmaz (DB/dosya yok).

### Client — `client/actions/ekrani_ozetle.py` (yeni araç)

- `kayit.py`'ye `calisma="arkaplan"` ile; parametre `mod` (`ozet`/`anlat`).
  Açıklama `ekrandaki_soruyu_oku` ile ayrışacak: "ekrandaki **soru**" →
  `ekrandaki_soruyu_oku`; "bu sayfayı/ekrandakini **özetle / anlat**" →
  `ekrani_ozetle`. Çağrı hemen kısa onayla döner; sonuç ayrı turda `[ÖZET]`
  etiketiyle gelir, model o gelmeden içerik uydurmaz.
- Yakalama `ekrandaki_soruyu_oku` ile aynı (`player._win._screenshot_sig`,
  `CTX_BEKLEME_SN`, `ctx["gizli"]`). Ortak kod gerekirse küçük bir yardımcıya
  çıkarılır; `ekrandaki_soruyu_oku`'nun davranışı değişmez.
- `requests.post(f"{sunucu_url}/api/egitim/ekran_ozet", files=…, data={"mod": …},
  headers=auth_headers(), timeout=90)`.
- `ok` → `player.show_content("ÖZET", answer)` + `speak("[ÖZET] " + answer +
  anlatım talimatı)`; diğer durumlar → tek kısa cümle (aşağıdaki tablo), panel
  açılmaz. Hiçbir durumda tam ekran hata yok.

## Hata durumları

| Durum | Sunucu `status` | Tahtada |
|---|---|---|
| Gizlilik filtresi | — (görüntü gönderilmez) | "Ekranda kişisel veri olabilir, o pencereyi kapatıp tekrar isteyebilirsiniz." |
| Yakalama zaman aşımı / boş | — | "Ekran görüntüsünü alamadım, derse devam edelim." |
| OCR zinciri tamamen başarısız | `hata` | "Sayfayı şu an okuyamadım." |
| Metin < 80 karakter | `okunamadi` | "Ekranda özetlenecek yeterli yazı göremedim." |
| Ollama yok/zaman aşımı | (zincir buluta düşer) | fark edilmez |
| Özet zinciri tamamen başarısız | `hata` | "Özeti şu an hazırlayamadım." |
| Aynı tahtadan süren istek | `mesgul` | "Hâlâ önceki sayfayı okuyorum." |
| Sunucuya ulaşılamıyor / HTTP hatası | — | "Özeti şu an hazırlayamadım." |

## Süre bütçesi

OCR ~8–14 sn (pixtral ölçümü 8,4–9,4 sn) + Ollama özeti ~5–15 sn
(27–31 tok/s) ≈ 15–30 sn. Araç arka planda çalıştığı için ders beklemez.
Sunucu özet görevi zaman aşımı 60 sn, client POST 90 sn.

## Gizlilik

Ekran görüntüsü buluta (Mistral, gerekirse NVIDIA) gider. Kitap sayfası halka
açık (2026-09-29). Öğrenci verisini gizlilik filtresi korur — **sınır:**
filtre pencere başlığına bakar; öğretmen öğrenci listesini bir PDF içinde
açıp "özetle" derse o görüntü buluta gider. Bilinen, kabul edilen sınır;
CLAUDE.md "Gizlilik"e not düşülecek.

## Test

- `server/tests/test_ekran_ozet.py` (sahte `gorsel_uret`/`metin_uret`, GPU/ağ
  yok): kip başına sistem istemi; derslik → düzey (`10-A`, `fenlab`, `None`);
  `okunamadi` eşiği; OCR hatası → `hata`; özet hatası → `hata`; `mesgul`;
  auth zorunlu; yanıtta ham OCR metni yok.
- `GOREV_ZINCIRLERI["ekran_ozet"]` için zincir testi (Ollama birinci, bulut
  yedek var).
- `client/tests/test_ekrani_ozetle.py` (tahtada koşar): gizlilik ve zaman aşımı
  dalları; `ok` → `show_content` + `speak("[ÖZET]…")`; her hata durumunda tek
  kısa cümle, panel yok; araç kaydı (`test_arac_kaydi.py`) güncel.
- Canlı: gerçek bir kitap sayfası render'ı (`/api/egitim/pdf_sayfa` PNG'si)
  uçtan uca, süreler ölçülür.
- Son kabul: Atakan, fiziksel tahtada (Kural 12).

## Teslim sırası

1. Sunucu: router + zincir + testler → `farabi-api` restart → canlı deneme.
2. Client: araç + kayıt + testler → GitHub push → tahtalar 20:00'de çeker
   (9-A'da `~/farabi/repo/client`). Testler tahtada koşulur.
3. Dokümanlar: server/CLAUDE.md uç tablosu, client/CLAUDE.md araç listesi,
   kök CLAUDE.md "Gizlilik" notu, DECISIONS.md kaydı.

## Kapsam dışı (sonraki işler)

- Kitapların önceden sayfa/bölüm bazında özetlenmesi (Ollama gece işi ya da
  ücretsiz bulut).
- OCR metnini `icerik/metin/` ile eşleştirip kitap + sayfa tespiti ve hazır
  özet kullanımı.
- Çok sayfa toplama ("bu sayfayı da ekle"), otomatik sayfa kaydırma.
- Görsel/grafik yorumlama (pixtral grafik değerlerinde güvenilmez,
  2026-09-29).
