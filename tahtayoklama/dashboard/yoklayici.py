"""Polling motoru — tüm tahtaları eşzamanlı tarar, sonuçları içerikteki
`sinif` alanına göre birleştirir (tahta kimliğine göre DEĞİL — bkz.
CLAUDE.md "kayıt tahta kimliğine değil, o an seçili sınıfa göre
isimlendirilir"), ve yoklama_onbellek tablosuna yazar.
"""

import asyncio
import json
from datetime import date

import ssh_istemci
import zil

# Tahta istemcisinden (tahta_istemci.py, bkz. tahta_api.py) son nabız bu
# kadar yeniyse tahta "erişilebilir" sayılır ve kısmi turda SSH ile
# taranmaz — kayıtlar zaten anında itiliyor. Nabız bayatlarsa (istemci
# çöktü/kurulu değil) tahta otomatik olarak SSH taramasına geri döner.
NABIZ_TAZE_SN = 300

# yoklama.py'nin ürettiği durum alanları -> pano'nun sunduğu isimler
_YOK = "yok"
_IZINLI = "izinli"


async def _tahtayi_tara(tahta: dict, tarih: str) -> tuple[dict, bool]:
    """Bir tahtanın o günkü tüm kayıtlarını getirir.
    Döner: (kayitlar: {(sinif, ders_no): kayit_dict}, ulasilabilir: bool)."""
    sonuc = await ssh_istemci.tahtanin_kayitlarini_tara(
        tahta["ip"], tahta["ssh_kullanici"], tarih
    )
    if not sonuc.basarili:
        return {}, False

    try:
        dosyalar = json.loads(sonuc.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Tahta cevap verdi ama beklenmedik çıktı üretti — erişilemez değil,
        # ama okunabilir veri de yok. Boş sonuçla devam, tahtayı erişilebilir say.
        return {}, True

    kayitlar: dict[tuple[str, int], dict] = {}
    for dosya_adi, icerik in dosyalar.items():
        if "_hata" in icerik:
            continue
        sinif = icerik.get("sinif")
        ders_no = icerik.get("ders_no")
        if sinif is None or ders_no is None:
            continue
        icerik["_kaynak_tahta"] = tahta["ad"]
        anahtar = (sinif, ders_no)
        mevcut = kayitlar.get(anahtar)
        if mevcut is None or icerik.get("kaydedilme_saati", "") >= mevcut.get(
            "kaydedilme_saati", ""
        ):
            kayitlar[anahtar] = icerik
    return kayitlar, True


def _yok_isimlerini_coz(kayit: dict, roster_by_no: dict[str, str], hedef_durum: str) -> list[str]:
    isimler = []
    for no, durum in kayit.get("durumlar", {}).items():
        if durum == hedef_durum:
            isimler.append(roster_by_no.get(no, f"No {no}"))
    return isimler


def onbellege_yaz(conn, tarih: str, sinif_adi: str, ders_no: int, durum: str,
                  yok_isimleri: list[str], izinli_isimleri: list[str],
                  kaynak_tahta: str | None, kaydedilme_saati: str | None) -> None:
    """yoklama_onbellek'e TEK yazma yolu — hem SSH polling'i hem tahta
    istemcisinin itmesi (tahta_api.py) bunu kullanır (iki kopya senkron
    kalmasın diye)."""
    conn.execute(
        """
        INSERT INTO yoklama_onbellek
            (tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri,
             kaynak_tahta, kaydedilme_saati, guncelleme_zamani)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(tarih, sinif, ders_no) DO UPDATE SET
            durum = excluded.durum,
            yok_isimleri = excluded.yok_isimleri,
            izinli_isimleri = excluded.izinli_isimleri,
            kaynak_tahta = excluded.kaynak_tahta,
            kaydedilme_saati = excluded.kaydedilme_saati,
            guncelleme_zamani = datetime('now')
        -- Bir kez 'alindi' olmuş satır YALNIZCA yeni bir 'alindi'
        -- kaydıyla güncellenir. Tahta bu turda kapalı/erişilemez
        -- olduğu için kayıt görülmemesi, daha önce okunmuş gerçek
        -- yoklamayı SİLMEZ (bkz. 2026-09-14 / 9-B olayı). 'alindi' üstüne
        -- 'alindi' ise yalnızca kaydedilme_saati KESİN DAHA YENİYSE yazılır:
        -- sırası karışmış bir yeniden deneme ya da aynı dersi kaydeden
        -- ikinci tahta (fenlab) yeni kaydı eskisiyle ezmesin; AYNI kayıt
        -- yeniden gelirse (istemcinin geçmiş günleri göndermesi) isimler
        -- bugünkü roster'a göre yeniden çözülüp tarihsel satır bozulmasın —
        -- 2026-10-06'da 9-A'dan çıkarılan bir öğrenci eski satırlarda
        -- "No 204"e dönüştü, bu yüzden >= yerine >.
        WHERE (excluded.durum = 'alindi' AND (
                  yoklama_onbellek.durum <> 'alindi'
                  OR COALESCE(excluded.kaydedilme_saati, '')
                     > COALESCE(yoklama_onbellek.kaydedilme_saati, '')))
           OR (excluded.durum <> 'alindi' AND yoklama_onbellek.durum <> 'alindi')
        """,
        (
            tarih, sinif_adi, ders_no, durum,
            json.dumps(yok_isimleri, ensure_ascii=False),
            json.dumps(izinli_isimleri, ensure_ascii=False),
            kaynak_tahta, kaydedilme_saati,
        ),
    )


def _roster_by_no(conn, sinif_id: int) -> dict[str, str]:
    return {
        str(r["no"]): r["ad_soyad"]
        for r in conn.execute(
            "SELECT no, ad_soyad FROM ogrenciler WHERE sinif_id = ? AND aktif = 1",
            (sinif_id,),
        )
    }


def itilen_kaydi_yaz(conn, kayit: dict, kaynak_tahta: str) -> bool:
    """Tahta istemcisinin ittiği (önceden doğrulanmış) tek bir yoklama
    kaydını önbelleğe 'alindi' olarak yazar. Sınıf aktif değilse False —
    tahta↔sınıf eşlemesine BAKILMAZ (kayıt içeriğindeki `sinif` esas, bkz.
    modül docstring'i; fenlab her sınıfı kaydedebilir)."""
    sinif = conn.execute(
        "SELECT id FROM siniflar WHERE ad = ? AND aktif = 1", (kayit["sinif"],)
    ).fetchone()
    if sinif is None:
        return False
    # GEÇMİŞ GÜNÜN 'alindi' satırına ASLA yazılmaz (2026-10-06). yoklama.py
    # yalnızca O ANKİ dersi kaydettirir; geçmiş tarihli farklı bir kayıt
    # meşru bir düzeltme olamaz, saati yanlış açılan tahtadan gelir (10-A:
    # CMOS pili bitik, açılışta son kapanış saatiyle başlıyor → "dün 5. ders"
    # sanıp gerçek kaydın üstüne yazardı). Geçmiş gün için yalnızca HİÇ
    # görülmemiş kayıt eklenir (tahta o gün kapalıyken alınmış yoklama).
    if kayit["tarih"] < zil.simdi_istanbul().date().isoformat():
        mevcut = conn.execute(
            "SELECT durum FROM yoklama_onbellek WHERE tarih = ? AND sinif = ? AND ders_no = ?",
            (kayit["tarih"], kayit["sinif"], kayit["ders_no"]),
        ).fetchone()
        if mevcut is not None and mevcut["durum"] == "alindi":
            return True
    roster = _roster_by_no(conn, sinif["id"])
    onbellege_yaz(
        conn, kayit["tarih"], kayit["sinif"], kayit["ders_no"], "alindi",
        _yok_isimlerini_coz(kayit, roster, _YOK),
        _yok_isimlerini_coz(kayit, roster, _IZINLI),
        kaynak_tahta, kayit.get("kaydedilme_saati"),
    )
    conn.commit()
    return True


def _taze_nabizli_tahtalar(conn) -> set[str]:
    return {
        r["tahta_ad"] for r in conn.execute(
            "SELECT tahta_ad FROM tahta_nabiz WHERE son_gorulme >= datetime('now', ?)",
            (f"-{NABIZ_TAZE_SN} seconds",),
        )
    }


async def bir_tur_calistir(conn, tarih: str, tam_tarama: bool = True) -> None:
    """Verilen tarih için tek bir polling turu çalıştırır, sonucu
    yoklama_onbellek'e yazar. UI'dan /api/yenile ile veya arka plan
    döngüsünden çağrılır.

    tam_tarama=False (arka plan döngüsünün çoğu turu): nabzı taze olan
    tahtalar SSH ile TARANMAZ, erişilebilir sayılır — kayıtları istemci
    zaten itiyor. Durum geçişleri (henuz_baslamadi → alinmadi) yine her
    turda hesaplanır, yani panonun güncelliği SSH'e bağlı değil."""
    ssh_istemci.tarih_dogrula(tarih)
    hedef_tarih = date.fromisoformat(tarih)
    bugun = zil.simdi_istanbul().date()

    tahtalar = [dict(r) for r in conn.execute(
        "SELECT id, ad, ip, ssh_kullanici, sinif_id FROM tahtalar WHERE aktif = 1"
    )]
    siniflar = [dict(r) for r in conn.execute(
        "SELECT id, ad FROM siniflar WHERE aktif = 1"
    )]
    taze = _taze_nabizli_tahtalar(conn) if hedef_tarih == bugun else set()

    # sinif_id -> en az bir tahtaya atanmış mı, atanan tahtalardan en az biri
    # bu turda erişilebilir miydi?
    sinif_id_to_tahta_adlari: dict[int, list[str]] = {}
    for t in tahtalar:
        if t["sinif_id"] is not None:
            sinif_id_to_tahta_adlari.setdefault(t["sinif_id"], []).append(t["ad"])

    taranacak = [t for t in tahtalar if tam_tarama or t["ad"] not in taze]
    sonuclar = await asyncio.gather(
        *(_tahtayi_tara(t, tarih) for t in taranacak)
    )
    tahta_erisilebilir: dict[str, bool] = {ad: True for ad in taze}
    for t, (_, ulasilabilir) in zip(taranacak, sonuclar):
        tahta_erisilebilir[t["ad"]] = ulasilabilir or t["ad"] in taze

    # (sinif, ders_no) -> kayıt, tüm tahtalardan birleştirilmiş (içerik esas).
    birlesik: dict[tuple[str, int], dict] = {}
    for kayitlar, _ulasilabilir in sonuclar:
        for anahtar, kayit in kayitlar.items():
            mevcut = birlesik.get(anahtar)
            if mevcut is None or kayit.get("kaydedilme_saati", "") >= mevcut.get(
                "kaydedilme_saati", ""
            ):
                birlesik[anahtar] = kayit

    simdi = zil.simdi_istanbul().time() if hedef_tarih == bugun else None

    for sinif in siniflar:
        sinif_adi = sinif["ad"]
        sinif_id = sinif["id"]
        roster_by_no = _roster_by_no(conn, sinif_id)

        for ders in zil.ders_saatleri():
            ders_no = ders["no"]
            kayit = birlesik.get((sinif_adi, ders_no))

            if kayit is not None:
                durum = "alindi"
                yok_isimleri = _yok_isimlerini_coz(kayit, roster_by_no, _YOK)
                izinli_isimleri = _yok_isimlerini_coz(kayit, roster_by_no, _IZINLI)
                kaynak_tahta = kayit.get("_kaynak_tahta")
                kaydedilme_saati = kayit.get("kaydedilme_saati")
            else:
                yok_isimleri, izinli_isimleri = [], []
                kaynak_tahta, kaydedilme_saati = None, None

                if not zil.okul_gunu_mu(hedef_tarih):
                    durum = "ders_yok_o_gun"
                elif sinif_id not in sinif_id_to_tahta_adlari:
                    durum = "tahta_atanmamis"
                elif not any(
                    tahta_erisilebilir.get(ad, False)
                    for ad in sinif_id_to_tahta_adlari[sinif_id]
                ):
                    durum = "tahta_ulasilamaz"
                elif hedef_tarih != bugun:
                    durum = "alinmadi"
                else:
                    gecen = zil.gecen_dk(ders_no, simdi)
                    if gecen is None or gecen < 0:
                        durum = "henuz_baslamadi"
                    elif gecen < zil.UYARI_ESIGI_DK:
                        durum = "henuz_baslamadi"
                    else:
                        durum = "alinmadi"

            onbellege_yaz(
                conn, tarih, sinif_adi, ders_no, durum, yok_isimleri,
                izinli_isimleri, kaynak_tahta, kaydedilme_saati,
            )
    conn.commit()
