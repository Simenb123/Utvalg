from __future__ import annotations

import views_settings


def test_format_active_baseline_label_json() -> None:
    assert (
        views_settings.format_active_baseline_label("regnskapslinje", "json")
        == "Aktiv regnskapslinje-baseline: JSON"
    )


def test_format_active_baseline_label_excel() -> None:
    assert (
        views_settings.format_active_baseline_label("kontoplan", "excel")
        == "Aktiv kontoplan-baseline: Excel"
    )


def test_format_active_baseline_label_missing() -> None:
    assert (
        views_settings.format_active_baseline_label("regnskapslinje", "missing")
        == "Aktiv regnskapslinje-baseline: mangler"
    )


def test_format_active_baseline_label_unknown_falls_back() -> None:
    assert views_settings.format_active_baseline_label("x", "noe-rart").endswith("ukjent")
    assert views_settings.format_active_baseline_label("x", "").endswith("ukjent")


def test_build_replace_baseline_confirm_text_includes_replace_language() -> None:
    text = views_settings.build_replace_baseline_confirm_text("regnskapslinje")
    assert "erstatte" in text.lower()
    assert "regnskapslinje" in text.lower()
    assert "Fortsette" in text


def test_import_regnskapslinjer_prompts_confirmation_before_replacing() -> None:
    """Settings-importen må be om bekreftelse før den overskriver JSON-baseline."""

    import inspect

    source = inspect.getsource(views_settings.SettingsView._import_regnskapslinjer)
    assert "askyesno" in source
    assert "build_replace_baseline_confirm_text" in source


def test_import_kontoplan_mapping_prompts_confirmation_before_replacing() -> None:
    import inspect

    source = inspect.getsource(views_settings.SettingsView._import_kontoplan_mapping)
    assert "askyesno" in source
    assert "build_replace_baseline_confirm_text" in source


def test_settings_view_uses_importer_og_erstatt_button_text() -> None:
    import inspect

    source = inspect.getsource(views_settings.SettingsView.__init__)
    # Begge import-knappene skal si 'Importer og erstatt…'
    assert source.count("Importer og erstatt") >= 2
