from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from selection_studio.ui_logic import build_bilag_dataframe
from selection_studio.ui_widget_selection import run_selection


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _DummyNotebook:
    def __init__(self):
        self.selected = None

    def select(self, index):
        self.selected = index


def test_run_selection_refreshes_before_using_amount_filtered_population(monkeypatch) -> None:
    shown = {"info": [], "warning": [], "error": []}

    monkeypatch.setattr(
        "selection_studio.ui_widget_selection.messagebox.showinfo",
        lambda *args, **kwargs: shown["info"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        "selection_studio.ui_widget_selection.messagebox.showwarning",
        lambda *args, **kwargs: shown["warning"].append((args, kwargs)),
    )
    monkeypatch.setattr(
        "selection_studio.ui_widget_selection.messagebox.showerror",
        lambda *args, **kwargs: shown["error"].append((args, kwargs)),
    )

    # Stale state: before refresh, bilag 1 would incorrectly still be available.
    stale_df = pd.DataFrame(
        {
            "Bilag": [1, 2],
            "Dato": ["2025-01-01", "2025-01-02"],
            "Tekst": ["For liten", "Stor nok"],
            "Beløp": [255.36, 6837.60],
        }
    )
    fresh_df = stale_df.loc[stale_df["Bilag"] == 2].copy()

    studio = SimpleNamespace()
    studio._df_filtered = stale_df.copy()
    studio._bilag_df = build_bilag_dataframe(stale_df)
    studio._df_sample = pd.DataFrame()
    studio.var_sample_n = _DummyVar(1)
    studio.nb = _DummyNotebook()

    def _refresh_all():
        studio._df_filtered = fresh_df.copy()
        studio._bilag_df = build_bilag_dataframe(fresh_df)

    studio._refresh_all = _refresh_all
    studio._get_tolerable_error_value = lambda: 0.0
    studio._compute_recommendation = lambda: SimpleNamespace(n_total_recommended=1)
    studio._draw_stratified_sample = lambda remaining, n: remaining["Bilag"].head(n).tolist()
    studio._stratify_remaining_values = lambda values: ([], {}, pd.DataFrame())
    studio._populate_tree = lambda df: setattr(studio, "_populated_df", df.copy())

    run_selection(studio)

    assert shown["error"] == []
    assert list(studio._df_sample["Bilag"]) == [2]
    assert list(studio._populated_df["Bilag"]) == [2]
    assert studio.nb.selected == 0
