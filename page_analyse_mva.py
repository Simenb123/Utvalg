"""page_analyse_mva.py

MVA-kode-pivot for Analyse-fanen.

Ansvar:
- Bygge pivot på MVA-kode-nivå med termin-kolonner (T1-T6)
- Summere MVA-beløp per kode per termin
- Vise summeringsrader (utgående, inngående, netto)
- Mappe valgte MVA-koder tilbake til kontoer for transaksjonslisten

Terminer (2-månedersperioder):
  T1: jan-feb, T2: mar-apr, T3: mai-jun,
  T4: jul-aug, T5: sep-okt, T6: nov-des
"""

from __future__ import annotations

import logging
from typing import Any, List

import pandas as pd

import formatting
import src.pages.mva.backend.codes as mva_codes

log = logging.getLogger("app")


def _resolve_code_mapping(client: str | None) -> dict[str, str]:
    """Hent klient-spesifikk MVA-kode-mapping {klient_kode: saft_kode}.

    Faller tilbake på standard-mapping for klientens regnskapssystem
    hvis ingen eksplisitt mapping er lagret. Returnerer tom dict hvis
    klient ikke er satt eller intet kan bestemmes.
    """
    if not client:
        return {}
    try:
        import src.shared.regnskap.client_overrides as rco
        mapping = rco.load_mva_code_mapping(client)
        if mapping:
            return dict(mapping)
        system = rco.load_accounting_system(client)
        if system:
            import src.pages.mva.backend.system_defaults as mva_system_defaults
            return mva_system_defaults.get_default_mapping(system)
    except Exception:
        log.debug("Kunne ikke laste MVA-kode-mapping for klient %s", client, exc_info=True)
    return {}


def _normalize_code(raw: str, mapping: dict[str, str]) -> str:
    """Slå opp rå-kode i klient-mapping; fall tilbake på rå-koden."""
    raw_s = str(raw or "").strip()
    if not raw_s:
        return raw_s
    if raw_s in mapping:
        return mapping[raw_s]
    return raw_s


def _current_client() -> str:
    try:
        import session
        return str(getattr(session, "client", None) or "").strip()
    except Exception:
        return ""

# Headings for MVA-modus (mapper til de 9 interne kolonne-IDene i pivot_tree)
MVA_PIVOT_HEADINGS = (
    "MVA-kode", "Beskrivelse", "T1", "T2", "T3", "T4", "T5", "T6", "Sum",
)
# Standard konto-modus headings (for tilbakestilling)
KONTO_PIVOT_HEADINGS = (
    "Konto", "Kontonavn", "", "", "Sum", "Antall", "", "", "",
)

# Interne kolonne-IDer i pivot_tree (fast, satt i page_analyse.py)
_COL_IDS = (
    "Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall",
    "UB_fjor", "Endring_fjor", "Endring_pct",
)


def month_to_termin(month: int) -> int:
    """Konverter måned (1-12) til termin (1-6)."""
    return (month - 1) // 2 + 1


def _compute_tax(code: str, grunnlag: float) -> float:
    """Beregn avgiftsbeløp fra grunnlag × sats for en MVA-kode.

    Brukes som fallback når MVA-beløp ikke finnes i dataene.
    """
    info = mva_codes.get_code_info(str(code).strip())
    if info is None:
        return 0.0
    rate = info.get("rate", 0.0)
    if rate == 0.0:
        return 0.0
    return grunnlag * rate / 100.0


# ---------------------------------------------------------------------------
# Pivot-bygging
# ---------------------------------------------------------------------------

