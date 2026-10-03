#!/usr/bin/env python3
"""openwebui/kur.py — Farabi modlarını Open WebUI'ye kurar (tekrar çalıştırılabilir).

Tasarım: docs/superpowers/specs/2026-10-03-openwebui-farabi-modlar-design.md §3.6, §6.
Yalnızca Open WebUI'nin resmi HTTP API'si kullanılır (DB'ye doğrudan yazılmaz,
token üretilmez). Kimlik bilgileri openwebui/.env'den (gitignore'lu):
    OPENWEBUI_URL=http://127.0.0.1:80
    OPENWEBUI_API_KEY=...        # yönetici API anahtarı
    OGRETMEN_SIFRE=...           # ortak Öğretmen hesabı
    IDARE_SIFRE=...              # ortak İdare hesabı
farabi-api anahtarı server/config/api_keys.json::webui_key'den okunur.

Kullanım:  server/venv/bin/python openwebui/kur.py [--kuru]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent
TABAN_MODEL = "qwen3.8:27b"
FILTRE_ID = "farabi_kaynak"
GRUPLAR = {"Öğretmenler": "Okulun öğretmenleri (ortak hesap)", "İdare": "Okul idaresi"}
HESAPLAR = [  # (ad, e-posta, .env anahtarı, grup)
    ("Öğretmen", "ogretmen@farabi.local", "OGRETMEN_SIFRE", "Öğretmenler"),
    ("İdare", "idare@farabi.local", "IDARE_SIFRE", "İdare"),
    ("Farabi Tahta", "tahta@farabi.local", "TAHTA_SIFRE", "Öğretmenler"),  # akıllı tahtalar için ortak hesap
]
GOREV_MODEL_ID = "farabi-gorev"  # yalnızca arka plan görevleri (başlık) için, düşünme kapalı
ARAC_ID = "farabi_yonetim"  # yalnızca admin: tahta yönetimi aracı (Tool)
YONETIM_MODEL_ID = "farabi-yonetim"
# Open WebUI utils/tools.py get_builtin_tools: meta.builtinTools[kategori] (varsayılan True).
BUILTIN_KATEGORILER = ("time", "memory", "chats", "notes", "knowledge", "channels", "web_search",
                       "image_generation", "code_interpreter", "files", "tasks", "automations",
                       "calendar", "notifications", "subagents")


def env_oku(yol: Path) -> dict[str, str]:
    sonuc = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        k, v = satir.split("=", 1)
        sonuc[k.strip()] = v.strip().strip("'\"")
    return sonuc


def mevcut_ogretmenler(env: dict) -> list[str]:
    """Önceden açılmış kişisel hesap adları (.env: MEVCUT_OGRETMENLER, virgüllü; yoksa [])."""
    return [a.strip() for a in env.get("MEVCUT_OGRETMENLER", "").split(",") if a.strip()]


def model_govdesi(mod: dict, cekirdek: str, ek: str, grup_idleri: dict[str, str]) -> dict:
    return {
        "id": mod["id"],
        "base_model_id": TABAN_MODEL,
        "name": mod["ad"],
        "meta": {
            "description": mod["aciklama"],
            "filterIds": [FILTRE_ID],
            "farabi_kapsam": mod["kapsam"],
            "farabi_think": bool(mod["think"]),
        },
        # think BURAYA KONMAZ: Open WebUI model parametrelerini sohbet
        # ayarlarının üzerine yazar; varsayılanı filtre (farabi_think) verir.
        "params": {"system": f"{cekirdek.strip()}\n\n{ek.strip()}"},
        "access_grants": [{"principal_type": "group", "principal_id": grup_idleri[g],
                           "permission": "read"} for g in mod["gruplar"]],
        "is_active": True,
    }


def ham_model_govdesi(grup_idleri: dict[str, str]) -> dict:
    """Ham taban model. Bu Open WebUI sürümü base_model_id zincirinde her halkada
    okuma izni arar; izinsiz ham model, türetilmiş tüm modları öğretmene kapatır.
    Bu yüzden iki gruba okuma izni verilir, seçiciden meta.hidden ile gizlenir."""
    return {"id": TABAN_MODEL, "base_model_id": None, "name": TABAN_MODEL,
            "meta": {"description": "Ham model — model seçicide gizli.", "hidden": True},
            "params": {},
            "access_grants": [{"principal_type": "group", "principal_id": grup_idleri[g],
                               "permission": "read"} for g in GRUPLAR],
            "is_active": True}


def gorev_model_govdesi(grup_idleri: dict[str, str]) -> dict:
    """Gizli, yalnızca görev modeli. Open WebUI görev yolunda (başlık üretimi) hiçbir
    Function inlet'i çalışmaz; Ollama varsayılan düşünmesi (medium) başlığı yavaşlatır.
    Model params["think"] False, routers/ollama.py'de payload köküne taşınır."""
    return {"id": GOREV_MODEL_ID, "base_model_id": TABAN_MODEL, "name": "Farabi (görev)",
            "meta": {"description": "Arka plan görevleri (başlık) — düşünme kapalı.", "hidden": True},
            "params": {"think": False},
            "access_grants": [{"principal_type": "group", "principal_id": grup_idleri[g],
                               "permission": "read"} for g in GRUPLAR],
            "is_active": True}


