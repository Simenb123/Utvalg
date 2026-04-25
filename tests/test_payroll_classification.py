from __future__ import annotations

import importlib


def test_payroll_classification_split_modules_are_importable() -> None:
    modules = [
        "tests.test_payroll_classification_suggest",
        "tests.test_payroll_classification_classify",
        "tests.test_payroll_classification_catalog",
        "tests.test_payroll_classification_audit",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
