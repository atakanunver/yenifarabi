"""
server/tests/test_ses_cephe.py — Faz 1a ses cephesi (server/ses_cephe.py)
mock testleri (pytest). Ağsız/GPU'suz/DB'siz:

- Ollama HER ZAMAN `ses_cephe._istemci_fabrikasi` üzerinden enjekte edilen
  bir `httpx.MockTransport`'la sahtelenir — gerçek 127.0.0.1:11434'e ASLA
  gidilmez (`conftest.py`'nin `_ag_kapisi`'i yalnızca `rag.py`'yi kapsıyor,
  burada ayrıca kendi kapımız var: `_istemci_fabrikasi` her testte
  monkeypatch'lenir).
- RAG (`kitap_sorusu`) `ses_cephe._durum`/`_kitap_id_bul`/`_rag_sorgula`
  monkeypatch'lenerek sahtelenir — gerçek DB/GPU'ya hiç dokunulmaz.
- `ders_icerigi` `icerik.ders_icerigi_endpoint` monkeypatch'lenerek
  sahtelenir — gerçek NAS/PDF'e hiç dokunulmaz.

`main.app` yerine yalnızca `ses_cephe.router` bağlı izole bir FastAPI app
kullanılır (`test_auth.py::_yalitilmis_app` ile aynı desen) — `main.app`'in
lifespan'ı gerçek SentenceTransformer/CrossEncoder/PostgreSQL'e bağlanıyor,
burada gereksiz.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import httpx
import icerik
import pytest
import ses_cephe
from fastapi import FastAPI
from fastapi.testclient import TestClient

HEADER = auth.HEADER_ADI


# ── NDJSON yardımcıları (Ollama /api/chat stream biçimi, curl ile doğrulandı) ─

def _ndjson(*parcalar: dict) -> bytes:
    return b"".join((json.dumps(p, ensure_ascii=False) + "\n").encode("utf-8") for p in parcalar)


def _icerik_yaniti(metin: str) -> bytes:
    olaylar = [{"message": {"role": "assistant", "content": ch}, "done": False} for ch in metin]
    olaylar.append({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
    return _ndjson(*olaylar)


def _arac_yaniti(ad: str, args: dict, call_id: str = "call_test1") -> bytes:
    return _ndjson(
        {"message": {"role": "assistant", "content": "",
                     "tool_calls": [{"id": call_id, "function": {"index": 0, "name": ad, "arguments": args}}]},
         "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
    )


def _coklu_arac_yaniti(ad1: str, args1: dict, ad2: str, args2: dict) -> bytes:
    return _ndjson(
        {"message": {"role": "assistant", "content": "",
                     "tool_calls": [
                         {"id": "call_a", "function": {"index": 0, "name": ad1, "arguments": args1}},
                         {"id": "call_b", "function": {"index": 1, "name": ad2, "arguments": args2}},
                     ]}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
    )


def _bos_yanit() -> bytes:
    return _ndjson({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})


def _hata_yaniti(mesaj: str) -> bytes:
    return _ndjson({"error": mesaj})


def _mock_istemci_fabrikasi(cevaplar: list, gorulen_govdeler: list | None = None):
    """`ses_cephe._istemci_fabrikasi`'nin yerine geçecek fabrika üretir.
    `cevaplar`: her çağrıda sırayla döndürülecek (status_code, bytes) ya da
    yalnızca bytes (200 varsayılır). Son eleman tükenince tekrar tekrar
    döner. `gorulen_govdeler` verilirse her istek gövdesi (dict) oraya
    eklenir — testler Ollama'ya NE gönderildiğini denetleyebilir."""
    kuyruk = list(cevaplar)

    def handler(request: httpx.Request) -> httpx.Response:
        if gorulen_govdeler is not None:
            gorulen_govdeler.append(json.loads(request.content.decode("utf-8")))
        eleman = kuyruk.pop(0) if kuyruk else (cevaplar[-1] if cevaplar else (200, b""))
        if isinstance(eleman, tuple):
            kod, icerik_bytes = eleman
        else:
            kod, icerik_bytes = 200, eleman
        return httpx.Response(kod, content=icerik_bytes)

    def fabrika():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock-ollama")

    return fabrika


