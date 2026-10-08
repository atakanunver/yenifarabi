from core.yerel_ayar import YEREL_KURALLAR


# Not: "derse başlayalım mı" gibi sohbet örnekleri kurala eklenince model açık
# komutlarda da araç çağırmayı bıraktı (google aç, video aç) — eklemeyin.
def test_yerel_main_ayni_kurali_kullanir():
    import yerel_main
    assert yerel_main._YEREL_KURALLAR is YEREL_KURALLAR
