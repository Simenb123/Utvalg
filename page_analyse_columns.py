"""page_analyse_columns.py

Kolonnehåndtering for Analyse-fanen: pivot-synlighet, TX-kolonnevalg,
auto-fit og breddepersistens.

Alle funksjoner tar ``page`` (AnalysePage-instans) som duck-typed objekt
og leser/skriver attributter direkte – samme mønster som de øvrige
page_analyse_*-modulene.
"""

from __future__ import annotations

from typing import Any, List, Optional

import analyse_columns
import analyse_treewidths
import preferences


# =====================================================================
# Pivot-kolonnesynlighet
# =====================================================================

# Konstanter (PIVOT_STRETCH_COLS, PIVOT_FILL_PRIORITY, PIVOT_FILL_WEIGHTS,
# TX_HEADER_DRAG_THRESHOLD_PX) er flyttet til page_analyse_columns_widths og
# re-eksporteres nederst i denne fila for bakoverkompatibilitet.


def normalize_aggregation_mode(value: object) -> str:
    """Map user-facing og legacy mode-verdier til kanonisk intern verdi.

    GUI viser nå bare "Saldobalanse" og "Regnskapslinje". Legacy/interne
    moduser ("Konto", "SB-konto", "HB-konto", "MVA-kode") kollapses til
    kanonisk "SB-konto" slik at eldre prefs/kode fortsatt fungerer.
    """
    v = str(value or "").strip()
    if v == "Regnskapslinje":
        return "Regnskapslinje"
    return "SB-konto"


def normalize_view_mode(value: object) -> str:
    """Map høyre-side view-modus til kanonisk intern verdi.

    GUI viser nå bare "Saldobalanse" og "Hovedbok". Gamle moduser
    ("Saldobalansekontoer", "Transaksjoner", "Nøkkeltall", "Motposter",
    "Motposter (kontonivå)") normaliseres slik at eldre prefs/kode
    fortsatt fungerer. Ukjente/fjernede verdier → "Saldobalansekontoer".
    """
    v = str(value or "").strip()
    if v in ("Hovedbok", "Transaksjoner"):
        return "Transaksjoner"
    return "Saldobalansekontoer"


def _read_agg_mode(page: Any) -> str:
    """Les aggregeringsmodus fra page med legacy-migrering."""
    try:
        raw = page._var_aggregering.get() if page._var_aggregering is not None else ""
    except Exception:
        raw = ""
    return normalize_aggregation_mode(raw)


def _read_view_mode(page: Any) -> str:
    """Les høyre-panel view-modus fra page med legacy-migrering."""
    try:
        raw = page._var_tx_view_mode.get() if page._var_tx_view_mode is not None else ""
    except Exception:
        raw = ""
    return normalize_view_mode(raw)


# =====================================================================
# Felles brukerrettet label-mapper for Analyse-kolonner
# =====================================================================

# Kanoniske labels for kolonne-ID-er som brukes både i venstre pivot og
# høyre SB-tree. UB / UB_fjor får årstall injisert via analysis_heading.
_ANALYSIS_HEADINGS_STATIC = {
    "Konto": "Konto",
    "Kontonavn": "Kontonavn",
    "OK": "OK",
    "OK_av": "OK av",
    "OK_dato": "OK dato",
    "Vedlegg": "Vedlegg",
    "Gruppe": "Gruppe",
    "IB": "IB",
    "Endring": "Bevegelse i år",       # periode-bevegelse (UB-IB)
    "Endring_fjor": "Endring",          # år-over-år (UB - UB_fjor)
    "Endring_pct": "Endring %",
    "Antall": "Antall",
    "AO_belop": "Tilleggspostering",
    "UB_for_ao": "UB før ÅO",
    "UB_etter_ao": "UB etter ÅO",
    "BRREG": "BRREG",
    "Avvik_brreg": "Avvik mot BRREG",
    "Avvik_brreg_pct": "Avvik % mot BRREG",
}


def analysis_heading(
    col_id: str,
    *,
    year: Optional[int] = None,
    brreg_year: Optional[int] = None,
) -> str:
    """Returner kanonisk brukerrettet overskrift for en Analyse-kolonne-ID.

    Brukes av både venstre pivot og høyre SB-tree slik at samme kolonne
    ID vises med samme label overalt.

    - ``Sum`` / ``UB``   → ``UB <år>`` når år er kjent, ellers ``UB``.
    - ``UB_fjor``        → ``UB <år-1>`` når år er kjent, ellers ``UB i fjor``.
    - ``BRREG``          → ``BRREG <år>`` når brreg_year er kjent, ellers ``BRREG``.
    - Øvrige kolonner    → fra ``_ANALYSIS_HEADINGS_STATIC``, fallback til ID.
    """
    if col_id in ("Sum", "UB"):
        return f"UB {year}" if year is not None else "UB"
    if col_id == "UB_fjor":
        return f"UB {year - 1}" if year is not None else "UB i fjor"
    if col_id == "BRREG":
        return f"BRREG {brreg_year}" if brreg_year is not None else "BRREG"
    return _ANALYSIS_HEADINGS_STATIC.get(col_id, col_id)


