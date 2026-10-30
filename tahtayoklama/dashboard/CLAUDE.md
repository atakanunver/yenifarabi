# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Bu dizin `farabi-yoklama-dashboard` servisidir (FastAPI + Jinja2 + SQLite, port 80). Üst dizindeki `../CLAUDE.md` (§4 dashboard, §5 uzaktan yönetim, tasarım standartları) ve kök `/home/ata/farabi/CLAUDE.md` da yüklenir; burada yalnızca onlarda olmayan, kod okuyarak çıkması zor olanlar var.

## Komutlar (bu dizinden)
```bash
venv/bin/python -m unittest discover -p 'test_*.py'          # pytest YOK
venv/bin/python -m unittest test_menu                        # tek dosya (modül adı, .py'siz)
venv/bin/python -m unittest test_menu.TestMenu.<test_adi>    # tek test
/home/ata/farabi/.venv-tools/bin/ruff check <dosya>          # F821/F811/F632 sıfır kalmalı
sudo systemctl restart farabi-yoklama-dashboard              # yalnız 08:00-17:00 TR DIŞINDA
```
`uvicorn app:app --reload` elle başlatılırsa lifespan polling'i de başlatır → canlıyla çift polling. Şablon/CSS/JS değişikliği restart istemez (anında yansır), `.py` ister.

## Mimari (birkaç dosyayı okuyarak çıkan resim)
- `app.py` yalnız giriş noktasıdır; özellikler `APIRouter` modülleri olarak `include_router` ile bağlanır (`admin`, `uzaktan_yonetim`, `ajan_api`, `tahta_api`, `okul_ana_panel`, `acil`, `guvenlik`, `kameralar`, `sunucular`, `servis_yonetimi`, `zamanlanmis_gorevler`, `yakinda`…). Yeni sayfa: router + `menu.py::MENU` girişi + her `Jinja2Templates` örneğine `templates.env.globals["menu_agaci"]` (aksi halde `test_menu` kırılır).
- **Üç ayrı kimlik alanı, karıştırma:** (1) ortak yönetici şifresi → `auth.dogrula` oturum çerezi (`admin`, `uzaktan`, `okul_ana_panel`…); (2) `/guvenlik` kendi şifresi + çerezi (`config/guvenlik.json`), `/acil`/`/admin` onu tanımaz; (3) makine API'leri yalnız yerel IP + anahtar başlığı: `/api/ajan` (`X-Farabi-Ajan-Key`), `/api/v1/tahta/*` (tahta başına token, SHA-256), `/api/okul/sql` (`X-Farabi-Okul-Key`).
- **Veri akışı — okul verisi:** tek kaynak `okul_ana` (PostgreSQL). `okul_ana_veri` (psycopg 3, tek transaction + denetim) → `okul_ana_yayin` eski depolara yansıtır (`yoklama_pano.db`, `okul.db`, `smssistemi.db`; okul_no ile eşler, kuru çalıştırma varsayılan, `--uygula` yazar) → `okul_ana_goruntu` tahta JSON'larını (`zil.json`, `ders_programi.json`, baytı baytına aynı biçim) üretir. Yayın başarısız olsa veri DB'de güvende kalır; panel "Yayınla" ile tekrar dener.
- **Yoklama akışı:** tahta `yoklama.py` → `tahta_istemci.py` → `tahta_api.py` (push) ve/veya `yoklayici.py` (SSH polling, hafta içi ders penceresi). İkisi de `yoklayici.onbellege_yaz` ile `yoklama_onbellek`'e yazar; 'alindi' üstüne yalnız daha yeni `kaydedilme_saati` yazar. Kulüp yoklaması `kulup_yoklama` tablosunda ayrı tutulur.
- **Diğer servislerle bağ yalnızca HTTP** (DB paylaşılmaz): `veli_mesajlari` → smssistemi (`config/sms_panel.json`), `devamsizlik_bildirim` → okul (`config/devamsizlik_bildirim.json`). Servis kapalıysa sessizce atlanır; dashboard dersi/yoklamayı bozmaz. İstisnalar (salt-okunur): `sistem_durumu` Farabi PG'sine, `aylik_ozet` `okul.db`'ye, `okul_sql` birkaç kaynağa.
- **Ayrıcalıklı işler sudo betiği üzerinden, kabuksuz argüman listesiyle:** `servis_yonetimi` → `sudo -n /usr/local/sbin/farabi-servis`, `zamanlanmis_gorevler` → `farabi-zamanlayici` (kaynaklar `scripts/`). Birim listeleri betik ile modülde birebir aynı olmalı (`test_farabi_servis`, `test_farabi_zamanlayici` denetler); yetki denetimi betikten ÖNCE Python'da yapılır.
- **Acil durum (`acil.py`)**: bir düğme üç bağımsız kanalı (zil anonsu, SMS, tahta kiosk ekranı) tetikler; biri düşse diğerleri çalışır. `guvenlik._baslat` aynı yolu kullanır. Olaylar `veri/acil_olaylar.jsonl`. Tatbikat/gerçek ayrımı SMS alıcı kümesini değiştirir — test dışında gerçek modda tetikleme.
- Çoğu uzak makine işi (`sunucular`, `ssh_istemci`) paramiko'suz düz `ssh` alt sürecidir; yeni ağır bağımlılık ekleme (`requirements.txt` 4 paket).

## Tuzaklar
- `config/` gizli dosyalar içerir (gitignore'lu); `*.bak-*` / `*.yedek-*` dosyaları eski yedeklerdir, kod tabanı değil — okuma/düzenleme.
- Systemd birimindeki 8010 `port80.conf` drop-in'i ile 80'e ezilir; `curl` ile test ederken gerçek port 80.
- `okul_sql.py` ve `okul_bilgisi.py` değişince kök `CLAUDE.md`'deki "Atos veri erişimi" kurallarına (yeni tablo = sabit + `IZINLI_TABLOLAR` + şema açıklaması) uy.
