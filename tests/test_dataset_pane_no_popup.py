from __future__ import annotations

from types import SimpleNamespace

import pandas as pd


def test_build_dataset_clicked_suppresses_ready_popup(monkeypatch) -> None:
    import dataset_pane
    from dataset_pane_build import BuildResult
    from models import Columns

    pane = dataset_pane.DatasetPane.__new__(dataset_pane.DatasetPane)

    df = pd.DataFrame({"Konto": ["1000"], "Bilag": ["1"], "Beløp": [1.0]})
    cols = Columns(konto="Konto", bilag="Bilag", belop="Beløp")
    res = BuildResult(df=df, cols=cols)

    pane._gather_build_request = lambda: object()
    pane._on_error = None
    pane.loading = SimpleNamespace(
        run_async=lambda _msg, work, on_done, on_error: on_done(work())
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(dataset_pane, "build_dataset", lambda _req: res)
    monkeypatch.setattr(
        dataset_pane.DatasetPane,
        "_apply_build_result",
        lambda self, _res, *, update_ml, show_message: captured.update(
            {"update_ml": update_ml, "show_message": show_message}
        ),
    )

    dataset_pane.DatasetPane._build_dataset_clicked(pane)

    assert captured == {"update_ml": True, "show_message": False}
