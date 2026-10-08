"""Son inceleme (2026-10-08) bulguları — FarabiYerel davranışları, ağır kurulum olmadan."""
import asyncio
import importlib
import threading
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("google.genai")


def yerel():
    ym = importlib.import_module("yerel_main")
    f = ym.FarabiYerel.__new__(ym.FarabiYerel)
    f.ui = MagicMock()
    f.ui.muted = False
    f._speaking_lock = threading.Lock()
    f._is_speaking = False
    f.audio_in_queue = asyncio.Queue()
    f._turn_done_event = asyncio.Event()
    f._loop = None
    f.oturum = None
    f._kayit, f._kayit_akisi = [], None
    f._video_yuzunden_susturuldu = False
    return ym, f


def test_cal_cumleyi_kucuk_parcalara_boler():
    ym, f = yerel()
    pcm = bytes(range(256)) * 80  # 20480 bayt ≈ 0,4 sn
    f._cal(ym._wav_yap(pcm))
    parcalar = []
    while not f.audio_in_queue.empty():
        parcalar.append(f.audio_in_queue.get_nowait())
    assert len(parcalar) > 1
    assert all(len(p) <= ym.CHUNK_SIZE * 2 for p in parcalar)
    assert b"".join(parcalar) == pcm


def test_sesi_sustur_qwen_turunu_de_keser():
    _, f = yerel()
    f.oturum = MagicMock()
    f.audio_in_queue.put_nowait(b"x")
    f._sesi_sustur()
    f.oturum.iptal.assert_called_once()
    assert f.audio_in_queue.empty()


def test_ptt_birak_mikrofon_hatasi_patlamaz():
    _, f = yerel()
    akis = MagicMock()
    akis.stop.side_effect = RuntimeError("PortAudio: device unavailable")
    f._kayit_akisi = akis
    f._ptt_birak()  # Qt yuvasında istisna = uygulama çöker (Kural 2)
    assert f._kayit_akisi is None


def test_ptt_bas_acik_eski_akisi_kapatir(monkeypatch):
    ym, f = yerel()
    eski = MagicMock()
    f._kayit_akisi = eski
    monkeypatch.setattr(ym.sd, "RawInputStream", MagicMock())
    f._ptt_bas()
    eski.close.assert_called_once()


def test_ptt_bas_birak_oturum_yokken_patlamaz(monkeypatch):
    ym, f = yerel()
    monkeypatch.setattr(ym.sd, "RawInputStream", MagicMock())
    f._ptt_bas()
    f._ptt_birak()


def test_ses_turu_bos_kalirsa_dusunuyor_durumundan_cikar():
    _, f = yerel()
    f.oturum = MagicMock()

    async def bos(wav):
        return None

    f.oturum.ses_turu = bos
    asyncio.run(f._ses_turu_calistir(b"RIFF"))
    f.ui.set_state.assert_called_with("LISTENING")


def test_ses_turu_istisnasi_yutulur_ve_loglanir(caplog):
    _, f = yerel()
    f.oturum = MagicMock()

    async def patla(wav):
        raise ValueError("bozuk wav")

    f.oturum.ses_turu = patla
    asyncio.run(f._ses_turu_calistir(b"RIFF"))
    assert "bozuk wav" in caplog.text


def test_oturumu_kapat_v1_ders_sonu_sifirlamalarini_yapar(monkeypatch):
    ym, f = yerel()
    oturum = MagicMock()
    f.oturum = oturum
    f.ui.muted = True
    f._video_yuzunden_susturuldu = True
    f._oturum_izni = asyncio.Event()
    yeni = MagicMock()
    monkeypatch.setattr(ym.transcript, "yeni_oturum_baslat", yeni)
    f._oturumu_kapat()
    oturum.iptal.assert_called_once()
    yeni.assert_called_once()
    assert f.oturum is None and f.session is None
    assert f.ui.muted is False and f._video_yuzunden_susturuldu is False
    f.ui.dersi_sifirla.assert_called_once()


def test_ders_hazirligi_patlarsa_istemci_olmez():
    ym, f = yerel()
    f.ses = MagicMock()
    f.ses.saglik.return_value = True
    f._log_startup_banner = lambda: None
    f.transcript_yeni = None

    async def patla():
        raise RuntimeError("program okunamadı")

    f._ders_hazirla = patla

    async def senaryo():
        g = asyncio.create_task(f.run())
        await asyncio.sleep(0.05)
        f._oturum_izni.set()
        await asyncio.sleep(0.3)
        bitti = g.done()
        g.cancel()
        return bitti

    assert asyncio.run(senaryo()) is False
    f.ui.dersi_sifirla.assert_called()


def test_saat_sistem_metninin_sonuna_alinir():
    ym = importlib.import_module("yerel_main")
    metin = ("[CURRENT DATE & TIME]\nRight now it is: 08.10.2026 — saat 10:05\n"
             "Use this when the lesson or the student refers to time.\n\nKURALLAR burada.")
    sonuc = ym._saati_sona_al(metin)
    assert sonuc.startswith("KURALLAR burada.")
    assert sonuc.rstrip().endswith("Use this when the lesson or the student refers to time.")
    assert ym._saati_sona_al("saatsiz metin") == "saatsiz metin"
