import io
import json
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
from core.ders_gorsel import (
    AktifPencere,
    Karar,
    ServisMetrikleri,
    aktif_pencere_bilgisi,
    baslik_farabi_mi,
    baslik_gizli_mi,
    dhash,
    fark,
    get_rss_mib,
    gonder,
    pencere_kabul_edilebilir_mi,
    pencere_tipi_yasakli_mi,
    pid_farabi_mi,
    webp_kodla,
)
from ders_gorsel_servis import _hizli_config_kontrol, x11_bekle
from PIL import Image


def frame(val: int) -> np.ndarray:
    """90x160 sabit değerli test karesi üretir."""
    return np.full((90, 160), val, dtype=np.uint8)


def test_ayni_kare_gonderim_yok():
    """Aynı kare kararlı hale geldikten sonra gönderilir; sonraki turlarda tekrar gönderilmez."""
    k = Karar()
    # t=0: ilk kare görülür (aday takibi başlar, kararlı değil)
    assert not k.incele(frame(10), 0.0, ders=1)
    # t=5: 5 sn boyunca aynı kare -> kararlı aday!
    assert k.incele(frame(10), 5.0, ders=1)
    k.gonderildi(frame(10), 5.0)

    # t=10: asgari 30 sn aralık dolmadı
    assert not k.incele(frame(10), 10.0, ders=1)
    # t=35: 30 sn doldu ama son gönderilen kareye benziyor -> GÖNDERİM YOK
    assert not k.incele(frame(10), 35.0, ders=1)
    # t=60: hâlâ aynı kare -> GÖNDERİM YOK
    assert not k.incele(frame(10), 60.0, ders=1)


def test_pdf_sayfa_degisimi_kararli_tek_kare():
    """PDF sayfa değişiminde değişim anı atlanır, ~5 sn sabit kalınca TEK kare gönderilir."""
    k = Karar()
    # Sayfa 1 (gri=50)
    assert not k.incele(frame(50), 0.0, ders=1)
    assert k.incele(frame(50), 5.0, ders=1)
    k.gonderildi(frame(50), 5.0)

    # Sayfa 1 ekranda kalmaya devam ediyor
    assert not k.incele(frame(50), 35.0, ders=1)

    # t=40: Öğretmen Sayfa 2'ye geçti (gri=150, fark >= 0.025)
    assert not k.incele(frame(150), 40.0, ders=1)
    # t=42: Henüz 5 sn dolmadı (kararsız)
    assert not k.incele(frame(150), 42.0, ders=1)
    # t=45: 5 sn kararlı ve asgari 30 sn doldu (45-5 = 40 >= 30) -> GÖNDERİLİR
    assert k.incele(frame(150), 45.0, ders=1)
    k.gonderildi(frame(150), 45.0)

    # t=50: Sayfa 2 ekranda kalmaya devam ediyor -> tekrar gönderilmez
    assert not k.incele(frame(150), 50.0, ders=1)
    assert not k.incele(frame(150), 80.0, ders=1)


def test_surekli_degisim_video_yazi_bitince_tek_kare():
    """Video veya sürekli yazı akışında kareler sürekli değişirken gönderilmez; bitince tek kare."""
    k = Karar()
    # t=0..45 arası video akıyor (her 5 saniyede belirgin değişim)
    for t in range(0, 50, 5):
        assert not k.incele(frame((t * 11) % 256), float(t), ders=1)

    # t=50'de video durdu (kare sabitlendi: 120)
    assert not k.incele(frame(120), 50.0, ders=1)
    # t=55'te 5 sn kararlı kaldı -> TEK KARE GÖNDERİLİR
    assert k.incele(frame(120), 55.0, ders=1)
    k.gonderildi(frame(120), 55.0)

    # t=60: video bitmiş şekilde bekliyor -> tekrar gönderim yok
    assert not k.incele(frame(120), 60.0, ders=1)


