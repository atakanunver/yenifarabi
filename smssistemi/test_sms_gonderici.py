"""sms_gonderici.py::toplu_gonder birim testleri.

2026-09-28 kök neden: Müdür PC proxy'si (WifiHttpProxy) düşünce `_baglan`
başarısız oluyor, eskiden TEK bir boş ("", "", "") "hata" satırı yazılıyordu
— telefon boş olduğu için `db.gonderim_basarisizlari` (telefon != '' filtresi)
bu satırı asla /tekrar-gonder ile yeniden deneyemiyordu ve 8 alıcı hiç
kaydedilmemiş oluyordu. Bu testler her alıcının kendi isim/telefon/mesajıyla
kaydedildiğini doğruluyor.
"""

from threading import Event
from unittest.mock import MagicMock

import sms_gonderici


def _bos_bayrak() -> Event:
    return Event()  # hiç set edilmez — "durdur" tetiklenmez


def test_baglanti_hatasinda_her_alici_kendi_bilgisiyle_hata_kaydedilir(monkeypatch):
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: (_ for _ in ()).throw(
        RuntimeError("proxy erişilemedi")
    ))

    kisiler = [
        ("Fatma Kaya", "05321112233", "merhaba 1"),
        # Kardeşler aynı telefonu paylaşabilir — indeksle takip edilmeli, telefonla değil.
        ("Mehmet Kaya", "05321112233", "merhaba 2"),
        ("Ayşe Demir", "05323334455", "merhaba 3"),
    ]
    kaydedilenler = []

    def callback(isim, telefon, mesaj, durum, hata_metni):
        kaydedilenler.append((isim, telefon, mesaj, durum, hata_metni))

    sms_gonderici.toplu_gonder(ayarlar={}, kisiler=kisiler, sonuc_callback=callback,
                                durdur_bayragi=_bos_bayrak(), bekleme_sn=0)

    assert len(kaydedilenler) == 3
    for (isim, telefon, mesaj, durum, hata_metni), kaynak in zip(kaydedilenler, kisiler):
        assert isim == kaynak[0]
        assert telefon == kaynak[1]
        assert mesaj == kaynak[2]
        assert durum == "hata"
        assert hata_metni == "BAĞLANTI HATASI: proxy erişilemedi"


def test_baglanti_hatasinda_bos_kisi_listesi_callback_cagirmaz(monkeypatch):
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: (_ for _ in ()).throw(
        RuntimeError("proxy erişilemedi")
    ))
    cagrildi = []
    sms_gonderici.toplu_gonder(ayarlar={}, kisiler=[], sonuc_callback=lambda *a: cagrildi.append(a),
                                durdur_bayragi=_bos_bayrak(), bekleme_sn=0)
    assert cagrildi == []


class _SahteBaglanti:
    def __init__(self, cikiste_hata: Exception | None = None):
        self._cikiste_hata = cikiste_hata

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if self._cikiste_hata is not None:
            raise self._cikiste_hata
        return False


def test_gonderim_sirasinda_baglanti_koparsa_islenmemis_aliciler_hata_kaydedilir(monkeypatch):
    """2. alıcıda (is_ascii çağrısında) bağlantı hatası simüle edilir —
    1. alıcı zaten kendi sonuc_callback'iyle kaydedilmiş olmalı (çift
    kayıt YOK), 2. ve 3. alıcılar 'gönderim sırasında' hatasıyla kaydedilir."""
    kisiler = [
        ("Ali Veli", "05321112233", "merhaba 1"),
        ("Can Demir", "05322223344", "merhaba 2"),
        ("Ece Yıldız", "05323334455", "merhaba 3"),
    ]
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: _SahteBaglanti())
    sahte_client = MagicMock()
    sahte_client.sms.send_sms.return_value = None
    monkeypatch.setattr(sms_gonderici, "Client", lambda conn: sahte_client)

    cagri_sayaci = {"n": 0}

    def sahte_is_ascii(mesaj):
        cagri_sayaci["n"] += 1
        if cagri_sayaci["n"] == 2:
            raise RuntimeError("bağlantı koptu")
        return True

    monkeypatch.setattr(sms_gonderici, "is_ascii", sahte_is_ascii)

    kaydedilenler = []
    sms_gonderici.toplu_gonder(
        ayarlar={}, kisiler=kisiler,
        sonuc_callback=lambda isim, tel, msg, durum, hata: kaydedilenler.append((isim, tel, msg, durum, hata)),
        durdur_bayragi=_bos_bayrak(), bekleme_sn=0,
    )

    assert len(kaydedilenler) == 3  # hiçbiri kayıpsız ya da çift kayıtlı değil
    assert kaydedilenler[0] == ("Ali Veli", "05321112233", "merhaba 1", "gonderildi", None)
    assert kaydedilenler[1] == (
        "Can Demir", "05322223344", "merhaba 2", "hata",
        "BAĞLANTI HATASI (gönderim sırasında): bağlantı koptu",
    )
    assert kaydedilenler[2] == (
        "Ece Yıldız", "05323334455", "merhaba 3", "hata",
        "BAĞLANTI HATASI (gönderim sırasında): bağlantı koptu",
    )


