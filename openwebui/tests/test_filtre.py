import asyncio
import time

import farabi_filtre as ff

KIMYA = {"info": {"meta": {"farabi_kapsam": "kimya", "farabi_think": False}}}
DERIN = {"info": {"meta": {"farabi_kapsam": "genel", "farabi_think": True}}}
ALMANCA = {"info": {"meta": {"farabi_kapsam": None, "farabi_think": False}}}
OK = {"durum": "ok", "parcalar": [{"kaynak": "Kimya 10, s. 84", "metin": "Mol, madde miktarı birimidir."}]}


def _govde(icerik="mol nedir", sistem=None):
    m = [{"role": "user", "content": icerik}]
    if sistem:
        m.insert(0, {"role": "system", "content": sistem})
    return {"model": "farabi-kimya", "messages": m}


def _filtre(sonuc=OK, gecikme=0.0, cagrilar=None):
    f = ff.Filter()

    def _sahte_ara(kapsam, soru):
        if cagrilar is not None:
            cagrilar.append((kapsam, soru))
        time.sleep(gecikme)
        return sonuc
    f._ara = _sahte_ara
    return f


def _calistir(f, govde, model=KIMYA, meta=None):
    return asyncio.run(f.inlet(govde, __model__=model, __metadata__=meta or {}))


def test_ok_sonucu_sistem_mesajina_eklenir():
    g = _calistir(_filtre(), _govde())
    assert g["messages"][0]["role"] == "system"
    assert "[1] Kimya 10, s. 84" in g["messages"][0]["content"]
    assert "Mol, madde miktarı birimidir." in g["messages"][0]["content"]


def test_var_olan_sistem_mesajinin_sonuna_eklenir():
    g = _calistir(_filtre(), _govde(sistem="Sen Farabi'sin."))
    assert g["messages"][0]["content"].startswith("Sen Farabi'sin.")
    assert "Kimya 10, s. 84" in g["messages"][0]["content"]
    assert len([m for m in g["messages"] if m["role"] == "system"]) == 1


def test_zayif_sonucta_genel_bilgi_notu():
    g = _calistir(_filtre({"durum": "zayif", "parcalar": []}), _govde())
    assert "bulunamadı" in g["messages"][0]["content"]


def test_hata_sonucunda_mesajlar_degismez():
    g = _calistir(_filtre({"durum": "hata", "parcalar": []}), _govde())
    assert g["messages"] == _govde()["messages"]


def test_api_ulasilamazsa_govde_degismez():
    f = ff.Filter()
    f.valves.api_url = "http://127.0.0.1:9/api/webui/ara"   # kapalı port
    f.valves.zaman_asimi_sn = 1.0
    g = _calistir(f, _govde())
    assert g["messages"] == _govde()["messages"]


def test_gorev_isteginde_arama_yapilmaz():
    c = []
    g = _calistir(_filtre(cagrilar=c), _govde(), meta={"task": "title_generation"})
    assert c == [] and g["messages"] == _govde()["messages"]


def test_kapsamsiz_modda_arama_yapilmaz_ama_think_ayarlanir():
    c = []
    g = _calistir(_filtre(cagrilar=c), _govde(), model=ALMANCA)
    assert c == [] and g["think"] is False


def test_think_varsayilani_moddan():
    assert _calistir(_filtre(), _govde())["think"] is False
    assert _calistir(_filtre(), _govde(), model=DERIN)["think"] is True


def test_kullanici_think_secimi_EZILMEZ():
    g = _govde()
    g["think"] = True
    assert _calistir(_filtre(), g)["think"] is True
    g2 = _govde()
    g2["params"] = {"think": True}
    assert "think" not in _calistir(_filtre(), g2)  # sohbet ayarı params'ta — dokunulmaz
    g3 = _govde()
    g3["options"] = {"think": True, "temperature": 0.2}  # Open WebUI params'ı buraya taşır
    r = _calistir(_filtre(), g3)
    assert r["options"] == {"think": True, "temperature": 0.2} and "think" not in r


