#!/usr/bin/env python3
"""
benchmark/soru_taslak.py — Faz 0a soru seti için AI-YARDIMLI TASLAK üretir.
BU BETİĞİN ÇIKTISI GROUND TRUTH DEĞİLDİR — recall_test.py'ye vermeden önce
bir insanın (öğretmen) her soruyu ve "dogru_sayfa" etiketini onaylaması/
düzeltmesi gerekir. Bu yüzden çıktı dosyası bilinçli olarak
`sorular_taslak.json` adını taşır, recall_test.py'nin beklediği `sorular.json`
değil — kopyalama/yeniden adlandırma insanın bilinçli bir "onayladım" adımı
olsun diye.

Neden insan onayı hâlâ zorunlu (bkz. konuşma geçmişi / docs/mimari.md)
-----------------------------------------------------------------------
Bir modelin hem soruyu hem "doğru sayfa" etiketini aynı geçişte üretmesi
dairesel doğrulamadır — model kendi ürettiği soruyu kendi okuduğu sayfaya
kolayca bağlar, bu retrieval kalitesini gerçekte olduğundan iyi gösterir.
Grup C ("kitapta yok") için ise bir modelin yokluğu güvenilir şekilde iddia
etmesi mümkün değil. Bu betik bu sorunları ÇÖZMÜYOR, sadece taslak yazma
işini hızlandırıyor; nihai karar hâlâ insanda.

Neden yeni bir LLM/servis eklenmedi
------------------------------------
core/saglayicilar.py'nin zaten yapılandırılmış altı sağlayıcılı havuzunu
kullanır (tools/kitap_ozet.py ile birebir aynı desen) — 'soru_taslak' görev
zinciri saglayicilar.py'ye eklendi, yeni bir API/servis DEĞİL.

ÜCRETLİDİR — --onayla olmadan hiçbir API çağrısı yapılmaz (dry run, yalnızca
plan yazdırır).

Kullanım:
    venv/bin/python soru_taslak.py --kitap-id 1                 # kuru çalışma
    venv/bin/python soru_taslak.py --kitap-id 1 --onayla         # gerçekten üret
    venv/bin/python soru_taslak.py --kitap-id 1 --onayla \
        --n-a 20 --n-b 15 --n-c 8 --cikti sorular_taslak.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CLIENT_DIR = BASE_DIR.parent / "client"
sys.path.insert(0, str(CLIENT_DIR))

from ortak import baglan, kitap_idyi_coz  # noqa: E402

MIN_CHUNK_UZUNLUK = 300  # bundan kısa parçalar (glossary vb.) atlanır

# Kitap başı/sonu (kapak, ISBN sayfası, harita eki) düz metin taşımayan
# "doldurma" chunk'lar örneklemeye girmesin — canlı testte yakalandı: harita
# ekindeki bir sayfa yüzlerce "!" karakterinden ibaretti. Bu, ISBN sayfası
# gibi OKUNAKLI ama biyoloji-dışı metni ELEMEZ — o ayrım insan onayının işi,
# bu yalnızca gürültüyü temizler.
_TEKRAR_KARAKTER_RE = re.compile(r"(.)\1{14,}")


def _muhtemelen_icerik_mi(metin: str) -> bool:
    if _TEKRAR_KARAKTER_RE.search(metin):
        return False
    harfli = sum(1 for ch in metin if ch.isalpha())
    return harfli / max(len(metin), 1) >= 0.6

GRUP_A_SISTEM = (
    "Sen 9. sınıf biyoloji öğretmenisin. Sana ders kitabından TEK bir sayfa "
    "parçası veriliyor. Bu parçada doğrudan ve açıkça cevaplanan TEK bir soru "
    "yaz — cevap parçanın içinde birebir geçmeli. Sadece soruyu yaz, başka "
    "hiçbir açıklama, tırnak işareti veya numaralandırma ekleme."
)

GRUP_B_SISTEM = (
    "Sen 9. sınıf biyoloji öğretmenisin. Sana ders kitabından birbirini "
    "izleyen birkaç sayfa parçası veriliyor, her biri [SAYFA N] etiketiyle "
    "işaretli. Bu parçaların BİRDEN FAZLASINI ilişkilendirmeden "
    "cevaplanamayacak TEK bir soru yaz — cevap tek bir cümlede değil, "
    "parçaları birleştirerek bulunmalı. Ardından bu sorunun asıl/birincil "
    "kaynağı hangi sayfaysa onu belirt. YALNIZCA şu JSON'u döndür, başka hiçbir "
    'şey yazma: {"soru": "...", "birincil_sayfa": <sayfa numarası (int)>}'
)

GRUP_C_SISTEM = (
    "Sen 9. sınıf biyoloji öğretmenisin. Sana ders kitabından bir sayfa "
    "parçası veriliyor. Bu parçanın konusuyla İLGİLİ ama parçada CEVABI "
    "OLMAYAN, daha ileri düzey/sentezleyici bir soru yaz — örnek stil: 'X ile "
    "Y'nin evrimsel avantajı nedir?', 'X'in gerçek hayatta Z açısından önemi "
    "nedir?'. Soru kitabın geri kalanında da muhtemelen cevaplanmamış "
    "olmalı. Sadece soruyu yaz, başka hiçbir şey ekleme."
)


def _chunklari_getir(conn, kitap_id: int) -> list[tuple[int, int, str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sayfa_no, metin FROM chunk_egitim "
            "WHERE kitap_id = %s ORDER BY id",
            (kitap_id,),
        )
        return [r for r in cur.fetchall()
                if len(r[2].strip()) >= MIN_CHUNK_UZUNLUK and _muhtemelen_icerik_mi(r[2])]


def _esit_araliklarla_sec(liste: list, adet: int) -> list:
    if adet <= 0 or not liste:
        return []
    adet = min(adet, len(liste))
    if adet == 1:
        return [liste[len(liste) // 2]]
    adim = (len(liste) - 1) / (adet - 1)
    return [liste[round(i * adim)] for i in range(adet)]


def _ilk_json_nesnesi(metin: str) -> dict | None:
    m = re.search(r"\{.*\}", metin, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _soru_temizle(metin: str) -> str:
    """İlk anlamlı satırı seçer. Bazı sağlayıcılar (özellikle openrouter/free'nin
    yönlendirdiği modeller) 'Bu parçada doğrudan cevaplanan soru şudur:' gibi bir
    önsöz satırı ekleyip asıl soruyu ikinci satıra koyuyor — canlı çalıştırmada
    43'te 2 örnek yakalandı. Önsöz benzeri (':' ile biten, kısa, '?' içermeyen)
    satırlar atlanır."""
    for satir in metin.strip().splitlines():
        satir = satir.strip().strip('"\'“”').strip()
        if not satir:
            continue
        if satir.endswith(":") and "?" not in satir and len(satir) < 80:
            continue
        return satir
    return metin.strip().splitlines()[0].strip() if metin.strip() else ""


def _grup_a_uret(saglayicilar, chunk) -> dict:
    _id, sayfa, metin = chunk
    soru = _soru_temizle(saglayicilar.metin_uret("soru_taslak", metin, sistem=GRUP_A_SISTEM))
    return {
        "soru": soru, "dogru_sayfa": sayfa, "grup": "A",
        "kaynak_sayfa": [sayfa], "kaynak_ozet": metin[:200],
        "onaylandi": False,
    }


def _grup_b_uret(saglayicilar, chunk_grubu) -> dict | None:
    """chunk_grubu: İKİ ARDIŞIK SAYFAYA ait chunk'ların tamamı (bkz. çağıran —
    sayfa numarasına göre eşleştirilir, chunk index sırasına göre DEĞİL; aynı
    sayfadan iki chunk'ı eşleştirmek 'ilişkilendirme' sorusunun amacını
    bozar — ilk sürümde bu hata vardı, canlı testte yakalandı)."""
    istem = "\n\n".join(f"[SAYFA {s}]\n{m}" for _, s, m in chunk_grubu)
    ham = saglayicilar.metin_uret("soru_taslak", istem, sistem=GRUP_B_SISTEM)
    ayristirilmis = _ilk_json_nesnesi(ham)
    if not ayristirilmis or "soru" not in ayristirilmis:
        print(f"  ⚠ grup B ayrıştırılamadı, atlanıyor: {ham[:120]!r}")
        return None
    sayfalar = sorted(set(s for _, s, _ in chunk_grubu))
    birincil = ayristirilmis.get("birincil_sayfa")
    if birincil not in sayfalar:
        birincil = sayfalar[0]
    return {
        "soru": ayristirilmis["soru"], "dogru_sayfa": birincil, "grup": "B",
        "kaynak_sayfa": sayfalar,
        "kaynak_ozet": " / ".join(m[:120] for _, _, m in chunk_grubu),
        "onaylandi": False,
    }


def _grup_c_uret(saglayicilar, chunk, embed_model, conn, kitap_id) -> dict:
    _id, sayfa, metin = chunk
    soru = _soru_temizle(saglayicilar.metin_uret("soru_taslak", metin, sistem=GRUP_C_SISTEM))
    vektor = embed_model.encode(soru, normalize_embeddings=True)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sayfa_no, embedding <=> %s AS mesafe FROM chunk_egitim "
            "WHERE kitap_id = %s ORDER BY mesafe LIMIT 1",
            (vektor, kitap_id),
        )
        en_yakin_sayfa, mesafe = cur.fetchone()
    benzerlik = 1 - mesafe
    uyari = None
    if benzerlik > 0.55:
        uyari = (f"Benzerlik yüksek ({benzerlik:.2f}, s.{en_yakin_sayfa}) — "
                 f"kitapta gerçekten yok mu KONTROL ET (kalibre edilmemiş eşik, "
                 f"yalnızca ipucu).")
    return {
        "soru": soru, "dogru_sayfa": None, "grup": "C",
        "kaynak_sayfa": [sayfa], "kaynak_ozet": metin[:200],
        "onaylandi": False, "otomatik_uyari": uyari,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Faz 0a soru seti TASLAĞI üretir (insan onayı gerekir)")
    ap.add_argument("--kitap-id", type=int, default=None)
    ap.add_argument("--n-a", type=int, default=20, help="Grup A (doğrudan bilgi) adedi")
    ap.add_argument("--n-b", type=int, default=15, help="Grup B (ilişkilendirme) adedi")
    ap.add_argument("--n-c", type=int, default=8, help="Grup C (kitapta yok) adedi")
    ap.add_argument("--cikti", default=str(BASE_DIR / "sorular_taslak.json"))
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    ap.add_argument("--onayla", action="store_true",
                    help="Gerçekten API çağrısı yap (ücretli). Verilmezse yalnızca plan yazdırılır.")
    a = ap.parse_args()

    conn = baglan(a.db_host, a.db_name, a.db_user)
    kitap_id = kitap_idyi_coz(conn, a.kitap_id)
    chunklar = _chunklari_getir(conn, kitap_id)
    if len(chunklar) < 2:
        raise SystemExit(f"kitap_id={kitap_id} için yeterli chunk yok ({len(chunklar)}).")

    a_secim = _esit_araliklarla_sec(chunklar, a.n_a)
    kalan = [c for c in chunklar if c not in a_secim]

    # Grup B: SAYFA bazlı ardışık çift (chunk index'i değil — aynı sayfanın
    # iki chunk'ını eşleştirmek "ilişkilendirme" amacını bozar).
    sayfa_haritasi: dict[int, list] = {}
    for c in chunklar:
        sayfa_haritasi.setdefault(c[1], []).append(c)
    sayfalar_sirali = sorted(sayfa_haritasi)
    gecerli_sayfa_ciftleri = [(p, p + 1) for p in sayfalar_sirali if (p + 1) in sayfa_haritasi]
    secilen_sayfa_ciftleri = _esit_araliklarla_sec(gecerli_sayfa_ciftleri, a.n_b)
    b_gruplari = [sayfa_haritasi[p1] + sayfa_haritasi[p2] for p1, p2 in secilen_sayfa_ciftleri]

    c_secim = _esit_araliklarla_sec(kalan or chunklar, a.n_c)

    print(f"kitap_id={kitap_id}: {len(chunklar)} kullanılabilir chunk.")
    print(f"Plan: Grup A={len(a_secim)}, Grup B={len(b_gruplari)}, Grup C={len(c_secim)}")

    if not a.onayla:
        print("\n(--onayla verilmedi: kuru çalışma, hiçbir API çağrısı yapılmadı.)")
        print("Gerçekten üretmek için: --onayla (ücretlidir, altı sağlayıcı havuzu kullanılır)")
        return 0

    from core import saglayicilar
    from sentence_transformers import SentenceTransformer
    embed_model = SentenceTransformer("BAAI/bge-m3", device="cpu")

    taslaklar = []
    for i, c in enumerate(a_secim, 1):
        print(f"  Grup A {i}/{len(a_secim)} (s.{c[1]})…")
        try:
            taslaklar.append(_grup_a_uret(saglayicilar, c))
        except Exception as e:
            print(f"    ✖ atlandı: {type(e).__name__}: {str(e)[:120]}")

    for i, grup in enumerate(b_gruplari, 1):
        sayfalar = sorted(set(c[1] for c in grup))
        print(f"  Grup B {i}/{len(b_gruplari)} (s.{sayfalar})…")
        try:
            kayit = _grup_b_uret(saglayicilar, grup)
            if kayit:
                taslaklar.append(kayit)
        except Exception as e:
            print(f"    ✖ atlandı: {type(e).__name__}: {str(e)[:120]}")

    for i, c in enumerate(c_secim, 1):
        print(f"  Grup C {i}/{len(c_secim)} (s.{c[1]})…")
        try:
            taslaklar.append(_grup_c_uret(saglayicilar, c, embed_model, conn, kitap_id))
        except Exception as e:
            print(f"    ✖ atlandı: {type(e).__name__}: {str(e)[:120]}")

    hedef = Path(a.cikti)
    hedef.write_text(json.dumps(taslaklar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(taslaklar)} taslak yazıldı: {hedef}")
    print("⚠ Bu bir TASLAK. recall_test.py'ye vermeden önce her soruyu ve "
          "dogru_sayfa'yı elle onayla/düzelt, sonra sorular.json olarak kaydet.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
