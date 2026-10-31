import concurrent.futures
import io
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import auth
import ders_gorsel as dg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

TZ = ZoneInfo("Europe/Istanbul")


def make_image(size=(40, 40), animated=False, fmt="WEBP") -> bytes:
    """Test için WebP veya diğer formatlarda görsel oluşturur."""
    buf = io.BytesIO()
    im = Image.new("RGB", size, "white")
    if fmt == "WEBP":
        if animated:
            im2 = Image.new("RGB", size, "black")
            im.save(buf, format="WEBP", save_all=True, append_images=[im2], duration=100, loop=0)
        else:
            im.save(buf, format="WEBP")
    else:
        im.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    archive_dir = tmp_path / "archive"
    mount_dir = tmp_path / "mount"
    mount_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dg, "ROOT", archive_dir)
    monkeypatch.setattr(dg, "MOUNT", mount_dir)
    monkeypatch.setattr(dg.os.path, "ismount", lambda p: str(Path(p).resolve()) == str(mount_dir.resolve()))
    monkeypatch.setattr(dg, "MIN_FREE", 0)

    fixed_now = datetime(2026, 10, 26, 10, 15, tzinfo=TZ)
    monkeypatch.setattr(dg, "get_now", lambda: fixed_now)
    monkeypatch.setattr(dg, "context", lambda board, now: (3, "Fizik", "gozde", ["Gözde"]))

    app = FastAPI()
    app.include_router(dg.router)
    app.dependency_overrides[auth.dogrula_tahta] = lambda: auth.TahtaKimligi("9-A")
    return app, archive_dir, mount_dir, fixed_now


def post_frame(client, raw=None, sira=1, metadata_override=None, files_override=None, data_override=None):
    """API endpoint'ine multipart istek gönderen yardımcı."""
    data = data_override
    if data is None:
        meta_val = metadata_override if metadata_override is not None else {"sira": sira}
        if isinstance(meta_val, dict):
            meta_val = json.dumps(meta_val)
        data = {"metadata": meta_val}

    files = files_override
    if files is None:
        files = {"image": ("test.webp", raw if raw is not None else make_image(), "image/webp")}

    return client.post("/api/ders-gorsel", data=data, files=files)


def test_auth_variations(test_setup):
    """auth yok, yanlış key ve None kimlik durumlarını test eder."""
    app, _, _, _ = test_setup
    c = TestClient(app)

    # 1. Başarılı auth (dependency override TahtaKimligi('9-A'))
    r = post_frame(c)
    assert r.status_code == 202
    assert r.json()["status"] == "ok"

    # 2. None kimlik (FARABI_AUTH_REQUIRED=0 modunda dogrula_tahta None dönerse bile 401 olmalı)
    app.dependency_overrides[auth.dogrula_tahta] = lambda: None
    assert post_frame(c).status_code == 401

    # 3. Gerçek auth dependency ile test (override kaldırılır)
    app.dependency_overrides.clear()
    # Headersız istek -> 401
    assert post_frame(c).status_code == 401
    # Yanlış key ile istek -> 401
    assert c.post("/api/ders-gorsel", headers={"X-Farabi-Board-Key": "gecersiz-anahtar"}).status_code == 401


def test_invalid_images_and_formats(test_setup):
    """sahte WebP, animasyonlu WebP, >2 MP görsel testleri."""
    app, _, _, _ = test_setup
    c = TestClient(app)

    # Sahte / bozuk WebP
    assert post_frame(c, raw=b"bu-bir-webp-degil").status_code == 415
    assert post_frame(c, raw=b"RIFF\x00\x00\x00\x00WEBPbadbad").status_code == 415
    assert post_frame(c, raw=b"").status_code == 415
    # JPEG formatı
    assert post_frame(c, raw=make_image(fmt="JPEG")).status_code == 415

    # Animasyonlu WebP (n_frames > 1) -> 415
    assert post_frame(c, raw=make_image(animated=True)).status_code == 415

    # 2 MP'den büyük çözünürlük (2000x1001 = 2_002_000 piksel) -> 413
    assert post_frame(c, raw=make_image(size=(2000, 1001))).status_code == 413


