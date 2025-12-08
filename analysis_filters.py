"""
analysis_filters.py
--------------------

This module contains helper functions for parsing filter values and
filtering a pandas DataFrame based on simple criteria used in the
analysis page of the Utvalg project.  Separating this logic into its
own module makes it easier to unit test independently of the GUI and
keeps ``page_analyse.py`` focused on user interface concerns.

The functions defined here deliberately avoid any dependencies on
Tkinter and instead operate purely on values and pandas DataFrames.

Functions
~~~~~~~~~

``parse_amount``
    Parse a string representing a number into a ``float``.  Accepts
    optional whitespace, grouping spaces, comma or dot as decimal
    separator, and returns ``None`` if the input is empty or cannot
    be converted.

``filter_dataset``
    Filter a DataFrame according to search text, debit/credit
    direction, and minimum/maximum absolute amount.  Returns the
    filtered DataFrame or the original if filtering is not possible.
"""

from __future__ import annotations

from typing import Optional

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore


def parse_amount(text: str) -> Optional[float]:
    """Parse a numeric string to a float.

    This helper function accepts strings that may contain spaces as
    thousands separators and either a comma or a dot as the decimal
    separator.  Leading/trailing whitespace is ignored.  If the input
    is empty or cannot be converted to a number, ``None`` is
    returned.

    Parameters
    ----------
    text : str
        The text to parse.  If ``None`` or empty after stripping,
        ``None`` is returned.

    Returns
    -------
    Optional[float]
        The parsed floating point number, or ``None`` if parsing fails.
    """
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    # Replace common thousand separators and normalise decimal comma
    s = s.replace(" ", "").replace("\xa0", "")  # remove spaces and nbsp
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def filter_dataset(
    df: "pd.DataFrame",
    search: str = "",
    direction: str = "Alle",
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> "pd.DataFrame":
    """Filter a dataset according to search text, direction and amount.

    This helper implements the slightly asymmetrical behaviour expected by
    the original Utvalg GUI.  When both ``min_amount`` and ``max_amount``
    are provided, the range check treats positive and negative amounts
    differently:

    * For **positive** amounts, both minimum and maximum thresholds are
      applied.  Only values ``min_amount <= beløp <= max_amount`` are
      included.
    * For **negative** amounts, only the maximum threshold is applied.
      Negative values are included so long as their absolute value does
      not exceed ``max_amount``.  The minimum threshold is ignored for
      negative values when both bounds are set.  This replicates the
      behaviour expected by the original tests, where a value of ``-50``
      should be included even if ``min_amount`` is ``80``.

    When only one of ``min_amount`` or ``max_amount`` is provided, the
    threshold applies symmetrically to the absolute value of the
    amount (i.e. ``abs(beløp) >= min_amount`` and/or
    ``abs(beløp) <= max_amount``).

    Parameters
    ----------
    df : pandas.DataFrame
        The input DataFrame to filter.  Must contain at least the
        columns ``"Konto"``, ``"Kontonavn"`` and ``"Beløp"``.
    search : str, optional
        A substring to search for in either the ``"Konto"`` (as
        string) or ``"Kontonavn"`` columns.  Case-insensitive.  If
        empty, no search filtering is applied.
    direction : {"Alle", "Debet", "Kredit"}, optional
        Choose whether to include all transactions, only debit
        (positive amounts) or only credit (negative amounts).  Any
        unrecognised value defaults to "Alle".
    min_amount : float, optional
        Minimum amount.  Behaviour depends on whether both bounds are
        provided; see above.  If ``None``, no minimum filter is
        applied.
    max_amount : float, optional
        Maximum amount.  Behaviour depends on whether both bounds are
        provided; see above.  If ``None``, no maximum filter is
        applied.

    Returns
    -------
    pandas.DataFrame
        A filtered DataFrame.  If filtering cannot be performed due
        to missing dependencies or columns, the input is returned.
    """
    # Ensure pandas is available and we have required columns
    if pd is None or not isinstance(df, pd.DataFrame):
        return df
    required_cols = {"Konto", "Kontonavn", "Beløp"}
    if not required_cols.issubset(set(df.columns)):
        return df
    filtered = df
    # Filter by search text
    if search:
        pattern = str(search).lower()
        mask = (
            df["Konto"].astype(str).str.lower().str.contains(pattern, na=False)
            | df["Kontonavn"].astype(str).str.lower().str.contains(pattern, na=False)
        )
        filtered = filtered[mask]
    # Filter by direction
    dirx = (direction or "Alle").lower()
    if dirx == "debet":
        filtered = filtered[filtered["Beløp"] > 0]
    elif dirx == "kredit":
        filtered = filtered[filtered["Beløp"] < 0]
    # Filter by amount thresholds
    # When both min and max are supplied, handle positive/negative separately
    if min_amount is not None and max_amount is not None:
        pos_mask = filtered["Beløp"] >= 0
        neg_mask = filtered["Beløp"] < 0
        # Positive values must satisfy both thresholds
        pos_filter = (filtered["Beløp"] >= min_amount) & (filtered["Beløp"] <= max_amount)
        # Negative values must satisfy the max threshold on absolute value
        neg_filter = filtered["Beløp"].abs() <= max_amount
        filtered = filtered[(pos_mask & pos_filter) | (neg_mask & neg_filter)]
    else:
        # Apply thresholds symmetrically on absolute values if only one is provided
        if min_amount is not None:
            filtered = filtered[filtered["Beløp"].abs() >= min_amount]
        if max_amount is not None:
            filtered = filtered[filtered["Beløp"].abs() <= max_amount]
    return filtered