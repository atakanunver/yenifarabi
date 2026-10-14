"""Google Form kazanım testi sonuçlarının TOPLU okunması (PostgreSQL soru_havuzu) — yalnızca SELECT.

Sınıf/okul raporları öğrenci başına ayrı sorgu yerine tek sorgu kullanır. Yazma yoktur; erişilemezse
KaynakHatasi fırlar ve çağıran 'kaynak erişilemedi' der (veri uydurulmaz).
"""

from collections import defaultdict

from kaynaklar.kazanim import TestSonucu, _baglan


def sonuclar(okul_nolar: list[int]) -> dict[int, list[TestSonucu]]:
    """okul_no -> o öğrencinin form testi sonuçları (kaynaklar.kazanim.form_sonuclari ile aynı şekil)."""
    if not okul_nolar:
        return {}
    cikti: dict[int, list[TestSonucu]] = defaultdict(list)
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            "SELECT c.okul_no, t.ders, t.hafta, t.kazanim, count(*) FILTER (WHERE c.dogru), count(*),"
            " to_char(min(c.zaman) AT TIME ZONE 'Europe/Istanbul', 'YYYY-MM-DD')"
            " FROM form_cevap c JOIN form_testi t ON t.id = c.form_testi_id"
            " WHERE c.okul_no = ANY(%s) GROUP BY c.okul_no, t.id, t.ders, t.hafta, t.kazanim",
            (list(okul_nolar),),
        )
        for r in cur.fetchall():
            cikti[r[0]].append(TestSonucu(*r[1:]))
    return dict(cikti)
