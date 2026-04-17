from __future__ import annotations

from pathlib import Path


MAX_LINES = 500


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def _targets(repo_root: Path) -> list[Path]:
    files: set[Path] = set()
    patterns = (
        "page_consolidation*.py",
        "consolidation/*.py",
        "consolidation_readiness*.py",
    )
    for pattern in patterns:
        files.update(repo_root.glob(pattern))
    files.add(repo_root / "consolidation_mapping_tab.py")
    files.add(repo_root / "consolidation_pdf_review_dialog.py")
    return sorted(path for path in files if path.is_file())


def test_consolidation_modules_stay_under_size_limit() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in _targets(repo_root):
        line_count = _count_lines(path)
        if line_count > MAX_LINES:
            offenders.append(f"{path.relative_to(repo_root)}: {line_count}")
    assert not offenders, "Modules over size limit:\n" + "\n".join(offenders)
