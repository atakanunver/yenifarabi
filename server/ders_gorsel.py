"""Ders görsellerinin kimliği doğrulanmış, kalıcı dosya arşivi."""
from __future__ import annotations

import fcntl
import io
import json
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import auth
from fastapi import APIRouter, Depends, HTTPException, Request
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

log = logging.getLogger("farabi.ders_gorsel")
router = APIRouter()

LIMIT = 512 * 1024  # 512 KiB
MIN_FREE = int(os.environ.get("FARABI_MIN_FREE", str(50 * 1024**3)))  # 50 GB
TZ = ZoneInfo("Europe/Istanbul")
DAYS = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma", 6: "cumartesi", 7: "pazar"}

DEFAULT_ROOT = Path("/mnt/farabi-data/farabi/ders_gorselleri")
DEFAULT_MOUNT = Path("/mnt/farabi-data")
DEFAULT_DATA = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data"
DEFAULT_TEACHERS = Path(__file__).resolve().parent.parent / "tahtayoklama" / "dashboard" / "config" / "ogretmenler.json"

ROOT = Path(os.environ.get("FARABI_DERS_GORSEL_ROOT", str(DEFAULT_ROOT)))
MOUNT = Path(os.environ.get("FARABI_DERS_GORSEL_MOUNT", str(DEFAULT_MOUNT)))
DATA = DEFAULT_DATA
TEACHERS = DEFAULT_TEACHERS
ZIL_PATH = Path(os.environ.get("FARABI_ZIL_PATH", str(DEFAULT_DATA / "zil.json")))
PROGRAM_PATH = Path(os.environ.get("FARABI_PROGRAM_PATH", str(DEFAULT_DATA / "ders_programi.json")))
TEACHERS_PATH = Path(os.environ.get("FARABI_TEACHERS_PATH", str(DEFAULT_TEACHERS)))


def get_now() -> datetime:
    """Sunucu saatini döndürür; testlerde enjeksiyon veya monkeypatch için izoledir."""
    return datetime.now(TZ)


def slug(value: str) -> str:
    """Türkçe karakterleri güvenli ascii slug'a çevirir; traversal karakterlerini temizler."""
    if not value or not isinstance(value, str):
        return "_bilinmeyen"
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "I": "i",
        "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u",
        "ö": "o", "Ö": "o",
        "ç": "c", "Ç": "c",
    })
    clean = value.translate(tr_map)
    clean = unicodedata.normalize("NFKD", clean).encode("ascii", "ignore").decode().lower()
    clean = re.sub(r"[^a-z0-9_-]+", "-", clean).strip("-")[:80]
    return clean or "_bilinmeyen"


def read_json(path: Path) -> dict:
    """JSON dosyasını güvenle okur; hata veya geçersiz içerikte boş sözlük döner."""
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def context(board: str, now: datetime) -> tuple[int, str, str, list[str]]:
    """Zil, ders programı ve öğretmen verisinden ders slotunu çözümler."""
    zil_file = ZIL_PATH if ZIL_PATH != DEFAULT_DATA / "zil.json" else (DATA / "zil.json")
    bell = read_json(zil_file)
    ders_gunleri = bell.get("ders_gunleri", [1, 2, 3, 4, 5])
    weekday = now.isoweekday()
    if weekday not in ders_gunleri:
        raise HTTPException(status_code=422, detail="Ders saati dışında")

    minute = now.hour * 60 + now.minute
    lesson = None
    for item in bell.get("dersler", []):
        try:
            start_parts = item["baslangic"].split(":")
            end_parts = item["bitis"].split(":")
            start_min = int(start_parts[0]) * 60 + int(start_parts[1])
            end_min = int(end_parts[0]) * 60 + int(end_parts[1])
            if start_min <= minute <= end_min:
                lesson = int(item["no"])
                break
        except (KeyError, ValueError, TypeError, IndexError):
            continue

    if lesson is None or not (1 <= lesson <= 12):
        raise HTTPException(status_code=422, detail="Ders saati dışında")

    day = DAYS.get(weekday, "pazartesi")

    # Ders adı
    prog_file = PROGRAM_PATH if PROGRAM_PATH != DEFAULT_DATA / "ders_programi.json" else (DATA / "ders_programi.json")
    prog = read_json(prog_file)
    try:
        s_val = prog.get("siniflar", {}).get(board, {}).get(day, {}).get(str(lesson))
        if isinstance(s_val, dict):
            s_val = s_val.get("ders", "")
        if isinstance(s_val, str) and s_val.strip():
            subject = s_val.strip()
        else:
            subject = "_bilinmeyen"
    except (KeyError, TypeError, ValueError):
        subject = "_bilinmeyen"

    # Öğretmen(ler)
    teachers_file = TEACHERS_PATH if TEACHERS_PATH != DEFAULT_TEACHERS else TEACHERS
    teachers_data = read_json(teachers_file)
    raw_teachers: list[str] = []
    try:
        t_val = teachers_data.get("program", {}).get(board, {}).get(day, {}).get(str(lesson))
        if isinstance(t_val, list):
            raw_teachers = [str(t).strip() for t in t_val if isinstance(t, str) and str(t).strip()]
    except (KeyError, TypeError, ValueError):
        raw_teachers = []

    if not raw_teachers:
        folder_teacher = "_bilinmeyen"
        teachers_list: list[str] = []
    elif len(raw_teachers) == 1:
        folder_teacher = slug(raw_teachers[0])
        teachers_list = raw_teachers
    else:
        folder_teacher = "_birden_fazla"
        teachers_list = raw_teachers

    return lesson, subject, folder_teacher, teachers_list