# ── Ortak fixture'lar ────────────────────────────────────────────────────────

TOKEN = "test-ses-token"
BOARD_KEY = "test-tahta-anahtari"


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    monkeypatch.setenv("FARABI_SES_TOKEN", TOKEN)
    monkeypatch.setenv("FARABI_SES_IZINLI", "127.0.0.1,::1,testclient")
    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
    monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": BOARD_KEY})
    # Persona sabit/kısa — testlerde tam metnin içeriği önemsiz.
    monkeypatch.setattr(ses_cephe, "_persona_metni", lambda: "PERSONA.")


@pytest.fixture
def istemci() -> TestClient:
    app = FastAPI()
    app.include_router(ses_cephe.router)
    return TestClient(app)


def _basliklar(board_key: str = BOARD_KEY) -> dict:
    return {"Authorization": f"Bearer {TOKEN}", HEADER: board_key}


def _istek_govdesi(mesaj: str, stream: bool = False, kip: str | None = None,
                    ders: str | None = None) -> dict:
    metadata = {}
    if kip is not None:
        metadata["kip"] = kip
    if ders is not None:
        metadata["ders"] = ders
    return {
        "model": "farabi-brain",
        "messages": [{"role": "user", "content": mesaj}],
        "stream": stream,
        "metadata": metadata,
    }


def _sse_olaylarini_ayikla(metin: str) -> list[dict]:
    olaylar = []
    for satir in metin.splitlines():
        if not satir.startswith("data: "):
            continue
        govde = satir[len("data: "):]
        if govde == "[DONE]":
            olaylar.append("[DONE]")
            continue
        olaylar.append(json.loads(govde))
    return olaylar


# ── /v1/models ───────────────────────────────────────────────────────────────

class TestModeller:
    def test_modeller_listesi(self, istemci):
        r = istemci.get("/v1/models", headers=_basliklar())
        assert r.status_code == 200
        veri = r.json()
        assert veri["object"] == "list"
        assert veri["data"][0]["id"] == "farabi-brain"

    def test_modeller_anahtarsiz_401(self, istemci):
        r = istemci.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 401


# ── Erişim katmanı — adres / bearer / tahta ─────────────────────────────────

class TestErisim:
    def test_izinsiz_adres_403(self, istemci, monkeypatch):
        monkeypatch.setenv("FARABI_SES_IZINLI", "10.0.0.9")  # testclient İZİNLİ DEĞİL
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"), headers=_basliklar())
        assert r.status_code == 403

    def test_token_tanimsiz_503(self, istemci, monkeypatch):
        monkeypatch.delenv("FARABI_SES_TOKEN", raising=False)
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"), headers=_basliklar())
        assert r.status_code == 503

    def test_bearer_eksik_401(self, istemci):
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"),
                          headers={HEADER: BOARD_KEY})
        assert r.status_code == 401

    def test_bearer_yanlis_401(self, istemci):
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"),
                          headers={"Authorization": "Bearer yanlis-token", HEADER: BOARD_KEY})
        assert r.status_code == 401

    def test_tahta_anahtari_yanlis_401(self, istemci):
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"),
                          headers=_basliklar(board_key="yanlis-anahtar"))
        assert r.status_code == 401

    def test_rollback_modunda_tahta_anahtari_gerekmez(self, istemci, monkeypatch):
        """FARABI_AUTH_REQUIRED=0 — tahta katmanı atlanır, metadata.derslik
        kullanılır (plan 'Erişim' madde 3 istisnası)."""
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "0")
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba.")]))
        govde = _istek_govdesi("selam")
        govde["metadata"]["derslik"] = "9-A"
        r = istemci.post("/v1/chat/completions", json=govde,
                          headers={"Authorization": f"Bearer {TOKEN}"})  # board key YOK
        assert r.status_code == 200


# ── SSE biçimi + [DONE] + stream:false ───────────────────────────────────────