def test_request_size_and_chunked_streaming(test_setup):
    """>512 KiB gövde ve chunked büyük gövde testleri."""
    app, _, _, _ = test_setup
    c = TestClient(app)

    # 512 KiB'den büyük multipart içerik -> 413
    assert post_frame(c, raw=b"x" * (dg.LIMIT + 1024)).status_code == 413

    # Chunked / streaming büyük gövde testi
    def chunk_generator():
        for _ in range(60):
            yield b"x" * 10240  # 600 KiB > 512 KiB

    resp = c.post("/api/ders-gorsel", content=chunk_generator(), headers={"Content-Type": "application/octet-stream"})
    assert resp.status_code == 413


def test_metadata_and_form_schema(test_setup):
    """Metadata JSON doğrulaması (yalnız sira 1..99; bilinmeyen alanlar -> 422)."""
    app, _, _, _ = test_setup
    c = TestClient(app)

    # Geçersiz JSON -> 422
    assert post_frame(c, metadata_override="gecersiz-json").status_code == 422
    # JSON sözlük değil -> 422
    assert post_frame(c, metadata_override="[1, 2, 3]").status_code == 422
    # Bilinmeyen alanlar -> 422
    assert post_frame(c, metadata_override={"sira": 1, "fazla": "alan"}).status_code == 422
    assert post_frame(c, metadata_override={"sequence": 1}).status_code == 422
    # Sıra int değil -> 422
    assert post_frame(c, metadata_override={"sira": "1"}).status_code == 422
    assert post_frame(c, metadata_override={"sira": True}).status_code == 422
    # Sıra sınır dışı (<1 veya >99) -> 422
    assert post_frame(c, metadata_override={"sira": 0}).status_code == 422
    assert post_frame(c, metadata_override={"sira": 100}).status_code == 422

    # Fazla form alanı -> 422
    assert post_frame(c, data_override={"metadata": '{"sira": 1}', "ekstra": "deger"}).status_code == 422
    # Fazla dosya -> 422
    assert post_frame(c, files_override={
        "image": ("1.webp", make_image(), "image/webp"),
        "extra": ("2.webp", make_image(), "image/webp"),
    }).status_code == 422


def test_schedule_and_outside_lesson(tmp_path, monkeypatch):
    """Zil, gün ve ders dışı durumlar -> 422."""
    zil_data = {
        "ders_gunleri": [1, 2, 3, 4, 5],
        "dersler": [{"no": 3, "baslangic": "10:00", "bitis": "10:40"}],
    }
    zil_file = tmp_path / "zil.json"
    zil_file.write_text(json.dumps(zil_data))
    monkeypatch.setattr(dg, "ZIL_PATH", zil_file)
    monkeypatch.setattr(dg, "DATA", tmp_path)

    prog_file = tmp_path / "ders_programi.json"
    prog_file.write_text(json.dumps({"siniflar": {"9-A": {"pazartesi": {"3": "Biyoloji"}}}}))
    monkeypatch.setattr(dg, "PROGRAM_PATH", prog_file)

    teach_file = tmp_path / "ogretmenler.json"
    teach_file.write_text(json.dumps({"program": {"9-A": {"pazartesi": {"3": ["Sevgi"]}}}}))
    monkeypatch.setattr(dg, "TEACHERS_PATH", teach_file)
    monkeypatch.setattr(dg, "TEACHERS", teach_file)

    # 1. Ders saati içi (Pazartesi 10:15) -> başarılı
    now_in = datetime(2026, 10, 26, 10, 15, tzinfo=TZ)
    lesson, subject, folder, teachers = dg.context("9-A", now_in)
    assert lesson == 3
    assert subject == "Biyoloji"
    assert folder == "sevgi"
    assert teachers == ["Sevgi"]

    # 2. Teneffüs / ders dışı saat (10:45) -> 422
    with pytest.raises(HTTPException) as exc1:
        dg.context("9-A", now_in.replace(minute=45))
    assert exc1.value.status_code == 422

    # 3. Hafta sonu (Pazar) -> 422
    now_weekend = datetime(2026, 11, 1, 10, 15, tzinfo=TZ)
    with pytest.raises(HTTPException) as exc2:
        dg.context("9-A", now_weekend)
    assert exc2.value.status_code == 422


