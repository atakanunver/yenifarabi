# Giriş IP Eşiğini Artırma Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `giris_ip` hareket eşiğini `0.018`'den `0.025`'e yükseltmek.

**Architecture:** Yalnız kamera ayarındaki `giris_ip.esik` değeri değişecek. Önce canlı JSON yedeklenecek, sonra ayar başlangıçta yüklendiği için kullanıcı onayıyla `farabi-hareket` yeniden başlatılacak.

**Tech Stack:** JSON, Python 3 stdlib.

**Spec:** `docs/superpowers/specs/2026-11-14-giris-ip-threshold-design.md`

## Global Constraints

- Yalnız `giris_ip` ayarı değişecek; diğer kamera eşikleri ve algılama kodu aynı kalacak.
- Mevcut ayarın yedeği değişiklikten önce alınacak.
- Kullanıcının açık onayıyla canlı `farabi-hareket` servisi restart edilecek.

## Review Focus

- Geçersiz JSON servis ayarını bozabilir — `json.load` doğrulaması yapılacak.
- Değişiklik yanlışlıkla diğer kameraları etkileyebilir — tüm kamera eşiklerinin önce/sonra karşılaştırması yapılacak.
- Ayar bellekte eski kalabilir — servis restart sonrası `active` ve yeni başlangıç logu doğrulanmalı.

---

### Task 1: Giriş kamerası eşiğini güncelle

**Files:**
- Modify: `kameralar/hareket/ayar.json` (`kameralar.giris_ip.esik`)
- Create backup: mevcut dosyanın aynı dizinde tarih etiketli kopyası

**Interfaces:**
- Consumes: `kameralar/hareket/ayar.json` mevcut ayarları.
- Produces: geçerli JSON; `giris_ip.esik == 0.025`; diğer kamera ayarları değişmeden kalır.

- [ ] **Step 1: Ayarın başlangıçta belleğe alındığını doğrula**

Run: `rg -n 'kameralar = ayar_oku|target=izle' kameralar/hareket/hareket.py`
Expected: `main()` kamera ayarlarını bir kez okuyup `izle` iş parçacıklarına geçiriyor; bu nedenle restart gerekiyor.

- [ ] **Step 2: Önceki ayar dosyasını yedekle**

Yedek adı `ayar.json.2026-11-14.bak` olsun; hedef varsa üzerine yazmadan dur.

- [ ] **Step 3: Yalnız `kameralar.giris_ip.esik` değerini `0.025` yap**

Diğer alanlara dokunma.

- [ ] **Step 4: JSON ve kapsamı doğrula**

Run: `kameralar/hareket/venv/bin/python -c 'import json; p="kameralar/hareket/ayar.json"; d=json.load(open(p)); assert d["kameralar"]["giris_ip"]["esik"] == 0.025; print("JSON OK; giris_ip esik=0.025")'`
Expected: `JSON OK; giris_ip esik=0.025`.

Diğer kamera eşiklerini yedek dosyayla karşılaştır ve yalnızca `giris_ip.esik` farkı bulunduğunu doğrula.

- [ ] **Step 5: Kullanıcının onayladığı hareket servisini yeniden başlat ve doğrula**

Run: `sudo systemctl restart farabi-hareket.service && systemctl is-active farabi-hareket.service`
Expected: `active`; ardından `journalctl -u farabi-hareket.service --since '-2 minutes' --no-pager` içinde yeni başlangıç satırı.
