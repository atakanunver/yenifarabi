#!/bin/sh
# Atos adı (2026-10-05): Open WebUI, WEBUI_NAME verilince sonuna " (Open WebUI)" ekler
# (open_webui/env.py). Lisans ≤50 kullanıcıda marka değişikliğine izin veriyor (README).
# atos-ad.conf drop-in her açılışta çalıştırır — pip upgrade sonrası da kalıcı. İdempotent.
ENV=/opt/open-webui/venv/lib/python3.12/site-packages/open_webui/env.py
sed -i "s/^    WEBUI_NAME += .*(Open WebUI).*\$/    pass  # Atos: marka eki kaldirildi (webui-tema\/atos_ad_yama.sh)/" "$ENV"
