import asyncio
import html
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from telegram import Bot
from telegram.error import TelegramError

# ========== LOGGING AYARI ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


# ========== .env YÜKLE ==========
# Yeni bağımlılık eklemeden (python-dotenv yok) — düz KEY=VALUE satırlarını okur.
def _env_yukle(yol: Path) -> None:
    if not yol.exists():
        return
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, _, deger = satir.partition("=")
        os.environ.setdefault(anahtar.strip(), deger.strip())


_env_yukle(Path(__file__).resolve().parent / ".env")

# ========== AYARLAR ==========
# Sırlar KODA YAZILMAZ — yalnızca ortam değişkeninden okunur (.env, gitignore'lu).
# 2026-09-20: eski hardcoded BOT_TOKEN/GEMINI_API_KEY kaldırıldı (Kural 9 ihlaliydi,
# üstelik Gemini anahtarı artık geçersiz — kullanıcı isteğiyle Ollama'ya geçildi).
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
KULLANICI_IDS = [7637440640, 5583784403]
EXCEL_DOSYASI = str(Path(__file__).resolve().parent / "Dogum.xlsx")

# Doğum günü mesajları artık yerel Ollama (qwen2.5:14b, farabi.local) ile
# üretiliyor — bulut anahtarı gerekmiyor. server/saglayicilar.py'deki
# OpenAI-uyumlu Ollama entegrasyon deseniyle aynı (base_url + "ollama" anahtarı).
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = "qwen2.5:14b"
_OLLAMA_SISTEM_MESAJI = (
    "Sadece Türkçe cevap ver. Başka hiçbir dile geçme. Kısa ve net yaz."
)
# ==============================


def bugun_dogum_gunleri() -> list[str]:
    """Excel dosyasından bugün doğum günü olanların TAM adını (ad + soyad) döndürür."""
    try:
        df = pd.read_excel(EXCEL_DOSYASI, sheet_name="Sayfa1")
    except FileNotFoundError:
        log.error(f"Excel dosyası bulunamadı: {EXCEL_DOSYASI}")
        return []
    except Exception as e:
        log.error(f"Excel okuma hatası: {e}")
        return []

    # Sütun adlarındaki baştaki/sondaki boşlukları temizle
    df.columns = df.columns.str.strip()

    gerekli_sutunlar = ["ADI", "SOYADI", "DOĞUM TARİHİ", "GÜN", "AY"]
    eksik = [s for s in gerekli_sutunlar if s not in df.columns]
    if eksik:
        log.error(f"Excel'de eksik sütunlar: {eksik}")
        log.info(f"Mevcut sütunlar: {list(df.columns)}")
        return []

    df = df[gerekli_sutunlar].copy()

    # GÜN ve AY sütunlarını sayısal tipe dönüştür
    df["GÜN"] = pd.to_numeric(df["GÜN"], errors="coerce")
    df["AY"] = pd.to_numeric(df["AY"], errors="coerce")

    bugun = datetime.today()
    filtrelenmis = df[
        (df["GÜN"] == bugun.day) & (df["AY"] == bugun.month)
    ]

    isimler = []
    for _, row in filtrelenmis.iterrows():
        try:
            ad = str(row["ADI"]).strip()
            soyad = str(row["SOYADI"]).strip()
            # "nan" olarak gelen boş hücreleri temizle
            if ad.lower() == "nan":
                ad = ""
            if soyad.lower() == "nan":
                soyad = ""
            # Ad ve soyadı birleştir (soyad boşsa bile kişi atlanmaz)
            tam_ad = f"{ad} {soyad}".strip()
            if tam_ad:
                isimler.append(tam_ad)
        except Exception as e:
            log.warning(f"Satır işlenirken hata: {e}")

    return isimler


def _ollama_istemcisi():
    """Ollama istemcisini oluşturur; hata olursa None döner."""
    try:
        from openai import OpenAI
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama", max_retries=0, timeout=30.0)
    except Exception as e:
        log.error(f"Ollama istemcisi oluşturulamadı: {e}")
        return None


