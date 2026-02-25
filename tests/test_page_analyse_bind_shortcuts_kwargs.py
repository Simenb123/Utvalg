from __future__ import annotations


class _DummyWidget:
    """Minimal widget stub for shortcut binding tests.

    We do *not* rely on tkinter in these tests.
    """

    def __init__(self) -> None:
        self.bound_sequences: list[str] = []

    def bind(self, sequence: str, _func) -> None:  # noqa: ANN001
        self.bound_sequences.append(sequence)


class _RaisingWidget:
    def bind(self, _sequence: str, _func) -> None:  # noqa: ANN001
        raise RuntimeError("boom")


def test_bind_shortcuts_accepts_kwargs_and_binds() -> None:
    """Happy path.

    Regression test for the Windows failure described in the handover:
    page_analyse_ui.build_ui() calls AnalysePage._bind_shortcuts(...) with
    keyword args (cmb_dir/spn_max). AnalysePage must accept these.
    """

    import page_analyse

    AnalysePage = page_analyse.AnalysePage

    page = AnalysePage.__new__(AnalysePage)  # avoid Tk init in tests

    ent_search = _DummyWidget()
    ent_min = _DummyWidget()
    ent_max = _DummyWidget()
    cmb_dir = _DummyWidget()
    spn_max = _DummyWidget()

    # Should not raise TypeError for unexpected keyword arguments.
    AnalysePage._bind_shortcuts(
        page,
        ent_search=ent_search,
        ent_min=ent_min,
        ent_max=ent_max,
        cmb_dir=cmb_dir,
        spn_max=spn_max,
        future_kw="ignored",
    )

    for w in (ent_search, ent_min, ent_max, cmb_dir, spn_max):
        assert "<Control-f>" in w.bound_sequences
        assert "<Control-F>" in w.bound_sequences
        assert "<Escape>" in w.bound_sequences


def test_bind_shortcuts_ignores_widget_bind_errors() -> None:
    """Typical error case.

    If one widget's .bind raises, AnalysePage._bind_shortcuts must not crash.
    """

    import page_analyse

    AnalysePage = page_analyse.AnalysePage

    page = AnalysePage.__new__(AnalysePage)  # avoid Tk init in tests

    ok = _DummyWidget()
    bad = _RaisingWidget()

    # Should not raise even if some widgets fail binding.
    AnalysePage._bind_shortcuts(
        page,
        ent_search=ok,
        ent_min=ok,
        ent_max=ok,
        cmb_dir=bad,
        spn_rows=bad,
    )

    assert "<Control-f>" in ok.bound_sequences
    assert "<Escape>" in ok.bound_sequences
