"""
Mikrofonsuz mod (2026-09-25) — tahtaların mikrofonları bozuk.

Sorun: öğrenci modunda DERSİ BAŞLAT'tan sonra Farabi sesli bir cevap
bekliyordu (açılışta öğretmenden konu, sınıftan yoklama) ve Gemini Live,
kullanıcıdan ses gelmeyince her turdan sonra susuyordu. Mikrofonsuz modda:
konu DERSİ BAŞLAT'ta yazılı alınır, açılış doğrudan anlatıma geçer ve
`_devam_karari` her tur bittiğinde modeli bir sonraki adıma iter.

Ağ yok — session mock'lanır, zaman parametreyle verilir.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main                              # noqa: E402
from core import tahta                   # noqa: E402
from core.ders_motoru import DersDurumu  # noqa: E402


# ── Ayar: config/api_keys.json "mikrofon" ─────────────────────────────────

class TestMikrofonAyari:
    def _yaz(self, tmp_path, monkeypatch, veri):
        yol = tmp_path / "api_keys.json"
        yol.write_text(json.dumps(veri), encoding="utf-8")
        monkeypatch.setattr(tahta, "CONFIG_PATH", yol)

    def test_alan_yoksa_mikrofon_var_sayilir(self, tmp_path, monkeypatch):
        self._yaz(tmp_path, monkeypatch, {"derslik": "12-A"})
        assert tahta.mikrofon_var() is True

    def test_false_ise_mikrofon_yok(self, tmp_path, monkeypatch):
        self._yaz(tmp_path, monkeypatch, {"mikrofon": False})
        assert tahta.mikrofon_var() is False

    @pytest.mark.parametrize("deger", ["yok", "false", "kapali", 0])
    def test_metin_ve_sifir_de_kabul_edilir(self, tmp_path, monkeypatch, deger):
        self._yaz(tmp_path, monkeypatch, {"mikrofon": deger})
        assert tahta.mikrofon_var() is False

    def test_dosya_yoksa_mikrofon_var_sayilir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "yok.json")
        assert tahta.mikrofon_var() is True


# ── Sistem talimatı ────────────────────────────────────────────────────────

def _sistem_metni(cfg) -> str:
    si = cfg.system_instruction
    return si if isinstance(si, str) else "".join(p.text for p in si.parts)


def _yapilandirma(mikrofonsuz: bool):
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = {"subject": "Fizik", "topic": "Newton'un yasaları",
                         "kazanim": ""}
    f._ders_kipi = main.KIP_OGRETMENLI
    f._ders_kipi_taban = main.KIP_OGRETMENLI
    f._mikrofonsuz = mikrofonsuz
    return _sistem_metni(f._build_config())


def test_mikrofonsuz_kurallari_sistem_talimatinda():
    metin = _yapilandirma(True)
    assert "[MİKROFONSUZ MOD]" in metin
    assert "cevabı kendin" in metin


def test_normal_modda_mikrofonsuz_kurali_yok():
    assert "[MİKROFONSUZ MOD]" not in _yapilandirma(False)


# ── Açılış ─────────────────────────────────────────────────────────────────

class _SahteSession:
    def __init__(self):
        self.gonderilen: list[str] = []

    async def send_client_content(self, turns, turn_complete=True):
        self.gonderilen.append(turns["parts"][0]["text"])


def _acilis_farabi(mikrofonsuz: bool, lesson: dict | None):
    f = main.FarabiLive.__new__(main.FarabiLive)
    f.session = _SahteSession()
    f.ui = SimpleNamespace(write_log=lambda *_a: None, ders_dili="tr")
    f._ders_kipi = main.KIP_OGRETMENLI
    f._program_slotu = None
    f._current_lesson = lesson
    f._mikrofonsuz = mikrofonsuz
    return f


def _acilis_metni(f) -> str:
    asyncio.run(f._send_session_opening())
    return f.session.gonderilen[0]


class TestAcilis:
    DERS = {"subject": "Fizik", "topic": "Newton'un yasaları", "kazanim": ""}

    def test_mikrofonsuz_acilis_yoklama_istemez_ve_anlatima_baslar(self):
        metin = _acilis_metni(_acilis_farabi(True, self.DERS))
        assert "Yoklama al" not in metin
        assert "cevabı bekle" not in metin
        assert "anlatmaya başla" in metin.lower()

    def test_normal_acilis_degismedi(self):
        metin = _acilis_metni(_acilis_farabi(False, self.DERS))
        assert "Yoklama al" in metin

    def test_mikrofonsuz_konu_yoksa_sesli_istemez(self):
        metin = _acilis_metni(_acilis_farabi(True, None))
        assert "söylemesini" not in metin
        assert "yazmasını" in metin


# ── Otomatik devam kararı ──────────────────────────────────────────────────

class _Kuyruk:
    def __init__(self, bos=True):
        self._bos = bos

    def empty(self):
        return self._bos


def _devam_farabi(**degisiklik):
    """Her şeyin 'devam gönder' dediği bir başlangıç durumu; testler tek
    bir koşulu bozar."""
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._mikrofonsuz = True
    f._ders_kipi = main.KIP_OGRETMENLI
    f._is_speaking = False
    f.audio_in_queue = _Kuyruk(bos=True)
    f.motor = SimpleNamespace(durum=DersDurumu())
    f._video_yuzunden_susturuldu = False
    f._arac_suruyor = 0
    f._tur_no = 3
    f._devam_son_tur = 2
    f._son_tur_ts = 100.0
    f._sessizlik_ts = 100.0
    f._miksiz_baslangic = 0.0
    f._miksiz_kapanis_gonderildi = False
    for k, v in degisiklik.items():
        setattr(f, k, v)
    return f


SIMDI = 100.0 + main.FarabiLive.DEVAM_BEKLEME_SN + 0.1


class TestDevamKarari:
    def test_tur_bitti_ses_bitti_sessizlik_doldu_devam(self):
        assert _devam_farabi()._devam_karari(SIMDI) == "devam"

    def test_yeni_tur_yoksa_gonderilmez(self):
        f = _devam_farabi(_devam_son_tur=3)
        assert f._devam_karari(SIMDI) is None

    def test_konusurken_gonderilmez(self):
        assert _devam_farabi(_is_speaking=True)._devam_karari(SIMDI) is None

    def test_calinacak_ses_varken_gonderilmez(self):
        f = _devam_farabi(audio_in_queue=_Kuyruk(bos=False))
        assert f._devam_karari(SIMDI) is None

    def test_sessizlik_payi_dolmadan_gonderilmez(self):
        f = _devam_farabi()
        assert f._devam_karari(100.5) is None

    def test_ses_bittikten_sonra_sayilir(self):
        # Tur 100'de bitti ama ses 105'te bitti — pay 105'ten sayılır.
        f = _devam_farabi(_sessizlik_ts=105.0)
        assert f._devam_karari(SIMDI) is None
        assert f._devam_karari(105.0 + f.DEVAM_BEKLEME_SN + 0.1) == "devam"

    def test_bos_turdan_sonra_daha_uzun_beklenir(self):
        f = _devam_farabi(_son_tur_konustu=False)
        assert f._devam_karari(SIMDI) is None
        assert f._devam_karari(100.0 + f.BOS_TUR_BEKLEME_SN + 0.1) == "devam"

    def test_duraklatilmisken_gonderilmez(self):
        f = _devam_farabi()
        f.motor.durum.duraklatildi = True
        assert f._devam_karari(SIMDI) is None

    def test_video_oynarken_gonderilmez(self):
        f = _devam_farabi(_video_yuzunden_susturuldu=True)
        assert f._devam_karari(SIMDI) is None

    def test_arac_calisirken_gonderilmez(self):
        assert _devam_farabi(_arac_suruyor=1)._devam_karari(SIMDI) is None

    def test_mikrofon_varsa_hic_calismaz(self):
        assert _devam_farabi(_mikrofonsuz=False)._devam_karari(SIMDI) is None

    def test_talimat_modunda_hic_calismaz(self):
        f = _devam_farabi(_ders_kipi=main.KIP_TALIMAT)
        assert f._devam_karari(SIMDI) is None

    def test_sure_dolunca_kapanis(self):
        f = _devam_farabi(_miksiz_baslangic=SIMDI - main.MIKSIZ_DERS_DK * 60)
        assert f._devam_karari(SIMDI) == "kapanis"

    def test_zil_yaklasinca_kapanis(self):
        f = _devam_farabi()
        f.motor.durum.kalan_dk = 2
        assert f._devam_karari(SIMDI) == "kapanis"

    def test_kapanis_konusmasi_bitince_ders_biter(self):
        f = _devam_farabi(_miksiz_kapanis_gonderildi=True)
        assert f._devam_karari(SIMDI) == "bitir"

    def test_kapanis_konusmasi_surerken_bitmez(self):
        f = _devam_farabi(_miksiz_kapanis_gonderildi=True, _is_speaking=True)
        assert f._devam_karari(SIMDI) is None


class TestDevamMesaji:
    def test_devam_mesaji_gonderilir_ve_tur_isaretlenir(self):
        f = _devam_farabi()
        f.session = _SahteSession()
        f.ui = SimpleNamespace(write_log=lambda *_a: None)
        asyncio.run(f._devam_gonder("devam"))
        assert f.session.gonderilen and "[DEVAM]" in f.session.gonderilen[0]
        assert f._devam_son_tur == f._tur_no
        assert f._devam_karari(SIMDI) is None   # aynı tura ikinci kez yok

    def test_kapanis_bir_kez(self):
        f = _devam_farabi()
        f.session = _SahteSession()
        f.ui = SimpleNamespace(write_log=lambda *_a: None)
        asyncio.run(f._devam_gonder("kapanis"))
        assert "[DERS_KAPANISI]" in f.session.gonderilen[0]
        assert f._miksiz_kapanis_gonderildi is True


# ── DERSİ BAŞLAT'ta yazılan çerçeve ────────────────────────────────────────

class TestBaslangicCercevesi:
    def _f(self, cerceve, mevcut=None):
        f = main.FarabiLive.__new__(main.FarabiLive)
        f.ui = SimpleNamespace(baslangic_cercevesi=cerceve)
        f._current_lesson = mevcut
        return f

    def test_yazilan_konu_cerceveye_girer(self):
        f = self._f({"ders": "Fizik", "konu": "Kuvvet", "kazanim": ""})
        f._baslangic_cercevesini_uygula()
        assert f._current_lesson["subject"] == "Fizik"
        assert f._current_lesson["topic"] == "Kuvvet"

    def test_bos_ders_programdakini_ezmez(self):
        mevcut = {"subject": "Kimya", "topic": "", "kazanim": ""}
        f = self._f({"ders": "", "konu": "Mol", "kazanim": ""}, mevcut)
        f._baslangic_cercevesini_uygula()
        assert f._current_lesson["subject"] == "Kimya"
        assert f._current_lesson["topic"] == "Mol"

    def test_cerceve_yoksa_dokunmaz(self):
        f = self._f(None)
        f._baslangic_cercevesini_uygula()
        assert f._current_lesson is None
