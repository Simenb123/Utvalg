from pathlib import Path


def test_selection_studio_recommendation_var_alias_exists() -> None:
    """SelectionStudio should provide _var_recommendation as alias to var_recommendation.

    This guards against AttributeError when older code paths still reference the
    underscored name.
    """

    src = Path("views_selection_studio_ui.py").read_text(encoding="utf-8")
    assert "_var_recommendation = self.var_recommendation" in src