def _active_year() -> Optional[int]:
    """Les aktivt regnskapsår fra session som int når mulig."""
    try:
        import session as _session
        raw = getattr(_session, "year", None)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


_LEGACY_RL_VISIBLE_DEFAULTS = {
    (
        "Konto",
        "Kontonavn",
        "IB",
        "Endring",
        "Sum",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
    ),
    (
        "Konto",
        "Kontonavn",
        "Endring",
        "Sum",
        "UB_fjor",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
        "Endring_pct",
    ),
    # Tidligere PIVOT_COLS_DEFAULT_RL (uten fjor\u00e5rsdata)
    ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall"),
    # Tidligere default med fjor\u00e5rsdata (avledet av gammel pivot_default_for_mode)
    ("Konto", "Kontonavn", "Endring", "Sum", "UB_fjor", "Antall", "Endring_pct"),
    # Forrige PIVOT_COLS_DEFAULT_RL (med intern Endring = Bevegelse i \u00e5r)
    (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    ),
    # Tidligere slank fallback uten fj\u00e5rsdata med intern Endring innskutt etter Sum
    ("Konto", "Kontonavn", "Sum", "Endring", "Antall"),
}


def _has_prev_year(page: Any) -> bool:
    """Returner True dersom fjorårsdata er lastet og tilgjengelig."""
    import pandas as pd
    pivot_df = getattr(page, "_pivot_df_last", None)
    if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
        return True
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev, pd.DataFrame) and not sb_prev.empty:
        return True
    return False


def _rl_like_default(*, page: Any, base: tuple[str, ...]) -> tuple[str, ...]:
    """Samme komparative kolonne-default som RL, med slank fallback uten fjorårsdata.

    Brukes av både Regnskapslinje- og SB-konto-modus: begge viser
    ``UB <år>``, ``UB <år-1>``, ``Endring`` og ``Endring %`` når
    fjorårsdata er tilgjengelig. Uten fjorårsdata droppes de
    fjorårsavhengige kolonnene uten å sette inn intern ``Endring``
    (Bevegelse i år) som fallback — den forblir tilgjengelig via
    kolonne-menyen, men er ikke standard synlig.
    """
    if _has_prev_year(page):
        return tuple(base)
    prev_dependent = {"UB_fjor", "Endring_fjor", "Endring_pct"}
    result: list[str] = []
    seen: set[str] = set()
    for col in base:
        if col in prev_dependent:
            continue
        if col in seen:
            continue
        result.append(col)
        seen.add(col)
    return tuple(result)


def pivot_default_for_mode(*, page: Any) -> tuple[str, ...]:
    """Returner standard synlige pivot-kolonner for gjeldende aggregeringsmodus.

    RL / SB-konto standardrekkefølge (med fjorårsdata):
        Nr / Konto | Regnskapslinje / Kontonavn | UB <aktivt år> |
        UB <aktivt år-1> | Endring | Endring % | Antall
        (kolonne-IDer: Konto | Kontonavn | Sum | UB_fjor | Endring_fjor |
         Endring_pct | Antall)

    Uten fjorårsdata:
        UB <aktivt år> | Bevegelse i år | Antall
        (kolonne-IDer: Konto | Kontonavn | Sum | Endring | Antall)

    HB-konto: Konto | Kontonavn | HB-bevegelse | Antall (ingen komparativ).
    """
    agg = _read_agg_mode(page)
    if agg == "HB-konto":
        return getattr(page, "PIVOT_COLS_DEFAULT_HB_KONTO", page.PIVOT_COLS_DEFAULT_VISIBLE)
    if agg == "SB-konto":
        base = getattr(page, "PIVOT_COLS_DEFAULT_SB_KONTO", page.PIVOT_COLS_DEFAULT_VISIBLE)
        return _rl_like_default(page=page, base=tuple(base))
    if agg == "Regnskapslinje":
        base = getattr(page, "PIVOT_COLS_DEFAULT_RL", page.PIVOT_COLS_DEFAULT_VISIBLE)
        return _rl_like_default(page=page, base=tuple(base))
    return page.PIVOT_COLS_DEFAULT_VISIBLE