def test_missing_program_and_teacher(tmp_path, monkeypatch, test_setup):
    """Programda ders veya öğretmen eksikse _bilinmeyen atanır."""
    app, archive_dir, _, _ = test_setup
    c = TestClient(app)

    zil_file = tmp_path / "zil.json"
    zil_file.write_text(json.dumps({
        "ders_gunleri": [1],
        "dersler": [{"no": 2, "baslangic": "09:00", "bitis": "09:40"}],
    }))
    monkeypatch.setattr(dg, "ZIL_PATH", zil_file)
    monkeypatch.setattr(dg, "PROGRAM_PATH", tmp_path / "bos_program.json")
    monkeypatch.setattr(dg, "TEACHERS_PATH", tmp_path / "bos_ogretmenler.json")

    now = datetime(2026, 10, 26, 9, 20, tzinfo=TZ)
    monkeypatch.setattr(dg, "get_now", lambda: now)
    monkeypatch.undo()  # context mock'unu kaldırıp gerçek fonksiyonu kullan
    monkeypatch.setattr(dg, "ROOT", archive_dir)
    monkeypatch.setattr(dg, "MOUNT", tmp_path)
    monkeypatch.setattr(dg.os.path, "ismount", lambda p: True)
    monkeypatch.setattr(dg, "MIN_FREE", 0)
    monkeypatch.setattr(dg, "ZIL_PATH", zil_file)
    monkeypatch.setattr(dg, "PROGRAM_PATH", tmp_path / "bos_program.json")
    monkeypatch.setattr(dg, "TEACHERS_PATH", tmp_path / "bos_ogretmenler.json")
    monkeypatch.setattr(dg, "get_now", lambda: now)

    r = post_frame(c, sira=1)
    assert r.status_code == 202
    assert r.json()["ders_no"] == 2

    # Arşivde _bilinmeyen klasörü kontrolü
    meta_files = list(archive_dir.rglob("ders.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["ders"] == "_bilinmeyen"
    assert meta["ogretmen"] == "_bilinmeyen"
    assert "_bilinmeyen/_bilinmeyen" in str(meta_files[0])


def test_multiple_teachers_slot(tmp_path, monkeypatch, test_setup):
    """Slotta >1 öğretmen varsa klasör _birden_fazla olur, tüm adlar ders.json'a yazılır."""
    app, archive_dir, _, _ = test_setup
    c = TestClient(app)

    # 2 öğretmenli mock context
    monkeypatch.setattr(dg, "context", lambda board, now: (3, "Kimya", "_birden_fazla", ["Ali Yılmaz", "Zeynep Kaya"]))

    r = post_frame(c, sira=5)
    assert r.status_code == 202

    meta_files = list(archive_dir.rglob("ders.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert "_birden_fazla" in str(meta_files[0])
    assert meta["ogretmenler"] == ["Ali Yılmaz", "Zeynep Kaya"]
    assert meta["kareler"][0]["sira"] == 5


def test_path_traversal_and_symlinks(test_setup, monkeypatch):
    """Path traversal ve symlink reddi testleri."""
    app, archive_dir, _, _ = test_setup
    c = TestClient(app)

    # Traversal denemesi slug tarafından temizlenir ve kök dışına çıkamaz
    assert "/" not in dg.slug("../../etc/passwd")
    assert dg.slug("../../etc/passwd") == "etc-passwd"

    # Symlink klasör reddi
    symlink_dir = archive_dir / "9-a" / "fizik" / "gozde" / "2026-10-26_3.ders"
    symlink_dir.parent.mkdir(parents=True, exist_ok=True)
    outside_target = archive_dir.parent / "outside"
    outside_target.mkdir(parents=True, exist_ok=True)
    symlink_dir.symlink_to(outside_target, target_is_directory=True)

    # Symlink içeren dizine yazma denemesi 400 ile reddedilmeli
    r = post_frame(c)
    assert r.status_code == 400


def test_quota_and_concurrent_uploads(test_setup):
    """20 kare kotası ve thread'lerle eşzamanlı isteklerde kota ve ders.json bütünlüğü."""
    app, archive_dir, _, _ = test_setup
    c = TestClient(app)

    # 20 kare yükle
    for i in range(1, 21):
        resp = post_frame(c, sira=i)
        assert resp.status_code == 202
        assert resp.json()["kare_sayisi"] == i

    # 21. kare kotayı aşar -> 429
    assert post_frame(c, sira=21).status_code == 429

    # Toplam kaydedilen WebP dosya sayısı tam 20 olmalı
    webp_files = list(archive_dir.rglob("*.webp"))
    assert len(webp_files) == 20

    meta_files = list(archive_dir.rglob("ders.json"))
    assert len(meta_files) == 1
    metadata = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert len(metadata["kareler"]) == 20


def test_concurrent_threads_quota(test_setup):
    """Birden fazla thread ile eşzamanlı isteklerde kotanın asla 20'yi aşmadığını doğrular."""
    app, archive_dir, _, _ = test_setup

    def upload_task(seq):
        c = TestClient(app)
        return post_frame(c, sira=seq).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(upload_task, i) for i in range(1, 26)]
        codes = [f.result() for f in futures]

    # Başarılı olanlar tam 20, kotaya takılanlar tam 5 olmalı
    assert codes.count(202) == 20
    assert codes.count(429) == 5

    webp_files = list(archive_dir.rglob("*.webp"))
    assert len(webp_files) == 20

    meta_files = list(archive_dir.rglob("ders.json"))
    metadata = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert len(metadata["kareler"]) == 20


def test_mount_and_disk_space_503(test_setup, monkeypatch):
    """Mount yoksa veya boş disk alanı < 50 GB ise 503 döner."""
    app, _, _, _ = test_setup
    c = TestClient(app)

    # 1. Mount yok
    monkeypatch.setattr(dg.os.path, "ismount", lambda p: False)
    assert post_frame(c).status_code == 503

    # 2. Mount var ama boş alan < 50 GB
    monkeypatch.setattr(dg.os.path, "ismount", lambda p: True)
    monkeypatch.setattr(dg, "MIN_FREE", 50 * 1024**3)
    # disk free alanını 10 GB simüle et
    monkeypatch.setattr(dg.shutil, "disk_usage", lambda p: type("Usage", (), {"free": 10 * 1024**3})())
    assert post_frame(c).status_code == 503


def test_atomic_ders_json_failure_leaves_no_orphan(test_setup, monkeypatch):
    """ders.json yazımı başarısız olduğunda görsel silinmeli, yarım kalmamalı."""
    app, archive_dir, _, _ = test_setup
    c = TestClient(app)

    real_atomic = dg._atomic_write

    def failing_atomic_write(target_path, content):
        if target_path.name == "ders.json":
            raise OSError("Simüle edilmiş disk yazma hatası")
        real_atomic(target_path, content)

    monkeypatch.setattr(dg, "_atomic_write", failing_atomic_write)

    resp = post_frame(c)
    assert resp.status_code == 503

    # ders.json yazılamadığı için görsel silinmiş olmalı
    webp_files = list(archive_dir.rglob("*.webp"))
    assert len(webp_files) == 0
