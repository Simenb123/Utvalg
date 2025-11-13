import tkinter as tk
import pandas as pd

from page_analyse import AnalysePage
from session import set_dataset
from models import Columns


def _make_dummy_dataset() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Konto": ["3000", "3000", "4000"],
            "Kontonavn": ["Salg", "Salg", "Annen inntekt"],
            "Bilag": ["1", "2", "3"],
            "Dato": ["01.01.2024", "02.01.2024", "03.01.2024"],
            "Beløp": [1000.0, 200.0, 500.0],
            "Tekst": ["Faktura 1", "Faktura 2", "Faktura 3"],
        }
    )


def test_analysepage_refresh_from_session_loads_dataset():
    # Sett opp globalt dataset i session
    df = _make_dummy_dataset()
    cols = Columns(konto="Konto", kontonavn="Kontonavn", bilag="Bilag", belop="Beløp", dato="Dato", tekst="Tekst")
    set_dataset(df, cols)

    # Opprett en skjult Tk-root slik at GUI-komponenter kan lages
    root = tk.Tk()
    root.withdraw()

    try:
        page = AnalysePage(root, controller=None, bus=None)

        # Viktig: metoden skal finnes og kunne kalles uten feil
        assert hasattr(page, "refresh_from_session")
        assert callable(page.refresh_from_session)

        page.refresh_from_session()

        # Etter refresh forventer vi at _df er satt og har samme lengde som df
        assert hasattr(page, "_df")
        assert isinstance(page._df, pd.DataFrame)
        assert len(page._df) == len(df)

    finally:
        # Rydd opp GUI
        root.destroy()