class TestYanitBicimi:
    def test_stream_sse_bicimi_ve_done(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("günaydın", stream=True),
                          headers=_basliklar())
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        olaylar = _sse_olaylarini_ayikla(r.text)
        assert olaylar[-1] == "[DONE]"
        assert olaylar[0]["object"] == "chat.completion.chunk"
        assert olaylar[0]["choices"][0]["delta"]["role"] == "assistant"
        birlesik = "".join(o["choices"][0]["delta"].get("content", "") for o in olaylar[:-1]
                            if isinstance(o, dict))
        assert birlesik == "Merhaba!"
        son_chunk = olaylar[-2]
        assert son_chunk["choices"][0]["finish_reason"] == "stop"

    def test_stream_false_tek_json(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("günaydın", stream=False),
                          headers=_basliklar())
        assert r.status_code == 200
        veri = r.json()
        assert veri["object"] == "chat.completion"
        assert veri["choices"][0]["message"]["content"] == "Merhaba!"
        assert veri["choices"][0]["finish_reason"] == "stop"


# ── kip parse + araç filtresi ────────────────────────────────────────────────

class TestKip:
    def test_bilinmeyen_kip_ogretmenliye_duser(self, istemci, monkeypatch):
        gorulen = []
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")], gorulen))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("selam", kip="tanimsiz-kip"), headers=_basliklar())
        assert r.status_code == 200
        araclar = {t["function"]["name"] for t in gorulen[0].get("tools", [])}
        assert "ders_icerigi" in araclar  # ogretmenli kipteki araç seti

    def test_talimat_kipinde_ders_icerigi_yok_pencere_kapat_var(self, istemci, monkeypatch):
        gorulen = []
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Açılıyor.")], gorulen))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("youtube'u kapat", kip="talimat"), headers=_basliklar())
        assert r.status_code == 200
        araclar = {t["function"]["name"] for t in gorulen[0].get("tools", [])}
        assert "ders_icerigi" not in araclar
        assert "pencere_kapat" in araclar


# ── kitap_sorusu ─────────────────────────────────────────────────────────────

