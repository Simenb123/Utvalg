"""page_analyse_columns_presets.py

TX- og SB-kolonnepresets for Analyse-fanen (last/lagre/velg/reset/chooser).

Utskilt fra page_analyse_columns.py. Re-eksportert via page_analyse_columns
som fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

import analyse_columns
import preferences

from page_analyse_columns_widths import configure_tx_tree_columns


# =====================================================================
# ColumnSpec-bygger for ManagedTreeview-drevet TX-tree
# =====================================================================

def build_pivot_column_specs(
    *,
    page: Any,
    year: Optional[int] = None,
):
    """Returner ColumnSpec-liste for pivot-treet i Analyse-fanen.

    Brukes når pivot_tree wrappes med ManagedTreeview. Alle PIVOT_COLS
    inkluderes, men ``visible_by_default`` styres av gjeldende
    aggregeringsmodus (Regnskapslinje/SB-konto/HB-konto).
    """
    from src.shared.ui.managed_treeview import ColumnSpec
    import analyse_treewidths

    try:
        from page_analyse_columns import pivot_default_for_mode
        default_visible = set(pivot_default_for_mode(page=page))
    except Exception:
        default_visible = set(getattr(page, "PIVOT_COLS_DEFAULT_VISIBLE", ()))

    pivot_cols = getattr(page, "PIVOT_COLS", ())
    pinned_set = set(getattr(page, "PIVOT_COLS_PINNED", ("Konto", "Kontonavn")))

    # Heading-tekster hentes via analysis_heading — år-avhengige labels
    # som "UB 2025", "Δ UB 25/24" kommer fra felles vokabular.
    try:
        from page_analyse_columns import analysis_heading
    except Exception:
        analysis_heading = lambda c, year=None: c  # type: ignore[assignment]

    specs = []
    for col in pivot_cols:
        try:
            heading = analysis_heading(col, year=year)
        except Exception:
            heading = col
        specs.append(
            ColumnSpec(
                id=col,
                heading=heading or col,
                width=analyse_treewidths.default_column_width(col),
                minwidth=analyse_treewidths.column_minwidth(col),
                anchor=analyse_treewidths.column_anchor(col),
                # stretch=False per playbook-regel (samme som TX og SB):
                # Tk's stretch-logikk overstyrer brukerens manuelle resize.
                stretch=False,
                visible_by_default=col in default_visible,
                pinned=col in pinned_set,
                sortable=True,
            )
        )
    return specs


def build_sb_column_specs(
    *,
    year: Optional[int] = None,
):
    """Returner ColumnSpec-liste for SB-treet i Analyse-fanen.

    Brukes av page_analyse_ui_panels når SB-treet wrappes med
    ManagedTreeview. Overskrifter kommer fra analysis_heading (felles
    vokabular, årsavhengig), bredder fra analyse_sb_tree._SB_COL_WIDTHS.
    Pinned = Konto + Kontonavn, matcher tidligere SB_PINNED_COLS.
    """
    from src.shared.ui.managed_treeview import ColumnSpec

    try:
        import page_analyse_sb as _sb
    except Exception:
        return []

    try:
        from page_analyse_columns import analysis_heading
    except Exception:
        analysis_heading = lambda c, year=None: c  # type: ignore[assignment]

    default_order = list(_sb.SB_COLS)
    default_visible = set(getattr(_sb, "SB_DEFAULT_VISIBLE", _sb.SB_COLS))
    numeric_cols = set(_sb._SB_NUMERIC_COLS)
    center_cols = set(_sb._SB_CENTER_COLS)
    col_widths = _sb._SB_COL_WIDTHS
    pinned_set = set(SB_PINNED_COLS)

    specs = []
    for col in default_order:
        if col in numeric_cols:
            anchor = "e"
        elif col in center_cols:
            anchor = "center"
        else:
            anchor = "w"
        try:
            heading = analysis_heading(col, year=year)
        except Exception:
            heading = col
        specs.append(
            ColumnSpec(
                id=col,
                heading=heading,
                width=int(col_widths.get(col, 100)),
                minwidth=40,
                anchor=anchor,
                # Ingen kolonne stretches — samme regel som TX-treet:
                # stretch=True overstyrer brukerens manuelle resize ved
                # neste layout-runde og lar kolonnen "sprette tilbake".
                stretch=False,
                visible_by_default=col in default_visible,
                pinned=col in pinned_set,
                sortable=True,
            )
        )
    return specs


def build_tx_column_specs(
    *,
    tx_cols_default: Sequence[str],
    pinned_cols: Sequence[str] = ("Konto", "Kontonavn"),
    optional_cols: Sequence[str] = (),
):
    """Returner ColumnSpec-liste for TX-treet.

    Brukes av page_analyse_ui_panels når TX-treet opprettes med
    ManagedTreeview (drag-n-drop, kolonnevelger, preferences). Bredder/
    ankre kommer fra analyse_treewidths-heuristikken, som er samme kilde
    som den tidligere manuelle oppsett-løkken i configure_tx_tree_columns
    brukte.

    Kolonner i ``optional_cols`` får ``visible_by_default=False`` slik at
    de er tilgjengelige i kolonnevelgeren men ikke synlige automatisk.
    """
    from src.shared.ui.managed_treeview import ColumnSpec
    import analyse_treewidths

    pinned_set = set(pinned_cols)
    optional_set = set(optional_cols)
    # Heading-overrides for konsistens med pivot-siden (RL-mode bruker
    # "Nr" som heading for regnr-kolonnen — samme bør gjelde i TX-treet).
    # Bilag_PDF vises som binders-emoji (📎) for kompakthet — kolonnen
    # er ren markør (✓ / tom).
    _HEADING_OVERRIDES = {"Regnr": "Nr", "Bilag_PDF": "📎"}
    # Per-kolonne anchor-override (center for markør-kolonner).
    _ANCHOR_OVERRIDES = {"Bilag_PDF": "center"}
    # Per-kolonne bredde-override (smal markør-kolonne).
    _WIDTH_OVERRIDES = {"Bilag_PDF": 42}
    specs = []
    for col in tx_cols_default:
        specs.append(
            ColumnSpec(
                id=col,
                heading=_HEADING_OVERRIDES.get(col, col),
                width=_WIDTH_OVERRIDES.get(col, analyse_treewidths.default_column_width(col)),
                minwidth=analyse_treewidths.column_minwidth(col),
                anchor=_ANCHOR_OVERRIDES.get(col, analyse_treewidths.column_anchor(col)),
                # Ingen kolonne skal stretche. Når en kolonne har stretch=True
                # vil Tk fylle ledig plass med den, og brukerens manuelle
                # resize blir overstyrt av neste layout-runde — kolonnen
                # "spretter tilbake" til opprinnelig størrelse. Tom plass på
                # høyre i brede vinduer er akseptabelt; brukeren vil heller
                # ha kontroll over kolonnebreddene.
                stretch=False,
                visible_by_default=col not in optional_set,
                pinned=col in pinned_set,
                sortable=True,
            )
        )
    return specs


# =====================================================================
# TX-kolonnepreferanser
# =====================================================================

def load_tx_columns_from_preferences(*, page: Any) -> None:
    """Last inn kolonneoppsett for transaksjonslisten fra preferences."""
    try:
        stored_order = preferences.get("analyse.tx_cols.order", None)
        stored_visible = preferences.get("analyse.tx_cols.visible", None)
    except Exception:
        stored_order = None
        stored_visible = None

    order = stored_order if isinstance(stored_order, list) else list(page.TX_COLS_DEFAULT)
    visible = stored_visible if isinstance(stored_visible, list) else list(page.TX_COLS_DEFAULT)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=None,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)


def persist_tx_columns_to_preferences(*, page: Any) -> None:
    try:
        preferences.set("analyse.tx_cols.order", list(page._tx_cols_order))
        preferences.set("analyse.tx_cols.visible", list(page.TX_COLS))
    except Exception:
        pass


def get_all_tx_columns_for_chooser(*, page: Any) -> List[str]:
    import pandas as pd
    cols: List[str] = []
    cols.extend(getattr(page, "_tx_cols_order", []))
    cols.extend(list(page.TX_COLS_DEFAULT))

    df = page._df_filtered if isinstance(page._df_filtered, pd.DataFrame) else page.dataset
    if isinstance(df, pd.DataFrame):
        for c in df.columns:
            try:
                name = str(c)
            except Exception:
                continue
            if not name or name.startswith("_"):
                continue
            cols.append(name)

    return analyse_columns.unique_preserve(cols, canonicalize=True)


def apply_tx_column_config(*, page: Any, order: List[str], visible: List[str],
                           all_cols: Optional[List[str]] = None) -> None:
    all_cols = all_cols or get_all_tx_columns_for_chooser(page=page)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=all_cols,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)

    persist_tx_columns_to_preferences(page=page)

    configure_tx_tree_columns(page=page)
    page._refresh_transactions_view()


def open_tx_column_chooser(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    try:
        from views_column_chooser import open_column_chooser
    except Exception:
        return

    all_cols = get_all_tx_columns_for_chooser(page=page)
    current_visible = list(getattr(page, "TX_COLS", page.TX_COLS_DEFAULT))
    initial_order = list(getattr(page, "_tx_cols_order", all_cols))

    res = open_column_chooser(
        page,
        all_cols=all_cols,
        visible_cols=current_visible,
        initial_order=initial_order,
        default_visible_cols=list(page.TX_COLS_DEFAULT),
        default_order=list(page.TX_COLS_DEFAULT),
    )
    if not res:
        return

    order, visible = res
    if not isinstance(order, list) or not isinstance(visible, list):
        return

    apply_tx_column_config(page=page, order=order, visible=visible, all_cols=all_cols)


def reset_tx_columns_to_default(*, page: Any) -> None:
    apply_tx_column_config(
        page=page,
        order=list(page.TX_COLS_DEFAULT),
        visible=list(page.TX_COLS_DEFAULT),
    )


# =====================================================================
# SB-kolonnepreferanser (Saldobalansekontoer-visning)
# =====================================================================

# SB-pinned kolonner (kan ikke skjules eller flyttes fra starten)
SB_PINNED_COLS = ("Konto", "Kontonavn")

# Dynamiske kolonner som skjules midlertidig når fjorårsdata mangler,
# men der brukerens preferanse ikke slettes.
SB_DYNAMIC_COLS = ("UB_fjor", "Endring_fjor", "Endring_pct")


def _sb_defaults(page: Any) -> tuple[list[str], list[str]]:
    """Returner (alle SB-kolonner, kanonisk standard synlig-sett)."""
    try:
        import page_analyse_sb as _sb
        all_cols = list(_sb.SB_COLS)
        default_visible = list(getattr(_sb, "SB_DEFAULT_VISIBLE", _sb.SB_COLS))
    except Exception:
        all_cols = list(SB_PINNED_COLS)
        default_visible = list(SB_PINNED_COLS)
    # Sørg for at pinned alltid ligger først i default_visible
    for p in reversed(SB_PINNED_COLS):
        if p not in default_visible:
            default_visible.insert(0, p)
    return all_cols, default_visible


def _sb_ub_fjor_available(page: Any) -> bool:
    """Har SB-visningen fjorårsdata tilgjengelig for UB_fjor-kolonnen?"""
    import pandas as pd
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev, pd.DataFrame) and not sb_prev.empty:
        return True
    return False


def load_sb_columns_from_preferences(*, page: Any) -> None:
    """Last inn SB-kolonneoppsett fra preferences og normaliser."""
    try:
        stored_order = preferences.get("analyse.sb_cols.order", None)
        stored_visible = preferences.get("analyse.sb_cols.visible", None)
    except Exception:
        stored_order = None
        stored_visible = None

    default_order, default_visible = _sb_defaults(page)

    # Migrer gamle preferanser til ny kanonisk standard (UB <år> + UB <år-1>
    # + Endring + Endring %) når stored_visible mangler de nye komparative
    # kolonnene men inneholder legacy-kolonner (IB/Endring intern).
    if isinstance(stored_visible, list) and stored_visible:
        has_new_canonical = any(
            c in stored_visible for c in ("Endring_fjor", "Endring_pct")
        )
        has_legacy_intern = any(c in stored_visible for c in ("IB", "Endring"))
        if has_legacy_intern and not has_new_canonical:
            stored_visible = None

    order = stored_order if isinstance(stored_order, list) else list(default_order)
    visible = stored_visible if isinstance(stored_visible, list) else list(default_visible)

    # Auto-migrer: hvis en kolonne fra default_visible mangler både i order
    # og visible, ble preferansen lagret før den kolonnen var standard. Legg
    # den inn (siste posisjon) slik at brukeren ser den uten å måtte åpne
    # kolonnevelgeren manuelt. Bevarer kolonner brukeren bevisst har skjult
    # (de er fortsatt i order men ikke i visible).
    for col in default_visible:
        if col not in order and col not in visible:
            order.append(col)
            visible.append(col)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=default_order,
        pinned=SB_PINNED_COLS,
        required=SB_PINNED_COLS,
    )

    page._sb_cols_order = list(order_clean)
    page._sb_cols_visible = list(visible_order)


def persist_sb_columns_to_preferences(*, page: Any) -> None:
    try:
        preferences.set("analyse.sb_cols.order", list(getattr(page, "_sb_cols_order", [])))
        preferences.set("analyse.sb_cols.visible", list(getattr(page, "_sb_cols_visible", [])))
    except Exception:
        pass


def apply_sb_column_config(*, page: Any, order: List[str], visible: List[str]) -> None:
    default_order, _ = _sb_defaults(page)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=default_order,
        pinned=SB_PINNED_COLS,
        required=SB_PINNED_COLS,
    )

    page._sb_cols_order = list(order_clean)
    page._sb_cols_visible = list(visible_order)

    persist_sb_columns_to_preferences(page=page)
    configure_sb_tree_columns(page=page)


def open_sb_column_chooser(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return
    try:
        from views_column_chooser import open_column_chooser
    except Exception:
        return

    default_order, default_visible = _sb_defaults(page)
    current_visible = list(getattr(page, "_sb_cols_visible", default_visible))
    initial_order = list(getattr(page, "_sb_cols_order", default_order))

    res = open_column_chooser(
        page,
        all_cols=list(default_order),
        visible_cols=current_visible,
        initial_order=initial_order,
        default_visible_cols=list(default_visible),
        default_order=list(default_order),
    )
    if not res:
        return
    order, visible = res
    if not isinstance(order, list) or not isinstance(visible, list):
        return
    apply_sb_column_config(page=page, order=order, visible=visible)


def reset_sb_columns_to_default(*, page: Any) -> None:
    default_order, default_visible = _sb_defaults(page)
    apply_sb_column_config(page=page, order=default_order, visible=default_visible)


def configure_sb_tree_columns(*, page: Any) -> None:
    """Sett displaycolumns + bredder på SB-treet basert på preferanser.

    UB_fjor skjules dynamisk når fjorårsdata mangler, men brukerens
    preferanse beholdes.
    """
    if not getattr(page, "_tk_ok", False):
        return
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return

    # Lazy import for å unngå sirkularitet med page_analyse_columns-fasaden.
    from page_analyse_columns import _active_year, analysis_heading

    # ManagedTreeview-flyt — SB-treet er allerede satt opp ved init.
    # Her oppdaterer vi bare det som kan endre seg når brukeren veksler
    # inn til SB-visningen:
    #   (a) årsavhengige heading-tekster (analysis_heading avhenger av
    #       aktiv sesjon-år),
    #   (b) dynamisk UB_fjor-skjul via tree["displaycolumns"] når
    #       fjorårsdata mangler — brukerens lagrede synlighets-
    #       preferanse forblir urørt i column_manager.
    # Vi rører IKKE tree["columns"] eller kolonne-bredder her, for å
    # unngå å ødelegge data-rader som akkurat er (eller blir) satt inn
    # via refresh_sb_view.
    managed = getattr(page, "_sb_managed", None)
    if managed is not None:
        year = None
        try:
            year = _active_year()
        except Exception:
            pass
        try:
            import page_analyse_sb as _sb_mod
            for col in _sb_mod.SB_COLS:
                try:
                    tree.heading(col, text=analysis_heading(col, year=year))
                except Exception:
                    pass
        except Exception:
            pass
        has_prev = _sb_ub_fjor_available(page)
        try:
            visible_order = list(managed.column_manager.visible_cols)
            if not has_prev:
                visible_order = [c for c in visible_order if c not in SB_DYNAMIC_COLS]
            tree["displaycolumns"] = tuple(visible_order)
        except Exception:
            pass
        return

    try:
        import page_analyse_sb as _sb
    except Exception:
        return

    default_order, _ = _sb_defaults(page)
    order = list(getattr(page, "_sb_cols_order", default_order))
    visible_pref = list(getattr(page, "_sb_cols_visible", default_order))

    has_prev = _sb_ub_fjor_available(page)
    effective_visible = [
        c for c in visible_pref
        if not (c in SB_DYNAMIC_COLS and not has_prev)
    ]

    try:
        tree.configure(columns=tuple(default_order))
        tree["displaycolumns"] = tuple(effective_visible)
    except Exception:
        return

    widths_pref = getattr(page, "_sb_col_widths", None) or {}
    year = _active_year()

    for c in default_order:
        heading = analysis_heading(c, year=year)
        try:
            tree.heading(c, text=heading)
        except Exception:
            pass

        if c in _sb._SB_NUMERIC_COLS:
            anchor = "e"
        elif c in _sb._SB_CENTER_COLS:
            anchor = "center"
        else:
            anchor = "w"
        stretch = (c == "Kontonavn")

        default_width = _sb._SB_COL_WIDTHS.get(c, 100)
        width = int(widths_pref.get(c, default_width))
        try:
            tree.column(c, width=width, minwidth=40, anchor=anchor, stretch=stretch)
        except Exception:
            pass