def test_durdurma_sonrasi_cikis_hatasi_kalan_alicilari_kaydetmez():
    """DURDUR'a basılıp `with connection:` çıkışında da hata olursa (ör.
    modemden logout isteği aynı kopuk proxy'den geçmeye çalışır), durdurma
    davranışı korunmalı — henüz işlenmemiş alıcılar kayıtsız kalmalı."""
    kisiler = [
        ("Ali Veli", "05321112233", "merhaba 1"),
        ("Can Demir", "05322223344", "merhaba 2"),
    ]
    import sms_gonderici as sg
    baglanti = _SahteBaglanti(cikiste_hata=RuntimeError("cikis hatasi"))

    sahte_client = MagicMock()
    durdur_bayragi = Event()

    def sahte_send_sms(tel, msg, text_mode=None):
        durdur_bayragi.set()  # ilk SMS gönderildikten sonra DURDUR'a basıldı

    sahte_client.sms.send_sms.side_effect = sahte_send_sms

    import unittest.mock as mock
    with mock.patch.object(sg, "_baglan", lambda ayarlar: baglanti), \
         mock.patch.object(sg, "Client", lambda conn: sahte_client):
        kaydedilenler = []
        sg.toplu_gonder(
            ayarlar={}, kisiler=kisiler,
            sonuc_callback=lambda isim, tel, msg, durum, hata: kaydedilenler.append((isim, tel, msg, durum, hata)),
            durdur_bayragi=durdur_bayragi, bekleme_sn=0,
        )

    # Yalnızca ilk alıcı kaydedildi (gönderildi); ikinci alıcı DURDUR
    # yüzünden hiç işlenmedi, çıkış hatası yüzünden de "hata" olarak
    # eklenmemeli.
    assert len(kaydedilenler) == 1
    assert kaydedilenler[0][0] == "Ali Veli"
    assert kaydedilenler[0][3] == "gonderildi"


# --- 2026-10-14: giden kutusu temizliği + modem kilidi -------------------

def _sahte_client_kurulumu(monkeypatch, giden_sayfalari):
    from unittest.mock import MagicMock
    client = MagicMock()
    client.sms.get_sms_list.side_effect = giden_sayfalari
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: MagicMock())
    monkeypatch.setattr(sms_gonderici, "Client", lambda c: client)
    return client


def test_toplu_gonder_sonunda_yalniz_giden_kutusu_temizlenir(monkeypatch):
    from huawei_lte_api.enums.sms import BoxTypeEnum
    sayfalar = [{"Messages": {"Message": [{"Index": "10"}, {"Index": "11"}]}}, {"Messages": {"Message": []}}]
    client = _sahte_client_kurulumu(monkeypatch, sayfalar)
    kayit = []
    sms_gonderici.toplu_gonder({}, [("A", "05550000001", "mesaj")], lambda *a: kayit.append(a),
                               _bos_bayrak(), 0)
    assert kayit[0][3] == "gonderildi"
    assert [c.args[0] for c in client.sms.delete_sms.call_args_list] == [10, 11]
    for c in client.sms.get_sms_list.call_args_list:
        assert c.kwargs["box_type"] == BoxTypeEnum.LOCAL_SENT  # gelen kutusuna dokunulmaz


def test_silme_hatasi_gonderimi_bozmaz(monkeypatch):
    client = _sahte_client_kurulumu(monkeypatch, [RuntimeError("modem")])
    kayit = []
    sms_gonderici.toplu_gonder({}, [("A", "05550000001", "mesaj")], lambda *a: kayit.append(a),
                               _bos_bayrak(), 0)
    assert [k[3] for k in kayit] == ["gonderildi"]  # hata kaydı eklenmedi
    client.sms.delete_sms.assert_not_called()


def test_toplu_gonder_modem_kilidini_tutar(monkeypatch):
    import threading
    gorulen = []

    def sahte_baglan(ayarlar):
        gorulen.append(sms_gonderici.modem_kilidi.acquire(blocking=False))  # RLock: aynı thread ise True
        raise RuntimeError("x")

    monkeypatch.setattr(sms_gonderici, "_baglan", sahte_baglan)
    # Başka thread'den bakınca kilit alınamamalı
    sonuc = []

    def baska_thread_denesin(*a):
        t = threading.Thread(target=lambda: sonuc.append(sms_gonderici.modem_kilidi.acquire(blocking=False)))
        t.start(); t.join()

    sms_gonderici.toplu_gonder({}, [("A", "05550000001", "m")], baska_thread_denesin, _bos_bayrak(), 0)
    assert sonuc == [False]
    assert sms_gonderici.modem_kilidi.acquire(blocking=False)  # bitince serbest
    sms_gonderici.modem_kilidi.release()


def test_gelen_kutusu_turu_giden_kutusu_artiklarini_da_siler(monkeypatch):
    """Modem gönderilen mesajı gecikmeyle yazar; poller turu artığı süpürür."""
    import sms_gonderici

    silinenler = []

    class _Sms:
        def get_sms_list(self, page=1, box_type=None, read_count=50, **kw):
            if box_type == sms_gonderici.BoxTypeEnum.LOCAL_SENT and not silinenler:
                return {"Messages": {"Message": [{"Index": "40000", "SmsType": "1"}]}, "Count": "1"}
            return {"Messages": None, "Count": "0"}

        def delete_sms(self, index):
            silinenler.append(index)

    class _Client:
        sms = _Sms()

    class _Baglanti:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: _Baglanti())
    monkeypatch.setattr(sms_gonderici, "Client", lambda c: _Client())
    assert sms_gonderici.gelen_kutusunu_isle({}, lambda m: []) == 0
    assert silinenler == [40000]
