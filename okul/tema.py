"""Arayüz temaları: kod → (görünen ad, tarayıcı çubuğu rengi, önizleme renkleri). Renklerin kendisi static/temalar.css'te."""

import sqlite3

VARSAYILAN = "defter"

TEMALAR = {
    "defter": ("Kareli defter", "#4b1f6f", ("#fafcff", "#2446c7", "#d7263d")),
    "harita": ("Orman haritası", "#2f4b2a", ("#eef0dc", "#2f4b2a", "#e8a93b")),
    "tahta": ("Tahta", "#1f3a33", ("#1f3a33", "#f4d35e", "#8fd3e8")),
    "neon": ("Neon", "#07060c", ("#07060c", "#00f3ff", "#ff0055")),
    "blueprint": ("Blueprint", "#0b3a66", ("#0f4c81", "#e8f1fb", "#ffd166")),
    "gokyuzu": ("Gökyüzü", "#1c2b5a", ("#1c2b5a", "#ffd479", "#7fb2ff")),
    "radar": ("Radar", "#02100a", ("#041407", "#00ff55", "#d6ff3b")),
    "terminal": ("Terminal", "#0a120b", ("#0f1a10", "#b6f2a0", "#f5d76e")),
    "piksel": ("Piksel", "#0f380f", ("#9bbc0f", "#306230", "#0f380f")),
    "laboratuvar": ("Laboratuvar", "#0a1118", ("#0d151c", "#00e5ff", "#b537f2")),
    "kaset": ("Kaset", "#0f0f13", ("#141318", "#ff2a85", "#ffee00")),
    "pusula": ("Pusula", "#1a4254", ("#f4edd7", "#b8860b", "#1a4254")),
    "nakis": ("Nakış", "#5b4033", ("#f4ecdc", "#c9574a", "#d8a13e")),
}


def gecerli(kod: str) -> bool:
    return kod in TEMALAR


def kaydet(conn: sqlite3.Connection, kullanici_id: int, kod: str) -> None:
    conn.execute(
        "INSERT INTO kullanici_tema (kullanici_id, tema) VALUES (?, ?)"
        " ON CONFLICT(kullanici_id) DO UPDATE SET tema = excluded.tema",
        (kullanici_id, kod),
    )
    conn.commit()