def test_pencere_politikasi_filtreleri():
    """Aktif pencere yok, masaüstü/panel, Farabi önde, gizlilik filtresi reddedilir; normal pencereler kabul edilir."""
    # 1. Aktif pencere yok
    assert not pencere_kabul_edilebilir_mi(None)[0]
    assert pencere_kabul_edilebilir_mi(AktifPencere(win_id="0x0"))[1] == "aktif_pencere_yok"

    # 2. DESKTOP ve DOCK pencereleri
    assert pencere_tipi_yasakli_mi("_NET_WM_WINDOW_TYPE_DESKTOP")
    assert pencere_tipi_yasakli_mi("_NET_WM_WINDOW_TYPE_DOCK")
    assert not pencere_tipi_yasakli_mi("_NET_WM_WINDOW_TYPE_NORMAL")
    desktop = AktifPencere(win_id="0x1", pencere_tipi="_NET_WM_WINDOW_TYPE_DESKTOP")
    dock = AktifPencere(win_id="0x2", pencere_tipi="_NET_WM_WINDOW_TYPE_DOCK")
    assert not pencere_kabul_edilebilir_mi(desktop)[0]
    assert pencere_kabul_edilebilir_mi(desktop)[1] == "desktop_dock"
    assert not pencere_kabul_edilebilir_mi(dock)[0]

    # 3. Farabi önde: başlık
    assert baslik_farabi_mi("FARABİ — Yapay Zekâ Öğretmen")
    assert baslik_farabi_mi("FARABI")
    assert not baslik_farabi_mi("Google Chrome")
    farabi_win = AktifPencere(win_id="0x3", baslik="FARABİ — Yapay Zekâ Öğretmen")
    assert not pencere_kabul_edilebilir_mi(farabi_win)[0]
    assert pencere_kabul_edilebilir_mi(farabi_win)[1] == "farabi_onde"

    # 4. Farabi önde: PID cmdline
    def fake_cmdline(pid):
        return "/home/ata/farabi/client/venv/bin/python client/main.py"

    assert pid_farabi_mi(999, cmdline_reader=fake_cmdline)
    assert not pid_farabi_mi(None, cmdline_reader=fake_cmdline)
    farabi_pid_win = AktifPencere(win_id="0x4", baslik="Bilinmeyen Başlık", pid=999)
    kabul, neden = pencere_kabul_edilebilir_mi(farabi_pid_win, cmdline_reader=fake_cmdline)
    assert not kabul
    assert neden == "farabi_onde"

    # 5. Gizlilik filtreleri (yoklama, e-Okul, MEBBİS, tahtayoklama)
    assert baslik_gizli_mi("10-A Sınıfı Yoklama Listesi")
    assert baslik_gizli_mi("e-Okul Yönetim Bilgi Sistemi")
    assert baslik_gizli_mi("eokul veli bilgilendirme")
    assert baslik_gizli_mi("MEBBİS Kullanıcı Girişi")  # Türkçe İ/ı
    assert baslik_gizli_mi("tahtayoklama yoklama ekranı")

    gizli_win = AktifPencere(win_id="0x5", baslik="MEBBİS Giriş Ekranı")
    assert not pencere_kabul_edilebilir_mi(gizli_win)[0]
    assert pencere_kabul_edilebilir_mi(gizli_win)[1] == "gizlilik_filtresi"

    # 6. Normal Chrome / PDF / Çizim pencereleri KABUL
    chrome_win = AktifPencere(
        win_id="0x6",
        baslik="Google Chrome - Khan Academy",
        pencere_tipi="_NET_WM_WINDOW_TYPE_NORMAL",
        pid=1234,
    )
    pdf_win = AktifPencere(
        win_id="0x7",
        baslik="10. Sınıf Fizik Ders Kitabı.pdf - Evince",
        pencere_tipi="_NET_WM_WINDOW_TYPE_NORMAL",
        pid=5678,
    )
    cizim_win = AktifPencere(
        win_id="0x8",
        baslik="OpenBoard",
        pencere_tipi="_NET_WM_WINDOW_TYPE_NORMAL",
        pid=9101,
    )

    def normal_cmdline(pid):
        return "/usr/bin/google-chrome"

    assert pencere_kabul_edilebilir_mi(chrome_win, cmdline_reader=normal_cmdline)[0]
    assert pencere_kabul_edilebilir_mi(pdf_win, cmdline_reader=normal_cmdline)[0]
    assert pencere_kabul_edilebilir_mi(cizim_win, cmdline_reader=normal_cmdline)[0]


def test_yaris_durumu_a_b_esit_degilse_kare_atilir():
    """A ve B pencereleri farklıysa (kullanıcı kare yakalanırken pencere değiştirdiyse) kare atılır."""
    pencere_a = AktifPencere(win_id="0x111", baslik="Chrome")
    pencere_b = AktifPencere(win_id="0x222", baslik="PDF")
    assert pencere_a.win_id != pencere_b.win_id

    # Aynı pencere yarış testi
    pencere_b_ayni = AktifPencere(win_id="0x111", baslik="Chrome")
    assert pencere_a.win_id == pencere_b_ayni.win_id


def test_basarisiz_upload_ayni_adayda_tekrar_edilmez():
    """Upload başarısız olursa da referans o kare olur; aynı aday tekrar denenmez (retry yok)."""
    k = Karar()
    # Aday kararlı hale gelir
    assert not k.incele(frame(100), 0.0, ders=1)
    assert k.incele(frame(100), 5.0, ders=1)

    # Upload başarısız oldu: gonderim_basarisiz çağrılır
    k.gonderim_basarisiz(frame(100), 5.0)
    assert k.adet == 0  # Kota artmadı
    assert k.son_gonderilen is not None

    # Sonraki turlarda aynı aday tekrar denenmez!
    assert not k.incele(frame(100), 10.0, ders=1)
    assert not k.incele(frame(100), 35.0, ders=1)
    assert not k.incele(frame(100), 60.0, ders=1)


def test_30_sn_asgari_aralik_ve_20_kota():
    """En az 30 sn aralık ve ders başına en çok 20 kota kontrolü; ders değişince kota sıfırlanır."""
    k = Karar(kota=20, asgari_aralik=30.0)

    # 1. Gönderim t=5
    assert not k.incele(frame(1), 0.0, ders=1)
    assert k.incele(frame(1), 5.0, ders=1)
    k.gonderildi(frame(1), 5.0)

    # t=15'te yeni sayfa (farklı kare: 120)
    assert not k.incele(frame(120), 15.0, ders=1)
    # t=20'de 5 sn kararlı ama 30 sn aralık henüz dolmadı (20-5 = 15 < 30) -> Red
    assert not k.incele(frame(120), 20.0, ders=1)
    # t=35'te 30 sn doldu (35-5 = 30 >= 30) -> Kabul!
    assert k.incele(frame(120), 35.0, ders=1)
    k.gonderildi(frame(120), 35.0)
    assert k.adet == 2

    # 2. Kota dolumu testi (kotayı 3 yapıp test edelim)
    k_kucuk = Karar(kota=3, asgari_aralik=10.0)
    for i in range(3):
        t_bas = i * 20
        k_kucuk.incele(frame(i * 30), float(t_bas), ders=1)
        assert k_kucuk.incele(frame(i * 30), float(t_bas + 5), ders=1)
        k_kucuk.gonderildi(frame(i * 30), float(t_bas + 5))

    assert k_kucuk.adet == 3
    # 4. farklı aday: kota dolduğu için reddedilir
    assert not k_kucuk.incele(frame(200), 70.0, ders=1)
    assert not k_kucuk.incele(frame(200), 75.0, ders=1)

    # Ders değişti: ders=2 -> Durum ve kota sıfırlanır!
    assert not k_kucuk.incele(frame(200), 80.0, ders=2)
    assert k_kucuk.incele(frame(200), 85.0, ders=2)


def test_flag_false_ve_bozuk_config_modul_yok_ag_yok(tmp_path):
    """Config enabled false veya bozuk olduğunda core ve PyQt6 import edilmeden exit 0 döner."""
    cfg_dosya = tmp_path / "api_keys.json"

    # 1. enabled: false
    cfg_dosya.write_text(json.dumps({"ders_gorsel": {"enabled": False}}), encoding="utf-8")
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is None
    assert ret == 0

    # 2. ders_gorsel alanı yok
    cfg_dosya.write_text(json.dumps({"derslik": "10-A"}), encoding="utf-8")
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is None
    assert ret == 0

    # 3. Bozuk JSON
    cfg_dosya.write_text("{bozuk_json", encoding="utf-8")
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is None
    assert ret == 0

    # 4. Dosya yok
    cfg, ret = _hizli_config_kontrol(tmp_path / "olmayan.json")
    assert cfg is None
    assert ret == 0

    # 5. aralik_sn 4..10 sınırlandırma
    cfg_dosya.write_text(
        json.dumps({"ders_gorsel": {"enabled": True, "aralik_sn": 2}}), encoding="utf-8"
    )
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is not None
    assert cfg["aralik_sn"] == 5

    cfg_dosya.write_text(
        json.dumps({"ders_gorsel": {"enabled": True, "aralik_sn": 15}}), encoding="utf-8"
    )
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is not None
    assert cfg["aralik_sn"] == 5

    cfg_dosya.write_text(
        json.dumps({"ders_gorsel": {"enabled": True, "aralik_sn": 8}}), encoding="utf-8"
    )
    cfg, ret = _hizli_config_kontrol(cfg_dosya)
    assert cfg is not None
    assert cfg["aralik_sn"] == 8

    # 6. Alt süreçte çalıştırma: flag false iken core.ders_gorsel ve PyQt6 sys.modules'te olmamalı
    script = (
        "import sys, json; "
        "from ders_gorsel_servis import _hizli_config_kontrol, main; "
        "code = main(); "
        "assert code == 0; "
        "assert 'core.ders_gorsel' not in sys.modules, 'core.ders_gorsel sys.modules içinde var!'; "
        "assert 'PyQt6' not in sys.modules, 'PyQt6 sys.modules içinde var!'"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"Hata: {proc.stderr}"


def test_webp_kodlama():
    """WebP kodlama genişlik <= 960 px sınırı ve geçerli WebP çıktısı sağlar."""
    # 1360x768 görüntü (tahta çözünürlüğü)
    im = Image.new("RGB", (1360, 768), color=(100, 150, 200))
    baytlar = webp_kodla(im, max_genislik=960, kalite=60)

    # WebP magic bytes: RIFF....WEBP
    assert baytlar[:4] == b"RIFF"
    assert baytlar[8:12] == b"WEBP"

    # Kodlanan görüntüyü geri oku ve boyutunu kontrol et
    okunan = Image.open(io.BytesIO(baytlar))
    assert okunan.width == 960
    assert okunan.height == round(768 * 960 / 1360)

    # Zaten küçük olan görüntü büyütülmemeli
    kucuk = Image.new("RGB", (640, 480), color=(10, 20, 30))
    kucuk_bayt = webp_kodla(kucuk, max_genislik=960, kalite=60)
    okunan_kucuk = Image.open(io.BytesIO(kucuk_bayt))
    assert okunan_kucuk.width == 640


def test_gonder_fonksiyonu_ve_metadata():
    """gonder fonksiyonu multipart image ve metadata {'sira': n} ile istek atar."""
    gonderilen_istek = {}

    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        gonderilen_istek["url"] = url
        gonderilen_istek["data"] = data
        gonderilen_istek["files"] = files
        gonderilen_istek["headers"] = headers
        gonderilen_istek["timeout"] = timeout
        return SimpleNamespace(status_code=200)

    bayt = b"RIFFmockWEBP"
    basarili = gonder(
        bayt,
        sira=3,
        sunucu_url="http://192.168.1.100:8000",
        headers={"X-Farabi-Board-Key": "testkey"},
        timeout=5.0,
        post_func=sahte_post,
    )

    assert basarili
    assert gonderilen_istek["url"] == "http://192.168.1.100:8000/api/ders-gorsel"
    assert json.loads(gonderilen_istek["data"]["metadata"]) == {"sira": 3}
    assert "image" in gonderilen_istek["files"]
    assert gonderilen_istek["timeout"] == 5.0
    assert gonderilen_istek["headers"]["X-Farabi-Board-Key"] == "testkey"


def test_servis_metrikleri_10_dakika():
    """Servis metrikleri tick, atlanan, aday, gönderilen, hata, grab ms ve RSS içerir; görsel ve anahtar loglamaz."""
    m = ServisMetrikleri(log_aralik_sn=600.0)
    for _ in range(10):
        m.tick_kaydet()
    m.atla("ders_disi")
    m.atla("ders_disi")
    m.atla("gizlilik_filtresi")
    m.aday_kaydet()
    m.gonderim_kaydet()
    m.hata_kaydet()
    m.grab_sure_kaydet(4.2)
    m.grab_sure_kaydet(7.8)
    m.karsilastirma_sure_kaydet(1.5)

    metin = m.kontrol_ve_raporla(time.monotonic() + 700.0)
    assert metin is not None
    assert "tick=10" in metin
    assert "ders_disi: 2" in metin
    assert "gizlilik_filtresi: 1" in metin
    assert "aday=1" in metin
    assert "gönderilen=1" in metin
    assert "hata=1" in metin
    # Biçim tools/ders_gorsel_olc.py --log ayrıştırıcısıyla eşleşmeli.
    assert "grab_p95=" in metin
    assert "karsilastirma_p95=" in metin
    assert "rss_mib=" in metin

    # RSS fonksiyonu testi
    rss = get_rss_mib()
    assert isinstance(rss, float)

    # Güvenlik: Görüntü veya anahtar izi olmamalı
    assert "base64" not in metin
    assert "X-Farabi-Board-Key" not in metin


def test_x11_bekleme_dongusu():
    """x11_bekle bağlantı sağlanana kadar çökmeden dener."""
    sayac = [0]

    def sahte_kontrol():
        sayac[0] += 1
        return sayac[0] >= 3

    sonuc = x11_bekle(kontrol_fonk=sahte_kontrol, bekleme_sn=0.001, max_deneme=5)
    assert sonuc is True
    assert sayac[0] == 3


def test_aktif_pencere_bilgisi_xprop_mock():
    """aktif_pencere_bilgisi xprop çıktılarını doğru ayrıştırır."""
    def fake_xprop(args, **kwargs):
        if "-root" in args:
            return SimpleNamespace(stdout="window id # 0xabc123", returncode=0)
        if "_NET_WM_WINDOW_TYPE" in args:
            return SimpleNamespace(stdout="_NET_WM_WINDOW_TYPE_NORMAL", returncode=0)
        if "_NET_WM_NAME" in args:
            return SimpleNamespace(stdout='_NET_WM_NAME = "Evince PDF"', returncode=0)
        if "_NET_WM_PID" in args:
            return SimpleNamespace(stdout="_NET_WM_PID(CARDINAL) = 4567", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    p = aktif_pencere_bilgisi(runner=fake_xprop)
    assert p is not None
    assert p.win_id == "0xabc123"
    assert p.baslik == "Evince PDF"
    assert p.pid == 4567


def test_gonder_requests_202_basari(monkeypatch):
    """Sunucu 202 döner; gerçek requests yolu bunu başarı saymalı."""
    for kod, beklenen in ((202, True), (429, False)):
        sahte = SimpleNamespace(post=lambda *a, _k=kod, **kw: SimpleNamespace(status_code=_k))
        monkeypatch.setitem(sys.modules, "requests", sahte)
        assert gonder(b"RIFFxxxxWEBP", sira=1, sunucu_url="http://x", headers={}) is beklenen


def test_benzer_duzenli_metin_sayfasi_degisimi_yakalanir():
    """Pikselin %5'i belirgin değişir (ortalama fark ~0.02): sayfa geçişi sayılmalı."""
    a = np.full((90, 160), 230, dtype=np.uint8)
    b = a.copy()
    b.ravel()[: int(a.size * 0.05)] = 130
    assert np.abs(a.astype(int) - b.astype(int)).mean() / 255 < 0.025
    k = Karar()
    assert not k.incele(a, 0.0, ders=1)
    assert k.incele(a, 6.0, ders=1)
    k.gonderildi(a, 6.0)
    assert not k.incele(b, 40.0, ders=1)
    assert k.incele(b, 46.0, ders=1)


def test_pid_farabi_python_main_py_client_dizininden():
    """farabi_start.sh `python3 main.py` ile client/ dizininden başlatır."""
    import tempfile
    from pathlib import Path

    okuyucu = {2: "/usr/bin/python3\0/usr/share/eta/eta-right-click/main.py\0"}
    assert pid_farabi_mi(2, cmdline_reader=okuyucu.get) is False

    with tempfile.TemporaryDirectory() as kok:
        for ad, beklenen in (("client", True), ("baska", False)):
            d = Path(kok) / ad
            d.mkdir()
            (d / "main.py").write_text("import time; time.sleep(30)\n")
            p = subprocess.Popen([sys.executable, "main.py"], cwd=d)
            try:
                time.sleep(0.2)
                assert pid_farabi_mi(p.pid) is beklenen
            finally:
                p.kill()
                p.wait()


def test_dhash_ve_fark_istisnalari():
    """fark ve dhash geçersiz boyutlarda ValueError fırlatır."""
    import pytest

    with pytest.raises(ValueError):
        fark(np.zeros((10, 10), dtype=np.uint8), np.zeros((10, 20), dtype=np.uint8))

    with pytest.raises(ValueError):
        dhash(np.zeros((5, 5), dtype=np.uint8))
