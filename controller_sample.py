# controller_sample.py
from __future__ import annotations
from typing import Iterable, List, Tuple
import pandas as pd

from models import Columns
from formatting import temp_xlsx_path, open_with_system


def frames_for_sample(df: pd.DataFrame, cols: Columns,
                      sample_ids: Iterable[str], accounts: Iterable[int]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bygger de tre rammene som tidligere: fullt, internt (kun valgte kontoer), summer pr. bilag."""
    c = cols
    sample_ids = set(str(x) for x in sample_ids)
    accounts = set(int(a) for a in accounts)

    fullt = df[df[c.bilag].astype(str).isin(sample_ids)].copy()
    internt = fullt[fullt[c.konto].astype("Int64").astype(int).isin(accounts)].copy()

    summer = (
        internt.groupby(c.bilag)[c.belop]
        .agg(Sum_i_valgte_kontoer="sum", Linjer_i_valgte_kontoer="count")
        .reset_index()
    )
    return fullt, internt, summer


def export_sample_to_excel(path: str, fullt: pd.DataFrame, internt: pd.DataFrame, summer: pd.DataFrame) -> None:
    """Skriver tre ark til angitt path."""
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        fullt.to_excel(xw, "Fullt_bilagsutvalg", index=False)
        internt.to_excel(xw, "Kun_valgte_kontoer", index=False)
        summer.to_excel(xw, "Bilag_summer", index=False)


def export_sample_to_temp_and_open(fullt: pd.DataFrame, internt: pd.DataFrame, summer: pd.DataFrame,
                                   prefix: str = "Bilag_uttrekk_") -> str:
    """Skriver til en midlertidig .xlsx og åpner i Excel. Returnerer filstien."""
    path = temp_xlsx_path(prefix=prefix)
    export_sample_to_excel(path, fullt, internt, summer)
    open_with_system(path)
    return path
