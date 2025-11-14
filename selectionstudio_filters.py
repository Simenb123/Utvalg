import pandas as pd
from typing import Tuple, Optional


def _parse_number(value: str) -> Optional[float]:
    """Parse et norsk/engelsk tall fra tekst.

    Tom streng eller ugyldig input gir None i stedet for exception.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Fjern mellomrom (tusenskilletegn) og bruk punktum som desimal
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def filter_selectionstudio_dataframe(
    df_base: pd.DataFrame,
    direction: str,
    min_value: str,
    max_value: str,
    use_abs: bool,
) -> Tuple[pd.DataFrame, dict]:
    """Filtrer grunnlaget i SelectionStudio på retning og beløpsintervall.

    Parametre
    ---------
    df_base : DataFrame
        Ufiltrert grunnlag (kontointervall fra Utvalg).
    direction : {"Alle", "Debet", "Kredit"}
        Retning basert på fortegn i Beløp.
    min_value, max_value : str
        Tekstverdier slik brukeren taster dem inn (norsk/engelsk format).
    use_abs : bool
        Hvis True filtreres på absoluttbeløp; ellers på netto beløp.

    Returnerer
    ----------
    df : DataFrame
        Filtrert DataFrame.
    summary : dict
        Sammendrag med nøkler: N, S, N0, S0, removed_n, removed_s.
    """
    if df_base is None or df_base.empty:
        empty = df_base.iloc[0:0].copy() if df_base is not None else pd.DataFrame()
        return empty, {
            "N": 0,
            "S": 0.0,
            "N0": 0,
            "S0": 0.0,
            "removed_n": 0,
            "removed_s": 0.0,
        }

    df = df_base.copy()

    # Retningsfilter
    bel = pd.to_numeric(df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
    if direction == "Debet":
        mask = bel > 0
        df = df[mask]
        bel = bel.loc[df.index]
    elif direction == "Kredit":
        mask = bel < 0
        df = df[mask]
        bel = bel.loc[df.index]

    # Beløpsfilter (min/max)
    bel_for_limit = bel.abs() if use_abs else bel
    min_val = _parse_number(min_value)
    max_val = _parse_number(max_value)

    if min_val is not None:
        mask = bel_for_limit >= min_val
        df = df[mask]
        bel_for_limit = bel_for_limit.loc[df.index]

    if max_val is not None:
        mask = bel_for_limit <= max_val
        df = df[mask]
        bel_for_limit = bel_for_limit.loc[df.index]

    # Sammendrag for info-etiketten i GUI
    N = len(df)
    S = pd.to_numeric(df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()
    N0 = len(df_base)
    S0 = pd.to_numeric(df_base.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()
    removed_n = N0 - N
    removed_s = S0 - S

    summary = {
        "N": int(N),
        "S": float(S),
        "N0": int(N0),
        "S0": float(S0),
        "removed_n": int(removed_n),
        "removed_s": float(removed_s),
    }

    return df, summary