class TestKitapSorusu:
    def _hazir_ortam(self, monkeypatch, sonuc: dict, kitap_id=1):
        monkeypatch.setattr(ses_cephe, "_durum", lambda: {"hazir": True, "motor": object()})
        monkeypatch.setattr(ses_cephe, "_kitap_id_bul", lambda ders, sinif: (kitap_id, 9, "Biyoloji") if kitap_id is not None else None)
        monkeypatch.setattr(ses_cephe, "_rag_sorgula", lambda kid, soru, sinif, ders: sonuc)

    def test_once_dolgu_sonra_cevap_aynen_kaynakli(self, istemci, monkeypatch):
        self._hazir_ortam(monkeypatch, {
            "status": "ok", "answer": "Mitokondri hücrenin enerji santralidir.",
            "sources": [{"chunk_id": 1, "sayfa": 42}, {"chunk_id": 2, "sayfa": 42}, {"chunk_id": 3, "sayfa": 43}],
        })
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_arac_yaniti("kitap_sorusu", {"soru": "x", "ders": "biyoloji"})]))
        govde = _istek_govdesi("Mitokondri nedir, kitaba göre?", ders="biyoloji")
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        metin = r.json()["choices"][0]["message"]["content"]
        assert metin.startswith("Kitaba bakıyorum. ")
        assert "Mitokondri hücrenin enerji santralidir." in metin
        assert "sayfa 42, 43" in metin
        # Kaynak satırı modelin "biyoloji" argümanını değil kitabın DB
        # kaydını kullanır (main.py::soru_sor ile aynı biçim).
        assert "Kaynak: 9. Sınıf Biyoloji, sayfa 42, 43." in metin

    def test_soru_metni_kullanici_mesajindan_alinir(self, istemci, monkeypatch):
        """Plan madde 4: RAG'a giden soru MODEL ARGÜMANI değil kullanıcının
        SON mesajı olmalı (qwen 'ı'→'i' bozabiliyor)."""
        yakalanan = {}

        def _sahte_rag(kid, soru, sinif, ders):
            yakalanan["soru"] = soru
            return {"status": "ok", "answer": "cevap", "sources": []}

        monkeypatch.setattr(ses_cephe, "_durum", lambda: {"hazir": True, "motor": object()})
        monkeypatch.setattr(ses_cephe, "_kitap_id_bul", lambda ders, sinif: (1, 9, "Biyoloji"))
        monkeypatch.setattr(ses_cephe, "_rag_sorgula", _sahte_rag)
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("kitap_sorusu", {"soru": "MODELIN UYDURDUGU FARKLI SORU", "ders": "biyoloji"})]))
        govde = _istek_govdesi("Kullanıcının GERÇEK sorusu bu.", ders="biyoloji")
        istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert yakalanan["soru"] == "Kullanıcının GERÇEK sorusu bu."

    def test_ders_yoksa_soru_sorulmaz_rag_cagrilmaz(self, istemci, monkeypatch):
        cagrildi = {"deger": False}

        def _sahte_rag(*a, **kw):
            cagrildi["deger"] = True
            return {"status": "ok", "answer": "x", "sources": []}

        monkeypatch.setattr(ses_cephe, "_durum", lambda: {"hazir": True, "motor": object()})
        monkeypatch.setattr(ses_cephe, "_kitap_id_bul", lambda ders, sinif: (1, 9, "Biyoloji"))
        monkeypatch.setattr(ses_cephe, "_rag_sorgula", _sahte_rag)
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("kitap_sorusu", {"soru": "x"})]))  # ders YOK, metadata.ders da YOK
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("bir şey sor"), headers=_basliklar())
        assert r.status_code == 200
        assert "Hangi dersin kitabına bakayım?" in r.json()["choices"][0]["message"]["content"]
        assert cagrildi["deger"] is False

    @pytest.mark.parametrize("durum_kodu,beklenen", [
        ("yetersiz_kaynak", "Bu bilgi ders kitabında bu haliyle bulunmuyor."),
        ("sayi_kontrolu_reddi", "Bu bilgi ders kitabında bu haliyle bulunmuyor."),
        ("hata", "Şu an kitaba ulaşamıyorum."),
    ])
    def test_ret_durumlarinin_cumleleri(self, istemci, monkeypatch, durum_kodu, beklenen):
        self._hazir_ortam(monkeypatch, {"status": durum_kodu, "answer": None, "sources": []})
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("kitap_sorusu", {"soru": "x", "ders": "biyoloji"})]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("soru?", ders="biyoloji"), headers=_basliklar())
        assert beklenen in r.json()["choices"][0]["message"]["content"]

    def test_hazir_degilse_ulasilamiyor_cumlesi(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_durum", lambda: {"hazir": False, "motor": None})
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("kitap_sorusu", {"soru": "x", "ders": "biyoloji"})]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("soru?", ders="biyoloji"), headers=_basliklar())
        assert "Şu an kitaba ulaşamıyorum." in r.json()["choices"][0]["message"]["content"]

    def test_kitap_bulunamazsa_ulasilamiyor_cumlesi(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_durum", lambda: {"hazir": True, "motor": object()})
        monkeypatch.setattr(ses_cephe, "_kitap_id_bul", lambda ders, sinif: None)
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("kitap_sorusu", {"soru": "x", "ders": "uzaybilimi"})]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("soru?", ders="uzaybilimi"), headers=_basliklar())
        assert "Şu an kitaba ulaşamıyorum." in r.json()["choices"][0]["message"]["content"]


# ── ders_icerigi ─────────────────────────────────────────────────────────────