def yonetim_model_govdesi() -> dict:
    """Gizli, yalnızca admin modeli (access_grants boş: yalnızca sahip/admin görür) — Farabi Yönetim
    aracını kullanır. Çekirdek (öğretmen) prompt'u eklenmez, filtre yok. Open WebUI yerleşik araçları
    kapalı: meta.capabilities.builtin_tools False (middleware.py use_builtin_tools kapısı) ve ayrıca
    meta.builtinTools[kategori] False (utils/tools.py get_builtin_tools). params["think"] False,
    routers/ollama.py'de payload köküne taşınır (gorev_model_govdesi ile aynı gerekçe)."""
    return {"id": YONETIM_MODEL_ID, "base_model_id": TABAN_MODEL, "name": "Farabi Yönetim",
            "meta": {"description": "Yalnızca yönetici: tahta durumu, uzaktan eylem, yeniden başlatma, yoklama sorgusu.",
                     "hidden": True, "toolIds": [ARAC_ID],
                     "capabilities": {"builtin_tools": False},
                     "builtinTools": {k: False for k in BUILTIN_KATEGORILER}},
            "params": {"system": (KOK / "promptlar" / "yonetim.md").read_text(encoding="utf-8"),
                       "function_calling": "native", "think": False},
            "access_grants": [], "is_active": True}


class Api:
    def __init__(self, url: str, anahtar: str, kuru: bool):
        self.url, self.anahtar, self.kuru = url.rstrip("/"), anahtar, kuru

    def __call__(self, yontem: str, yol: str, govde=None, yazma=True):
        if self.kuru and yazma and yontem != "GET":
            print(f"[kuru] {yontem} {yol}")
            return {}
        istek = urllib.request.Request(
            self.url + yol, method=yontem,
            data=None if govde is None else json.dumps(govde, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.anahtar}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=60) as r:
                veri = r.read()
                return json.loads(veri) if veri else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 404) and yontem == "GET":
                return None
            raise SystemExit(f"{yontem} {yol} → {e.code}: {e.read()[:300]!r}")


def gruplari_kur(api: Api) -> dict[str, str]:
    mevcut = {g["name"]: g["id"] for g in (api("GET", "/api/v1/groups/") or [])}
    for ad, aciklama in GRUPLAR.items():
        if ad not in mevcut:
            g = api("POST", "/api/v1/groups/create", {"name": ad, "description": aciklama})
            mevcut[ad] = (g or {}).get("id", f"<kuru:{ad}>")
            print(f"grup oluşturuldu: {ad}")
    return mevcut


def kullanici_bul(api: Api, sorgu: str) -> list[dict]:
    y = api("GET", "/api/v1/users/?" + urllib.parse.urlencode({"query": sorgu})) or {}
    return y.get("users", []) if isinstance(y, dict) else []


def hesaplari_kur(api: Api, env: dict, grup_idleri: dict[str, str]) -> None:
    for ad, eposta, env_anahtar, grup in HESAPLAR:
        bulunan = [u for u in kullanici_bul(api, eposta) if u.get("email") == eposta]
        if bulunan:
            uid = bulunan[0]["id"]
        else:
            u = api("POST", "/api/v1/auths/add",
                    {"name": ad, "email": eposta, "password": env[env_anahtar], "role": "user"})
            uid = (u or {}).get("id", f"<kuru:{eposta}>")
            print(f"hesap oluşturuldu: {eposta}")
        api("POST", f"/api/v1/groups/id/{grup_idleri[grup]}/users/add", {"user_ids": [uid]})
    for ad in mevcut_ogretmenler(env):
        for u in kullanici_bul(api, ad):
            if u.get("name") == ad and u.get("role") != "admin":
                api("POST", f"/api/v1/groups/id/{grup_idleri['Öğretmenler']}/users/add",
                    {"user_ids": [u["id"]]})
                print(f"mevcut hesap Öğretmenler'e eklendi: {ad}")


def filtreyi_kur(api: Api, webui_key: str) -> None:
    icerik = (KOK / "farabi_filtre.py").read_text(encoding="utf-8")
    govde = {"id": FILTRE_ID, "name": "Farabi Kaynak Arama", "content": icerik,
             "meta": {"description": "Farabi modları için kitap/mevzuat parçası ekler."}}
    var = api("GET", f"/api/v1/functions/id/{FILTRE_ID}")
    api("POST", f"/api/v1/functions/id/{FILTRE_ID}/update" if var else "/api/v1/functions/create", govde)
    simdi = api("GET", f"/api/v1/functions/id/{FILTRE_ID}") or {}
    if simdi and not simdi.get("is_active"):
        api("POST", f"/api/v1/functions/id/{FILTRE_ID}/toggle")
    api("POST", f"/api/v1/functions/id/{FILTRE_ID}/valves/update",
        {"api_url": "http://127.0.0.1:8000/api/webui/ara", "api_key": webui_key, "zaman_asimi_sn": 8.0})
    print("filtre kuruldu: farabi_kaynak")


