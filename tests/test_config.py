from claude_dev_watch.config import load_env


def test_env_file_fills_unset_and_empty(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("A=from_file\nB=from_file\nC=from_file\nD=\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("A", raising=False)
    monkeypatch.setenv("B", "")  # シェルに残った空の変数
    monkeypatch.setenv("C", "from_shell")
    monkeypatch.delenv("D", raising=False)
    load_env()
    import os

    assert os.environ["A"] == "from_file"
    assert os.environ["B"] == "from_file"
    assert os.environ["C"] == "from_shell"
    assert "D" not in os.environ
