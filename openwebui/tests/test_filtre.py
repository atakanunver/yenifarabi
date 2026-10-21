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


ZAMAN = "Şu an (Türkiye saati): 5 Ekim 2026 Pazartesi, saat 08:20 — 1. ders saati."


def _baglam(g):
    """Son kullanıcı mesajının metni (dinamik <baglam> bloğu burada olur)."""
    return [m for m in g["messages"] if m["role"] == "user"][-1]["content"]


def _yalniz_zaman(g, orijinal):
    """Arama sonucu eklenmediğinde gövdede yalnızca zaman satırı olmalı (son kullanıcı mesajının sonunda)."""
    assert g["messages"][:-1] == orijinal[:-1]
    assert g["messages"][-1] == {"role": "user", "content": orijinal[-1]["content"] + f"\n\n<baglam>\n{ZAMAN}\n</baglam>"}
    return True


def _filtre(sonuc=OK, gecikme=0.0, cagrilar=None):
    f = ff.Filter()
    f._zaman = lambda: ZAMAN

    def _sahte_ara(kapsam, soru):
        if cagrilar is not None:
            cagrilar.append((kapsam, soru))
        time.sleep(gecikme)
        return sonuc
    f._ara = _sahte_ara
    return f


def _calistir(f, govde, model=KIMYA, meta=None):
    return asyncio.run(f.inlet(govde, __model__=model, __metadata__=meta or {}))


def test_ok_sonucu_son_kullanici_mesajinin_sonuna_eklenir():
    g = _calistir(_filtre(), _govde())
    assert [m["role"] for m in g["messages"]] == ["user"]  # sistem mesajı eklenmez
    assert _baglam(g).startswith("mol nedir\n\n<baglam>\n") and _baglam(g).endswith("\n</baglam>")
    assert "[1] Kimya 10, s. 84" in _baglam(g)
    assert "Mol, madde miktarı birimidir." in _baglam(g)


def test_sistem_mesaji_degismez_baglam_kullanici_mesajinda():
    g = _calistir(_filtre(), _govde(sistem="Sen Farabi'sin."))
    assert g["messages"][0] == {"role": "system", "content": "Sen Farabi'sin."}
    assert "Kimya 10, s. 84" in _baglam(g)
    assert len([m for m in g["messages"] if m["role"] == "system"]) == 1


def test_zayif_sonucta_genel_bilgi_notu():
    g = _calistir(_filtre({"durum": "zayif", "parcalar": []}), _govde())
    assert "eşleşen parça gelmedi" in _baglam(g)


def test_hata_sonucunda_mesajlar_degismez():
    g = _calistir(_filtre({"durum": "hata", "parcalar": []}), _govde())
    assert _yalniz_zaman(g, _govde()["messages"])


def test_api_ulasilamazsa_govde_degismez():
    f = ff.Filter()
    f.valves.api_url = "http://127.0.0.1:9/api/webui/ara"   # kapalı port
    f.valves.zaman_asimi_sn = 1.0
    f._zaman = lambda: ZAMAN
    g = _calistir(f, _govde())
    assert _yalniz_zaman(g, _govde()["messages"])


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
    assert c == [("kimya", "ilk ikinci soru")]  # kısa takip → önceki soru eklenir


def test_uzun_mesaj_tek_basina_aranir():
    c = []
    uzun = "mol kavramı ve avogadro sayısı ile ilgili ayrıntılı bir açıklama yapar mısın"
    g = {"messages": [{"role": "user", "content": "ilk"}, {"role": "assistant", "content": "cvp"},
                      {"role": "user", "content": uzun}]}
    _calistir(_filtre(cagrilar=c), g)
    assert c == [("kimya", uzun)]


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
    assert _yalniz_zaman(g, _govde()["messages"])


