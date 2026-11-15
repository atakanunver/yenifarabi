#!/usr/bin/env python3
"""
sistem_dizayni_pdf_uret.py
--------------------------
Farabi Akıllı Tahta ve Bütünleşik Okul Operasyon Ekosistemi
Sistem Mimarisi, Servis Envanteri ve Tanıtım PDF Dokümanı Üretici.

Çıktı:
  /home/ata/farabi/FARABI_SISTEM_DIZAYNI_VE_TANITIMI.pdf
"""

import sys
import subprocess
from pathlib import Path

OUTPUT_PDF = Path("/home/ata/farabi/FARABI_SISTEM_DIZAYNI_VE_TANITIMI.pdf")
TMP_HTML = Path("/tmp/farabi_sistem_dizayni.html")

def generate_html():
    return """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Farabi — Sistem Mimarisi ve Tanıtım Raporu</title>
<style>
  @page {
    size: A4 portrait;
    margin: 0;
  }
  * {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1E293B;
    background: #FFFFFF;
    font-size: 11.5px;
    line-height: 1.5;
  }
  .page {
    width: 210mm;
    height: 297mm;
    max-height: 297mm;
    padding: 16mm 18mm;
    margin: 0 auto;
    position: relative;
    page-break-after: always;
    page-break-inside: avoid;
    overflow: hidden;
    background: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .header {
    border-bottom: 2px solid #0F172A;
    padding-bottom: 8px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }
  .header-left h1 {
    margin: 0;
    font-size: 19px;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: -0.3px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .header-left h1 span.badge {
    font-size: 9.5px;
    font-weight: 700;
    background: #7A1E2B;
    color: #FFFFFF;
    padding: 2px 7px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .header-left .sub {
    font-size: 10px;
    color: #64748B;
    margin-top: 2px;
    font-weight: 500;
  }
  .header-right {
    text-align: right;
    font-size: 9.5px;
    color: #475569;
    font-weight: 500;
    line-height: 1.35;
  }
  .footer {
    border-top: 1px solid #E2E8F0;
    padding-top: 8px;
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 8.5px;
    color: #64748B;
  }
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  
  /* Kartlar & Grid */
  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 10px;
  }
  .grid-4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }
  .card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 10px 12px;
  }
  .card-header {
    font-weight: 700;
    font-size: 11.5px;
    color: #0F172A;
    margin-bottom: 5px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 4px;
  }
  .stat-card {
    background: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-top: 3px solid #7A1E2B;
    border-radius: 6px;
    padding: 8px 10px;
    text-align: center;
  }
  .stat-val {
    font-size: 20px;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.1;
  }
  .stat-lbl {
    font-size: 9px;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    margin-top: 3px;
  }
  
  /* Tablolar */
  table.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 9.5px;
    margin-top: 4px;
  }
  table.data-table th {
    background: #0F172A;
    color: #FFFFFF;
    font-weight: 600;
    text-align: left;
    padding: 5px 8px;
  }
  table.data-table td {
    padding: 5px 8px;
    border-bottom: 1px solid #E2E8F0;
    vertical-align: middle;
  }
  table.data-table tr:nth-child(even) td {
    background: #F8FAFC;
  }
  .pill {
    display: inline-block;
    padding: 1.5px 6px;
    border-radius: 3px;
    font-size: 8px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .pill-green { background: #DCFCE7; color: #166534; }
  .pill-blue { background: #DBEAFE; color: #1E40AF; }
  .pill-purple { background: #F3E8FF; color: #6B21A8; }
  .pill-amber { background: #FEF3C7; color: #92400E; }
  .pill-red { background: #FEE2E2; color: #991B1B; }
  
  /* Şema Kutusı */
  .diagram-box {
    background: #F1F5F9;
    border: 1px dashed #94A3B8;
    border-radius: 6px;
    padding: 10px;
    text-align: center;
  }
  
  /* Liste */
  ul.feat-list {
    margin: 0;
    padding-left: 15px;
    font-size: 10.5px;
  }
  ul.feat-list li {
    margin-bottom: 3px;
  }
  
  /* İmzalar */
  .sign-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 10px;
  }
  .sign-box {
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 8px;
    text-align: center;
    background: #FAF5FF;
  }
  .sign-title {
    font-size: 8.5px;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
  }
  .sign-name {
    font-size: 10px;
    font-weight: 700;
    color: #0F172A;
    margin-top: 2px;
  }
  .sign-space {
    height: 32px;
  }
</style>
</head>
<body>

<!-- SAYFA 1: KAPAK & YÖNETİCİ ÖZETİ -->
<div class="page">
  <div>
    <div class="header">
      <div class="header-left">
        <h1>FARABİ <span class="badge">Eğitim & Operasyon Ekosistemi</span></h1>
        <div class="sub">T.C. Millî Eğitim Bakanlığı · Şehit Murat Ustaoğlu Anadolu Lisesi</div>
      </div>
      <div class="header-right">
        <div><strong>Doküman No:</strong> FRB-SYS-2026-V4</div>
        <div><strong>Tarih:</strong> 08 Kasım 2026</div>
        <div><strong>Gizlilik:</strong> Hizmete Özel / Kurumsal</div>
      </div>
    </div>

    <div class="content">
      <!-- Özet Banner -->
      <div class="card" style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); color: #F8FAFC; border: none; padding: 14px 16px;">
        <div style="font-size: 15px; font-weight: 800; color: #F59E0B; margin-bottom: 4px;">
          YENİ NESİL AKILLI OKUL VE TAHTA ASİSTANI MİMARİSİ
        </div>
        <div style="font-size: 10.5px; line-height: 1.55; color: #CBD5E1;">
          <strong>Farabi</strong>, sınıf içi akıllı tahtalarda çalışan gerçek zamanlı yapay zeka ders asistanı ile okulun tüm operasyonel süreçlerini (dijital yoklama, veli SMS otomasyonu, dijital okul portalı, ortak sınav dağıtımı, 3D dijital ikiz ve güvenlik izleme) tek bir yerel sunucu kümesinde birleştiren bütünleşik bir okul işletim ekosistemidir.
        </div>
      </div>

      <!-- Temel Metrikler -->
      <div class="grid-4" style="margin-top: 4px;">
        <div class="stat-card">
          <div class="stat-val">12+</div>
          <div class="stat-lbl">Akıllı Tahta Filosu</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">10</div>
          <div class="stat-lbl">Mikro Web Servisi</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">%100</div>
          <div class="stat-lbl">Yerel KVKK Koruma</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">27B</div>
          <div class="stat-lbl">Yerel LLM (Qwen 3.8)</div>
        </div>
      </div>

      <!-- Temel Çalışma İlkeleri -->
      <div class="card" style="margin-top: 4px;">
        <div class="card-header">🏛️ FARABİ SİSTEMİNİN TEMEL İLKELERİ</div>
        <div class="grid-2" style="gap: 12px; font-size: 10px; margin-top: 6px;">
          <div>
            <strong style="color: #7A1E2B;">1. "Client İnce, Server Beyin" İlkesi:</strong>
            <p style="margin: 2px 0 6px 0; color: #475569;">
              Akıllı tahtalar (Vestel/Pardus ETAP) yalnızca ince etkileşim yüzeyidir. PyQt6 render ve Gemini Live ses oturumunu yürütür. Tüm iş mantığı, PDF kitap indeksleri, sınav analizleri ve model kararları merkezi Farabi sunucusundadır.
            </p>
            <strong style="color: #7A1E2B;">2. Fail-Safe & Kesintisiz Ders Güvencesi:</strong>
            <p style="margin: 2px 0 0 0; color: #475569;">
              Sunucu veya okul ağı geçici olarak kapansa dahi akıllı tahtanın temel fonksiyonları ve ders işleyişi asla kilitlenmez; istemci sessizce bekler ve sistem kendini toparlar.
            </p>
          </div>
          <div>
            <strong style="color: #7A1E2B;">3. Sıfır Bulut Veri Sızıntısı (KVKK):</strong>
            <p style="margin: 2px 0 6px 0; color: #475569;">
              Öğrenci, veli ve idari veriler (yoklama, telefon rehberi, e-Okul listeleri) ASLA harici bulut servislerine iletilmez. Okul verisine dokunan sorgular yalnızca sunucu içi izole modelle (Ollama `qwen3.8:27b`) işlenir.
            </p>
            <strong style="color: #7A1E2B;">4. Modüler Servis İzolasyonu:</strong>
            <p style="margin: 2px 0 0 0; color: #475569;">
              Monolitik veya hantal Docker yapıları yerine, her proje bağımsız bir `systemd` servisi ve izole `venv` olarak koşar. Servisler arası iletişim REST API ve HMAC anahtarlarıyla güvenceye alınır.
            </p>
          </div>
        </div>
      </div>

      <!-- Sistem Katmanları Blok Şeması -->
      <div class="card" style="margin-top: 4px;">
        <div class="card-header">📊 SİSTEM KATMANLARI VE AKIŞ ŞEMASI</div>
        <div style="background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 4px; padding: 10px; font-size: 9.5px;">
          <div style="display: flex; justify-content: space-between; text-align: center; gap: 8px;">
            <div style="flex: 1; background: #EFF6FF; border: 1px solid #BFDBFE; padding: 8px; border-radius: 4px;">
              <strong style="color: #1E40AF; display: block; margin-bottom: 3px;">1. KULLANICI / TAHTA KATMANI</strong>
              Pardus ETAP Tahtalar · PyQt6 UI · Gemini Live Ses · Sınıf Arenası · 3D Okul
            </div>
            <div style="display: flex; align-items: center; color: #94A3B8; font-weight: 800;">➔</div>
            <div style="flex: 1; background: #FDF2F8; border: 1px solid #FBCFE8; padding: 8px; border-radius: 4px;">
              <strong style="color: #9D174D; display: block; margin-bottom: 3px;">2. SERVİS & API KATMANI</strong>
              farabi-api (:8000) · Yoklama (:80) · SMS (:8020) · smual.app (:9090) · Kelebek (:8050)
            </div>
            <div style="display: flex; align-items: center; color: #94A3B8; font-weight: 800;">➔</div>
            <div style="flex: 1; background: #F0FDF4; border: 1px solid #BBF7D0; padding: 8px; border-radius: 4px;">
              <strong style="color: #166534; display: block; margin-bottom: 3px;">3. MODEL & VERİ KATMANI</strong>
              Ollama 27B · PostgreSQL · SQLite WAL · Atos / AnythingLLM · MediaMTX RTSP
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <div>Farabi Ekosistemi Mimari Dokümantasyonu · Şehit Murat Ustaoğlu Anadolu Lisesi</div>
    <div>Sayfa 01 / 04</div>
  </div>
</div>

<!-- SAYFA 2: SERVİSLER VE PROJE ENVANTERİ -->
<div class="page">
  <div>
    <div class="header">
      <div class="header-left">
        <h1>SERVİSLER VE BİLEŞEN ENVANTERİ</h1>
        <div class="sub">Farabi Monorepo Aktif Systemd Servisleri ve Port Tahsis Haritası</div>
      </div>
      <div class="header-right">
        <div><strong>Altyapı:</strong> Linux Ubuntu 24.04 LTS</div>
        <div><strong>Donanım:</strong> 2x NVIDIA RTX 3060 (24 GB)</div>
        <div><strong>Depolama:</strong> /mnt/farabi-data NVMe</div>
      </div>
    </div>

    <div class="content">
      <div class="card" style="padding: 0; overflow: hidden;">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 18%;">Servis Adı</th>
              <th style="width: 14%;">Dizin / Env</th>
              <th style="width: 10%;">Port / Protokol</th>
              <th style="width: 16%;">Veritabanı / Veri</th>
              <th style="width: 42%;">Temel Görevi ve Sorumluluk Alanı</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>farabi-api</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>server/</code><br>Python venv</td>
              <td><strong>:8000</strong><br>HTTP / REST</td>
              <td>Kitap / YKS PDF'leri<br><code>ders_gorselleri/</code></td>
              <td>Eğitim beyni; akıllı tahta yetkilendirmesi (Board-Key), YKS çıkmış soru arama, ders kitapları görsel ve sayfa çıkarma, tahta telemetrisi.</td>
            </tr>
            <tr>
              <td><strong>farabi-yoklama-dashboard</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>tahtayoklama/</code><br>Python venv</td>
              <td><strong>:80</strong><br>HTTP Nginx</td>
              <td><code>yoklama_pano.db</code><br>SQLite WAL</td>
              <td>Okul merkezi yönetim paneli; sınıf yoklamaları, tahtalara uzaktan SSH yönetimi, servis denetimleri, Atos SQL sorgulama köprüsü.</td>
            </tr>
            <tr>
              <td><strong>farabi-smssistemi</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>smssistemi/</code><br>Python venv</td>
              <td><strong>:8020</strong><br>HTTP Fast/Flask</td>
              <td><code>smssistemi.db</code><br>SQLite WAL</td>
              <td>Veli devamsızlık bildirim SMS'leri, doğum günü otomasyonu, kurum içi SMS gönderimi, rehber ve bakiye takibi.</td>
            </tr>
            <tr>
              <td><strong>farabi-okul</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>okul/</code><br>Python venv</td>
              <td><strong>:9090</strong><br>Cloudflare Tunnel</td>
              <td><code>okul.db</code><br>PostgreSQL köprü</td>
              <td><strong>smual.app</strong> üzerinden veli ve öğrencilere açık dijital okul portalı; anlık ders programı, nöbetçi öğretmenler, yemek listesi ve duyurular.</td>
            </tr>
            <tr>
              <td><strong>farabi-kelebek</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>kelebek/</code><br>Python venv</td>
              <td><strong>:8050</strong><br>HTTP / REST</td>
              <td><code>kelebek.db</code><br>SQLite</td>
              <td>Ortak sınav salon ve sıra dağıtımı; kopya çekmeyi önleyen gelişmiş kelebek yerleşim algoritması ve resmi sınav tutanak çıktıları.</td>
            </tr>
            <tr>
              <td><strong>farabi-okul3d</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>okul3d/</code><br>Python stdlib</td>
              <td><strong>:8095 / :8096</strong><br>Three.js WebGL</td>
              <td><code>oda_adlari.json</code><br><code>mimari.json</code></td>
              <td>Şehit Murat Ustaoğlu Anadolu Lisesi 3D Dijital İkizi; interaktif bina gezisi, canlı ders/öğrenci/nöbetçi simülasyonu, A4 vektörel mimari PDF üretimi.</td>
            </tr>
            <tr>
              <td><strong>sinif-arena</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>arenasinif/</code><br>Python venv</td>
              <td><strong>:8030</strong><br>HTTP / WebSocket</td>
              <td><code>arena.db</code><br>Soru bankası</td>
              <td>Akıllı tahtalar arası yarışma oyunları; Düello, Sınıf Arenası ve sınıfların okul haritasında bilgiyle yarıştığı HexaFetih strateji oyunu.</td>
            </tr>
            <tr>
              <td><strong>farabi-kameralar</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>kameralar/</code><br>MediaMTX</td>
              <td><strong>:8889</strong><br>WebRTC / RTSP</td>
              <td>Kamera Kayıt NVMe<br><code>durum.json</code></td>
              <td>DVR ve IP kamera canlı akışları; 127.0.0.1 kısıtlı RTSP/WebRTC yayını ve `farabi-hareket` servisi ile yapay zeka hareket algılama.</td>
            </tr>
            <tr>
              <td><strong>farabi-atlas</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>tahtaatlasfarabi/</code><br>FastAPI + Node</td>
              <td><strong>:8099</strong><br>Cesium / Three</td>
              <td><code>var/atlas.db</code><br>HGM Küre Entegr.</td>
              <td>Akıllı tahtalarda 3D interaktif küre, coğrafya, tarih ve harita oyunları; yerel coğrafi bilgi sistemi entegrasyonu.</td>
            </tr>
            <tr>
              <td><strong>pm2-anythingllm</strong><br><span class="pill pill-green">Canlı / Aktif</span></td>
              <td><code>/opt/anythingllm</code><br>Node / PM2</td>
              <td><strong>:8010</strong><br>HTTP Dashboard</td>
              <td>Bellek içi SQLite<br><code>okul_ana</code> ro</td>
              <td><strong>Atos</strong> yerel idari yapay zeka asistanı; okul veritabanı üzerinde güvenli SQL sorguları (`sql-sorgu`, `tablo-dosyasi`) ve kontrollü SMS gönderimi.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Veri ve İletişim Güvenliği -->
      <div class="grid-2" style="margin-top: 4px;">
        <div class="card">
          <div class="card-header">🔐 SERVİSLER ARASI İLETİŞİM PROTOKOLÜ</div>
          <p style="margin: 0; font-size: 10px; color: #475569;">
            Servisler doğrudan birbirlerinin veritabanlarına yazmaz. Tüm iletişim <strong>HTTP REST + HMAC / Token</strong> ile sağlanır. Tek istisna, SMS sisteminin devamsızlık sayılarını okumak için <code>yoklama_pano.db</code>'yi salt-okunur (read-only) açmasıdır. Nginx ters proxy ile tüm statik dosyalar Gzip seviye 6 ile sıkıştırılarak okul ağı rahatlatılır.
          </p>
        </div>
        <div class="card">
          <div class="card-header">⚡ VERİTABANI İNTİZAMI & WAL MODU</div>
          <p style="margin: 0; font-size: 10px; color: #475569;">
            Tüm SQLite veritabanlarında eşzamanlı okuma/yazma kilitlenmelerini önlemek amacıyla <code>PRAGMA journal_mode=WAL;</code> ve <code>PRAGMA synchronous=NORMAL;</code> zorunlu kılınmıştır. Ana okul verisi PostgreSQL (<code>okul_ana</code>) üzerinde tutulur; tahtalara dağıtılan zil ve ders programı JSON dosyaları bu ana kaynaktan türer.
          </p>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <div>Farabi Ekosistemi Mimari Dokümantasyonu · Şehit Murat Ustaoğlu Anadolu Lisesi</div>
    <div>Sayfa 02 / 04</div>
  </div>
</div>

<!-- SAYFA 3: AKILLI TAHTA, SES VE YAPAY ZEKA MİMARİSİ -->
<div class="page">
  <div>
    <div class="header">
      <div class="header-left">
        <h1>AKILLI TAHTA VE HİBRİT YAPAY ZEKA</h1>
        <div class="sub">Gemini Live Sesli Asistan, Yerel Qwen LLM ve Sınıf Etkileşimi</div>
      </div>
      <div class="header-right">
        <div><strong>İstemci OS:</strong> Pardus 21/23 ETAP (Linux)</div>
        <div><strong>Ses Motoru:</strong> Gemini Live WebSocket</div>
        <div><strong>Yerel Model:</strong> Ollama qwen3.8:27b</div>
      </div>
    </div>

    <div class="content">
      <!-- Akıllı Tahta Yapısı -->
      <div class="card">
        <div class="card-header">🖥️ AKILLI TAHTA İSTEMCİSİ (`client/`) ÇALIŞMA MEKANİZMASI</div>
        <div class="grid-2" style="font-size: 10px; gap: 10px; margin-top: 4px;">
          <div>
            <strong style="color: #0F172A;">Gerçek Zamanlı Ses ve Etkileşim:</strong>
            <p style="margin: 2px 0 6px 0; color: #475569;">
              Öğretmen ve öğrenciler tahtada Farabi ile doğrudan konuşur. Ses verisi tahtadan doğrudan Google Gemini Live WebSocket tüneline akar (düşük gecikme süresi, doğal diyalog). Farabi ders anlatımı, soru çözümü ve komutları anlık olarak seslendirir.
            </p>
            <strong style="color: #0F172A;">Fiziksel Tahta Eylemleri (`actions/`):</strong>
            <p style="margin: 2px 0 0 0; color: #475569;">
              Yapay zeka yalnızca konuşmakla kalmaz; tahtada ekran görüntüsü alma, ders PDF'si açma, tahta cetvelini getirme, HGM Küre haritasını başlatma veya tarayıcıda ilgili ders materyalini ekrana getirme eylemlerini otonom icra eder.
            </p>
          </div>
          <div>
            <strong style="color: #0F172A;">Bağımsız Dağıtım & GitHub Senkronizasyonu:</strong>
            <p style="margin: 2px 0 6px 0; color: #475569;">
              Tahtalar kodlarını sunucudan değil, doğrudan <code>github.com/atakanunver/yenifarabi</code> genel reposundan çeker. Sunucu kapansa bile tahtalar güncellenir. Heartbeat mekanizması ile her 15 dakikada bir tahta sağlığı dashboard'a bildirilir.
            </p>
            <strong style="color: #0F172A;">Kimliklendirme (Avahi / mDNS):</strong>
            <p style="margin: 2px 0 0 0; color: #475569;">
              Okul ağında IP adresleri DHCP ile değişse bile tahtalar sabit avahi hostname'leri (örn. <code>vestel9b.local</code>, <code>vestel10a.local</code>) üzerinden tanınır; derslik eşleştirmesi dinamik olarak korunur.
            </p>
          </div>
        </div>
      </div>

      <!-- Hibrit Yapay Zeka Katmanı -->
      <div class="grid-2" style="margin-top: 4px;">
        <div class="card">
          <div class="card-header">🤖 YEREL LLM: OLLAMA (`qwen3.8:27b`)</div>
          <div style="font-size: 10px; color: #475569;">
            <p style="margin: 0 0 4px 0;">
              Sunucuda 2x RTX 3060 GPU üzerinde koşan Ollama motorunda tek model <strong>Qwen 3.8 27B</strong>'dir. İstemciler modele <code>farabi</code> takma adıyla erişir.
            </p>
            <ul style="margin: 0; padding-left: 14px; font-size: 9.5px;">
              <li><strong>Bağlam Penceresi:</strong> 49.152 token (OLLAMA_CONTEXT_LENGTH).</li>
              <li><strong>Sürekli Bellekte:</strong> <code>OLLAMA_KEEP_ALIVE=-1</code> ile sıfır soğuk başlangıç gecikmesi.</li>
              <li><strong>Görevleri:</strong> SMS metin taslakları, EBYS özetleri, Atos SQL sorgu üretimi, soru havuzu analizleri.</li>
            </ul>
          </div>
        </div>

        <div class="card">
          <div class="card-header">🧠 ATOS (ANYTHINGLLM) VERİ YETENEKLERİ</div>
          <div style="font-size: 10px; color: #475569;">
            <p style="margin: 0 0 4px 0;">
              İdari personele yönelik Türkçe akıllı okul veri asistanıdır. Panelde <code>POST /api/okul/sql</code> uç noktası üzerinden güvenli çalışır:
            </p>
            <ul style="margin: 0; padding-left: 14px; font-size: 9.5px;">
              <li><strong>Güvenli Bellek İçi SQL:</strong> Kaynak tablolar anlık kopyalanır; SQLite <code>set_authorizer</code> ile yalnız SELECT serbesttir.</li>
              <li><strong>Gizlilik İzolasyonu:</strong> Parola, oturum ve gizli anahtarlar asla sorgu alanına alınmaz; veri dışarı sızmaz.</li>
              <li><strong>SMS Onay Döngüsü:</strong> Toplu SMS gönderimleri insan onayı olmadan tetiklenmez.</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Soru Bankası ve Dijital İkiz -->
      <div class="grid-2" style="margin-top: 4px;">
        <div class="card">
          <div class="card-header">📚 SORU BANKASI & YKS MOTORU</div>
          <div style="font-size: 10px; color: #475569;">
            <p style="margin: 0;">
              11.000+ onaylı sorudan oluşan dijital soru bankası ve ÖSYM çıkmış YKS soruları arşivi. Öğretmen tahtada bir konuyu işlerken Farabi konuya en uygun ÖSYM çıkmış sorusunu veya MEB kazanım testini anında tahtaya yansıtır.
            </p>
          </div>
        </div>

        <div class="card">
          <div class="card-header">🏛️ 3D DİJİTAL İKİZ (OKUL3D)</div>
          <div style="font-size: 10px; color: #475569;">
            <p style="margin: 0;">
              Şehit Murat Ustaoğlu Anadolu Lisesi binasının Three.js r128 ile modellenmiş tarayıcı tabanlı ikizi. Canlı yoklama sayılarıyla sınıflarda oturan öğrenciler, teneffüs simülasyonları, nöbetçi öğretmenler ve vektörel mimari kat planları sunar.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <div>Farabi Ekosistemi Mimari Dokümantasyonu · Şehit Murat Ustaoğlu Anadolu Lisesi</div>
    <div>Sayfa 03 / 04</div>
  </div>
</div>

<!-- SAYFA 4: AĞ, GÜVENLİK, DAĞITIM VE ONAY -->
<div class="page">
  <div>
    <div class="header">
      <div class="header-left">
        <h1>AĞ TOPOLOJİSİ, GÜVENLİK VE YÖNETİM</h1>
        <div class="sub">Okul Ağı Güvenlik Katmanı, Denetim Sistemleri ve Onay Matrisi</div>
      </div>
      <div class="header-right">
        <div><strong>Ağ Çıkışı:</strong> MEB Kablolu (192.168.16.1)</div>
        <div><strong>Dış Tünel:</strong> Cloudflare Tunnel (smual.app)</div>
        <div><strong>Durum:</strong> Canlı Üretim (Production)</div>
      </div>
    </div>

    <div class="content">
      <!-- Ağ Çıkış Hatları -->
      <div class="card">
        <div class="card-header">🌐 İNTERNET ÇIKIŞ VE AĞ POLİTİKASI</div>
        <div class="grid-2" style="font-size: 10px; gap: 10px; margin-top: 4px;">
          <div>
            <strong style="color: #1E40AF;">Kablolu MEB Hattı (Doğrudan Çıkış):</strong>
            <p style="margin: 2px 0 4px 0; color: #475569;">
              Farabi sunucusu ve Telegram botları öncelikli olarak kablolu MEB hattını (gateway <code>192.168.16.1</code>) kullanır. MEB kök sertifikası sisteme eklenmiş olup SSL denetimi sorunsuz işler. Kota ve zaman aşımı riski bulunan Wi-Fi proxy kullanılmaz.
            </p>
          </div>
          <div>
            <strong style="color: #9D174D;">Cloudflare Edge Relay (smual.app):</strong>
            <p style="margin: 2px 0 4px 0; color: #475569;">
              Okul dışındaki veli ve öğrencilerin portala erişimi için statik IP veya port yönlendirme gerekmez. Güvenli Cloudflare Tüneli (<code>cf-edge-relay</code>) üzerinden yalnız <code>farabi-okul</code> (:9090) servisi kontrollü şekilde internete açılır.
            </p>
          </div>
        </div>
      </div>

      <!-- Güvenlik & Denetim -->
      <div class="grid-2" style="margin-top: 4px;">
        <div class="card">
          <div class="card-header">🛡️ GÜVENLİK & İZLEME (AUDIT)</div>
          <div style="font-size: 9.5px; color: #475569;">
            <p style="margin: 0 0 4px 0;"><strong>Farabi Audit Watcher:</strong> Sunucudaki servis çöküşlerini, bellek sızıntılarını ve CPU aşırılıklarını izler; acil durumlarda yöneticiye anlık Telegram bildirimi gönderir.</p>
            <p style="margin: 0;"><strong>Haftalık NAS Yedeklemesi:</strong> Her pazar gecesi 03:30'da tüm SQLite ve PostgreSQL veritabanları, ayar dosyaları ve modeller yerel NAS cihazına otomatik şifreli yedeklenir.</p>
          </div>
        </div>

        <div class="card">
          <div class="card-header">🔧 MERKEZİ SERVİS KONTROLÜ (`farabi-servis`)</div>
          <div style="font-size: 9.5px; color: #475569;">
            <p style="margin: 0 0 4px 0;">Dashboard paneli (port 80) üzerinden sistem servislerini güvenle yönetmek için kısıtlı sudoer yetkisiyle çalışan <code>farabi-servis</code> betiği kullanılır.</p>
            <p style="margin: 0;">Ders saatlerinde (08:10–16:00) canlı dersi etkileyebilecek servislerin durdurulması çifte onay koruması (HTTP 409) ile engellenir.</p>
          </div>
        </div>
      </div>

      <!-- Dağıtım ve Sürüm Modeli -->
      <div class="card" style="margin-top: 4px;">
        <div class="card-header">📦 DAĞITIM VE SÜRÜM YÖNETİMİ DÖNGÜSÜ</div>
        <div style="font-size: 9.5px; color: #475569; line-height: 1.5;">
          <strong>Monorepo Yönetimi:</strong> Tüm projeler <code>/home/ata/farabi</code> altında versiyonlanır. Master dalına yapılan her commit canlı üretim kaynağıdır. Servislerin güncellenmesi <code>sudo systemctl restart &lt;servis&gt;</code> ile gerçekleşir. Akıllı tahtalarda ise yerel cron görevleri her gün ilk zil öncesinde GitHub üzerinden otomatik olarak en güncel kararlı sürüme senkronize olur.
        </div>
      </div>

      <!-- Resmi İmzalar ve Onay -->
      <div class="card" style="margin-top: 4px; background: #FFFFFF;">
        <div class="card-header">✍️ RESMİ ONAY VE SİSTEM MÜHENDİSLİĞİ İMZA BLOĞU</div>
        <div class="sign-grid">
          <div class="sign-box">
            <div class="sign-title">SİSTEM MİMARI & GELİŞTİRİCİ</div>
            <div class="sign-name">Atakan ÜNVER</div>
            <div style="font-size: 8px; color: #64748B;">Bilişim Teknolojileri & Sistem Yöneticisi</div>
            <div class="sign-space"></div>
            <div style="font-size: 7.5px; color: #94A3B8;">İmza / Tarih</div>
          </div>
          <div class="sign-box">
            <div class="sign-title">MÜDÜR YARDIMCISI</div>
            <div class="sign-name">Okul Yönetimi</div>
            <div style="font-size: 8px; color: #64748B;">İdari ve Teknik Koordinasyon</div>
            <div class="sign-space"></div>
            <div style="font-size: 7.5px; color: #94A3B8;">İmza / Tarih</div>
          </div>
          <div class="sign-box">
            <div class="sign-title">OKUL MÜDÜRÜ</div>
            <div class="sign-name">Kurum Onayı</div>
            <div style="font-size: 8px; color: #64748B;">Şehit Murat Ustaoğlu Anadolu Lisesi</div>
            <div class="sign-space"></div>
            <div style="font-size: 7.5px; color: #94A3B8;">Mühür / İmza</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <div>Farabi Ekosistemi Mimari Dokümantasyonu · Şehit Murat Ustaoğlu Anadolu Lisesi</div>
    <div>Sayfa 04 / 04</div>
  </div>
</div>

</body>
</html>
"""

def main():
    print(">>> 1/3: Farabi Sistem Mimarisi & Tanıtım HTML içeriği hazırlanıyor...")
    html_content = generate_html()
    TMP_HTML.write_text(html_content, encoding="utf-8")
    
    print(">>> 2/3: Google Chrome headless ile vektörel A4 PDF üretiliyor...")
    chrome_bin = "/usr/bin/google-chrome"
    if not Path(chrome_bin).exists():
        print(f"HATA: Chrome bulunamadı: {chrome_bin}", file=sys.stderr)
        sys.exit(1)
        
    cmd = [
        chrome_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={OUTPUT_PDF}",
        str(TMP_HTML)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"HATA: Chrome PDF üretemedi!", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
        
    if not OUTPUT_PDF.exists():
        print(f"HATA: Çıktı dosyası oluşmadı: {OUTPUT_PDF}", file=sys.stderr)
        sys.exit(1)
        
    size_kb = OUTPUT_PDF.stat().st_size / 1024
    print(f">>> 3/3: [BAŞARILI] PDF dosyası üretildi:")
    print(f"  Yol: {OUTPUT_PDF}")
    print(f"  Boyut: {size_kb:.1f} KB")

if __name__ == "__main__":
    main()
