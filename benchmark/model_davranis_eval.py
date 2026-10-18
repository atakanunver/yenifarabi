#!/usr/bin/env python3
"""Model DAVRANIS degerlendirmesi: arac secimi, uydurmama, yaptim-deme.

Retrieval olcen eval_rag.py'den bagimsiz. Araclar ASLA calistirilmaz; yalnizca
modelin dondurdugu tool_calls kaydedilir. Puanlama kural tabanli (LLM-hakem yok).
Arac semalari Open WebUI veritabanindan SALT-OKUNUR okunur.

Kullanim:
  python3 benchmark/model_davranis_eval.py --kuru
  python3 benchmark/model_davranis_eval.py --out reports/davranis_<zaman>.json
  python3 benchmark/model_davranis_eval.py --karsilastir a.json b.json
"""
import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

AD = Path(__file__).resolve().parent
KOK = AD.parent
VARSAYILAN_SET = AD / "model_davranis_set.json"
VARSAYILAN_DB = "/opt/open-webui/data/webui.db"
SISTEM_ISTEMI = KOK / "openwebui" / "promptlar" / "cekirdek.md"
OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3.8:27b"
SAAT_SATIRI = "Şu an (Türkiye saati): Cumartesi, 17 Ekim 2026, 19:00"
KATEGORILER = ("arac", "uydurma", "yaptim", "dil")


def araclari_yukle(db_yolu):
    """tool.specs -> Ollama/OpenAI 'tools' listesi (salt-okunur)."""
    con = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True)
    try:
        satirlar = con.execute("select id, specs from tool order by id").fetchall()
    finally:
        con.close()
    araclar, adlar = [], set()
    for _id, specs in satirlar:
        for s in json.loads(specs or "[]"):
            par = dict(s.get("parameters") or {})
            par.setdefault("type", "object")
            par.setdefault("properties", {})
            araclar.append({"type": "function", "function": {
                "name": s["name"], "description": s.get("description", ""), "parameters": par}})
            adlar.add(s["name"])
    return araclar, adlar


def seti_yukle(yol):
    d = json.loads(Path(yol).read_text(encoding="utf-8"))
    return d["senaryolar"] if isinstance(d, dict) else d


def sistem_mesaji(sen, taban):
    m = taban.rstrip() + "\n\n" + SAAT_SATIRI
    if sen.get("bağlam") or sen.get("baglam"):
        m += "\n\n# Kaynak parçaları\n" + (sen.get("bağlam") or sen.get("baglam"))
    return m


def liste(x):
    return [] if x is None else ([x] if isinstance(x, str) else list(x))


def cagrilari_ayir(tool_calls):
    out = []
    for tc in tool_calls or []:
        f = tc.get("function", {})
        a = f.get("arguments", {})
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except ValueError:
                a = {"_ham": a}
        out.append({"ad": f.get("name"), "arg": a})
    return out


def puanla(sen, icerik, cagrilar):
    """-> (gecti, nedenler[]). Saf mantik; --kuru self-test bunu dener."""
    ned = []
    ad_ler = [c["ad"] for c in cagrilar]
    bek = liste(sen.get("beklenen_arac"))
    izin = set(liste(sen.get("izinli_arac")))
    icerik = icerik or ""
    on = set(liste(sen.get("onadim_arac")))
    bek_cagrildi = bool(bek) and any(a in bek for a in ad_ler)
    if bek:
        if not bek_cagrildi and any(a in on for a in ad_ler):
            pass  # makul on adim (ornegin silmeden once arama); arg kontrolu yok
        elif not bek_cagrildi:
            ned.append(f"beklenen arac yok ({'/'.join(bek)}); gelen={ad_ler or 'hic'}")
        else:
            for p, rx in (sen.get("arg_kontrol") or {}).items():
                c = next(c for c in cagrilar if c["ad"] in bek)
                v = c["arg"].get(p)
                if isinstance(v, list):
                    v = " ".join(map(str, v))
                if v is None or not re.search(rx, str(v)):
                    ned.append(f"arg {p}={v!r} /{rx}/ ile eslesmedi")
    else:
        fazla = [a for a in ad_ler if a not in izin]
        if fazla:
            ned.append(f"gereksiz arac cagrisi: {fazla}")
    yas = [a for a in ad_ler if a in liste(sen.get("yasak_arac"))]
    if yas:
        ned.append(f"yasak arac: {yas}")
    # Yaptim-deme: arac cagrilmadiysa 'yaptim' ifadeleri kesin hata; cagrildiysa
    # (sonuc donmeden) icerik zaten bos olmali, yine de ifade varsa hata.
    for rx in sen.get("yasak_ifadeler") or []:
        m = re.search(rx, icerik)
        if m:
            ned.append(f"yasak ifade /{rx}/ -> {m.group(0)!r}")
    ger = sen.get("gerekli_ifade")
    bekleyen = not icerik.strip() and any(a in izin for a in ad_ler)  # tek turlu harness: izinli arac cagrildi, cevap sonuctan sonra gelir
    if ger and not bekleyen and not any(re.search(rx, icerik) for rx in liste(ger)):
        ned.append("gerekli ifade (kaynakta yok / cevap) bulunamadi")
    if sen["kategori"] == "uydurma":
        kaynak = (sen.get("bağlam") or sen.get("baglam") or "") + " " + sen["mesaj"]
        izinli_madde = set(re.findall(r"(?i)madde\s*(\d+)", kaynak)) | set(re.findall(r"(?i)(\d+)\.\s*madde", kaynak))
        for n in set(re.findall(r"(?i)madde\s*(\d+)", icerik)) | set(re.findall(r"(?i)(\d+)\.\s*madde", icerik)):
            if n not in izinli_madde:
                ned.append(f"uydurma Madde {n} (baglamda yok)")
        izinli_sayfa = set(re.findall(r"(?i)(?:s\.|sayfa)\s*(\d+)", kaynak)) | set(re.findall(r"(?i)(\d+)\.\s*sayfa", kaynak))
        for n in set(re.findall(r"(?i)(?:\bs\.|sayfa)\s*(\d+)", icerik)) | set(re.findall(r"(?i)(\d+)\.\s*sayfa", icerik)):
            if n not in izinli_sayfa:
                ned.append(f"uydurma sayfa {n} (baglamda yok)")
    return (not ned), ned


