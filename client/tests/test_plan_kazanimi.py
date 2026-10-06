"""
main.py — yıllık plan kazanımı (GET /api/egitim/kazanim) ders çerçevesine işlenir.

Karar (2026-10-06): "Planı kullan, konuyu sor" — kazanım plandan gelir
(kazanim_kaynagi="plan"), konu YİNE öğretmene sorulur; öğretmen kazanım
yazarsa/söylerse plan alanları ezilir. Ağ hiç kullanılmaz (requests sahte).
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import requests  # noqa: E402

import main  # noqa: E402


class _Yanit:
    def __init__(self, kod=200, veri=None, bozuk=False):
        self.status_code = kod
        self._veri = veri
        self._bozuk = bozuk

    def json(self):
        if self._bozuk:
            raise ValueError("bozuk json")
        return self._veri


def _sahte_get(monkeypatch, yanit=None, hata=None):
    cagrilar = []

    def get(url, **kw):
        cagrilar.append((url, kw))
        if hata:
            raise hata
        return yanit

    monkeypatch.setattr(requests, "get", get)
    return cagrilar


TAMAM = {"durum": "tamam", "ders": "matematik", "hafta": 4,
         "kazanimlar": ["12.1.2.2. Birinci", "12.1.2.3. İkinci"]}


def _farabi(cerceve=None) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = cerceve
    f._son_isitilan_konu = None
    f._loop = None
    f.motor = SimpleNamespace(durum=SimpleNamespace(ders_adi="", konu=""))
    f.ui = SimpleNamespace(baslangic_cercevesi={})
    return f


def _cerceve():
    return {"subject": "matematik", "unit": "", "topic": "", "kazanim": "",
            "kazanim_kodu": "", "kazanimlar": [], "kazanim_kaynagi": "", "period": 3}


def test_basarida_alanlar_dolar(monkeypatch):
    cagrilar = _sahte_get(monkeypatch, _Yanit(200, TAMAM))
    sonuc = main.FarabiLive._plan_kazanimini_getir("12-A", 3)
    assert sonuc["kazanim"] == "12.1.2.2. Birinci; 12.1.2.3. İkinci"
    assert sonuc["kazanimlar"] == TAMAM["kazanimlar"]
    assert sonuc["kazanim_kodu"] == "12.1.2.2."
    assert sonuc["kazanim_kaynagi"] == "plan"
    url, kw = cagrilar[0]
    assert url.endswith("/api/egitim/kazanim")
    assert kw["params"] == {"derslik": "12-A", "ders_no": 3}
    assert kw["timeout"] <= 3.0


def test_kod_yoksa_bos(monkeypatch):
    _sahte_get(monkeypatch, _Yanit(200, {"durum": "tamam", "kazanimlar": ["Serbest metin"]}))
    assert main.FarabiLive._plan_kazanimini_getir("12-A", 3)["kazanim_kodu"] == ""


@pytest.mark.parametrize("yanit,hata", [
    (None, requests.Timeout("zaman aşımı")),
    (None, requests.ConnectionError("ağ yok")),
    (_Yanit(500, {}), None),
    (_Yanit(401, {}), None),
    (_Yanit(200, bozuk=True), None),
    (_Yanit(200, {"durum": "yok"}), None),
    (_Yanit(200, ["liste"]), None),
])
def test_hatada_sessizce_none(monkeypatch, yanit, hata):
    _sahte_get(monkeypatch, yanit, hata)
    assert main.FarabiLive._plan_kazanimini_getir("12-A", 3) is None


def test_derslik_bossa_istek_atilmaz(monkeypatch):
    cagrilar = _sahte_get(monkeypatch, _Yanit(200, TAMAM))
    assert main.FarabiLive._plan_kazanimini_getir("", 3) is None
    assert cagrilar == []


def test_cerceveye_islenir(monkeypatch):
    _sahte_get(monkeypatch, _Yanit(200, TAMAM))
    f = _farabi(_cerceve())
    monkeypatch.setattr(main.tahta, "derslik", lambda: "12-A")
    asyncio.run(f._cerceveye_plan_kazanimi_ekle())
    assert f._current_lesson["kazanim_kaynagi"] == "plan"
    assert f._current_lesson["kazanimlar"] == TAMAM["kazanimlar"]
    assert f._current_lesson["topic"] == ""


def test_cerceve_hatada_bos_kalir(monkeypatch):
    _sahte_get(monkeypatch, hata=requests.Timeout("x"))
    f = _farabi(_cerceve())
    monkeypatch.setattr(main.tahta, "derslik", lambda: "12-A")
    asyncio.run(f._cerceveye_plan_kazanimi_ekle())
    assert f._current_lesson == _cerceve()


def test_cerceve_yoksa_dokunulmaz(monkeypatch):
    cagrilar = _sahte_get(monkeypatch, _Yanit(200, TAMAM))
    f = _farabi(None)
    asyncio.run(f._cerceveye_plan_kazanimi_ekle())
    assert f._current_lesson is None and cagrilar == []


def _plan_cercevesi():
    c = _cerceve()
    c.update(kazanim="A; B", kazanimlar=["A", "B"], kazanim_kodu="12.1.", kazanim_kaynagi="plan")
    return c


def test_ogretmen_yazili_kazanim_plani_ezer():
    f = _farabi(_plan_cercevesi())
    f._cerceveyi_ogretmenden_guncelle("konu: Türev · kazanım: Anlık değişim hızı")
    c = f._current_lesson
    assert c["kazanim"] == "Anlık değişim hızı"
    assert c["kazanimlar"] == [] and c["kazanim_kodu"] == ""
    assert c["kazanim_kaynagi"] == "ogretmen"


def test_ogretmen_yalniz_konu_planin_kazanimini_korur():
    f = _farabi(_plan_cercevesi())
    f._cerceveyi_ogretmenden_guncelle("konu: Türev")
    c = f._current_lesson
    assert c["topic"] == "Türev" and c["kazanim"] == "A; B"
    assert c["kazanim_kaynagi"] == "plan"


def test_baslangic_cercevesi_kazanimi_plani_ezer():
    f = _farabi(_plan_cercevesi())
    f.ui.baslangic_cercevesi = {"ders": "", "konu": "Limit", "kazanim": "Limit tanımı"}
    f._baslangic_cercevesini_uygula()
    c = f._current_lesson
    assert c["kazanim"] == "Limit tanımı" and c["kazanim_kaynagi"] == "ogretmen"
    assert c["kazanimlar"] == []


# ── Sistem talimatı ────────────────────────────────────────────────────────

def _sistem_metni(cerceve) -> str:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._current_lesson = cerceve
    f._ders_kipi = main.KIP_OGRETMENLI
    f._ders_kipi_taban = main.KIP_OGRETMENLI
    si = f._build_config().system_instruction
    return si if isinstance(si, str) else "".join(p.text for p in si.parts)


def test_prompt_plan_kazanimi_etiketi_ve_konu_istegi():
    metin = _sistem_metni(_plan_cercevesi())
    assert "Kazanım (yıllık plan, bu hafta): A; B" in metin
    assert "[KONU BEKLENİYOR]" in metin
    assert "Yıllık plana göre bu haftanın kazanımı yukarıda" in metin


def test_prompt_plan_kazanimi_konu_varsa_konu_istenmez():
    c = _plan_cercevesi()
    c["topic"] = "Türev"
    assert "[KONU BEKLENİYOR]" not in _sistem_metni(c)


def test_prompt_ogretmen_kazanimi_eski_etiket():
    c = _plan_cercevesi()
    c.update(kazanim="Limit", kazanim_kaynagi="ogretmen")
    metin = _sistem_metni(c)
    # Yalnızca etikete bak: genel sistem metni "yıllık plan" ifadesini başka
    # bağlamda zaten içeriyor.
    assert "Kazanım: Limit" in metin and "Kazanım (yıllık plan, bu hafta)" not in metin
    assert "[KONU BEKLENİYOR]" not in metin


def test_prompt_kazanimsiz_eski_blok_aynen():
    metin = _sistem_metni(_cerceve())
    assert "[KONU BEKLENİYOR]" in metin
    assert "konu ve kazanım henüz" in metin