def test_bozuk_parcalar_hata_firlatmaz():
    sonuc = {"durum": "ok", "parcalar": [{"kaynak": "K"}, {"metin": None}, "bozuk"]}
    g = _calistir(_filtre(sonuc), _govde())
    assert _yalniz_zaman(g, _govde()["messages"])
    karisik = {"durum": "ok", "parcalar": ["bozuk", {"kaynak": "K1", "metin": "iyi"}]}
    g = _calistir(_filtre(karisik), _govde())
    assert "[1] K1" in _baglam(g)


def test_zayif_notu_takip_mesajini_yanlis_yonlendirmez():
    assert "eşleşen parça gelmedi" in ff.ZAYIF_NOTU
    assert "söylemene gerek yok" in ff.ZAYIF_NOTU
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


# --- 2026-10-04: tarih/saat + kaynak önceliği -----------------------------

def test_zaman_satiri_kaynaktan_once_tek_sistem_mesaji():
    g = _calistir(_filtre(), _govde(sistem="Sen Farabi'sin."))
    sistem = [m for m in g["messages"] if m["role"] == "system"]
    assert len(sistem) == 1 and sistem[0]["content"] == "Sen Farabi'sin."
    assert _baglam(g).index(ZAMAN) < _baglam(g).index("Kimya 10, s. 84")


def test_kapsamsiz_modda_da_zaman_eklenir():
    c = []
    g = _calistir(_filtre(cagrilar=c), _govde(), model=ALMANCA)
    assert c == [] and ZAMAN in _baglam(g)


def test_gorev_isteginde_zaman_eklenmez():
    g = _calistir(_filtre(), _govde(), meta={"task": "title_generation"})
    assert g["messages"] == _govde()["messages"]


def test_zaman_api_ulasilamazsa_yerel_saat():
    f = ff.Filter()
    f.valves.okul_url = "http://127.0.0.1:9/api/okul"   # kapalı port
    metin = f._zaman()
    assert metin.startswith("Şu an (Türkiye saati): ") and "saat " in metin
    assert any(g in metin for g in ff.GUNLER) and any(a in metin for a in ff.AYLAR)


def test_yerel_zaman_metni_turkce():
    from datetime import datetime
    an = datetime(2026, 10, 4, 21, 5, tzinfo=ff.ISTANBUL)
    assert ff.yerel_zaman_metni(an) == "Şu an (Türkiye saati): 4 Ekim 2026 Pazar, saat 21:05."


def test_giris_kaynak_onceligi_ve_uydurma_yasagi():
    assert "tek cümleyle belirtip genel bilginle" in ff.GIRIS
    assert "uydurma" in ff.GIRIS.lower()
    assert "önce" in ff.GIRIS.lower()


def test_zaman_hatasi_sohbeti_bozmaz():
    f = _filtre()

    def patla():
        raise RuntimeError("x")
    f._zaman = patla
    g = _calistir(f, _govde())
    assert "Kimya 10, s. 84" in _baglam(g) and ZAMAN not in _baglam(g)


# --- Atos wiki sabit sayfaları (hafızanın yerine, 2026-10-21) ---

HAFIZA_MODEL = {"info": {"meta": {"farabi_kapsam": "genel", "farabi_think": False, "farabi_hafiza": True}}}
WIKI = {"durum": "ok", "sayfalar": [{"ad": "Telefon kuralı", "tarih": "2026-10-16", "metin": "Telefonlar kilitli kutuda tutulur."}]}


def _wikili(sonuc=WIKI, cagrilar=None):
    f = _filtre(sonuc=None)

    def _w():
        if cagrilar is not None:
            cagrilar.append("çağrı")
        return sonuc
    f._wiki_sabit = _w
    return f


def _hal(f, model, rol):
    return asyncio.run(f.inlet(_govde("nöbet ne zaman"), __model__=model, __metadata__={}, __user__={"role": rol}))


def test_wiki_sabit_blogu_admin_ve_wiki_modelinde_eklenir():
    g = _hal(_wikili(), HAFIZA_MODEL, "admin")
    s = _baglam(g)
    assert "Okul wiki'sinin sabit sayfaları" in s and "[Telefon kuralı, 2026-10-16] Telefonlar kilitli kutuda tutulur." in s


