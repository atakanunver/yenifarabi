"""yoklama_al: tam klonda <repo>/tahtayoklama, sparse-checkout tahtada ~/tahtayoklama."""

from pathlib import Path

from actions import yoklama_al as ya


def _kur(tmp_path, monkeypatch, venvli):
    ev = tmp_path / "ev"
    (ev / "tahtayoklama").mkdir(parents=True)
    (ev / "tahtayoklama" / "yoklama.py").write_text("")
    if venvli:
        (ev / "tahtayoklama" / "venv" / "bin").mkdir(parents=True)
        (ev / "tahtayoklama" / "venv" / "bin" / "python").write_text("")
    monkeypatch.setattr(ya, "BASE_DIR", tmp_path / "farabi" / "client")
    monkeypatch.setattr(Path, "home", lambda: ev)
    cagri = []
    monkeypatch.setattr(ya.subprocess, "Popen", lambda argv, **_: cagri.append(argv))
    return ev, cagri


def test_sparse_tahtada_ev_dizinini_ve_kendi_venvini_bulur(tmp_path, monkeypatch):
    ev, cagri = _kur(tmp_path, monkeypatch, venvli=True)
    assert "açıyorum" in ya.yoklama_al()
    assert cagri == [[str(ev / "tahtayoklama/venv/bin/python"), str(ev / "tahtayoklama/yoklama.py")]]


def test_venv_yoksa_farabi_pythonu(tmp_path, monkeypatch):
    _, cagri = _kur(tmp_path, monkeypatch, venvli=False)
    ya.yoklama_al()
    assert cagri[0][0] == ya.sys.executable


def test_hic_yoksa_bulunamadi(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "BASE_DIR", tmp_path / "a" / "client")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "bos")
    assert "bulunamadı" in ya.yoklama_al()
