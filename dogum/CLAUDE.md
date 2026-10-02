# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**`dogum/` — UYKUDA.** Tek dosyalık Telegram doğum günü botu (`dogum.py`).
crontab/systemd'de kayıtlı değil, son çalışma 2026-09-20. İşlevini
`smssistemi`'nin Doğum Günleri modülü (`/dogum-gunleri`) aldı.

- Kullanıcı açıkça istemeden yeniden canlandırma (cron/systemd ekleme),
  smssistemi'ye taşıma ya da silme yapma.
- `Dogum.xlsx` (gerçek öğrenci/personel doğum tarihleri — KVKK),
  `aboneler.json` (Telegram kullanıcı ID'leri), `dogum.log` ve `.env`
  gitignore'lu: okuma, commit etme, buluta gönderme.
- Kendi `venv/`'i var; bağımlılıklar `requirements.txt` (pandas, openpyxl,
  python-telegram-bot, openai).
- Kök Ruff kapsamı bu dizini bilinçli olarak dışarıda bırakır.
