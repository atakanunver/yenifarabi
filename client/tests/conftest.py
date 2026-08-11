"""
Testler gerçek tanı logunu VE gerçek ders kaydını kirletmez.

Neden: `core.logger` proje kökündeki `logs/farabi.log` dosyasına yazıyor ve
pytest çalıştırmaları oraya onlarca "Ders adımı: …" satırı bırakıyordu. O
dosya sınıfta ne olduğunu anlamak için okunuyor; test gürültüsü gerçek
oturumun izini gömer. `core.transcript` (logs/ders/YYYY-AA-GG.txt) aynı
sınıftan bir risk taşıyordu, ayrı bir ortam değişkeniyle korunur.
"""

import os
import tempfile

# İçe aktarmadan ÖNCE ayarlanmalı: ilgili modüller yolu import anında okuyor.
os.environ.setdefault("FARABI_LOG_DIR", tempfile.mkdtemp(prefix="farabi-test-log-"))
os.environ.setdefault("FARABI_DERS_LOG_DIR", tempfile.mkdtemp(prefix="farabi-test-ders-"))
