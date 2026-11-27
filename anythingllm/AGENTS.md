# Atos / AnythingLLM (anythingllm/)
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

(`CLAUDE.md` → `AGENTS.md` sembolik bağı; düzenlemeyi AGENTS.md'de yap. Kök `../CLAUDE.md` ortak kurallar + "Atos veri erişimi" akışını anlatır; burada tekrarlanmaz.)

## Bu dizin ne
Atos = AnythingLLM v1.18.0, **Docker'sız**, `/opt/anythingllm` altında PM2 ile (`pm2-anythingllm`, port 8010, collector 8888; kullanıcı `anythingllm`). Bu dizin AnythingLLM'in kendisini değil, onun **kurulum betiğini** ve **özel agent yeteneklerini** (skills) tutar. Uygulama kaynağı depoda yok (`/opt/anythingllm/app`).

## Komutlar
- Test (yalnız SMS yeteneği; Node yerleşik runner): `node --test tests/sms-gonder.test.js` — `node --test tests/` (dizin) bu Node sürümünde çalışmıyor.
- Yetenekleri dağıt (sudo'suz, `ata` kullanıcısıyla; içeride `sudo` kullanır): `./kur_yetenekler.sh`. Sonra AnythingLLM arayüzünde Ajan Yetenekleri'nde açık olduklarını doğrula.
- Sıfırdan kurulum (`sudo ./setup_anythingllm.sh`, idempotent, parola ister) üretim sunucusunu yeniden yazar: `.env`'i yeniden üretir, PM2 süreçlerini yeniden başlatır. Yalnız açıkça istenirse çalıştır.

## Mimari (birden çok dosyayı okuyarak çıkan resim)
- `skills/<ad>/{plugin.json,handler.js}` AnythingLLM'in özel agent yeteneği biçimidir; `handler.js` `module.exports.runtime = { handler }` verir, `this.runtimeArgs` plugin.json `setup_args` değerleridir, `this.super` AnythingLLM agent nesnesidir.
- `kur_yetenekler.sh` her `skills/*` dizinini geçici dizine kopyalar, `plugin.json` içindeki yer tutucuları doldurur ve `/opt/anythingllm/storage/plugins/agent-skills/` altına yazar (0600, `anythingllm` sahibi). Yer tutucular:
  `__SEMA__` ← `sema_aciklamasi.txt` (yalnız `sql-sorgu` açıklaması; LLM'in gördüğü şema), `__ANAHTAR__` ← `tahtayoklama/dashboard/config/okul.json::anahtar`, `__SMS_ANAHTAR__` ← `smssistemi/config/arac.json::anahtar`. Anahtarlar depoya yazılmaz; `plugin.json`'a gerçek değer koyma.
- `skills/_ortak/okul.js`: `sql-sorgu` ve `tablo-dosyasi` ortak yardımcısı (dashboard `/api/okul/sql` çağrısı, tablo metni, xlsx/pdf üretimi). AnythingLLM'in kendi `node_modules`'unu (`exceljs`, `@mintplex-labs/mdpdf`, `create-files/lib.js`) `/opt/anythingllm/app/server` yolundan yükler; AnythingLLM yükseltilince bu iç yollar kırılabilir. `kur_yetenekler.sh` `_ortak`'ı da kopyalar (`plugin.json`'u olmayan dizin).
- `skills/okul-liste` beş sabit sorguyu yönetici rolüyle `POST /api/okul/liste` üzerinden çağırır ve metin, Excel, Word veya PDF döndürür.
- `skills/_ortak/cikti.js` Excel ve Word belgelerini oluşturur, dosya adlarını temizler ve indirme kartını sohbete ekler.
- Dashboard, `okul_ana` tablolarını çalışma anında `sql_dsn` rolünün SELECT yetkisinden keşfeder. `GRANT SELECT` sonrasında tablo servis yeniden başlatılmadan sorgulanabilir. Atos’un tabloyu tanıması için tabloyu `sema_aciklamasi.txt` dosyasına ekleyip `kur_yetenekler.sh` betiğini yeniden çalıştır.
- `sms-gonder`: taslak (`:8020/api/arac/*-taslak`) → `requestToolApproval` → gönderim. Onay yalnız `message === 'User approved the tool execution.'` ise geçerli; otomatik onay/izin listesi gönderim yapmaz. Bu davranışı gevşetme; AnythingLLM güncellenince testle yeniden doğrula.
- `hafiza`: AnythingLLM'in `models/memory.js` modelini doğrudan `require` eder (`Memory.create/forUserWorkspace/delete`). Bu dizinde git'te izlenmiyor (untracked) ve testi yok.
- `setup_anythingllm.sh` başlığındaki "düzeltmeler" yorumu (yükleme klasörü köprüsü `/opt/collector`, `TARGET_OCR_LANG="tur,eng"`, `frontend/src/i18n.js`'e `lng: "tr"` yaması) AnythingLLM güncellenince yeniden uygulanması gereken yamaları listeler.
