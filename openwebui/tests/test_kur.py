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


def test_tahta_hesabi_var_ve_yonetici_degil():
    assert ("Farabi Tahta", "tahta@farabi.local", "TAHTA_SIFRE", "Öğretmenler") in kur.HESAPLAR
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
    assert govde["id"] == "farabi_yonetim" and govde["name"] == "Farabi Yönetim"
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


def _main_calistir(monkeypatch, anahtar, capsys):
    cagrilar = []

    class A(SahteApi):
        def __init__(self, *a, **k):
            super().__init__(var=False)
            self.cagrilar = cagrilar

    monkeypatch.setattr(kur, "Api", A)
    monkeypatch.setattr(kur, "env_oku", lambda p: {"OPENWEBUI_API_KEY": "k"})
    monkeypatch.setattr(kur, "gruplari_kur", lambda api: {})
    monkeypatch.setattr(kur, "hesaplari_kur", lambda *a: None)
    monkeypatch.setattr(kur, "filtreyi_kur", lambda *a: None)
    monkeypatch.setattr(kur, "modelleri_kur", lambda *a: ["farabi"])
    monkeypatch.setattr(kur, "ayarlari_kur", lambda *a: None)
    monkeypatch.setattr(kur, "ajan_anahtari_oku", lambda: anahtar)
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
