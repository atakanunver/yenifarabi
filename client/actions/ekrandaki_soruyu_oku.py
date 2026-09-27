"""
actions/ekrandaki_soruyu_oku.py — Tahtanın KENDİ ekranındaki sorunun
görüntüsünü yakalar (kamera DEĞİL — bkz. ekran_goruntusu_al.py).

2026-09-27: OCR'a (`file_processor`'ın "ocr" görevi, bulut vision → metin)
indirgeme yerine yakalanan görüntü artık DOĞRUDAN Gemini Live oturumuna,
ayrı bir kullanıcı turu olarak gönderiliyor (`ekrani_gonder` — main.py'nin
`FarabiLive.ekrani_modele_gonder`'i, oturuma tek erişim main.py'de olduğu
için buraya parametre olarak enjekte edilir, `player`/`speak` ile aynı
desen). Gerçek tahtada ölçüldü: `send_realtime_input(video=...)` rakamları
YANLIŞ okuyordu ("2x + 3 = 11" içeren bir soru), `send_client_content` ile
aynı görüntü doğru okundu — bu yüzden realtime video KULLANILMIYOR.

`main.py::_execute_tool` bu aracı artık `calisma="arkaplan"` ile çalıştırır
(bkz. actions/kayit.py) — model çağrının SONUCUNU BEKLEMEZ, hemen bir
"yakalanıyor" onayı alır; görüntü (ya da OCR yedeği, ya da gizlilik/hata
bildirimi) `speak()` ile AYRICA, bir sonraki turda gelir. Bu yüzden bu
fonksiyonun `return` değeri yalnızca doğrudan/test çağrılarında anlamlıdır —
main.py'nin arkaplan işçisi tarafından atılır.

Gizlilik filtresi `ui.py::_ekran_goruntusu_cek`'te uygulanır: ekranda
yoklama/e-Okul/MEBBİS gibi kişisel veri olabilecek bir pencere önde ise
hiç yakalama yapılmaz, `ctx["gizli"] = True` döner.

`ekrani_gonder` başarısız olursa (oturum yok, görüntü bozuk, ...) eski OCR
yoluna düşülür — Farabi asla dersi bozmaz (Kural 2), tek görüntü yolunun
kesilmesi tüm özelliği susturmamalı.
"""

import threading
from actions.file_processor import file_processor

# GUI thread'inin gizleme (~400 ms) + grabWindow için makul bir üst sınır —
# ui.py::MainWindow._EKRAN_GIZLEME_BEKLEME_MS'ten büyük tutulur ki normal
# akışta hiç tetiklenmesin, yalnızca gerçek bir donma/kilitlenmede devreye
# girsin.
CTX_BEKLEME_SN = 6.0


def ekrandaki_soruyu_oku(parameters: dict | None = None, player=None, speak=None,
                          ekrani_gonder=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)
    say = speak or (lambda *_a: None)
    p = parameters or {}
    talimat = (p.get("talimat") or "").strip() or "Ekrandaki soruyu oku, çözümünü yap ve açıkla."

    if player is None or not hasattr(player, "_win"):
        say("Ekran görüntüsü okuma arayüzü şu an hazır değil, efendim.")
        return "Ekran görüntüsü okuma arayüzü şu an hazır değil, efendim."

    log("[Ekran Soru Oku] Ekran yakalanıyor…")

    # GUI operasyonları için ana thread ile senkronizasyon nesneleri
    ctx = {"event": threading.Event(), "path": "", "gizli": False}

    try:
        # Sinyali tetikle
        player._win._screenshot_sig.emit(ctx)
        # GUI thread'inin ekranı gizleyip (gerekiyorsa) yakalamasını bekle.
        if not ctx["event"].wait(timeout=CTX_BEKLEME_SN):
            log("[Ekran Soru Oku] Zaman aşımı — ekran yakalanamadı.")
            say("Ekran görüntüsünü zamanında alamadım efendim, derse böyle devam edelim.")
            return "Zaman aşımı."

        if ctx.get("gizli"):
            log("[Ekran Soru Oku] Gizlilik filtresi — ekranda kişisel veri olabileceği için yakalanmadı.")
            say(
                "Ekranda kişisel veri olabileceği için görüntüyü alamadım "
                "efendim — o pencereyi kapatıp tekrar isteyebilirsiniz."
            )
            return "Gizlilik filtresi nedeniyle ekran yakalanmadı."

        yol = ctx["path"]
        if not yol:
            log("[Ekran Soru Oku] Ekran yakalanamadı.")
            say("Ekran görüntüsü alınamadığı için soruyu okuyamadım efendim.")
            return "Ekran görüntüsü alınamadı."

        log(f"[Ekran Soru Oku] Ekran yakalandı: {yol}.")

        gonderildi = False
        if ekrani_gonder is not None:
            try:
                gonderildi = bool(ekrani_gonder(yol, talimat))
            except Exception as e:  # noqa: BLE001 — bilerek geniş: enjekte
                # edilen `ekrani_gonder` (main.py) neyle patlarsa patlasın,
                # OCR yedeğine düşme sinyaline dönüşmeli — Farabi asla dersi
                # bozmaz (Kural 2).
                log(f"[Ekran Soru Oku] Doğrudan gönderim hatası: {e}")
                gonderildi = False

        if gonderildi:
            log("[Ekran Soru Oku] Görüntü modele doğrudan gönderildi.")
            return "Ekran görüntüsü modele gönderildi."

        # Yedek: doğrudan gönderim yok/başarısız — eski OCR yoluna düş.
        log("[Ekran Soru Oku] Doğrudan gönderim yok/başarısız — OCR yedeğine düşülüyor.")
        fp_params = {"file_path": yol, "action": "ocr", "instruction": talimat}
        ocr_metni = file_processor(fp_params, player=player, speak=None)
        say(f"[EKRAN] {ocr_metni}")
        return ocr_metni

    except Exception as e:
        log(f"[Ekran Soru Oku] Hata: {e}")
        say("Ekrandaki soruyu okurken bir sorun oluştu efendim.")
        return f"Ekrandaki soru okunurken bir hata oluştu: {e}"