def test_wiki_admin_olmayana_ya_da_wikisiz_modele_gitmez():
    cagri = []
    f = _wikili(cagrilar=cagri)
    assert "Okul wiki'sinin" not in _baglam(_hal(f, HAFIZA_MODEL, "user"))
    assert "Okul wiki'sinin" not in _baglam(_hal(f, KIMYA, "admin"))
    assert cagri == []  # sunucuya hiç gidilmedi


def test_wiki_hatasi_sohbeti_bozmaz():
    for bozuk in (None, {"durum": "hata", "sayfalar": []}, {"durum": "ok", "sayfalar": []}, {"durum": "ok", "sayfalar": ["x", {"ad": "a"}]}):
        g = _hal(_wikili(bozuk), HAFIZA_MODEL, "admin")
        assert "Okul wiki'sinin" not in str(g["messages"])
        assert g["messages"][-1]["role"] == "user"


# --- 2026-10-21: bağlam her kullanıcı mesajına bir kez ve aynı metinle bağlı kalır (Ollama önbelleği) ---

def _tur(f, mesajlar, sohbet="c1"):
    return asyncio.run(f.inlet({"messages": mesajlar}, __model__=KIMYA, __metadata__={"chat_id": sohbet}))


def test_onceki_tur_blogu_sonraki_turda_ayni_metinle_geri_gelir():
    ff.BAGLAM_ONBELLEK.clear()
    g1 = _tur(_filtre(), [{"role": "user", "content": "mol nedir"}])
    ilk = _baglam(g1)
    f2 = _filtre()
    f2._zaman = lambda: "Şu an (Türkiye saati): 5 Ekim 2026 Pazartesi, saat 08:21 — 1. ders saati."  # dakika değişti
    g2 = _tur(f2, [{"role": "user", "content": "mol nedir"}, {"role": "assistant", "content": "Madde miktarı."},
                   {"role": "user", "content": "peki avogadro sayısı"}])
    assert g2["messages"][0]["content"] == ilk  # geçmiş, bayt bayt önceki turdaki gibi (önbellek öneki bozulmaz)
    assert g2["messages"][1] == {"role": "assistant", "content": "Madde miktarı."}
    assert "08:21" in g2["messages"][2]["content"] and "08:21" not in g2["messages"][0]["content"]


def test_baglam_sohbetler_arasinda_karismaz():
    ff.BAGLAM_ONBELLEK.clear()
    _tur(_filtre(), [{"role": "user", "content": "mol nedir"}], sohbet="A")
    g = _tur(_filtre(), [{"role": "user", "content": "mol nedir"}, {"role": "assistant", "content": "x"},
                         {"role": "user", "content": "devam"}], sohbet="B")
    assert g["messages"][0]["content"] == "mol nedir"  # B sohbetinin geçmişine A'nın bloğu eklenmez


def test_liste_icerikli_son_mesaja_metin_parcasi_eklenir():
    ff.BAGLAM_ONBELLEK.clear()
    icerik = [{"type": "image_url", "image_url": {"url": "data:..."}}, {"type": "text", "text": "bu tablodaki mol sayısı"}]
    g = _tur(_filtre(), [{"role": "user", "content": icerik}])
    son = g["messages"][0]["content"]
    assert son[-1]["type"] == "text" and son[-1]["text"].startswith("<baglam>") and len(son) == 3


def test_baglam_onbellegi_sinirli():
    ff.BAGLAM_ONBELLEK.clear()
    for i in range(ff.BAGLAM_AZAMI_KAYIT + 5):
        _tur(_filtre(), [{"role": "user", "content": f"soru {i}"}], sohbet=f"s{i}")
    assert len(ff.BAGLAM_ONBELLEK) == ff.BAGLAM_AZAMI_KAYIT