class TestDersIcerigi:
    def test_derslik_gecirilir(self, istemci, monkeypatch):
        yakalanan = {}

        def _sahte_endpoint(istek):
            yakalanan["derslik"] = istek.derslik
            return icerik.KonuYanit(status="ok", metin="KİTAP METNİ BURADA", baslik="X",
                                     latency_ms=1, request_id="r1")

        monkeypatch.setattr(icerik, "ders_icerigi_endpoint", _sahte_endpoint)
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi([
            _arac_yaniti("ders_icerigi", {"konu": "hücre", "ders": "biyoloji"}),
            _icerik_yaniti("Hücre, canlıların yapı taşıdır."),
        ]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("hücreyi anlat"),
                          headers=_basliklar())  # board key 9-A -> derslik=9-A
        assert r.status_code == 200
        assert yakalanan["derslik"] == "9-A"
        assert "Hücre" in r.json()["choices"][0]["message"]["content"]

    def test_status_ok_degilse_bulunamadi_cumlesi(self, istemci, monkeypatch):
        monkeypatch.setattr(icerik, "ders_icerigi_endpoint",
                             lambda istek: icerik.KonuYanit(status="bulunamadi", metin=None,
                                                             latency_ms=1, request_id="r1"))
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi([
            _arac_yaniti("ders_icerigi", {"konu": "yok-olan-konu"}),
        ]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("bir konu anlat"), headers=_basliklar())
        assert "Bu konuyu kitapta bulamadım." in r.json()["choices"][0]["message"]["content"]


# ── Tahta araçları — tool_calls + finish_reason, sonraki istekte tool sonucu ─

class TestTahtaAraclari:
    def test_pdf_sayfa_tool_calls_ve_finish_reason(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("pdf_sayfa", {"sayfa": 9, "ders": "biyoloji"}, call_id="call_pdf1")]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("9. sayfayı göster", stream=False), headers=_basliklar())
        assert r.status_code == 200
        veri = r.json()
        assert veri["choices"][0]["finish_reason"] == "tool_calls"
        assert veri["choices"][0]["message"]["content"] is None
        tc = veri["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "pdf_sayfa"
        assert json.loads(tc["function"]["arguments"]) == {"sayfa": 9, "ders": "biyoloji"}
        assert tc["id"] == "call_pdf1"

    def test_pdf_sayfa_stream_tool_calls_delta(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("pdf_sayfa", {"sayfa": 9, "ders": "biyoloji"}, call_id="call_pdf1")]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("9. sayfayı göster", stream=True), headers=_basliklar())
        olaylar = _sse_olaylarini_ayikla(r.text)
        assert olaylar[-1] == "[DONE]"
        tool_delta = next(o for o in olaylar[:-1] if o["choices"][0]["delta"].get("tool_calls"))
        tc = tool_delta["choices"][0]["delta"]["tool_calls"][0]
        assert tc["index"] == 0
        assert tc["function"]["name"] == "pdf_sayfa"
        son = olaylar[-2]
        assert son["choices"][0]["finish_reason"] == "tool_calls"

    def test_tool_sonucu_iceren_takip_istegi(self, istemci, monkeypatch):
        """Ses düğümü tahtada aracı çalıştırıp sonucu `tool` mesajıyla YENİ
        bir istekte gönderir — bu, ajanın ikinci kez içerik üretmesiyle
        sonuçlanmalı (döngü 1. adımdan devam eder)."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("9. sayfada hücre bölünmesi var.")]))
        govde = _istek_govdesi("bu sayfada ne var")
        govde["messages"] = [
            {"role": "user", "content": "9. sayfayı göster"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_pdf1", "type": "function",
                 "function": {"name": "pdf_sayfa", "arguments": json.dumps({"sayfa": 9})}}]},
            {"role": "tool", "tool_call_id": "call_pdf1", "content": "Sayfa gösterildi."},
        ]
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        assert "hücre bölünmesi" in r.json()["choices"][0]["message"]["content"]

    def test_coklu_arac_yalnizca_ilki_kullanilir(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_coklu_arac_yaniti("pdf_sayfa", {"sayfa": 3}, "yks_sorulari", {"konu": "türev"})]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("bir şey yap"), headers=_basliklar())
        veri = r.json()
        tcs = veri["choices"][0]["message"]["tool_calls"]
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "pdf_sayfa"

    def test_kipte_kapali_arac_yok_sayilir(self, istemci, monkeypatch):
        """Model kip filtresine RAĞMEN talimat-dışı bir kipte pencere_kapat
        döndürürse (araçlar listesine hiç gönderilmediği halde) düşüş
        cümlesi verilir, ham tool_calls İLETİLMEZ."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", _mock_istemci_fabrikasi(
            [_arac_yaniti("pencere_kapat", {"hedef": "youtube"})]))
        r = istemci.post("/v1/chat/completions",
                          json=_istek_govdesi("youtube'u kapat", kip="ogretmenli"), headers=_basliklar())
        veri = r.json()
        assert veri["choices"][0]["finish_reason"] != "tool_calls"
        assert "Bunu şu an yapamıyorum." in veri["choices"][0]["message"]["content"]


