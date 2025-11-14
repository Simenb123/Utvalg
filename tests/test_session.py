import pandas as pd

import session as session_mod
from models import Columns


def _make_df_and_cols():
    df = pd.DataFrame(
        {
            "Konto": ["3000", "4000"],
            "Kontonavn": ["Salg", "Annen inntekt"],
            "Bilag": ["1", "2"],
            "Dato": ["01.01.2024", "02.01.2024"],
            "Beløp": [1000.0, 200.0],
            "Tekst": ["Faktura 1", "Faktura 2"],
        }
    )
    cols = Columns(
        konto="Konto",
        kontonavn="Kontonavn",
        bilag="Bilag",
        dato="Dato",
        belop="Beløp",
        tekst="Tekst",
    )
    return df, cols


def test_set_and_get_dataset_updates_globals():
    df, cols = _make_df_and_cols()

    # Kall funksjonen vi tester
    session_mod.set_dataset(df, cols)

    # get_dataset() skal returnere de samme objektene
    got_df, got_cols = session_mod.get_dataset()
    assert got_df is df
    assert got_cols is cols

    # Det skal også finnes et globalt attribute 'dataset'
    assert hasattr(session_mod, "dataset")
    assert session_mod.dataset is df

    # has_dataset() skal nå være True
    assert session_mod.has_dataset() is True


def test_has_dataset_false_when_no_data(monkeypatch):
    # Nullstill interne globale variabler
    monkeypatch.setattr(session_mod, "_df", None, raising=False)
    monkeypatch.setattr(session_mod, "_cols", None, raising=False)

    # has_dataset() skal være False når det ikke er lastet noe
    assert session_mod.has_dataset() is False


def test_selection_global_dict_is_mutable_and_shared():
    # Sørg for ren start
    session_mod.SELECTION.clear()

    session_mod.SELECTION["3000"] = True
    session_mod.SELECTION["4000"] = False

    assert session_mod.SELECTION == {"3000": True, "4000": False}

    # Og endringer i samme dict skal være synlige (deler global state)
    ref = session_mod.SELECTION
    ref["3000"] = False
    assert session_mod.SELECTION["3000"] is False
