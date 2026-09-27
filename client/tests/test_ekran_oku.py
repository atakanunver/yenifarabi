"""
main.py — "ekranı oku" özelliği: yazılı komut eşleştirici
(`_ekran_okuma_komutu_mu`), transkript etiket temizleme (`_ETIKET_RE`),
görüntünün doğrudan Gemini Live oturumuna gönderilmesi
(`FarabiLive.ekrani_modele_gonder`) ve öğretmen yazılı komutunun modele
düz metin YERİNE arka plan işçisini tetiklemesi (`_on_teacher_command`).

Ağ yok — session/loop mock'lanır (bkz. tests/test_ders_bitir_dugmesi.py'nin
aynı `asyncio.get_running_loop()` deseni). Gerçek Gemini Live'a hiç gidilmez.
"""

import asyncio
import sys
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main

# ── _ekran_okuma_komutu_mu ───────────────────────────────────────────────

@pytest.mark.parametrize("metin", [
    "ekranı oku",
    "ekrani oku",
    "EKRANI OKU!",
    "ekrandaki soruyu oku lütfen",
    "ekrana bak",
    "ekrandakini oku",
    "[ÖĞRETMEN KOMUTU] ekranı oku",
    "Ekranı Oku.",
    "EKRANDAKİ SORUYU OKU",
])
def test_ekran_okuma_komutu_pozitif(metin):
    assert main._ekran_okuma_komutu_mu(metin) is True


@pytest.mark.parametrize("metin", [
    "ekran görüntüsü al",
    "kitabı oku",
    "konu: Türev · kazanım: Anlık değişim hızı",
    "derse devam et",
    "",
    "ekranı kapat",
    # Olumsuz biçimler — "oku" "okuma"nın ÖNEKİ, düz alt dize araması bunları
    # yanlışlıkla eşleştiriyordu (\b eklenmeden önce, ölçüldü).
    "ekranı okuma",
    "ekranı okumayın",
    "ekrana bakma",
])
def test_ekran_okuma_komutu_negatif(metin):
    assert main._ekran_okuma_komutu_mu(metin) is False


# ── _ETIKET_RE ────────────────────────────────────────────────────────────

def test_etiket_re_ekrani_temizler():
    metin = main._konusma_temizle("[EKRAN] Bu soruyu çöz. Ekranın o anki görüntüsü ekte.")
    assert "[EKRAN]" not in metin
    assert "Bu soruyu çöz" in metin


# ── FarabiLive.ekrani_modele_gonder ─────────────────────────────────────

class _SahteSession:
    def __init__(self):
        self.gonderilen: list[dict] = []

    async def send_client_content(self, turns, turn_complete=True):
        self.gonderilen.append(turns)


def _gecici_png(tmp_path: Path, boyut=(2000, 1000)) -> Path:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    img = QImage(*boyut, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    yol = tmp_path / "ekran.png"
    assert img.save(str(yol), "PNG")
    return yol


def test_ekrani_modele_gonder_oturum_yoksa_false(tmp_path):
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = None
    f.session = None
    assert f.ekrani_modele_gonder(str(tmp_path / "yok.png"), "çöz") is False


def _calisan_loop():
    """Gerçek, AYRI bir iş parçacığında çalışan bir asyncio loop döner.

    `ekrani_modele_gonder` artık `fut.result(timeout=...)` ile SONUCU
    BEKLİYOR (2026-09-27 düzeltmesi, bkz. main.py docstring'i) — bu yüzden
    onu ÇAĞIRAN iş parçacığı, loop'u ÇALIŞTIRAN iş parçacığından FARKLI
    olmalı, aksi hâlde kilitlenir. Üretimde de böyle: `ekrani_modele_gonder`
    her zaman bir işçi iş parçacığından çağrılır, `self._loop`u çalıştıran
    ana asyncio görevinden değil."""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def _loop_durdur(loop, t):
    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=2.0)


def test_ekrani_modele_gonder_kullanici_turu_ve_kucultme(tmp_path):
    pytest.importorskip("PyQt6")
    yol = _gecici_png(tmp_path, boyut=(2000, 1000))

    loop, t = _calisan_loop()
    try:
        f = main.FarabiLive.__new__(main.FarabiLive)
        f._loop = loop
        f.session = _SahteSession()
        sonuc = f.ekrani_modele_gonder(str(yol), "bu soruyu çöz")
    finally:
        _loop_durdur(loop, t)

    assert sonuc is True
    assert len(f.session.gonderilen) == 1

    turns = f.session.gonderilen[0]
    assert turns["role"] == "user"
    parcalar = turns["parts"]
    assert len(parcalar) == 2
    assert parcalar[0]["text"].startswith("[EKRAN] bu soruyu çöz")

    inline = parcalar[1]["inline_data"]
    assert inline["mime_type"] == "image/jpeg"

    from PIL import Image
    with Image.open(BytesIO(inline["data"])) as im:
        assert max(im.size) <= 1024
        # En-boy oranı korunmalı: 2000x1000 -> 1024x512
        assert im.size == (1024, 512)


