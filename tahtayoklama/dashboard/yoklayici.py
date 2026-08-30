"""Polling motoru — tüm tahtaları eşzamanlı tarar, sonuçları içerikteki
`sinif` alanına göre birleştirir (tahta kimliğine göre DEĞİL — bkz.
CLAUDE.md "kayıt tahta kimliğine değil, o an seçili sınıfa göre
isimlendirilir"), ve yoklama_onbellek tablosuna yazar.
"""

import json
from datetime import date

import ssh_istemci
import zil

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


async def bir_tur_calistir(conn, tarih: str) -> None:
    """Verilen tarih için tek bir polling turu çalıştırır, sonucu
    yoklama_onbellek'e yazar. UI'dan /api/yenile ile veya arka plan
    döngüsünden çağrılır."""
    ssh_istemci.tarih_dogrula(tarih)
    hedef_tarih = date.fromisoformat(tarih)
    bugun = zil.simdi_istanbul().date()

    tahtalar = [dict(r) for r in conn.execute(
        "SELECT id, ad, ip, ssh_kullanici, sinif_id FROM tahtalar WHERE aktif = 1"
    )]
    siniflar = [dict(r) for r in conn.execute(
        "SELECT id, ad FROM siniflar WHERE aktif = 1"
    )]

    # sinif_id -> en az bir tahtaya atanmış mı, atanan tahtalardan en az biri
    # bu turda erişilebilir miydi?
    sinif_id_to_tahta_adlari: dict[int, list[str]] = {}
    for t in tahtalar:
        if t["sinif_id"] is not None:
            sinif_id_to_tahta_adlari.setdefault(t["sinif_id"], []).append(t["ad"])

    # Tüm tahtaları eşzamanlı tara.
    import asyncio

    sonuclar = await asyncio.gather(
        *(_tahtayi_tara(t, tarih) for t in tahtalar)
    )
    tahta_erisilebilir: dict[str, bool] = {
        t["ad"]: ulasilabilir for t, (_, ulasilabilir) in zip(tahtalar, sonuclar)
    }

    # (sinif, ders_no) -> kayıt, tüm tahtalardan birleştirilmiş (içerik esas).
    birlesik: dict[tuple[str, int], dict] = {}
    for _, (kayitlar, _ulasilabilir) in zip(tahtalar, sonuclar):
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
        roster_by_no = {
            str(r["no"]): r["ad_soyad"]
            for r in conn.execute(
                "SELECT no, ad_soyad FROM ogrenciler WHERE sinif_id = ? AND aktif = 1",
                (sinif_id,),
            )
        }

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
                """,
                (
                    tarih, sinif_adi, ders_no, durum,
                    json.dumps(yok_isimleri, ensure_ascii=False),
                    json.dumps(izinli_isimleri, ensure_ascii=False),
                    kaynak_tahta, kaydedilme_saati,
                ),
            )
    conn.commit()