def validate_image(raw: bytes) -> None:
    """WebP biçimini, tek kareliği ve çözünürlük sınırını (≤2 MP) doğrular."""
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        raise HTTPException(status_code=415, detail="Geçersiz WebP imzası")

    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format != "WEBP":
                raise HTTPException(status_code=415, detail="Yalnızca WebP desteklenir")
            if getattr(img, "n_frames", 1) > 1:
                raise HTTPException(status_code=415, detail="Animasyonlu WebP kabul edilmez")
            if img.width * img.height > 2_000_000:
                raise HTTPException(status_code=413, detail="Görsel çözünürlüğü 2 MP sınırını aşıyor")
            img.load()
    except Image.DecompressionBombError:
        raise HTTPException(status_code=413, detail="Görsel boyutu aşırı büyük") from None
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=415, detail="Geçersiz WebP görseli") from None


def _atomic_write(target_path: Path, content: bytes) -> None:
    """Aynı dizinde tmp oluşturur, fsync ile diske yazar ve atomik olarak taşır."""
    directory = target_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def persist(
    board: str,
    lesson: int,
    subject: str,
    folder_teacher: str,
    teachers_list_or_now: list[str] | datetime,
    now_or_sira: datetime | int,
    sira_or_raw: int | bytes,
    raw: bytes | None = None,
) -> tuple[str, int]:
    """Görseli ve ders.json'u fcntl kilit altında atomik olarak kaydeder."""
    if raw is None:
        teachers_list = [folder_teacher] if folder_teacher not in ("_bilinmeyen", "_birden_fazla") else []
        now = teachers_list_or_now  # type: ignore[assignment]
        sira = now_or_sira  # type: ignore[assignment]
        raw_bytes: bytes = sira_or_raw  # type: ignore[assignment]
    else:
        teachers_list = teachers_list_or_now  # type: ignore[assignment]
        now = now_or_sira  # type: ignore[assignment]
        sira = sira_or_raw  # type: ignore[assignment]
        raw_bytes = raw

    if not os.path.ismount(MOUNT) or shutil.disk_usage(MOUNT).free < MIN_FREE:
        raise HTTPException(status_code=503, detail="Arşiv diski kullanılamıyor")

    ROOT.mkdir(parents=True, exist_ok=True)
    resolved_root = ROOT.resolve()

    date_str = now.strftime("%Y-%m-%d")
    date_lesson_dir = f"{date_str}_{lesson}.ders"
    directory = ROOT / slug(board) / slug(subject) / folder_teacher / date_lesson_dir
    directory.mkdir(parents=True, exist_ok=True)

    resolved_dir = directory.resolve()
    if not resolved_dir.is_relative_to(resolved_root):
        raise HTTPException(status_code=400, detail="Geçersiz dizin yolu")

    cur = directory
    while cur != ROOT and cur != cur.parent:
        if cur.is_symlink():
            raise HTTPException(status_code=400, detail="Symlink kullanılamaz")
        cur = cur.parent

    # Ders başına fcntl kilidi (anahtar: derslik + tarih + ders_no)
    lock_dir = ROOT / ".kilitler"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{slug(board)}_{date_str}_{lesson}.lock"

    with open(lock_path, "a+b") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            # Kota ders bazındadır (derslik + tarih + ders_no)
            board_dir = ROOT / slug(board)
            pattern = f"*/*/{date_lesson_dir}/*.webp"
            existing_frames = list(board_dir.glob(pattern))
            current_count = len(existing_frames)
            if current_count >= 20:
                raise HTTPException(status_code=429, detail="Ders kotası dolu")

            name = f"{now:%H%M%S}_{sira}.webp"
            target_path = directory / name
            if target_path.exists():
                stem = f"{now:%H%M%S}_{sira}"
                for suffix in range(1, 100):
                    cand = f"{stem}_{suffix}.webp"
                    if not (directory / cand).exists():
                        name = cand
                        target_path = directory / name
                        break
                else:
                    raise HTTPException(status_code=429, detail="Kayıt sınırı")

            if target_path.is_symlink():
                raise HTTPException(status_code=400, detail="Symlink kullanılamaz")

            metadata_path = directory / "ders.json"
            if metadata_path.is_symlink():
                raise HTTPException(status_code=400, detail="Symlink kullanılamaz")

            metadata = read_json(metadata_path)
            if not metadata:
                teacher_field = teachers_list[0] if len(teachers_list) == 1 else folder_teacher
                metadata = {
                    "derslik": board,
                    "sinif": board,
                    "ders": subject,
                    "ogretmen": teacher_field,
                    "ogretmenler": teachers_list,
                    "tarih": date_str,
                    "ders_no": lesson,
                    "kareler": [],
                }
            else:
                if "ogretmenler" not in metadata:
                    metadata["ogretmenler"] = teachers_list
                if "kareler" not in metadata or not isinstance(metadata["kareler"], list):
                    metadata["kareler"] = []

            metadata["kareler"].append({
                "dosya": name,
                "saat": now.isoformat(),
                "sira": sira,
            })

            # 1. Görseli atomik yaz
            _atomic_write(target_path, raw_bytes)

            # 2. ders.json atomik yaz; hata olursa görseli sil
            try:
                meta_bytes = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
                _atomic_write(metadata_path, meta_bytes)
            except Exception:
                target_path.unlink(missing_ok=True)
                raise

            return name, current_count + 1
        finally:
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


