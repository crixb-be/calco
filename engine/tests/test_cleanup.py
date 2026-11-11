from pathlib import Path

from docforge_engine.core.cleanup import purge_temp_artifacts


def test_purge_temp_artifacts_only_removes_owned_root(tmp_path: Path):
    root = tmp_path / "DocForge"
    root.mkdir()
    (root / ".pytest-tmp").mkdir()
    (root / "leftover.bin").write_bytes(b"x")

    assert purge_temp_artifacts(root) == 2
    assert not root.exists()


def test_purge_temp_artifacts_does_not_touch_unowned_directory(tmp_path: Path):
    root = tmp_path / "OtherApp"
    root.mkdir()
    (root / "keep.txt").write_text("keep", encoding="utf-8")

    assert purge_temp_artifacts(root) == 0
    assert (root / "keep.txt").is_file()
