import kur
import pytest

MOD = {"id": "farabi-kimya", "ad": "Kimya Öğretmeni", "aciklama": "Kimya", "kapsam": "kimya",
       "think": False, "gruplar": ["Öğretmenler", "İdare"], "ek": "kimya.md"}
GRUPLAR = {"Öğretmenler": "g-ogr", "İdare": "g-idr"}


def test_model_govdesi_temel_alanlar():
    g = kur.model_govdesi(MOD, "ÇEKİRDEK", "EK", GRUPLAR)
    assert g["id"] == "farabi-kimya" and g["base_model_id"] == "qwen3.8:27b"
    assert g["name"] == "Kimya Öğretmeni" and g["is_active"] is True
    assert g["params"]["system"] == "ÇEKİRDEK\n\nEK"


def test_think_params_e_KONMAZ_meta_ya_konur():
    g = kur.model_govdesi(MOD, "c", "e", GRUPLAR)
    assert "think" not in g["params"]
    assert g["meta"]["farabi_think"] is False and g["meta"]["farabi_kapsam"] == "kimya"


def test_filtre_bagli():
    assert kur.model_govdesi(MOD, "c", "e", GRUPLAR)["meta"]["filterIds"] == ["farabi_kaynak"]


def test_grup_erisimi():
    g = kur.model_govdesi({**MOD, "gruplar": ["İdare"]}, "c", "e", GRUPLAR)
    assert g["access_grants"] == [{"principal_type": "group", "principal_id": "g-idr", "permission": "read"}]


