from __future__ import annotations

import ast
from pathlib import Path


def test_no_duplicate_test_function_names_per_file() -> None:
    tests_dir = Path(__file__).resolve().parent
    duplicates: list[str] = []

    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        seen: dict[str, int] = {}
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            if node.name in seen:
                duplicates.append(f"{path.name}:{seen[node.name]} and {node.lineno}: {node.name}")
            else:
                seen[node.name] = int(node.lineno)

    assert duplicates == []