def ajan_anahtari_oku() -> str | None:
    """Dashboard'un /api/ajan anahtarı (gitignore'lu); dosya yoksa None."""
    yol = KOK.parent / "tahtayoklama/dashboard/config/ajan.json"
    if not yol.exists():
        return None
    return json.loads(yol.read_text(encoding="utf-8"))["anahtar"]


def araci_kur(api: Api, ajan_key: str) -> None:
    icerik = (KOK / "farabi_yonetim_araci.py").read_text(encoding="utf-8")
    govde = {"id": ARAC_ID, "name": "Farabi Yönetim", "content": icerik,
             "meta": {"description": "Yalnızca yönetici: tahta durumu, uzaktan eylem, yeniden başlatma (onaylı)."},
             "access_grants": []}
    var = api("GET", f"/api/v1/tools/id/{ARAC_ID}")
    api("POST", f"/api/v1/tools/id/{ARAC_ID}/update" if var else "/api/v1/tools/create", govde)
    api("POST", f"/api/v1/tools/id/{ARAC_ID}/access/update", {"access_grants": []})  # yalnızca admin
    api("POST", f"/api/v1/tools/id/{ARAC_ID}/valves/update",
        {"api_url": "http://127.0.0.1:8010/api/ajan", "api_key": ajan_key, "zaman_asimi_sn": 60.0})
    print(f"araç kuruldu: {ARAC_ID}")


def model_yaz(api: Api, govde: dict) -> bool:
    var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": govde["id"]}))
    api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", govde)
    return bool(var)


def yonetimi_kur(api: Api) -> None:
    ajan_key = ajan_anahtari_oku()
    if ajan_key is None:
        print("uyarı: ajan.json yok, Farabi Yönetim atlandı "
              "(önce tahtayoklama/dashboard/scripts/ajan_anahtari_olustur.py)")
        return
    araci_kur(api, ajan_key)
    guncellendi = model_yaz(api, yonetim_model_govdesi())
    print(f"model {'güncellendi' if guncellendi else 'oluşturuldu'}: Farabi Yönetim")


def modelleri_kur(api: Api, grup_idleri: dict[str, str]) -> list[str]:
    cekirdek = (KOK / "promptlar" / "cekirdek.md").read_text(encoding="utf-8")
    modlar = json.loads((KOK / "modlar.json").read_text(encoding="utf-8"))
    for mod in modlar:
        ek = (KOK / "promptlar" / mod["ek"]).read_text(encoding="utf-8")
        govde = model_govdesi(mod, cekirdek, ek, grup_idleri)
        var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": mod["id"]}))
        api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", govde)
        print(f"model {'güncellendi' if var else 'oluşturuldu'}: {mod['ad']}")
    ham = ham_model_govdesi(grup_idleri)
    var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": TABAN_MODEL}))
    api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", ham)
    gorev = gorev_model_govdesi(grup_idleri)
    var = api("GET", "/api/v1/models/model?" + urllib.parse.urlencode({"id": GOREV_MODEL_ID}))
    api("POST", "/api/v1/models/model/update" if var else "/api/v1/models/create", gorev)
    return [m["id"] for m in modlar]


def ayarlari_kur(api: Api, mod_idleri: list[str]) -> None:
    cfg = api("GET", "/api/v1/configs/models") or {}
    cfg.update({"DEFAULT_MODELS": "farabi", "MODEL_ORDER_LIST": mod_idleri})
    api("POST", "/api/v1/configs/models", cfg)
    gorev = api("GET", "/api/v1/tasks/config") or {}
    gorev.update({"TASK_MODEL": GOREV_MODEL_ID, "ENABLE_TAGS_GENERATION": False,
                  "ENABLE_FOLLOW_UP_GENERATION": False})
    api("POST", "/api/v1/tasks/config/update", gorev)
    print("ayarlar: varsayılan model farabi, etiket/takip üretimi kapalı, görev modeli farabi-gorev")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="yalnızca okur, yazacaklarını listeler")
    a = ap.parse_args()
    env = env_oku(KOK / ".env")
    webui_key = json.loads((KOK.parent / "server/config/api_keys.json").read_text(encoding="utf-8"))["webui_key"]
    api = Api(env.get("OPENWEBUI_URL", "http://127.0.0.1:80"), env["OPENWEBUI_API_KEY"], a.kuru)
    if api("GET", "/api/v1/auths/", yazma=False) is None:
        raise SystemExit("API anahtarı geçersiz ya da API anahtarları kapalı.")
    grup_idleri = gruplari_kur(api)
    hesaplari_kur(api, env, grup_idleri)
    filtreyi_kur(api, webui_key)
    mod_idleri = modelleri_kur(api, grup_idleri)
    yonetimi_kur(api)
    ayarlari_kur(api, mod_idleri)
    print("tamam")
    return 0


if __name__ == "__main__":
    sys.exit(main())
