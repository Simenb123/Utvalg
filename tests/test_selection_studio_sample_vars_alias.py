from pathlib import Path


def test_selectionstudio_sample_var_aliases_present_if_used() -> None:
    """Guard against runtime AttributeError if code uses _var_sample_text/_var_sample_n.

    The SelectionStudio widget historically used underscored tkinter vars.
    If implementation still references those names, ensure they're defined.
    """

    root = Path(__file__).resolve().parents[1]
    src = (root / "views_selection_studio_ui.py").read_text(encoding="utf-8")

    if "self._var_sample_text" in src:
        assert "self._var_sample_text =" in src

    if "self._var_sample_n" in src:
        assert "self._var_sample_n =" in src
