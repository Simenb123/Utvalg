import importlib


def test_models_exposes_scopeconfig_and_columns():
    models = importlib.import_module("models")
    assert hasattr(models, "Columns")
    assert hasattr(models, "ScopeConfig")

    ScopeConfig = getattr(models, "ScopeConfig")
    cfg = ScopeConfig()

    # Sjekk at de viktigste feltene finnes (vi bryr oss mest om at import ikke feiler)
    assert hasattr(cfg, "name")
    assert hasattr(cfg, "accounts_spec")
    assert hasattr(cfg, "direction")
    assert hasattr(cfg, "basis")
    assert hasattr(cfg, "min_amount")
    assert hasattr(cfg, "max_amount")
    assert hasattr(cfg, "date_from")
    assert hasattr(cfg, "date_to")


def test_controller_export_imports_after_scopeconfig_added():
    # Dette er selve “regresjonstesten” som sikrer at pytest ikke stopper i collection
    importlib.import_module("controller_export")
