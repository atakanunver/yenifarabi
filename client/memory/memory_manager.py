import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

def _empty_memory() -> dict:
    return {
        "identity":     {},
        "subjects":     {},
        "weak_topics":  {},
        "goals":        {},
        "study_habits": {},
        "notes":        {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "grade", "school", "class", "target_exam", "target_department"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.replace('_', ' ').title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    sections = [
        ("subjects",     "Subject levels and progress:", 12),
        ("weak_topics",  "Topics they struggle with — revisit these:", 12),
        ("goals",        "Goals and deadlines:", 6),
        ("study_habits", "How they learn best:", 8),
        ("notes",        "Other notes:", 8),
    ]
    for cat, title, limit in sections:
        items = memory.get(cat, {})
        if not items:
            continue
        lines.append("")
        lines.append(title)
        for key, entry in list(items.items())[:limit]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    if not lines:
        return ""

    header = (
        "[WHAT YOU KNOW ABOUT THIS STUDENT — use naturally to shape your teaching, "
        "never recite it back like a list]\n"
    )
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "subjects", "weak_topics", "goals", "study_habits", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget