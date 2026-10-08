import asyncio
import importlib.util
import threading
from pathlib import Path

from core import kaliplar as istemci_kaliplar
from core.qwen_istemci import AracCagrisi, QwenZamanAsimi
from core.ses_istemci import SesServisiHatasi
from core.yerel_oturum import RISKLI, YerelOturum

K = istemci_kaliplar.KALIPLAR


class SahteSes:
    def __init__(self, stt_metin="mitoz nedir", stt_hata=False, tts_hata=False):
        self.stt_metin, self.stt_hata, self.tts_hata = stt_metin, stt_hata, tts_hata
        self.tts_cagri = []

    def stt(self, wav):
        if self.stt_hata:
            raise SesServisiHatasi("x")
        return self.stt_metin

    def tts(self, metin):
        self.tts_cagri.append(metin)
        if self.tts_hata:
            raise SesServisiHatasi("x")
        return b"WAV:" + metin.encode()

    def saglik(self):
        return not self.tts_hata


class SahteQwen:
    """Her akis() çağrısında senaryodaki sıradaki listeyi üretir."""

    def __init__(self, *senaryo, hata=None):
        self.senaryo, self.hata, self.cagri = list(senaryo), hata, []

    def akis(self, mesajlar, araclar, iptal):
        self.cagri.append((list(mesajlar), araclar))
        if self.hata:
            raise self.hata
        for x in self.senaryo.pop(0) if self.senaryo else []:
            if iptal.is_set():
                return
            yield x


def kur(ses=None, qwen=None, arac_sonuc="Kitapta: mitoz dört evre."):
    calinan, gosterilen, araclar = [], [], []

    async def arac_calistir(ad, args):
        araclar.append((ad, args))
        return arac_sonuc

    o = YerelOturum(ses or SahteSes(), qwen or SahteQwen(["Merhaba çocuklar."]),
                    sistem_metni=lambda: "SİSTEM", araclar=lambda: [{"type": "function"}],
                    arac_calistir=arac_calistir, cal=calinan.append,
                    metin_goster=lambda k, m: gosterilen.append((k, m)))
    return o, calinan, gosterilen, araclar


def w(metin):
    return b"WAV:" + metin.encode()


def wav(anahtar):
    return w(K[anahtar])


def test_kaliplar_sunucuyla_ayni():
    yol = Path(__file__).resolve().parents[2] / "sesdugumu" / "kaliplar.py"
    spec = importlib.util.spec_from_file_location("sunucu_kaliplar", yol)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.KALIPLAR == K


def test_sohbet_turu():
    o, calinan, gosterilen, _ = kur(qwen=SahteQwen(["Harika bir ", "soru! Mitoz dört evreden oluşur."]))
    asyncio.run(o.ses_turu(b"RIFF"))
    assert calinan == [w("Harika bir soru!"), w("Mitoz dört evreden oluşur.")]
    assert ("ogretmen", "mitoz nedir") in gosterilen
    assert o.gecmis[-1] == {"role": "assistant", "content": "Harika bir soru! Mitoz dört evreden oluşur."}


def test_bos_stt_qwene_gitmez():
    q = SahteQwen(["x."])
    o, calinan, _, _ = kur(ses=SahteSes(stt_metin=""), qwen=q)
    asyncio.run(o.ses_turu(b"RIFF"))
    assert q.cagri == [] and calinan == []


def test_stt_hatasi_kalip():
    o, calinan, _, _ = kur(ses=SahteSes(stt_hata=True))
    asyncio.run(o.ses_turu(b"RIFF"))
    assert calinan == [wav("duyamadim")]


def test_aracli_tur():
    q = SahteQwen([AracCagrisi("kitap_sorusu", {"soru": "mitoz"})], ["Mitoz dört evreden oluşur."])
    o, calinan, _, araclar = kur(qwen=q)
    asyncio.run(o.metin_turu("kitapta mitoz neydi"))
    assert araclar == [("kitap_sorusu", {"soru": "mitoz"})]
    assert calinan[0] == wav("kitap")
    assert calinan[-1] == w("Mitoz dört evreden oluşur.")
    assert any(m.get("role") == "tool" for m in q.cagri[1][0])


def test_uc_arac_siniri():
    a = [AracCagrisi("web_search", {"q": "x"})]
    q = SahteQwen(a, a, a, ["Bitti."])
    o, _, _, araclar = kur(qwen=q)
    asyncio.run(o.metin_turu("ara"))
    assert len(araclar) == 3
    assert q.cagri[3][1] == []


def test_riskli_arac_onay_evet():
    q = SahteQwen([AracCagrisi("yoklama_al", {})], ["Yoklama alındı."])
    o, calinan, _, araclar = kur(qwen=q)
    asyncio.run(o.metin_turu("yoklama al"))
    assert araclar == [] and calinan[-1] == wav(RISKLI["yoklama_al"])
    asyncio.run(o.metin_turu("evet"))
    assert araclar == [("yoklama_al", {})]


def test_riskli_arac_onay_hayir():
    o, calinan, _, araclar = kur(qwen=SahteQwen([AracCagrisi("yoklama_al", {})]))
    asyncio.run(o.metin_turu("derse başlayalım mı"))
    asyncio.run(o.metin_turu("hayır"))
    assert araclar == [] and calinan[-1] == wav("iptal")


def test_qwen_zaman_asimi():
    o, calinan, _, _ = kur(qwen=SahteQwen(hata=QwenZamanAsimi("x")))
    asyncio.run(o.metin_turu("soru"))
    assert calinan == [wav("yogunum")]


def test_tts_hatasi_metin_gosterilir_ve_servis_kapali_uyarisi():
    o, calinan, gosterilen, _ = kur(
        ses=SahteSes(tts_hata=True),
        qwen=SahteQwen(["Bir cümle burada var. İkinci uzun cümle de burada var. Üçüncü uzun cümle de burada son."]))
    asyncio.run(o.metin_turu("anlat"))
    assert calinan == []
    assert ("farabi", "Bir cümle burada var. İkinci uzun cümle de burada var. "
                      "Üçüncü uzun cümle de burada son.") in gosterilen
    assert ("sistem", "Ses servisi kapalı (Bilgehan)") in gosterilen


def test_iptal_eski_cumleler_calmaz():
    async def senaryo():
        bekle = threading.Event()

        class YavasQwen(SahteQwen):
            def akis(self, mesajlar, araclar, iptal):
                yield "Birinci cümle buradadır uzun. "
                bekle.wait(2)
                yield "İkinci cümle de buradadır uzun."

        o, calinan, _, _ = kur(qwen=YavasQwen())
        gorev = asyncio.create_task(o.metin_turu("anlat"))
        await asyncio.sleep(0.2)
        o.iptal()
        bekle.set()
        await gorev
        return o, calinan

    o, calinan = asyncio.run(senaryo())
    assert "İkinci".encode() not in b"".join(calinan)
    assert o.gecmis[-1]["content"].endswith("(kesildi)")


def test_gecmis_siniri():
    q = SahteQwen(*[["Tamam."]] * 20)
    o, _, _, _ = kur(qwen=q)
    for i in range(20):
        asyncio.run(o.metin_turu(f"soru {i}"))
    mesajlar = q.cagri[-1][0]
    assert mesajlar[0] == {"role": "system", "content": "SİSTEM"}
    assert len(mesajlar) <= 1 + 12 + 1


# ── Son inceleme (2026-10-08) bulguları ─────────────────────────────────


def test_stt_surerken_basilirsa_eski_tur_qwene_gitmez():
    q = SahteQwen(["Cevap."])
    ses = SahteSes()
    o, calinan, _, _ = kur(ses=ses, qwen=q)
    ses.stt = lambda wav: (o.iptal(), "eski soru")[1]  # STT sürerken öğretmen yeniden bastı
    asyncio.run(o.ses_turu(b"RIFF"))
    assert q.cagri == [] and calinan == []


def test_kayit_surerken_sistem_turu_dusurulur():
    q = SahteQwen(["Cevap."])
    o, _, _, _ = kur(qwen=q)
    o.dinliyor = True
    asyncio.run(o.metin_turu("[DERS] 10 dk kaldı", kaynak="sistem"))
    assert q.cagri == []


def test_basistan_once_kuyruga_giren_tur_calismaz():
    async def senaryo():
        bekle = threading.Event()

        class YavasQwen(SahteQwen):
            def akis(self, mesajlar, araclar, iptal):
                self.cagri.append(mesajlar)
                bekle.wait(2)
                yield "Tamam."

        q = YavasQwen()
        o, _, _, _ = kur(qwen=q)
        a = asyncio.create_task(o.metin_turu("birinci"))
        await asyncio.sleep(0.1)
        b = asyncio.create_task(o.metin_turu("[DERS] bildirim", kaynak="sistem"))
        await asyncio.sleep(0.05)
        o.iptal()
        bekle.set()
        await a
        await b
        return q

    assert len(asyncio.run(senaryo()).cagri) == 1


def test_farabi_cevabi_ekrana_ve_transkripte():
    o, _, gosterilen, _ = kur(qwen=SahteQwen(["Harika bir soru! Mitoz dört evreden oluşur."]))
    asyncio.run(o.metin_turu("mitoz nedir"))
    assert ("farabi", "Harika bir soru! Mitoz dört evreden oluşur.") in gosterilen


def test_kesilen_cevap_kesildi_notuyla_gosterilir():
    async def senaryo():
        bekle = threading.Event()

        class YavasQwen(SahteQwen):
            def akis(self, mesajlar, araclar, iptal):
                yield "Birinci cümle buradadır uzun. "
                bekle.wait(2)
                yield "İkinci."

        o, _, gosterilen, _ = kur(qwen=YavasQwen())
        g = asyncio.create_task(o.metin_turu("anlat"))
        await asyncio.sleep(0.2)
        o.iptal()
        bekle.set()
        await g
        return gosterilen

    assert any(k == "farabi" and m.endswith("(kesildi)") for k, m in asyncio.run(senaryo()))


def _riskli_bekleyen():
    q = SahteQwen([AracCagrisi("yoklama_al", {})], ["Normal cevap."])
    o, calinan, gosterilen, araclar = kur(qwen=q)
    asyncio.run(o.metin_turu("yoklama al"))
    return o, q, calinan, araclar


def test_onay_olumsuzluk_kazanir():
    for soz in ("Hayır, tamam gerek yok", "yoklamayı sonra alalım, şimdi alma", "vazgeç"):
        o, _, calinan, araclar = _riskli_bekleyen()
        asyncio.run(o.metin_turu(soz))
        assert araclar == [], soz
        assert calinan[-1] == wav("iptal"), soz


def test_onay_alakasiz_soz_normal_tur_olur():
    o, q, _, araclar = _riskli_bekleyen()
    asyncio.run(o.metin_turu("Tamam çocuklar şimdi mitoz konusuna geçiyoruz bakalım"))
    assert araclar == []
    assert q.cagri[-1][0][-1] == {"role": "user",
                                  "content": "Tamam çocuklar şimdi mitoz konusuna geçiyoruz bakalım"}


def test_onay_suresi_dolar(monkeypatch):
    import core.yerel_oturum as yo
    saat = [1000.0]
    monkeypatch.setattr(yo.time, "monotonic", lambda: saat[0])
    o, _, _, araclar = _riskli_bekleyen()
    saat[0] += yo.ONAY_SURESI_SN + 1
    asyncio.run(o.metin_turu("evet"))
    assert araclar == []


def test_sistem_turu_bekleyen_onayi_temizler():
    o, _, _, araclar = _riskli_bekleyen()
    asyncio.run(o.metin_turu("[YAZILI] mitoz nedir", kaynak="sistem"))
    asyncio.run(o.metin_turu("evet"))
    assert araclar == []


def test_arac_turu_keserse_qwen_yeniden_cagrilmaz():
    q = SahteQwen([AracCagrisi("web_search", {"q": "x"})], ["Sonuç."])
    o, _, _, _ = kur(qwen=q)

    async def kesen_arac(ad, args):  # youtube_video gibi: araç sesi susturur
        o.iptal()
        return "Video açıldı."

    o._arac_calistir = kesen_arac
    asyncio.run(o.metin_turu("video aç"))
    assert len(q.cagri) == 1