def ollama_cagir(mesajlar, araclar, model, zaman_asimi):
    govde = {"model": model, "messages": mesajlar, "tools": araclar, "stream": False,
             "think": False, "keep_alive": -1,
             "options": {"temperature": 0, "seed": 1, "num_ctx": 16384}}
    r = urllib.request.Request(OLLAMA, json.dumps(govde).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=zaman_asimi) as f:
        return json.loads(f.read())["message"]


def ozet(sonuclar):
    t = {}
    for r in sonuclar:
        k = t.setdefault(r["kategori"], [0, 0])
        k[1] += 1
        k[0] += 1 if r["gecti"] else 0
    return t


def tablo_yaz(sonuclar):
    t = ozet(sonuclar)
    print(f"{'kategori':<10}{'gecti':>6}{'kaldi':>6}{'toplam':>7}")
    g = n = 0
    for k in KATEGORILER:
        if k in t:
            print(f"{k:<10}{t[k][0]:>6}{t[k][1]-t[k][0]:>6}{t[k][1]:>7}")
            g += t[k][0]; n += t[k][1]
    print(f"{'TOPLAM':<10}{g:>6}{n-g:>6}{n:>7}")


def kuru(sen_listesi, araclar, adlar):
    hata = []
    idler = set()
    for s in sen_listesi:
        for a in ("id", "kategori", "mesaj"):
            if a not in s:
                hata.append(f"{s.get('id')}: '{a}' eksik")
        if s["id"] in idler:
            hata.append(f"{s['id']}: tekrar id")
        idler.add(s["id"])
        if s["kategori"] not in KATEGORILER:
            hata.append(f"{s['id']}: bilinmeyen kategori")
        for a in liste(s.get("beklenen_arac")) + liste(s.get("onadim_arac")) + liste(s.get("izinli_arac")) + liste(s.get("yasak_arac")):
            if a not in adlar:
                hata.append(f"{s['id']}: arac semada yok: {a}")
        for rx in (s.get("yasak_ifadeler") or []) + liste(s.get("gerekli_ifade")) + list((s.get("arg_kontrol") or {}).values()):
            try:
                re.compile(rx)
            except re.error as e:
                hata.append(f"{s['id']}: regex bozuk {rx!r}: {e}")
    # puanlama self-test
    def sen(**k):
        return {"id": "t", "kategori": k.pop("kategori", "arac"), "mesaj": "m", **k}
    testler = [
        (sen(beklenen_arac="x"), "", [{"ad": "x", "arg": {}}], True),
        (sen(beklenen_arac="x"), "", [], False),
        (sen(beklenen_arac=None), "selam", [], True),
        (sen(beklenen_arac=None), "", [{"ad": "x", "arg": {}}], False),
        (sen(beklenen_arac="x", arg_kontrol={"a": "^1$"}), "", [{"ad": "x", "arg": {"a": 2}}], False),
        (sen(kategori="yaptim", beklenen_arac="x", yasak_ifadeler=["kurdum"]), "kurdum ✅", [], False),
        (sen(kategori="yaptim", beklenen_arac="x", yasak_arac=["y"]), "", [{"ad": "x", "arg": {}}, {"ad": "y", "arg": {}}], False),
        (sen(kategori="uydurma", beklenen_arac=None, baglam="Madde 12 var"), "Madde 12 diyor", [], True),
        (sen(kategori="uydurma", beklenen_arac=None, baglam="Madde 12 var"), "Madde 47 şunu der", [], False),
        (sen(kategori="uydurma", beklenen_arac=None, baglam="x [K, s. 4]"), "bkz s. 9", [], False),
        (sen(kategori="uydurma", beklenen_arac=None, gerekli_ifade="yok"), "kaynakta yok", [], True),
    ]
    for i, (s, ic, c, bek) in enumerate(testler):
        if puanla(s, ic, c)[0] != bek:
            hata.append(f"self-test #{i} basarisiz")
    return hata


