"""
actions/pencere_kapat.py — Öğretmen talimat modunda pencere/uygulama kapatır.

ÖĞRETMEN TALİMAT MODUNA ÖZEL (kip="talimat"). Gerçek bir sınıf içi testte
(2026-08-23, logs/ders/2026-08-23_14-17-09_9-A.txt) "kapat" komutlarının
karşılığı hiç yoktu — model "Kapatılıyor." diyip HİÇBİR ŞEY yapmıyordu ya da
web_ac/uygulama_ac'ı 'kapat' kelimesini parametre gibi geçirerek kötüye
kullanıyordu (ör. web_ac(hedef='kapat') → Google'da "kapat" araması açtı).
Bu araç o boşluğu dolduruyor.

PENCERE BAŞLIĞI eşleştirmesi (wmctrl -c) kullanılır, süreç PID'i takibi
DEĞİL: web_ac'ın açtığı bir tarayıcı sekmesinin arkasındaki `xdg-open`
süreci genelde saniyeler içinde ölür — URL, zaten çalışan tarayıcı
sürecine IPC ile devredilir, Popen'ın döndürdüğü PID tarayıcı penceresiyle
hiç ilişkili kalmaz. Başlık eşleştirmesi hem tarayıcı sekmeleri hem
uygulama pencereleri (Kalem, Çizim, Nemo) için tek, tutarlı bir mekanizma.

`wmctrl` paketi gerekli (2026-08-23'te bu tahtaya `apt install wmctrl` ile
kuruldu — kurulu değilse araç bunu açıkça söyler, sessizce "kapatıldı"
YALANI SÖYLEMEZ).
"""

import subprocess


def pencere_kapat(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    hedef = (params.get("hedef") or "").strip()

    if player:
        player.write_log(f"[TALİMAT] pencere_kapat: '{hedef}'")

    if not hedef:
        return "Hangi pencereyi kapatacağımı söyleyin."

    try:
        sonuc = subprocess.run(
            ["wmctrl", "-c", hedef],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return "Pencere kapatma aracı (wmctrl) bu tahtada kurulu değil."
    except Exception as e:
        return f"Kapatılamadı: {e}"

    if sonuc.returncode != 0:
        return f"'{hedef}' başlıklı açık bir pencere bulamadım."

    return f"Kapatıldı: {hedef}"
