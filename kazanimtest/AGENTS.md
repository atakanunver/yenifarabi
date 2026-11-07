# kazanimtest

🛑 KALICI İPTAL (2026-10-24, Atakan): kazanım testi bir daha açılmaz; açıkça istenmeden yeniden açma/önerme.
- Zamanlayıcılar `/etc/systemd/system`'den silindi (2026-10-14); birim kopyaları `_arsiv/kazanimtest-systemd/`.
- Kod, DB tabloları (`soru_havuzu` DB: `form_testi`, `form_cevap`) ve raporlar silinmeden duruyor; pano `/kazanim` ve dijital okul
  gelişim ekranı mevcut veriyi göstermeye devam eder. Bu tabloları/kodu silme.
- Test (kökten): `server/venv/bin/python -m pytest kazanimtest/tests -q`.
