"""Yaklaşan deneme sınavlarını (ör. MEBİ YKS) teneffüste tahtada hatırlatır (2026-11-01).

Kaynak okul portalının sınav takvimidir: `http://127.0.0.1:9090/api/pano` →
`yaklasan_denemeler` (okul/sinavlar.py::yaklasan_denemeler; başlangıca 3 gün kala → hafta
bitene kadar). Dashboard okul.db'yi açmaz, tarih tutmaz.

Okul günü iki yuvada (zil.json'dan): ilk teneffüs (1. ders bitişi) ve öğle arası başı.
Yuvanın ilk YUVA_DK dakikasında bir kez, denemenin düzeyindeki sınıfların tahtalarına
`bilgi` duyurusu (mavi, sessiz, 10 sn) yazılır. Aynı mesaj+hedef son 30 dakikada yazıldıysa
atlanır (restart'ta tekrar çıkmaz). Her hata loglanıp yutulur (Farabi dersi bozmaz).
"""

import asyncio
import json
import logging
import urllib.request
from datetime import datetime
from datetime import time as dtime

import db
import duyuru
import zil

log = logging.getLogger("deneme_hatirlatma")

PANO_URL = "http://127.0.0.1:9090/api/pano"
ARALIK_SN = 60
YUVA_DK = 5


def yuvalar() -> list[dtime]:
    """İlk teneffüs başı + öğle arası başı (zil.json'da yoksa o yuva atlanır)."""
    sonuc = []
    dersler = zil.ders_saatleri()
    if dersler:
        sonuc.append(zil._saat_ayristir(dersler[0]["bitis"]))
    ogle = zil._zil_yukle().get("ogle_arasi") or {}
    if ogle.get("baslangic"):
        sonuc.append(zil._saat_ayristir(ogle["baslangic"]))
    return sonuc


def yuvada_mi(simdi: datetime) -> bool:
    if not zil.okul_gunu_mu(simdi.date()):
        return False
    dk = simdi.hour * 60 + simdi.minute
    return any(0 <= dk - (y.hour * 60 + y.minute) < YUVA_DK for y in yuvalar())


def denemeleri_cek() -> list[dict]:
    with urllib.request.urlopen(PANO_URL, timeout=5) as yanit:
        return json.loads(yanit.read()).get("yaklasan_denemeler") or []


def _hedefler(conn, duzeyler: str) -> list[str]:
    """Denemenin düzeyindeki aktif sınıflar ("11,12" → 11-A, 11-B, ...; boş = tüm okul)."""
    if not duzeyler:
        return [duyuru.TUM_OKUL]
    istenen = set(duzeyler.split(","))
    return [
        r["ad"] for r in conn.execute("SELECT ad FROM siniflar WHERE aktif = 1 ORDER BY ad")
        if r["ad"].split("-")[0] in istenen
    ]


def gonder(conn, denemeler: list[dict]) -> int:
    """Her deneme için hedeflere duyuru yazar; son 30 dk'da yazılmış olanı atlar. Dönen: yazılan satır."""
    yazilan = 0
    for d in denemeler:
        try:
            mesaj = duyuru.mesaj_temizle(
                f"{d['baslik']}: {d['durum']}" + (f" — {d['aciklama']}" if d.get("aciklama") else "")
            )
        except duyuru.DuyuruHatasi:
            continue
        hedefler = [
            h for h in _hedefler(conn, d.get("duzeyler") or "")
            if conn.execute(
                "SELECT 1 FROM duyuru WHERE hedef = ? AND mesaj = ? "
                "AND olusturma > datetime('now', '-30 minutes')", (h, mesaj),
            ).fetchone() is None
        ]
        if hedefler:
            yazilan += len(duyuru.olustur(conn, hedefler, mesaj, "bilgi", False, None))
    return yazilan


async def dongu() -> None:
    while True:
        try:
            if yuvada_mi(zil.simdi_istanbul()):
                denemeler = await asyncio.to_thread(denemeleri_cek)
                if denemeler:
                    conn = db.baglanti()
                    try:
                        gonder(conn, denemeler)
                    finally:
                        conn.close()
        except Exception as e:  # noqa: BLE001 — hatırlatma dashboard'u asla düşürmemeli
            log.warning("deneme hatırlatma hatası: %s", type(e).__name__)
        await asyncio.sleep(ARALIK_SN)
