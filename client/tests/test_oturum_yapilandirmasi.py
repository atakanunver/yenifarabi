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
from actions import kayit                      # noqa: E402


class _SahteUI:
    def __init__(self, ders_dili="tr", talimat_modu=False):
        self.ders_dili = ders_dili
        self.talimat_modu = talimat_modu


@pytest.fixture
def config():
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = None
    f._ders_kipi = main.KIP_OGRETMENLI
    return f._build_config()


@pytest.fixture
def talimat_config():
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = None
    f._ders_kipi = main.KIP_OGRETMENLI       # ui.talimat_modu bunu geçersiz kılmalı
    f.ui = _SahteUI(talimat_modu=True)
    return f._build_config()


def _sistem_metni(cfg) -> str:
    si = cfg.system_instruction
    return si if isinstance(si, str) else "".join(p.text for p in si.parts)


def test_arac_bildirimleri_config_e_giriyor(config):
    """
    Bildirilen araçlar kipe göre FİLTRELENİR (2026-08-23, talimat modu) —
    artık main._TOOL_ADLARI (filtresiz TAM liste) ile eşit değil, o listenin
    KIP_OGRETMENLI'de açık olan ALT KÜMESİYLE eşit olmalı. web_ac/
    uygulama_ac/dosya_ac gibi kip=("talimat",) araçları normal derste hiç
    bildirilmemeli.
    """
    assert config.tools, "tools= verilmemiş: model araçları göremez"
    adlar = [d.name for d in config.tools[0].function_declarations]
    beklenen = [d["name"] for d in kayit.bildirimler(main.KIP_OGRETMENLI)]
    assert adlar == beklenen
    assert "save_memory" not in adlar
    assert "web_ac" not in adlar and "uygulama_ac" not in adlar and "dosya_ac" not in adlar


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


class TestTalimatModu:
    """
    Öğretmen talimat modu (2026-08-23) — ders yok, yalnızca sesle sistem
    komutu. `ui.talimat_modu=True`, __init__'te belirlenen ders kipini
    bağlantı anında geçersiz kılmalı (ders_dili ile aynı desen).
    """

    def test_ui_talimat_modu_ders_kipini_gecersiz_kilar(self, talimat_config):
        assert talimat_config.system_instruction == main._TALIMAT_PERSONASI

    def test_normal_ders_personasi_karismaz(self, talimat_config):
        # core/prompt.txt, ders çerçevesi, dil kuralı vb. HİÇ girmemeli.
        assert "DİL KURALI" not in talimat_config.system_instruction
        assert "FARABİ" not in talimat_config.system_instruction.upper() or \
            "TALİMAT" in talimat_config.system_instruction.upper()

    def test_yalnizca_talimat_araclari_bildirilir(self, talimat_config):
        adlar = {d.name for d in talimat_config.tools[0].function_declarations}
        beklenen = {d["name"] for d in kayit.bildirimler(main.KIP_TALIMAT)}
        assert adlar == beklenen
        assert {"web_ac", "uygulama_ac", "dosya_ac", "pdf_sayfa", "yks_sorulari"} <= adlar
        # Normal ders araçları bu modda görünmemeli.
        assert "ders_icerigi" not in adlar and "web_search" not in adlar

    def test_talimat_modu_yoksa_normal_persona_kullanilir(self, config):
        assert config.system_instruction != main._TALIMAT_PERSONASI