@router.post("/api/ders-gorsel", status_code=202)
async def upload(
    request: Request,
    identity: Annotated[auth.TahtaKimligi | None, Depends(auth.dogrula_tahta)] = None,
):
    if identity is None:
        raise HTTPException(status_code=401, detail="Tahta kimliği gerekli")

    # 1. Gövde boyutu sınırı (512 KiB) — chunked / no-Content-Length dahil
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > LIMIT:
            raise HTTPException(status_code=413, detail="İstek çok büyük")

    # Starlette multipart parser'ının stream'i bellekten ayrıştırabilmesi için
    request._body = bytes(body)

    # 2. Multipart form ayrıştırma ve alan doğrulama
    try:
        form = await request.form(max_files=1, max_fields=1)
    except (StarletteHTTPException, HTTPException) as exc:
        if exc.status_code == 400:
            raise HTTPException(status_code=422, detail="Form alanı/dosya sayısı sınırı aşıldı") from None
        raise
    except (MultiPartException, ValueError, RuntimeError, OSError):
        raise HTTPException(status_code=422, detail="Geçersiz metadata") from None

    if set(form.keys()) != {"image", "metadata"}:
        raise HTTPException(status_code=422, detail="Geçersiz metadata")

    image_item = form["image"]
    if not isinstance(image_item, UploadFile):
        raise HTTPException(status_code=422, detail="Geçersiz metadata")

    raw_metadata = form["metadata"]
    if not isinstance(raw_metadata, str):
        raise HTTPException(status_code=422, detail="Geçersiz metadata")

    try:
        meta = json.loads(raw_metadata)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=422, detail="Geçersiz metadata") from None

    if not isinstance(meta, dict) or set(meta.keys()) != {"sira"}:
        raise HTTPException(status_code=422, detail="Geçersiz metadata")

    sira = meta["sira"]
    if type(sira) is not int or not (1 <= sira <= 99):
        raise HTTPException(status_code=422, detail="Geçersiz metadata")

    raw_image = await image_item.read()
    if not raw_image:
        raise HTTPException(status_code=415, detail="Geçersiz WebP")

    # 3. Ders context'i çözümleme
    now = get_now()
    ctx = context(identity.derslik, now)
    if len(ctx) == 4:
        lesson, subject, folder_teacher, teachers_list = ctx
    else:
        lesson, subject, folder_teacher = ctx
        teachers_list = [folder_teacher] if folder_teacher not in ("_bilinmeyen", "_birden_fazla") else []

    # 4. Görsel doğrulama ve arşiv kaydı (threadpool)
    await run_in_threadpool(validate_image, raw_image)

    try:
        _name, kare_sayisi = await run_in_threadpool(
            persist,
            identity.derslik,
            lesson,
            subject,
            folder_teacher,
            teachers_list,
            now,
            sira,
            raw_image,
        )
    except HTTPException:
        raise
    except OSError:
        log.exception("Ders görseli kaydedilemedi")
        raise HTTPException(status_code=503, detail="Arşiv kullanılamıyor") from None

    return {"status": "ok", "ders_no": lesson, "kare_sayisi": kare_sayisi}