def test_ekrani_modele_gonder_gonderim_patlarsa_false(tmp_path):
    """2026-09-27 düzeltmesi: eskiden `run_coroutine_threadsafe` yalnızca
    "loop'a kondu" demekti — `send_client_content`in KENDİSİ daha sonra
    patlarsa (ör. bağlantı kapalı) bu asla görülmüyordu, True dönüyordu ve
    OCR yedeğine hiç düşülmüyordu. Şimdi `fut.result(timeout=...)` ile
    SONUÇ beklenir — bu test onu doğrudan kanıtlar."""
    pytest.importorskip("PyQt6")
    yol = _gecici_png(tmp_path)

    class _PatlayanSession:
        async def send_client_content(self, turns, turn_complete=True):
            raise RuntimeError("bağlantı kapalı")

    loop, t = _calisan_loop()
    try:
        f = main.FarabiLive.__new__(main.FarabiLive)
        f._loop = loop
        f.session = _PatlayanSession()
        sonuc = f.ekrani_modele_gonder(str(yol), "çöz")
    finally:
        _loop_durdur(loop, t)

    assert sonuc is False


# ── _on_teacher_command: yazılı "ekranı oku" modele metin göndermez ──────
#
# KRİTİK: `_on_teacher_command`'ın kendisi `ui.py::_send`/`_ogretmen_komutu`
# tarafından DÜZ bir `threading.Thread` üzerinde çağrılır — LOOP'SUZ bir iş
# parçacığıdır. İlk uygulama burada `self._arkaplan`'ı çağırıyordu; o da
# `asyncio.get_event_loop()` çağırır ve yalnızca ÇALIŞAN bir loop'un İÇİNDEN
# güvenlidir (`_execute_tool` gibi) — loop'suz bir iş parçacığında
# `RuntimeError: There is no current event loop in thread ...` ile patlar
# (ölçüldü). Bu testler `_arkaplan`'ı MONKEYPATCH'LEMEZ ve GERÇEK bir
# `threading.Thread` içinde çalıştırır — regresyon olursa iş parçacığı
# sessizce ölür ve aşağıdaki event hiç set edilmez, test zaman aşımıyla
# başarısız olur (asıl bug canlıda tam olarak böyle görünüyordu: öğretmen
# "ekranı oku" yazdı, hiçbir şey olmadı).

def _farabi_live_ogretmen() -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = None   # gerçek kod loop'a hiç ihtiyaç duymamalı
    f._son_etkinlik = 0.0
    f.motor = SimpleNamespace(duraklat=lambda *_a: None, mudahale=lambda *_a: None)
    f.ui = SimpleNamespace(write_log=lambda *_a: None, set_state=lambda *_a: None, muted=False)
    f.ekrani_modele_gonder = lambda *_a, **_kw: True
    return f


def test_yazili_ekran_oku_komutu_isciyi_tetikler_metni_gondermez(monkeypatch):
    cagrildi = threading.Event()
    yakalanan = {}

    def _sahte_ekrandaki_soruyu_oku(parameters=None, player=None, speak=None,
                                     ekrani_gonder=None, **_kw):
        yakalanan["parameters"] = parameters
        cagrildi.set()
        return "ok"

    monkeypatch.setattr(main, "ekrandaki_soruyu_oku", _sahte_ekrandaki_soruyu_oku)

    f = _farabi_live_ogretmen()
    metin_cagrilari = []
    f._on_text_command = lambda metin: metin_cagrilari.append(metin)

    t = threading.Thread(
        target=f._on_teacher_command,
        args=("yazili", "[ÖĞRETMEN KOMUTU] ekranı oku"),
        daemon=True,
    )
    t.start()
    t.join(timeout=2.0)

    assert cagrildi.wait(timeout=2.0), "ekrandaki_soruyu_oku hiç çağrılmadı (thread sessizce mi öldü?)"
    assert metin_cagrilari == []
    assert yakalanan["parameters"] == {"talimat": "ekranı oku"}


def test_diger_yazili_komutlar_hala_metin_olarak_gider(monkeypatch):
    cagrildi = threading.Event()
    monkeypatch.setattr(main, "ekrandaki_soruyu_oku",
                        lambda *_a, **_kw: cagrildi.set())

    f = _farabi_live_ogretmen()
    metin_cagrilari = []
    f._on_text_command = lambda metin: metin_cagrilari.append(metin)

    t = threading.Thread(
        target=f._on_teacher_command,
        args=("yazili", "[ÖĞRETMEN KOMUTU] konu: Türev"),
        daemon=True,
    )
    t.start()
    t.join(timeout=2.0)

    assert not cagrildi.is_set()
    assert len(metin_cagrilari) == 1
    assert "konu: Türev" in metin_cagrilari[0]