def load_pivot_visible_columns(*, page: Any) -> None:
    """Last lagret pivot-kolonnesynlighet fra preferences."""
    try:
        stored = preferences.get("analyse.pivot_cols.visible", None)
    except Exception:
        stored = None

    if isinstance(stored, list) and stored:
        valid = [c for c in stored if c in page.PIVOT_COLS]
        for p in page.PIVOT_COLS_PINNED:
            if p not in valid:
                valid.insert(0, p)
        page._pivot_visible_cols = valid
    else:
        page._pivot_visible_cols = list(page.PIVOT_COLS_DEFAULT_VISIBLE)


def persist_pivot_visible_columns(*, page: Any) -> None:
    try:
        preferences.set("analyse.pivot_cols.visible", list(page._pivot_visible_cols))
    except Exception:
        pass


def apply_pivot_visible_columns(*, page: Any) -> None:
    """Oppdater pivot-tree displaycolumns basert på _pivot_visible_cols."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    all_cols = list(tree["columns"])
    visible = [c for c in page._pivot_visible_cols if c in all_cols]
    if not visible:
        visible = list(page.PIVOT_COLS_DEFAULT_VISIBLE)
    try:
        tree["displaycolumns"] = visible
    except Exception:
        pass


def toggle_pivot_column(*, page: Any, col: str) -> None:
    """Slå av/på en kolonne i pivot-visningen."""
    if col in page.PIVOT_COLS_PINNED:
        return
    if col in page._pivot_visible_cols:
        page._pivot_visible_cols.remove(col)
    else:
        pos = 0
        for pc in page.PIVOT_COLS:
            if pc == col:
                break
            if pc in page._pivot_visible_cols:
                pos += 1
        page._pivot_visible_cols.insert(pos, col)
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


# =====================================================================
# Kolonne-kontekstmeny er flyttet til page_analyse_columns_menu,
# og re-eksporteres nederst i denne fila for bakoverkompatibilitet.
# =====================================================================


def reset_pivot_columns(*, page: Any) -> None:
    page._pivot_visible_cols = list(pivot_default_for_mode(page=page))
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def adapt_pivot_columns_for_mode(*, page: Any) -> None:
    """Tilpass synlige kolonner når aggregeringsmodus endres."""
    defaults = pivot_default_for_mode(page=page)
    agg = _read_agg_mode(page)
    if agg in ("Regnskapslinje", "SB-konto"):
        current = tuple(getattr(page, "_pivot_visible_cols", []) or [])
        if current in _LEGACY_RL_VISIBLE_DEFAULTS:
            page._pivot_visible_cols = list(defaults)
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    relevant: set[str] = set(page.PIVOT_COLS_PINNED)
    for col_id in page.PIVOT_COLS:
        try:
            heading_text = tree.heading(col_id, "text")
        except Exception:
            heading_text = ""
        if heading_text and heading_text.strip():
            relevant.add(col_id)
    new_visible = list(defaults)
    for col in page._pivot_visible_cols:
        if col not in new_visible and col in relevant:
            new_visible.append(col)
    new_visible = [c for c in new_visible if c in relevant]
    if not new_visible:
        new_visible = list(defaults)
    page._pivot_visible_cols = new_visible
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def update_pivot_columns_for_prev_year(*, page: Any) -> None:
    """Kall etter at fjorårsdata er lastet.

    Legger automatisk til UB_fjor, Endring_fjor og Endring_pct (fjerner IB)
    i RL-modus så brukeren får ny komparativ standard. Gjør ingenting i
    Konto-modus. Rekkefølge: Sum → UB_fjor → Endring_fjor → Endring_pct.
    """
    agg = ""
    try:
        agg = str(page._var_aggregering.get())
    except Exception:
        pass
    if agg != "Regnskapslinje":
        return

    if not _has_prev_year(page):
        return

    visible = list(getattr(page, "_pivot_visible_cols", []))

    changed = False
    # Fjern IB hvis det er der (ikke del av ny komparativ default)
    if "IB" in visible:
        visible.remove("IB")
        changed = True

    # Sørg for rekkefølge Sum → UB_fjor → Endring_fjor → Endring_pct ved å
    # sette inn manglende kolonner rett etter "Sum" (eller hver etter den
    # forrige hvis Sum mangler).
    def _insert_after(anchor: str, col: str) -> bool:
        if col in visible:
            return False
        try:
            idx = visible.index(anchor)
            visible.insert(idx + 1, col)
        except ValueError:
            visible.append(col)
        return True

    changed |= _insert_after("Sum", "UB_fjor")
    changed |= _insert_after("UB_fjor", "Endring_fjor")
    changed |= _insert_after("Endring_fjor", "Endring_pct")

    if changed:
        page._pivot_visible_cols = visible
        apply_pivot_visible_columns(page=page)
        persist_pivot_visible_columns(page=page)


def update_pivot_columns_for_brreg(*, page: Any) -> None:
    """Kall etter at BRREG-data er hentet.

    Viser BRREG, Avvik_brreg og Avvik_brreg_pct i RL-modus når tilgjengelig.
    """
    agg = ""
    try:
        agg = str(page._var_aggregering.get())
    except Exception:
        pass
    if agg != "Regnskapslinje":
        return

    if not getattr(page, "_nk_brreg_data", None):
        return

    visible = list(getattr(page, "_pivot_visible_cols", []))
    changed = False
    for col in ("BRREG", "Avvik_brreg", "Avvik_brreg_pct"):
        if col not in visible:
            visible.append(col)
            changed = True

    if changed:
        page._pivot_visible_cols = visible
        apply_pivot_visible_columns(page=page)
        persist_pivot_visible_columns(page=page)


def clear_pivot_columns_for_brreg(*, page: Any) -> None:
    """Skjul BRREG-kolonner i RL-modus (kalles når BRREG-data tømmes)."""
    visible = list(getattr(page, "_pivot_visible_cols", []))
    changed = False
    for col in ("BRREG", "Avvik_brreg", "Avvik_brreg_pct"):
        if col in visible:
            visible.remove(col)
            changed = True
    if changed:
        page._pivot_visible_cols = visible
        try:
            apply_pivot_visible_columns(page=page)
            persist_pivot_visible_columns(page=page)
        except Exception:
            pass


# =====================================================================
# TX- og SB-kolonnepresets er flyttet til page_analyse_columns_presets,
# og re-eksporteres nederst i denne fila for bakoverkompatibilitet.
# =====================================================================


# =====================================================================
# Re-eksporter fra submoduler (bakoverkompatibilitet)
# =====================================================================

from page_analyse_columns_widths import (  # noqa: F401
    PIVOT_FILL_PRIORITY,
    PIVOT_FILL_WEIGHTS,
    PIVOT_STRETCH_COLS,
    TX_HEADER_DRAG_THRESHOLD_PX,
    auto_fit_analyse_columns,
    auto_fit_pivot_columns,
    auto_fit_tree_columns,
    auto_fit_tx_columns,
    column_id_from_event,
    configure_tx_tree_columns,
    enable_tx_sorting,
    load_saved_column_widths,
    maybe_auto_fit_pivot_tree,
    maybe_auto_fit_tx_tree,
    on_pivot_tree_double_click,
    on_pivot_tree_mouse_drag,
    on_pivot_tree_mouse_press,
    on_pivot_tree_mouse_release,
    on_tx_tree_double_click,
    on_tx_tree_mouse_drag,
    on_tx_tree_mouse_press,
    on_tx_tree_mouse_release,
    persist_saved_column_widths,
    rebalance_pivot_tree_columns,
    rebalance_tree_columns_to_available_width,
    refresh_pivot_sorting,
    remember_pivot_column_widths,
    remember_sb_column_widths,
    remember_tx_column_widths,
    reset_pivot_column_widths,
    reset_tx_column_widths,
    safe_tree_column_width,
    sample_tx_values_for_width,
    schedule_balance_pivot_tree,
    snapshot_tree_widths,
    tree_display_columns,
    tree_rows_for_width_estimate,
)

from page_analyse_columns_menu import (  # noqa: F401
    _action_link_label,
    _open_account_comment,
    _open_action_link,
    _open_rl_comment,
    _open_statistikk,
    show_pivot_column_menu,
)

from page_analyse_columns_presets import (  # noqa: F401
    SB_DYNAMIC_COLS,
    SB_PINNED_COLS,
    _sb_defaults,
    _sb_ub_fjor_available,
    apply_sb_column_config,
    apply_tx_column_config,
    configure_sb_tree_columns,
    get_all_tx_columns_for_chooser,
    load_sb_columns_from_preferences,
    load_tx_columns_from_preferences,
    open_sb_column_chooser,
    open_tx_column_chooser,
    persist_sb_columns_to_preferences,
    persist_tx_columns_to_preferences,
    reset_sb_columns_to_default,
    reset_tx_columns_to_default,
)