# ── Boş cevap → tek yeniden deneme → düşüş cümlesi ──────────────────────────

class TestBosCevap:
    def test_bos_cevap_bir_kez_yeniden_dener_sonra_duser(self, istemci, monkeypatch):
        gorulen = []
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_bos_yanit(), _bos_yanit()], gorulen))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("hı"), headers=_basliklar())
        assert r.status_code == 200
        assert "Anlayamadım, tekrar eder misiniz?" in r.json()["choices"][0]["message"]["content"]
        assert len(gorulen) == 2  # ilk deneme + tam olarak BİR yeniden deneme

    def test_ilk_bos_ikinci_icerikli_basarili_sayilir(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_bos_yanit(), _icerik_yaniti("Merhaba!")]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("hı"), headers=_basliklar())
        assert r.json()["choices"][0]["message"]["content"] == "Merhaba!"


# ── Hata / zaman aşımı — stream başladıktan sonra 500 asla, özür + [DONE] ────

class TestHataVeZamanAsimi:
    def test_ollama_http_hatasi_ozur_cumlesi(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([(500, b"internal error")]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"), headers=_basliklar())
        assert r.status_code == 200  # ASLA çıplak 500
        assert "Şu an yanıt veremiyorum." in r.json()["choices"][0]["message"]["content"]

    def test_ollama_ndjson_hata_satiri_ozur_cumlesi(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_hata_yaniti("model bulunamadı")]))
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"), headers=_basliklar())
        assert r.status_code == 200
        assert "Şu an yanıt veremiyorum." in r.json()["choices"][0]["message"]["content"]

    def test_karar_zaman_asimi_ozur_cumlesi(self, istemci, monkeypatch):
        """`asyncio.wait_for`'ın kalan süresi <=0 olacak şekilde karar zaman
        aşımını sıfıra indirip gerçek bir Ollama yanıtı hiç göndermeden
        zaman aşımı yolunu tetikler."""
        monkeypatch.setattr(ses_cephe, "KARAR_ZAMAN_ASIMI_SN", 0.01)
        monkeypatch.setattr(ses_cephe, "GENEL_ZAMAN_ASIMI_SN", 0.01)

        async def _sonsuz_bekleme(request):
            import asyncio as _asyncio
            await _asyncio.sleep(1)
            return httpx.Response(200, content=_icerik_yaniti("gec gelen"))

        def fabrika():
            return httpx.AsyncClient(transport=httpx.MockTransport(_sonsuz_bekleme), base_url="http://mock")

        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", fabrika)
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam"), headers=_basliklar())
        assert r.status_code == 200
        assert "Şu an yanıt veremiyorum." in r.json()["choices"][0]["message"]["content"]

    def test_stream_ortasi_istisna_ozur_ve_done(self, istemci, monkeypatch):
        """İçerik akışı BAŞLADIKTAN SONRA bağlantı kopması/istisna — plan
        madde 6: hiçbir istisna 500'e dönmez, özür + [DONE] ile biter."""

        async def _yaricak_akis(request):
            raise httpx.RemoteProtocolError("bağlantı koptu")

        def fabrika():
            return httpx.AsyncClient(transport=httpx.MockTransport(_yaricak_akis), base_url="http://mock")

        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi", fabrika)
        r = istemci.post("/v1/chat/completions", json=_istek_govdesi("selam", stream=True), headers=_basliklar())
        assert r.status_code == 200
        olaylar = _sse_olaylarini_ayikla(r.text)
        assert olaylar[-1] == "[DONE]"
        icerikler = "".join(o["choices"][0]["delta"].get("content", "") for o in olaylar[:-1])
        assert "Şu an yanıt veremiyorum." in icerikler


# ── Geçmiş kırpma ────────────────────────────────────────────────────────────

