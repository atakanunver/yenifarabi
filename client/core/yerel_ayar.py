"""Farabi 2.0 yerel ses ayarları (config/api_keys.json; core/tahta.py ile aynı okuma deseni)."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Sistem talimatına eklenir (yerel_main + benchmark/v2_uctan_uca.py aynısını kullanır).
YEREL_KURALLAR = (
    "\n\n[YEREL SES KURALLARI] Konuşma diliyle, en fazla 2-3 kısa cümleyle cevap ver. "
    "Yıldız, liste, başlık, numaralandırma, emoji KULLANMA — metin seslendirilecek. "
    "Selamlaşma, hal hatır, teşekkür ve genel sohbette HİÇBİR ARAÇ ÇAĞIRMA; doğrudan cevap ver. "
    "Öğretmenin sınıfa söylediği sözler de sohbettir, araç çağırma: örneğin "
    "\"Çocuklar hazır mıyız, derse başlayalım mı?\" ya da \"İkinci soruya kim cevap vermek ister?\" "
    "— bunlara kısa bir sözle karşılık ver. "
    "Araç yalnızca öğretmen açıkça bir iş istediğinde (kitaba bak, ekrandaki soruyu oku, video aç, "
    "yoklama al) çağrılır."
)


def _oku(alan: str, varsayilan: str) -> str:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get(alan, "") or "").strip()
    except Exception:  # noqa: BLE001 — eksik/bozuk config varsayılana düşer
        return varsayilan
    return ham or varsayilan


def ses_modu() -> str:
    m = _oku("ses_modu", "gemini").lower()
    return m if m in {"gemini", "yerel"} else "gemini"


def ses_dugumu_url() -> str:
    return _oku("ses_dugumu_url", "http://bilgehan.local:8060").rstrip("/")


def ollama_url() -> str:
    return _oku("ollama_url", "http://192.168.23.252:11434").rstrip("/")
