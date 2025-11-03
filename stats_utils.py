# stats_utils.py
from __future__ import annotations
from typing import Dict, Iterable, Tuple, List
import pandas as pd

# Visningsrekkefølge + visningsnavn
STAT_ORDER: List[Tuple[str, str]] = [
    ("rows", "Linjer"),
    ("vouchers", "Bilag (unik)"),
    ("accounts", "Konto (unik)"),
    ("sum_net", "Sum (netto)"),
    ("sum_abs", "Sum (|beløp|)"),
    ("debet", "Debet"),
    ("kredit", "Kredit"),
    ("min", "Min"),
    ("p25", "P25"),
    ("median", "Median"),
    ("p75", "P75"),
    ("max", "Maks"),
    ("mean", "Snitt"),
    ("std", "Std.avvik"),
]

AMOUNT_KEYS = {k for k, _ in STAT_ORDER if k not in {"rows", "vouchers", "accounts"}}


def stats_to_long_df(stats: Dict[str, float], kolonnenavn: str = "Verdi") -> pd.DataFrame:
    """Enkel tabell med to kolonner: 'Nøkkel' + kolonnenavn (for 1 statistikk)."""
    rows = []
    for key, label in STAT_ORDER:
        rows.append({"Nøkkel": label, kolonnenavn: stats.get(key, 0.0)})
    return pd.DataFrame(rows)


def stats_to_wide_df(stats_all: Dict[str, float], stats_sel: Dict[str, float]) -> pd.DataFrame:
    """Tabell (Nøkkel, Alle, Markert) for Excel-ark."""
    rows = []
    for key, label in STAT_ORDER:
        rows.append({
            "Nøkkel": label,
            "Alle": stats_all.get(key, 0.0),
            "Markert": stats_sel.get(key, 0.0),
        })
    return pd.DataFrame(rows)