def test_env_okuma(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# yorum\nOPENWEBUI_API_KEY=abc\nOGRETMEN_SIFRE='x y'\n\n", encoding="utf-8")
    assert kur.env_oku(p) == {"OPENWEBUI_API_KEY": "abc", "OGRETMEN_SIFRE": "x y"}


def test_ham_model_gruplara_okuma_izni_ve_gizli():
    g = kur.ham_model_govdesi(GRUPLAR)
    assert g["id"] == "qwen3.8:27b" and g["base_model_id"] is None
    assert g["meta"]["hidden"] is True
    assert g["access_grants"] == [
        {"principal_type": "group", "principal_id": "g-ogr", "permission": "read"},
        {"principal_type": "group", "principal_id": "g-idr", "permission": "read"}]


def test_ortak_ogretmen_ve_tahta_hesabi_acilmaz_kapatilir():
    # 2026-10-05: Atos yalnızca idari kadro için — ortak hesaplar oluşturulmaz, kapatılır
    epostalar = [h[1] for h in kur.HESAPLAR]
    assert "tahta@farabi.local" not in epostalar and "ogretmen@farabi.local" not in epostalar
    assert set(kur.KAPALI_HESAPLAR) == {"tahta@farabi.local", "ogretmen@farabi.local", "idare@farabi.local"}
    assert kur.HESAPLAR == []
    import inspect
    assert '"role": "user"' in inspect.getsource(kur.hesaplari_kur)
    assert "admin" not in inspect.getsource(kur.hesaplari_kur).split("mevcut_ogretmenler(env)")[0]


def test_gorev_modeli_gizli_think_kapali_filtresiz():
    g = kur.gorev_model_govdesi(GRUPLAR)
    assert g["id"] == "farabi-gorev" and g["base_model_id"] == "qwen3.8:27b"
    assert g["name"] == "Farabi (görev)" and g["params"] == {"think": False}
    assert g["meta"]["hidden"] is True and "filterIds" not in g["meta"]
    assert [a["principal_id"] for a in g["access_grants"]] == ["g-ogr", "g-idr"]
    assert all(a["permission"] == "read" for a in g["access_grants"])


def test_gorev_modeli_modlar_json_da_degil():
    import json
    modlar = json.loads((kur.KOK / "modlar.json").read_text(encoding="utf-8"))
    assert kur.GOREV_MODEL_ID not in [m["id"] for m in modlar]


def test_task_model_gorev_modeli():
    cagrilar = []

    def api(yontem, yol, govde=None, yazma=True):
        cagrilar.append((yontem, yol, govde))
        return {}
    kur.ayarlari_kur(api, ["farabi"])
    govde = next(c[2] for c in cagrilar if c[1] == "/api/v1/tasks/config/update")
    assert govde["TASK_MODEL"] == "farabi-gorev"


def test_mevcut_ogretmenler_env_den():
    assert kur.mevcut_ogretmenler({}) == []
    assert kur.mevcut_ogretmenler({"MEVCUT_OGRETMENLER": ""}) == []
    assert kur.mevcut_ogretmenler({"MEVCUT_OGRETMENLER": "Aa, Bb ,"}) == ["Aa", "Bb"]


# --- Farabi Yönetim (admin-only araç + gizli model) ---

class SahteApi:
    def __init__(self, var=True):
        self.cagrilar, self.var = [], var

    def __call__(self, yontem, yol, govde=None, yazma=True):
        self.cagrilar.append((yontem, yol, govde))
        if yol == "/api/v1/auths/":
            return {"id": "admin"}
        if yontem == "GET":
            return {"id": "x"} if self.var else None
        return {}


def test_yonetim_modeli():
    g = kur.yonetim_model_govdesi()
    assert g["id"] == "farabi-yonetim" and g["base_model_id"] == "qwen3.8:27b"
    assert g["access_grants"] == [] and g["is_active"] is True
    assert g["meta"]["toolIds"] == ["farabi_yonetim"] and "filterIds" not in g["meta"]
    assert g["params"]["function_calling"] == "native" and g["params"]["think"] is False
    assert g["params"]["system"] == (kur.KOK / "promptlar" / "yonetim.md").read_text(encoding="utf-8")
    assert "UYDURMA" in g["params"]["system"]
    assert g["meta"]["capabilities"]["builtin_tools"] is False
    assert g["meta"]["builtinTools"] and not any(g["meta"]["builtinTools"].values())
    assert not g["meta"].get("hidden")  # admin model seçicide görebilmeli


def test_yonetim_modeli_modlar_json_ve_siralamada_degil():
    import json
    modlar = json.loads((kur.KOK / "modlar.json").read_text(encoding="utf-8"))
    assert "farabi-yonetim" not in [m["id"] for m in modlar]


@pytest.mark.parametrize("var", [True, False])
def test_araci_kur(var):
    api = SahteApi(var)
    kur.araci_kur(api, "AJAN-ANAHTARI")
    posts = [(y, g) for m, y, g in api.cagrilar if m == "POST"]
    assert api.cagrilar[0] == ("GET", "/api/v1/tools/id/farabi_yonetim", None)
    yol, govde = posts[0]
    assert yol == ("/api/v1/tools/id/farabi_yonetim/update" if var else "/api/v1/tools/create")
    assert govde["id"] == "farabi_yonetim" and govde["name"] == "Atos Yönetim"
    assert govde["access_grants"] == [] and "description" in govde["meta"]
    assert govde["content"] == (kur.KOK / "farabi_yonetim_araci.py").read_text(encoding="utf-8")
    assert posts[1] == ("/api/v1/tools/id/farabi_yonetim/access/update", {"access_grants": []})
    assert posts[2] == ("/api/v1/tools/id/farabi_yonetim/valves/update",
                        {"api_url": "http://127.0.0.1:8010/api/ajan", "api_key": "AJAN-ANAHTARI",
                         "zaman_asimi_sn": 60.0})


def test_ajan_anahtari_oku(tmp_path, monkeypatch):
    monkeypatch.setattr(kur, "KOK", tmp_path / "openwebui")
    assert kur.ajan_anahtari_oku() is None
    p = tmp_path / "tahtayoklama/dashboard/config"
    p.mkdir(parents=True)
    (p / "ajan.json").write_text('{"anahtar": "abc"}', encoding="utf-8")
    assert kur.ajan_anahtari_oku() == "abc"


def _main_calistir(monkeypatch, anahtar, capsys, ek=None):
    cagrilar = []

    class A(SahteApi):
        def __init__(self, *a, **k):
            super().__init__(var=False)
            self.cagrilar = cagrilar

    monkeypatch.setattr(kur, "Api", A)
    monkeypatch.setattr(kur, "env_oku", lambda p: {"OPENWEBUI_API_KEY": "k"})
    monkeypatch.setattr(kur, "gruplari_kur", lambda api: {})
    monkeypatch.setattr(kur, "hesaplari_kur", lambda *a: None)
    monkeypatch.setattr(kur, "hesaplari_kapat", lambda *a: None)
    monkeypatch.setattr(kur, "belge_araci_kur", lambda *a: None)
    monkeypatch.setattr(kur, "sms_araci_kur", lambda *a: False)
    monkeypatch.setattr(kur, "filtreyi_kur", lambda *a: None)
    monkeypatch.setattr(kur, "modelleri_kur", lambda *a: ["farabi"])
    monkeypatch.setattr(kur, "ayarlari_kur", lambda *a: None)
    monkeypatch.setattr(kur, "ajan_anahtari_oku", lambda: anahtar)
    monkeypatch.setattr(kur, "kimlik_ayarlarini_kur", lambda api: None)
    if ek:
        ek()
    monkeypatch.setattr(kur.json, "loads", lambda s: {"webui_key": "w"})
    monkeypatch.setattr(kur.Path, "read_text", lambda self, **k: "{}")
    monkeypatch.setattr(kur.sys, "argv", ["kur.py"])
    assert kur.main() == 0
    return cagrilar, capsys.readouterr().out


def test_main_ajan_json_yoksa_atlar(monkeypatch, capsys):
    cagrilar, cikti = _main_calistir(monkeypatch, None, capsys)
    assert not [c for c in cagrilar if "farabi_yonetim" in c[1] or c[1].startswith("/api/v1/models")]
    assert "ajan.json yok" in cikti and "atlandı" in cikti


def test_main_ajan_json_varsa_kurar(monkeypatch, capsys):
    cagrilar, _ = _main_calistir(monkeypatch, "anahtar", capsys)
    yollar = [c[1] for c in cagrilar]
    assert "/api/v1/tools/create" in yollar and "/api/v1/models/create" in yollar
    model = next(c[2] for c in cagrilar if c[1] == "/api/v1/models/create")
    assert model["id"] == "farabi-yonetim"


# --- Kimlik ayarları (C1) ve sıralama ---

ADMIN_CFG = {"SHOW_ADMIN_DETAILS": True, "WEBUI_URL": "http://x", "ENABLE_SIGNUP": True,
             "DEFAULT_USER_ROLE": "admin", "JWT_EXPIRES_IN": "4w", "ENABLE_FOLDERS": True}


class CfgApi:
    def __init__(self, cfg):
        self.cfg, self.cagrilar = cfg, []

    def __call__(self, yontem, yol, govde=None, yazma=True):
        self.cagrilar.append((yontem, yol, govde))
        return self.cfg if yontem == "GET" else {}


def test_kimlik_ayarlari_yalniz_iki_alan_degisir():
    api = CfgApi(dict(ADMIN_CFG))
    kur.kimlik_ayarlarini_kur(api)
    posts = [c for c in api.cagrilar if c[0] == "POST"]
    assert len(posts) == 1 and posts[0][1] == "/api/v1/auths/admin/config"
    beklenen = dict(ADMIN_CFG, ENABLE_SIGNUP=False, DEFAULT_USER_ROLE="user")
    assert posts[0][2] == beklenen


def test_kimlik_ayarlari_okunamazsa_durur():
    with pytest.raises(SystemExit):
        kur.kimlik_ayarlarini_kur(CfgApi(None))


def test_main_kimlik_hesaplardan_once(monkeypatch, capsys):
    sira = []

    def ek():
        monkeypatch.setattr(kur, "kimlik_ayarlarini_kur", lambda api: sira.append("kimlik"))
        monkeypatch.setattr(kur, "hesaplari_kur", lambda *a: sira.append("hesap"))
        monkeypatch.setattr(kur, "ayarlari_kur", lambda *a: sira.append("ayar"))
        monkeypatch.setattr(kur, "yonetimi_kur", lambda *a: sira.append("yonetim"))
    _main_calistir(monkeypatch, "anahtar", capsys, ek)
    assert sira == ["kimlik", "hesap", "ayar", "yonetim"]


@pytest.mark.parametrize("icerik", ["{bozuk", "{}", '{"anahtar": ""}', "[]", '{"anahtar": 5}'])
def test_ajan_anahtari_bozuksa_none(tmp_path, monkeypatch, icerik):
    monkeypatch.setattr(kur, "KOK", tmp_path / "openwebui")
    p = tmp_path / "tahtayoklama/dashboard/config"
    p.mkdir(parents=True)
    (p / "ajan.json").write_text(icerik, encoding="utf-8")
    assert kur.ajan_anahtari_oku() is None


def test_yonetimi_kur_bozuk_ajan_json_cokmez(monkeypatch, capsys):
    monkeypatch.setattr(kur, "ajan_anahtari_oku", lambda: None)
    api = SahteApi()
    kur.yonetimi_kur(api)
    assert api.cagrilar == [] and "atlandı" in capsys.readouterr().out


# --- 2026-10-04: Okul Bilgisi aracı ---

def test_model_aracsiz_eskisi_gibi():
    g = kur.model_govdesi(MOD, "c", "e", GRUPLAR)
    assert "toolIds" not in g["meta"] and "function_calling" not in g["params"]


def test_model_okul_araciyla_native_ve_yerlesik_araclar_kapali():
    g = kur.model_govdesi(MOD, "c", "e", GRUPLAR, arac_idleri=[kur.OKUL_ARAC_ID])
    assert g["meta"]["toolIds"] == ["farabi_okul"]
    assert g["params"]["function_calling"] == "native"
    assert g["meta"]["capabilities"]["builtin_tools"] is False
    assert not any(g["meta"]["builtinTools"].values())
    assert g["meta"]["filterIds"] == ["farabi_kaynak"]


def test_okul_ayari_oku(tmp_path, monkeypatch):
    monkeypatch.setattr(kur, "KOK", tmp_path / "openwebui")
    assert kur.okul_ayari_oku() is None
    p = tmp_path / "tahtayoklama/dashboard/config"
    p.mkdir(parents=True)
    (p / "okul.json").write_text('{"anahtar": "k", "ogrenci_izinli": ["a@b"]}', encoding="utf-8")
    assert kur.okul_ayari_oku() == {"anahtar": "k", "ogrenci_izinli": ["a@b"]}
    (p / "okul.json").write_text('{"anahtar": ""}', encoding="utf-8")
    assert kur.okul_ayari_oku() is None


@pytest.mark.parametrize("var", [True, False])
def test_okul_araci_kur(var):
    api = SahteApi(var)
    kur.okul_araci_kur(api, {"anahtar": "OKUL", "ogrenci_izinli": ["idare@farabi.local", "x@y"]}, GRUPLAR)
    posts = [(y, g) for m, y, g in api.cagrilar if m == "POST"]
    yol, govde = posts[0]
    assert yol == ("/api/v1/tools/id/farabi_okul/update" if var else "/api/v1/tools/create")
    assert govde["content"] == (kur.KOK / "farabi_okul_araci.py").read_text(encoding="utf-8")
    erisim = dict(posts)["/api/v1/tools/id/farabi_okul/access/update"]["access_grants"]
    assert sorted(a["principal_id"] for a in erisim) == ["g-idr", "g-ogr"]
    assert dict(posts)["/api/v1/tools/id/farabi_okul/valves/update"] == {
        "api_url": "http://127.0.0.1:8010/api/okul", "api_key": "OKUL",
        "ogrenci_izinli": "idare@farabi.local,x@y", "zaman_asimi_sn": 15.0}


def test_tahta_hesabi_izinli_listeye_girmez():
    liste = kur.ogrenci_izinli_liste(["idare@farabi.local", "tahta@farabi.local"], ["k@okul"])
    assert "tahta@farabi.local" not in liste and liste == ["idare@farabi.local", "k@okul"]


def test_filtre_okul_valfleri():
    api = SahteApi(True)
    kur.filtreyi_kur(api, "WEBUI", {"anahtar": "OKUL"})
    valf = next(g for m, y, g in api.cagrilar if y.endswith("/valves/update"))
    assert valf["okul_key"] == "OKUL" and valf["okul_url"] == "http://127.0.0.1:8010/api/okul"
    assert valf["api_key"] == "WEBUI"


def test_filtre_okul_ayari_yoksa_bos_anahtar():
    api = SahteApi(True)
    kur.filtreyi_kur(api, "WEBUI", None)
    valf = next(g for m, y, g in api.cagrilar if y.endswith("/valves/update"))
    assert valf["okul_key"] == ""


class KayitApi:
    def __init__(self, kullanicilar=(), var=None):
        self.kullanicilar, self.var, self.cagrilar = list(kullanicilar), var, []

    def __call__(self, yontem, yol, govde=None, yazma=True):
        self.cagrilar.append((yontem, yol, govde))
        if yol.startswith("/api/v1/users/search") or yol.startswith("/api/v1/users/?"):
            return {"users": self.kullanicilar}
        return self.var if yontem == "GET" else {}


def test_hesaplari_kapat_pending_yapar_aciklari_atlar(monkeypatch):
    kullanicilar = [{"id": "t", "email": "tahta@farabi.local", "name": "Farabi Tahta", "role": "user"},
                    {"id": "o", "email": "ogretmen@farabi.local", "name": "Öğretmen", "role": "pending"}]
    monkeypatch.setattr(kur, "kullanici_bul", lambda api, s: [u for u in kullanicilar if u["email"] == s])
    api = KayitApi()
    kur.hesaplari_kapat(api)
    posts = [c for c in api.cagrilar if c[0] == "POST"]
    assert [p[1] for p in posts] == ["/api/v1/users/t/update"] and posts[0][2]["role"] == "pending"


def test_belge_araci_yalniz_idareye_acik():
    api = KayitApi(var=None)
    kur.belge_araci_kur(api, "w", {"Öğretmenler": "g-ogr", "İdare": "g-idr"})
    erisim = next(c[2] for c in api.cagrilar if c[1].endswith("/access/update"))
    assert erisim == {"access_grants": [{"principal_type": "group", "principal_id": "g-idr",
                                         "permission": "read"}]}
    valf = next(c[2] for c in api.cagrilar if c[1].endswith("/valves/update"))
    assert valf["api_key"] == "w" and valf["api_url"].endswith("/api/webui/belge-kaydet")


def test_yonetici_epostalari_envden():
    # 2026-10-06: kişisel e-postalar koddan .env'e taşındı.
    assert kur.yonetici_epostalari({"YONETICI_EPOSTALAR": " a@x.com, ,b@y.com "}) == ["a@x.com", "b@y.com"]
    assert kur.yonetici_epostalari({}) == []