def _tek_kisi_mesaji(client, tam_ad: str) -> str:
    """Tek bir kişi için Ollama (qwen2.5:14b) ile kişiye özel Türkçe doğum günü mesajı üretir."""
    yedek = f"Nice mutlu, sağlıklı ve huzurlu yıllara {tam_ad}! 🥳"

    if client is None:
        return yedek

    istem = (
        f"'{tam_ad}' adlı kişi için Türkçe, samimi ve içten bir doğum günü kutlama "
        f"mesajı yaz. Her seferinde farklı ve özgün olsun; klişelerden kaçın. "
        f"En fazla 2 kısa cümle olsun ve birkaç uygun emoji kullanabilirsin. "
        f"Kişiye tam adıyla ('{tam_ad}') hitap et. "
        f"Sadece kutlama mesajını yaz, başka hiçbir açıklama, tırnak veya başlık ekleme."
    )
    try:
        yanit = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _OLLAMA_SISTEM_MESAJI},
                {"role": "user", "content": istem},
            ],
            temperature=1.1,
            max_tokens=200,
        )
        metin = (yanit.choices[0].message.content or "").strip().strip('"').strip()
        if metin:
            log.info(f"🤖 Ollama mesajı üretildi → {tam_ad}")
            return metin
        log.warning(f"Ollama boş yanıt döndü ({tam_ad}); yedek mesaj kullanılıyor.")
    except Exception as e:
        log.error(f"Ollama mesaj hatası ({tam_ad}): {e}")

    return yedek


def kisisel_mesajlar_uret(isimler: list[str]) -> dict[str, str]:
    """Her kişi için ayrı Ollama mesajı üretir: {tam_ad: mesaj}."""
    client = _ollama_istemcisi()
    mesajlar: dict[str, str] = {}
    for tam_ad in isimler:
        mesajlar[tam_ad] = _tek_kisi_mesaji(client, tam_ad)
    return mesajlar


def mesaj_olustur(kisisel: dict[str, str]) -> str:
    """Telegram için HTML formatlı, her kişiye özel mesajları içeren metin oluşturur.

    HTML kullanılıyor çünkü model çıktısındaki * _ gibi karakterler
    Markdown ayrıştırmasını bozabilir. Dinamik alanlar html.escape ile kaçırılır.
    """
    tarih = datetime.today().strftime("%d.%m.%Y")
    bloklar = []
    for tam_ad, mesaj in kisisel.items():
        ad_safe = html.escape(tam_ad)
        mesaj_safe = html.escape(mesaj)
        bloklar.append(f"🎂 <b>{ad_safe}</b>\n{mesaj_safe}")

    govde = "\n\n".join(bloklar)
    return (
        f"🎉 <b>Bugün Doğanlar</b> ({tarih})\n\n"
        f"{govde}\n\n"
        f"Nice mutlu yıllara! 🥳"
    )


async def kullaniciya_gonder(bot: Bot, kullanici_id: int, mesaj: str):
    """Tek bir kullanıcıya metin mesajı gönderir."""
    try:
        await bot.send_message(
            chat_id=kullanici_id,
            text=mesaj,
            parse_mode="HTML"
        )
        log.info(f"✅ Metin mesajı gönderildi → {kullanici_id}")
    except TelegramError as e:
        log.error(f"❌ Metin gönderilemedi ({kullanici_id}): {e}")


async def gonder(mesaj: str):
    """Tüm kullanıcılara paralel olarak mesaj gönderir."""
    async with Bot(token=BOT_TOKEN) as bot:
        gorevler = [
            kullaniciya_gonder(bot, uid, mesaj)
            for uid in KULLANICI_IDS
        ]
        await asyncio.gather(*gorevler)


def main():
    log.info("🚀 Doğum günü botu başlatıldı.")

    if not BOT_TOKEN:
        log.error("BOT_TOKEN ortam değişkeni boş — dogum/.env dosyasını kontrol edin.")
        return

    isimler = bugun_dogum_gunleri()

    if not isimler:
        log.info("📅 Bugün doğum günü olan kimse yok.")
        return

    log.info(f"🎂 Bugün doğum günü olanlar: {', '.join(isimler)}")

    # Her kişi için ayrı Ollama mesajı üret
    kisisel = kisisel_mesajlar_uret(isimler)

    mesaj = mesaj_olustur(kisisel)
    log.info(f"Gönderilecek mesaj:\n{mesaj}")

    try:
        asyncio.run(gonder(mesaj))
    except Exception as e:
        log.error(f"Gönderim sırasında hata: {e}")

    log.info("✅ Bot çalışması tamamlandı.")


if __name__ == "__main__":
    main()
