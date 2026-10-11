# Runbook

Kök CLAUDE.md'den taşındı (docs-cleanup). Kimlik bilgileri/MAC: `network.txt` (gitignore'lu). Çelişkide `server/tahtalar.json` esas.

## Ağ Envanteri

Kimlik bilgileri (şifreler) ve tüm MAC adresleri **yalnızca
`network.txt`'te** (gitignore'lu). Bu dosya public GitHub'a gidiyor —
buraya şifre yazılmaz.

Üç ayrı makine sınıfı var:

1. **Vestel akıllı tahtalar** (Pardus ETAP GNU/Linux, hostname
   `vestel<düzey><şube>` deseninde — ör. `vestel9a`, ağ `192.168.23.0/24`,
   VLAN/güvenlik duvarı yok). **Sayım:** ağda 11 fiziksel tahta; **8'inde**
   Farabi client kurulu (aşağıdaki tablo = `config_dagit.sh`'in varsayılan
   hedef listesi), 8'in **7'si** sınıf, 8.'si `fenlab`. Kalan 3 tahta
   (`.234`, `.235`, `.236`) `server/tahtalar.json`'da `tahta-NNN` geçici
   adıyla kayıtlı, sınıfı atanmamış, client kurulu değil. Kurulum tarihleri
   ve ayrıntıları DECISIONS.md'de.

   | Sınıf/Ad | IP             | Hostname  | Yoklama | Farabi client |
   |----------|----------------|-----------|---------|---------------|
   | 9-A      | 192.168.23.245 | vestel9a  | evet (Farabi client venv'ini paylaşır) | evet (pilot; tam klon yapısı `~/farabi/repo`) |
   | 9-B      | 192.168.23.239 | vestel9b  | evet | evet |
   | 10-A     | 192.168.23.242 | vestel10a | evet | evet |
   | 11-A     | 192.168.23.228 | vestel11a | evet | evet |
   | 11-B     | 192.168.23.233 | vestel11b | evet | evet |
   | 12-A     | 192.168.23.226 | vestel12a | evet | evet |
   | 12-B     | 192.168.23.240 | vestel12b | evet | evet |
   | fenlab   | 192.168.23.244 | fenlab    | evet (7 sınıfın rosterı birden; dashboard'da sınıf atanmamış) | evet |

   ⚠️ **fenlab'ın `derslik` değeri `"fenlab"`** — Farabi sınıf düzeyini
   `derslik`ten çıkarıyor (`10-A` → 10. sınıf); `"fenlab"` bir düzeye
   çözülemez, bu yüzden kitap ararken öğretmene sınıfı soracak. Tek bir
   düzeye sabitlenecekse `derslik` değiştirilmeli.

   Donanım: Pardus ETAP 23, Intel i3-2330M (eski mobil işlemci).
   Bağlanma: `server/tahta-ssh.sh <derslik>` (`ogretmen`) ya da
   `--admin <derslik>` (`etapadmin`, sudo). NOPASSWD sudo tahtadan tahtaya
   değişiyor — önce `sudo -n true` ile dene. MAC adresleri ve kimlik
   bilgileri `network.txt`'te (ikincil referans; çelişkide
   `server/tahtalar.json` esas).

2. **Kapıdaki yüz tanıma sistemi** (giriş yoklaması kiosk PC'si,
   `192.168.23.254`, Debian 12) — bu repodaki hiçbir projeye BAĞLI DEĞİL,
   yalnızca envanter notu.

3. **Farabi sunucu** (bu makine, `ata@farabi.local` / `192.168.23.252`,
   Ubuntu 26.04, Ryzen 9 3900X, 2× RTX 3060, 64 GB RAM, sudo NOPASSWD) —
   tüm servisler burada, tahtalara buradan SSH ile bağlanılıyor.

