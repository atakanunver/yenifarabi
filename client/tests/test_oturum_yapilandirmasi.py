"""
Oturum yapılandırması — modele NE GİTTİĞİNİ doğrular.

Bu dosyanın varlık sebebi iki gerçek arıza:

1. `system_instruction` config'e verilmiyordu; `parts` kuruluyor, sonra
   düşüyordu. Farabi personasız çalıştı ve araçları kendiliğinden çağırmadı.
2. `tools` config'e verilmiyordu; `TOOL_DECLARATIONS` kuruluyor, sonra
   düşüyordu. Model araçların varlığından habersizdi ve 30.07.2026 dersinde
   `youtube_video`'yu ÇAĞIRIYORMUŞ GİBİ konuşup "ekranda video dönüyor" dedi.
   O oturumun logunda tek bir araç çağrısı yok.

İkisi de "çalışıyor görünen" arızalardı: log dosyayı okuduğunu yazıyordu,
model de akıcı konuşuyordu. Tek güvenilir kontrol, kurulan config nesnesine
bakmaktır.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main                                    # noqa: E402


class _SahteUI:
    def __init__(self, ders_dili="tr"):
        self.ders_dili = ders_dili


@pytest.fixture
def config():
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = None
    f._ders_kipi = main.KIP_OGRETMENLI
    return f._build_config()


def _sistem_metni(cfg) -> str:
    si = cfg.system_instruction
    return si if isinstance(si, str) else "".join(p.text for p in si.parts)


def test_arac_bildirimleri_config_e_giriyor(config):
    assert config.tools, "tools= verilmemiş: model araçları göremez"
    adlar = [d.name for d in config.tools[0].function_declarations]
    assert adlar == main._TOOL_ADLARI
    assert "save_memory" not in adlar


def test_sistem_promptu_config_e_giriyor(config):
    si = config.system_instruction
    metin = si if isinstance(si, str) else "".join(p.text for p in si.parts)
    assert "FARABİ" in metin and "DİL KURALI" in metin
    assert len(metin) > 5000, "persona düşmüş olabilir"
    assert "save_memory" not in metin
    # Öğrenci hafızası enjekte edilmemeli
    assert "LONG-TERM MEMORY" not in metin.upper()
    assert "ÖĞRENCİ HAFIZA" not in metin.upper()


def test_ses_ayari_sade_kalmali(config):
    """
    VAD/`realtime_input_config` eklemek Farabi'yi tamamen sağır etmişti.
    Ses ayarı yalnızca giriş/çıkış transkripsiyonundan ibaret kalmalı.
    """
    assert getattr(config, "realtime_input_config", None) is None


def test_dusunce_metni_disa_verilmiyor(config):
    """Ders kaydına İngilizce iç muhakeme sızmıştı."""
    assert config.thinking_config.include_thoughts is False


class TestDersDili:
    """
    ui.ders_dili yoksa (bare test double, self.ui hiç yok) ya da 'tr' ise
    davranış değişmemeli — bkz. AttributeError regresyonu: getattr(self.ui, …)
    self.ui'nin KENDİSİ yoksa da patlıyordu, yalnız ders_dili eksikse değil.
    """

    def _cfg(self, ders_dili: str | None):
        f = main.FarabiLive.__new__(main.FarabiLive)
        f._current_lesson = None
        f._ders_kipi = main.KIP_OGRETMENLI
        if ders_dili is not None:
            f.ui = _SahteUI(ders_dili)
        return f._build_config()

    def test_ui_hic_yoksa_turkce_varsayilan(self):
        metin = _sistem_metni(self._cfg(None))
        assert "DİL KURALI" in metin
        assert "LANGUAGE RULE" not in metin
        assert "SPRACHREGEL" not in metin

    def test_tr_acik_secim(self):
        metin = _sistem_metni(self._cfg("tr"))
        assert "DİL KURALI" in metin and "TÜRKÇE" in metin

    def test_en_secilirse_ingilizce_direktifi_girer(self):
        metin = _sistem_metni(self._cfg("en"))
        assert "LANGUAGE RULE" in metin
        assert "ENGLISH" in metin
        assert "DİL KURALI — ÇOK ÖNEMLİ" not in metin

    def test_de_secilirse_almanca_direktifi_girer(self):
        metin = _sistem_metni(self._cfg("de"))
        assert "SPRACHREGEL" in metin
        assert "DEUTSCH" in metin
        assert "DİL KURALI — ÇOK ÖNEMLİ" not in metin

    def test_bilinmeyen_dil_kodu_turkceye_duser(self):
        metin = _sistem_metni(self._cfg("fr"))
        assert "DİL KURALI" in metin


class TestAcilisSelamGun:
    def test_tr_varsayilan_selamlari_dondurur(self):
        gece_yarisi_sonrasi = main.datetime(2026, 8, 3, 9, 0)   # Pazartesi
        selam, gun = main._acilis_selam_gun("tr", gece_yarisi_sonrasi)
        assert selam == "Günaydın"
        assert gun == "Pazartesi"

    def test_en_selam_ve_gun_ingilizce(self):
        simdi = main.datetime(2026, 8, 3, 14, 0)   # Pazartesi, öğleden sonra
        selam, gun = main._acilis_selam_gun("en", simdi)
        assert selam == "Good afternoon"
        assert gun == "Monday"

    def test_de_selam_ve_gun_almanca(self):
        simdi = main.datetime(2026, 8, 3, 20, 0)   # Pazartesi, akşam
        selam, gun = main._acilis_selam_gun("de", simdi)
        assert selam == "Guten Abend"
        assert gun == "Montag"
