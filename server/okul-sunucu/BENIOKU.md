# okul-sunucu

Okul sunucularının (farabi, bilgehan, debian) ortak durum/proxy betiği.
Dashboard'un **Sunucular** sekmesi (`tahtayoklama/dashboard/sunucular.py`) ve
`server/proxy_kontrol.sh` (EBYS Telegram botu) bunu çağırır.

| Dosya | Kurulum yeri | Görev |
|---|---|---|
| `okul-sunucu` | `/usr/local/sbin/` (root 755) | `durum` (JSON), `proxy-ac`, `proxy-kapat` |
| `okul-sunucu-ssh` | `/usr/local/sbin/` (root 755) | `authorized_keys command=` hedefi; yalnızca bu üç alt komutu geçirir |
| `sudoers-okul-sunucu` | `/etc/sudoers.d/okul-sunucu` (440) | `ata` → yalnızca bu betik NOPASSWD |
| `kur.sh` | — | `sudo sh kur.sh '<PROXY_URL>'` — betikleri + sudoers'ı (visudo -cf ile doğrulayarak) yerleştirir, `/etc/okul-sunucu.conf` yoksa oluşturur. Proxy durumunu DEĞİŞTİRMEZ. |

Proxy URL'si (parolalı) **repoda yok**: hedefte `/etc/okul-sunucu.conf`
(root:root 600) içinde `PROXY_URL=...`. Değer için llm-cluster-wiki
`nodes/mudur-pc.md`'ye bakın.

Proxy açıkken yazılan dosyalar: `/etc/profile.d/okul-proxy.sh`,
`/etc/apt/apt.conf.d/95okul-proxy`, Ollama kuruluysa
`/etc/systemd/system/ollama.service.d/proxy.conf`. Ollama drop-in'i değişirse
restart gerekir; 08:00–17:00 (Europe/Istanbul, hafta içi) arasında bu,
`okul-proxy-ollama-restart` adlı tek seferlik systemd timer'ıyla 17:05'e
ertelenir. GitHub SSH `ProxyCommand` (~/.ssh/config) kapsam dışı — hep açık.

Uzak makineler: Farabi'deki `~/.ssh/sunucu_izleme` anahtarı hedeflerin
`authorized_keys`'ine
`command="/usr/local/sbin/okul-sunucu-ssh",no-pty,no-agent-forwarding,no-port-forwarding,no-X11-forwarding`
önekiyle eklenir.