class TestGecmisKirpma:
    def test_gecmis_kullanici_sinirinda_kirpilir(self):
        cok_uzun = "x" * 6000  # ~2222 token — MAX_GECMIS_TOKEN (2000) tek başına aşar
        mesajlar = [
            {"role": "user", "content": cok_uzun},
            {"role": "assistant", "content": "eski cevap"},
            {"role": "user", "content": "son soru"},
        ]
        kirpilmis = ses_cephe._gecmis_kirp(mesajlar)
        # son kullanıcı mesajı HER ZAMAN kalır
        assert kirpilmis[-1]["content"] == "son soru"
        # kırpılmış geçmiş bir 'tool' ya da yalın assistant.tool_calls İLE BAŞLAMAZ
        assert kirpilmis[0]["role"] in ("user", "system")

    def test_bos_gecmis_hata_vermez(self):
        assert ses_cephe._gecmis_kirp([]) == []

    def test_kisa_gecmis_kirpilmaz(self):
        mesajlar = [{"role": "user", "content": "kısa"}, {"role": "assistant", "content": "kısa cevap"},
                    {"role": "user", "content": "son"}]
        assert ses_cephe._gecmis_kirp(mesajlar) == mesajlar


# ── Mesaj dönüştürme ──────────────────────────────────────────────────────────