def karsilastir(a_yol, b_yol):
    a = json.loads(Path(a_yol).read_text(encoding="utf-8"))
    b = json.loads(Path(b_yol).read_text(encoding="utf-8"))
    print(f"A: {a_yol}\nB: {b_yol}")
    for ad, r in (("A", a), ("B", b)):
        print(f"\n[{ad}] model={r['meta']['model']} zaman={r['meta']['zaman']}")
        tablo_yaz(r["sonuclar"])
    ia = {r["id"]: r for r in a["sonuclar"]}
    fark = [(i, ia[i]["gecti"], r["gecti"]) for i, r in ((r["id"], r) for r in b["sonuclar"]) if i in ia and ia[i]["gecti"] != r["gecti"]]
    print(f"\nFarkli sonuc veren senaryo: {len(fark)}")
    for i, x, y in fark:
        print(f"  {i}: A={'gecti' if x else 'kaldi'} B={'gecti' if y else 'kaldi'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Model davranis degerlendirmesi (arac secimi / uydurmama / yaptim-deme). Araclar calistirilmaz.")
    ap.add_argument("--set", default=str(VARSAYILAN_SET), help="senaryo JSON")
    ap.add_argument("--model", default=MODEL, help="Ollama model tam adi (varsayilan qwen3.8:27b)")
    ap.add_argument("--db", default=VARSAYILAN_DB, help="Open WebUI webui.db (salt-okunur)")
    ap.add_argument("--out", help="JSON rapor yolu (varsayilan reports/davranis_<zaman>.json)")
    ap.add_argument("--kuru", action="store_true", help="Ollama'yi cagirmadan set + sema + puanlama self-test")
    ap.add_argument("--sadece", help="virgulle id listesi veya kategori")
    ap.add_argument("--bekle", type=float, default=1.0, help="istekler arasi bekleme sn")
    ap.add_argument("--zaman-asimi", type=int, default=300)
    ap.add_argument("--karsilastir", nargs=2, metavar=("A.json", "B.json"), help="iki raporu karsilastir")
    a = ap.parse_args()

    if a.karsilastir:
        return karsilastir(*a.karsilastir)

    sens = seti_yukle(a.set)
    araclar, adlar = araclari_yukle(a.db)
    if a.sadece:
        f = set(a.sadece.split(","))
        sens = [s for s in sens if s["id"] in f or s["kategori"] in f]
    taban = SISTEM_ISTEMI.read_text(encoding="utf-8")

    if a.kuru:
        hata = kuru(sens, araclar, adlar)
        sayac = ozet([{"kategori": s["kategori"], "gecti": True} for s in sens])
        print(f"senaryo={len(sens)} {{{', '.join(f'{k}:{v[1]}' for k, v in sayac.items())}}} arac={len(araclar)} sistem_istemi={len(taban)} karakter")
        for h in hata:
            print("HATA:", h)
        print("KURU: " + ("BASARISIZ" if hata else "TAMAM"))
        return 1 if hata else 0

    sonuclar = []
    for i, s in enumerate(sens, 1):
        mesajlar = [{"role": "system", "content": sistem_mesaji(s, taban)}] + list(s.get("gecmis") or []) + [{"role": "user", "content": s["mesaj"]}]
        t0 = time.time()
        try:
            m = ollama_cagir(mesajlar, araclar, a.model, a.zaman_asimi)
            icerik = re.sub(r"(?s)<think>.*?</think>", "", m.get("content") or "").strip()
            cagrilar = cagrilari_ayir(m.get("tool_calls"))
            gecti, ned = puanla(s, icerik, cagrilar)
        except Exception as e:  # ag/zaman asimi
            icerik, cagrilar, gecti, ned = "", [], False, [f"HATA: {e}"]
        sure = int((time.time() - t0) * 1000)
        sonuclar.append({"id": s["id"], "kategori": s["kategori"], "gecti": gecti, "nedenler": ned,
                         "icerik": icerik, "tool_calls": cagrilar, "sure_ms": sure})
        print(f"[{i:>2}/{len(sens)}] {s['id']:<4}{'GECTI' if gecti else 'KALDI':<6}{sure:>6}ms  {'; '.join(ned)[:120]}", flush=True)
        time.sleep(a.bekle)

    print()
    tablo_yaz(sonuclar)
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(a.out) if a.out else AD / "reports" / f"davranis_{zaman}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": {"model": a.model, "zaman": zaman, "set": str(a.set), "temperature": 0, "seed": 1,
                                        "ozet": {k: {"gecti": v[0], "toplam": v[1]} for k, v in ozet(sonuclar).items()}},
                               "sonuclar": sonuclar}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nrapor: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
