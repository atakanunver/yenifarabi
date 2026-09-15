"""Faz 4 — bir tahtada yoklama.py'yi uzaktan başlatma/öne getirme.

X-ortamı (DISPLAY/XAUTHORITY) keşfi 2026-09-15'te ssh_istemci.py'ye taşındı
(x_ortamini_kesfet) — uzaktan_yonetim.py da aynı keşfe ihtiyaç duyuyor, tek
kopya (bkz. tahtaayar/CLAUDE.md'deki "iki kopya senkron kalmadı" dersi).
"""

import asyncio

import ssh_istemci

# '[t]ahtayoklama' — klasik pgrep öz-eşleşme kaçınma numarası: SSH bu komutu
# çalıştırırken bazı durumlarda komut metnini içeren bir ara kabuk süreci
# (örn. bileşik komutlarda "sh -c '...'") arkada kalabiliyor, o sürecin
# KENDİ argümanları da "tahtayoklama/yoklama.py" alt dizesini içerdiği için
# yanlış pozitif üretebilir (canlı test edildi, 2026-08-23). Köşeli parantez
# regex'i hâlâ gerçek süreci eşler ama bu komutun kendi metnini eşlemez.
_CALISIYOR_MU_KOMUTU = "pgrep -af '[t]ahtayoklama/yoklama.py'"


async def baslat(tahta: dict) -> dict:
    """tahta: {ip, ssh_kullanici, python_yolu, ad} — db'deki tahtalar satırı
    (ya da uzaktan_yonetim.py'nin tahta_kaydi.py'den derlediği eşdeğeri).
    Döner: {"basarili": bool, "durum": str, "detay": str}."""
    ip = tahta["ip"]
    kullanici = tahta["ssh_kullanici"]

    ortam = await ssh_istemci.x_ortamini_kesfet(ip, kullanici)
    if ortam is None:
        return {
            "basarili": False,
            "durum": "hata",
            "detay": "Tahtada aktif masaüstü oturumu bulunamadı (tahta kapalı olabilir).",
        }
    display, xauthority, _uid = ortam

    calisiyor_mu = await ssh_istemci.komut_calistir(ip, kullanici, _CALISIYOR_MU_KOMUTU)
    zaten_calisiyor = calisiyor_mu.basarili and calisiyor_mu.stdout.strip() != b""

    if zaten_calisiyor:
        komut = f'DISPLAY={display} XAUTHORITY={xauthority} wmctrl -a Yoklama'
        sonuc = await ssh_istemci.komut_calistir(ip, kullanici, komut)
        if sonuc.basarili:
            return {"basarili": True, "durum": "one_getirildi", "detay": "Pencere öne getirildi."}
        return {
            "basarili": False,
            "durum": "hata",
            "detay": f"wmctrl başarısız: {sonuc.stderr.decode(errors='replace')[:200]}",
        }

    # Çalışmıyor — arka planda, SSH oturumundan bağımsız (setsid) başlat.
    python_yolu = tahta["python_yolu"]
    komut = (
        f"setsid env DISPLAY={display} XAUTHORITY={xauthority} "
        f"{python_yolu} /home/{kullanici}/tahtayoklama/yoklama.py "
        f"</dev/null >/tmp/yoklama_dashboard_baslatma.log 2>&1 &"
    )
    baslatma = await ssh_istemci.komut_calistir(ip, kullanici, komut)
    if not baslatma.basarili:
        return {
            "basarili": False,
            "durum": "hata",
            "detay": f"Başlatma komutu başarısız: {baslatma.stderr.decode(errors='replace')[:200]}",
        }

    # ~2sn sonra tekrar kontrol et — süreç gerçekten ayakta mı?
    await asyncio.sleep(2)
    dogrulama = await ssh_istemci.komut_calistir(ip, kullanici, _CALISIYOR_MU_KOMUTU)
    if dogrulama.basarili and dogrulama.stdout.strip() != b"":
        return {"basarili": True, "durum": "yeni_baslatildi", "detay": "Yoklama ekranı başlatıldı."}

    log = await ssh_istemci.komut_calistir(
        ip, kullanici, "tail -c 500 /tmp/yoklama_dashboard_baslatma.log 2>/dev/null"
    )
    return {
        "basarili": False,
        "durum": "hata",
        "detay": f"Süreç 2sn sonra bulunamadı. Log: {log.stdout.decode(errors='replace')[:300]}",
    }