def test_think_ollama_icin_options_a_yazilir():
    g = _calistir(_filtre(), _govde())
    assert g["options"]["think"] is False
    g2 = _govde()
    g2["options"] = {"temperature": 0.2}
    assert _calistir(_filtre(), g2, model=DERIN)["options"] == {"temperature": 0.2, "think": True}


def test_liste_icerikli_mesajdan_metin_alinir():
    c = []
    icerik = [{"type": "image_url", "image_url": {"url": "data:..."}},
              {"type": "text", "text": "bu tablodaki mol sayısı"}]
    _calistir(_filtre(cagrilar=c), _govde(icerik=icerik))
    assert c == [("kimya", "bu tablodaki mol sayısı")]


def test_son_kullanici_mesaji_aranir():
    c = []
    g = {"messages": [{"role": "user", "content": "ilk"}, {"role": "assistant", "content": "cvp"},
                      {"role": "user", "content": "ikinci soru"}]}
    _calistir(_filtre(cagrilar=c), g)
    assert c == [("kimya", "ikinci soru")]


def test_blok_azami_uzunlugu_asmaz():
    uzun = {"durum": "ok", "parcalar": [{"kaynak": f"K{i}", "metin": "x" * 5000} for i in range(4)]}
    assert len(ff.kaynak_blogu(uzun)) <= ff.BLOK_AZAMI_KARAKTER


def test_eszamanli_iki_istek_birbirini_beklemez():
    f = _filtre(gecikme=0.5)

    async def iki():
        t = time.perf_counter()
        await asyncio.gather(f.inlet(_govde(), __model__=KIMYA, __metadata__={}),
                             f.inlet(_govde(), __model__=KIMYA, __metadata__={}))
        return time.perf_counter() - t
    assert asyncio.run(iki()) < 0.9


def test_api_liste_dondururse_govde_degismez():
    g = _calistir(_filtre(["x"]), _govde())
    assert g["messages"] == _govde()["messages"]


def test_bozuk_parcalar_hata_firlatmaz():
    sonuc = {"durum": "ok", "parcalar": [{"kaynak": "K"}, {"metin": None}, "bozuk"]}
    g = _calistir(_filtre(sonuc), _govde())
    assert g["messages"] == _govde()["messages"]
    karisik = {"durum": "ok", "parcalar": ["bozuk", {"kaynak": "K1", "metin": "iyi"}]}
    g = _calistir(_filtre(karisik), _govde())
    assert "[1] K1" in g["messages"][0]["content"]


def test_zayif_notu_takip_mesajini_yanlis_yonlendirmez():
    assert "yeni bir kaynak parçası bulunamadı" in ff.ZAYIF_NOTU
    assert "Önceki cevaplarında" in ff.ZAYIF_NOTU


def test_patolojik_govde_gorevi_bozmaz():
    f = _filtre()
    govde = {"messages": ["metin", {"role": "user", "content": [{"type": "text", "text": None}]}]}
    g = _calistir(f, govde, KIMYA)
    assert g["messages"] == ["metin", {"role": "user", "content": [{"type": "text", "text": None}]}]


def test_ara_proxy_kullanmaz(monkeypatch):
    import urllib.request
    gorulen = {}

    class Yanit:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return b'{"durum": "ok", "parcalar": []}'

    class Acici:
        def open(self, istek, timeout=None):
            gorulen["acici"] = True
            return Yanit()

    def build_opener(*handlers):
        gorulen["handler"] = [type(h).__name__ for h in handlers]
        gorulen["proxies"] = [h.proxies for h in handlers if hasattr(h, "proxies")]
        return Acici()
    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    assert ff.Filter()._ara("kimya", "x") == {"durum": "ok", "parcalar": []}
    assert gorulen["proxies"] == [{}] and gorulen["acici"]
