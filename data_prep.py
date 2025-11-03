"""
data_prep.py
------------
Felles funksjon for å bygge et renset/regnet datasett fra brukerens kolonnevalg.
Brukes av både DatasetPane (GUI) og DataControllerCore (backend).

- Lager netto beløp (enten fra én kolonne eller Debet−Kredit)
- Støtter norsk/engelsk beløpsformat via io_utils.build_amount_series
- Standardiserer kontonummer (Int64), parser dato (datetime64)
- Dropper rader uten bilag/beløp
- Setter kolonnenavnet for beløp til "__BELØP__"

Return: (df_prepared: pd.DataFrame, cols_out: Columns)
"""

from __future__ import annotations
from typing import Tuple

import pandas as pd

from models import Columns, AmountMode
from io_utils import build_amount_series, extract_int_series, parse_date_series


def build_dataset_from_choice(
    df_src: pd.DataFrame,
    cols_choice: Columns,
    amount_mode: AmountMode,
) -> Tuple[pd.DataFrame, Columns]:
    if df_src is None or df_src.empty:
        return pd.DataFrame(), Columns()

    # Kopi og bygg netto beløp
    df = df_src.copy()
    net = build_amount_series(df, cols_choice, amount_mode)
    df["__BELØP__"] = net

    # Returner Columns som peker på standardisert beløp
    cols_out = Columns(**cols_choice.__dict__)
    cols_out.belop = "__BELØP__"

    # Standardiser kontonummer og dato hvis valgt & finnes
    if cols_out.konto and cols_out.konto in df.columns:
        df[cols_out.konto] = extract_int_series(df[cols_out.konto])
    if cols_out.dato and cols_out.dato in df.columns:
        df[cols_out.dato] = parse_date_series(df[cols_out.dato])

    # Dropp rader uten bilag/beløp
    df = df.dropna(subset=[cols_out.bilag, cols_out.belop])

    return df, cols_out
