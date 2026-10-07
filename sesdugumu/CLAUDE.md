# sesdugumu/ — farabi2-ses (Farabi 2.0 yerel ses düğümü)

Bilgehan (`bilgehan.local`) üzerinde koşan tek süreçli FastAPI servisi:
`/stt` (faster-whisper large-v3-turbo, int8) + `/tts` (Chatterbox Multilingual
+ hızlı T3, ses `nisan_kumru_2.wav`, 0.7/0.3/0.75) + `/saglik`. Port **8060**.
Tasarım: `docs/superpowers/specs/2026-10-07-farabi2-yerel-ses-design.md`.
Yalnızca `v2-yerel-ses` dalı / pilot; master'daki tahtalar bunu kullanmaz.

## Kurallar
- GPU: `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=1` (RTX 3060).
  GPU0 (1660 Ti) ve `farabi-embed` (:8040, `/opt/farabi-embed`) DOKUNULMAZ.
- Debian 192.168.23.251'deki Chatterbox (ebys) bu servisle ilgisiz — dokunma.
- venv: `~/chatterbox-tts/.venv` (uv, py3.12, torch 2.6.0+cu124). Paket
  dosyaları düzenlenmez; hız `hizli_t3.py` ile (monkeypatch).
- `hizli_t3.py` ve `kuyruk.py` kopyadır (kaynak: Bilgehan
  `~/chatterbox-tts/hiz/hizli_t3.py`, Debian `/opt/chatterbox-tts/kuyruk.py`).
- `kaliplar.py` ile `client/core/kaliplar.py` BİREBİR aynı olmalı
  (`client/tests/test_yerel_oturum.py::test_kaliplar_sunucuyla_ayni`).
- Model indirme proxy'den: `HF_HUB_DISABLE_XET=1` şart (Xet paralel parçaları
  okul proxy'sinde kopuyor); proxy yalnızca komuta export edilir.

## Komutlar (Farabi'den)
```bash
sesdugumu/test_uzak.sh                 # saf testler (Bilgehan venv'inde)
sesdugumu/test_uzak.sh -m gpu          # gerçek modellerle (servis DURDURULMUŞKEN — VRAM)
! sesdugumu/kur.sh                     # kurulum / yeniden başlatma (sudo şifresi)
ssh ata@bilgehan.local journalctl -u farabi2-ses -n 100
curl -s http://bilgehan.local:8060/saglik
```
Git: worktree sparse-checkout `sesdugumu/`'yu kapsamıyor → `git add --sparse sesdugumu`.
