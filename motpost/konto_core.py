"""Motpostanalyse – kjernefunksjoner (uten GUI).

Denne modulen inneholder:
  - bygging av motpost-datasett (pandas)
  - beregninger og oppsummeringer

GUI-koden ligger i :mod:`views_motpost_konto`.

Vi skiller dette ut for å holde business-logikk og eksport
adskilt fra Tkinter-visningen, slik at koden blir enklere
å teste og videreutvikle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Iterable, Optional

import pandas as pd



from formatting import fmt_amount
from .utils import _bilag_str, _konto_str, _safe_float


# -----------------------------
# Data modeller
# -----------------------------


@dataclass(frozen=True)
class MotpostData:
    selected_accounts: tuple[str, ...]
    bilag_count: int
    selected_sum: float
    control_sum: float
    df_motkonto: pd.DataFrame
    df_selected: pd.DataFrame
    df_scope: pd.DataFrame

    # How to interpret the "selected side" when summing amounts for the selected accounts.
    # Expected values: "Alle", "Debet", "Kredit".
    selected_direction: str = "Alle"

    # Lazy cache for bilagsdetaljer (1 rad per bilag per motkonto) brukt i eksport / tester.
    _df_details_cache: Optional[pd.DataFrame] = field(default=None, init=False, repr=False)

    @property
    def df_summary(self) -> pd.DataFrame:
        """Bakoverkompatibel alias for pivoten over motkonto."""
        df = self.df_motkonto
        if df is None:
            return pd.DataFrame()
        # Legg på evt. alias-kolonner brukt i eldre tester, uten å påvirke UI/Excel.
        if "SumBeløp" not in df.columns and "Sum" in df.columns:
            df = df.copy()
            df["SumBeløp"] = df["Sum"]
        if "AntallBilag" not in df.columns and "Antall bilag" in df.columns:
            df = df.copy()
            df["AntallBilag"] = df["Antall bilag"]
        return df

    @property
    def df_details(self) -> pd.DataFrame:
        """Bakoverkompatibel: bilagsdetaljer per (bilag, motkonto) i scope."""
        if self._df_details_cache is None:
            df = build_bilag_details_all(self)
            object.__setattr__(self, "_df_details_cache", df)
        return self._df_details_cache


def _to_datetime(value: Any) -> Optional[datetime]:
    """Best effort-konvertering til datetime.

    Viktig: pandas.NaT er (overraskende) en instans av datetime, så vi må
    eksplisitt behandle NaT/NaN som tom verdi før vi sjekker isinstance(..., datetime).
    """
    if value is None:
        return None

    # Håndter NaN/NaT (og andre pandas "missing") tidlig
    try:
        is_na = pd.isna(value)
        if isinstance(is_na, bool) and is_na:
            return None
    except Exception:
        # pd.isna kan feile for enkelte typer; da forsøker vi videre
        pass

    if isinstance(value, datetime):
        return value

    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
        if isinstance(ts, datetime):
            return ts
        return None
    except Exception:
        return None


def _fmt_date_ddmmyyyy(value: Any) -> str:
    dt = _to_datetime(value)
    if dt is None:
        return ""
    # Ekstra sikkerhet: dt kan i sjeldne tilfeller være NaT-likevel
    try:
        is_na = pd.isna(dt)
        if isinstance(is_na, bool) and is_na:
            return ""
    except Exception:
        pass
    try:
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return ""


def _fmt_percent_points(value: Any, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        v = float(value)
    except Exception:
        return ""
    fmt = f"{{:.{decimals}f}}".format(v)
    # Norsk: komma som desimal
    fmt = fmt.replace(".", ",")
    return f"{fmt} %"


def _first_non_empty(series: pd.Series) -> Any:
    for v in series.tolist():
        if v is None:
            continue
        if isinstance(v, float) and pd.isna(v):
            continue
        s = str(v).strip()
        if s != "" and s.lower() != "nan":
            return v
    return None


def _unique_join(values: Iterable[str]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = str(v).strip()
        if s == "" or s.lower() == "nan":
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return ", ".join(out)


# -----------------------------
# Bygg analysegrunnlag
# -----------------------------


def build_motpost_data(
    df_all: pd.DataFrame,
    selected_accounts: set[str] | Iterable[str],
    *,
    selected_direction: str = "Alle",
) -> MotpostData:
    """Bygger datagrunnlag for motpostanalyse.

    Forventede kolonner i df_all (minimum):
      - Bilag
      - Konto
      - Beløp

    Ekstra (valgfritt):
      - Kontonavn, Dato, Tekst
    """

    selected_set = {_konto_str(k) for k in selected_accounts}
    selected_tuple = tuple(sorted(selected_set))

    if df_all is None or df_all.empty:
        empty = pd.DataFrame()
        return MotpostData(
            selected_accounts=selected_tuple,
            bilag_count=0,
            selected_sum=0.0,
            selected_direction=selected_direction,
            control_sum=0.0,
            df_motkonto=empty,
            df_selected=empty,
            df_scope=empty,
        )

    required = {"Bilag", "Konto", "Beløp"}
    missing = required - set(df_all.columns)
    if missing:
        # Returner tomt grunnlag hvis essensielle kolonner mangler
        empty = pd.DataFrame()
        return MotpostData(
            selected_accounts=selected_tuple,
            bilag_count=0,
            selected_sum=0.0,
            selected_direction=selected_direction,
            control_sum=0.0,
            df_motkonto=empty,
            df_selected=empty,
            df_scope=empty,
        )

    df = df_all.copy()

    # Normaliser nøkler
    df["Bilag_str"] = df["Bilag"].map(_bilag_str)
    df["Konto_str"] = df["Konto"].map(_konto_str)

    # Beløp som float
    df["Beløp_num"] = df["Beløp"].map(_safe_float)

    # Dato (kan være tom)
    if "Dato" in df.columns:
        df["Dato_dt"] = pd.to_datetime(df["Dato"], errors="coerce")
    else:
        df["Dato_dt"] = pd.NaT

    # Scope: bilag som inneholder minst én valgt konto
    df_sel = df[df["Konto_str"].isin(selected_set)].copy()

    # Retning filter for valgte kontoer (typisk: "Kredit" for 3xxx).
    dir_norm = (selected_direction or "Alle").strip().lower()
    if dir_norm in {"debet", "debit"}:
        df_sel = df_sel[df_sel["Beløp_num"] > 0]
    elif dir_norm in {"kredit", "credit"}:
        df_sel = df_sel[df_sel["Beløp_num"] < 0]
    bilag_scope = sorted(df_sel["Bilag_str"].dropna().unique().tolist())

    if not bilag_scope:
        empty = pd.DataFrame()
        return MotpostData(
            selected_accounts=selected_tuple,
            bilag_count=0,
            selected_sum=0.0,
            selected_direction=selected_direction,
            control_sum=0.0,
            df_motkonto=empty,
            df_selected=empty,
            df_scope=empty,
        )

    df_scope = df[df["Bilag_str"].isin(set(bilag_scope))].copy()

    selected_sum = float(df_sel["Beløp_num"].sum())
    control_sum = float(df_scope["Beløp_num"].sum())
    bilag_count = int(len(bilag_scope))

    # Pivot for valgte kontoer
    df_selected_pivot = (
        df_sel.groupby("Konto_str", dropna=False)
        .agg(
            Kontonavn=("Kontonavn", _first_non_empty) if "Kontonavn" in df_sel.columns else ("Konto_str", lambda s: ""),
            Sum=("Beløp_num", "sum"),
            Antall_bilag=("Bilag_str", pd.Series.nunique),
        )
        .reset_index()
        .rename(columns={"Konto_str": "Konto", "Antall_bilag": "Antall bilag"})
    )
    df_selected_pivot["% andel"] = (
        (df_selected_pivot["Sum"] / selected_sum * 100.0) if selected_sum != 0 else 0.0
    )
    df_selected_pivot = df_selected_pivot[["Konto", "Kontonavn", "Sum", "% andel", "Antall bilag"]]
    df_selected_pivot = df_selected_pivot.sort_values(by="Sum", key=lambda s: s.abs(), ascending=False)

    # Pivot for motkontoer (alle andre kontoer i scope)
    df_mot = df_scope[~df_scope["Konto_str"].isin(selected_set)].copy()

    df_mot_pivot = (
        df_mot.groupby("Konto_str", dropna=False)
        .agg(
            Kontonavn=("Kontonavn", _first_non_empty) if "Kontonavn" in df_mot.columns else ("Konto_str", lambda s: ""),
            Sum=("Beløp_num", "sum"),
            Antall_bilag=("Bilag_str", pd.Series.nunique),
        )
        .reset_index()
        .rename(columns={"Konto_str": "Motkonto", "Antall_bilag": "Antall bilag"})
    )
    df_mot_pivot["% andel"] = ((df_mot_pivot["Sum"] / selected_sum * 100.0) if selected_sum != 0 else 0.0)
    df_mot_pivot = df_mot_pivot[["Motkonto", "Kontonavn", "Sum", "% andel", "Antall bilag"]]
    df_mot_pivot = df_mot_pivot.sort_values(by="Sum", key=lambda s: s.abs(), ascending=False)

    # df_scope: behold standard kolonnenavn for videre bruk.
    # NB: Dersom kildedata allerede har en "Beløp"-kolonne (ofte tekst), vil en rename
    # gi duplikatnavn. Vi overstyrer derfor eksplisitt og fjerner hjelpekollonnen.
    df_scope["Beløp"] = df_scope["Beløp_num"]
    df_scope = df_scope.drop(columns=["Beløp_num"], errors="ignore")

    return MotpostData(
        selected_accounts=selected_tuple,
        bilag_count=bilag_count,
        selected_sum=selected_sum,
        selected_direction=selected_direction,
        control_sum=control_sum,
        df_motkonto=df_mot_pivot.reset_index(drop=True),
        df_selected=df_selected_pivot.reset_index(drop=True),
        df_scope=df_scope.reset_index(drop=True),
    )


def build_bilag_details(data: MotpostData, motkonto: str) -> pd.DataFrame:
    """Bygger bilagsliste for en gitt motkonto."""

    if data.df_scope is None or data.df_scope.empty:
        return pd.DataFrame()

    motkonto = _konto_str(motkonto)
    selected_set = set(data.selected_accounts)

    df = data.df_scope.copy()
    df["Bilag_str"] = df["Bilag"].map(_bilag_str)
    df["Konto_str"] = df["Konto"].map(_konto_str)

    # Bilag som inneholder motkonto
    df_m = df[df["Konto_str"] == motkonto]
    if df_m.empty:
        return pd.DataFrame()
    bilag_set = set(df_m["Bilag_str"].unique().tolist())

    rows: list[dict[str, Any]] = []
    for bilag in sorted(bilag_set):
        df_b = df[df["Bilag_str"] == bilag]
        sel_vals = df_b[df_b["Konto_str"].isin(selected_set)]["Beløp"].map(_safe_float)
        dir_norm = (data.selected_direction or "Alle").strip().lower()
        if dir_norm.startswith("deb"):
            selected_sum = float(sel_vals[sel_vals > 0].sum())
        elif dir_norm.startswith("kre") or dir_norm.startswith("cri"):
            selected_sum = float(sel_vals[sel_vals < 0].sum())
        else:
            selected_sum = float(sel_vals.sum())
        mot_sum = float(df_b[df_b["Konto_str"] == motkonto]["Beløp"].map(_safe_float).sum())
        kontoer = _unique_join(sorted({_konto_str(x) for x in df_b["Konto"].tolist()}))
        dato = _first_non_empty(df_b["Dato"].astype(object)) if "Dato" in df_b.columns else None
        tekst = _first_non_empty(df_b["Tekst"].astype(object)) if "Tekst" in df_b.columns else None
        rows.append(
            {
                "Bilag": bilag,
                "Dato": _to_datetime(dato),
                "Tekst": tekst or "",
                "Beløp (valgte kontoer)": selected_sum,
                "Motbeløp": mot_sum,
                "Kontoer i bilag": kontoer,
            }
        )

    return pd.DataFrame(rows)



def build_bilag_details_all(data: MotpostData) -> pd.DataFrame:
    """Bygger bilagsdetaljer for *alle* motkontoer i scope.

    Returnerer 1 rad per (bilag, motkonto) med bl.a. sum for valgte kontoer og motbeløp.
    Denne brukes i Excel-eksport når ingen motkonto er valgt, og som bakoverkompatibel `df_details`.
    """
    df = data.df_scope
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "Bilag_key",
                "Bilag",
                "Dato",
                "Tekst",
                "Motkonto",
                "Motkontonavn",
                "Beløp (valgte kontoer)",
                "Motbeløp",
                "Kontoer i bilag",
            ]
        )

    selected_set = set(_konto_str(k) for k in data.selected_accounts)

    # Sikre at hjelpekolonnene finnes (build_motpost_data legger disse på, men vær robust).
    df_work = df.copy()
    if "Bilag_str" not in df_work.columns:
        df_work["Bilag_str"] = df_work.get("Bilag", "").map(_konto_str)
    if "Konto_str" not in df_work.columns:
        df_work["Konto_str"] = df_work.get("Konto", "").map(_konto_str)

    # Beløp er forventet numerisk i df_scope. Hvis ikke, forsøk å konvertere.
    if "Beløp" in df_work.columns and not pd.api.types.is_numeric_dtype(df_work["Beløp"]):
        df_work["Beløp"] = df_work["Beløp"].map(_safe_float)

    sel_account_mask = df_work["Konto_str"].isin(selected_set)
    sel_sum_mask = sel_account_mask.copy()
    # Optional direction filter for the selected side.
    dir_norm = (data.selected_direction or "Alle").strip().lower()
    if dir_norm.startswith("deb"):
        sel_sum_mask = sel_sum_mask & (df_work["Beløp"] > 0)
    elif dir_norm.startswith("kre") or dir_norm.startswith("cri"):
        sel_sum_mask = sel_sum_mask & (df_work["Beløp"] < 0)

    # Sum valgte kontoer per bilag
    sel_sum = (
        df_work.loc[sel_sum_mask]
        .groupby("Bilag_str")["Beløp"]
        .sum()
        .rename("Beløp (valgte kontoer)")
    )

    # Motkonto summer per bilag
    df_mot = df_work.loc[~sel_account_mask].copy()
    if df_mot.empty:
        return pd.DataFrame(
            columns=[
                "Bilag_key",
                "Bilag",
                "Dato",
                "Tekst",
                "Motkonto",
                "Motkontonavn",
                "Beløp (valgte kontoer)",
                "Motbeløp",
                "Kontoer i bilag",
            ]
        )

    def _first_date(series: pd.Series):
        s = series.dropna()
        return s.iloc[0] if not s.empty else None

    mot_agg = (
        df_mot.groupby(["Bilag_str", "Konto_str"])
        .agg(
            Motbeløp=("Beløp", "sum"),
            Motkontonavn=("Kontonavn", _first_non_empty),
        )
        .reset_index()
        .rename(columns={"Konto_str": "Motkonto"})
    )

    # Meta per bilag
    # Bilag_key kan mangle; bruk da Bilag_str
    if "Bilag_key" in df_work.columns:
        bilag_key = df_work.groupby("Bilag_str")["Bilag_key"].agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else "")
    else:
        bilag_key = pd.Series(df_work["Bilag_str"].unique(), index=df_work["Bilag_str"].unique())

    meta = (
        df_work.groupby("Bilag_str")
        .agg(
            Bilag=("Bilag", lambda s: s.dropna().iloc[0] if not s.dropna().empty else ""),
            Dato=("Dato", _first_date),
            Tekst=("Tekst", _first_non_empty),
            **{"Kontoer i bilag": ("Konto_str", lambda s: ", ".join(sorted(set(x for x in s.dropna().tolist() if str(x).strip()))))},
        )
        .reset_index()
    )
    meta["Bilag_key"] = meta["Bilag_str"].map(bilag_key.to_dict()).fillna(meta["Bilag_str"])

    details = mot_agg.merge(sel_sum.reset_index(), on="Bilag_str", how="left").merge(meta, on="Bilag_str", how="left")
    details["Beløp (valgte kontoer)"] = details["Beløp (valgte kontoer)"].fillna(0.0)

    # Kolonneordre
    out_cols = [
        "Bilag_key",
        "Bilag",
        "Dato",
        "Tekst",
        "Motkonto",
        "Motkontonavn",
        "Beløp (valgte kontoer)",
        "Motbeløp",
        "Kontoer i bilag",
    ]
    details = details[out_cols]

    # Alias brukt i eldre tester
    if "Beløp valgte kontoer" not in details.columns:
        details["Beløp valgte kontoer"] = details["Beløp (valgte kontoer)"]

    return details


def build_outlier_bilag_transactions(data: MotpostData, outliers: set[str]) -> pd.DataFrame:
    """Alle transaksjoner for bilag som inneholder outlier-motkonto(er)."""

    if data.df_scope is None or data.df_scope.empty or not outliers:
        return pd.DataFrame()

    out_set = {_konto_str(x) for x in outliers}
    selected_set = set(data.selected_accounts)

    df = data.df_scope.copy()
    df["Bilag_str"] = df["Bilag"].map(_bilag_str)
    df["Konto_str"] = df["Konto"].map(_konto_str)
    df["Beløp_num"] = df["Beløp"].map(_safe_float)

    df_out = df[df["Konto_str"].isin(out_set)]
    if df_out.empty:
        return pd.DataFrame()

    bilag_out = sorted(df_out["Bilag_str"].unique().tolist())
    df_all = df[df["Bilag_str"].isin(set(bilag_out))].copy()

    # Agg for hver bilag
    sum_selected_per_bilag = (
        df_all[df_all["Konto_str"].isin(selected_set)]
        .groupby("Bilag_str")["Beløp_num"]
        .sum()
        .to_dict()
    )
    outliers_per_bilag = (
        df_all[df_all["Konto_str"].isin(out_set)]
        .groupby("Bilag_str")["Konto_str"]
        .apply(lambda s: _unique_join(sorted(set(s.tolist()))))
        .to_dict()
    )

    df_all["Beløp (valgte kontoer)"] = df_all["Bilag_str"].map(lambda b: float(sum_selected_per_bilag.get(b, 0.0)))
    df_all["Outlier motkontoer i bilag"] = df_all["Bilag_str"].map(lambda b: outliers_per_bilag.get(b, ""))

    # Normaliser dato
    if "Dato" in df_all.columns:
        df_all["Dato_dt"] = pd.to_datetime(df_all["Dato"], errors="coerce")
    else:
        df_all["Dato_dt"] = pd.NaT

    # Kolonneutvalg
    cols = [
        "Bilag_str",
        "Dato_dt",
        "Tekst" if "Tekst" in df_all.columns else None,
        "Konto_str",
        "Kontonavn" if "Kontonavn" in df_all.columns else None,
        "Beløp_num",
        "Beløp (valgte kontoer)",
        "Outlier motkontoer i bilag",
    ]
    cols = [c for c in cols if c is not None]
    df_outlier = df_all[cols].copy()

    rename_map = {
        "Bilag_str": "Bilag",
        "Dato_dt": "Dato",
        "Konto_str": "Konto",
        "Beløp_num": "Beløp",
    }
    df_outlier = df_outlier.rename(columns=rename_map)

    # Sorter pent
    sort_cols = ["Bilag", "Dato"] if "Dato" in df_outlier.columns else ["Bilag"]
    df_outlier = df_outlier.sort_values(by=sort_cols, ascending=True)
    return df_outlier.reset_index(drop=True)




# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

# -----------------------------
# Excel export
# -----------------------------

# Selve Excel-byggingen ligger i motpost_excel.py for å holde denne modulen
# fokusert på data/pivot. Vi beholder en tynn wrapper her for bakoverkompatibilitet
# (tester/GUI importerer fortsatt fra motpost_konto_core).

def build_motpost_excel_workbook(*args, **kwargs):
    """Bygger openpyxl Workbook for motpostanalyse (delegert).

    Implementasjonen ligger i :mod:`motpost_excel`.
    """

    from .excel import build_motpost_excel_workbook as _impl

    return _impl(*args, **kwargs)
