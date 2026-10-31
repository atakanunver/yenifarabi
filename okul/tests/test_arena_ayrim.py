"""İki arena ayrı kalır: smual.app (bireysel, okul.db) ve tahta Sınıf Arenası (/home/ata/farabi/arenasinif, kendi sonuç DB'si).

Ortak olan yalnızca salt-okunur soru havuzudur; okul tarafı havuza yazmaz ve tahta arenasının verisine/koduna dokunmaz.
"""

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
HAVUZ_OKUYUCULAR = ["kaynaklar/soru.py", "kaynaklar/arena_soru.py", "kaynaklar/form_toplu.py", "kaynaklar/kazanim.py"]
YAZMA = re.compile(r"^\s*[\"'(]?\s*(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE)\b", re.I)


def test_okul_havuza_yazmaz():
    for yol in HAVUZ_OKUYUCULAR:
        for no, satir in enumerate((KOK / yol).read_text(encoding="utf-8").splitlines(), 1):
            ham = satir.strip().lstrip("f").lstrip("\"'")
            assert not YAZMA.match(ham), f"{yol}:{no} havuza yazma benzeri SQL: {satir.strip()}"


def test_okul_tahta_arenasina_bagli_degil():
    yasak = ("arenasinif", "sonuclar.db", "sinif_arena", "soru_kullanim", "kullanim_sayisi =")
    for dosya in KOK.rglob("*.py"):
        if "venv" in dosya.parts or "tests" in dosya.parts or ".venv" in str(dosya):
            continue
        metin = dosya.read_text(encoding="utf-8")
        for y in yasak:
            if y in metin:
                satir = next(s for s in metin.splitlines() if y in s)
                # yalnızca açıklama/yorum satırı olarak anılabilir
                assert satir.lstrip().startswith(("#", '"', "'")) or "salt" in satir.lower() or "dokunulmaz" in satir.lower() or "yazılm" in satir.lower(), (
                    f"{dosya.name}: '{y}' kullanımı tahta arenasıyla ayrımı bozabilir: {satir.strip()}"
                )


def test_arena_tablolari_okul_dbsinde():
    import db

    sema = "\n".join(db.GOCLER)
    for t in ("bilgi_tur", "bilgi_cevap", "bilgi_xp", "bilgi_rozet", "odul", "avatar"):
        assert f"CREATE TABLE {t} " in sema or f"CREATE TABLE {t}(" in sema
