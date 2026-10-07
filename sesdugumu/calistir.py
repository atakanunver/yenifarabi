"""Üretim giriş noktası: gerçek motorlarla uvicorn (systemd buradan başlatır)."""
import logging
import os

import uvicorn

from sesdugumu.app import uygulama_kur
from sesdugumu.motorlar import STTMotoru, TTSMotoru

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

REFERANS = os.environ.get("FARABI2_SES_REFERANS",
                          "/home/ata/chatterbox-tts/voices/adaylar/nisan_kumru_2.wav")

if __name__ == "__main__":
    tts = TTSMotoru(REFERANS, float(os.environ.get("FARABI2_SES_EXAGGERATION", "0.7")),
                    float(os.environ.get("FARABI2_SES_CFG", "0.3")),
                    float(os.environ.get("FARABI2_SES_TEMPERATURE", "0.75")))
    stt = STTMotoru(os.environ.get("FARABI2_STT_MODEL", "large-v3-turbo"))
    uvicorn.run(uygulama_kur(tts, stt), host="0.0.0.0",
                port=int(os.environ.get("FARABI2_SES_PORT", "8060")), workers=1)