def build_mva_pivot(df: pd.DataFrame, *, client: str | None = None) -> pd.DataFrame:
    """Bygg MVA-pivot fra filtrert DataFrame.

    Grupperer transaksjoner etter MVA-kode og termin.
    Viser beregnet avgift (grunnlag × sats) per kode per termin.

    Hvis MVA-beløp finnes i dataene brukes det direkte.
    Hvis MVA-beløp er 0/mangler, beregnes avgift fra grunnlag (Beløp) × sats.

    Hvis ``client`` er satt, normaliseres klient-spesifikke MVA-koder til
    SAF-T standardkoder via ``regnskap_client_overrides.load_mva_code_mapping``
    (med fallback til ``mva_system_defaults``). Ukjente koder beholdes som-er.

    Returnerer DataFrame med kolonnene:
        MVA-kode, Beskrivelse, T1, T2, T3, T4, T5, T6, Sum
    """
    if df is None or df.empty:
        return _empty_pivot()

    code_mapping = _resolve_code_mapping(client)

    # Finn MVA-relevante kolonner
    mva_code_col = _find_col(df, ["MVA-kode", "mva-kode", "Mva-kode"])
    mva_amount_col = _find_col(df, ["MVA-beløp", "mva-beløp", "Mva-beløp"])
    belop_col = _find_col(df, ["Beløp", "beløp", "Belop"])
    dato_col = _find_col(df, ["Dato", "dato"])

    if not mva_code_col or not dato_col:
        return _empty_pivot()

    # Samle relevante kolonner
    use_cols = [mva_code_col, dato_col]
    if mva_amount_col:
        use_cols.append(mva_amount_col)
    if belop_col:
        use_cols.append(belop_col)
    work = df[[c for c in use_cols if c]].copy()

    work.rename(columns={mva_code_col: "_code", dato_col: "_dato"}, inplace=True)
    if mva_amount_col:
        work.rename(columns={mva_amount_col: "_mva_amt"}, inplace=True)
    else:
        work["_mva_amt"] = 0.0
    if belop_col:
        work.rename(columns={belop_col: "_belop"}, inplace=True)
    else:
        work["_belop"] = 0.0

    # Fjern rader uten MVA-kode
    work["_code"] = work["_code"].astype(str).str.strip()
    work = work[work["_code"].ne("") & work["_code"].ne("nan") & work["_code"].ne("None")]
    if work.empty:
        return _empty_pivot()

    # Normaliser klient-spesifikke koder til SAF-T standardkoder
    if code_mapping:
        work["_code_raw"] = work["_code"]
        work["_code"] = work["_code"].map(lambda c: _normalize_code(c, code_mapping))

    # Parse numeriske kolonner
    work["_mva_amt"] = pd.to_numeric(work["_mva_amt"], errors="coerce").fillna(0.0)
    work["_belop"] = pd.to_numeric(work["_belop"], errors="coerce").fillna(0.0)

    # Sjekk om MVA-beløp faktisk har data — hvis alt er 0, beregn fra grunnlag
    has_mva_amounts = work["_mva_amt"].abs().sum() > 0.01

    if not has_mva_amounts:
        # Beregn avgift fra grunnlag × sats for hver rad
        work["_mva_amt"] = work.apply(
            lambda r: _compute_tax(r["_code"], r["_belop"]), axis=1
        )

    # Derive termin fra dato
    work["_dato"] = pd.to_datetime(work["_dato"], errors="coerce")
    work["_termin"] = work["_dato"].dt.month.apply(
        lambda m: month_to_termin(int(m)) if pd.notna(m) else 0
    )

    # Grupper per MVA-kode + termin: sum avgift OG grunnlag
    grouped = (
        work
        .groupby(["_code", "_termin"], as_index=False)
        .agg(_mva_amt=("_mva_amt", "sum"), _belop=("_belop", "sum"))
    )

    # Pivot avgift til bredt format
    pivot = grouped.pivot_table(
        index="_code",
        columns="_termin",
        values="_mva_amt",
        aggfunc="sum",
        fill_value=0.0,
    )

    # Pivot grunnlag separat (for lagring / eksport)
    pivot_grunnlag = grouped.pivot_table(
        index="_code",
        columns="_termin",
        values="_belop",
        aggfunc="sum",
        fill_value=0.0,
    )

    # Sikre at alle terminer finnes
    for t in range(1, 7):
        if t not in pivot.columns:
            pivot[t] = 0.0
        if t not in pivot_grunnlag.columns:
            pivot_grunnlag[t] = 0.0
    pivot = pivot[[1, 2, 3, 4, 5, 6]]
    pivot_grunnlag = pivot_grunnlag[[1, 2, 3, 4, 5, 6]]

    # Sum-kolonner
    pivot["Sum"] = pivot.sum(axis=1)
    pivot_grunnlag["G_Sum"] = pivot_grunnlag.sum(axis=1)

    # Berik med metadata fra mva_codes
    rows = []
    for code in sorted(pivot.index, key=lambda c: (c.isdigit(), int(c) if c.isdigit() else 0, c)):
        info = mva_codes.get_code_info(str(code))
        desc = info["description"] if info else ""
        direction = info.get("direction", "") if info else ""

        row_data = {
            "MVA-kode": str(code),
            "Beskrivelse": desc,
            "direction": direction,
        }
        for t in range(1, 7):
            row_data[f"T{t}"] = pivot.loc[code, t]
        row_data["Sum"] = pivot.loc[code, "Sum"]

        # Grunnlag per termin
        if code in pivot_grunnlag.index:
            for t in range(1, 7):
                row_data[f"G_T{t}"] = pivot_grunnlag.loc[code, t]
            row_data["G_Sum"] = pivot_grunnlag.loc[code, "G_Sum"]
        else:
            for t in range(1, 7):
                row_data[f"G_T{t}"] = 0.0
            row_data["G_Sum"] = 0.0

        rows.append(row_data)

    if not rows:
        return _empty_pivot()

    result = pd.DataFrame(rows)

    # Legg til summeringsrader
    result = _add_summary_rows(result)

    return result


