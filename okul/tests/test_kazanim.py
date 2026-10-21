from kaynaklar import kazanim
from kaynaklar.kazanim import TestSonucu


def test_ozet_form_ve_odev_birlesir():
    form = [
        TestSonucu("matematik", 3, "Kesirler", 8, 10, "2026-10-01"),
        TestSonucu("matematik", 4, "Oran", 3, 10, "2026-10-08"),
        TestSonucu("fizik", 2, "Hız", 7, 10, "2026-10-02"),
    ]
    odev = [
        ("matematik", "Kesirler", False),
        ("matematik", "Kesirler", True),
        ("fizik", "Kuvvet", True),
    ]
    o = kazanim.ozet(form, odev)
    mat = {d.kazanim: (d.dogru, d.toplam) for d in o["matematik"]}
    assert mat == {"Kesirler": (9, 12), "Oran": (3, 10)}
    assert {d.kazanim for d in o["fizik"]} == {"Hız", "Kuvvet"}


def test_basari_esigi():
    d = kazanim.KazanimDurum("matematik", "K", 7, 10)
    assert d.basarili(0.7)
    assert not kazanim.KazanimDurum("matematik", "K", 6, 10).basarili(0.7)
    assert d.yuzde == 70


def test_ders_ozeti():
    o = kazanim.ozet(
        [
            TestSonucu("matematik", 1, "A", 9, 10, "x"),
            TestSonucu("matematik", 2, "B", 1, 10, "x"),
        ],
        [],
    )
    assert kazanim.ders_ozeti(o, 0.7) == [("matematik", 1, 2)]


def test_plan_kazanimlari_ve_haftalik_kazanim(tmp_path, monkeypatch):
    import json
    from datetime import date

    from ayarlar import AYAR

    veri = {
        "haftalar": {
            "1": "2026-09-14",
            "2": "2026-09-21",
            "5": "2026-10-12",
        },
        "kazanimlar": {
            "10": {
                "kimya": {"5": "KİM.10.1.4. Mol kavramı"},
                "matematik": {"5": "MAT.10.1. Üçgen alanı"},
            },
            "9": {
                "beden eğitimi": {"5": "TSE.9.2.1. Kuvvet tanımı"},
            },
        },
    }
    dosya = tmp_path / "kazanimlar.json"
    dosya.write_text(json.dumps(veri), encoding="utf-8")
    monkeypatch.setattr(AYAR, "kazanim_yolu", dosya)
    # cache sıfırla
    kazanim._plan_onbellek.clear()

    # Tam eşleşme
    assert kazanim.haftalik_kazanim("10-A", "kimya", date(2026, 10, 13)) == "KİM.10.1.4. Mol kavramı"
    assert kazanim.haftalik_kazanim("10-B", "matematik", date(2026, 10, 15)) == "MAT.10.1. Üçgen alanı"

    # Alternatif ad eşleşmesi: spor etkinlikleri -> beden eğitimi
    assert kazanim.haftalik_kazanim("9-A", "spor etkinlikleri", date(2026, 10, 14)) == "TSE.9.2.1. Kuvvet tanımı"

    # Hafta dışı / olmayan ders / geçersiz sınıf
    assert kazanim.haftalik_kazanim("10-A", "fizik", date(2026, 10, 13)) is None
    assert kazanim.haftalik_kazanim("10-A", "kimya", date(2026, 11, 1)) is None
    assert kazanim.haftalik_kazanim("", "kimya") is None
    assert kazanim.haftalik_kazanim("10-A", "") is None


def test_ogretmen_ana_sayfa_kazanim(ornek, conn, tmp_path, monkeypatch, saat):
    import json

    from app import app
    from ayarlar import AYAR
    from starlette.testclient import TestClient

    veri = {
        "haftalar": {"5": "2026-10-12"},
        "kazanimlar": {
            "10": {"kimya": {"5": "KİM.10.1.4. Mol kavramı"}},
        },
    }
    dosya = tmp_path / "kazanimlar.json"
    dosya.write_text(json.dumps(veri), encoding="utf-8")
    monkeypatch.setattr(AYAR, "kazanim_yolu", dosya)
    kazanim._plan_onbellek.clear()

    # Hoca kullanıcısına görev ata
    hoca_id = ornek["ogretmen"]
    conn.execute("INSERT OR REPLACE INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, ?, ?)",
                 (hoca_id, "10-A", "kimya"))
    conn.commit()

    # Giriş yap ve ana sayfayı iste
    istemci = TestClient(app)
    res_giris = istemci.post("/giris", data={"kullanici_adi": "hoca", "sifre": "hoca-sifre"})
    assert res_giris.status_code in (200, 303)
    res = istemci.get("/ogretmen")
    assert res.status_code == 200
    assert "KİM.10.1.4. Mol kavramı" in res.text

