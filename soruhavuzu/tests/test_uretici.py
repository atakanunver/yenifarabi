import json

from soruhavuzu import uretici

BIRIM = {
    "tur": "kitap",
    "ders": "matematik",
    "sinif": 12,
    "etiket": "Matematik 12, s. 40",
    "metin": "Logaritma üstel fonksiyonun tersidir...",
}
IYI = {
    "konu": "Logaritma",
    "soru": "log2(8) kaçtır?",
    "kisa_cevap": "3",
    "secenekler": ["2", "3", "4", "8"],
    "dogru_index": 1,
    "zorluk": 1,
    "sayfa": 41,
}


def test_gecerli_soru_alinir_ve_kaynak_sayfasi_yazilir():
    s = uretici.ayristir(json.dumps({"sorular": [IYI]}), BIRIM)
    assert len(s) == 1
    assert s[0]["ders"] == "matematik" and s[0]["sinif"] == 12
    assert s[0]["kaynak"] == "Matematik 12, s. 41"


def test_bozuk_ve_sekilli_sorular_elenir():
    kotu = [
        {**IYI, "dogru_index": 7},
        {**IYI, "secenekler": ["a", "b"]},
        {**IYI, "soru": "Şekildeki üçgenin alanı?"},
        {**IYI, "soru": ""},
        {**IYI, "secenekler": ["1", "1", "2", "3"]},
    ]
    assert uretici.ayristir(json.dumps({"sorular": kotu}), BIRIM) == []
    assert uretici.ayristir("json değil", BIRIM) == []


def test_yks_dersi_sorudan_gelir_bilinmeyen_elenir_sayfa_degismez():
    yks = {**BIRIM, "tur": "yks", "ders": None, "etiket": "YKS: AYT_SAY, s. 3"}
    s = uretici.ayristir(
        json.dumps({"sorular": [{**IYI, "ders": "fizik"}, {**IYI, "ders": "beden"}]}),
        yks,
    )
    assert [x["ders"] for x in s] == ["fizik"]
    assert s[0]["kaynak"] == "YKS: AYT_SAY, s. 3"


def test_istem_think_kapali_ve_json():
    yakalanan = {}

    class SahteYanit:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": json.dumps({"sorular": [IYI]})}}

    class SahteIstemci:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, json):
            yakalanan.update(json)
            return SahteYanit()

    eski = uretici.httpx.Client
    uretici.httpx.Client = SahteIstemci
    try:
        assert len(uretici.uret(BIRIM)) == 1
    finally:
        uretici.httpx.Client = eski
    assert yakalanan["think"] is False and yakalanan["format"] == "json"
    assert yakalanan["model"] == "gemma4:12b"
    assert yakalanan["options"]["num_predict"] == 2048


def test_tablo_atifi_elenir_cevap_basi_temizlenir():
    sorular = [{**IYI, "soru": "Tablosunda hangisi var?"}, {**IYI, "kisa_cevap": ": 3"}]
    s = uretici.ayristir(json.dumps({"sorular": sorular}), BIRIM)
    assert [x["kisa_cevap"] for x in s] == ["3"]


def test_500_bir_kez_tekrar_denenir():
    durumlar = [500, 200]
    cagri = []

    class SahteYanit:
        def __init__(self, kod):
            self.status_code = kod

        def raise_for_status(self):
            if self.status_code != 200:
                raise RuntimeError("500")

        def json(self):
            return {"message": {"content": json.dumps({"sorular": [IYI]})}}

    class SahteIstemci:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, json):
            cagri.append(1)
            return SahteYanit(durumlar[len(cagri) - 1])

    eski = uretici.httpx.Client
    uretici.httpx.Client = SahteIstemci
    try:
        assert len(uretici.uret(BIRIM)) == 1
    finally:
        uretici.httpx.Client = eski
    assert len(cagri) == 2


def test_temizlenince_bos_kalan_kisa_cevap_elenir():
    for bos in ("   ", ":", " - ", "."):
        assert uretici.ayristir(json.dumps({"sorular": [{**IYI, "kisa_cevap": bos}]}), BIRIM) == []


def test_uret_kazanim_agy_basarili(monkeypatch):
    sahte_cikti = json.dumps(
        {
            "status": "SUCCESS",
            "structured_output": {
                "sorular": [
                    {
                        "konu": "Türev",
                        "soru": "f(x) = x^2 ise f'(3) kaçtır?",
                        "kisa_cevap": "6",
                        "secenekler": ["3", "5", "6", "9"],
                        "dogru_index": 2,
                        "zorluk": 2,
                        "sayfa": 42,
                    }
                ]
            },
        }
    )

    class SahteSubprocess:
        returncode = 0
        stdout = sahte_cikti

    monkeypatch.setattr(uretici.subprocess, "run", lambda *a, **k: SahteSubprocess())
    monkeypatch.setattr(uretici.Path, "exists", lambda self: True)

    kazanim = {"ders": "matematik", "sinif": 12, "metin": "Türev alma kuralları"}
    kaynak = {"etiket": "Matematik 12, s. 40", "metin": "Türev tanımı..."}

    sorular = uretici.uret_kazanim_agy(kazanim, kaynak)
    assert len(sorular) == 1
    assert sorular[0]["soru"] == "f(x) = x^2 ise f'(3) kaçtır?"
    assert sorular[0]["kisa_cevap"] == "6"
    assert sorular[0]["dogru_index"] == 2
    assert sorular[0]["kaynak"] == "Matematik 12, s. 42"


def test_uret_kazanim_hibrit_ollama_bos_olunca_agyye_duser(monkeypatch):
    kazanim = {"ders": "fizik", "sinif": 11, "metin": "Bağıl hareket"}
    kaynak = {"etiket": "Fizik 11, s. 20", "metin": "Bağıl hız formülü..."}

    # Ollama boş döndürsün
    class SahteYanitBos:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "{\"sorular\": []}"}}

    class SahteIstemci:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, json):
            return SahteYanitBos()

    monkeypatch.setattr(uretici.httpx, "Client", SahteIstemci)
    agy_cagrildi = []
    monkeypatch.setattr(
        uretici,
        "uret_kazanim_agy",
        lambda k, kay, model="gemini-3.8-flash-low": agy_cagrildi.append(1) or [{"soru": "agy sorusu", "ders": "fizik", "sinif": 11, "konu": "hız", "kisa_cevap": "10", "secenekler": ["a", "b", "c", "d"], "dogru_index": 0, "zorluk": 1, "kaynak": "Fizik 11"}],
    )

    sorular = uretici.uret_kazanim(kazanim, kaynak, motor="hibrit")
    assert len(sorular) == 1
    assert len(agy_cagrildi) == 1
    assert sorular[0]["soru"] == "agy sorusu"


def test_uret_kazanim_motor_agy_dogrudan_agy_cagirir(monkeypatch):
    kazanim = {"ders": "kimya", "sinif": 10, "metin": "Mol kavramı"}
    kaynak = {"etiket": "Kimya 10, s. 15", "metin": "Avogadro sayısı..."}

    cagri = []
    monkeypatch.setattr(
        uretici,
        "uret_kazanim_agy",
        lambda k, kay, model="gemini-3.8-flash-low": cagri.append(model) or [{"soru": "mol sorusu"}],
    )

    sorular = uretici.uret_kazanim(kazanim, kaynak, motor="agy", agy_model="gemini-3.8-flash-low")
    assert len(sorular) == 1
    assert cagri == ["gemini-3.8-flash-low"]
