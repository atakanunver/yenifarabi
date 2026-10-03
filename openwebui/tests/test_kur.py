import kur

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
