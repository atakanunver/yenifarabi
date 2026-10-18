#!/usr/bin/env python3
"""
v2_arac_testi.py — Farabi Ollama qwen3.8:27b Araç Seçimi (Function Calling) Testi

HEDEF: Farabi'deki Ollama qwen3.8:27b modelinin, tahta istemcisinin Gemini Live'a
verdiği araç bildirimleriyle öğretmen cümlelerinde doğru aracı ve argümanları
seçip seçemediğini ölçmek. SALT-OKUNUR benchmark betiğidir.

KULLANIM:
    cd /home/ata/farabi/benchmark && venv/bin/python v2_arac_testi.py
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Client dizini ve kayit.py importu
BASE_DIR = Path(__file__).resolve().parent
FARABI_DIR = BASE_DIR.parent
CLIENT_DIR = FARABI_DIR / "client"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Bildirimleri kayit.py üzerinden yükle
try:
    if str(CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(CLIENT_DIR))
    from actions import kayit
    def get_bildirimler(kip: str) -> list[dict]:
        return kayit.bildirimler(kip)
except Exception as e:
    print(f"[HATA] kayit.py yüklenemedi: {e}")
    sys.exit(1)


def gemini_to_openai_schema(schema: dict) -> dict:
    """Gemini şemasındaki büyük harfli tipleri (STRING, OBJECT vb.) küçük harfe çevirir."""
    if not isinstance(schema, dict):
        return schema
    res = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            res[k] = v.lower()
        elif k == "properties" and isinstance(v, dict):
            res[k] = {prop_name: gemini_to_openai_schema(prop_val) for prop_name, prop_val in v.items()}
        elif isinstance(v, dict):
            res[k] = gemini_to_openai_schema(v)
        elif isinstance(v, list):
            res[k] = [gemini_to_openai_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            res[k] = v
    if "type" not in res and "properties" in res:
        res["type"] = "object"
    return res


def build_tools_payload(kip: str) -> list[dict]:
    """İlgili kip için OpenAI formatında tools listesi üretir."""
    raw_tools = get_bildirimler(kip)
    openai_tools = []
    for t in raw_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": gemini_to_openai_schema(t.get("parameters", {}))
            }
        })
    return openai_tools


# Kipler için sistem talimatı özetleri (main.py ve prompt.txt esas alınarak)
PROMPTLAR = {
    "ogretmenli": (
        "Sen Farabi'sin — Kurşunlu Şehit Murat Ustaoğlu Anadolu Lisesinde, sınıftaki akıllı tahtada çalışan yapay zekâ öğretmensin.\n"
        "[DERS KİPİ: ÖĞRETMENLİ]\n"
        "Sınıfta bir insan öğretmen ve yaklaşık 20 öğrenci var. Sınıf düzeni ve disiplin öğretmenin sorumluluğunda; senin işin içeriği anlatmak. "
        "Öğretmene 'kıymetli öğretmenim' diye hitap et, sınıfa 'çocuklar' de. Her zaman TÜRKÇE konuş.\n\n"
        "ARAÇ KULLANIM KURALLARI (Yalnızca gerektiğinde ilgili aracı çağır):\n"
        "- ders_icerigi: Öğretmen dersin konusunu açıkça belirtip ders kitabı sayfalarını/iskeletini istediğinde (ders, konu, sinif) çağrılır. Konu belirtilmeden uydurma konuyla ASLA çağırma.\n"
        "- kitap_sorusu: 'Kitapta ne yazıyor?', 'kitaba göre...' gibi kitaptaki belirli bir kavrama/tanıma/formüle yönelik somut soru sorulduğunda çağrılır.\n"
        "- pdf_sayfa: Kitaptan belirli bir sayfa numarası istendiğinde ('9. sayfayı aç/yansıt') çağrılır.\n"
        "- yks_sorulari: Konuyla ilgili çıkmış YKS/TYT/AYT sorusu istendiğinde çağrılır.\n"
        "- ders_hafizasi: 'Geçen ders ne işlemiştik', 'nereye kadar gelmiştik' gibi geçmiş ders hatırlatma isteklerinde çağrılır.\n"
        "- site_goster: Sözlük (TDK), Vikipedi veya resmî izinli web sitesi göstermek için çağrılır.\n"
        "- geogebra: Matematik/geometri çizimi, fonksiyon grafiği çizimi için çağrılır.\n"
        "- file_processor: Tahtaya yüklenen dosyayı (PDF, ödev, tablo) işlemek için çağrılır.\n"
        "- web_search: Güncel bilgi doğrulamak veya konuyu derinleştirmek için arama yapar.\n"
        "- youtube_video: Konuyla ilgili video açmak/oynatmak istendiğinde çağrılır.\n"
        "- eba: EBA portalından video veya içerik açmak istendiğinde çağrılır.\n"
        "- ekrandaki_soruyu_oku: Tahta ekranında o an açık olan soruyu/yazıyı okumak/çözmek için çağrılır.\n"
        "- ekran_goruntusu_al: Ekran görüntüsü al/kaydet dendiğinde çağrılır.\n"
        "- gorsel_uret: Kitapta olmayan yeni bir şema/görsel üretilmek istendiğinde çağrılır.\n"
        "- yoklama_al: Derse başlarken yoklama alma işlemi için çağrılır.\n"
        "- shutdown_farabi: Ders bittiğinde veya tahtayı kapatma istendiğinde ('dersi bitir', 'kapat') çağrılır.\n"
        "- ARAÇ GEREKMEYEN DURUMLAR: Normal sınıf içi diyalog, selamlama, hal hatır sorma, öğrenciye soru sorma veya pekiştirme konuşmalarında HİÇBİR ARAÇ ÇAĞIRMA; doğrudan Türkçe yanıt ver."
    ),
    "talimat": (
        "Sen Farabi'sin. Şu anda ÖĞRETMEN TALİMAT MODUNDASIN.\n"
        "Bu modda DERS ANLATMAZSIN, SORU SORMAZSIN, YOKLAMA ALMAZSIN, sohbet etmezsin, konuyu açıklamazsın. "
        "Tek işin öğretmenin söylediği TEK CÜMLELİK sesli komutu dinleyip en uygun aracı çağırmak.\n\n"
        "AÇMA örnekleri: 'internet aç', 'google aç', 'eba.gov.tr aç', 'youtube aç', '9.21.mp3 dosyasını çal', "
        "'pardus kalem uygulamasını aç', 'çizim uygulamasını aç', 'ev dizinini aç', 'fizik kitabının 45. sayfasını aç'.\n"
        "KAPAMA örnekleri: 'youtube\'u kapat', 'çizim uygulamasını kapat', 'tarayıcıyı kapat' → pencere_kapat aracını çağır "
        "(hedefe pencere başlığından bir kelime/kelime öbeği ver, ör. 'youtube', 'çizim', 'chrome'). "
        "AÇMA aracıyla (web_ac/uygulama_ac) 'kapat' kelimesini ASLA parametre olarak gönderme.\n"
        "ÇIKMA: 'öğretmen talimat modundan çık', 'normal derse dön' → talimat_modundan_cik aracını çağır.\n"
        "DERS KİTAPLARI: 'kitabın X. sayfasını aç/göster' HER ZAMAN pdf_sayfa ile (ders + sayfa numarası), "
        "'kitapta/kitaba göre X nedir' kitap_sorusu ile (ders + soru) karşılanır. dosya_ac'ı kitap için ASLA kullanma.\n"
        "KURALLAR:\n"
        "- Komut içermeyen genel diyalog, selamlama veya teşekkür ifadelerinde araç çağırma.\n"
        "- Her zaman Türkçe konuş."
    )
}


# En az 25 test cümlesi (gerçek tahta dili, Türkçe, konuşma dili)
# Format:
# (cumle, kip, beklenen_arac, alternatif_arac, beklenen_args, emin_mi, aciklama)
TEST_CUMLELERI = [
    # ── ÖĞRETMENLİ KİP — ARAÇ ÇAĞRILARI ──
    (
        "dokuzuncu sınıf biyoloji kitabında mitoz neydi",
        "ogretmenli",
        "kitap_sorusu",
        "ders_icerigi",
        {"ders": "biyoloji", "sinif": "9"},
        False,  # Emin olunmayan: kitapta belirli bir tanım sorduğu için kitap_sorusu da olabilir, konu getirme için ders_icerigi de
        "Kitapta geçen mitoz tanımını soruyor (kitap_sorusu / ders_icerigi)."
    ),
    (
        "9. sınıf matematik kitabından fonksiyonlar konusunu getir",
        "ogretmenli",
        "ders_icerigi",
        None,
        {"ders": "matematik", "konu": "fonksiyonlar", "sinif": "9"},
        True,
        "Kitaptan konu iskeletini getirme talebi."
    ),
    (
        "fizik kitabının 45. sayfasını aç",
        "ogretmenli",
        "pdf_sayfa",
        None,
        {"ders": "fizik", "sayfa": 45},
        True,
        "Belirli bir sayfa numarasını yansıtma."
    ),
    (
        "kimya kitabında periyodik cetvel için ne yazıyor?",
        "ogretmenli",
        "kitap_sorusu",
        None,
        {"ders": "kimya"},
        True,
        "Kitaptaki somut içeriği sorgulama."
    ),
    (
        "ekrandaki soruyu oku",
        "ogretmenli",
        "ekrandaki_soruyu_oku",
        None,
        {},
        True,
        "Tahta ekranındaki soruyu OCR ile okuma."
    ),
    (
        "ekrandaki soruyu oku ve çöz",
        "ogretmenli",
        "ekrandaki_soruyu_oku",
        None,
        {},
        True,
        "Ekrandaki soruyu okuyup çözme talimatı."
    ),
    (
        "bir video aç",
        "ogretmenli",
        "youtube_video",
        None,
        {},
        False,  # Emin olunmayan: konu belirtilmediği için soru sorabilir veya varsayılan youtube_video çağırabilir
        "Konusuz video açma isteği."
    ),
    (
        "mitoz bölünmeyle ilgili bir video aç",
        "ogretmenli",
        "youtube_video",
        None,
        {"query": "mitoz"},
        True,
        "Konulu YouTube video arama ve açma."
    ),
    (
        "türev ile ilgili çıkmış yks sorularını göster",
        "ogretmenli",
        "yks_sorulari",
        None,
        {"konu": "türev"},
        True,
        "Çıkmış YKS sorusu getirme."
    ),
    (
        "geçen ders nerede kalmıştık?",
        "ogretmenli",
        "ders_hafizasi",
        None,
        {},
        True,
        "Geçmiş ders hatırlatma."
    ),
    (
        "vikipedi'den fotosentez maddesini aç",
        "ogretmenli",
        "site_goster",
        None,
        {"arama": "fotosentez"},
        True,
        "Vikipedi / resmî web sayfası açma."
    ),
    (
        "geogebra'da y = 2x + 1 grafiğini çiz",
        "ogretmenli",
        "geogebra",
        None,
        {},
        True,
        "GeoGebra matematik grafiği çizimi."
    ),
    (
        "eba'dan periyodik tablo videosunu aç",
        "ogretmenli",
        "eba",
        None,
        {"query": "periyodik tablo"},
        True,
        "EBA eğitim portalı içeriği."
    ),
    (
        "ekran görüntüsü al",
        "ogretmenli",
        "ekran_goruntusu_al",
        None,
        {},
        True,
        "Ekran görüntüsü kaydetme."
    ),
    (
        "bize kloroplast yapısını gösteren bir görsel üret",
        "ogretmenli",
        "gorsel_uret",
        None,
        {"konu": "kloroplast"},
        True,
        "Yapay zekâ görsel üretimi."
    ),
    (
        "derse başlamadan önce yoklamayı alalım",
        "ogretmenli",
        "yoklama_al",
        None,
        {},
        True,
        "Yoklama alma çağrısı."
    ),
    (
        "dersi bitir",
        "ogretmenli",
        "shutdown_farabi",
        None,
        {},
        True,
        "Dersi bitirme ve tahtayı kapatma."
    ),
    (
        "bugünkü dersimiz bitti tahtayı kapat",
        "ogretmenli",
        "shutdown_farabi",
        None,
        {},
        True,
        "Dersi sonlandırma."
    ),
    (
        "James Webb teleskobunun en son keşiflerini internette araştır",
        "ogretmenli",
        "web_search",
        None,
        {"query": "James Webb"},
        True,
        "İnternet araması."
    ),
    (
        "tahtaya yüklenen pdf dosyasını özetle",
        "ogretmenli",
        "file_processor",
        None,
        {},
        True,
        "Dosya işleme ve özetleme."
    ),

    # ── TALİMAT KİPİ — ARAÇ ÇAĞRILARI ──
    (
        "google aç",
        "talimat",
        "web_ac",
        None,
        {"hedef": "google"},
        True,
        "Tarayıcıda site açma."
    ),
    (
        "eba.gov.tr aç",
        "talimat",
        "web_ac",
        None,
        {"hedef": "eba.gov.tr"},
        True,
        "Tarayıcıda belirli bir URL açma."
    ),
    (
        "pardus kalem uygulamasını aç",
        "talimat",
        "uygulama_ac",
        None,
        {"uygulama": "kalem"},
        True,
        "Masaüstü uygulaması açma."
    ),
    (
        "çizim uygulamasını aç",
        "talimat",
        "uygulama_ac",
        None,
        {"uygulama": "çizim"},
        True,
        "Çizim uygulaması açma."
    ),
    (
        "ev dizinini aç",
        "talimat",
        "dosya_ac",
        None,
        {"hedef": "ev dizini"},
        True,
        "Genel dosya / klasör açma."
    ),
    (
        "youtube'u kapat",
        "talimat",
        "pencere_kapat",
        None,
        {"hedef": "youtube"},
        True,
        "Açık pencereyi kapatma."
    ),
    (
        "tarayıcıyı kapat",
        "talimat",
        "pencere_kapat",
        None,
        {},
        True,
        "Tarayıcı penceresini kapatma."
    ),
    (
        "öğretmen talimat modundan çık",
        "talimat",
        "talimat_modundan_cik",
        None,
        {},
        True,
        "Talimat modundan çıkış."
    ),
    (
        "normal derse dön",
        "talimat",
        "talimat_modundan_cik",
        None,
        {},
        True,
        "Ders moduna dönüş."
    ),

    # ── ARAÇ YOK (SOHBET / SELAMLAŞMA / PEDAGOJİ — EN AZ 5 TANE) ──
    (
        "Günaydın Farabi, bugün nasılsın?",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Selamlama ve hal hatır — araç yok."
    ),
    (
        "Çocuklar hazır mıyız derse başlayalım mı?",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Sınıf içi hitap ve soru — araç yok."
    ),
    (
        "Aferin Ahmet, cevabın çok güzeldi.",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Öğrenciye pekiştirme — araç yok."
    ),
    (
        "Mitoz bölünme vücut hücrelerinde görülür değil mi çocuklar?",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Ders anlatım sorusu — araç yok."
    ),
    (
        "İkinci soruya kim cevap vermek ister?",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Söz isteme — araç yok."
    ),
    (
        "Bugünkü konumuz çok zevkli, dikkatle dinleyin.",
        "ogretmenli",
        None,
        None,
        {},
        True,
        "Öğretmen yönlendirmesi — araç yok."
    ),
    (
        "Teşekkür ederim Farabi, eline sağlık.",
        "talimat",
        None,
        None,
        {},
        True,
        "Talimat modunda teşekkür/selamlama — araç yok."
    ),
]


def query_ollama(cumle: str, kip: str, tools: list[dict], host: str = "http://localhost:11434", model: str = "qwen3.8:27b") -> tuple[dict, float]:
    """Ollama API'sine ardışık istek atar, yanıtı ve gecikmeyi (ms) döner."""
    url = f"{host}/api/chat"
    sys_prompt = PROMPTLAR.get(kip, PROMPTLAR["ogretmenli"])
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": cumle}
        ],
        "tools": tools,
        "stream": False,
        "think": False
    }
    
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"}
    )
    
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
    t1 = time.perf_counter()
    
    latency_ms = round((t1 - t0) * 1000, 2)
    return res_data, latency_ms


