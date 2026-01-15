from __future__ import annotations

from pathlib import Path

import pytest


def test_find_project_root_finds_app_py(tmp_path: Path) -> None:
    # Arrange: fake project root
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    import build_exe

    # Act
    root = build_exe.find_project_root(start=tmp_path)

    # Assert
    assert root == tmp_path


def test_write_runtime_hook_creates_file(tmp_path: Path) -> None:
    import build_exe

    hook = build_exe.write_runtime_hook_set_cwd(tmp_path)
    assert hook.exists()
    content = hook.read_text(encoding="utf-8")
    assert "os.chdir" in content
    assert "sys.executable" in content


def test_build_pyinstaller_args_contains_expected_flags(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    import build_exe

    opts = build_exe.BuildOptions(
        name="UtvalgTest",
        onefile=True,
        console=False,
        clean=True,
        dist_dir="dist_exe",
        work_dir="build_exe",
        extra_hidden_imports=["some_dynamic_mod"],
        extra_args=["--log-level=INFO"],
        dry_run=True,
    )
    hook = build_exe.write_runtime_hook_set_cwd(tmp_path)

    # Act
    args = build_exe.build_pyinstaller_args(tmp_path, opts, hook)

    # Assert (core flags)
    assert "--onefile" in args
    assert "--noconsole" in args
    assert any(a.startswith("--name=") and "UtvalgTest" in a for a in args)
    assert "--runtime-hook" in args
    assert str(hook) in args

    # Hidden imports
    # ui_main må alltid være med pga dynamisk import i app.py
    assert "--hidden-import" in args
    # sjekk at både ui_main og ekstra hidden import er med
    joined = " ".join(args)
    assert "ui_main" in joined
    assert "some_dynamic_mod" in joined

    # Entry script
    assert str(tmp_path / "app.py") == args[-1]


def test_run_build_calls_subprocess(monkeypatch, tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")

    import build_exe

    # Tving prosjektrot til vår tmp-mappe
    monkeypatch.setattr(build_exe, "find_project_root", lambda start=None: tmp_path)
    # Ikke krev at PyInstaller faktisk finnes i testmiljøet
    monkeypatch.setattr(build_exe, "ensure_pyinstaller_available", lambda: None)

    calls = {}

    def _fake_run(cmd, cwd=None, check=None):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["check"] = check
        return 0

    monkeypatch.setattr(build_exe.subprocess, "run", _fake_run)

    opts = build_exe.BuildOptions(name="UtvalgTest", dry_run=False)

    # Act
    exe_path = build_exe.run_build(opts)

    # Assert
    assert calls["check"] is True
    assert Path(calls["cwd"]) == tmp_path
    assert calls["cmd"][0]  # sys.executable
    assert calls["cmd"][1:3] == ["-m", "PyInstaller"]
    assert str(tmp_path / "app.py") in calls["cmd"]
    assert exe_path.name == "UtvalgTest.exe"


def test_ensure_pyinstaller_available_raises_when_missing(monkeypatch) -> None:
    import build_exe

    monkeypatch.setattr(build_exe, "is_pyinstaller_available", lambda: False)

    with pytest.raises(RuntimeError) as e:
        build_exe.ensure_pyinstaller_available()

    assert "pip install pyinstaller" in str(e.value).lower()