class TestMesajDonusumu:
    def test_icerik_listesi_metne_indirgenir(self):
        assert ses_cephe._icerik_metni([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "ab"

    def test_icerik_none_bos_dize(self):
        assert ses_cephe._icerik_metni(None) == ""

    def test_tool_calls_arguments_json_string_dicte_cevrilir(self):
        mesajlar = [ses_cephe.SohbetMesaji(role="assistant", content="", tool_calls=[
            {"id": "call_1", "type": "function",
             "function": {"name": "pdf_sayfa", "arguments": json.dumps({"sayfa": 5})}}])]
        sonuc = ses_cephe._ollama_mesajlarina_cevir(mesajlar)
        assert sonuc[0]["tool_calls"][0]["function"]["arguments"] == {"sayfa": 5}

    def test_system_mesaji_yok_sayilir(self):
        mesajlar = [ses_cephe.SohbetMesaji(role="system", content="istemci sistemi"),
                    ses_cephe.SohbetMesaji(role="user", content="soru")]
        sonuc = ses_cephe._ollama_mesajlarina_cevir(mesajlar)
        assert len(sonuc) == 1
        assert sonuc[0]["role"] == "user"

    def test_developer_mesaji_yok_sayilir(self):
        """Pipecat'in OpenAILLMService'i (async function call akışında)
        bağlama 'developer' rollü bir mesaj koyabiliyor (OpenAI'nin
        system'in yeni adı) — system gibi YOK SAYILMALI."""
        mesajlar = [ses_cephe.SohbetMesaji(role="developer", content="geliştirici talimatı"),
                    ses_cephe.SohbetMesaji(role="user", content="soru")]
        sonuc = ses_cephe._ollama_mesajlarina_cevir(mesajlar)
        assert len(sonuc) == 1
        assert sonuc[0]["role"] == "user"

    def test_bilinmeyen_rol_yok_sayilir_cokmez(self):
        """Tanınan yalnızca user/assistant/tool — başka HERHANGİ bir rol
        (gelecekteki bir SDK rolü) sessizce atlanır, asla çökme sebebi
        olmaz."""
        mesajlar = [ses_cephe.SohbetMesaji(role="function", content="eski OpenAI biçimi"),
                    ses_cephe.SohbetMesaji(role="user", content="soru")]
        sonuc = ses_cephe._ollama_mesajlarina_cevir(mesajlar)
        assert len(sonuc) == 1
        assert sonuc[0]["role"] == "user"


# ── Pipecat uyumluluğu (2026-09-25, kaynak araştırmasıyla doğrulandı) ───────

class TestPipecatUyumlulugu:
    def test_stream_options_alani_hata_vermez(self, istemci, monkeypatch):
        """Pipecat'in OpenAILLMService'i HER ZAMAN `stream: true` +
        `stream_options: {"include_usage": true}` gönderir (base_llm.py) —
        bu alan bilinmeyen/gereksiz, ama isteği 422 ile REDDETMEMELİ."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")]))
        govde = _istek_govdesi("selam", stream=True)
        govde["stream_options"] = {"include_usage": True}
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200

    def test_metadata_string_degerler_kabul_edilir(self, istemci, monkeypatch):
        """openai SDK'nın `metadata: Dict[str, str]` alanı TÜM değerleri
        dize olarak gönderir — kip/ders/derslik zaten `str | None` alanlar,
        ekstra bir tür dönüşümü gerekmiyor."""
        gorulen = []
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Açılıyor.")], gorulen))
        govde = {
            "model": "farabi-brain", "stream": False,
            "messages": [{"role": "user", "content": "youtube'u kapat"}],
            "metadata": {"kip": "talimat", "ders": "biyoloji", "derslik": "10-B"},
        }
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        araclar = {t["function"]["name"] for t in gorulen[0].get("tools", [])}
        assert "pencere_kapat" in araclar  # kip="talimat" doğru ayrıştırıldı

    def test_arac_sonucu_tool_mesaji_json_govde_ile_cokmez(self, istemci, monkeypatch):
        """Pipecat'te tool sonucu `json.dumps(result, ensure_ascii=False)`
        (bir JSON OBJESİ dizesi) olarak `tool` mesajının content'ine gelir,
        orijinal tool_call_id korunur — düz metinden farklı biçimi çökmeye
        sebep olmamalı."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("9. sayfa gösterildi.")]))
        govde = _istek_govdesi("bu sayfada ne var")
        govde["messages"] = [
            {"role": "user", "content": "9. sayfayı göster"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_abc12345", "type": "function",
                 "function": {"name": "pdf_sayfa", "arguments": json.dumps({"sayfa": 9})}}]},
            {"role": "tool", "tool_call_id": "call_abc12345",
             "content": json.dumps({"status": "ok", "sayfa": 9}, ensure_ascii=False)},
        ]
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        assert "9. sayfa gösterildi." in r.json()["choices"][0]["message"]["content"]

    def test_devam_eden_arac_in_progress_tool_mesaji_cokmez(self, istemci, monkeypatch):
        """Araç hâlâ çalışırken Pipecat context'inde `tool` mesajının
        content'i 'IN_PROGRESS' olabilir — gerçek bir sonuç DEĞİLDİR, ama
        cepheyi ÇÖKERTMEMELİ; olduğu gibi içerik olarak geçer."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Devam ediyorum.")]))
        govde = _istek_govdesi("bekleniyor")
        govde["messages"] = [
            {"role": "user", "content": "bir görsel oluştur"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_xyz", "type": "function",
                 "function": {"name": "pdf_sayfa", "arguments": json.dumps({"sayfa": 1})}}]},
            {"role": "tool", "tool_call_id": "call_xyz", "content": "IN_PROGRESS"},
            {"role": "user", "content": "devam ediyor musun?"},
        ]
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        assert "Devam ediyorum." in r.json()["choices"][0]["message"]["content"]

    def test_bilinmeyen_model_adi_reddedilmez(self, istemci, monkeypatch):
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")]))
        govde = _istek_govdesi("selam")
        govde["model"] = "gpt-4o-tamamen-farkli-bir-ad"
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
        assert r.json()["model"] == "farabi-brain"  # cephe HER ZAMAN kendi model id'siyle döner

    def test_arac_gonderilmeyen_istek_hata_vermez(self, istemci, monkeypatch):
        """Pipecat, kayıtlı hiçbir fonksiyon yokken `tools` alanını hiç
        göndermez — cephenin kendi araç seçimi buna bağlı değil."""
        monkeypatch.setattr(ses_cephe, "_istemci_fabrikasi",
                             _mock_istemci_fabrikasi([_icerik_yaniti("Merhaba!")]))
        govde = _istek_govdesi("selam")
        assert "tools" not in govde and "tool_choice" not in govde
        r = istemci.post("/v1/chat/completions", json=govde, headers=_basliklar())
        assert r.status_code == 200
