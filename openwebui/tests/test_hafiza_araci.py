import asyncio

import farabi_hafiza_araci as fh

ADMIN = {"role": "admin", "id": "u1"}
USER = {"role": "user", "id": "u2"}


class Yanit:
    status_code = 200

    def __init__(self, v):
        self.v = v

    def json(self):
        return self.v


def _arac(monkeypatch, yanit=None, istisna=None):
    cagrilar = []

    class Istemci:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, headers, json):
            cagrilar.append((url, headers, json))
            if istisna:
                raise istisna
            return Yanit(yanit)

    monkeypatch.setattr(fh.httpx, "AsyncClient", Istemci)
    t = fh.Tools()
    t.valves.api_key = "WK"
    return t, cagrilar


def _c(x):
    return asyncio.run(x)


def test_yalniz_yonetici_sunucuya_gitmez(monkeypatch):
    t, c = _arac(monkeypatch, {"durum": "ok", "kayitlar": []})
    for cikti in (_c(t.hafizaya_kaydet("b", "i", __user__=USER)), _c(t.hafizada_ara("x", __user__=USER)),
                  _c(t.hafizayi_unut(1, __user__=USER))):
        assert "yalnızca yönetici" in cikti
    assert c == []


def test_taslak_henuz_kaydedilmedi_der(monkeypatch):
    y = {"durum": "taslak", "onizleme": {"tur": "bilgi", "baslik": "Nöbet", "icerik": "Pazartesi", "son_gecerlilik": None},
         "benzer": [{"id": 3, "baslik": "Eski nöbet"}]}
    t, c = _arac(monkeypatch, y)
    cikti = _c(t.hafizaya_kaydet("Nöbet", "Pazartesi", __user__=ADMIN))
    assert "KAYDEDİLMEDİ" in cikti and "#3 Eski nöbet" in cikti and "onaylandi=True" in cikti
    assert c[0][0].endswith("/kaydet") and c[0][1] == {"X-Farabi-WebUI-Key": "WK"} and c[0][2]["onaylandi"] is False


def test_onayli_kayit_ve_sonuc_metinleri(monkeypatch):
    t, c = _arac(monkeypatch, {"durum": "kaydedildi", "id": 7, "embedding": True})
    assert _c(t.hafizaya_kaydet("b", "i", onaylandi=True, __user__=ADMIN)) == "Kaydedildi (#7)."
    assert c[0][2]["onaylandi"] is True
    t, _ = _arac(monkeypatch, {"durum": "guncellendi", "id": 4})
    assert "güncellendi (#4)" in _c(t.hafizaya_kaydet("b", "i", onaylandi=True, __user__=ADMIN))
    t, _ = _arac(monkeypatch, {"durum": "dolu", "neden": "sınırda"})
    assert _c(t.hafizaya_kaydet("b", "i", onaylandi=True, __user__=ADMIN)).startswith("KAYDEDİLMEDİ")


def test_tarih_gecersizse_gonderilmez(monkeypatch):
    t, c = _arac(monkeypatch, {})
    assert "YYYY-AA-GG" in _c(t.hafizaya_kaydet("b", "i", son_gecerlilik="30 Haziran", __user__=ADMIN))
    assert c == []


def test_ulasilamadi_kaydettim_dedirtmez_ve_istisna_sizmaz(monkeypatch):
    t, _ = _arac(monkeypatch, istisna=RuntimeError("SIR-AYRINTI"))
    k = _c(t.hafizaya_kaydet("b", "i", onaylandi=True, __user__=ADMIN))
    assert "KAYDEDİLMEDİ" in k and "SIR-AYRINTI" not in k
    assert "UNUTULMADI" in _c(t.hafizayi_unut(1, __user__=ADMIN))


def test_ara_listeler_ve_bos_sonucta_uydurtmaz(monkeypatch):
    k = {"id": 2, "tur": "karar", "baslik": "Nöbet", "icerik": "Pazartesi", "tarih": "2026-10-15",
         "sabit": False, "son_gecerlilik": "2026-12-01"}
    t, _ = _arac(monkeypatch, {"durum": "ok", "kayitlar": [k]})
    c = _c(t.hafizada_ara("nöbet", __user__=ADMIN))
    assert "#2 [karar] Nöbet: Pazartesi (2026-10-15, son geçerlilik 2026-12-01)" in c
    t, _ = _arac(monkeypatch, {"durum": "ok", "kayitlar": []})
    assert "uydurma" in _c(t.hafizada_ara("x", __user__=ADMIN))


def test_unut(monkeypatch):
    t, _ = _arac(monkeypatch, {"durum": "unutuldu", "id": 5})
    assert _c(t.hafizayi_unut(5, __user__=ADMIN)) == "Unutuldu (#5)."
    t, _ = _arac(monkeypatch, {"durum": "bulunamadi", "id": 9})
    assert "bulunamadı" in _c(t.hafizayi_unut(9, __user__=ADMIN))