def _add_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Legg til summeringsrader for utgående, inngående og netto."""
    termin_cols = [f"T{t}" for t in range(1, 7)] + ["Sum"]
    grunnlag_cols = [f"G_T{t}" for t in range(1, 7)] + ["G_Sum"]

    def _sum_row(label: str, mask) -> dict:
        subset = df[mask]
        row: dict = {
            "MVA-kode": "",
            "Beskrivelse": label,
            "direction": "_summary",
        }
        for col in termin_cols:
            row[col] = subset[col].sum() if not subset.empty else 0.0
        for col in grunnlag_cols:
            if col in df.columns:
                row[col] = subset[col].sum() if not subset.empty else 0.0
            else:
                row[col] = 0.0
        return row

    utgaende = df["direction"] == "utgående"
    inngaende = df["direction"] == "inngående"

    summary_rows = [
        _sum_row("Sum utgående MVA", utgaende),
        _sum_row("Sum inngående MVA", inngaende),
    ]

    # Netto = utgående - inngående (positivt = skyldig)
    netto: dict = {
        "MVA-kode": "",
        "Beskrivelse": "Netto MVA (utgående - inngående)",
        "direction": "_netto",
    }
    for col in termin_cols:
        utg_val = summary_rows[0][col]
        inn_val = summary_rows[1][col]
        netto[col] = utg_val - inn_val
    for col in grunnlag_cols:
        netto[col] = summary_rows[0].get(col, 0.0) - summary_rows[1].get(col, 0.0)
    summary_rows.append(netto)

    return pd.concat([df, pd.DataFrame(summary_rows)], ignore_index=True)


def _empty_pivot() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "MVA-kode", "Beskrivelse", "direction",
        "T1", "T2", "T3", "T4", "T5", "T6", "Sum",
    ])


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str:
    """Finn første matchende kolonnenavn (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        actual = lower_map.get(cand.lower())
        if actual:
            return actual
    return ""


# ---------------------------------------------------------------------------
# Pivot-headings
# ---------------------------------------------------------------------------

def update_pivot_headings_mva(*, page: Any) -> None:
    """Sett treeview-headings for MVA-modus."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    for col_id, heading in zip(_COL_IDS, MVA_PIVOT_HEADINGS):
        try:
            tree.heading(col_id, text=heading)
        except Exception:
            pass

    # Juster kolonnebredder for MVA-modus
    try:
        tree.column("Konto", width=70, anchor="center")      # MVA-kode
        tree.column("Kontonavn", width=200, anchor="w")       # Beskrivelse
        tree.column("IB", width=90, anchor="e")               # T1
        tree.column("Endring", width=90, anchor="e")          # T2
        tree.column("Sum", width=90, anchor="e")              # T3
        tree.column("Antall", width=90, anchor="e")           # T4
        tree.column("UB_fjor", width=90, anchor="e")          # T5
        tree.column("Endring_fjor", width=90, anchor="e")     # T6
        tree.column("Endring_pct", width=100, anchor="e")     # Sum
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GUI-refresh
# ---------------------------------------------------------------------------

def refresh_mva_pivot(*, page: Any) -> None:
    """Fyll pivot_tree med MVA-kode-rader per termin."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    update_pivot_headings_mva(page=page)

    try:
        page._clear_tree(tree)
    except Exception:
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        return

    client = _current_client()
    pivot_df = build_mva_pivot(df_filtered, client=client or None)

    # Cache for eksport
    try:
        page._mva_pivot_df_last = pivot_df.copy()
    except Exception:
        pass

    if pivot_df.empty:
        _show_mva_not_available(tree)
        return

    _dec = 2
    try:
        _var_dec = getattr(page, "_var_decimals", None)
        if _var_dec is not None and not bool(_var_dec.get()):
            _dec = 0
    except Exception:
        pass

    for _, row in pivot_df.iterrows():
        code = str(row.get("MVA-kode", ""))
        desc = str(row.get("Beskrivelse", ""))
        direction = str(row.get("direction", ""))

        # Formater termin-verdier
        t_vals = []
        for t in range(1, 7):
            val = row.get(f"T{t}", 0.0)
            t_vals.append(formatting.fmt_amount(val, decimals=_dec) if val else "")
        sum_val = formatting.fmt_amount(row.get("Sum", 0.0), decimals=_dec)

        # Bestem tag
        tags: tuple = ()
        if direction == "_summary":
            tags = ("sumline",)
        elif direction == "_netto":
            tags = ("sumline_major",)

        try:
            tree.insert(
                "", "end",
                values=(code, desc, *t_vals, sum_val),
                tags=tags,
            )
        except Exception:
            continue

    _maybe_auto_fit(page)


def _show_mva_not_available(tree: Any) -> None:
    try:
        tree.insert(
            "", "end",
            values=("-", "Ingen transaksjoner med MVA-kode funnet", "", "", "", "", "", "", ""),
        )
    except Exception:
        pass


def _maybe_auto_fit(page: Any) -> None:
    fn = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Kontooppslag for MVA-valg
# ---------------------------------------------------------------------------

def get_selected_mva_accounts(*, page: Any) -> List[str]:
    """Returner kontoer som har transaksjoner med valgte MVA-koder."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

    # Samle valgte MVA-koder
    selected_codes: List[str] = []
    try:
        selected = tree.selection()
        if not selected:
            selected = tree.get_children()
        for item in selected:
            try:
                code = str(tree.set(item, "Konto")).strip()  # "Konto" = intern kolonne-ID
                if code and code != "-":
                    selected_codes.append(code)
            except Exception:
                pass
    except Exception:
        pass

    if not selected_codes:
        return []

    # Finn alle kontoer i df_filtered som har disse MVA-kodene
    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or df_filtered.empty:
        return []

    mva_code_col = _find_col(df_filtered, ["MVA-kode", "mva-kode", "Mva-kode"])
    if not mva_code_col or "Konto" not in df_filtered.columns:
        return []

    codes_set = set(selected_codes)
    mask = df_filtered[mva_code_col].astype(str).str.strip().isin(codes_set)
    accounts = df_filtered.loc[mask, "Konto"].astype(str).unique().tolist()

    return sorted(set(accounts))