def check_arguments(beklenen_args: dict, secilen_args: dict) -> list[str]:
    """Beklenen argümanlar ile modelin ürettiği argümanları karşılaştırır."""
    hatalar = []
    if not beklenen_args:
        return hatalar
    
    for k, v in beklenen_args.items():
        if k not in secilen_args:
            hatalar.append(f"Eksik parametre '{k}' (beklenen: '{v}')")
            continue
        
        gelen_val = secilen_args[k]
        if isinstance(v, (int, float)):
            try:
                if int(gelen_val) != int(v):
                    hatalar.append(f"Parametre '{k}' sayısal uyumsuz (beklenen: {v}, gelen: {gelen_val})")
            except Exception:
                hatalar.append(f"Parametre '{k}' sayıya dönüştürülemedi (beklenen: {v}, gelen: {gelen_val})")
        elif isinstance(v, str):
            v_low = v.strip().lower()
            gelen_low = str(gelen_val).strip().lower()
            if v_low not in gelen_low and gelen_low not in v_low:
                hatalar.append(f"Parametre '{k}' uyumsuz (beklenen: '{v}', gelen: '{gelen_val}')")
    return hatalar


def main():
    print("=" * 70)
    print("Farabi v2 Araç Seçimi Testi (qwen3.8:27b)")
    print(f"Toplam Test Cümlesi: {len(TEST_CUMLELERI)}")
    print("=" * 70)

    # İlgili kiplerin araç listelerini önceden oluştur
    tools_by_kip = {
        "ogretmenli": build_tools_payload("ogretmenli"),
        "talimat": build_tools_payload("talimat")
    }
    print(f"[BİLGİ] 'ogretmenli' araç sayısı: {len(tools_by_kip['ogretmenli'])}")
    print(f"[BİLGİ] 'talimat' araç sayısı:    {len(tools_by_kip['talimat'])}")

    sonuclar = []
    gecikmeler = []
    
    aracli_toplam = 0
    aracli_dogru = 0
    arac_yok_toplam = 0
    arac_yok_dogru = 0
    
    yanlislar = []
    arguman_hatalari = []

    for idx, (cumle, kip, beklenen, alternatif, beklenen_args, emin_mi, aciklama) in enumerate(TEST_CUMLELERI, 1):
        print(f"\n[{idx}/{len(TEST_CUMLELERI)}] ({kip}) '{cumle}'")
        tools = tools_by_kip[kip]
        
        try:
            resp, latency_ms = query_ollama(cumle, kip, tools)
            gecikmeler.append(latency_ms)
        except Exception as e:
            print(f"  HATA: İstek başarısız oldu: {e}")
            continue

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        
        if tool_calls:
            secilen_arac = tool_calls[0]["function"]["name"]
            secilen_args = tool_calls[0]["function"].get("arguments", {})
        else:
            secilen_arac = None
            secilen_args = {}

        # Doğruluk kontrolü
        is_arac_yok_testi = (beklenen is None)
        if is_arac_yok_testi:
            arac_yok_toplam += 1
            dogru = (secilen_arac is None)
            if dogru:
                arac_yok_dogru += 1
        else:
            aracli_toplam += 1
            dogru = (secilen_arac == beklenen)
            if not dogru and alternatif and (secilen_arac == alternatif):
                dogru = True  # Kabul edilebilir alternatif

            if dogru:
                aracli_dogru += 1

        # Argüman kontrolü
        arg_hatalari_item = []
        if secilen_arac and (secilen_arac == beklenen or secilen_arac == alternatif):
            arg_hatalari_item = check_arguments(beklenen_args, secilen_args)
            if arg_hatalari_item:
                arguman_hatalari.append({
                    "cumle": cumle,
                    "kip": kip,
                    "arac": secilen_arac,
                    "beklenen_args": beklenen_args,
                    "secilen_args": secilen_args,
                    "hatalar": arg_hatalari_item
                })

        durum_str = "DOĞRU" if dogru else "YANLIŞ"
        print(f"  -> Seçilen: {secilen_arac or 'ARAÇ YOK'} | Beklenen: {beklenen or 'ARAÇ YOK'} | {durum_str} ({latency_ms} ms)")
        if secilen_args:
            print(f"     Argümanlar: {secilen_args}")
        if arg_hatalari_item:
            print(f"     [!] Argüman Hataları: {', '.join(arg_hatalari_item)}")

        if not dogru:
            yanlislar.append({
                "cumle": cumle,
                "kip": kip,
                "beklenen": beklenen,
                "alternatif": alternatif,
                "secilen": secilen_arac,
                "secilen_args": secilen_args,
                "emin_mi": emin_mi,
                "aciklama": aciklama
            })

        sonuclar.append({
            "idx": idx,
            "cumle": cumle,
            "kip": kip,
            "beklenen": beklenen,
            "alternatif": alternatif,
            "secilen": secilen_arac,
            "secilen_args": secilen_args,
            "dogru": dogru,
            "latency_ms": latency_ms,
            "emin_mi": emin_mi,
            "arg_hatalari": arg_hatalari_item,
            "aciklama": aciklama
        })

    # İstatistikler
    import numpy as np
    medyan_gecikme = round(float(np.median(gecikmeler)), 2) if gecikmeler else 0.0
    p90_gecikme = round(float(np.percentile(gecikmeler, 90)), 2) if gecikmeler else 0.0
    ortalama_gecikme = round(float(np.mean(gecikmeler)), 2) if gecikmeler else 0.0

    toplam_test = len(TEST_CUMLELERI)
    toplam_dogru = aracli_dogru + arac_yok_dogru
    genel_oran = round((toplam_dogru / toplam_test) * 100, 1)
    arac_oran = round((aracli_dogru / aracli_toplam) * 100, 1) if aracli_toplam else 0.0
    arac_yok_oran = round((arac_yok_dogru / arac_yok_toplam) * 100, 1) if arac_yok_toplam else 0.0

    print("\n" + "=" * 70)
    print("TEST SONUÇLARI:")
    print(f"Genel Doğruluk:     {toplam_dogru}/{toplam_test} (%{genel_oran})")
    print(f"Araç Seçimi:        {aracli_dogru}/{aracli_toplam} (%{arac_oran})")
    print(f"Araç Yok (Sohbet):  {arac_yok_dogru}/{arac_yok_toplam} (%{arac_yok_oran})")
    print(f"Argüman Hataları:   {len(arguman_hatalari)}")
    print(f"Gecikme (Medyan):   {medyan_gecikme} ms")
    print(f"Gecikme (p90):      {p90_gecikme} ms")
    print(f"Gecikme (Ortalama): {ortalama_gecikme} ms")
    print("=" * 70)

    # Rapor JSON kaydet
    zaman_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    rapor_dosyasi = REPORTS_DIR / f"v2_arac_testi_{zaman_str}.json"
    
    rapor_icerik = {
        "tarih": datetime.now().isoformat(),
        "model": "qwen3.8:27b",
        "toplam_test": toplam_test,
        "arac_testleri": {
            "toplam": aracli_toplam,
            "dogru": aracli_dogru,
            "oran": arac_oran
        },
        "arac_yok_testleri": {
            "toplam": arac_yok_toplam,
            "dogru": arac_yok_dogru,
            "oran": arac_yok_oran
        },
        "genel": {
            "toplam": toplam_test,
            "dogru": toplam_dogru,
            "oran": genel_oran
        },
        "arguman_hatalari_sayisi": len(arguman_hatalari),
        "gecikme_ms": {
            "medyan": medyan_gecikme,
            "p90": p90_gecikme,
            "ortalama": ortalama_gecikme,
            "min": round(min(gecikmeler), 2) if gecikmeler else 0,
            "max": round(max(gecikmeler), 2) if gecikmeler else 0
        },
        "yanlislar": yanlislar,
        "arguman_hatalari": arguman_hatalari,
        "detaylar": sonuclar
    }

    with open(rapor_dosyasi, "w", encoding="utf-8") as f:
        json.dump(rapor_icerik, f, ensure_ascii=False, indent=2)

    print(f"\nRapor başarıyla kaydedildi: {rapor_dosyasi}")
    return rapor_dosyasi


if __name__ == "__main__":
    main()
